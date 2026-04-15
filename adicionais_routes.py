"""
adicionais_routes.py
=====================
CRUD completo de adicionais por produto.
Segue exatamente o mesmo padrão de product_routes e bairro_routes.

Registre no main.py:
    from adicionais_routes import adicionais_router
    app.include_router(adicionais_router)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from dependencias import pegar_sessao, verificar_admin
from schemas import AdicionalSchema, ResponseAdicionalSchema
from models import AdicionalProduto, Produto, Usuario

adicionais_router = APIRouter(prefix="/Produto", tags=["Adicionais"])


# ==========================
# LISTAR adicionais de um produto  — público
# ==========================
@adicionais_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista adicionais de um produto",
)
async def listar_adicionais(
    produto_id: int,
    apenas_disponiveis: bool = True,
    session: Session = Depends(pegar_sessao),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    q = session.query(AdicionalProduto).filter(AdicionalProduto.produto_id == produto_id)
    if apenas_disponiveis:
        q = q.filter(AdicionalProduto.disponivel == True)

    return q.order_by(AdicionalProduto.nome).all()


# ==========================
# CRIAR adicional  — admin
# ==========================
@adicionais_router.post(
    "/produtos/{produto_id}/adicionais",
    response_model=ResponseAdicionalSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria adicional para um produto (somente admin)",
)
async def criar_adicional(
    produto_id: int,
    dados:      AdicionalSchema,
    session:    Session = Depends(pegar_sessao),
    _: Usuario          = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicional = AdicionalProduto(
        nome       = dados.nome,
        descricao  = dados.descricao,
        preco      = dados.preco,
        disponivel = dados.disponivel if dados.disponivel is not None else True,
        produto_id = produto_id,
    )
    session.add(adicional)
    try:
        session.commit()
        session.refresh(adicional)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao criar adicional")

    return adicional


# ==========================
# EDITAR adicional  — admin
# ==========================
@adicionais_router.put(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    response_model=ResponseAdicionalSchema,
    summary="Edita adicional (somente admin)",
)
async def editar_adicional(
    produto_id:   int,
    adicional_id: int,
    dados:        AdicionalSchema,
    session:      Session = Depends(pegar_sessao),
    _: Usuario            = Depends(verificar_admin),
):
    adicional = (
        session.query(AdicionalProduto)
        .filter(
            AdicionalProduto.id         == adicional_id,
            AdicionalProduto.produto_id == produto_id,
        )
        .first()
    )
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    adicional.nome      = dados.nome
    adicional.descricao = dados.descricao
    adicional.preco     = dados.preco
    if dados.disponivel is not None:
        adicional.disponivel = dados.disponivel

    try:
        session.commit()
        session.refresh(adicional)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao atualizar adicional")

    return adicional


# ==========================
# ATIVAR / DESATIVAR  — admin
# ==========================
@adicionais_router.patch(
    "/produtos/{produto_id}/adicionais/{adicional_id}/disponivel",
    response_model=ResponseAdicionalSchema,
    summary="Ativa ou desativa adicional (somente admin)",
)
async def toggle_adicional(
    produto_id:   int,
    adicional_id: int,
    disponivel:   bool,
    session:      Session = Depends(pegar_sessao),
    _: Usuario            = Depends(verificar_admin),
):
    adicional = (
        session.query(AdicionalProduto)
        .filter(
            AdicionalProduto.id         == adicional_id,
            AdicionalProduto.produto_id == produto_id,
        )
        .first()
    )
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    adicional.disponivel = disponivel
    session.commit()

    return adicional


# ==========================
# DELETAR adicional  — admin
# ==========================
@adicionais_router.delete(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    summary="Remove adicional (somente admin)",
)
async def deletar_adicional(
    produto_id:   int,
    adicional_id: int,
    session:      Session = Depends(pegar_sessao),
    _: Usuario            = Depends(verificar_admin),
):
    adicional = (
        session.query(AdicionalProduto)
        .filter(
            AdicionalProduto.id         == adicional_id,
            AdicionalProduto.produto_id == produto_id,
        )
        .first()
    )
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    nome = adicional.nome
    session.delete(adicional)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Erro ao remover adicional")

    return {"mensagem": f"Adicional '{nome}' removido com sucesso"}
