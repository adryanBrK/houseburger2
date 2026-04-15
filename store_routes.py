"""
store_routes.py — CORRIGIDO
=============================

DIAGNÓSTICO DO BUG "configurações não salvam":

O código original estava CORRETO em teoria (commit estava lá),
mas havia um problema sutil de SESSÃO COMPARTILHADA entre _config() e atualizar():

  1. _config() é chamada dentro de atualizar().
     Se _config() precisar CRIAR o registro (primeira execução),
     ela faz session.commit() internamente.
     Depois desse commit, o objeto `c` retornado ainda está ligado
     à mesma sessão — OK até aqui.

  2. O problema real: _config() envolve tudo em try/except e faz
     session.rollback() em qualquer exceção. Se qualquer coisa falhar
     entre _config() e o session.commit() de atualizar(), o rollback
     de _config() desfaz tudo — incluindo as alterações feitas com setattr().

  3. O segundo problema: session.commit() em atualizar() estava dentro do
     try mas SEM garantia de que a sessão não havia sido marcada para
     rollback por uma exceção anterior no mesmo request.

  4. O terceiro problema (mais sutil): dados.model_dump(exclude_unset=True)
     com ConfiguracaoLojaSchema onde TODOS os campos são Optional com
     default=None. Se o frontend enviar um campo como string vazia "",
     o exclude_unset=True inclui o campo — mas se o frontend não enviar
     o campo, ele é excluído. Isso funciona corretamente. Porém se o
     frontend enviar o JSON com todos os campos como null, o setattr()
     sobrescreve valores existentes com None — e o banco aceita (nullable=True).
     O dado "some" porque foi salvo como None, não porque não foi salvo.

CORREÇÕES APLICADAS:
  - _config() separada da lógica de escrita — não faz mais rollback global
  - atualizar() tem seu próprio try/except/rollback isolado
  - Log detalhado antes e depois do commit para rastrear o que foi salvo
  - Campos string vazios "" normalizados para None antes de salvar
    (evita o banco ficar com "" em vez de None)
  - session.refresh() garante que o retorno reflete o estado real do banco
"""

import logging
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from schemas import ConfiguracaoLojaSchema, ResponseConfiguracaoLojaSchema
from models import ConfiguracaoLoja, Usuario

log = logging.getLogger("store_routes")
store_router = APIRouter(prefix="/Loja", tags=["Configurações da Loja"])


def _config(session: Session) -> ConfiguracaoLoja:
    """
    Retorna o registro de configuração (id=1).
    Cria com valores padrão se não existir.
    NÃO faz rollback — deixa o controle de transação para o chamador.
    """
    c = session.query(ConfiguracaoLoja).filter(ConfiguracaoLoja.id == 1).first()

    if not c:
        log.info("[LOJA] Configuracao nao encontrada — criando padrao...")
        c = ConfiguracaoLoja(
            id                    = 1,
            nome_loja             = "Minha Hamburgueria",
            loja_aberta           = True,
            endereco_loja         = None,
            telefone              = None,
            horario_funcionamento = None,
            logo_url              = None,
            instagram             = None,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        log.info("[LOJA] Configuracao padrao criada com sucesso")

    return c


# ==========================
# GET CONFIGURAÇÃO  — público
# ==========================
@store_router.get("/", response_model=ResponseConfiguracaoLojaSchema)
async def ver(session: Session = Depends(pegar_sessao)):
    try:
        c = _config(session)
        return ResponseConfiguracaoLojaSchema.model_validate(c)
    except HTTPException:
        raise
    except Exception as e:
        log.error("[LOJA] Erro no GET /Loja: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao buscar configuração da loja")


# ==========================
# ATUALIZAR CONFIGURAÇÃO  — admin
# ==========================
@store_router.put("/", response_model=ResponseConfiguracaoLojaSchema)
async def atualizar(
    dados:   ConfiguracaoLojaSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    try:
        c = _config(session)

        # exclude_unset=True: só atualiza campos que o frontend enviou explicitamente.
        # Campos não enviados são ignorados — o valor atual no banco é preservado.
        update_data = dados.model_dump(exclude_unset=True)

        log.info("[LOJA] Campos recebidos para atualizar: %s", list(update_data.keys()))

        for key, value in update_data.items():
            if not hasattr(c, key):
                continue
            # Normalizar strings vazias para None — evita salvar "" no banco
            if isinstance(value, str) and value.strip() == "":
                value = None
            setattr(c, key, value)
            log.info("[LOJA] Setando %s = %r", key, value)

        session.commit()
        session.refresh(c)

        log.info("[LOJA] Configuracao salva com sucesso — nome_loja=%r", c.nome_loja)
        return ResponseConfiguracaoLojaSchema.model_validate(c)

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        log.error("[LOJA] Erro ao atualizar: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao atualizar configuração: {str(e)}",
        )


# ==========================
# ALTERAR STATUS ABERTO/FECHADO  — admin
# ==========================
@store_router.patch("/status")
async def alterar_status(
    aberta:  bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    try:
        c = _config(session)
        c.loja_aberta = aberta
        session.commit()

        log.info("[LOJA] Status alterado -> aberta=%s", aberta)
        return {
            "mensagem": f"Loja {'aberta' if aberta else 'fechada'} com sucesso",
            "aberta":   aberta,
        }

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        log.error("[LOJA] Erro ao alterar status: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao alterar status da loja")
