"""
bairro_routes.py — VERSÃO COMPLETA
=====================================
O sistema já usava Bairro como taxa de entrega por bairro.
Esta versão adiciona o que estava faltando:
  - GET /{bairro_id} — busca individual (estava ausente)
  - try/except + rollback em criar e atualizar
  - Logs em todas as operações de escrita
  - Verificação de nome duplicado no PUT também
  - Documentação inline
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from dependencias import pegar_sessao, verificar_admin
from schemas import BairroSchema, ResponseBairroSchema
from models import Bairro, Usuario

log = logging.getLogger("bairro_routes")

# ── Router principal  (prefixo /Bairros — não alterar, pedidos dependem dele)
bairro_router = APIRouter(prefix="/Bairros", tags=["Bairros / Taxas de Entrega"])

# ── Alias em /delivery para quem preferir esse padrão
# Ambos apontam para as mesmas funções — sem duplicação de lógica.
delivery_router = APIRouter(prefix="/delivery", tags=["Delivery Rates"])


# ══════════════════════════════════════════════════════════════════
# GET /  — listar todos
# ══════════════════════════════════════════════════════════════════

async def _listar(apenas_ativos: bool, session: Session):
    q = session.query(Bairro)
    if apenas_ativos:
        q = q.filter(Bairro.ativo == True)
    return q.order_by(Bairro.nome).all()


@bairro_router.get(
    "/",
    response_model=List[ResponseBairroSchema],
    summary="Lista bairros com taxa de entrega (público)",
)
async def listar_bairros(
    apenas_ativos: bool    = True,
    session: Session       = Depends(pegar_sessao),
):
    """
    Retorna todos os bairros com suas taxas de entrega.
    Por padrão retorna apenas os ativos.
    Passe `apenas_ativos=false` para ver todos.
    """
    return await _listar(apenas_ativos, session)


@delivery_router.get(
    "/",
    response_model=List[ResponseBairroSchema],
    summary="Lista taxas de entrega (público)",
)
async def listar_delivery(
    apenas_ativos: bool    = True,
    session: Session       = Depends(pegar_sessao),
):
    return await _listar(apenas_ativos, session)


# ══════════════════════════════════════════════════════════════════
# GET /{id}  — buscar individual  (estava faltando)
# ══════════════════════════════════════════════════════════════════

async def _buscar_por_id(bairro_id: int, session: Session) -> Bairro:
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")
    return bairro


@bairro_router.get(
    "/{bairro_id}",
    response_model=ResponseBairroSchema,
    summary="Busca bairro por ID (público)",
)
async def buscar_bairro(
    bairro_id: int,
    session: Session = Depends(pegar_sessao),
):
    return await _buscar_por_id(bairro_id, session)


@delivery_router.get(
    "/{bairro_id}",
    response_model=ResponseBairroSchema,
    summary="Busca taxa de entrega por ID (público)",
)
async def buscar_delivery(
    bairro_id: int,
    session: Session = Depends(pegar_sessao),
):
    return await _buscar_por_id(bairro_id, session)


# ══════════════════════════════════════════════════════════════════
# POST /  — criar
# ══════════════════════════════════════════════════════════════════

async def _criar(dados: BairroSchema, session: Session, admin: Usuario) -> Bairro:
    log.info("[BAIRRO] POST | nome=%s | valor=R$%.2f", dados.nome, dados.valor_entrega)

    existe = session.query(Bairro).filter(Bairro.nome == dados.nome.strip()).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail=f"Bairro '{dados.nome}' já está cadastrado (id={existe.id})",
        )

    bairro = Bairro(
        nome          = dados.nome.strip(),
        valor_entrega = dados.valor_entrega,
        ativo         = dados.ativo if dados.ativo is not None else True,
    )
    session.add(bairro)
    try:
        session.commit()
        session.refresh(bairro)
    except Exception as exc:
        session.rollback()
        log.error("[BAIRRO] Erro ao criar: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar bairro: {exc}")

    log.info("[BAIRRO] Criado id=%s | nome=%s | valor=R$%.2f", bairro.id, bairro.nome, bairro.valor_entrega)
    return bairro


@bairro_router.post(
    "/",
    response_model=ResponseBairroSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra bairro com taxa de entrega (admin)",
)
async def criar_bairro(
    dados:   BairroSchema,
    session: Session  = Depends(pegar_sessao),
    admin: Usuario    = Depends(verificar_admin),
):
    """
    Cadastra um bairro com sua taxa de entrega.

    **Exemplo:**
    ```json
    {
      "nome": "Centro",
      "valor_entrega": 5.00,
      "ativo": true
    }
    ```
    """
    return await _criar(dados, session, admin)


@delivery_router.post(
    "/",
    response_model=ResponseBairroSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra taxa de entrega (admin)",
)
async def criar_delivery(
    dados:   BairroSchema,
    session: Session  = Depends(pegar_sessao),
    admin: Usuario    = Depends(verificar_admin),
):
    return await _criar(dados, session, admin)


# ══════════════════════════════════════════════════════════════════
# PUT /{id}  — atualizar
# ══════════════════════════════════════════════════════════════════

async def _atualizar(bairro_id: int, dados: BairroSchema, session: Session) -> Bairro:
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")

    # Verificar conflito de nome com OUTRO bairro
    conflito = (
        session.query(Bairro)
        .filter(Bairro.nome == dados.nome.strip(), Bairro.id != bairro_id)
        .first()
    )
    if conflito:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe outro bairro com o nome '{dados.nome}' (id={conflito.id})",
        )

    bairro.nome          = dados.nome.strip()
    bairro.valor_entrega = dados.valor_entrega
    if dados.ativo is not None:
        bairro.ativo = dados.ativo

    try:
        session.commit()
        session.refresh(bairro)
    except Exception as exc:
        session.rollback()
        log.error("[BAIRRO] Erro ao atualizar #%s: %s", bairro_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar bairro: {exc}")

    log.info("[BAIRRO] Atualizado id=%s | nome=%s | valor=R$%.2f", bairro.id, bairro.nome, bairro.valor_entrega)
    return bairro


@bairro_router.put(
    "/{bairro_id}",
    response_model=ResponseBairroSchema,
    summary="Atualiza bairro (admin)",
)
async def atualizar_bairro(
    bairro_id: int,
    dados:   BairroSchema,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _atualizar(bairro_id, dados, session)


@delivery_router.put(
    "/{bairro_id}",
    response_model=ResponseBairroSchema,
    summary="Atualiza taxa de entrega (admin)",
)
async def atualizar_delivery(
    bairro_id: int,
    dados:   BairroSchema,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _atualizar(bairro_id, dados, session)


# ══════════════════════════════════════════════════════════════════
# DELETE /{id}  — remover
# ══════════════════════════════════════════════════════════════════

async def _deletar(bairro_id: int, session: Session) -> dict:
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")

    nome = bairro.nome
    session.delete(bairro)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível remover '{nome}' — existem pedidos vinculados a este bairro. "
                "Desative-o em vez de deletar (PATCH /{id}/ativar)."
            ),
        )

    log.info("[BAIRRO] Removido id=%s | nome=%s", bairro_id, nome)
    return {"mensagem": f"Bairro '{nome}' removido com sucesso"}


@bairro_router.delete(
    "/{bairro_id}",
    summary="Remove bairro (admin)",
)
async def deletar_bairro(
    bairro_id: int,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _deletar(bairro_id, session)


@delivery_router.delete(
    "/{bairro_id}",
    summary="Remove taxa de entrega (admin)",
)
async def deletar_delivery(
    bairro_id: int,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _deletar(bairro_id, session)


# ══════════════════════════════════════════════════════════════════
# PATCH /{id}/ativar  — toggle ativo/inativo
# ══════════════════════════════════════════════════════════════════

async def _toggle(bairro_id: int, ativo: bool, session: Session) -> dict:
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")

    bairro.ativo = ativo
    session.commit()

    status_str = "ativado" if ativo else "desativado"
    log.info("[BAIRRO] id=%s %s", bairro_id, status_str)
    return {"mensagem": f"Bairro '{bairro.nome}' {status_str}"}


@bairro_router.patch(
    "/{bairro_id}/ativar",
    summary="Ativa ou desativa bairro (admin)",
)
async def toggle_bairro(
    bairro_id: int,
    ativo:   bool,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _toggle(bairro_id, ativo, session)


@delivery_router.patch(
    "/{bairro_id}/ativar",
    summary="Ativa ou desativa taxa de entrega (admin)",
)
async def toggle_delivery(
    bairro_id: int,
    ativo:   bool,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    return await _toggle(bairro_id, ativo, session)
