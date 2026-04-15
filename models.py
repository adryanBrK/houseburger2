"""
models.py — ADICIONADO: model AdicionalProduto
Única mudança em relação à versão anterior:
  - Classe AdicionalProduto adicionada após VariacaoProduto
  - Relationship "adicionais" adicionado em Produto
Tudo mais permanece idêntico.
"""

import os
import enum
import bcrypt
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean,
    Float, ForeignKey, DateTime, Text, Enum as SAEnum,
)
from sqlalchemy.orm import declarative_base, relationship

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "\n\n❌  DATABASE_URL não definida!\n"
        "    Configure a variável de ambiente antes de iniciar.\n"
    )

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

if DATABASE_URL.startswith("postgresql://") and "+psycopg2" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if "sqlite" in DATABASE_URL.lower():
    raise RuntimeError("❌  SQLite não é suportado. Configure DATABASE_URL com PostgreSQL.")

db = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

Base = declarative_base()


# ==========================
# ENUMS
# ==========================
class StatusPedido(str, enum.Enum):
    PENDENTE   = "PENDENTE"
    FINALIZADO = "FINALIZADO"
    CANCELADO  = "CANCELADO"


class TipoPedido(str, enum.Enum):
    ENTREGA  = "ENTREGA"
    RETIRADA = "RETIRADA"
    BALCAO   = "BALCAO"


class FormaPagamento(str, enum.Enum):
    PIX      = "PIX"
    DINHEIRO = "DINHEIRO"
    CARTAO   = "CARTAO"


# ==========================
# CATEGORIAS
# ==========================
class Categoria(Base):
    __tablename__ = "categorias"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    nome      = Column(String, nullable=False, unique=True)
    descricao = Column(String, nullable=True)
    ativo     = Column(Boolean, default=True)

    produtos = relationship("Produto", back_populates="categoria")


# ==========================
# PORÇÕES
# ==========================
class Porcao(Base):
    __tablename__ = "porcoes"

    id    = Column(Integer, primary_key=True, autoincrement=True)
    nome  = Column(String, nullable=False, unique=True)
    preco = Column(Float, nullable=False)

    produtos = relationship("Produto", back_populates="porcao")


# ==========================
# PRODUTOS
# ==========================
class Produto(Base):
    __tablename__ = "produtos"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    nome         = Column(String, nullable=False, unique=True)
    preco        = Column(Float, nullable=False)
    descricao    = Column(String, nullable=True)
    imagem_url   = Column(String, nullable=True)
    disponivel   = Column(Boolean, default=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    porcao_id    = Column(Integer, ForeignKey("porcoes.id"), nullable=True)

    categoria  = relationship("Categoria", back_populates="produtos")
    porcao     = relationship("Porcao", back_populates="produtos")
    variacoes  = relationship(
        "VariacaoProduto", back_populates="produto", cascade="all, delete-orphan"
    )
    # NOVO — adicionais deste produto
    adicionais = relationship(
        "AdicionalProduto", back_populates="produto", cascade="all, delete-orphan"
    )


# ==========================
# VARIAÇÕES DE PRODUTO
# ==========================
class VariacaoProduto(Base):
    __tablename__ = "variacoes_produto"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False)
    descricao  = Column(String, nullable=True)
    acrescimo  = Column(Float, default=0.0)
    disponivel = Column(Boolean, default=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)

    produto = relationship("Produto", back_populates="variacoes")


# ==========================
# ADICIONAIS DE PRODUTO  ← NOVO
# Exemplo: borda recheada, queijo extra, bacon adicional.
# Diferença de VariacaoProduto: adicionais são opcionais e cumulativos
# (o cliente pode pedir vários). Variações são mutuamente exclusivas
# (tamanho P/M/G). Ambos têm acréscimo de preço.
# ==========================
class AdicionalProduto(Base):
    __tablename__ = "adicionais_produto"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False)
    descricao  = Column(String, nullable=True)
    preco      = Column(Float, nullable=False, default=0.0)
    disponivel = Column(Boolean, default=True)
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)

    produto = relationship("Produto", back_populates="adicionais")


# ==========================
# BAIRROS
# ==========================
class Bairro(Base):
    __tablename__ = "bairros"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    nome          = Column(String, nullable=False, unique=True)
    valor_entrega = Column(Float, nullable=False, default=0.0)
    ativo         = Column(Boolean, default=True)
    criado_em     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    pedidos = relationship("Pedido", back_populates="bairro")


