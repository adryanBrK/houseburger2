"""
impressora_routes.py
====================
Rotas FastAPI para:
  - Listar impressoras cadastradas
  - Marcar pedido como impresso (cozinha / motoboy)
  - Registrar log de impressão
  - Buscar pedidos pendentes de impressão (usado pelo cliente Windows)

Adicione ao main.py:
    from impressora_routes import impressora_router
    app.include_router(impressora_router)
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from dependencias import pegar_sessao, verificar_admin, verificar_token
from models import Pedido, StatusPedido, LogImpressao, Impressora, Usuario
from schemas import ResponseImpressoraSchema, ImpressoraSchema

log = logging.getLogger("impressora_routes")
impressora_router = APIRouter(prefix="/Pedidos", tags=["Impressão"])


# ══════════════════════════════════════════════════════════════════
# SCHEMAS LOCAIS
# ══════════════════════════════════════════════════════════════════

class MarcarImpressoSchema(BaseModel):
    """
    tipo: "cozinha" | "motoboy" | "ambos"
    """
    tipo: str  # "cozinha" | "motoboy" | "ambos"


class LogImpressaoSchema(BaseModel):
    tipo_comanda:  str            # "COZINHA" | "MOTOBOY"
    sucesso:       bool
    erro:          Optional[str] = None
    impressora_id: Optional[int] = None


# ══════════════════════════════════════════════════════════════════
# BUSCAR PEDIDOS PENDENTES DE IMPRESSÃO
# Usado pelo cliente Windows para polling
# ══════════════════════════════════════════════════════════════════

@impressora_router.get(
    "/impressao/pendentes",
    summary="Pedidos PENDENTES não impressos na cozinha (somente admin)",
)
async def pedidos_pendentes_impressao(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    """
    Retorna pedidos com status=PENDENTE e impresso_cozinha=False.
    Ordenados por criado_em ASC (mais antigo primeiro — FIFO).
    Usado pelo cliente de impressão Windows via polling.
    """
    pedidos = (
        session.query(Pedido)
        .filter(
            Pedido.status          == StatusPedido.PENDENTE,
            Pedido.impresso_cozinha == False,
        )
        .order_by(Pedido.criado_em.asc())
        .all()
    )
    return pedidos


# ══════════════════════════════════════════════════════════════════
# MARCAR COMO IMPRESSO
# Chamado pelo cliente Windows após impressão bem-sucedida
# ══════════════════════════════════════════════════════════════════

@impressora_router.patch(
    "/pedido/{pedido_id}/marcar-impresso",
    summary="Marca pedido como impresso — cozinha, motoboy ou ambos (somente admin)",
)
async def marcar_impresso(
    pedido_id: int,
    dados:     MarcarImpressoSchema,
    session:   Session = Depends(pegar_sessao),
    _: Usuario         = Depends(verificar_admin),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    agora = datetime.now(timezone.utc)
    tipo  = dados.tipo.lower()

    if tipo in ("cozinha", "ambos"):
        # Proteção contra dupla marcação: só atualiza se ainda não foi impresso
        if not pedido.impresso_cozinha:
            pedido.impresso_cozinha       = True
            pedido.data_impressao_cozinha = agora
            log.info("🖨️  Pedido #%s marcado: cozinha", pedido.codigo or pedido_id)
        else:
            log.warning("⚠️  Pedido #%s já estava marcado como impresso (cozinha)", pedido_id)

    if tipo in ("motoboy", "ambos"):
        if not pedido.impresso_motoboy:
            pedido.impresso_motoboy       = True
            pedido.data_impressao_motoboy = agora
            log.info("🛵  Pedido #%s marcado: motoboy", pedido.codigo or pedido_id)

    session.commit()

    return {
        "mensagem":               "Marcado com sucesso",
        "impresso_cozinha":       pedido.impresso_cozinha,
        "impresso_motoboy":       pedido.impresso_motoboy,
        "data_impressao_cozinha": pedido.data_impressao_cozinha,
        "data_impressao_motoboy": pedido.data_impressao_motoboy,
    }


# ══════════════════════════════════════════════════════════════════
# REGISTRAR LOG DE IMPRESSÃO
# ══════════════════════════════════════════════════════════════════

@impressora_router.post(
    "/pedido/{pedido_id}/log-impressao",
    summary="Registra tentativa de impressão (somente admin)",
)
async def registrar_log_impressao(
    pedido_id: int,
    dados:     LogImpressaoSchema,
    session:   Session = Depends(pegar_sessao),
    _: Usuario         = Depends(verificar_admin),
):
    pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
    if not pedido:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")

    log_entry = LogImpressao(
        pedido_id     = pedido_id,
        tipo_comanda  = dados.tipo_comanda.upper(),
        sucesso       = dados.sucesso,
        erro          = dados.erro,
        impressora_id = dados.impressora_id,
    )
    session.add(log_entry)
    session.commit()

    return {"mensagem": "Log registrado"}


# ══════════════════════════════════════════════════════════════════
# CRUD DE IMPRESSORAS
# ══════════════════════════════════════════════════════════════════

_impressora_router = APIRouter(prefix="/Impressoras", tags=["Impressoras"])


@_impressora_router.get("/", response_model=List[ResponseImpressoraSchema])
async def listar_impressoras(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    return session.query(Impressora).all()


@_impressora_router.post("/", response_model=ResponseImpressoraSchema, status_code=201)
async def criar_impressora(
    dados:   ImpressoraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    impressora = Impressora(**dados.model_dump())
    session.add(impressora)
    session.commit()
    session.refresh(impressora)
    return impressora


@_impressora_router.delete("/{impressora_id}")
async def deletar_impressora(
    impressora_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    imp = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    session.delete(imp)
    session.commit()
    return {"mensagem": "Impressora removida"}


# Exportar ambos os routers
# No main.py: app.include_router(impressora_router) e app.include_router(_impressora_router)
