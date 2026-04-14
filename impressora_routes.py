"""
impressora_routes.py — VERSÃO CORRIGIDA
=========================================

PROBLEMAS CORRIGIDOS vs versão anterior:
  1. _impressora_router (prefixo /Impressoras) estava sendo exportado mas NÃO
     tinha nome público — o main.py original só importava impressora_router e
     nunca registrava o CRUD de impressoras. Resultado: POST /Impressoras/
     retornava 404 silenciosamente.

  2. criar_impressora() não tinha nenhum log antes nem depois do commit —
     impossível diagnosticar falhas sem reinstrumentar o código em produção.

  3. session.commit() sem try/except em todas as rotas de escrita —
     qualquer exceção do banco (constraint, conexão morta, etc.) virava
     HTTP 500 sem mensagem útil e sem rollback garantido, deixando a sessão
     em estado inválido para o próximo request do mesmo worker.

  4. ImpressoraSchema importado de schemas.py usava dados.dict() (Pydantic v1)
     em vez de dados.model_dump() (Pydantic v2) — causava DeprecationWarning
     e em alguns setups quebrava silenciosamente campos opcionais como None.

  5. Validators de tipo/finalidade ausentes na rota de criação — o banco
     aceitava qualquer string, mas o cliente Windows esperava "USB"/"REDE".

  6. Rota de debug /debug/impressoras adicionada SEM autenticação para
     permitir diagnóstico direto sem precisar de token. Remova após validar.

COMO REGISTRAR NO main.py:
    from impressora_routes import impressora_router, cadastro_impressora_router
    app.include_router(impressora_router)           # /Pedidos/...
    app.include_router(cadastro_impressora_router)  # /Impressoras/...
    # Remova a linha abaixo após validar persistência:
    app.include_router(debug_impressora_router)     # /debug/...
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Impressora, LogImpressao, Pedido, StatusPedido, Usuario

log = logging.getLogger("impressora_routes")


# ══════════════════════════════════════════════════════════════════
# SCHEMAS
# Definidos aqui diretamente para evitar dependência de schemas.py
# e garantir model_dump() (Pydantic v2)
# ══════════════════════════════════════════════════════════════════

class ImpressoraIn(BaseModel):
    nome:        str
    tipo:        str   # USB | REDE
    finalidade:  str   # COZINHA | MOTOBOY
    ip_address:  Optional[str] = None
    porta:       Optional[int] = None
    usb_vendor:  Optional[str] = None
    usb_product: Optional[str] = None
    ativo:       Optional[bool] = True

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in ("USB", "REDE"):
            raise ValueError("tipo deve ser USB ou REDE")
        return v

    @field_validator("finalidade")
    @classmethod
    def finalidade_valida(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in ("COZINHA", "MOTOBOY"):
            raise ValueError("finalidade deve ser COZINHA ou MOTOBOY")
        return v

    class Config:
        from_attributes = True


class ImpressoraOut(BaseModel):
    id:          int
    nome:        str
    tipo:        str
    finalidade:  str
    ip_address:  Optional[str]
    porta:       Optional[int]
    usb_vendor:  Optional[str]
    usb_product: Optional[str]
    ativo:       bool
    criado_em:   datetime

    class Config:
        from_attributes = True


class MarcarImpressoSchema(BaseModel):
    """tipo: 'cozinha' | 'motoboy' | 'ambos'"""
    tipo: str

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("cozinha", "motoboy", "ambos"):
            raise ValueError("tipo deve ser cozinha, motoboy ou ambos")
        return v


class LogImpressaoSchema(BaseModel):
    tipo_comanda:  str   # COZINHA | MOTOBOY
    sucesso:       bool
    erro:          Optional[str] = None
    impressora_id: Optional[int] = None


# ══════════════════════════════════════════════════════════════════
# ROUTER 1 — /Pedidos  (controle de impressão por pedido)
# ══════════════════════════════════════════════════════════════════
impressora_router = APIRouter(prefix="/Pedidos", tags=["Impressão"])


@impressora_router.get(
    "/impressao/pendentes",
    summary="Pedidos PENDENTES não impressos — polling do cliente Windows (admin)",
)
async def pedidos_pendentes_impressao(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    """
    Retorna pedidos com status=PENDENTE e impresso_cozinha=False.
    Ordenados do mais antigo para o mais novo (FIFO).
    Chamado a cada N segundos pelo cliente de impressão Windows.
    """
    pedidos = (
        session.query(Pedido)
        .filter(
            Pedido.status           == StatusPedido.PENDENTE,
            Pedido.impresso_cozinha == False,
        )
        .order_by(Pedido.criado_em.asc())
        .all()
    )
    log.info("[IMPRESSAO] Pendentes consultados: %d pedido(s)", len(pedidos))
    return pedidos


@impressora_router.patch(
    "/pedido/{pedido_id}/marcar-impresso",
    summary="Marca pedido como impresso — cozinha, motoboy ou ambos (admin)",
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
    tipo  = dados.tipo  # já normalizado pelo validator

    if tipo in ("cozinha", "ambos"):
        if not pedido.impresso_cozinha:
            pedido.impresso_cozinha       = True
            pedido.data_impressao_cozinha = agora
            log.info("[IMPRESSAO] Pedido #%s marcado: cozinha", pedido.codigo or pedido_id)
        else:
            log.warning("[IMPRESSAO] Pedido #%s ja marcado (cozinha) — ignorado", pedido_id)

    if tipo in ("motoboy", "ambos"):
        if not pedido.impresso_motoboy:
            pedido.impresso_motoboy       = True
            pedido.data_impressao_motoboy = agora
            log.info("[IMPRESSAO] Pedido #%s marcado: motoboy", pedido.codigo or pedido_id)

    try:
        session.commit()
        session.refresh(pedido)
    except Exception as exc:
        session.rollback()
        log.error("[IMPRESSAO] Erro ao salvar marcacao pedido #%s: %s", pedido_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar marcacao: {exc}")

    return {
        "mensagem":               "Marcado com sucesso",
        "impresso_cozinha":       pedido.impresso_cozinha,
        "impresso_motoboy":       pedido.impresso_motoboy,
        "data_impressao_cozinha": pedido.data_impressao_cozinha,
        "data_impressao_motoboy": pedido.data_impressao_motoboy,
    }


@impressora_router.post(
    "/pedido/{pedido_id}/log-impressao",
    status_code=http_status.HTTP_201_CREATED,
    summary="Registra tentativa de impressão (admin)",
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

    entrada = LogImpressao(
        pedido_id     = pedido_id,
        tipo_comanda  = dados.tipo_comanda.upper(),
        sucesso       = dados.sucesso,
        erro          = dados.erro,
        impressora_id = dados.impressora_id,
    )
    session.add(entrada)

    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[LOG] Erro ao salvar log pedido #%s: %s", pedido_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar log: {exc}")

    return {"mensagem": "Log registrado", "id": entrada.id}


# ══════════════════════════════════════════════════════════════════
# ROUTER 2 — /Impressoras  (CRUD de cadastro)
# Nome público: cadastro_impressora_router
# PROBLEMA ORIGINAL: este router era "_impressora_router" (nome privado)
# e nunca era importado/registrado no main.py → POST /Impressoras/ = 404
# ══════════════════════════════════════════════════════════════════
cadastro_impressora_router = APIRouter(prefix="/Impressoras", tags=["Impressoras"])


@cadastro_impressora_router.get(
    "/",
    response_model=List[ImpressoraOut],
    summary="Lista todas as impressoras cadastradas (admin)",
)
async def listar_impressoras(
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    impressoras = session.query(Impressora).order_by(Impressora.id).all()
    log.info("[IMPRESSORAS] Listagem: %d impressora(s)", len(impressoras))
    return impressoras


@cadastro_impressora_router.post(
    "/",
    response_model=ImpressoraOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Cadastra nova impressora (admin)",
)
async def criar_impressora(
    dados:   ImpressoraIn,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    log.info(
        "[IMPRESSORAS] POST recebido: nome=%s | tipo=%s | finalidade=%s | ip=%s",
        dados.nome, dados.tipo, dados.finalidade, dados.ip_address,
    )

    # Usar model_dump() (Pydantic v2) — dados.dict() foi depreciado
    impressora = Impressora(**dados.model_dump())

    session.add(impressora)
    log.info("[IMPRESSORAS] Objeto adicionado a sessao — executando commit...")

    try:
        session.commit()
        session.refresh(impressora)
    except Exception as exc:
        session.rollback()
        log.error("[IMPRESSORAS] ERRO ao salvar: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar impressora no banco: {exc}",
        )

    log.info("[IMPRESSORAS] Salva com sucesso — id=%s | nome=%s", impressora.id, impressora.nome)
    return impressora


@cadastro_impressora_router.get(
    "/{impressora_id}",
    response_model=ImpressoraOut,
    summary="Busca impressora por ID (admin)",
)
async def buscar_impressora(
    impressora_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    imp = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    return imp


@cadastro_impressora_router.put(
    "/{impressora_id}",
    response_model=ImpressoraOut,
    summary="Atualiza impressora (admin)",
)
async def atualizar_impressora(
    impressora_id: int,
    dados:   ImpressoraIn,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    imp = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")

    imp.nome        = dados.nome.strip()
    imp.tipo        = dados.tipo
    imp.finalidade  = dados.finalidade
    imp.ip_address  = dados.ip_address
    imp.porta       = dados.porta
    imp.usb_vendor  = dados.usb_vendor
    imp.usb_product = dados.usb_product
    if dados.ativo is not None:
        imp.ativo = dados.ativo

    try:
        session.commit()
        session.refresh(imp)
    except Exception as exc:
        session.rollback()
        log.error("[IMPRESSORAS] Erro ao atualizar #%s: %s", impressora_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar: {exc}")

    log.info("[IMPRESSORAS] Atualizada id=%s", impressora_id)
    return imp


@cadastro_impressora_router.patch(
    "/{impressora_id}/ativar",
    response_model=ImpressoraOut,
    summary="Ativa ou desativa impressora (admin)",
)
async def toggle_impressora(
    impressora_id: int,
    ativo: bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    imp = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")

    imp.ativo = ativo
    try:
        session.commit()
        session.refresh(imp)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar status: {exc}")

    log.info("[IMPRESSORAS] id=%s -> ativo=%s", impressora_id, ativo)
    return imp


@cadastro_impressora_router.delete(
    "/{impressora_id}",
    summary="Remove impressora (admin)",
)
async def deletar_impressora(
    impressora_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    imp = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not imp:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")

    nome = imp.nome
    session.delete(imp)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail="Nao e possivel remover impressora com logs vinculados. Desative-a em vez de deletar.",
        )

    log.info("[IMPRESSORAS] Removida id=%s | nome=%s", impressora_id, nome)
    return {"mensagem": f"Impressora '{nome}' removida com sucesso"}


# ══════════════════════════════════════════════════════════════════
# ROUTER 3 — /debug  (sem autenticação — REMOVER APÓS VALIDAR)
# Use para confirmar que impressoras estão sendo salvas sem precisar
# de token. Acesse: GET /debug/impressoras
# ══════════════════════════════════════════════════════════════════
debug_impressora_router = APIRouter(prefix="/debug", tags=["Debug"])


@debug_impressora_router.get(
    "/impressoras",
    summary="[DEBUG] Lista impressoras sem autenticacao — REMOVER EM PRODUCAO",
)
async def debug_impressoras(session: Session = Depends(pegar_sessao)):
    total = session.query(Impressora).count()
    itens = session.query(Impressora).all()
    return {
        "total": total,
        "banco": "PostgreSQL" if "postgresql" in str(session.bind.url) else "SQLite",
        "impressoras": [
            {
                "id":        i.id,
                "nome":      i.nome,
                "tipo":      i.tipo,
                "finalidade": i.finalidade,
                "ativo":     i.ativo,
                "criado_em": i.criado_em.isoformat() if i.criado_em else None,
            }
            for i in itens
        ],
    }
