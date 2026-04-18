"""
main.py — VERSÃO CORRIGIDA v2.5.0
====================================

CORREÇÕES v2.5.0:
  - Exception handlers globais adicionados → resolve CORS falso em erros 401/422/500
  - Mantido suporte completo a adicionais, impressoras e banco automático
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario

# ── Routers
from auth_routes    import auth_router
from product_routes import product_router
from order_routes   import order_router
from sales_routes   import sales_router
from store_routes   import store_router
from bairro_routes  import bairro_router
from extras_routes  import extras_router

from impressora_routes import (
    impressora_router,
    cadastro_impressora_router,
    debug_impressora_router,
)

from adicionais_routes import adicionais_router
import adicionais_routes  # noqa


# ══════════════════════════════════════════════════════════════
# LOG
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════
# BANCO
# ══════════════════════════════════════════════════════════════
def _inicializar():
    try:
        Base.metadata.create_all(bind=db)
        logger.info("Tabelas OK")
    except Exception as e:
        logger.error("Erro ao criar tabelas: %s", e, exc_info=True)
        raise

    session = sessionmaker(bind=db)()
    try:
        admin_email = "admin@hamburgueria.com"
        existe = session.query(Usuario).filter(Usuario.email == admin_email).first()

        if not existe:
            session.add(Usuario(
                nome="Administrador",
                email=admin_email,
                senha="admin123",
                admin=True,
                ativo=True,
            ))
            session.commit()
            logger.info("Admin criado")
    except Exception as e:
        session.rollback()
        logger.error("Erro ao criar admin: %s", e, exc_info=True)
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════
# LIFESPAN
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando API")
    _inicializar()
    yield
    logger.info("Encerrando API")


# ══════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════
app = FastAPI(
    title="API Hamburgueria",
    version="2.5.0",
    lifespan=lifespan,
)

# ── CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://house-burgers.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ══════════════════════════════════════════════════════════════
# 🔥 EXCEPTION HANDLERS (CORREÇÃO PRINCIPAL)
# ══════════════════════════════════════════════════════════════

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://house-burgers.vercel.app",
    "Access-Control-Allow-Credentials": "true",
}

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=CORS_HEADERS,
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
        headers=CORS_HEADERS,
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error("Erro interno: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno no servidor"},
        headers=CORS_HEADERS,
    )


# ══════════════════════════════════════════════════════════════
# ROUTERS
# ══════════════════════════════════════════════════════════════
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(extras_router)

app.include_router(adicionais_router)

app.include_router(impressora_router)
app.include_router(cadastro_impressora_router)
app.include_router(debug_impressora_router)


# ══════════════════════════════════════════════════════════════
# STATUS
# ══════════════════════════════════════════════════════════════
@app.get("/")
def raiz():
    return {
        "status": "online",
        "versao": "2.5.0",
    }

@app.get("/health")
def health():
    return {"status": "ok"}
