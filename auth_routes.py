from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt
from datetime import datetime, timedelta, timezone

from config import ALGORITHM, SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES
from dependencias import pegar_sessao, verificar_token, bcrypt_context
from schemas import UsuarioSchema, LoginSchema, TokenSchema
from models import Usuario

auth_router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _criar_token(id_usuario: int, duracao: timedelta = None) -> str:
    if duracao is None:
        duracao = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    expira = datetime.now(timezone.utc) + duracao

    return jwt.encode(
        {"sub": str(id_usuario), "exp": expira},
        SECRET_KEY,
        algorithm=ALGORITHM
    )


def _autenticar(email: str, senha: str, session: Session):
    usuario = session.query(Usuario).filter(Usuario.email == email).first()

    if not usuario or not bcrypt_context.verify(senha, usuario.senha):
        return None

    return usuario


# 🔹 LOGIN JSON (frontend)
@auth_router.post("/login", response_model=TokenSchema)
async def login(dados: LoginSchema, session: Session = Depends(pegar_sessao)):
    usuario = _autenticar(dados.email, dados.senha, session)

    if not usuario:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")

    return TokenSchema(
        access_token=_criar_token(usuario.id),
        refresh_token=_criar_token(usuario.id, timedelta(days=7)),
    )


# 🔹 LOGIN SWAGGER (OAuth2)
@auth_router.post("/login-form", response_model=TokenSchema)
async def login_form(
    dados: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(pegar_sessao)
):
    usuario = _autenticar(dados.username, dados.password, session)

    if not usuario:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")

    return TokenSchema(
        access_token=_criar_token(usuario.id),
        token_type="bearer"
    )


@auth_router.get("/refresh", response_model=TokenSchema)
async def refresh(usuario: Usuario = Depends(verificar_token)):
    return TokenSchema(
        access_token=_criar_token(usuario.id)
    )


@auth_router.get("/me")
async def me(usuario: Usuario = Depends(verificar_token)):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "admin": usuario.admin,
        "ativo": usuario.ativo
    }
