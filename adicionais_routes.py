"""
adicionais_routes.py
====================

Rotas de adicionais POR PRODUTO.

Prefixo: /Produto

Rotas:
  GET    /Produto/produtos/{produto_id}/adicionais
  POST   /Produto/produtos/{produto_id}/adicionais
  DELETE /Produto/produtos/{produto_id}/adicionais/{adicional_id}
"""

# ============================================================
# IMPORTS
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from typing import List, Optional
from pydantic import BaseModel

from dependencias import pegar_sessao, verificar_admin
from models import Base, Produto, Usuario


# ============================================================
# ROUTER
# ============================================================

adicionais_router = APIRouter(
    prefix="/Produto",
    tags=["Adicionais por Produto"]
)


# ============================================================
# MODEL — ProdutoAdicional
# ============================================================

class ProdutoAdicional(Base):
    __tablename__ = "produto_adicionais"

    id = Column(Integer, primary_key=True, autoincrement=True)
    produto_id = Column(Integer, ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False)

    nome = Column(String, nullable=False)
    descricao = Column(String, nullable=True)
    preco = Column(Float, nullable=False)
    disponivel = Column(Boolean, default=True)


# ============================================================
# SCHEMAS
# ============================================================

class AdicionalSchema(BaseModel):
    nome: str
    preco: float
    descricao: Optional[str] = None
    disponivel: Optional[bool] = True


class ResponseAdicionalSchema(BaseModel):
    id: int
    produto_id: int
    nome: str
    descricao: Optional[str]
    preco: float
    disponivel: bool

    class Config:
        from_attributes = True


# ============================================================
# HELPERS
# ============================================================

def _get_produto(produto_id: int, session: Session) -> Produto:
    produto = session.query(Produto).filter(Produto.id == produto_id).first()

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    return produto


# ============================================================
# ROTAS
# ============================================================

@adicionais_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista adicionais de um produto"
)
async def listar_adicionais(
    produto_id: int,
    apenas_disponiveis: bool = True,
    session: Session = Depends(pegar_sessao)
):
    _get_produto(produto_id, session)

    query = session.query(ProdutoAdicional).filter(
        ProdutoAdicional.produto_id == produto_id
    )

    if apenas_disponiveis:
        query = query.filter(ProdutoAdicional.disponivel == True)

    return query.all()


@adicionais_router.post(
    "/produtos/{produto_id}/adicionais",
    response_model=ResponseAdicionalSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona um adicional ao produto (admin)"
)
async def criar_adicional(
    produto_id: int,
    dados: AdicionalSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    _get_produto(produto_id, session)

    adicional = ProdutoAdicional(
        produto_id=produto_id,
        nome=dados.nome,
        descricao=dados.descricao,
        preco=dados.preco,
        disponivel=dados.disponivel if dados.disponivel is not None else True
    )

    session.add(adicional)
    session.commit()
    session.refresh(adicional)

    return adicional


@adicionais_router.delete(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    summary="Remove um adicional do produto (admin)"
)
async def deletar_adicional(
    produto_id: int,
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    _get_produto(produto_id, session)

    adicional = session.query(ProdutoAdicional).filter(
        ProdutoAdicional.id == adicional_id,
        ProdutoAdicional.produto_id == produto_id
    ).first()

    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    session.delete(adicional)
    session.commit()

    return {
        "mensagem": f"Adicional '{adicional.nome}' removido do produto"
    }
