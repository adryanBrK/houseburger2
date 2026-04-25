from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from typing import List, Optional
from pydantic import BaseModel

from dependencias import pegar_sessao, verificar_admin
from models import Base, Produto, Usuario


adicionais_router = APIRouter(
    prefix="/Produto",
    tags=["Adicionais por Produto"]
)


# MODEL
class ProdutoAdicional(Base):
    __tablename__ = "produto_adicionais"

    id = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id", ondelete="CASCADE"))

    nome = Column(String, nullable=False)
    descricao = Column(String)
    preco = Column(Float, nullable=False)
    disponivel = Column(Boolean, default=True)


# SCHEMA
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


# HELPER
def _get_produto(produto_id: int, session: Session):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto


# GET
@adicionais_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[ResponseAdicionalSchema]
)
def listar_adicionais(produto_id: int, session: Session = Depends(pegar_sessao)):
    _get_produto(produto_id, session)

    return session.query(ProdutoAdicional).filter(
        ProdutoAdicional.produto_id == produto_id,
        ProdutoAdicional.disponivel == True
    ).all()


# POST
@adicionais_router.post(
    "/produtos/{produto_id}/adicionais",
    response_model=ResponseAdicionalSchema,
    status_code=201
)
def criar_adicional(
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
        disponivel=dados.disponivel
    )

    session.add(adicional)
    session.commit()
    session.refresh(adicional)

    return adicional


# DELETE
@adicionais_router.delete(
    "/produtos/{produto_id}/adicionais/{adicional_id}"
)
def deletar_adicional(
    produto_id: int,
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    adicional = session.query(ProdutoAdicional).filter(
        ProdutoAdicional.id == adicional_id,
        ProdutoAdicional.produto_id == produto_id
    ).first()

    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    session.delete(adicional)
    session.commit()

    return {"mensagem": "Adicional removido"}
