"""
caixa_routes.py
================
Rotas existentes (não alteradas):
  GET  /Caixa/hoje
  GET  /Caixa/historico
  GET  /Caixa/{data_str}
  POST /Caixa/abrir
  POST /Caixa/movimentacao

Rotas novas:
  POST /Caixa/fechar             — cria snapshot em CaixaFechado
  GET  /Caixa/historico-fechados — lista snapshots imutáveis ordenados por data desc
"""

import logging
from datetime import date, datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Caixa, CaixaFechado, MovimentacaoCaixa, TipoMovimentacao, Usuario

log = logging.getLogger("caixa_routes")
caixa_router = APIRouter(prefix="/Caixa", tags=["Caixa"])


# ══════════════════════════════════════════════════════════════════
# HELPERS  (inalterados)
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
    Registra ENTRADA no caixa do dia. Sem commit — responsabilidade do chamador.
    Chamado por order_routes.finalizar_pedido() na mesma transação.
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


# ── Schemas do fechamento ──────────────────────────────────────────

class ResponseCaixaFechadoSchema(BaseModel):
    """
    Schema de retorno para CaixaFechado.
    Retorna também o nome de quem fechou (sem expor senha/email).
    """
    id:             int
    data:           date
    caixa_inicial:  float
    total_entradas: float
    total_saidas:   float
    saldo_final:    float
    fechado_em:     datetime
    fechado_por:    Optional[str] = None   # nome do admin que fechou

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════
# ROTAS EXISTENTES  (inalteradas)
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
    return (
        session.query(Caixa)
        .filter(Caixa.data >= inicio)
        .order_by(Caixa.data.desc())
        .all()
    )


@caixa_router.get(
    "/historico-fechados",
    response_model=List[ResponseCaixaFechadoSchema],
    summary="Lista caixas fechados — snapshots imutáveis (admin)",
)
async def historico_fechados(
    dias:    int     = 30,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    """
    Retorna os snapshots de fechamento, do mais recente para o mais antigo.
    Parâmetro `dias` filtra pelo período (padrão: últimos 30 dias).
    """
    if dias < 1 or dias > 365:
        raise HTTPException(status_code=400, detail="dias deve estar entre 1 e 365")

    inicio = datetime.now(timezone.utc).date() - timedelta(days=dias - 1)
    fechados = (
        session.query(CaixaFechado)
        .filter(CaixaFechado.data >= inicio)
        .order_by(CaixaFechado.fechado_em.desc())
        .all()
    )

    # Montar response manualmente para injetar o nome do admin
    resultado = []
    for f in fechados:
        resultado.append({
            "id":             f.id,
            "data":           f.data,
            "caixa_inicial":  f.caixa_inicial,
            "total_entradas": f.total_entradas,
            "total_saidas":   f.total_saidas,
            "saldo_final":    f.saldo_final,
            "fechado_em":     f.fechado_em,
            "fechado_por":    f.fechado_por.nome if f.fechado_por else None,
        })

    return resultado


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
    return {
        "id": 0,
        "data": dia,
        "caixa_inicial": 0.0,
        "entradas": 0.0,
        "saidas": 0.0,
        "saldo_atual": 0.0,
        "criado_em": datetime.now(timezone.utc),
        "movimentacoes": []
    }

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
    return mov


# ══════════════════════════════════════════════════════════════════
# ROTA NOVA — POST /Caixa/fechar
# ══════════════════════════════════════════════════════════════════

@caixa_router.post(
    "/fechar",
    response_model=ResponseCaixaFechadoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Fecha o caixa do dia e grava snapshot imutável (admin)",
)
async def fechar_caixa(
    session: Session  = Depends(pegar_sessao),
    admin: Usuario    = Depends(verificar_admin),
):
    """
    ## O que este endpoint faz

    1. Busca o `Caixa` do dia atual.
    2. Verifica se já existe um `CaixaFechado` para hoje — impede duplicação.
    3. Cria um registro em `CaixaFechado` copiando os valores atuais do caixa
       (snapshot imutável).
    4. **Não altera nem apaga** o `Caixa` original — ele continua acessível.

    ## O que NÃO faz

    - Não impede novas movimentações no `Caixa` após o fechamento.
      Se quiser bloquear, implemente um campo `fechado=True` em `Caixa` futuramente.
    - Não consolida pedidos pendentes — apenas copia o estado atual.

    ## Retorna

    O snapshot gravado com data, valores e horário do fechamento.
    """
    hoje = datetime.now(timezone.utc).date()

    # ── 1. Verificar se já foi fechado hoje
    ja_fechado = session.query(CaixaFechado).filter(CaixaFechado.data == hoje).first()
    if ja_fechado:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O caixa de {hoje} já foi fechado às "
                f"{ja_fechado.fechado_em.strftime('%H:%M')} UTC "
                f"(id={ja_fechado.id})"
            ),
        )

    # ── 2. Buscar o caixa do dia
    caixa = session.query(Caixa).filter(Caixa.data == hoje).first()
    if not caixa:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum caixa aberto para {hoje}. "
                "Abra o caixa com POST /Caixa/abrir antes de fechar."
            ),
        )

    # ── 3. Criar snapshot
    agora         = datetime.now(timezone.utc)
    saldo_final   = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    fechado = CaixaFechado(
        data           = hoje,
        caixa_inicial  = caixa.caixa_inicial,
        total_entradas = caixa.entradas,
        total_saidas   = caixa.saidas,
        saldo_final    = saldo_final,
        fechado_em     = agora,
        fechado_por_id = admin.id,
    )
    session.add(fechado)

    try:
        session.commit()
        session.refresh(fechado)
    except Exception as exc:
        session.rollback()
        log.error("[CAIXA] Erro ao fechar caixa: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao fechar caixa: {exc}")

    log.info(
        "[CAIXA] Fechado por %s | data=%s | saldo=R$%.2f",
        admin.nome, hoje, saldo_final,
    )

    return {
        "id":             fechado.id,
        "data":           fechado.data,
        "caixa_inicial":  fechado.caixa_inicial,
        "total_entradas": fechado.total_entradas,
        "total_saidas":   fechado.total_saidas,
        "saldo_final":    fechado.saldo_final,
        "fechado_em":     fechado.fechado_em,
        "fechado_por":    admin.nome,
    }
