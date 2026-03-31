from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from schemas import ConfiguracaoLojaSchema, ResponseConfiguracaoLojaSchema
from models import ConfiguracaoLoja, Usuario

store_router = APIRouter(prefix="/Loja", tags=["Configurações da Loja"])


def _config(session: Session) -> ConfiguracaoLoja:
    c = session.query(ConfiguracaoLoja).filter(ConfiguracaoLoja.id == 1).first()
    if not c:
        c = ConfiguracaoLoja(id=1)
        session.add(c)
        session.commit()
        session.refresh(c)
    return c


@store_router.get("/", response_model=ResponseConfiguracaoLojaSchema, summary="Configurações da loja")
async def ver(session: Session = Depends(pegar_sessao)):
    return _config(session)


@store_router.put("/", response_model=ResponseConfiguracaoLojaSchema, summary="Atualiza configurações (somente admin)")
async def atualizar(
    dados: ConfiguracaoLojaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    c = _config(session)
    if dados.nome_loja             is not None: c.nome_loja             = dados.nome_loja
    if dados.taxa_entrega          is not None: c.taxa_entrega          = dados.taxa_entrega
    if dados.loja_aberta           is not None: c.loja_aberta           = dados.loja_aberta
    if dados.endereco_loja         is not None: c.endereco_loja         = dados.endereco_loja
    if dados.telefone              is not None: c.telefone              = dados.telefone
    if dados.horario_funcionamento is not None: c.horario_funcionamento = dados.horario_funcionamento
    session.commit()
    session.refresh(c)
    return c


@store_router.patch("/status", summary="Abre ou fecha a loja (somente admin)")
async def status(aberta: bool, session: Session = Depends(pegar_sessao), _: Usuario = Depends(verificar_admin)):
    c = _config(session)
    c.loja_aberta = aberta
    session.commit()
    return {"mensagem": f"Loja {'aberta' if aberta else 'fechada'} com sucesso"}