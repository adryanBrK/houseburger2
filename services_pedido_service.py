"""
services/pedido_service.py v3.0.0
===================================
Correções:
  - listar_pedidos() adicionada (estava faltando — causava 500 em qualquer chamada)
  - reordenar_categorias() adicionada no service para quem quiser chamar via service
  - criar_categoria() / editar_categoria() / deletar_categoria() adicionadas
  - Todos os métodos que order_routes.py chama existem aqui
  - Adicionais via N:N (produto.adicionais) — sem ProdutoAdicional
  - SELECT FOR UPDATE em finalizar_pedido (race condition)
  - Preço lido sempre do banco (nunca do cliente)
  - Batch query para adicionais (sem N+1)
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from models import (
    Adicional, Bairro, Categoria, ItemPedido, Pedido,
    Produto, StatusPedido, VariacaoProduto,
)
from services_caixa_service import registrar_entrada, ValorInvalidoError

log = logging.getLogger("pedido_service")


# ══════════════════════════════════════════════════════════════════
# EXCEÇÕES DE DOMÍNIO
# ══════════════════════════════════════════════════════════════════

class PedidoError(Exception):
    """Base para erros de pedido."""


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


class CategoriaError(Exception):
    """Base para erros de categoria."""


class CategoriaNaoEncontradaError(CategoriaError):
    pass


class CategoriaJaExisteError(CategoriaError):
    pass


# ══════════════════════════════════════════════════════════════════
# UTILITÁRIOS INTERNOS
# ══════════════════════════════════════════════════════════════════

def _gerar_codigo(pedido_id: int) -> str:
    return str(1000 + pedido_id)


def calcular_total_pedido(pedido: Pedido) -> float:
    """
    Fórmula centralizada: Σ(preco_unitario + adicionais_preco) × qty + entrega.
    Chamada em adicionar_item e remover_item para consistência.
    """
    subtotal = sum(
        (i.preco_unitario + i.adicionais_preco) * i.quantidade
        for i in pedido.itens
    )
    return round(subtotal + pedido.valor_entrega, 2)


def _buscar_adicionais_em_lote(
    session: Session,
    ids: List[int],
) -> dict:
    """Uma query com IN — elimina N+1."""
    if not ids:
        return {}
    rows = session.query(Adicional).filter(Adicional.id.in_(ids)).all()
    return {a.id: a for a in rows}


# ══════════════════════════════════════════════════════════════════
# CATEGORIAS (service layer)
# Routers podem chamar diretamente o model, mas centralizar aqui
# permite validação consistente e testabilidade.
# ══════════════════════════════════════════════════════════════════

def criar_categoria(
    session:    Session,
    nome:       str,
    descricao:  Optional[str] = None,
    ativo:      bool = True,
    imagem_url: Optional[str] = None,
    ordem:      int = 0,
) -> Categoria:
    nome = nome.strip()
    existe = session.query(Categoria).filter(Categoria.nome == nome).first()
    if existe:
        raise CategoriaJaExisteError(f"Categoria '{nome}' já existe (id={existe.id})")

    cat = Categoria(
        nome=nome, descricao=descricao,
        ativo=ativo, imagem_url=imagem_url, ordem=ordem,
    )
    session.add(cat)
    try:
        session.commit()
        session.refresh(cat)
    except IntegrityError:
        session.rollback()
        raise CategoriaJaExisteError(f"Categoria '{nome}' já existe")
    log.info("[CatService] Criada id=%s nome=%s", cat.id, cat.nome)
    return cat


def editar_categoria(
    session:      Session,
    categoria_id: int,
    nome:         Optional[str] = None,
    descricao:    Optional[str] = None,
    ativo:        Optional[bool] = None,
    imagem_url:   Optional[str] = None,
    ordem:        Optional[int] = None,
) -> Categoria:
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise CategoriaNaoEncontradaError(f"Categoria id={categoria_id} não encontrada")

    if nome is not None:
        nome = nome.strip()
        conflito = session.query(Categoria).filter(
            Categoria.nome == nome, Categoria.id != categoria_id
        ).first()
        if conflito:
            raise CategoriaJaExisteError(f"Nome '{nome}' já usado por id={conflito.id}")
        cat.nome = nome
    if descricao  is not None: cat.descricao  = descricao
    if ativo      is not None: cat.ativo      = ativo
    if imagem_url is not None: cat.imagem_url = imagem_url
    if ordem      is not None: cat.ordem      = ordem

    session.commit()
    session.refresh(cat)
    log.info("[CatService] Editada id=%s", categoria_id)
    return cat


def deletar_categoria(session: Session, categoria_id: int) -> dict:
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise CategoriaNaoEncontradaError(f"Categoria id={categoria_id} não encontrada")
    nome = cat.nome
    session.delete(cat)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise CategoriaError(
            f"Não é possível remover '{nome}' — possui produtos vinculados. Desative-a."
        )
    log.info("[CatService] Removida id=%s nome=%s", categoria_id, nome)
    return {"mensagem": f"Categoria '{nome}' removida"}


def reordenar_categorias(session: Session, ids: List[int]) -> List[Categoria]:
    """
    Recebe lista de IDs na nova ordem.
    IDs inexistentes são ignorados silenciosamente.
    """
    if not ids:
        return session.query(Categoria).order_by(Categoria.ordem.asc()).all()

    for posicao, cat_id in enumerate(ids):
        cat = session.query(Categoria).filter(Categoria.id == cat_id).first()
        if cat is None:
            log.warning("[CatService] reordenar: id=%s não encontrado — ignorado", cat_id)
            continue
        cat.ordem = posicao

    session.commit()
    log.info("[CatService] Reordenadas: %s", ids)
    return session.query(Categoria).order_by(Categoria.ordem.asc()).all()


# ══════════════════════════════════════════════════════════════════
# PEDIDOS
# ══════════════════════════════════════════════════════════════════

def listar_pedidos(
    session:         Session,
    status_filtro:   Optional[str] = None,
    forma_pagamento: Optional[str] = None,
    tipo_pedido:     Optional[str] = None,
) -> List[Pedido]:
    """Lista pedidos com filtros opcionais. Usada por admin."""
    q = session.query(Pedido)
    if status_filtro:
        q = q.filter(Pedido.status == status_filtro.upper())
    if forma_pagamento:
        q = q.filter(Pedido.forma_pagamento == forma_pagamento.upper())
    if tipo_pedido:
        q = q.filter(Pedido.tipo_pedido == tipo_pedido.upper())
    return q.order_by(Pedido.criado_em.desc()).all()


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
    """Taxa de entrega lida do banco — nunca do cliente."""
    valor_entrega = 0.0
    if bairro_id:
        bairro = session.query(Bairro).filter(
            Bairro.id == bairro_id, Bairro.ativo == True
        ).first()
        if not bairro:
            raise PedidoError(f"Bairro id={bairro_id} não encontrado ou inativo")
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
        preco_total   = valor_entrega,
    )

    session.add(pedido)
    session.flush()
    pedido.codigo = _gerar_codigo(pedido.id)
    session.commit()

    log.info("[PedidoService] Criado #%s | %s | entrega=R$%.2f",
             pedido.codigo, nome_cliente, valor_entrega)
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
    Preço lido SEMPRE do banco (Produto.preco + variacao.acrescimo).
    Adicionais via batch query — sem N+1.
    """
    # Pedido
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise PedidoNaoEncontradoError(f"Pedido id={pedido_id} não encontrado")
    if pedido.status != StatusPedido.PENDENTE:
        raise PedidoStatusInvalidoError(
            f"Pedido já está {pedido.status} — não é possível adicionar itens"
        )

    # Produto — preço do banco + adicionais carregados junto (evita N+1 na validação)
    produto = (
        session.query(Produto)
        .options(
            joinedload(Produto.variacoes),
            joinedload(Produto.adicionais),   # necessário para validar vínculo
        )
        .filter(Produto.id == produto_id)
        .first()
    )
    if not produto:
        raise ProdutoIndisponivelError(f"Produto id={produto_id} não encontrado")
    if not produto.disponivel:
        raise ProdutoIndisponivelError(f"Produto '{produto.nome}' está indisponível")

    preco_base    = produto.preco
    variacao_nome = None

    # Variação (opcional)
    if variacao_id is not None:
        variacao = next(
            (v for v in produto.variacoes if v.id == variacao_id), None
        )
        if not variacao:
            raise VariacaoIndisponivelError(
                f"Variação id={variacao_id} não pertence ao produto id={produto_id}"
            )
        if not variacao.disponivel:
            raise VariacaoIndisponivelError(f"Variação '{variacao.nome}' indisponível")
        preco_base   += variacao.acrescimo
        variacao_nome = variacao.nome

    # Adicionais — batch query + validação de vínculo com o produto
    adicionais_nomes = None
    adicionais_preco = 0.0

    if adicionais_ids:
        # IDs dos adicionais vinculados a este produto (já carregados via joinedload)
        ids_vinculados = {a.id for a in produto.adicionais}

        mapa = _buscar_adicionais_em_lote(session, adicionais_ids)
        nomes = []
        for aid in adicionais_ids:
            ad = mapa.get(aid)
            if not ad:
                raise AdicionalInativoError(f"Adicional id={aid} não encontrado")
            # Regra crítica: adicional deve estar vinculado a este produto
            if aid not in ids_vinculados:
                raise AdicionalInativoError(
                    f"Adicional '{ad.nome}' (id={aid}) não está disponível "
                    f"para o produto '{produto.nome}' (id={produto_id})"
                )
            if not ad.ativo:
                raise AdicionalInativoError(f"Adicional '{ad.nome}' está inativo")
            nomes.append(ad.nome)
            adicionais_preco += ad.preco
        adicionais_nomes = ", ".join(nomes)

    item = ItemPedido(
        quantidade       = quantidade,
        nomedoproduto    = produto.nome,
        variacao_nome    = variacao_nome,
        preco_unitario   = round(preco_base, 2),
        adicionais_nomes = adicionais_nomes,
        adicionais_preco = round(adicionais_preco, 2),
        observacoes      = observacoes,
        pedido_id        = pedido_id,
    )
    session.add(item)
    session.flush()
    pedido.preco_total = calcular_total_pedido(pedido)
    session.commit()

    log.info("[PedidoService] Item | pedido=#%s | %s | qty=%d | R$%.2f",
             pedido.codigo, produto.nome, quantidade, preco_base)
    return item


