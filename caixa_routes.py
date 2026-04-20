"""
caixa_routes.py
================
Módulo de caixa: consulta, movimentações manuais e histórico.

Registre no main.py:
    from caixa_routes import caixa_router
    app.include_router(caixa_router)
"""

import logging
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Caixa, MovimentacaoCaixa, TipoMovimentacao, Usuario

log = logging.getLogger("caixa_routes")
caixa_router = APIRouter(prefix="/Caixa", tags=["Caixa"])


# ══════════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════════

def _obter_ou_criar_caixa(dia: date, session: Session) -> Caixa:
    caixa = session.query(Caixa).filter(Caixa.data == dia).first()
    if not caixa:
        caixa = Caixa(
            data          = dia,
            caixa_inicial = 0.0,
            entradas      = 0.0,
            saidas        = 0.0,
            saldo_atual   = 0.0,
        )
        session.add(caixa)
        try:
            session.flush()
        except Exception:
            session.rollback()
            caixa = session.query(Caixa).filter(Caixa.data == dia).first()
            if not caixa:
                raise
    return caixa


def _registrar_entrada(
    session:   Session,
    valor:     float,
    descricao: str,
    pedido_id: Optional[int] = None,
) -> MovimentacaoCaixa:
    """
    Registra uma ENTRADA no caixa do dia atual.
    Chamado automaticamente ao finalizar um pedido — independente da forma de pagamento.
    Sem commit — responsabilidade do chamador.
    """
    if valor <= 0:
        raise ValueError(f"Valor de entrada deve ser positivo, recebido: {valor}")

    hoje  = datetime.now(timezone.utc).date()
    caixa = _obter_ou_criar_caixa(hoje, session)

    caixa.entradas   += valor
    caixa.saldo_atual = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    mov = MovimentacaoCaixa(
        tipo      = TipoMovimentacao.ENTRADA,
        valor     = valor,
        descricao = descricao,
        caixa_id  = caixa.id,
        pedido_id = pedido_id,
    )
    session.add(mov)
    return mov


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


class AbrirCaixaSchema(BaseModel):
    caixa_inicial: float = 0.0

    @field_validator("caixa_inicial")
    @classmethod
    def nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Caixa inicial não pode ser negativo")
        return v


class MovimentacaoManualSchema(BaseModel):
    tipo:      str   # SAIDA | SANGRIA | SUPRIMENTO
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
    summary="Retorna o caixa do dia com todas as movimentações (admin)",
)
async def caixa_hoje(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    hoje  = datetime.now(timezone.utc).date()
    caixa = session.query(Caixa).filter(Caixa.data == hoje).first()

    if not caixa:
        return {
            "id":            0,
            "data":          hoje,
            "caixa_inicial": 0.0,
            "entradas":      0.0,
            "saidas":        0.0,
            "saldo_atual":   0.0,
            "criado_em":     datetime.now(timezone.utc),
            "movimentacoes": [],
        }

    return caixa


@caixa_router.get(
    "/historico",
    response_model=List[ResponseCaixaSchema],
    summary="Histórico de caixas dos últimos N dias (admin)",
)
async def historico_caixas(
    dias:    int     = 30,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    if dias < 1 or dias > 365:
        raise HTTPException(status_code=400, detail="dias deve estar entre 1 e 365")

    inicio = datetime.now(timezone.utc).date() - timedelta(days=dias - 1)
    caixas = (
        session.query(Caixa)
        .filter(Caixa.data >= inicio)
        .order_by(Caixa.data.desc())
        .all()
    )
    return caixas


@caixa_router.get(
    "/{data_str}",
    response_model=ResponseCaixaDetalhadoSchema,
    summary="Caixa de uma data específica YYYY-MM-DD (admin)",
)
async def caixa_por_data(
    data_str: str,
    session:  Session = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    try:
        dia = date.fromisoformat(data_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD")

    caixa = session.query(Caixa).filter(Caixa.data == dia).first()
    if not caixa:
        raise HTTPException(status_code=404, detail=f"Nenhum caixa registrado em {data_str}")

    return caixa


@caixa_router.post(
    "/abrir",
    response_model=ResponseCaixaSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Abre o caixa do dia com valor inicial (admin)",
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
        log.error("[CAIXA] Erro ao abrir caixa: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao abrir caixa: {exc}")

    log.info("[CAIXA] Aberto para %s | inicial=R$%.2f", hoje, dados.caixa_inicial)
    return caixa


@caixa_router.post(
    "/movimentacao",
    response_model=ResponseMovimentacaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Registra movimentação manual: SAIDA, SANGRIA ou SUPRIMENTO (admin)",
)
async def movimentacao_manual(
    dados:   MovimentacaoManualSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    hoje  = datetime.now(timezone.utc).date()
    caixa = _obter_ou_criar_caixa(hoje, session)
    tipo  = TipoMovimentacao(dados.tipo)

    if tipo in (TipoMovimentacao.SAIDA, TipoMovimentacao.SANGRIA):
        if dados.valor > caixa.saldo_atual:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Valor R${dados.valor:.2f} excede o saldo atual "
                    f"R${caixa.saldo_atual:.2f}"
                ),
            )
        caixa.saidas      += dados.valor
        caixa.saldo_atual  = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    elif tipo == TipoMovimentacao.SUPRIMENTO:
        caixa.caixa_inicial += dados.valor
        caixa.saldo_atual    = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    mov = MovimentacaoCaixa(
        tipo      = tipo,
        valor     = dados.valor,
        descricao = dados.descricao,
        caixa_id  = caixa.id,
        pedido_id = None,
    )
    session.add(mov)

    try:
        session.commit()
        session.refresh(mov)
    except Exception as exc:
        session.rollback()
        log.error("[CAIXA] Erro ao registrar movimentacao: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar movimentação: {exc}")

    log.info(
        "[CAIXA] %s R$%.2f | %s | saldo=R$%.2f",
        tipo.value, dados.valor, dados.descricao or "-", caixa.saldo_atual,
    )
    return mov COLOCA ISSO MANO
