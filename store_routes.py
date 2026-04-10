from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import traceback

from dependencias import pegar_sessao, verificar_admin
from schemas import ConfiguracaoLojaSchema, ResponseConfiguracaoLojaSchema
from models import ConfiguracaoLoja, Usuario

store_router = APIRouter(prefix="/Loja", tags=["Configurações da Loja"])


def _config(session: Session) -> ConfiguracaoLoja:
    try:
        c = session.query(ConfiguracaoLoja).filter(ConfiguracaoLoja.id == 1).first()

        if not c:
            print("⚠️ Config não encontrada, criando...")

            c = ConfiguracaoLoja(
                id=1,
                nome_loja="Minha Hamburgueria",
                loja_aberta=True,
            )

            session.add(c)

            try:
                session.commit()
            except Exception as e:
                session.rollback()
                print("🔥 ERRO AO COMMITAR CONFIG:", e)
                raise

            session.refresh(c)

        return c

    except Exception as e:
        print("🔥 ERRO GRAVE EM _config:", e)
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail="Erro ao carregar configuração da loja"
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

        # Atualização segura
        update_data = dados.dict(exclude_unset=True)

        for key, value in update_data.items():
            if hasattr(c, key):
                setattr(c, key, value)

        session.commit()
        session.refresh(c)

        return c

    except Exception as e:
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

        return {"mensagem": f"Loja {'aberta' if aberta else 'fechada'} com sucesso"}

    except Exception as e:
        print("ERRO AO ALTERAR STATUS:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Erro ao alterar status")
