"""
adicionais_routes.py
====================
Rotas de adicionais POR PRODUTO.

Prefixo: /Produto  (registrado no mesmo router de produtos)

Rotas geradas:
  GET    /Produto/produtos/{produto_id}/adicionais
  POST   /Produto/produtos/{produto_id}/adicionais
  DELETE /Produto/produtos/{produto_id}/adicionais/{adicional_id}

O front-end (adm.html e index.html) chama exatamente essas URLs.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey
from typing import List, Optional
from pydantic import BaseModel

from dependencias import pegar_sessao, verificar_admin
from models import Base, Produto, Usuario

adicionais_router = APIRouter(prefix="/Produto", tags=["Adicionais por Produto"])


# ══════════════════════════════════════════════════════════════
# MODEL — tabela produto_adicionais
# ══════════════════════════════════════════════════════════════

class ProdutoAdicional(Base):
    """Adicional vinculado a um produto específico."""
    __tablename__ = "produto_adicionais"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    produto_id  = Column(Integer, ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False)
    nome        = Column(String, nullable=False)
    descricao   = Column(String, nullable=True)
    preco       = Column(Float, nullable=False)
    disponivel  = Column(Boolean, default=True)


# ══════════════════════════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════════════════════════

class AdicionalSchema(BaseModel):
    nome:       str
    preco:      float
    descricao:  Optional[str] = None
    disponivel: Optional[bool] = True


class ResponseAdicionalSchema(BaseModel):
    id:         int
    produto_id: int
    nome:       str
    descricao:  Optional[str]
    preco:      float
    disponivel: bool

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════════

def _get_produto(produto_id: int, session: Session) -> Produto:
    p = session.query(Produto).filter(Produto.id == produto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return p


# ══════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════

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
    """
    Retorna todos os adicionais vinculados ao produto.
    Usado pelo index.html (cardápio público) e adm.html.
    """
    _get_produto(produto_id, session)  # garante 404 se produto não existe

    q = session.query(ProdutoAdicional).filter(
        ProdutoAdicional.produto_id == produto_id
    )
    if apenas_disponiveis:
        q = q.filter(ProdutoAdicional.disponivel == True)
    return q.all()


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
    """
    Cria um adicional vinculado ao produto.
    Chamado pelo adm.html ao salvar um novo adicional.
    """
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
    """
    Remove o adicional de um produto específico.
    Chamado pelo adm.html ao clicar em Excluir.
    """
    _get_produto(produto_id, session)

    adicional = session.query(ProdutoAdicional).filter(
        ProdutoAdicional.id == adicional_id,
        ProdutoAdicional.produto_id == produto_id
    ).first()

    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    session.delete(adicional)
    session.commit()
    return {"mensagem": f"Adicional '{adicional.nome}' removido do produto"}
