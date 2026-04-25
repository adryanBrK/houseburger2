"""
order_routes.py — REFATORADO
==============================
O router agora é apenas um controlador HTTP:
  - Valida entrada (via schemas/Pydantic)
  - Chama o service
  - Traduz exceções de domínio em HTTPException
  - Devolve a resposta

Zero lógica de negócio aqui.
Zero imports de outros routers.
"""

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
    ReordenarCategoriasSchema,
)
from models import Categoria, Porcao, Pedido, ItemPedido, Usuario, StatusPedido
import services_pedido_service as pedido_svc
from services_pedido_service import (
    PedidoNaoEncontradoError,
    PedidoStatusInvalidoError,
    PedidoSemItensError,
    ProdutoIndisponivelError,
    VariacaoIndisponivelError,
    AdicionalInativoError,
    PedidoError,
)

log = logging.getLogger("order_routes")
order_router = APIRouter(prefix="/Pedidos", tags=["Pedidos"])


# ══════════════════════════════════════════════════════════════════
# TRADUTOR DE EXCEÇÕES
# Centraliza o mapeamento domínio → HTTP para não repetir em cada rota.
# ══════════════════════════════════════════════════════════════════

def _traduzir(exc: Exception) -> HTTPException:
    """Converte exceção de domínio em HTTPException com código correto."""
    if isinstance(exc, PedidoNaoEncontradoError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (PedidoStatusInvalidoError, PedidoSemItensError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (ProdutoIndisponivelError, VariacaoIndisponivelError, AdicionalInativoError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PedidoError):
        return HTTPException(status_code=400, detail=str(exc))
    # Erro inesperado — loga e retorna 500
    log.error("[order_routes] Erro inesperado: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="Erro interno — tente novamente")


# ══════════════════════════════════════════════════════════════════
# CATEGORIAS
# ══════════════════════════════════════════════════════════════════

@order_router.get(
    "/categorias",
    response_model=List[ResponseCategoriaSchema],
    summary="Lista categorias ordenadas (público)",
)
async def listar_categorias(session: Session = Depends(pegar_sessao)):
    # order_by garante a ordem do drag-and-drop do front
    return (
        session.query(Categoria)
        .order_by(Categoria.ordem.asc(), Categoria.id.asc())
        .all()
    )


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
    nova = Categoria(
        nome       = dados.nome,
        descricao  = dados.descricao,
        imagem_url = dados.imagem_url,
        ordem      = dados.ordem if dados.ordem is not None else 0,
    )
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
    cat.nome      = dados.nome
    cat.descricao = dados.descricao
    if dados.ativo is not None:
        cat.ativo = dados.ativo
    if dados.imagem_url is not None:
        cat.imagem_url = dados.imagem_url
    if dados.ordem is not None:
        cat.ordem = dados.ordem
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


@order_router.put(
    "/categorias/reordenar",
    response_model=List[ResponseCategoriaSchema],
    summary="Reordena categorias por drag-and-drop (admin)",
)
async def reordenar_categorias(
    dados:   ReordenarCategoriasSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """
    Recebe lista de IDs na nova ordem: {"ids": [3, 1, 2, 5]}
    Categoria com id=3 recebe ordem=0, id=1 → ordem=1, etc.
    IDs inexistentes são ignorados silenciosamente.
    """
    if not dados.ids:
        return (
            session.query(Categoria)
            .order_by(Categoria.ordem.asc())
            .all()
        )

    for posicao, cat_id in enumerate(dados.ids):
        cat = session.query(Categoria).filter(Categoria.id == cat_id).first()
        if cat is None:
            log.warning("reordenar_categorias: id=%s não encontrado — ignorado", cat_id)
            continue
        cat.ordem = posicao

    try:
        session.commit()
        log.info("Categorias reordenadas: %s", dados.ids)
    except Exception as exc:
        session.rollback()
        log.error("Erro ao salvar ordem: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Falha ao salvar a nova ordem: {exc}")

    return (
        session.query(Categoria)
        .order_by(Categoria.ordem.asc())
        .all()
    )


# ══════════════════════════════════════════════════════════════════
# PORÇÕES
# ══════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════
# PEDIDOS
# ══════════════════════════════════════════════════════════════════

@order_router.post(
    "/pedidos",
    response_model=ResponsePedidoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria pedido (público — sem login)",
)
async def criar_pedido(
    dados:   PedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    try:
        pedido = pedido_svc.criar_pedido(
            session      = session,
            nome_cliente = dados.nome_cliente,
            telefone     = dados.telefone,
            tipo_pedido  = dados.tipo_pedido,
            bairro_id    = dados.bairro_id,
            endereco     = dados.endereco,
            observacoes  = dados.observacoes,
            usuario_id   = dados.id_usuario,
        )
        return pedido
    except Exception as exc:
        raise _traduzir(exc)


@order_router.get(
    "/listar",
    response_model=List[ResponsePedidoSchema],
    summary="Lista todos os pedidos (somente admin)",
)
async def listar_todos_pedidos(
    status_filtro:   Optional[str] = None,
    forma_pagamento: Optional[str] = None,
    tipo_pedido:     Optional[str] = None,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
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
    summary="Lista pedidos do usuário logado",
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
    summary="Visualiza pedido (admin ou dono)",
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
    summary="Busca pedido por código — público",
)
async def buscar_pedido_por_codigo(
    codigo:  str,
    session: Session = Depends(pegar_sessao),
):
    pedido = session.query(Pedido).filter(Pedido.codigo == codigo).first()
    if not pedido:
        raise HTTPException(status_code=404, detail=f"Pedido #{codigo} não encontrado")
    return pedido


# ══════════════════════════════════════════════════════════════════
# ITENS
# ══════════════════════════════════════════════════════════════════

@order_router.post(
    "/pedido/adicionar-item/{pedido_id}",
    summary="Adiciona item ao pedido (público)",
)
async def adicionar_item(
    pedido_id: int,
    dados:     ItemPedidoSchema,
    session:   Session = Depends(pegar_sessao),
):
    """
    Preço lido do banco (Produto.preco + VariacaoProduto.acrescimo).
    O campo preco_unitario no schema ainda existe por compatibilidade,
    mas é IGNORADO — o service busca o preço real do banco.
    """
    try:
        item = pedido_svc.adicionar_item(
            session        = session,
            pedido_id      = pedido_id,
            produto_id     = dados.produto_id,
            quantidade     = dados.quantidade,
            variacao_id    = dados.variacao_id,
            adicionais_ids = dados.adicionais_ids or [],
            observacoes    = dados.observacoes,
        )
        pedido = item.pedido
        return {
            "mensagem":         "Item adicionado com sucesso",
            "item_id":          item.id,
            "produto":          item.nomedoproduto,
            "variacao":         item.variacao_nome,
            "adicionais":       item.adicionais_nomes,
            "preco_unitario":   item.preco_unitario,
            "adicionais_preco": item.adicionais_preco,
            "preco_total":      pedido.preco_total,
        }
    except Exception as exc:
        raise _traduzir(exc)


@order_router.delete(
    "/pedido/remover-item/{item_id}",
    summary="Remove item do pedido",
)
async def remover_item(
    item_id: int,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    try:
        return pedido_svc.remover_item(
            session    = session,
            item_id    = item_id,
            usuario_id = usuario.id,
            is_admin   = usuario.admin,
        )
    except Exception as exc:
        raise _traduzir(exc)


# ══════════════════════════════════════════════════════════════════
# FINALIZAR / CANCELAR
# ══════════════════════════════════════════════════════════════════

@order_router.post(
    "/pedido/finalizar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Finaliza pedido e registra no caixa (público)",
)
async def finalizar_pedido(
    pedido_id: int,
    dados:     FinalizarPedidoSchema,
    session:   Session = Depends(pegar_sessao),
):
    try:
        return pedido_svc.finalizar_pedido(
            session         = session,
            pedido_id       = pedido_id,
            forma_pagamento = dados.forma_pagamento,
            troco_para      = dados.troco_para,
        )
    except Exception as exc:
        raise _traduzir(exc)


@order_router.post(
    "/pedido/cancelar/{pedido_id}",
    response_model=ResponsePedidoSchema,
    summary="Cancela pedido (somente admin)",
)
async def cancelar_pedido(
    pedido_id: int,
    session:   Session = Depends(pegar_sessao),
    _:         Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.cancelar_pedido(session, pedido_id)
    except Exception as exc:
        raise _traduzir(exc)


# ══════════════════════════════════════════════════════════════════
# DEBUG
# ══════════════════════════════════════════════════════════════════

@order_router.get(
    "/debug/pedidos",
    summary="[DEBUG] Persistência e últimos 5 pedidos (somente admin)",
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
                "status":       p.status,
                "preco_total":  p.preco_total,
                "criado_em":    p.criado_em.isoformat() if p.criado_em else None,
            }
            for p in ultimos
        ],
    }
