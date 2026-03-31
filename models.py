import os
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone
import bcrypt

# ==========================
# BANCO DE DADOS
# Para desenvolvimento: SQLite
# Para produção na Vercel: PostgreSQL (via variável de ambiente DATABASE_URL)
# ==========================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banco.db")

# Se for PostgreSQL (Vercel/produção), ajustar o driver
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

db = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    pool_pre_ping=True
)
Base = declarative_base()


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
# PORÇÕES  (opcional — nem todo produto tem)
# ==========================
class Porcao(Base):
    __tablename__ = "porcoes"

    id    = Column(Integer, primary_key=True, autoincrement=True)
    nome  = Column(String, nullable=False, unique=True)
    preco = Column(Float, nullable=False)

    produtos = relationship("Produto", back_populates="porcao")


# ==========================
# PRODUTOS
# Porção é 100% opcional: categoria é obrigatória, porcao_id não.
# ==========================
class Produto(Base):
    __tablename__ = "produtos"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False, unique=True)
    preco      = Column(Float, nullable=False)       # preço base
    descricao  = Column(String, nullable=True)
    imagem_url = Column(String, nullable=True)       # Armazenar URL externa (Cloudinary, S3, etc.)
    disponivel = Column(Boolean, default=True)

    # Porção é OPCIONAL — porcao_id pode ser NULL
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=False)
    porcao_id    = Column(Integer, ForeignKey("porcoes.id"),    nullable=True)

    categoria = relationship("Categoria", back_populates="produtos")
    porcao    = relationship("Porcao",    back_populates="produtos")
    variacoes = relationship("VariacaoProduto", back_populates="produto", cascade="all, delete-orphan")


# ==========================
# VARIAÇÕES DE PRODUTO
# Ex: House Simples / House Pro / House Pro Max
# Cada variação tem nome e acréscimo sobre o preço base do produto.
# ==========================
class VariacaoProduto(Base):
    __tablename__ = "variacoes_produto"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False)    # ex: "Simples", "Pro", "Pro Max"
    descricao  = Column(String, nullable=True)     # ingredientes extras, diferenças
    acrescimo  = Column(Float, default=0.0)        # valor adicionado ao preço base
    disponivel = Column(Boolean, default=True)

    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    produto    = relationship("Produto", back_populates="variacoes")


# ==========================
# CONFIGURAÇÕES DA LOJA
# ==========================
class ConfiguracaoLoja(Base):
    __tablename__ = "configuracoes"

    id                    = Column(Integer, primary_key=True, default=1)
    nome_loja             = Column(String, default="Minha Hamburgueria")
    taxa_entrega          = Column(Float, default=0.0)
    loja_aberta           = Column(Boolean, default=True)
    endereco_loja         = Column(String, nullable=True)
    telefone              = Column(String, nullable=True)
    horario_funcionamento = Column(String, nullable=True)


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
# forma_pagamento: DINHEIRO | PIX | CARTAO  (informado ao finalizar)
# ==========================
class Pedido(Base):
    __tablename__ = "pedidos"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    status          = Column(String, default="PENDENTE")   # PENDENTE | FINALIZADO | CANCELADO
    preco_total     = Column(Float, default=0.0)
    forma_pagamento = Column(String, nullable=True)        # DINHEIRO | PIX | CARTAO
    criado_em       = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    usuario = relationship("Usuario", back_populates="pedidos")
    itens   = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")


# ==========================
# ITENS DO PEDIDO
# variacao_nome registra qual variação foi pedida (null = sem variação)
# ==========================
class ItemPedido(Base):
    __tablename__ = "itens_pedidos"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    quantidade     = Column(Integer, nullable=False)
    nomedoproduto  = Column(String, nullable=False)
    variacao_nome  = Column(String, nullable=True)   # ex: "Pro Max" — null se produto sem variação
    preco_unitario = Column(Float, nullable=False)   # já inclui o acréscimo da variação

    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    pedido    = relationship("Pedido", back_populates="itens")