def remover_item(
    session:    Session,
    item_id:    int,
    usuario_id: Optional[int] = None,
    is_admin:   bool          = False,
) -> dict:
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
        raise PedidoError("Acesso negado")
    if pedido.status != StatusPedido.PENDENTE:
        raise PedidoStatusInvalidoError(f"Pedido já está {pedido.status}")

    session.delete(item)
    session.flush()
    pedido.preco_total = calcular_total_pedido(pedido)
    session.commit()

    log.info("[PedidoService] Item #%d removido | pedido=#%s | total=R$%.2f",
             item_id, pedido.codigo, pedido.preco_total)
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
    SELECT FOR UPDATE: evita dupla finalização em requests simultâneos.
    Atomicidade total: pedido + caixa num único commit.
    """
    pedido = (
        session.query(Pedido)
        .filter(Pedido.id == pedido_id)
        .with_for_update()     # lock exclusivo no row — PostgreSQL serializa
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

    pedido.status          = StatusPedido.FINALIZADO
    pedido.forma_pagamento = forma_pagamento
    pedido.troco_para      = troco_para

    # Entrada no caixa — mesma sessão, sem commit interno
    registrar_entrada(
        session   = session,
        valor     = pedido.preco_total,
        descricao = f"Pedido #{pedido.codigo} | {forma_pagamento}",
        pedido_id = pedido.id,
    )

    # Commit único: pedido + caixa + movimentação
    session.commit()
    session.refresh(pedido)

    log.info("[PedidoService] Finalizado #%s | %s | R$%.2f",
             pedido.codigo, forma_pagamento, pedido.preco_total)
    return pedido


def cancelar_pedido(session: Session, pedido_id: int) -> Pedido:
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
    log.info("[PedidoService] Cancelado #%s", pedido.codigo)
    return pedido
