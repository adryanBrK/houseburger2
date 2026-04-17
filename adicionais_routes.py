"""
adicionais_routes.py
=====================
CRUD completo de adicionais globais + gerenciamento de vínculos com produtos.

Registre no main.py:
    from adicionais_routes import adicionais_router
    app.include_router(adicionais_router)
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Adicional, Produto, Usuario
from schemas import AdicionalSchema, ResponseAdicionalSchema, ResponseProdutoSchema

log = logging.getLogger("adicionais_routes")
adicionais_router = APIRouter(prefix="/Adicionais", tags=["Adicionais"])


# ══════════════════════════════════════════════════════════════════
# CRUD DE ADICIONAIS GLOBAIS
# ══════════════════════════════════════════════════════════════════

@adicionais_router.get(
    "/",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista todos os adicionais (público)",
)
async def listar_adicionais(
    apenas_ativos: bool = True,
    session: Session    = Depends(pegar_sessao),
):
    q = session.query(Adicional)
    if apenas_ativos:
        q = q.filter(Adicional.ativo == True)
    return q.order_by(Adicional.nome).all()


@adicionais_router.get(
    "/{adicional_id}",
    response_model=ResponseAdicionalSchema,
    summary="Busca adicional por ID (público)",
)
async def buscar_adicional(
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
):
    a = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")
    return a


@adicionais_router.post(
    "/",
    response_model=ResponseAdicionalSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria adicional global (admin)",
)
async def criar_adicional(
    dados:   AdicionalSchema,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    # Impedir duplicação de nome
    existe = session.query(Adicional).filter(Adicional.nome == dados.nome.strip()).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe um adicional com o nome '{dados.nome}'",
        )

    adicional = Adicional(
        nome       = dados.nome.strip(),
        descricao  = dados.descricao,
        preco      = dados.preco,
        ativo      = dados.ativo if dados.ativo is not None else True,
        limite_qtd = dados.limite_qtd,
    )
    session.add(adicional)
    try:
        session.commit()
        session.refresh(adicional)
    except Exception as exc:
        session.rollback()
        log.error("[ADICIONAIS] Erro ao criar: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar adicional: {exc}")

    log.info("[ADICIONAIS] Criado id=%s nome=%s", adicional.id, adicional.nome)
    return adicional


@adicionais_router.put(
    "/{adicional_id}",
    response_model=ResponseAdicionalSchema,
    summary="Atualiza adicional (admin)",
)
async def atualizar_adicional(
    adicional_id: int,
    dados:   AdicionalSchema,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    # Verificar conflito de nome com outro adicional
    conflito = (
        session.query(Adicional)
        .filter(Adicional.nome == dados.nome.strip(), Adicional.id != adicional_id)
        .first()
    )
    if conflito:
        raise HTTPException(
            status_code=400,
            detail=f"Já existe outro adicional com o nome '{dados.nome}'",
        )

    adicional.nome       = dados.nome.strip()
    adicional.descricao  = dados.descricao
    adicional.preco      = dados.preco
    adicional.limite_qtd = dados.limite_qtd
    if dados.ativo is not None:
        adicional.ativo = dados.ativo

    try:
        session.commit()
        session.refresh(adicional)
    except Exception as exc:
        session.rollback()
        log.error("[ADICIONAIS] Erro ao atualizar #%s: %s", adicional_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar adicional: {exc}")

    log.info("[ADICIONAIS] Atualizado id=%s", adicional_id)
    return adicional


@adicionais_router.patch(
    "/{adicional_id}/ativar",
    response_model=ResponseAdicionalSchema,
    summary="Ativa ou desativa adicional (admin)",
)
async def toggle_adicional(
    adicional_id: int,
    ativo:   bool,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    adicional.ativo = ativo
    session.commit()
    session.refresh(adicional)

    log.info("[ADICIONAIS] id=%s ativo=%s", adicional_id, ativo)
    return adicional


@adicionais_router.delete(
    "/{adicional_id}",
    summary="Remove adicional (admin)",
)
async def deletar_adicional(
    adicional_id: int,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    nome = adicional.nome
    # O cascade na tabela produto_adicional (ondelete=CASCADE) remove
    # automaticamente os vínculos com produtos ao deletar o adicional.
    session.delete(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao remover adicional: {exc}")

    log.info("[ADICIONAIS] Removido id=%s nome=%s", adicional_id, nome)
    return {"mensagem": f"Adicional '{nome}' removido com sucesso"}


# ══════════════════════════════════════════════════════════════════
# VÍNCULOS  produto ↔ adicional
# ══════════════════════════════════════════════════════════════════

@adicionais_router.get(
    "/produto/{produto_id}",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista adicionais disponíveis para um produto (público)",
)
async def listar_adicionais_do_produto(
    produto_id:    int,
    apenas_ativos: bool = True,
    session: Session    = Depends(pegar_sessao),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    if apenas_ativos:
        return [a for a in produto.adicionais if a.ativo]
    return produto.adicionais


@adicionais_router.post(
    "/produto/{produto_id}/{adicional_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Vincula adicional a um produto (admin)",
)
async def vincular_adicional_produto(
    produto_id:   int,
    adicional_id: int,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    # Impedir duplicação do vínculo
    if adicional in produto.adicionais:
        raise HTTPException(
            status_code=400,
            detail=f"Adicional '{adicional.nome}' já está vinculado a '{produto.nome}'",
        )

    produto.adicionais.append(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao vincular: {exc}")

    log.info("[ADICIONAIS] Vinculado adicional#%s ao produto#%s", adicional_id, produto_id)
    return {
        "mensagem":  f"Adicional '{adicional.nome}' vinculado a '{produto.nome}'",
        "produto_id":   produto_id,
        "adicional_id": adicional_id,
    }


@adicionais_router.delete(
    "/produto/{produto_id}/{adicional_id}",
    summary="Remove vínculo adicional ↔ produto (admin)",
)
async def desvincular_adicional_produto(
    produto_id:   int,
    adicional_id: int,
    session: Session  = Depends(pegar_sessao),
    _: Usuario        = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    if adicional not in produto.adicionais:
        raise HTTPException(
            status_code=400,
            detail=f"Adicional '{adicional.nome}' não está vinculado a '{produto.nome}'",
        )

    produto.adicionais.remove(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao desvincular: {exc}")

    log.info("[ADICIONAIS] Desvinculado adicional#%s do produto#%s", adicional_id, produto_id)
    return {
        "mensagem":  f"Adicional '{adicional.nome}' removido de '{produto.nome}'",
        "produto_id":   produto_id,
        "adicional_id": adicional_id,
    }
