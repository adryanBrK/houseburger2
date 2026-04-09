import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario

# ── Routers
from auth_routes       import auth_router
from product_routes    import product_router
from order_routes      import order_router
from sales_routes      import sales_router
from store_routes      import store_router
from bairro_routes     import bairro_router
from impressora_routes import impressora_router
from extras_routes     import extras_router

# ══════════════════════════════════════════════════════════════════
# LOGGING GLOBAL
# ══════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ══════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO DO BANCO
# ══════════════════════════════════════════════════════════════════
def _inicializar():
    """
    1. Cria todas as tabelas (se não existirem).
    2. Insere o usuário admin padrão na primeira execução.
    3. Loga o tipo de banco em uso.
    """
    db_url = str(db.url)
    tipo_banco = "PostgreSQL" if "postgresql" in db_url else "SQLite (⚠️ apenas dev)"
    logger.info("Banco de dados: %s", tipo_banco)

    Base.metadata.create_all(bind=db)
    logger.info("Tabelas verificadas/criadas com sucesso")

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
            logger.info("Admin criado  →  %s  /  admin123", admin_email)
        else:
            logger.info("Admin já existe — nenhuma ação necessária")
    finally:
        session.close()


# ══════════════════════════════════════════════════════════════════
# LIFESPAN
# ══════════════════════════════════════════════════════════════════
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Iniciando API Hamburgueria v2.3.0")
    _inicializar()
    logger.info("✅ API pronta para receber requisições")
    yield
    logger.info("🛑 API encerrada")


# ══════════════════════════════════════════════════════════════════
# APLICAÇÃO FASTAPI
# ══════════════════════════════════════════════════════════════════
app = FastAPI(
    title       = "🍔 API Hamburgueria",
    description = (
        "API completa para delivery de hamburgueria.\n\n"
        "**Pedidos públicos:** clientes criam pedidos sem login via `POST /Pedidos/pedidos`.\n\n"
        "**Painel admin:** autenticação via `POST /auth/login`."
    ),
    version  = "2.3.0",
    lifespan = lifespan,
)

# ── CORS (liberado para todas as origens — ajuste em produção se necessário)
origins = [
    "https://house-burgers.vercel.app",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
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
app.include_router(impressora_router)
app.include_router(extras_router)


# ══════════════════════════════════════════════════════════════════
# ENDPOINTS DE STATUS
# ══════════════════════════════════════════════════════════════════
@app.get("/", tags=["Status"])
def raiz():
    """Verificação rápida de status da API."""
    db_url = str(db.url)
    return {
        "status":   "online",
        "message":  "🍔 API Hamburgueria",
        "versao":   "2.3.0",
        "docs":     "/docs",
        "banco":    "PostgreSQL" if "postgresql" in db_url else "SQLite",
    }


@app.get("/health", tags=["Status"])
def health_check():
    """Health check para monitoramento (uptime robots, Render, etc.)."""
    return {"status": "healthy"}


# ── Handler para Vercel / Render
handler = app
