"""
auth_routes.py
===============
Correções:
  - bcrypt.verify() protegido por try/except — hash corrompido não causa 500
  - Usuário inativo retorna 403 explícito (não chega a gerar token)
  - Email normalizado (strip + lower) antes de buscar
  - criar-conta com rollback explícito
  - Sem lógica duplicada com dependencias.py
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt
from sqlalchemy.orm import Session

from config import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from dependencias import bcrypt_context, pegar_sessao, verificar_token
from models import Usuario
from schemas import LoginSchema, TokenSchema, UsuarioSchema

log = logging.getLogger("auth_routes")
auth_router = APIRouter(prefix="/auth", tags=["Autenticação"])


# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════

def _criar_token(id_usuario: int, duracao: timedelta | None = None) -> str:
    duracao = duracao or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expira  = datetime.now(timezone.utc) + duracao
    return jwt.encode({"sub": str(id_usuario), "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)


def _autenticar(email: str, senha: str, session: Session) -> Usuario | None:
    """
    Retorna o usuário autenticado ou None.
    NUNCA lança exceção — qualquer falha (hash corrompido, DB timeout) retorna None.
    Isso garante que o endpoint de login nunca retorna 500.
    """
    try:
        usuario = (
            session.query(Usuario)
            .filter(Usuario.email == email.strip().lower())
            .first()
        )
        if not usuario:
            return None
        if not bcrypt_context.verify(senha, usuario.senha):
            return None
        return usuario
    except Exception as exc:
        log.error("[auth] Erro ao autenticar '%s': %s", email, exc, exc_info=True)
        return None


# ══════════════════════════════════════════════════════════════════
# ROTAS
# ══════════════════════════════════════════════════════════════════

@auth_router.post(
    "/login",
    response_model=TokenSchema,
    summary="Login com e-mail e senha",
)
async def login(dados: LoginSchema, session: Session = Depends(pegar_sessao)):
    usuario = _autenticar(dados.email, dados.senha, session)

    if not usuario:
        # Mesmo erro para e-mail e senha inválidos (evita user enumeration)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada — entre em contato com o administrador",
        )

    log.info("[auth] Login OK | id=%s | email=%s", usuario.id, usuario.email)
    return TokenSchema(
        access_token  = _criar_token(usuario.id),
        refresh_token = _criar_token(usuario.id, duracao=timedelta(days=7)),
    )


@auth_router.post(
    "/login-form",
    response_model=TokenSchema,
    summary="Login via Swagger UI (OAuth2 form)",
)
async def login_form(
    dados:   OAuth2PasswordRequestForm = Depends(),
    session: Session                   = Depends(pegar_sessao),
):
    usuario = _autenticar(dados.username, dados.password, session)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not usuario.ativo:
        raise HTTPException(status_code=403, detail="Conta desativada")

    return TokenSchema(access_token=_criar_token(usuario.id))


@auth_router.get(
    "/refresh",
    response_model=TokenSchema,
    summary="Renova o access token",
)
async def refresh(usuario: Usuario = Depends(verificar_token)):
    return TokenSchema(access_token=_criar_token(usuario.id))


@auth_router.post(
    "/criar-conta",
    summary="Cria conta de operador (somente admin)",
)
async def criar_conta(
    dados:   UsuarioSchema,
    session: Session = Depends(pegar_sessao),
    admin:   Usuario = Depends(verificar_token),
):
    if not admin.admin:
        raise HTTPException(status_code=403, detail="Apenas administradores podem criar contas")

    if session.query(Usuario).filter(Usuario.email == dados.email.strip().lower()).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")

    novo = Usuario(
        nome  = dados.nome.strip(),
        email = dados.email.strip().lower(),
        senha = dados.senha,
        ativo = dados.ativo if dados.ativo is not None else True,
        admin = dados.admin if dados.admin is not None else False,
    )
    session.add(novo)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[auth] Erro ao criar conta: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Erro ao criar conta")

    log.info("[auth] Conta criada | email=%s | admin=%s", novo.email, novo.admin)
    return {"mensagem": f"Usuário '{novo.email}' criado com sucesso"}


@auth_router.get("/me", summary="Dados do usuário logado")
async def me(usuario: Usuario = Depends(verificar_token)):
    return {
        "id":    usuario.id,
        "nome":  usuario.nome,
        "email": usuario.email,
        "admin": usuario.admin,
        "ativo": usuario.ativo,
    }
