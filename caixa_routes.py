"""
caixa_routes.py — REFATORADO
==============================
O router delega toda lógica para services_caixa_service.
Sem mais helpers privados aqui — eles vivem no service.
Rotas e schemas inalterados externamente.
"""

import logging
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Caixa, TipoMovimentacao, Usuario
import services_caixa_service as caixa_svc
from services_caixa_service import (
    CaixaError,
    CaixaJaFechadoError,
    CaixaNaoEncontradoError,
    SaldoInsuficienteError,
    ValorInvalidoError,
)

log = logging.getLogger("caixa_routes")
caixa_router = APIRouter(prefix="/Caixa", tags=["Caixa"])


def _traduzir(exc: Exception) -> HTTPException:
    if isinstance(exc, (CaixaJaFechadoError, SaldoInsuficienteError, ValorInvalidoError)):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, CaixaNaoEncontradoError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, CaixaError):
        return HTTPException(status_code=400, detail=str(exc))
    log.error("[caixa_routes] Erro inesperado: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="Erro interno do caixa")


# ══════════════════════════════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════════════════════════════

class ResponseMovimentacaoSchema(BaseModel):
    id:        int
    tipo:      str
    valor:     float
    descricao: Optional[str]
    criado_em: datetime
    pedido_id: Optional[int]

    class Config:
        from_attributes = True


class ResponseCaixaSchema(BaseModel):
    id:            int
    data:          date
    caixa_inicial: float
    entradas:      float
    saidas:        float
    saldo_atual:   float
    criado_em:     datetime

    class Config:
        from_attributes = True


class ResponseCaixaDetalhadoSchema(ResponseCaixaSchema):
    movimentacoes: List[ResponseMovimentacaoSchema] = []

    class Config:
        from_attributes = True


class ResponseCaixaFechadoSchema(BaseModel):
    id:             int
    data:           date
    caixa_inicial:  float
    total_entradas: float
    total_saidas:   float
    saldo_final:    float
    fechado_em:     datetime
    fechado_por:    Optional[str] = None

    class Config:
        from_attributes = True


class AbrirCaixaSchema(BaseModel):
    caixa_inicial: float = 0.0

    @field_validator("caixa_inicial")
    @classmethod
    def nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Caixa inicial não pode ser negativo")
        return v


class MovimentacaoManualSchema(BaseModel):
    tipo:      str
    valor:     float
    descricao: Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        v = v.upper().strip()
        permitidos = {TipoMovimentacao.SAIDA, TipoMovimentacao.SANGRIA, TipoMovimentacao.SUPRIMENTO}
        if v not in {t.value for t in permitidos}:
            raise ValueError("tipo deve ser SAIDA, SANGRIA ou SUPRIMENTO")
        return v

    @field_validator("valor")
    @classmethod
    def valor_positivo(cls, v):
        if v <= 0:
            raise ValueError("Valor deve ser maior que zero")
        return v


# ══════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════

@caixa_router.get(
    "/hoje",
    response_model=ResponseCaixaDetalhadoSchema,
    summary="Caixa do dia com movimentações (admin)",
)
async def caixa_hoje(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    hoje  = datetime.now(timezone.utc).date()
    caixa = session.query(Caixa).filter(Caixa.data == hoje).first()

    if not caixa:
        return {
            "id": 0, "data": hoje,
            "caixa_inicial": 0.0, "entradas": 0.0, "saidas": 0.0, "saldo_atual": 0.0,
            "criado_em": datetime.now(timezone.utc), "movimentacoes": [],
        }
    return caixa


@caixa_router.get(
    "/historico",
    response_model=List[ResponseCaixaSchema],
    summary="Histórico de caixas (admin)",
)
async def historico_caixas(
    dias:    int     = 30,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    if dias < 1 or dias > 365:
        raise HTTPException(status_code=400, detail="dias deve estar entre 1 e 365")
    inicio = datetime.now(timezone.utc).date() - timedelta(days=dias - 1)
    return (
        session.query(Caixa)
        .filter(Caixa.data >= inicio)
        .order_by(Caixa.data.desc())
        .all()
    )


@caixa_router.get(
    "/historico-fechados",
    response_model=List[ResponseCaixaFechadoSchema],
    summary="Caixas fechados — snapshots imutáveis (admin)",
)
async def historico_fechados(
    dias:    int     = 30,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    from models import CaixaFechado
    if dias < 1 or dias > 365:
        raise HTTPException(status_code=400, detail="dias deve estar entre 1 e 365")
    inicio = datetime.now(timezone.utc).date() - timedelta(days=dias - 1)
    fechados = (
        session.query(CaixaFechado)
        .filter(CaixaFechado.data >= inicio)
        .order_by(CaixaFechado.fechado_em.desc())
        .all()
    )
    return [
        {
            "id": f.id, "data": f.data,
            "caixa_inicial": f.caixa_inicial,
            "total_entradas": f.total_entradas,
            "total_saidas": f.total_saidas,
            "saldo_final": f.saldo_final,
            "fechado_em": f.fechado_em,
            "fechado_por": f.fechado_por.nome if f.fechado_por else None,
        }
        for f in fechados
    ]


@caixa_router.get(
    "/{data_str}",
    response_model=ResponseCaixaDetalhadoSchema,
    summary="Caixa de data específica YYYY-MM-DD (admin)",
)
async def caixa_por_data(
    data_str: str,
    session:  Session = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    try:
        dia = date.fromisoformat(data_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato inválido. Use YYYY-MM-DD")
    caixa = session.query(Caixa).filter(Caixa.data == dia).first()
    if not caixa:
        if not caixa:
    return {
        "id": 0,
        "data": dia,
        "caixa_inicial": 0.0,
        "entradas": 0.0,
        "saidas": 0.0,
        "saldo_atual": 0.0,
        "criado_em": datetime.now(timezone.utc),
        "movimentacoes": [],
    }
    return caixa


@caixa_router.post(
    "/abrir",
    response_model=ResponseCaixaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Abre caixa do dia com valor inicial (admin)",
)
async def abrir_caixa(
    dados:   AbrirCaixaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    hoje = datetime.now(timezone.utc).date()
    existente = session.query(Caixa).filter(Caixa.data == hoje).first()
    if existente:
        raise HTTPException(
            status_code=400,
            detail=f"Caixa do dia {hoje} já está aberto (id={existente.id})",
        )
    caixa = Caixa(
        data          = hoje,
        caixa_inicial = dados.caixa_inicial,
        entradas      = 0.0,
        saidas        = 0.0,
        saldo_atual   = dados.caixa_inicial,
    )
    session.add(caixa)
    try:
        session.commit()
        session.refresh(caixa)
    except Exception as exc:
        session.rollback()
        log.error("[CAIXA] Erro ao abrir: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao abrir caixa: {exc}")
    log.info("[CAIXA] Aberto %s | inicial=R$%.2f", hoje, dados.caixa_inicial)
    return caixa


@caixa_router.post(
    "/movimentacao",
    response_model=ResponseMovimentacaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Movimentação manual: SAIDA, SANGRIA ou SUPRIMENTO (admin)",
)
async def movimentacao_manual(
    dados:   MovimentacaoManualSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    try:
        mov = caixa_svc.registrar_saida(
            session   = session,
            valor     = dados.valor,
            tipo      = TipoMovimentacao(dados.tipo),
            descricao = dados.descricao,
        )
        session.commit()
        session.refresh(mov)
        return mov
    except Exception as exc:
        session.rollback()
        raise _traduzir(exc)


@caixa_router.post(
    "/fechar",
    response_model=ResponseCaixaFechadoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Fecha caixa do dia — snapshot imutável (admin)",
)
async def fechar_caixa(
    session: Session  = Depends(pegar_sessao),
    admin: Usuario    = Depends(verificar_admin),
):
    try:
        fechado = caixa_svc.criar_snapshot_fechamento(
            session        = session,
            fechado_por_id = admin.id,
        )
        session.commit()
        session.refresh(fechado)
        return {
            "id": fechado.id, "data": fechado.data,
            "caixa_inicial": fechado.caixa_inicial,
            "total_entradas": fechado.total_entradas,
            "total_saidas": fechado.total_saidas,
            "saldo_final": fechado.saldo_final,
            "fechado_em": fechado.fechado_em,
            "fechado_por": admin.nome,
        }
    except Exception as exc:
        session.rollback()
        raise _traduzir(exc)
