from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from config import SECRET_KEY, ALGORITHM
from models import db, Usuario

# 🔐 HASH
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔥 CORREÇÃO PRINCIPAL AQUI
# Swagger (OAuth2) usa form-data → precisa apontar para /login-form
oauth2_schema = OAuth2PasswordBearer(tokenUrl="/auth/login-form")

SessionLocal = sessionmaker(bind=db, autocommit=False, autoflush=False)


# ─────────────────────────────────────────────
# SESSÃO
# ─────────────────────────────────────────────
def pegar_sessao():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ─────────────────────────────────────────────
# TOKEN
# ─────────────────────────────────────────────
def verificar_token(
    token: str = Depends(oauth2_schema),
    session: Session = Depends(pegar_sessao),
) -> Usuario:

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token não fornecido",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido",
            )

        user_id = int(user_id)

    except (JWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = session.query(Usuario).filter(Usuario.id == user_id).first()

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )

    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada",
        )

    return usuario


# ─────────────────────────────────────────────
# 🔥 ADMIN (BLINDADO)
# ─────────────────────────────────────────────
def verificar_admin(
    usuario: Usuario = Depends(verificar_token),
) -> Usuario:

    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não autenticado",
        )

    if not getattr(usuario, "admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )

    return usuario
