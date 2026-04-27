"""
main.py v3.0.0
===============
Correções:
  - CORS com allow_origins=["*"] para debug + lista de origens conhecidas
  - exception_handler global garante que erros 500 não quebrem headers CORS
  - Todos os routers registrados na ordem correta
  - Versão bumped para 3.0.0
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario

from auth_routes       import auth_router
from product_routes    import product_router
from order_routes      import order_router
from sales_routes      import sales_router
from store_routes      import store_router
from caixa_routes      import caixa_router
from bairro_routes     import bairro_router, delivery_router
from image_routes      import image_router
from impressora_routes import (
    impressora_router,
    cadastro_impressora_router,
    debug_impressora_router,
)

# extras_routes é opcional — importa só se existir
try:
    from extras_routes import extras_router
    _HAS_EXTRAS = True
except ImportError:
    _HAS_EXTRAS = False

logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt= "%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════

def _inicializar():
    db_url = str(db.url)
    logger.info("Banco: %s", "PostgreSQL" if "postgresql" in db_url else "SQLite (dev)")

    try:
        Base.metadata.create_all(bind=db)
        logger.info("Tabelas verificadas/criadas")
    except Exception as exc:
        logger.error("ERRO ao criar tabelas: %s", exc, exc_info=True)
        raise

    session = sessionmaker(bind=db)()
    try:
        admin_email = "admin@hamburgueria.com"
        if not session.query(Usuario).filter(Usuario.email == admin_email).first():
            session.add(Usuario(
                nome  = "Administrador",
                email = admin_email,
                senha = "admin123",
                admin = True,
                ativo = True,
            ))
            session.commit()
            logger.info("Admin criado → %s / admin123", admin_email)
        else:
            logger.info("Admin já existe")
    except Exception as exc:
        session.rollback()
        logger.error("ERRO ao criar admin: %s", exc, exc_info=True)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando API Hamburgueria v3.0.0")
    _inicializar()
    logger.info("API pronta")
    yield
    logger.info("API encerrada")


# ══════════════════════════════════════════════════════════════════
# APP
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title    = "API Hamburgueria",
    version  = "3.0.0",
    lifespan = lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────
# allow_origins=["*"] em modo debug garante que o frontend nunca recebe
# bloqueio de CORS independente de onde está rodando.
# Em produção, substitua ["*"] pela lista de origens reais.
#
# IMPORTANTE: CORSMiddleware deve ser adicionado ANTES dos routers
# para garantir que os headers sejam injetados mesmo em respostas de erro.
# ─────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],           # debug — restrinja em produção
    allow_credentials = False,           # False é obrigatório quando allow_origins=["*"]
    allow_methods     = ["*"],
    allow_headers     = ["*"],
    expose_headers    = ["*"],
)


# ── HANDLER GLOBAL DE ERROS ───────────────────────────────────────
# Garante que qualquer exceção não tratada retorna JSON 500
# em vez de um traceback em texto puro que quebraria o parsing do frontend.
# ─────────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        "Erro não tratado | %s %s | %s: %s",
        request.method, request.url.path,
        type(exc).__name__, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code = 500,
        content     = {"detail": "Erro interno do servidor — tente novamente"},
    )


# ── ROUTERS ───────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(delivery_router)
app.include_router(caixa_router)
app.include_router(image_router)
app.include_router(impressora_router)
app.include_router(cadastro_impressora_router)
app.include_router(debug_impressora_router)

if _HAS_EXTRAS:
    from extras_routes import extras_router
    app.include_router(extras_router)


# ── STATUS ────────────────────────────────────────────────────────
@app.get("/", tags=["Status"])
def raiz():
    db_url = str(db.url)
    return {
        "status": "online",
        "versao": "3.0.0",
        "docs":   "/docs",
        "banco":  "PostgreSQL" if "postgresql" in db_url else "SQLite",
    }


@app.get("/health", tags=["Status"])
def health():
    return {"status": "healthy"}


handler = app
