import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from dependencias import pegar_sessao, verificar_token, verificar_admin
from schemas import (
    CategoriaSchema, ResponseCategoriaSchema,
    PorcaoSchema, ResponsePorcaoSchema,
    PedidoSchema, ResponsePedidoSchema,
    ItemPedidoSchema, FinalizarPedidoSchema,
)
from models import (
    Adicional, Categoria, Porcao, Pedido, ItemPedido, VariacaoProduto,
    Bairro, Usuario, StatusPedido,
)

logger = logging.getLogger("order_routes")

order_router = APIRouter(prefix="/Pedidos", tags=["Pedidos"])


def _gerar_codigo(pedido_id: int) -> str:
    return str(1000 + pedido_id)


def _verificar_persistencia(pedido_id: int, session: Session) -> Pedido:
    pedido_salvo = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido_salvo:
        raise HTTPException(status_code=500, detail="Falha ao confirmar pedido no banco")
    return pedido_salvo


# ============================================================
# PEDIDOS — CRIAÇÃO PÚBLICA
# ============================================================

@order_router.post("/pedidos", response_model=ResponsePedidoSchema, status_code=201)
async def criar_pedido(
    dados: PedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    valor_entrega = 0.0

    if dados.bairro_id:
        bairro = session.query(Bairro).filter(
            Bairro.id == dados.bairro_id,
            Bairro.ativo == True
        ).first()

        if not bairro:
            raise HTTPException(status_code=404, detail="Bairro não encontrado")

        valor_entrega = bairro.valor_entrega

    pedido = Pedido(
        nome_cliente    = dados.nome_cliente.strip(),
        telefone        = dados.telefone.strip() if dados.telefone else None,  # 🔥 corrigido
        endereco        = dados.endereco.strip() if dados.endereco else None,
        tipo_pedido     = dados.tipo_pedido,
        bairro_id       = dados.bairro_id,
        valor_entrega   = valor_entrega,
        observacoes     = dados.observacoes,
        status          = StatusPedido.PENDENTE,
        usuario_id      = dados.id_usuario,
        forma_pagamento = dados.forma_pagamento,  # 🔥 corrigido
    )

    try:
        session.add(pedido)
        session.flush()
        pedido.codigo = _gerar_codigo(pedido.id)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error("Erro ao criar pedido: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao salvar pedido")

    return _verificar_persistencia(pedido.id, session)


# ============================================================
# ADICIONAR ITEM
# ============================================================

@order_router.post("/pedido/adicionar-item/{pedido_id}")
async def adicionar_item(
    pedido_id: int,
    dados: ItemPedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if pedido.status != StatusPedido.PENDENTE:
        raise HTTPException(status_code=400, detail="Pedido não pode ser alterado")

    preco_unitario = dados.preco_unitario
    variacao_nome = None

    if dados.variacao_id:
        variacao = session.query(VariacaoProduto).filter(
            VariacaoProduto.id == dados.variacao_id
        ).first()

        if not variacao:
            raise HTTPException(status_code=404, detail="Variação não encontrada")

        variacao_nome = variacao.nome
        preco_unitario += variacao.acrescimo

    adicionais_preco = 0.0
    adicionais_nomes = None

    if dados.adicionais_ids:
        nomes = []

        for aid in dados.adicionais_ids:
            adicional = session.query(Adicional).filter(Adicional.id == aid).first()

            if not adicional:
                raise HTTPException(status_code=404, detail=f"Adicional {aid} não encontrado")

            if not adicional.ativo:
                raise HTTPException(status_code=400, detail=f"{adicional.nome} indisponível")

            nomes.append(adicional.nome)
            adicionais_preco += adicional.preco

        adicionais_nomes = ", ".join(nomes)

    item = ItemPedido(
        quantidade       = dados.quantidade,
        nomedoproduto    = dados.nomedoproduto,
        variacao_nome    = variacao_nome,
        preco_unitario   = preco_unitario,
        adicionais_nomes = adicionais_nomes,
        adicionais_preco = adicionais_preco,
        observacoes      = dados.observacoes,
        pedido_id        = pedido_id,
    )

    session.add(item)
    session.flush()

    pedido.preco_total = sum(
        (i.preco_unitario + i.adicionais_preco) * i.quantidade
        for i in pedido.itens
    ) + pedido.valor_entrega

    session.commit()

    return {
        "mensagem": "Item adicionado",
        "preco_total": pedido.preco_total
    }


# ============================================================
# FINALIZAR
# ============================================================

@order_router.post("/pedido/finalizar/{pedido_id}")
async def finalizar_pedido(
    pedido_id: int,
    dados: FinalizarPedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()

    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    if not pedido.itens:
        raise HTTPException(status_code=400, detail="Pedido vazio")

    pedido.status = StatusPedido.FINALIZADO
    pedido.forma_pagamento = dados.forma_pagamento
    pedido.troco_para = dados.troco_para

    session.commit()
    session.refresh(pedido)

    return pedido
