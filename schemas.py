from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


# ==========================
# AUTH
# ==========================
class UsuarioSchema(BaseModel):
    nome:  str
    email: str
    senha: str
    ativo: Optional[bool] = True
    admin: Optional[bool] = False

    class Config:
        from_attributes = True


class LoginSchema(BaseModel):
    email: str
    senha: str


class TokenSchema(BaseModel):
    access_token:  str
    refresh_token: Optional[str] = None
    token_type:    str = "bearer"


# ==========================
# CATEGORIA
# ==========================
class CategoriaSchema(BaseModel):
    nome:      str
    descricao: Optional[str] = None
    ativo:     Optional[bool] = True


class ResponseCategoriaSchema(BaseModel):
    id:        int
    nome:      str
    descricao: Optional[str]
    ativo:     bool

    class Config:
        from_attributes = True


# ==========================
# PORÇÃO  (só usada quando o produto realmente tem porção)
# ==========================
class PorcaoSchema(BaseModel):
    nome:  str
    preco: float

    @field_validator("preco")
    @classmethod
    def preco_positivo(cls, v):
        if v <= 0:
            raise ValueError("Preço deve ser maior que zero")
        return v


class ResponsePorcaoSchema(BaseModel):
    id:    int
    nome:  str
    preco: float

    class Config:
        from_attributes = True


# ==========================
# VARIAÇÕES DE PRODUTO
# Ex: House Simples (acrescimo=0), House Pro (+5), House Pro Max (+10)
# ==========================
class VariacaoSchema(BaseModel):
    nome:      str
    descricao: Optional[str] = None
    acrescimo: float = 0.0
    disponivel: Optional[bool] = True

    @field_validator("acrescimo")
    @classmethod
    def acrescimo_nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Acréscimo não pode ser negativo")
        return v


class ResponseVariacaoSchema(BaseModel):
    id:         int
    nome:       str
    descricao:  Optional[str]
    acrescimo:  float
    disponivel: bool
    produto_id: int

    class Config:
        from_attributes = True


# ==========================
# PRODUTO
# porcao_id é completamente opcional — só enviar se o produto tiver porção
# ==========================
class ProdutoSchema(BaseModel):
    nome:         str
    descricao:    Optional[str]  = None
    preco:        float                    # preço base
    categoria_id: int
    porcao_id:    Optional[int]  = None   # OPCIONAL — não enviar se não tiver porção
    imagem_url:   Optional[str]  = None   # URL externa da imagem (Cloudinary, ImgBB, etc.)
    disponivel:   Optional[bool] = True

    @field_validator("preco")
    @classmethod
    def preco_positivo(cls, v):
        if v <= 0:
            raise ValueError("Preço deve ser maior que zero")
        return v


class ResponseProdutoSchema(BaseModel):
    id:           int
    nome:         str
    descricao:    Optional[str]
    preco:        float
    imagem_url:   Optional[str]
    disponivel:   bool
    categoria_id: int
    porcao_id:    Optional[int]    # null quando sem porção
    variacoes:    List[ResponseVariacaoSchema] = []

    class Config:
        from_attributes = True


class ResponseProdutoDetalhadoSchema(ResponseProdutoSchema):
    categoria: Optional[ResponseCategoriaSchema]
    porcao:    Optional[ResponsePorcaoSchema]    # null quando sem porção

    class Config:
        from_attributes = True


# ==========================
# ITENS DO PEDIDO
# variacao_id: opcional — só enviar se o cliente escolheu uma variação
# ==========================
class ItemPedidoSchema(BaseModel):
    quantidade:    int
    nomedoproduto: str
    preco_unitario: float
    variacao_id:   Optional[int] = None   # ID da VariacaoProduto escolhida (opcional)

    @field_validator("quantidade")
    @classmethod
    def quantidade_positiva(cls, v):
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v

    class Config:
        from_attributes = True


class ResponseItemPedidoSchema(BaseModel):
    id:             int
    quantidade:     int
    nomedoproduto:  str
    variacao_nome:  Optional[str]    # nome da variação ou null
    preco_unitario: float
    subtotal:       float = 0.0

    class Config:
        from_attributes = True


# ==========================
# PEDIDO
# forma_pagamento informada ao finalizar: DINHEIRO | PIX | CARTAO
# ==========================
FORMAS_PAGAMENTO_VALIDAS = {"DINHEIRO", "PIX", "CARTAO"}


class PedidoSchema(BaseModel):
    id_usuario: int

    class Config:
        from_attributes = True


class FinalizarPedidoSchema(BaseModel):
    forma_pagamento: str   # DINHEIRO | PIX | CARTAO

    @field_validator("forma_pagamento")
    @classmethod
    def forma_valida(cls, v):
        v = v.upper().strip()
        if v not in FORMAS_PAGAMENTO_VALIDAS:
            raise ValueError(f"Forma de pagamento inválida. Use: {', '.join(FORMAS_PAGAMENTO_VALIDAS)}")
        return v


class ResponsePedidoSchema(BaseModel):
    id:              int
    status:          str
    preco_total:     float
    forma_pagamento: Optional[str]
    criado_em:       datetime
    usuario_id:      int
    itens:           List[ResponseItemPedidoSchema] = []

    class Config:
        from_attributes = True


# ==========================
# CONFIGURAÇÃO DA LOJA
# ==========================
class ConfiguracaoLojaSchema(BaseModel):
    nome_loja:             Optional[str]   = None
    taxa_entrega:          Optional[float] = None
    loja_aberta:           Optional[bool]  = None
    endereco_loja:         Optional[str]   = None
    telefone:              Optional[str]   = None
    horario_funcionamento: Optional[str]   = None


class ResponseConfiguracaoLojaSchema(BaseModel):
    id:                    int
    nome_loja:             str
    taxa_entrega:          float
    loja_aberta:           bool
    endereco_loja:         Optional[str]
    telefone:              Optional[str]
    horario_funcionamento: Optional[str]

    class Config:
        from_attributes = True


# ==========================
# VENDAS / RELATÓRIOS
# ==========================
class ResumoFormasPagamentoSchema(BaseModel):
    dinheiro:      float
    pix:           float
    cartao:        float
    nao_informado: float   # pedidos finalizados sem forma de pagamento registrada


class ResponseVendasSchema(BaseModel):
    periodo:          str
    total_pedidos:    int
    receita_total:    float
    ticket_medio:     float
    por_pagamento:    ResumoFormasPagamentoSchema