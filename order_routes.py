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
    Categoria, Porcao, Pedido, ItemPedido, VariacaoProduto,
    Bairro, Usuario, StatusPedido,
)

logger = logging.getLogger("order_routes")
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

order_router = APIRouter(prefix="/Pedidos", tags=["Pedidos"])


def _gerar_codigo(pedido_id: int) -> str:
    return str(1000 + pedido_id)


def _verificar_persistencia(pedido_id: int, session: Session) -> Pedido:
    pedido_salvo = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido_salvo:
        logger.error("FALHA DE PERSISTÊNCIA — pedido %s não encontrado após commit", pedido_id)
        raise HTTPException(
            status_code=500,
            detail=(
                "Pedido criado mas não confirmado no banco de dados. "
                "Verifique a conexão com o PostgreSQL e tente novamente."
            ),
        )
    logger.info("✅ Persistência confirmada — pedido #%s (id=%s)", pedido_salvo.codigo, pedido_id)
    return pedido_salvo


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
    summary="Cria categoria (somente admin)",
)
async def criar_categoria(
    dados:   CategoriaSchema,
    session: Session  = Depends(pegar_sessao),
    _:       Usuario  = Depends(verificar_admin),
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
    summary="Edita categoria (somente admin)",
)
async def editar_categoria(
    categoria_id: int,
    dados:   CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
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
    _:       Usuario = Depends(verificar_admin),
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
    summary="Cria porção (somente admin)",
)
async def criar_porcao(
    dados:   PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
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
    summary="Edita porção (somente admin)",
)
async def editar_porcao(
    porcao_id: int,
    dados:   PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
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
    _:       Usuario = Depends(verificar_admin),
):
    porcao = session.query(Porcao).filter(Porcao.id == porcao_id).first()
    if not porcao:
        raise HTTPException(status_code=404, detail="Porção não encontrada")
    session.delete(porcao)
    session.commit()
    return {"mensagem": "Porção removida com sucesso"}


# ============================================================
# PEDIDOS — CRIAÇÃO PÚBLICA (sem login)
# ============================================================

