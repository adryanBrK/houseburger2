"""
adicional_routes.py
====================
Cria as rotas que estavam faltando:

  GET    /Produto/produtos/{produto_id}/adicionais
  POST   /Produto/produtos/{produto_id}/adicionais
  DELETE /Produto/produtos/{produto_id}/adicionais/{adicional_id}

No main.py, adicione:

    from adicional_routes import adicional_router
    app.include_router(adicional_router)
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Session, relationship

from dependencias import pegar_sessao, verificar_admin
from models import Base, Produto, Usuario

log = logging.getLogger("adicional_routes")


# ══════════════════════════════════════════════════════════════════
# MODEL
# ══════════════════════════════════════════════════════════════════

class Adicional(Base):
    __tablename__ = "adicionais"

    id         = Column(Integer, primary_key=True, index=True)
    produto_id = Column(Integer, ForeignKey("produtos.id", ondelete="CASCADE"), nullable=False, index=True)
    nome       = Column(String(120), nullable=False)
    preco      = Column(Float, nullable=False, default=0.0)
    descricao  = Column(String(255), nullable=True)
    disponivel = Column(Boolean, nullable=False, default=True)
    criado_em  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    produto = relationship("Produto", back_populates="adicionais")


# Injeta o relacionamento inverso em Produto sem editar models.py
if not hasattr(Produto, "adicionais"):
    Produto.adicionais = relationship(
        "Adicional",
        back_populates="produto",
        cascade="all, delete-orphan",
        lazy="select",
    )


# ══════════════════════════════════════════════════════════════════
# SCHEMAS
# ══════════════════════════════════════════════════════════════════

class AdicionalCreateSchema(BaseModel):
    nome:       str
    preco:      float = 0.0
    descricao:  Optional[str] = None
    disponivel: bool = True

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nome e obrigatorio")
        return v

    @field_validator("preco")
    @classmethod
    def preco_nao_negativo(cls, v: float) -> float:
        if v < 0:
            raise ValueError("preco nao pode ser negativo")
        return v


class AdicionalResponseSchema(BaseModel):
    id:         int
    produto_id: int
    nome:       str
    preco:      float
    descricao:  Optional[str]
    disponivel: bool
    criado_em:  datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════

adicional_router = APIRouter(prefix="/Produto", tags=["Adicionais"])


def _produto_ou_404(session: Session, produto_id: int) -> Produto:
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail=f"Produto id={produto_id} nao encontrado.")
    return produto


@adicional_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[AdicionalResponseSchema],
    summary="Lista adicionais de um produto (admin)",
)
def listar_adicionais(
    produto_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    _produto_ou_404(session, produto_id)
    return (
        session.query(Adicional)
        .filter(Adicional.produto_id == produto_id)
        .order_by(Adicional.id)
        .all()
    )


@adicional_router.post(
    "/produtos/{produto_id}/adicionais",
    response_model=AdicionalResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria adicional para um produto (admin)",
)
def criar_adicional(
    produto_id: int,
    dados:   AdicionalCreateSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    _produto_ou_404(session, produto_id)
    adicional = Adicional(
        produto_id = produto_id,
        nome       = dados.nome,
        preco      = dados.preco,
        descricao  = dados.descricao,
        disponivel = dados.disponivel,
    )
    session.add(adicional)
    try:
        session.commit()
        session.refresh(adicional)
    except Exception as exc:
        session.rollback()
        log.error("[ADICIONAL] Erro ao criar: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar adicional: {exc}")
    log.info("[ADICIONAL] Criado id=%s produto_id=%s nome=%s", adicional.id, produto_id, adicional.nome)
    return adicional


@adicional_router.delete(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove adicional de um produto (admin)",
)
def excluir_adicional(
    produto_id:   int,
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    _produto_ou_404(session, produto_id)
    adicional = (
        session.query(Adicional)
        .filter(Adicional.id == adicional_id, Adicional.produto_id == produto_id)
        .first()
    )
    if not adicional:
        raise HTTPException(
            status_code=404,
            detail=f"Adicional id={adicional_id} nao encontrado no produto id={produto_id}.",
        )
    session.delete(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[ADICIONAL] Erro ao excluir: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao excluir adicional: {exc}")
    log.info("[ADICIONAL] Excluido id=%s produto_id=%s", adicional_id, produto_id)
