"""
migrate_to_postgres.py — VERSÃO CORRIGIDA
==========================================
Migra dados do SQLite local para PostgreSQL (Neon).

CORREÇÕES:
  - Objetos SQLAlchemy não são passados entre sessões diretamente
    (causa DetachedInstanceError). Agora copiamos apenas os valores
    das colunas para um novo objeto limpo.
  - Respeita a ordem de foreign keys para evitar erros de integridade.
  - Mostra progresso e erros detalhados.

USO:
  1. Certifique-se de que banco.db existe na pasta do projeto
  2. Configure DATABASE_URL no .env ou como variável de ambiente
  3. Execute: python migrate_to_postgres.py
"""

import os
import sys
from pathlib import Path

# Carregar .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    print("⚠️  python-dotenv não instalado. Esperando DATABASE_URL no ambiente.")

from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

# Importar todos os models
from models import (
    Base,
    Usuario, Categoria, Porcao, Produto, VariacaoProduto,
    ConfiguracaoLoja, Bairro, Impressora, Pedido, ItemPedido, LogImpressao,
)

# ── Verificar banco de origem
SQLITE_PATH = Path(__file__).resolve().parent / "banco.db"
if not SQLITE_PATH.exists():
    print(f"❌ banco.db não encontrado em: {SQLITE_PATH}")
    sys.exit(1)

SQLITE_URL = f"sqlite:///{SQLITE_PATH}"

# ── Verificar banco de destino
POSTGRES_URL = os.getenv("DATABASE_URL")
if not POSTGRES_URL:
    print("❌ DATABASE_URL não definida. Configure o .env antes de rodar.")
    sys.exit(1)

# Normalizar URL
if POSTGRES_URL.startswith("postgres://"):
    POSTGRES_URL = POSTGRES_URL.replace("postgres://", "postgresql+psycopg2://", 1)
if POSTGRES_URL.startswith("postgresql://") and "+psycopg2" not in POSTGRES_URL:
    POSTGRES_URL = POSTGRES_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

print("=" * 60)
print("🔄  MIGRAÇÃO SQLite → PostgreSQL")
print(f"📤  Origem : {SQLITE_URL}")
print(f"📥  Destino: {POSTGRES_URL[:60]}...")
print("=" * 60)

# ── Conectar
try:
    sqlite_engine   = create_engine(SQLITE_URL)
    postgres_engine = create_engine(POSTGRES_URL, pool_pre_ping=True)

    SQLiteSession   = sessionmaker(bind=sqlite_engine)
    PostgresSession = sessionmaker(bind=postgres_engine)

    sqlite_session   = SQLiteSession()
    postgres_session = PostgresSession()
    print("✅  Conexões estabelecidas\n")
except Exception as e:
    print(f"❌  Erro ao conectar: {e}")
    sys.exit(1)

# ── Criar tabelas no PostgreSQL (se não existirem)
try:
    Base.metadata.create_all(bind=postgres_engine)
    print("✅  Tabelas verificadas/criadas no PostgreSQL\n")
except Exception as e:
    print(f"❌  Erro ao criar tabelas: {e}")
    sys.exit(1)


def _colunas(model) -> list[str]:
    """Retorna os nomes das colunas mapeadas de um model SQLAlchemy."""
    return [c.key for c in sa_inspect(model).mapper.column_attrs]


def migrate_table(model, name: str) -> None:
    """
    Copia todos os registros de uma tabela do SQLite para o PostgreSQL.

    Cria novos objetos Python com os valores copiados — nunca passa
    o objeto original entre sessões (evita DetachedInstanceError).
    """
    try:
        records = sqlite_session.query(model).all()

        if not records:
            print(f"  ⚠️  {name}: tabela vazia — nada a migrar")
            return

        col_names = _colunas(model)

        for record in records:
            data = {col: getattr(record, col) for col in col_names}
            postgres_session.merge(model(**data))

        postgres_session.commit()
        print(f"  ✅  {name}: {len(records)} registro(s) migrado(s)")

    except Exception as e:
        postgres_session.rollback()
        print(f"  ❌  Erro ao migrar {name}: {e}")


# ── Migrar na ordem correta (respeitar foreign keys)
print("🔄  Migrando tabelas...")
migrate_table(Usuario,          "Usuários")
migrate_table(Categoria,        "Categorias")
migrate_table(Porcao,           "Porções")
migrate_table(Produto,          "Produtos")
migrate_table(VariacaoProduto,  "Variações de Produtos")
migrate_table(ConfiguracaoLoja, "Configurações da Loja")
migrate_table(Bairro,           "Bairros")
migrate_table(Impressora,       "Impressoras")
migrate_table(Pedido,           "Pedidos")
migrate_table(ItemPedido,       "Itens de Pedidos")
migrate_table(LogImpressao,     "Logs de Impressão")

# ── Fechar conexões
sqlite_session.close()
postgres_session.close()

print("\n" + "=" * 60)
print("✅  Migração concluída!")
print("\n📋  Próximos passos:")
print("  1. Verifique os dados no painel do Neon (SQL Editor)")
print("  2. Confirme: SELECT COUNT(*) FROM usuarios;")
print("  3. Suba a API com DATABASE_URL apontando para o Neon")
print("  4. Teste: GET / deve retornar  \"banco\": \"PostgreSQL\"")
print("=" * 60)
