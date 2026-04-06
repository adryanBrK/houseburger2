import os
from sqlalchemy import create_engine, Column, String, Integer, Boolean, Float, ForeignKey, DateTime, Text
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
# BAIRROS E TAXA DE ENTREGA
# Cada bairro tem um valor específico de entrega
# ==========================
class Bairro(Base):
    __tablename__ = "bairros"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    nome          = Column(String, nullable=False, unique=True)
    valor_entrega = Column(Float, nullable=False, default=0.0)
    ativo         = Column(Boolean, default=True)
    criado_em     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pedidos = relationship("Pedido", back_populates="bairro")


# ==========================
# IMPRESSORAS
# Cadastro de impressoras térmicas para cozinha e motoboy
# ==========================
class Impressora(Base):
    __tablename__ = "impressoras"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    nome       = Column(String, nullable=False)             # Ex: "Impressora Cozinha Principal"
    tipo       = Column(String, nullable=False)             # USB | REDE
    finalidade = Column(String, nullable=False)             # COZINHA | MOTOBOY
    
    # Conexão
    ip_address = Column(String, nullable=True)              # Para tipo REDE
    porta      = Column(Integer, nullable=True)             # Para tipo REDE (ex: 9100)
    usb_vendor = Column(String, nullable=True)              # Para tipo USB (vendor ID)
    usb_product = Column(String, nullable=True)             # Para tipo USB (product ID)
    
    ativo      = Column(Boolean, default=True)
    criado_em  = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    logs = relationship("LogImpressao", back_populates="impressora", cascade="all, delete-orphan")


# ==========================
# CONFIGURAÇÕES DA LOJA
# Inclui logo e Instagram
# ==========================
class ConfiguracaoLoja(Base):
    __tablename__ = "configuracoes"

    id                    = Column(Integer, primary_key=True, default=1)
    nome_loja             = Column(String, default="Minha Hamburgueria")
    loja_aberta           = Column(Boolean, default=True)
    endereco_loja         = Column(String, nullable=True)
    telefone              = Column(String, nullable=True)
    horario_funcionamento = Column(String, nullable=True)
    
    # NOVOS CAMPOS
    logo_url              = Column(String, nullable=True)   # URL da logo
    instagram             = Column(String, nullable=True)   # @usuario ou link completo


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
# Novo sistema com tipo de entrega e controle de impressão
# ==========================
class Pedido(Base):
    __tablename__ = "pedidos"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    
    # Status do pedido
    status          = Column(String, default="PENDENTE")   # PENDENTE | FINALIZADO | CANCELADO
    
    # Tipo de pedido
    tipo_pedido     = Column(String, nullable=False)       # ENTREGA | BALCAO
    
    # Dados do cliente
    nome_cliente    = Column(String, nullable=False)
    telefone        = Column(String, nullable=True)
    endereco        = Column(String, nullable=True)        # Apenas se ENTREGA
    
    # Valores
    preco_total     = Column(Float, default=0.0)
    valor_entrega   = Column(Float, default=0.0)           # Preenchido automaticamente pelo bairro
    
    # Pagamento
    forma_pagamento = Column(String, nullable=True)        # DINHEIRO | PIX | CARTAO
    troco_para      = Column(Float, nullable=True)         # Se pagamento em dinheiro
    
    # CONTROLE DE IMPRESSÃO
    impresso_cozinha = Column(Boolean, default=False)      # Comanda cozinha impressa?
    impresso_motoboy = Column(Boolean, default=False)      # Comanda motoboy impressa?
    data_impressao_cozinha = Column(DateTime, nullable=True)
    data_impressao_motoboy = Column(DateTime, nullable=True)
    
    # Observações
    observacoes     = Column(Text, nullable=True)
    
    # Timestamps
    criado_em       = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    atualizado_em   = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relacionamentos
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    bairro_id  = Column(Integer, ForeignKey("bairros.id"), nullable=True)

    usuario = relationship("Usuario", back_populates="pedidos")
    bairro  = relationship("Bairro", back_populates="pedidos")
    itens   = relationship("ItemPedido", back_populates="pedido", cascade="all, delete-orphan")
    logs_impressao = relationship("LogImpressao", back_populates="pedido", cascade="all, delete-orphan")


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
    observacoes    = Column(Text, nullable=True)     # Ex: "Sem cebola", "Ponto da carne mal passado"

    pedido_id = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    pedido    = relationship("Pedido", back_populates="itens")


# ==========================
# LOG DE IMPRESSÃO
# Registra todas as tentativas de impressão para auditoria e retry
# ==========================
class LogImpressao(Base):
    __tablename__ = "logs_impressao"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    tipo_comanda  = Column(String, nullable=False)        # COZINHA | MOTOBOY
    sucesso       = Column(Boolean, default=False)        # Impressão bem-sucedida?
    erro          = Column(Text, nullable=True)           # Mensagem de erro se falhou
    tentativas    = Column(Integer, default=1)            # Número de tentativas
    criado_em     = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    pedido_id     = Column(Integer, ForeignKey("pedidos.id"), nullable=False)
    impressora_id = Column(Integer, ForeignKey("impressoras.id"), nullable=True)

    pedido     = relationship("Pedido", back_populates="logs_impressao")
    impressora = relationship("Impressora", back_populates="logs")
