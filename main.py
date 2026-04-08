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
from extras_routes    import extras_router
 
 
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
    description="API completa para delivery de hamburgueria",
    version="2.2.0",
    lifespan=lifespan,
)
 
# ═══════════════════════════════════════════════════════════════════
# CORS - LIBERADO PARA TODAS AS ORIGENS
# ═══════════════════════════════════════════════════════════════════
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                     # ✅ Aceita TODAS as origens
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
 
# Rotas
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(sales_router)
app.include_router(store_router)
app.include_router(bairro_router)
app.include_router(impressora_router)
app.include_router(extras_router)
 
 
@app.get("/", tags=["Status"])
def raiz():
    """Endpoint de verificação de status"""
    return {
        "status": "online",
        "message": "🍔 API Hamburgueria",
        "docs": "/docs",
        "versao": "2.2.0",
        "cors": "ALL ORIGINS"
    }
 
 
@app.get("/health", tags=["Status"])
def health_check():
    """Health check para monitoramento"""
    return {"status": "healthy"}
 
 
# Handler para Vercel/Render
handler = app
