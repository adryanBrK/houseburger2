"""
alembic/versions/xxxx_bairros_taxa_entrega.py
=============================================
Migration para criar a tabela bairros (taxa de entrega por bairro).

Se você já rodou alembic upgrade head antes, esta tabela JÁ EXISTE
e você NÃO precisa desta migration — ela já consta em 77b33f04f38a.

Use este arquivo apenas se estiver configurando o banco do zero
em um ambiente novo (ex: novo PostgreSQL no Neon/Render).

COMO USAR:
  1. Copie este arquivo para alembic/versions/
  2. Renomeie com um hash real: alembic revision --autogenerate -m "bairros_taxa_entrega"
     (o Alembic gerará o arquivo correto automaticamente)
  3. Ou rode direto: alembic upgrade head

ALTERNATIVA MAIS SIMPLES (sem Alembic):
  No main.py, Base.metadata.create_all(bind=db) já cria a tabela
  automaticamente ao iniciar a aplicação — não precisa de migration manual.
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


def upgrade() -> None:
    op.create_table(
        "bairros",
        sa.Column("id",            sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("nome",          sa.String(),   nullable=False),
        sa.Column("valor_entrega", sa.Float(),    nullable=False),
        sa.Column("ativo",         sa.Boolean(),  nullable=True,  default=True),
        sa.Column("criado_em",     sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("nome"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("bairros")
