import json
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Base, Usuario, db, ConfigExtra


# =========================================================
# CONFIG
# =========================================================

log = logging.getLogger("extras_routes")

extras_router = APIRouter(
    prefix="/Extras",
    tags=["Extras"]
)


# =========================================================
# MODELS
# =========================================================

class Extra(Base):
    __tablename__ = "extras"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=False, unique=True)
    preco = Column(Float, nullable=False)
    ativo = Column(Boolean, default=True)


Base.metadata.create_all(bind=db)


# =========================================================
# SCHEMAS — EXTRAS
# =========================================================

class ExtraSchema(BaseModel):
    nome: str
    preco: float
    ativo: Optional[bool] = True

    @field_validator("preco")
    @classmethod
    def validar_preco(cls, v):
        if v < 0:
            raise ValueError("Preço não pode ser negativo")
        return round(v, 2)


class ResponseExtraSchema(BaseModel):
    id: int
    nome: str
    preco: float
    ativo: bool

    class Config:
        from_attributes = True


# =========================================================
# SCHEMAS — DUPLO
# =========================================================

class DuploSchema(BaseModel):
    simples: float
    pro: float
    promax: float

    @field_validator("simples", "pro", "promax")
    @classmethod
    def nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Preço não pode ser negativo")
        return round(v, 2)


# =========================================================
# SCHEMAS — CONFIG GENÉRICA
# =========================================================

class ConfigExtraSchema(BaseModel):
    chave: str
    valor: Any


class ResponseConfigExtraSchema(BaseModel):
    chave: str
    valor: Any

    class Config:
        from_attributes = True


# =========================================================
# DEFAULTS
# =========================================================

_DUPLO_DEFAULT = {
    "simples": 6.0,
    "pro": 8.0,
    "promax": 10.0,
}


# =========================================================
# HELPERS
# =========================================================

def _get_config(chave: str, session: Session):
    return (
        session.query(ConfigExtra)
        .filter(ConfigExtra.chave == chave)
        .first()
    )


def _upsert_config(chave: str, valor: Any, session: Session):
    cfg = _get_config(chave, session)

    valor_json = json.dumps(valor, ensure_ascii=False)

    if cfg:
        cfg.valor = valor_json
    else:
        cfg = ConfigExtra(
            chave=chave,
            valor=valor_json
        )
        session.add(cfg)

    return cfg


# =========================================================
# ROTAS — DUPLO
# IMPORTANTE:
# DEVEM VIR ANTES DAS ROTAS DINÂMICAS
# =========================================================

@extras_router.get(
    "/duplo",
    response_model=DuploSchema,
    summary="Retorna preços do duplo"
)
async def get_duplo(
    session: Session = Depends(pegar_sessao)
):
    cfg = _get_config("duplo", session)

    if not cfg:
        return _DUPLO_DEFAULT

    try:
        dados = json.loads(cfg.valor)
        return DuploSchema(**dados)

    except Exception as exc:
        log.error(
            "[extras] erro ao ler config duplo: %s",
            exc
        )
        return _DUPLO_DEFAULT


@extras_router.put(
    "/duplo",
    response_model=DuploSchema,
    summary="Atualiza preços do duplo (admin)"
)
async def put_duplo(
    dados: DuploSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    _upsert_config(
        "duplo",
        dados.model_dump(),
        session
    )

    try:
        session.commit()

    except Exception as exc:
        session.rollback()

        log.error(
            "[extras] erro ao salvar duplo: %s",
            exc,
            exc_info=True
        )

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar configuração: {exc}"
        )

    return dados


# =========================================================
# ROTAS — EXTRAS GLOBAIS
# =========================================================

@extras_router.get(
    "/",
    response_model=List[ResponseExtraSchema],
    summary="Lista extras globais"
)
async def listar_extras(
    apenas_ativos: bool = True,
    session: Session = Depends(pegar_sessao)
):
    q = session.query(Extra)

    if apenas_ativos:
        q = q.filter(Extra.ativo == True)

    return q.all()


