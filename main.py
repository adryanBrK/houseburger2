"""
main.py — VERSÃO CORRIGIDA v2.4.0
====================================

MUDANÇAS v2.4.0:
  - adicionais_router registrado: resolve o 404 em
    GET/POST/DELETE /Produto/produtos/{id}/adicionais
    (rotas chamadas pelo adm.html e index.html)
  - Tabela produto_adicionais criada automaticamente no startup
    via Base.metadata.create_all (ProdutoAdicional está em adicionais_routes.py)

MUDANÇAS v2.3.0 (mantidas):
  - cadastro_impressora_router registrado: resolve 404 em POST /Impressoras/
  - debug_impressora_router: remover após validar persistência
  - _inicializar() com try/except e log detalhado
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario

# ── Routers existentes
from auth_routes    import auth_router
from product_routes import product_router
from order_routes   import order_router
from sales_routes   import sales_router
from store_routes   import store_router
from bairro_routes  import bairro_router
from extras_routes  import extras_router

# ── Routers de impressão
from impressora_routes import (
    impressora_router,
    cadastro_impressora_router,
    debug_impressora_router,   # REMOVA após confirmar persistência
)

# ── Adicionais por produto  ← NOVO em v2.4.0
# Importar o módulo garante que ProdutoAdicional seja registrado
# no Base.metadata antes do create_all rodar no startup.
from adicionais_routes import adicionais_router
import adicionais_routes  # noqa: F401 — necessário para Base.metadata


# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════
# INICIALIZAÇÃO DO BANCO
# ══════════════════════════════════════════════════════════════
def _inicializar():
    db_url    = str(db.url)
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
            logger.info("Admin já existe — nenhuma ação necessária")
    except Exception as exc:
        session.rollback()
        logger.error("ERRO ao criar admin: %s", exc, exc_info=True)
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════
# LIFESPAN
# ══════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando API Hamburgueria v2.4.0")
    _inicializar()
    logger.info("API pronta para receber requisições")
    yield
    logger.info("API encerrada")


# ══════════════════════════════════════════════════════════════
# APLICAÇÃO FASTAPI
# ══════════════════════════════════════════════════════════════
app = FastAPI(
    title       = "API Hamburgueria",
    description = (
        "API completa para delivery de hamburgueria.\n\n"
        "**Pedidos públicos:** clientes criam pedidos sem login via `POST /Pedidos/pedidos`.\n\n"
        "**Painel admin:** autenticação via `POST /auth/login`."
    ),
    version  = "2.4.0",
    lifespan = lifespan,
)

# ── CORS
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

# ── Routers
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(extras_router)

# Adicionais por produto — NOVO v2.4.0
# Rotas: GET/POST/DELETE /Produto/produtos/{id}/adicionais
app.include_router(adicionais_router)

# Impressão
app.include_router(impressora_router)           # /Pedidos/impressao/...
app.include_router(cadastro_impressora_router)  # /Impressoras/ CRUD
app.include_router(debug_impressora_router)     # /debug/impressoras — REMOVA depois


# ══════════════════════════════════════════════════════════════
# ENDPOINTS DE STATUS
# ══════════════════════════════════════════════════════════════
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
