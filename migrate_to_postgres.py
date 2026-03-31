"""
Script para migrar dados do SQLite local para PostgreSQL na Vercel

USO:
1. Configure a variável DATABASE_URL com a connection string do PostgreSQL
2. Execute: python migrate_to_postgres.py
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Importar modelos
from models import Base, Usuario, Categoria, Porcao, Produto, VariacaoProduto, ConfiguracaoLoja, Pedido, ItemPedido

# Configuração
SQLITE_DB = "sqlite:///./banco.db"  # Banco local
POSTGRES_DB = os.getenv("DATABASE_URL")  # Banco PostgreSQL

if not POSTGRES_DB:
    print("❌ Erro: Configure a variável DATABASE_URL com a connection string do PostgreSQL")
    print("Exemplo: export DATABASE_URL='postgresql://user:pass@host/db'")
    exit(1)

# Ajustar URL do Postgres se necessário
if POSTGRES_DB.startswith("postgres://"):
    POSTGRES_DB = POSTGRES_DB.replace("postgres://", "postgresql://", 1)

print("🔄 Iniciando migração...")
print(f"📤 Origem: {SQLITE_DB}")
print(f"📥 Destino: {POSTGRES_DB[:50]}...")

# Conectar aos bancos
try:
    sqlite_engine = create_engine(SQLITE_DB)
    postgres_engine = create_engine(POSTGRES_DB)
    
    SQLiteSession = sessionmaker(bind=sqlite_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)
    
    sqlite_session = SQLiteSession()
    postgres_session = PostgresSession()
    
    print("✅ Conexões estabelecidas")
except Exception as e:
    print(f"❌ Erro ao conectar: {e}")
    exit(1)

# Criar tabelas no PostgreSQL
try:
    Base.metadata.create_all(bind=postgres_engine)
    print("✅ Tabelas criadas no PostgreSQL")
except Exception as e:
    print(f"❌ Erro ao criar tabelas: {e}")
    exit(1)

# Função para migrar uma tabela
def migrate_table(model, name):
    try:
        records = sqlite_session.query(model).all()
        if not records:
            print(f"⚠️  {name}: 0 registros (tabela vazia)")
            return
        
        for record in records:
            # Criar novo objeto sem o ID para evitar conflitos
            postgres_session.merge(record)
        
        postgres_session.commit()
        print(f"✅ {name}: {len(records)} registros migrados")
    except Exception as e:
        postgres_session.rollback()
        print(f"❌ Erro ao migrar {name}: {e}")

# Migrar dados na ordem correta (respeitando foreign keys)
print("\n🔄 Migrando dados...")

migrate_table(Usuario, "Usuários")
migrate_table(Categoria, "Categorias")
migrate_table(Porcao, "Porções")
migrate_table(Produto, "Produtos")
migrate_table(VariacaoProduto, "Variações de Produtos")
migrate_table(ConfiguracaoLoja, "Configurações da Loja")
migrate_table(Pedido, "Pedidos")
migrate_table(ItemPedido, "Itens de Pedidos")

# Fechar conexões
sqlite_session.close()
postgres_session.close()

print("\n✅ Migração concluída com sucesso!")
print("\n📝 Próximos passos:")
print("1. Verifique os dados no PostgreSQL")
print("2. Faça deploy na Vercel com a DATABASE_URL configurada")
print("3. Teste a API em produção")
