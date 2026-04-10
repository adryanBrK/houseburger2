from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import traceback

from dependencias import pegar_sessao, verificar_admin
from schemas import ConfiguracaoLojaSchema, ResponseConfiguracaoLojaSchema
from models import ConfiguracaoLoja, Usuario

store_router = APIRouter(prefix="/Loja", tags=["Configurações da Loja"])

def _config(session: Session) -> ConfiguracaoLoja:
    """
    Busca a configuração (ID 1) ou cria uma padrão caso não exista.
    """
    try:
        c = session.query(ConfiguracaoLoja).filter(ConfiguracaoLoja.id == 1).first()

        if not c:
            print("⚠️ Config não encontrada, criando...")
            c = ConfiguracaoLoja(
                id=1,
                nome_loja="Minha Hamburgueria",
                loja_aberta=True,
                endereco_loja="",
                telefone="",
                horario_funcionamento="",
                logo_url="",
                instagram="",
            )
            session.add(c)
            session.commit()
            session.refresh(c)

        return c

    except Exception as e:
        session.rollback() # Garante que a transação falha de forma limpa
        print("🔥 ERRO GRAVE EM _config:", e)
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar ou inicializar configuração da loja"
        )


@store_router.get("/", response_model=ResponseConfiguracaoLojaSchema)
async def ver(session: Session = Depends(pegar_sessao)):
    return _config(session)


@store_router.put("/", response_model=ResponseConfiguracaoLojaSchema)
async def atualizar(
    dados: ConfiguracaoLojaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    try:
        c = _config(session)

        # model_dump substitui o .dict() no Pydantic v2
        update_data = dados.model_dump(exclude_unset=True)

        for key, value in update_data.items():
            if hasattr(c, key):
                setattr(c, key, value)

        session.commit()
        session.refresh(c)
        return c

    except Exception as e:
        session.rollback()
        print("🔥 ERRO AO ATUALIZAR LOJA:", str(e))
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao atualizar loja: {str(e)}"
        )


@store_router.patch("/status")
async def status(
    aberta: bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    try:
        c = _config(session)
        c.loja_aberta = aberta
        session.commit()
        return {"mensagem": f"Loja {'aberta' if aberta else 'fechada'} com sucesso", "aberta": aberta}

    except Exception as e:
        session.rollback()
        print("ERRO AO ALTERAR STATUS:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Erro ao alterar status")
