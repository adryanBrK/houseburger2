from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import sessionmaker, Session
from passlib.context import CryptContext
from jose import jwt, JWTError

from config import SECRET_KEY, ALGORITHM
from models import db, Usuario

bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_schema  = OAuth2PasswordBearer(tokenUrl="/auth/login-form")
SessionLocal   = sessionmaker(bind=db, autocommit=False, autoflush=False)


def pegar_sessao():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def verificar_token(
    token:   str     = Depends(oauth2_schema),
    session: Session = Depends(pegar_sessao),
) -> Usuario:
    try:
        payload    = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_usuario = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    usuario = session.query(Usuario).filter(Usuario.id == id_usuario).first()
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not usuario.ativo:
        raise HTTPException(status_code=403, detail="Conta desativada")
    return usuario


def verificar_admin(usuario: Usuario = Depends(verificar_token)) -> Usuario:
    if not usuario.admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return usuario