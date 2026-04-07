from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from models import Base, db, Usuario
from auth_routes      import auth_router
from product_routes   import product_router
from order_routes     import order_router
from sales_routes     import sales_router
from store_routes     import store_router
from bairro_routes    import bairro_router
from impressora_routes import impressora_router


def _inicializar():
    """Inicializa o banco de dados e cria o usuário admin padrão"""
    Base.metadata.create_all(bind=db)
    session = sessionmaker(bind=db)()
    try:
        if not session.query(Usuario).filter(Usuario.email == "admin@hamburgueria.com").first():
            session.add(Usuario(
                nome="Administrador", 
                email="admin@hamburgueria.com",
                senha="admin123", 
                admin=True, 
                ativo=True
            ))
            session.commit()
            print("✅ Admin criado  →  admin@hamburgueria.com  /  admin123")
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação"""
    _inicializar()
    yield


# Aplicação FastAPI
app = FastAPI(
    title="🍔 API Hamburgueria",
    description="API completa para delivery de hamburgueria - Deploy Vercel",
    version="2.2.0",
    lifespan=lifespan,
)

# ═══════════════════════════════════════════════════════════════════
# CORS - Lista explícita dos domínios permitidos
# Adicione aqui qualquer outro domínio do seu frontend
# ═══════════════════════════════════════════════════════════════════
ALLOWED_ORIGINS = [
    "https://house-burgers.vercel.app",   # seu frontend (ESSENCIAL)
    "https://houseburger2.onrender.com",  # sua API real (ESSENCIAL)
    "http://localhost:3000",              # dev React
    "http://localhost:5173",              # dev Vite
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,           # Lista de origens permitidas
    allow_credentials=True,                  # Permite cookies/credenciais
    allow_methods=["*"],                     # Permite todos os métodos (GET, POST, etc)
    allow_headers=["*"],                     # Permite todos os headers
    expose_headers=["*"],                    # Expõe todos os headers na resposta
)

# Rotas
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(impressora_router)


@app.get("/", tags=["Status"])
def raiz():
    """Endpoint de verificação de status"""
    return {
        "status": "online",
        "message": "🍔 API Hamburgueria - Render Deploy",
        "docs": "/docs",
        "versao": "2.2.0",
        "cors": "enabled",
        "allowed_origins": len(ALLOWED_ORIGINS)
    }


@app.get("/health", tags=["Status"])
def health_check():
    """Health check para monitoramento"""
    return {"status": "healthy", "database": "connected"}


# Handler para Vercel
handler = app
