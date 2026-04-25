"""
services/caixa_service.py
==========================
Camada de serviço para o caixa financeiro.

Responsabilidades:
  - Toda lógica de negócio do caixa fica aqui
  - Sem dependência de FastAPI (sem HTTPException, sem APIRouter)
  - Levanta exceções de domínio (CaixaError) que os routers traduzem em HTTP
  - Funções são puras em relação à sessão: recebem Session, não fazem commit

Por que sem commit:
  registrar_entrada() é chamado dentro da transação de finalizar_pedido().
  O commit único garante atomicidade total: pedido + caixa ou nada.
  Se o chamador quiser commitar, ele chama session.commit() depois.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import Caixa, CaixaFechado, MovimentacaoCaixa, TipoMovimentacao

log = logging.getLogger("caixa_service")


# ══════════════════════════════════════════════════════════════════
# EXCEÇÕES DE DOMÍNIO
# Routers capturam e convertem para HTTPException.
# Services nunca importam FastAPI.
# ══════════════════════════════════════════════════════════════════

class CaixaError(Exception):
    """Erro de regra de negócio do caixa."""


class CaixaJaFechadoError(CaixaError):
    pass


class CaixaNaoEncontradoError(CaixaError):
    pass


class SaldoInsuficienteError(CaixaError):
    pass


class ValorInvalidoError(CaixaError):
    pass


# ══════════════════════════════════════════════════════════════════
# FUNÇÕES INTERNAS (prefixo _ = uso apenas neste módulo)
# ══════════════════════════════════════════════════════════════════

def _obter_ou_criar_caixa(dia: date, session: Session) -> Caixa:
    """
    Retorna o caixa do dia, criando-o com saldo zero se não existir.

    Race condition protection:
      flush() tenta inserir; se outro request ganhar a corrida e violar
      o unique constraint em `data`, fazemos rollback parcial e relemos.
      Isso é seguro porque a sessão usa autocommit=False por padrão.
    """
    caixa = session.query(Caixa).filter(Caixa.data == dia).first()
    if caixa:
        return caixa

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
    except IntegrityError:
        # Outro worker criou o caixa simultaneamente — desfaz e relê
        session.rollback()
        caixa = session.query(Caixa).filter(Caixa.data == dia).first()
        if not caixa:
            raise  # erro real, não race condition
    return caixa


# ══════════════════════════════════════════════════════════════════
# API PÚBLICA DO SERVIÇO
# ══════════════════════════════════════════════════════════════════

def registrar_entrada(
    session:   Session,
    valor:     float,
    descricao: str,
    pedido_id: Optional[int] = None,
) -> MovimentacaoCaixa:
    """
    Registra uma ENTRADA no caixa do dia atual.

    Não faz commit — responsabilidade do chamador.
    Projetado para ser chamado dentro da transação de finalizar_pedido()
    garantindo atomicidade total (pedido + caixa num único commit).

    Levanta:
        ValorInvalidoError — se valor <= 0
    """
    if valor <= 0:
        raise ValorInvalidoError(
            f"Valor de entrada deve ser positivo, recebido: {valor:.2f}"
        )

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

    log.info(
        "[CaixaService] ENTRADA R$%.2f | pedido_id=%s | saldo_atual=R$%.2f",
        valor, pedido_id, caixa.saldo_atual,
    )
    return mov


def registrar_saida(
    session:   Session,
    valor:     float,
    tipo:      TipoMovimentacao,
    descricao: Optional[str] = None,
) -> MovimentacaoCaixa:
    """
    Registra SAIDA, SANGRIA ou SUPRIMENTO no caixa do dia.
    Não faz commit.

    Levanta:
        ValorInvalidoError       — valor <= 0
        SaldoInsuficienteError   — saldo insuficiente para SAIDA/SANGRIA
    """
    if valor <= 0:
        raise ValorInvalidoError(f"Valor deve ser positivo, recebido: {valor:.2f}")

    hoje  = datetime.now(timezone.utc).date()
    caixa = _obter_ou_criar_caixa(hoje, session)

    if tipo in (TipoMovimentacao.SAIDA, TipoMovimentacao.SANGRIA):
        if valor > caixa.saldo_atual:
            raise SaldoInsuficienteError(
                f"Valor R${valor:.2f} excede o saldo atual R${caixa.saldo_atual:.2f}"
            )
        caixa.saidas      += valor
        caixa.saldo_atual  = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    elif tipo == TipoMovimentacao.SUPRIMENTO:
        caixa.caixa_inicial += valor
        caixa.saldo_atual    = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    mov = MovimentacaoCaixa(
        tipo      = tipo,
        valor     = valor,
        descricao = descricao,
        caixa_id  = caixa.id,
        pedido_id = None,
    )
    session.add(mov)

    log.info(
        "[CaixaService] %s R$%.2f | saldo_atual=R$%.2f",
        tipo.value, valor, caixa.saldo_atual,
    )
    return mov


def criar_snapshot_fechamento(
    session:         Session,
    fechado_por_id:  Optional[int] = None,
) -> CaixaFechado:
    """
    Cria um snapshot imutável do caixa do dia atual.
    Não faz commit.

    Levanta:
        CaixaNaoEncontradoError — caixa do dia não existe
        CaixaJaFechadoError     — caixa já foi fechado hoje
    """
    hoje = datetime.now(timezone.utc).date()

    ja_fechado = session.query(CaixaFechado).filter(CaixaFechado.data == hoje).first()
    if ja_fechado:
        raise CaixaJaFechadoError(
            f"Caixa de {hoje} já foi fechado às "
            f"{ja_fechado.fechado_em.strftime('%H:%M')} UTC (id={ja_fechado.id})"
        )

    caixa = session.query(Caixa).filter(Caixa.data == hoje).first()
    if not caixa:
        raise CaixaNaoEncontradoError(
            f"Nenhum caixa aberto para {hoje}. "
            "Abra o caixa com POST /Caixa/abrir antes de fechar."
        )

    saldo_final = caixa.caixa_inicial + caixa.entradas - caixa.saidas

    fechado = CaixaFechado(
        data           = hoje,
        caixa_inicial  = caixa.caixa_inicial,
        total_entradas = caixa.entradas,
        total_saidas   = caixa.saidas,
        saldo_final    = saldo_final,
        fechado_em     = datetime.now(timezone.utc),
        fechado_por_id = fechado_por_id,
    )
    session.add(fechado)

    log.info(
        "[CaixaService] Snapshot criado | data=%s | saldo_final=R$%.2f",
        hoje, saldo_final,
    )
    return fechado
