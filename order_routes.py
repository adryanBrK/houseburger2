from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from dependencias import pegar_sessao, verificar_token, verificar_admin
from schemas import (
    CategoriaSchema, ResponseCategoriaSchema,
    PorcaoSchema, ResponsePorcaoSchema,
    PedidoSchema, ResponsePedidoSchema,
    ItemPedidoSchema, FinalizarPedidoSchema,
)
from models import Categoria, Porcao, Pedido, ItemPedido, VariacaoProduto, Usuario

order_router = APIRouter(prefix="/Pedidos", tags=["Pedidos"])


# ============================================================
# CATEGORIAS
# ============================================================

@order_router.get("/categorias", response_model=List[ResponseCategoriaSchema], summary="Lista categorias")
async def listar_categorias(session: Session = Depends(pegar_sessao)):
    return session.query(Categoria).all()


@order_router.post(
    "/categorias",
    response_model=ResponseCategoriaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria categoria (somente admin)"
)
async def criar_categoria(
    dados: CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    nova = Categoria(nome=dados.nome, descricao=dados.descricao)
    session.add(nova)
    try:
        session.commit()
        session.refresh(nova)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Categoria já existe")
    return nova


@order_router.put(
    "/categorias/{categoria_id}",
    response_model=ResponseCategoriaSchema,
    summary="Edita categoria (somente admin)"
)
async def editar_categoria(
    categoria_id: int,
    dados: CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    cat.nome = dados.nome
    cat.descricao = dados.descricao
    if dados.ativo is not None:
        cat.ativo = dados.ativo
    session.commit()
    session.refresh(cat)
    return cat


@order_router.delete("/categorias/{categoria_id}", summary="Remove categoria (somente admin)")
async def deletar_categoria(
    categoria_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    session.delete(cat)
    session.commit()
    return {"mensagem": "Categoria removida com sucesso"}


# ============================================================
# PORÇÕES
# ============================================================

@order_router.get("/porcoes", response_model=List[ResponsePorcaoSchema], summary="Lista porções")
async def listar_porcoes(session: Session = Depends(pegar_sessao)):
    return session.query(Porcao).all()


@order_router.post(
    "/porcoes",
    response_model=ResponsePorcaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria porção (somente admin)"
)
async def criar_porcao(
    dados: PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    nova = Porcao(nome=dados.nome, preco=dados.preco)
    session.add(nova)
    try:
        session.commit()
        session.refresh(nova)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Porção com esse nome já existe")
    return nova


@order_router.put(
    "/porcoes/{porcao_id}",
    response_model=ResponsePorcaoSchema,
    summary="Edita porção (somente admin)"
)
async def editar_porcao(
    porcao_id: int,
    dados: PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    porcao = session.query(Porcao).filter(Porcao.id == porcao_id).first()
    if not porcao:
        raise HTTPException(status_code=404, detail="Porção não encontrada")
    porcao.nome  = dados.nome
    porcao.preco = dados.preco
    session.commit()
    session.refresh(porcao)
    return porcao


@order_router.delete("/porcoes/{porcao_id}", summary="Remove porção (somente admin)")
async def deletar_porcao(
    porcao_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    porcao = session.query(Porcao).filter(Porcao.id == porcao_id).first()
    if not porcao:
        raise HTTPException(status_code=404, detail="Porção não encontrada")
    session.delete(porcao)
    session.commit()
    return {"mensagem": "Porção removida com sucesso"}


# ============================================================
# PEDIDOS
# ============================================================

@order_router.post(
    "/pedidos",
    response_model=ResponsePedidoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um novo pedido"
)
async def criar_pedido(
    dados: PedidoSchema,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    if not usuario.admin and usuario.id != dados.id_usuario:
        raise HTTPException(status_code=403, detail="Você só pode criar pedidos para si mesmo")

    pedido = Pedido(usuario_id=dados.id_usuario)
    session.add(pedido)
    session.commit()
    session.refresh(pedido)
    return pedido


@order_router.get(
    "/listar",
    response_model=List[ResponsePedidoSchema],
    summary="Lista todos os pedidos (somente admin)"
)
async def listar_todos_pedidos(
    status_filtro:   str = None,
    forma_pagamento: str = None,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    q = session.query(Pedido)
    if status_filtro:
        q = q.filter(Pedido.status == status_filtro.upper())
    if forma_pagamento:
        q = q.filter(Pedido.forma_pagamento == forma_pagamento.upper())
    return q.order_by(Pedido.criado_em.desc()).all()


@order_router.get(
    "/meus-pedidos",
    response_model=List[ResponsePedidoSchema],
    summary="Lista os pedidos do usuário logado"
)
async def listar_meus_pedidos(
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    return (
        session.query(Pedido)
        .filter(Pedido.usuario_id == usuario.id)
        .order_by(Pedido.criado_em.desc())
        .all()
    )


@order_router.get(
    "/pedido/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Visualiza um pedido"
)
async def visualizar_pedido(
    pedido_id: int,
    session:  Session = Depends(pegar_sessao),
    usuario:  Usuario = Depends(verificar_token),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return pedido


@order_router.post(
    "/pedido/adicionar-item/{pedido_id}",
    summary="Adiciona item ao pedido. Se o produto tiver variações, envie variacao_id."
)
async def adicionar_item(
    pedido_id: int,
    dados:   ItemPedidoSchema,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    if pedido.status != "PENDENTE":
        raise HTTPException(status_code=400, detail=f"Pedido já está {pedido.status}")

    # Se enviou variacao_id, busca a variação e calcula o preço real
    variacao_nome  = None
    preco_unitario = dados.preco_unitario

    if dados.variacao_id is not None:
        variacao = session.query(VariacaoProduto).filter(VariacaoProduto.id == dados.variacao_id).first()
        if not variacao:
            raise HTTPException(status_code=404, detail="Variação não encontrada")
        if not variacao.disponivel:
            raise HTTPException(status_code=400, detail=f"Variação '{variacao.nome}' está indisponível")

        variacao_nome  = variacao.nome
        preco_unitario = dados.preco_unitario + variacao.acrescimo  # preço base + acréscimo

    item = ItemPedido(
        quantidade=dados.quantidade,
        nomedoproduto=dados.nomedoproduto,
        variacao_nome=variacao_nome,
        preco_unitario=preco_unitario,
        pedido_id=pedido_id,
    )
    session.add(item)
    session.flush()

    pedido.preco_total = sum(i.preco_unitario * i.quantidade for i in pedido.itens)
    session.commit()
    session.refresh(item)

    return {
        "mensagem":      "Item adicionado com sucesso",
        "item_id":       item.id,
        "variacao":      variacao_nome,
        "preco_unitario": preco_unitario,
        "preco_total":   pedido.preco_total,
    }


@order_router.delete(
    "/pedido/remover-item/{item_id}",
    summary="Remove um item do pedido"
)
async def remover_item(
    item_id: int,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    item = session.query(ItemPedido).filter(ItemPedido.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    pedido = item.pedido
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    if pedido.status != "PENDENTE":
        raise HTTPException(status_code=400, detail=f"Pedido já está {pedido.status}")

    session.delete(item)
    session.flush()
    pedido.preco_total = sum(i.preco_unitario * i.quantidade for i in pedido.itens)
    session.commit()

    return {
        "mensagem":    "Item removido com sucesso",
        "preco_total": pedido.preco_total,
        "itens":       len(pedido.itens),
    }


@order_router.post(
    "/pedido/finalizar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Finaliza o pedido informando a forma de pagamento: DINHEIRO | PIX | CARTAO"
)
async def finalizar_pedido(
    pedido_id: int,
    dados:   FinalizarPedidoSchema,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    if pedido.status != "PENDENTE":
        raise HTTPException(status_code=400, detail=f"Pedido já está {pedido.status}")
    if not pedido.itens:
        raise HTTPException(status_code=400, detail="Não é possível finalizar pedido sem itens")

    pedido.status          = "FINALIZADO"
    pedido.forma_pagamento = dados.forma_pagamento   # DINHEIRO | PIX | CARTAO
    session.commit()
    session.refresh(pedido)
    return pedido


@order_router.post(
    "/pedido/cancelar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Cancela um pedido"
)
async def cancelar_pedido(
    pedido_id: int,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    if pedido.status == "CANCELADO":
        raise HTTPException(status_code=400, detail="Pedido já está cancelado")
    if pedido.status == "FINALIZADO":
        raise HTTPException(status_code=400, detail="Pedido finalizado não pode ser cancelado")

    pedido.status = "CANCELADO"
    session.commit()
    session.refresh(pedido)
    return pedido