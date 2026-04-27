"""
order_routes.py v3.0.0
=======================
Correções:
  - Rota estática /categorias/reordenar ANTES de /categorias/{id}
  - Todas as funções do service existem (sem chamadas para funções inexistentes)
  - listar_pedidos corretamente implementada no router
  - Router puro: sem lógica de negócio, sem queries diretas no router de pedidos
  - _traduzir() cobre todas as exceções de domínio
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
from models import Categoria, Porcao, Pedido, Usuario
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
# TRADUTOR CENTRALIZADO DE EXCEÇÕES
# ══════════════════════════════════════════════════════════════════

def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, PedidoNaoEncontradoError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (
        PedidoStatusInvalidoError, PedidoSemItensError,
        ProdutoIndisponivelError, VariacaoIndisponivelError,
        AdicionalInativoError, PedidoError,
    )):
        return HTTPException(status_code=400, detail=str(exc))
    log.error("[order_routes] Erro inesperado: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="Erro interno — tente novamente")


# ══════════════════════════════════════════════════════════════════
# CATEGORIAS
# CRÍTICO: rotas estáticas ANTES de /{id}
# /categorias/reordenar DEVE vir antes de /categorias/{categoria_id}
# ══════════════════════════════════════════════════════════════════

@order_router.get(
    "/categorias",
    response_model=List[ResponseCategoriaSchema],
    summary="Lista categorias ordenadas (público)",
)
async def listar_categorias(session: Session = Depends(pegar_sessao)):
    return (
        session.query(Categoria)
        .order_by(Categoria.ordem.asc(), Categoria.id.asc())
        .all()
    )


@order_router.post(
    "/categorias",
    response_model=ResponseCategoriaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria categoria (admin)",
)
async def criar_categoria(
    dados:   CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    existe = session.query(Categoria).filter(Categoria.nome == dados.nome.strip()).first()
    if existe:
        raise HTTPException(status_code=400, detail=f"Categoria '{dados.nome}' já existe")

    nova = Categoria(
        nome       = dados.nome.strip(),
        descricao  = dados.descricao,
        ativo      = dados.ativo if dados.ativo is not None else True,
        imagem_url = dados.imagem_url,
        ordem      = dados.ordem if dados.ordem is not None else 0,
    )
    session.add(nova)
    try:
        session.commit()
        session.refresh(nova)
    except Exception as exc:
        session.rollback()
        log.error("[order] Erro ao criar categoria: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Erro ao criar categoria")
    return nova


# ── ROTA ESTÁTICA — deve vir ANTES de /{categoria_id} ─────────────

@order_router.put(
    "/categorias/reordenar",
    response_model=List[ResponseCategoriaSchema],
    summary="Reordena categorias por drag-and-drop (admin)",
)
async def reordenar_categorias(
    dados:   ReordenarCategoriasSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    """
    Body: {"ids": [3, 1, 2, 5]}
    Categoria id=3 → ordem=0, id=1 → ordem=1, etc.
    IDs inexistentes são ignorados.
    """
    if not dados.ids:
        return session.query(Categoria).order_by(Categoria.ordem.asc()).all()

    for posicao, cat_id in enumerate(dados.ids):
        cat = session.query(Categoria).filter(Categoria.id == cat_id).first()
        if cat is None:
            log.warning("[order] reordenar: id=%s não encontrado — ignorado", cat_id)
            continue
        cat.ordem = posicao

    try:
        session.commit()
        log.info("[order] Categorias reordenadas: %s", dados.ids)
    except Exception as exc:
        session.rollback()
        log.error("[order] Erro ao reordenar: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Falha ao salvar nova ordem")

    return session.query(Categoria).order_by(Categoria.ordem.asc()).all()


# ── ROTA DINÂMICA — depois das estáticas ──────────────────────────

@order_router.put(
    "/categorias/{categoria_id}",
    response_model=ResponseCategoriaSchema,
    summary="Edita categoria (admin)",
)
async def editar_categoria(
    categoria_id: int,
    dados:   CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Checar conflito de nome com outra categoria
    conflito = session.query(Categoria).filter(
        Categoria.nome == dados.nome.strip(),
        Categoria.id   != categoria_id,
    ).first()
    if conflito:
        raise HTTPException(status_code=400, detail=f"Nome '{dados.nome}' já usado por outra categoria")

    cat.nome      = dados.nome.strip()
    cat.descricao = dados.descricao
    if dados.ativo is not None:
        cat.ativo = dados.ativo
    if dados.imagem_url is not None:
        cat.imagem_url = dados.imagem_url
    if dados.ordem is not None:
        cat.ordem = dados.ordem

    try:
        session.commit()
        session.refresh(cat)
    except Exception as exc:
        session.rollback()
        log.error("[order] Erro ao editar categoria %s: %s", categoria_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar categoria")
    return cat


@order_router.delete(
    "/categorias/{categoria_id}",
    summary="Remove categoria (admin)",
)
async def deletar_categoria(
    categoria_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    cat = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    nome = cat.nome
    session.delete(cat)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível remover '{nome}' — possui produtos vinculados",
        )
    return {"mensagem": f"Categoria '{nome}' removida"}


# ══════════════════════════════════════════════════════════════════
# PORÇÕES
# ══════════════════════════════════════════════════════════════════

@order_router.get("/porcoes", response_model=List[ResponsePorcaoSchema])
async def listar_porcoes(session: Session = Depends(pegar_sessao)):
    return session.query(Porcao).all()


@order_router.post(
    "/porcoes",
    response_model=ResponsePorcaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria porção (admin)",
)
async def criar_porcao(
    dados:   PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    nova = Porcao(nome=dados.nome.strip(), preco=dados.preco)
    session.add(nova)
    try:
        session.commit()
        session.refresh(nova)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Porção com esse nome já existe")
    return nova


@order_router.put("/porcoes/{porcao_id}", response_model=ResponsePorcaoSchema, summary="Edita porção (admin)")
async def editar_porcao(
    porcao_id: int,
    dados:   PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    p = session.query(Porcao).filter(Porcao.id == porcao_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Porção não encontrada")
    p.nome = dados.nome.strip()
    p.preco = dados.preco
    session.commit()
    session.refresh(p)
    return p


@order_router.delete("/porcoes/{porcao_id}", summary="Remove porção (admin)")
async def deletar_porcao(
    porcao_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    p = session.query(Porcao).filter(Porcao.id == porcao_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Porção não encontrada")
    session.delete(p)
    session.commit()
    return {"mensagem": "Porção removida"}


# ══════════════════════════════════════════════════════════════════
# PEDIDOS — CRUD
# ══════════════════════════════════════════════════════════════════

@order_router.post(
    "/pedidos",
    response_model=ResponsePedidoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria pedido (público)",
)
async def criar_pedido(
    dados:   PedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    try:
        return pedido_svc.criar_pedido(
            session      = session,
            nome_cliente = dados.nome_cliente,
            telefone     = dados.telefone,
            tipo_pedido  = dados.tipo_pedido,
            bairro_id    = dados.bairro_id,
            endereco     = dados.endereco,
            observacoes  = dados.observacoes,
            usuario_id   = dados.id_usuario,
        )
    except Exception as exc:
        raise _traduzir(exc)


@order_router.get(
    "/listar",
    response_model=List[ResponsePedidoSchema],
    summary="Lista todos os pedidos (admin)",
)
async def listar_pedidos(
    status_filtro:   Optional[str] = None,
    forma_pagamento: Optional[str] = None,
    tipo_pedido:     Optional[str] = None,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    """
    Filtros opcionais via query string:
      ?status_filtro=PENDENTE
      ?forma_pagamento=PIX
      ?tipo_pedido=ENTREGA
    """
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
    summary="Pedidos do usuário logado",
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
    "/buscar/{codigo}",
    response_model=ResponsePedidoSchema,
    summary="Busca pedido por código (público)",
)
async def buscar_por_codigo(codigo: str, session: Session = Depends(pegar_sessao)):
    pedido = session.query(Pedido).filter(Pedido.codigo == codigo).first()
    if not pedido:
        raise HTTPException(status_code=404, detail=f"Pedido #{codigo} não encontrado")
    return pedido


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
    summary="Cancela pedido (admin)",
)
async def cancelar_pedido(
    pedido_id: int,
    session:   Session = Depends(pegar_sessao),
    _: Usuario         = Depends(verificar_admin),
):
    try:
        return pedido_svc.cancelar_pedido(session, pedido_id)
    except Exception as exc:
        raise _traduzir(exc)


# ══════════════════════════════════════════════════════════════════
# DEBUG
# ══════════════════════════════════════════════════════════════════

@order_router.get("/debug/pedidos", tags=["Debug"], summary="Debug (admin)")
async def debug_pedidos(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    total   = session.query(Pedido).count()
    ultimos = session.query(Pedido).order_by(Pedido.criado_em.desc()).limit(5).all()
    return {
        "banco":         "PostgreSQL" if "postgresql" in str(session.bind.url) else "SQLite",
        "total_pedidos": total,
        "ultimos_5": [
            {
                "id": p.id, "codigo": p.codigo, "status": p.status,
                "preco_total": p.preco_total,
                "criado_em": p.criado_em.isoformat() if p.criado_em else None,
            }
            for p in ultimos
        ],
    }