@extras_router.post(
    "/",
    response_model=ResponseExtraSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria extra global (admin)"
)
async def criar_extra(
    dados: ExtraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    existe = (
        session.query(Extra)
        .filter(Extra.nome == dados.nome)
        .first()
    )

    if existe:
        raise HTTPException(
            status_code=400,
            detail="Extra já existe"
        )

    extra = Extra(
        nome=dados.nome,
        preco=dados.preco,
        ativo=dados.ativo if dados.ativo is not None else True
    )

    session.add(extra)

    try:
        session.commit()
        session.refresh(extra)

    except Exception as exc:
        session.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar extra: {exc}"
        )

    return extra


@extras_router.put(
    "/extra/{extra_id}",
    response_model=ResponseExtraSchema,
    summary="Atualiza extra global (admin)"
)
async def atualizar_extra(
    extra_id: int,
    dados: ExtraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    extra = (
        session.query(Extra)
        .filter(Extra.id == extra_id)
        .first()
    )

    if not extra:
        raise HTTPException(
            status_code=404,
            detail="Extra não encontrado"
        )

    extra.nome = dados.nome
    extra.preco = dados.preco

    if dados.ativo is not None:
        extra.ativo = dados.ativo

    try:
        session.commit()
        session.refresh(extra)

    except Exception as exc:
        session.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao atualizar extra: {exc}"
        )

    return extra


@extras_router.delete(
    "/extra/{extra_id}",
    summary="Remove extra global (admin)"
)
async def deletar_extra(
    extra_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    extra = (
        session.query(Extra)
        .filter(Extra.id == extra_id)
        .first()
    )

    if not extra:
        raise HTTPException(
            status_code=404,
            detail="Extra não encontrado"
        )

    session.delete(extra)

    try:
        session.commit()

    except Exception as exc:
        session.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao remover extra: {exc}"
        )

    return {
        "mensagem": f"Extra '{extra.nome}' removido"
    }


# =========================================================
# ROTAS — CONFIGS GENÉRICAS
# =========================================================

@extras_router.get(
    "/config",
    response_model=List[ResponseConfigExtraSchema],
    summary="Lista configs extras (admin)"
)
async def listar_configs(
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    configs = (
        session.query(ConfigExtra)
        .order_by(ConfigExtra.chave)
        .all()
    )

    return [
        {
            "chave": c.chave,
            "valor": json.loads(c.valor)
        }
        for c in configs
    ]


@extras_router.get(
    "/config/{chave}",
    response_model=ResponseConfigExtraSchema,
    summary="Busca config por chave (admin)"
)
async def get_config(
    chave: str,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    cfg = _get_config(chave, session)

    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"Configuração '{chave}' não encontrada"
        )

    return {
        "chave": cfg.chave,
        "valor": json.loads(cfg.valor)
    }


@extras_router.put(
    "/config/{chave}",
    response_model=ResponseConfigExtraSchema,
    summary="Cria/Atualiza config genérica (admin)"
)
async def upsert_extra_config(
    chave: str,
    dados: ConfigExtraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    cfg = _upsert_config(
        chave,
        dados.valor,
        session
    )

    try:
        session.commit()
        session.refresh(cfg)

    except Exception as exc:
        session.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao salvar configuração: {exc}"
        )

    return {
        "chave": cfg.chave,
        "valor": json.loads(cfg.valor)
    }


@extras_router.delete(
    "/config/{chave}",
    summary="Remove config (admin)"
)
async def deletar_config(
    chave: str,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    cfg = _get_config(chave, session)

    if not cfg:
        raise HTTPException(
            status_code=404,
            detail=f"Configuração '{chave}' não encontrada"
        )

    session.delete(cfg)

    try:
        session.commit()

    except Exception as exc:
        session.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"Erro ao remover configuração: {exc}"
        )

    return {
        "mensagem": f"Configuração '{chave}' removida com sucesso"
    }
