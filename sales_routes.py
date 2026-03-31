from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta

from dependencias import pegar_sessao, verificar_admin
from models import Pedido, ItemPedido, Usuario

sales_router = APIRouter(prefix="/Vendas", tags=["Vendas & Relatórios"])


# ============================================================
# HELPER: monta o resumo de um conjunto de pedidos
# Inclui breakdown completo por forma de pagamento
# ============================================================
def _resumo(pedidos: list, periodo: str) -> dict:
    finalizados = [p for p in pedidos if p.status == "FINALIZADO"]
    total       = len(finalizados)
    receita     = sum(p.preco_total for p in finalizados)

    # Breakdown por forma de pagamento
    dinheiro     = sum(p.preco_total for p in finalizados if p.forma_pagamento == "DINHEIRO")
    pix          = sum(p.preco_total for p in finalizados if p.forma_pagamento == "PIX")
    cartao       = sum(p.preco_total for p in finalizados if p.forma_pagamento == "CARTAO")
    nao_informado = sum(p.preco_total for p in finalizados if p.forma_pagamento is None)

    return {
        "periodo":       periodo,
        "total_pedidos": total,
        "receita_total": round(receita, 2),
        "ticket_medio":  round(receita / total, 2) if total else 0.0,
        "por_pagamento": {
            "dinheiro":      round(dinheiro, 2),
            "pix":           round(pix, 2),
            "cartao":        round(cartao, 2),
            "nao_informado": round(nao_informado, 2),
        },
        "pedidos_por_pagamento": {
            "dinheiro":      sum(1 for p in finalizados if p.forma_pagamento == "DINHEIRO"),
            "pix":           sum(1 for p in finalizados if p.forma_pagamento == "PIX"),
            "cartao":        sum(1 for p in finalizados if p.forma_pagamento == "CARTAO"),
            "nao_informado": sum(1 for p in finalizados if p.forma_pagamento is None),
        },
    }


def _filtrar(session: Session, inicio: datetime, fim: datetime) -> list:
    return (
        session.query(Pedido)
        .filter(Pedido.criado_em >= inicio, Pedido.criado_em <= fim)
        .all()
    )


# ============================================================
# VENDAS DO DIA
# ============================================================
@sales_router.get("/diario", summary="Vendas do dia atual (somente admin)")
async def vendas_diarias(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora  = datetime.now(timezone.utc)
    inicio = agora.replace(hour=0,  minute=0,  second=0,  microsecond=0)
    fim    = agora.replace(hour=23, minute=59, second=59, microsecond=999999)
    return _resumo(_filtrar(session, inicio, fim), f"Dia {agora.strftime('%d/%m/%Y')}")


# ============================================================
# VENDAS DOS ÚLTIMOS 7 DIAS
# ============================================================
@sales_router.get("/semanal", summary="Vendas dos últimos 7 dias (somente admin)")
async def vendas_semanais(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora  = datetime.now(timezone.utc)
    inicio = (agora - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    return _resumo(_filtrar(session, inicio, agora), f"{inicio.strftime('%d/%m/%Y')} → {agora.strftime('%d/%m/%Y')}")


# ============================================================
# VENDAS DO MÊS ATUAL
# ============================================================
@sales_router.get("/mensal", summary="Vendas do mês atual (somente admin)")
async def vendas_mensais(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora  = datetime.now(timezone.utc)
    inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return _resumo(_filtrar(session, inicio, agora), agora.strftime("%B/%Y"))


# ============================================================
# VENDAS DO ANO ATUAL
# ============================================================
@sales_router.get("/anual", summary="Vendas do ano atual (somente admin)")
async def vendas_anuais(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora  = datetime.now(timezone.utc)
    inicio = agora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return _resumo(_filtrar(session, inicio, agora), str(agora.year))


# ============================================================
# BREAKDOWN MÊS A MÊS DO ANO (com pagamento em cada mês)
# ============================================================
@sales_router.get("/anual/breakdown", summary="Receita mês a mês do ano atual com formas de pagamento (somente admin)")
async def vendas_anuais_breakdown(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora       = datetime.now(timezone.utc)
    nomes_meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    resultado   = []

    for mes in range(1, agora.month + 1):
        proximo = datetime(agora.year, mes + 1, 1, tzinfo=timezone.utc) if mes < 12 else datetime(agora.year + 1, 1, 1, tzinfo=timezone.utc)
        inicio  = datetime(agora.year, mes, 1, tzinfo=timezone.utc)
        fim     = proximo - timedelta(seconds=1)
        resultado.append(_resumo(_filtrar(session, inicio, fim), nomes_meses[mes - 1]))

    return {"ano": agora.year, "meses": resultado}


# ============================================================
# TOP PRODUTOS MAIS VENDIDOS (com receita por produto)
# ============================================================
@sales_router.get("/top-produtos", summary="Produtos mais vendidos com receita (somente admin)")
async def top_produtos(
    limite:  int = 10,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    rows = (
        session.query(
            ItemPedido.nomedoproduto,
            ItemPedido.variacao_nome,
            func.sum(ItemPedido.quantidade).label("total_vendido"),
            func.sum(ItemPedido.quantidade * ItemPedido.preco_unitario).label("receita"),
        )
        .join(Pedido, ItemPedido.pedido_id == Pedido.id)
        .filter(Pedido.status == "FINALIZADO")
        .group_by(ItemPedido.nomedoproduto, ItemPedido.variacao_nome)
        .order_by(func.sum(ItemPedido.quantidade).desc())
        .limit(limite)
        .all()
    )

    return [
        {
            "produto":       r.nomedoproduto,
            "variacao":      r.variacao_nome,   # null se sem variação
            "total_vendido": int(r.total_vendido),
            "receita":       round(float(r.receita), 2),
        }
        for r in rows
    ]


# ============================================================
# RESUMO GERAL — tudo de uma vez
# ============================================================
@sales_router.get("/resumo", summary="Resumo geral: diário, semanal, mensal e anual com pagamentos (somente admin)")
async def resumo_geral(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    agora  = datetime.now(timezone.utc)
    hoje   = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    semana = (agora - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
    mes    = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ano    = agora.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    return {
        "hoje":   _resumo(_filtrar(session, hoje,   agora), "Hoje"),
        "semana": _resumo(_filtrar(session, semana, agora), "Últimos 7 dias"),
        "mes":    _resumo(_filtrar(session, mes,    agora), agora.strftime("%B/%Y")),
        "ano":    _resumo(_filtrar(session, ano,    agora), str(agora.year)),
    }