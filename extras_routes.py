from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Integer, Float, Boolean
from typing import List, Optional
from pydantic import BaseModel

from dependencias import pegar_sessao, verificar_admin
from models import Base, db, Usuario

extras_router = APIRouter(prefix="/Extras", tags=["Extras"])


# ==========================
# MODEL - EXTRA
# ==========================
class Extra(Base):
    __tablename__ = "extras"
    
    id    = Column(Integer, primary_key=True, autoincrement=True)
    nome  = Column(String, nullable=False, unique=True)
    preco = Column(Float, nullable=False)
    ativo = Column(Boolean, default=True)


# ==========================
# SCHEMAS
# ==========================
class ExtraSchema(BaseModel):
    nome:  str
    preco: float
    ativo: Optional[bool] = True


class ResponseExtraSchema(BaseModel):
    id:    int
    nome:  str
    preco: float
    ativo: bool

    class Config:
        from_attributes = True


# ==========================
# ROTAS
# ==========================
@extras_router.get("/", response_model=List[ResponseExtraSchema], summary="Lista extras")
async def listar_extras(
    apenas_ativos: bool = True,
    session: Session = Depends(pegar_sessao)
):
    """Lista todos os adicionais"""
    q = session.query(Extra)
    if apenas_ativos:
        q = q.filter(Extra.ativo == True)
    return q.all()


@extras_router.post(
    "/",
    response_model=ResponseExtraSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria extra (admin)"
)
async def criar_extra(
    dados: ExtraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Cadastra um novo adicional"""
    existe = session.query(Extra).filter(Extra.nome == dados.nome).first()
    if existe:
        raise HTTPException(status_code=400, detail="Extra já existe")
    
    extra = Extra(
        nome=dados.nome,
        preco=dados.preco,
        ativo=dados.ativo if dados.ativo is not None else True
    )
    session.add(extra)
    session.commit()
    session.refresh(extra)
    return extra


@extras_router.put("/{extra_id}", response_model=ResponseExtraSchema, summary="Atualiza extra (admin)")
async def atualizar_extra(
    extra_id: int,
    dados: ExtraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Atualiza um adicional"""
    extra = session.query(Extra).filter(Extra.id == extra_id).first()
    if not extra:
        raise HTTPException(status_code=404, detail="Extra não encontrado")
    
    extra.nome = dados.nome
    extra.preco = dados.preco
    if dados.ativo is not None:
        extra.ativo = dados.ativo
    
    session.commit()
    session.refresh(extra)
    return extra


@extras_router.delete("/{extra_id}", summary="Remove extra (admin)")
async def deletar_extra(
    extra_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Remove um adicional"""
    extra = session.query(Extra).filter(Extra.id == extra_id).first()
    if not extra:
        raise HTTPException(status_code=404, detail="Extra não encontrado")
    
    session.delete(extra)
    session.commit()
    return {"mensagem": f"Extra '{extra.nome}' removido"}