@order_router.post(
    "/pedidos",
    response_model=ResponsePedidoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria um novo pedido (público — sem necessidade de login)",
)
async def criar_pedido(
    dados:   PedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    logger.info(
        "Novo pedido recebido | cliente: %s | tipo: %s",
        dados.nome_cliente,
        dados.tipo_pedido,
    )

    valor_entrega = 0.0
    if dados.bairro_id:
        bairro = session.query(Bairro).filter(
            Bairro.id == dados.bairro_id, Bairro.ativo == True
        ).first()
        if not bairro:
            raise HTTPException(
                status_code=404,
                detail=f"Bairro id={dados.bairro_id} não encontrado ou inativo",
            )
        valor_entrega = bairro.valor_entrega
        logger.info("Bairro: %s | taxa de entrega: R$ %.2f", bairro.nome, valor_entrega)

    pedido = Pedido(
        nome_cliente  = dados.nome_cliente.strip(),
        telefone      = dados.telefone.strip(),
        endereco      = dados.endereco.strip() if dados.endereco else None,
        tipo_pedido   = dados.tipo_pedido,
        bairro_id     = dados.bairro_id,
        valor_entrega = valor_entrega,
        observacoes   = dados.observacoes,
        status        = StatusPedido.PENDENTE,
        usuario_id    = dados.id_usuario,
    )

    try:
        session.add(pedido)
        session.flush()
        pedido.codigo = _gerar_codigo(pedido.id)
        session.commit()
        logger.info("Commit realizado | id=%s | codigo=%s", pedido.id, pedido.codigo)
    except Exception as exc:
        session.rollback()
        logger.error("Erro ao criar pedido: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao salvar pedido: {str(exc)}",
        )

    return _verificar_persistencia(pedido.id, session)


# ============================================================
# PEDIDOS — ADMIN
# ============================================================

@order_router.get(
    "/listar",
    response_model=List[ResponsePedidoSchema],
    summary="Lista todos os pedidos (somente admin)",
)
async def listar_todos_pedidos(
    status_filtro:    Optional[str] = None,
    forma_pagamento:  Optional[str] = None,
    tipo_pedido:      Optional[str] = None,
    session: Session  = Depends(pegar_sessao),
    _:       Usuario  = Depends(verificar_admin),
):
    q = session.query(Pedido)
    if status_filtro:
        q = q.filter(Pedido.status == status_filtro.upper())
    if forma_pagamento:
        q = q.filter(Pedido.forma_pagamento == forma_pagamento.upper())
    if tipo_pedido:
        q = q.filter(Pedido.tipo_pedido == tipo_pedido.upper())
    return q.order_by(Pedido.criado_em.desc()).all()


@order_router.get(
    "/meus-pedidos",
    response_model=List[ResponsePedidoSchema],
    summary="Lista os pedidos do usuário logado",
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
    summary="Visualiza um pedido (admin ou dono)",
)
async def visualizar_pedido(
    pedido_id: int,
    session:   Session = Depends(pegar_sessao),
    usuario:   Usuario = Depends(verificar_token),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if not usuario.admin and usuario.id != pedido.usuario_id:
        raise HTTPException(status_code=403, detail="Acesso negado")
    return pedido


@order_router.get(
    "/buscar/{codigo}",
    response_model=ResponsePedidoSchema,
    summary="Busca pedido pelo código (ex: 1023) — público",
)
async def buscar_pedido_por_codigo(
    codigo:  str,
    session: Session = Depends(pegar_sessao),
):
    pedido = session.query(Pedido).filter(Pedido.codigo == codigo).first()
    if not pedido:
        raise HTTPException(status_code=404, detail=f"Pedido #{codigo} não encontrado")
    return pedido


# ============================================================
# ITENS DO PEDIDO — PÚBLICO (cliente não tem login)
# ============================================================

@order_router.post(
    "/pedido/adicionar-item/{pedido_id}",
    summary="Adiciona item ao pedido (público — sem login)",
)
async def adicionar_item(
    pedido_id: int,
    dados:     ItemPedidoSchema,
    session:   Session = Depends(pegar_sessao),
    # ✅ Removido: verificar_token — cliente não tem login
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    # Segurança: só permite alterar pedido que ainda está PENDENTE
    if pedido.status != StatusPedido.PENDENTE:
        raise HTTPException(
            status_code=400,
            detail=f"Pedido já está {pedido.status} — não é possível adicionar itens",
        )

    variacao_nome  = None
    preco_unitario = dados.preco_unitario

    if dados.variacao_id is not None:
        variacao = session.query(VariacaoProduto).filter(
            VariacaoProduto.id == dados.variacao_id
        ).first()
        if not variacao:
            raise HTTPException(status_code=404, detail="Variação não encontrada")
        if not variacao.disponivel:
            raise HTTPException(
                status_code=400,
                detail=f"Variação '{variacao.nome}' está indisponível",
            )
        variacao_nome  = variacao.nome
        preco_unitario = dados.preco_unitario + variacao.acrescimo

    item = ItemPedido(
        quantidade     = dados.quantidade,
        nomedoproduto  = dados.nomedoproduto,
        variacao_nome  = variacao_nome,
        preco_unitario = preco_unitario,
        observacoes    = dados.observacoes,   # adicionais ficam aqui como texto
        pedido_id      = pedido_id,
    )
    session.add(item)
    session.flush()

    # Recalcular total (itens + taxa de entrega)
    subtotal_itens     = sum(i.preco_unitario * i.quantidade for i in pedido.itens)
    pedido.preco_total = subtotal_itens + pedido.valor_entrega

    session.commit()
    session.refresh(item)

    logger.info(
        "Item adicionado | pedido=%s | produto=%s | qty=%s | preço=%.2f",
        pedido_id, dados.nomedoproduto, dados.quantidade, preco_unitario,
    )

    return {
        "mensagem":       "Item adicionado com sucesso",
        "item_id":        item.id,
        "variacao":       variacao_nome,
        "preco_unitario": preco_unitario,
        "preco_total":    pedido.preco_total,
    }


@order_router.delete(
    "/pedido/remover-item/{item_id}",
    summary="Remove um item do pedido (admin)",
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
    if pedido.status != StatusPedido.PENDENTE:
        raise HTTPException(status_code=400, detail=f"Pedido já está {pedido.status}")

    session.delete(item)
    session.flush()

    subtotal_itens     = sum(i.preco_unitario * i.quantidade for i in pedido.itens)
    pedido.preco_total = subtotal_itens + pedido.valor_entrega
    session.commit()

    return {
        "mensagem":    "Item removido com sucesso",
        "preco_total": pedido.preco_total,
        "itens":       len(pedido.itens),
    }


# ============================================================
# FINALIZAR — PÚBLICO (cliente não tem login)
# ============================================================

@order_router.post(
    "/pedido/finalizar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Finaliza o pedido — DINHEIRO | PIX | CARTAO (público — sem login)",
)
async def finalizar_pedido(
    pedido_id: int,
    dados:     FinalizarPedidoSchema,
    session:   Session = Depends(pegar_sessao),
    # ✅ Removido: verificar_admin — cliente não tem login
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    # Segurança: só finaliza pedido PENDENTE
    if pedido.status != StatusPedido.PENDENTE:
        raise HTTPException(
            status_code=400,
            detail=f"Pedido já está {pedido.status} — não é possível finalizar novamente",
        )

    # Segurança: não finaliza pedido sem itens
    if not pedido.itens:
        raise HTTPException(
            status_code=400,
            detail="Não é possível finalizar um pedido sem itens",
        )

    pedido.status          = StatusPedido.FINALIZADO
    pedido.forma_pagamento = dados.forma_pagamento
    pedido.troco_para      = dados.troco_para

    session.commit()
    session.refresh(pedido)

    logger.info(
        "Pedido finalizado | id=%s | pagamento=%s | total=R$ %.2f",
        pedido.id, pedido.forma_pagamento, pedido.preco_total,
    )
    return pedido


# ============================================================
# CANCELAR — ADMIN
# ============================================================

@order_router.post(
    "/pedido/cancelar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Cancela um pedido (somente admin)",
)
async def cancelar_pedido(
    pedido_id: int,
    session:   Session = Depends(pegar_sessao),
    _:         Usuario = Depends(verificar_admin),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    if pedido.status == StatusPedido.CANCELADO:
        raise HTTPException(status_code=400, detail="Pedido já está cancelado")
    if pedido.status == StatusPedido.FINALIZADO:
        raise HTTPException(status_code=400, detail="Pedido finalizado não pode ser cancelado")

    pedido.status = StatusPedido.CANCELADO
    session.commit()
    session.refresh(pedido)

    logger.info("Pedido cancelado | id=%s", pedido.id)
    return pedido


# ============================================================
# DEBUG — somente admin
# ============================================================

@order_router.get(
    "/debug/pedidos",
    summary="[DEBUG] Verifica persistência — total e últimos 5 pedidos (somente admin)",
    tags=["Debug"],
)
async def debug_pedidos(
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    total   = session.query(Pedido).count()
    ultimos = (
        session.query(Pedido)
        .order_by(Pedido.criado_em.desc())
        .limit(5)
        .all()
    )

    return {
        "banco":         "PostgreSQL" if "postgresql" in str(session.bind.url) else "SQLite",
        "total_pedidos": total,
        "ultimos_5": [
            {
                "id":           p.id,
                "codigo":       p.codigo,
                "nome_cliente": p.nome_cliente,
                "telefone":     p.telefone,
                "tipo_pedido":  p.tipo_pedido,
                "status":       p.status,
                "preco_total":  p.preco_total,
                "criado_em":    p.criado_em.isoformat() if p.criado_em else None,
            }
            for p in ultimos
        ],
    }
