"""
main.py
========
Adição: caixa_router registrado em /Caixa
Nada mais foi alterado.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario

from auth_routes    import auth_router
from product_routes import product_router
from order_routes   import order_router
from sales_routes   import sales_router
from store_routes   import store_router
from bairro_routes  import bairro_router
from extras_routes  import extras_router
from caixa_routes   import caixa_router          # ← NOVO

from impressora_routes import (
    impressora_router,
    cadastro_impressora_router,
    debug_impressora_router,   # remova após validar persistência
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


def _inicializar():
    db_url     = str(db.url)
    tipo_banco = "PostgreSQL" if "postgresql" in db_url else "SQLite (apenas dev)"
    logger.info("Banco de dados: %s", tipo_banco)

    try:
        Base.metadata.create_all(bind=db)
        logger.info("Tabelas verificadas/criadas com sucesso")
    except Exception as exc:
        logger.error("ERRO ao criar tabelas: %s", exc, exc_info=True)
        raise

    session = sessionmaker(bind=db)()
    try:
        admin_email = "admin@hamburgueria.com"
        existe = session.query(Usuario).filter(Usuario.email == admin_email).first()
        if not existe:
            session.add(Usuario(
                nome  = "Administrador",
                email = admin_email,
                senha = "admin123",
                admin = True,
                ativo = True,
            ))
            session.commit()
            logger.info("Admin criado  ->  %s  /  admin123", admin_email)
        else:
            logger.info("Admin ja existe — nenhuma acao necessaria")
    except Exception as exc:
        session.rollback()
        logger.error("ERRO ao criar admin: %s", exc, exc_info=True)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando API Hamburgueria v2.4.0")
    _inicializar()
    logger.info("API pronta para receber requisicoes")
    yield
    logger.info("API encerrada")


app = FastAPI(
    title       = "API Hamburgueria",
    description = (
        "API completa para delivery de hamburgueria.\n\n"
        "**Pedidos publicos:** clientes criam pedidos sem login via `POST /Pedidos/pedidos`.\n\n"
        "**Painel admin:** autenticacao via `POST /auth/login`."
    ),
    version  = "2.4.0",
    lifespan = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://house-burgers.vercel.app",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(extras_router)
app.include_router(caixa_router)                 # ← NOVO  /Caixa/...
app.include_router(impressora_router)
app.include_router(cadastro_impressora_router)
app.include_router(debug_impressora_router)      # remova após validar


@app.get("/", tags=["Status"])
def raiz():
    db_url = str(db.url)
    return {
        "status":  "online",
        "message": "API Hamburgueria",
        "versao":  "2.4.0",
        "docs":    "/docs",
        "banco":   "PostgreSQL" if "postgresql" in db_url else "SQLite",
    }


@app.get("/health", tags=["Status"])
def health_check():
    return {"status": "healthy"}


handler = app