# ==========================
# IMPRESSORAS
# ==========================
class Impressora(Base):
    __tablename__ = "impressoras"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    nome        = Column(String, nullable=False)
    tipo        = Column(String, nullable=False)
    finalidade  = Column(String, nullable=False)
    ip_address  = Column(String, nullable=True)
    porta       = Column(Integer, nullable=True)
    usb_vendor  = Column(String, nullable=True)
    usb_product = Column(String, nullable=True)
    ativo       = Column(Boolean, default=True)
    criado_em   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    logs = relationship("LogImpressao", back_populates="impressora", cascade="all, delete-orphan")


# ==========================
# CONFIGURAÇÕES DA LOJA
# ==========================
class ConfiguracaoLoja(Base):
    __tablename__ = "configuracoes"

    id                    = Column(Integer, primary_key=True, default=1)
    nome_loja             = Column(String, default="Minha Hamburgueria")
    loja_aberta           = Column(Boolean, default=True)
    endereco_loja         = Column(String, nullable=True)
    telefone              = Column(String, nullable=True)
    horario_funcionamento = Column(String, nullable=True)
    logo_url              = Column(String, nullable=True)
    instagram             = Column(String, nullable=True)


# ==========================
# USUÁRIOS
# ==========================
class Usuario(Base):
    __tablename__ = "usuarios"

    id    = Column(Integer, primary_key=True, autoincrement=True)
    nome  = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    senha = Column(String, nullable=False)
    ativo = Column(Boolean, default=True)
    admin = Column(Boolean, default=False)

    pedidos = relationship("Pedido", back_populates="usuario")

    def __init__(self, nome: str, email: str, senha: str, ativo: bool = True, admin: bool = False):
        self.nome  = nome
        self.email = email
        self.ativo = ativo
        self.admin = admin
        self.senha = self._hash_senha(senha)

    @staticmethod
    def _hash_senha(senha_plana: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(senha_plana.encode("utf-8"), salt).decode("utf-8")


# ==========================
# PEDIDOS
# ==========================
class Pedido(Base):
    __tablename__ = "pedidos"

    id     = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String, nullable=True, index=True)

    status = Column(
        SAEnum(StatusPedido, values_callable=lambda e: [i.value for i in e]),
        default=StatusPedido.PENDENTE,
        nullable=False,
    )

    tipo_pedido = Column(
        SAEnum(TipoPedido, values_callable=lambda e: [i.value for i in e]),
        nullable=False,
    )

    nome_cliente = Column(String, nullable=False)
    telefone     = Column(String, nullable=False)
    endereco     = Column(String, nullable=True)

    preco_total   = Column(Float, default=0.0)
    valor_entrega = Column(Float, default=0.0)

    forma_pagamento = Column(
        SAEnum(FormaPagamento, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
    )
    troco_para = Column(Float, nullable=True)

    impresso_cozinha       = Column(Boolean, default=False)
    impresso_motoboy       = Column(Boolean, default=False)
    data_impressao_cozinha = Column(DateTime(timezone=True), nullable=True)
    data_impressao_motoboy = Column(DateTime(timezone=True), nullable=True)

    observacoes = Column(Text, nullable=True)

    criado_em     = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    atualizado_em = Column(
        DateTime(timezone=True),
        default=lambda:  datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    bairro_id  = Column(Integer, ForeignKey("bairros.id"), nullable=True)

    usuario        = relationship("Usuario", back_populates="pedidos")
    bairro         = relationship("Bairro", back_populates="pedidos")
    itens          = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")
    logs_impressao = relationship("LogImpressao", back_populates="pedido", cascade="all, delete-orphan")


# ==========================
# ITENS DO PEDIDO
# ==========================
class ItemPedido(Base):
    __tablename__ = "itens_pedidos"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    quantidade     = Column(Integer, nullable=False)
    nomedoproduto  = Column(String, nullable=False)
    variacao_nome  = Column(String, nullable=True)
    preco_unitario = Column(Float, nullable=False)
    observacoes    = Column(Text, nullable=True)

    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    pedido    = relationship("Pedido", back_populates="itens")


# ==========================
# LOG DE IMPRESSÃO
# ==========================
class LogImpressao(Base):
    __tablename__ = "logs_impressao"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    tipo_comanda = Column(String, nullable=False)
    sucesso      = Column(Boolean, default=False)
    erro         = Column(Text, nullable=True)
    tentativas   = Column(Integer, default=1)
    criado_em    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    pedido_id     = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    impressora_id = Column(Integer, ForeignKey("impressoras.id"), nullable=True)

    pedido     = relationship("Pedido", back_populates="logs_impressao")
    impressora = relationship("Impressora", back_populates="logs")
