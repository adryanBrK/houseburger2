from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from dependencias import pegar_sessao, verificar_admin
from schemas import BairroSchema, ResponseBairroSchema
from models import Bairro, Usuario

bairro_router = APIRouter(prefix="/Bairros", tags=["Bairros"])


@bairro_router.get("/", response_model=List[ResponseBairroSchema], summary="Lista bairros")
async def listar_bairros(
    apenas_ativos: bool = True,
    session: Session = Depends(pegar_sessao)
):
    """Lista todos os bairros (opcionalmente apenas ativos)"""
    q = session.query(Bairro)
    if apenas_ativos:
        q = q.filter(Bairro.ativo == True)
    return q.order_by(Bairro.nome).all()


@bairro_router.post(
    "/",
    response_model=ResponseBairroSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra bairro (admin)"
)
async def criar_bairro(
    dados: BairroSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Cadastra um novo bairro com valor de entrega"""
    # Verificar se já existe
    existe = session.query(Bairro).filter(Bairro.nome == dados.nome).first()
    if existe:
        raise HTTPException(status_code=400, detail="Bairro já cadastrado")
    
    bairro = Bairro(
        nome=dados.nome,
        valor_entrega=dados.valor_entrega,
        ativo=dados.ativo if dados.ativo is not None else True
    )
    session.add(bairro)
    session.commit()
    session.refresh(bairro)
    return bairro


@bairro_router.put("/{bairro_id}", response_model=ResponseBairroSchema, summary="Atualiza bairro (admin)")
async def atualizar_bairro(
    bairro_id: int,
    dados: BairroSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Atualiza dados de um bairro"""
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")
    
    bairro.nome = dados.nome
    bairro.valor_entrega = dados.valor_entrega
    if dados.ativo is not None:
        bairro.ativo = dados.ativo
    
    session.commit()
    session.refresh(bairro)
    return bairro


@bairro_router.delete("/{bairro_id}", summary="Remove bairro (admin)")
async def deletar_bairro(
    bairro_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Remove um bairro (se não tiver pedidos vinculados)"""
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")
    
    session.delete(bairro)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail="Não é possível deletar bairro com pedidos vinculados"
        )
    
    return {"mensagem": f"Bairro '{bairro.nome}' removido com sucesso"}


@bairro_router.patch("/{bairro_id}/ativar", summary="Ativa/desativa bairro (admin)")
async def toggle_bairro(
    bairro_id: int,
    ativo: bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Ativa ou desativa um bairro"""
    bairro = session.query(Bairro).filter(Bairro.id == bairro_id).first()
    if not bairro:
        raise HTTPException(status_code=404, detail="Bairro não encontrado")
    
    bairro.ativo = ativo
    session.commit()
    
    return {"mensagem": f"Bairro '{bairro.nome}' {'ativado' if ativo else 'desativado'}"}
