Order routes · PY
Copiar

"""
order_routes.py — CORRIGIDO
========================================
Correções aplicadas:
  1. /categorias/reordenar registrada ANTES de /categorias/{categoria_id}
  2. listar_pedidos chama pedido_svc.listar_pedidos() que agora existe no service
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from dependencias import pegar_sessao, verificar_admin
from schemas import (
    CategoriaSchema, ResponseCategoriaSchema,
    PorcaoSchema, ResponsePorcaoSchema,
    PedidoSchema, ResponsePedidoSchema,
    ItemPedidoSchema, FinalizarPedidoSchema,
    ReordenarCategoriasSchema,
)
from models import Categoria, Porcao, Usuario
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
# ══════════════════════════════════════════════════════════════════
def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, PedidoNaoEncontradoError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (PedidoStatusInvalidoError, PedidoSemItensError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (ProdutoIndisponivelError, VariacaoIndisponivelError, AdicionalInativoError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PedidoError):
        return HTTPException(status_code=400, detail=str(exc))
    log.error("[order_routes] Erro inesperado: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="Erro interno — tente novamente")
 
 
# ══════════════════════════════════════════════════════════════════
# CATEGORIAS
# ══════════════════════════════════════════════════════════════════
@order_router.get("/categorias", response_model=List[ResponseCategoriaSchema])
async def listar_categorias(session: Session = Depends(pegar_sessao)):
    return (
        session.query(Categoria)
        .order_by(Categoria.ordem.asc(), Categoria.id.asc())
        .all()
    )
 
 
@order_router.post("/categorias", response_model=ResponseCategoriaSchema, status_code=status.HTTP_201_CREATED)
async def criar_categoria(
    dados: CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.criar_categoria(session, dados)
    except Exception as exc:
        raise _traduzir(exc)
 
 
# ── REORDENAR deve vir ANTES de /{categoria_id} ──────────────────
@order_router.put("/categorias/reordenar", response_model=List[ResponseCategoriaSchema])
async def reordenar_categorias(
    dados: ReordenarCategoriasSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.reordenar_categorias(session, dados.ids)
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.put("/categorias/{categoria_id}", response_model=ResponseCategoriaSchema)
async def editar_categoria(
    categoria_id: int,
    dados: CategoriaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.editar_categoria(session, categoria_id, dados)
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.delete("/categorias/{categoria_id}")
async def deletar_categoria(
    categoria_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.deletar_categoria(session, categoria_id)
    except Exception as exc:
        raise _traduzir(exc)
 
 
# ══════════════════════════════════════════════════════════════════
# PORÇÕES
# ══════════════════════════════════════════════════════════════════
@order_router.get("/porcoes", response_model=List[ResponsePorcaoSchema])
async def listar_porcoes(session: Session = Depends(pegar_sessao)):
    return session.query(Porcao).all()
 
 
@order_router.post("/porcoes", response_model=ResponsePorcaoSchema, status_code=status.HTTP_201_CREATED)
async def criar_porcao(
    dados: PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.criar_porcao(session, dados)
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.put("/porcoes/{porcao_id}", response_model=ResponsePorcaoSchema)
async def editar_porcao(
    porcao_id: int,
    dados: PorcaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.editar_porcao(session, porcao_id, dados)
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.delete("/porcoes/{porcao_id}")
async def deletar_porcao(
    porcao_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.deletar_porcao(session, porcao_id)
    except Exception as exc:
        raise _traduzir(exc)
 
 
# ══════════════════════════════════════════════════════════════════
# PEDIDOS
# ══════════════════════════════════════════════════════════════════
@order_router.get("/pedidos", response_model=List[ResponsePedidoSchema])
async def listar_pedidos(session: Session = Depends(pegar_sessao)):
    try:
        return pedido_svc.listar_pedidos(session)
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.post("/pedidos", response_model=ResponsePedidoSchema, status_code=status.HTTP_201_CREATED)
async def criar_pedido(
    dados: PedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    try:
        return pedido_svc.criar_pedido(session=session, **dados.dict())
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.post("/pedidos/adicionar-item/{pedido_id}")
async def adicionar_item(
    pedido_id: int,
    dados: ItemPedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    try:
        return pedido_svc.adicionar_item(session=session, pedido_id=pedido_id, **dados.dict())
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.post("/pedidos/finalizar/{pedido_id}")
async def finalizar_pedido(
    pedido_id: int,
    dados: FinalizarPedidoSchema,
    session: Session = Depends(pegar_sessao),
):
    try:
        return pedido_svc.finalizar_pedido(session, pedido_id, **dados.dict())
    except Exception as exc:
        raise _traduzir(exc)
 
 
@order_router.post("/pedidos/cancelar/{pedido_id}")
async def cancelar_pedido(
    pedido_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        return pedido_svc.cancelar_pedido(session, pedido_id)
    except Exception as exc:
        raise _traduzir(exc)
