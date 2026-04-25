"""
services/pedido_service.py
===========================
Camada de serviço para o ciclo de vida de pedidos.

Responsabilidades:
  - Toda regra de negócio de pedidos fica aqui
  - Sem dependência de FastAPI
  - Levanta exceções de domínio que os routers traduzem
  - Lê preços SEMPRE do banco — nunca confia em valores do cliente
  - Garante atomicidade via transação única com o caixa

Segurança de concorrência:
  finalizar_pedido() usa SELECT FOR UPDATE no pedido.
  Isso garante que dois requests simultâneos para o mesmo pedido_id
  não consigam ambos ler status=PENDENTE e processar duas finalizações.
  O segundo request ficará bloqueado até o primeiro commitar,
  então lerá status=FINALIZADO e retornará erro 400.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload

from models import (
    Adicional, Bairro, ItemPedido, Pedido,
    Produto, StatusPedido, VariacaoProduto,
)
from services_caixa_service import registrar_entrada, ValorInvalidoError

log = logging.getLogger("pedido_service")


# ══════════════════════════════════════════════════════════════════
# EXCEÇÕES DE DOMÍNIO
# ══════════════════════════════════════════════════════════════════

class PedidoError(Exception):
    """Erro de regra de negócio de pedidos."""


class PedidoNaoEncontradoError(PedidoError):
    pass


class PedidoStatusInvalidoError(PedidoError):
    pass


class PedidoSemItensError(PedidoError):
    pass


class ProdutoIndisponivelError(PedidoError):
    pass


class VariacaoIndisponivelError(PedidoError):
    pass


class AdicionalInativoError(PedidoError):
    pass


# ══════════════════════════════════════════════════════════════════
# UTILITÁRIOS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _gerar_codigo(pedido_id: int) -> str:
    """Código legível exibido para o cliente (ex: #1042)."""
    return str(1000 + pedido_id)


def calcular_total_pedido(pedido: Pedido) -> float:
    """
    Recalcula o total do pedido a partir dos itens em memória.

    Centralizado aqui para não duplicar a fórmula em adicionar_item,
    remover_item e qualquer lugar futuro que precise recalcular.

    Fórmula:
        Σ (preco_unitario + adicionais_preco) × quantidade  +  valor_entrega
    """
    subtotal = sum(
        (item.preco_unitario + item.adicionais_preco) * item.quantidade
        for item in pedido.itens
    )
    return round(subtotal + pedido.valor_entrega, 2)


def _buscar_adicionais_em_lote(
    session:        Session,
    adicionais_ids: List[int],
) -> dict[int, Adicional]:
    """
    Busca todos os adicionais numa única query (evita N+1).
    Retorna dict {id: Adicional}.
    """
    if not adicionais_ids:
        return {}
    rows = (
        session.query(Adicional)
        .filter(Adicional.id.in_(adicionais_ids))
        .all()
    )
    return {a.id: a for a in rows}


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA DO SERVIÇO
# ══════════════════════════════════════════════════════════════════

def criar_pedido(
    session:      Session,
    nome_cliente: str,
    telefone:     str,
    tipo_pedido:  str,
    bairro_id:    Optional[int] = None,
    endereco:     Optional[str] = None,
    observacoes:  Optional[str] = None,
    usuario_id:   Optional[int] = None,
) -> Pedido:
    """
    Cria um novo pedido no status PENDENTE.

    - Taxa de entrega lida do banco (nunca do cliente)
    - Commit é feito aqui (criação é operação independente)

    Levanta:
        PedidoError — se bairro_id informado não existir ou estiver inativo
    """
    valor_entrega = 0.0
    if bairro_id:
        bairro = session.query(Bairro).filter(
            Bairro.id == bairro_id,
            Bairro.ativo == True,
        ).first()
        if not bairro:
            raise PedidoError(
                f"Bairro id={bairro_id} não encontrado ou inativo"
            )
        valor_entrega = bairro.valor_entrega

    pedido = Pedido(
        nome_cliente  = nome_cliente.strip(),
        telefone      = telefone.strip(),
        endereco      = endereco.strip() if endereco else None,
        tipo_pedido   = tipo_pedido,
        bairro_id     = bairro_id,
        valor_entrega = valor_entrega,
        observacoes   = observacoes,
        status        = StatusPedido.PENDENTE,
        usuario_id    = usuario_id,
        preco_total   = valor_entrega,  # sem itens ainda; inclui só a taxa
    )

    session.add(pedido)
    session.flush()                    # gera o ID sem commitar
    pedido.codigo = _gerar_codigo(pedido.id)
    session.commit()

    log.info(
        "[PedidoService] Criado pedido #%s | cliente=%s | tipo=%s | entrega=R$%.2f",
        pedido.codigo, nome_cliente, tipo_pedido, valor_entrega,
    )
    return pedido


def adicionar_item(
    session:        Session,
    pedido_id:      int,
    produto_id:     int,
    quantidade:     int,
    variacao_id:    Optional[int]   = None,
    adicionais_ids: Optional[List[int]] = None,
    observacoes:    Optional[str]   = None,
) -> ItemPedido:
    """
    Adiciona item ao pedido lendo preços SEMPRE do banco.

    Diferença crítica em relação à versão anterior:
      A versão anterior aceitava preco_unitario do cliente (campo no schema).
      Aqui o preço vem de Produto.preco + VariacaoProduto.acrescimo — imutável.
      Isso evita que o cliente envie preco=0.01 para burlar o sistema.

    Proteção N+1:
      Adicionais são buscados em lote (uma query com IN) em vez de
      uma query por adicional dentro de um loop.

    Levanta:
        PedidoNaoEncontradoError
        PedidoStatusInvalidoError
        ProdutoIndisponivelError
        VariacaoIndisponivelError
        AdicionalInativoError
    """
    # ── 1. Pedido
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise PedidoNaoEncontradoError(f"Pedido id={pedido_id} não encontrado")
    if pedido.status != StatusPedido.PENDENTE:
        raise PedidoStatusInvalidoError(
            f"Pedido já está {pedido.status} — não é possível adicionar itens"
        )

    # ── 2. Produto — preço lido do banco
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise ProdutoIndisponivelError(f"Produto id={produto_id} não encontrado")
    if not produto.disponivel:
        raise ProdutoIndisponivelError(f"Produto '{produto.nome}' está indisponível")

    preco_base    = produto.preco
    variacao_nome = None

    # ── 3. Variação (opcional) — acréscimo lido do banco
    if variacao_id is not None:
        variacao = (
            session.query(VariacaoProduto)
            .filter(
                VariacaoProduto.id         == variacao_id,
                VariacaoProduto.produto_id == produto_id,
            )
            .first()
        )
        if not variacao:
            raise VariacaoIndisponivelError(
                f"Variação id={variacao_id} não encontrada para produto id={produto_id}"
            )
        if not variacao.disponivel:
            raise VariacaoIndisponivelError(
                f"Variação '{variacao.nome}' está indisponível"
            )
        preco_base    += variacao.acrescimo
        variacao_nome  = variacao.nome

    # ── 4. Adicionais — busca em lote (única query com IN, evita N+1)
    adicionais_nomes = None
    adicionais_preco = 0.0

    if adicionais_ids:
        mapa = _buscar_adicionais_em_lote(session, adicionais_ids)

        nomes = []
        for aid in adicionais_ids:
            adicional = mapa.get(aid)
            if adicional is None:
                raise AdicionalInativoError(f"Adicional id={aid} não encontrado")
            if not adicional.ativo:
                raise AdicionalInativoError(
                    f"Adicional '{adicional.nome}' está inativo"
                )
            nomes.append(adicional.nome)
            adicionais_preco += adicional.preco

        adicionais_nomes = ", ".join(nomes)

    # ── 5. Criar item
    item = ItemPedido(
        quantidade       = quantidade,
        nomedoproduto    = produto.nome,   # snapshot do nome no momento do pedido
        variacao_nome    = variacao_nome,
        preco_unitario   = round(preco_base, 2),
        adicionais_nomes = adicionais_nomes,
        adicionais_preco = round(adicionais_preco, 2),
        observacoes      = observacoes,
        pedido_id        = pedido_id,
    )
    session.add(item)
    session.flush()

    # ── 6. Recalcular total usando a função centralizada
    pedido.preco_total = calcular_total_pedido(pedido)
    session.commit()

    log.info(
        "[PedidoService] Item adicionado | pedido=#%s | produto=%s | qty=%d"
        " | unitario=R$%.2f | adicionais=R$%.2f | total=R$%.2f",
        pedido.codigo, produto.nome, quantidade,
        preco_base, adicionais_preco, pedido.preco_total,
    )
    return item


def remover_item(
    session: Session,
    item_id: int,
    usuario_id: Optional[int] = None,
    is_admin:   bool          = False,
) -> dict:
    """
    Remove item do pedido e recalcula o total.

    Levanta:
        PedidoNaoEncontradoError
        PedidoStatusInvalidoError
        PedidoError — acesso negado
    """
    item = (
        session.query(ItemPedido)
        .options(joinedload(ItemPedido.pedido))
        .filter(ItemPedido.id == item_id)
        .first()
    )
    if not item:
        raise PedidoNaoEncontradoError(f"Item id={item_id} não encontrado")

    pedido = item.pedido

    if not is_admin and usuario_id != pedido.usuario_id:
        raise PedidoError("Acesso negado — você não tem permissão para remover este item")

    if pedido.status != StatusPedido.PENDENTE:
        raise PedidoStatusInvalidoError(
            f"Pedido já está {pedido.status} — não é possível remover itens"
        )

    session.delete(item)
    session.flush()
    pedido.preco_total = calcular_total_pedido(pedido)
    session.commit()

    log.info(
        "[PedidoService] Item #%d removido | pedido=#%s | total=R$%.2f",
        item_id, pedido.codigo, pedido.preco_total,
    )
    return {
        "mensagem":    "Item removido com sucesso",
        "preco_total": pedido.preco_total,
        "itens":       len(pedido.itens),
    }


def finalizar_pedido(
    session:         Session,
    pedido_id:       int,
    forma_pagamento: str,
    troco_para:      Optional[float] = None,
) -> Pedido:
    """
    Finaliza o pedido e registra entrada no caixa numa única transação.

    Proteção contra race condition:
      .with_for_update() executa SELECT ... FOR UPDATE no PostgreSQL.
      Se dois requests chegarem simultaneamente para o mesmo pedido_id,
      o banco serializa: apenas um adquire o lock, o outro espera.
      Quando o segundo adquire o lock, o pedido já está FINALIZADO
      e levanta PedidoStatusInvalidoError — sem dupla finalização.

    Atomicidade:
      registrar_entrada() não faz commit.
      session.commit() aqui persiste tudo (pedido + caixa + movimentação)
      numa única transação. Se qualquer parte falhar → rollback total.

    Levanta:
        PedidoNaoEncontradoError
        PedidoStatusInvalidoError
        PedidoSemItensError
        ValorInvalidoError — se preco_total <= 0 (pedido sem valor)
    """
    # SELECT FOR UPDATE — lock exclusivo no registro
    pedido = (
        session.query(Pedido)
        .filter(Pedido.id == pedido_id)
        .with_for_update()
        .first()
    )
    if not pedido:
        raise PedidoNaoEncontradoError(f"Pedido id={pedido_id} não encontrado")

    if pedido.status != StatusPedido.PENDENTE:
        raise PedidoStatusInvalidoError(
            f"Pedido já está {pedido.status} — não é possível finalizar novamente"
        )

    if not pedido.itens:
        raise PedidoSemItensError("Não é possível finalizar pedido sem itens")

    # Atualizar pedido
    pedido.status          = StatusPedido.FINALIZADO
    pedido.forma_pagamento = forma_pagamento
    pedido.troco_para      = troco_para

    # Registrar entrada no caixa — mesma transação, sem commit interno
    registrar_entrada(
        session   = session,
        valor     = pedido.preco_total,
        descricao = f"Pedido #{pedido.codigo} | {forma_pagamento}",
        pedido_id = pedido.id,
    )

    # Commit único: pedido + caixa + movimentação
    session.commit()
    session.refresh(pedido)

    log.info(
        "[PedidoService] Finalizado #%s | pagamento=%s | total=R$%.2f",
        pedido.codigo, forma_pagamento, pedido.preco_total,
    )
    return pedido


def cancelar_pedido(session: Session, pedido_id: int) -> Pedido:
    """
    Cancela pedido PENDENTE.

    Levanta:
        PedidoNaoEncontradoError
        PedidoStatusInvalidoError
    """
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise PedidoNaoEncontradoError(f"Pedido id={pedido_id} não encontrado")
    if pedido.status == StatusPedido.CANCELADO:
        raise PedidoStatusInvalidoError("Pedido já está cancelado")
    if pedido.status == StatusPedido.FINALIZADO:
        raise PedidoStatusInvalidoError("Pedido finalizado não pode ser cancelado")

    pedido.status = StatusPedido.CANCELADO
    session.commit()
    session.refresh(pedido)

    log.info("[PedidoService] Cancelado pedido #%s", pedido.codigo)
    return pedido

def listar_pedidos(session: Session):
    return (
        session.query(Pedido)
        .options(joinedload(Pedido.itens))
        .order_by(Pedido.id.desc())
        .all()
    )
