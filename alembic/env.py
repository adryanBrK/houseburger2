"""
alembic/env.py — VERSÃO CORRIGIDA
=================================
Localização correta: <raiz>/alembic/env.py

Correções aplicadas:
  1. Carrega .env com python-dotenv ANTES de qualquer import dos models
  2. Sobrescreve sqlalchemy.url com DATABASE_URL do ambiente
  3. Falha com mensagem clara se DATABASE_URL não estiver definida
  4. Importa TODOS os models para que o autogenerate detecte todas as tabelas
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── 1. Garantir que a raiz do projeto está no sys.path
#       (necessário para importar models.py, config.py, etc.)
ROOT = Path(__file__).resolve().parent.parent   # .../alembic/env.py → .../
sys.path.insert(0, str(ROOT))

# ── 2. Carregar o .env ANTES de qualquer import que leia variáveis de ambiente
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass   # python-dotenv não instalado; esperamos que as vars já estejam no ambiente

# ── 3. Verificar que DATABASE_URL foi carregada
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "\n\n❌  DATABASE_URL não definida!\n"
        "    Crie o arquivo .env na raiz do projeto com:\n"
        "    DATABASE_URL=postgresql+psycopg2://user:pass@host/db?sslmode=require\n"
    )

# Compatibilidade com URLs antigas no formato postgres:// (Heroku/Render legado)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# Garantir que usa o driver psycopg2 explicitamente
if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

# ── 4. Configuração do Alembic
alembic_config = context.config
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Sobrescrever a URL — isso garante que o Alembic NUNCA usa SQLite acidentalmente
alembic_config.set_main_option("sqlalchemy.url", DATABASE_URL)

# ── 5. Importar TODOS os models para que o autogenerate enxergue todas as tabelas
#       Se você criar novos models, adicione-os aqui também.
from models import (   # noqa: F401  (imports necessários para o metadata)
    Base,
    Categoria,
    Porcao,
    Produto,
    VariacaoProduto,
    Bairro,
    Impressora,
    ConfiguracaoLoja,
    Usuario,
    Pedido,
    ItemPedido,
    LogImpressao,
)

target_metadata = Base.metadata


# ── 6. Funções de migration (offline e online) — padrão Alembic

def run_migrations_offline() -> None:
    """
    Modo offline: gera SQL sem conectar ao banco.
    Útil para revisar as queries antes de aplicar.
    """
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detecta mudanças de tipo de coluna
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Modo online: conecta ao banco e aplica as migrations diretamente.
    """
    connectable = engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
