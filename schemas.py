from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import datetime

from models import StatusPedido, TipoPedido, FormaPagamento


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
    nome:       str
    descricao:  Optional[str]  = None
    ativo:      Optional[bool] = True
    # imagem_url e ordem são gerenciados por rotas dedicadas
    # mas aceitos aqui para compatibilidade com frontends que os enviam
    imagem_url: Optional[str] = None
    ordem:      Optional[int] = 0


class ResponseCategoriaSchema(BaseModel):
    id:         int
    nome:       str
    descricao:  Optional[str]
    ativo:      bool
    imagem_url: Optional[str] = None
    ordem:      int = 0

    class Config:
        from_attributes = True


# ==========================
# PORÇÃO
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
# ==========================
class VariacaoSchema(BaseModel):
    nome:       str
    descricao:  Optional[str] = None
    acrescimo:  float = 0.0
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
# ADICIONAIS
# ==========================
class AdicionalSchema(BaseModel):
    nome:       str
    descricao:  Optional[str] = None
    preco:      float = 0.0
    ativo:      Optional[bool] = True
    limite_qtd: Optional[int] = None

    @field_validator("preco")
    @classmethod
    def preco_nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Preço do adicional não pode ser negativo")
        return v

    @field_validator("limite_qtd")
    @classmethod
    def limite_positivo(cls, v):
        if v is not None and v <= 0:
            raise ValueError("limite_qtd deve ser maior que zero")
        return v


class ResponseAdicionalSchema(BaseModel):
    id:         int
    nome:       str
    descricao:  Optional[str]
    preco:      float
    ativo:      bool
    limite_qtd: Optional[int]

    class Config:
        from_attributes = True


# ==========================
# PRODUTO
# ==========================
class ProdutoSchema(BaseModel):
    nome:         str
    descricao:    Optional[str]  = None
    preco:        float
    categoria_id: int
    porcao_id:    Optional[int]  = None
    imagem_url:   Optional[str]  = None
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
    porcao_id:    Optional[int]
    variacoes:    List[ResponseVariacaoSchema]  = []
    adicionais:   List[ResponseAdicionalSchema] = []

    class Config:
        from_attributes = True


class ResponseProdutoDetalhadoSchema(ResponseProdutoSchema):
    categoria: Optional[ResponseCategoriaSchema]
    porcao:    Optional[ResponsePorcaoSchema]

    class Config:
        from_attributes = True


# ==========================
# BAIRROS
# ==========================
class BairroSchema(BaseModel):
    nome:          str
    valor_entrega: float
    ativo:         Optional[bool] = True

    @field_validator("valor_entrega")
    @classmethod
    def valor_nao_negativo(cls, v):
        if v < 0:
            raise ValueError("Valor de entrega não pode ser negativo")
        return v


class ResponseBairroSchema(BaseModel):
    id:            int
    nome:          str
    valor_entrega: float
    ativo:         bool
    criado_em:     datetime

    class Config:
        from_attributes = True


# ==========================
# IMPRESSORAS
# ==========================
class ImpressoraSchema(BaseModel):
    nome:        str
    tipo:        str
    finalidade:  str
    ip_address:  Optional[str] = None
    porta:       Optional[int] = None
    usb_vendor:  Optional[str] = None
    usb_product: Optional[str] = None
    ativo:       Optional[bool] = True

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v):
        v = v.upper()
        if v not in ["USB", "REDE"]:
            raise ValueError("Tipo deve ser USB ou REDE")
        return v

    @field_validator("finalidade")
    @classmethod
    def finalidade_valida(cls, v):
        v = v.upper()
        if v not in ["COZINHA", "MOTOBOY"]:
            raise ValueError("Finalidade deve ser COZINHA ou MOTOBOY")
        return v


class ResponseImpressoraSchema(BaseModel):
    id:          int
    nome:        str
    tipo:        str
    finalidade:  str
    ip_address:  Optional[str]
    porta:       Optional[int]
    usb_vendor:  Optional[str]
    usb_product: Optional[str]
    ativo:       bool
    criado_em:   datetime

    class Config:
        from_attributes = True


# ==========================
# ITENS DO PEDIDO
# ==========================
class ItemPedidoSchema(BaseModel):
    quantidade:     int
    nomedoproduto:  str
    preco_unitario: float
    variacao_id:    Optional[int]       = None
    adicionais_ids: Optional[List[int]] = None
    observacoes:    Optional[str]       = None

    @field_validator("quantidade")
    @classmethod
    def quantidade_positiva(cls, v):
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v

    class Config:
        from_attributes = True


class ResponseItemPedidoSchema(BaseModel):
    id:               int
    quantidade:       int
    nomedoproduto:    str
    variacao_nome:    Optional[str]
    preco_unitario:   float
    adicionais_nomes: Optional[str] = None
    adicionais_preco: float = 0.0
    observacoes:      Optional[str]
    subtotal:         float = 0.0

    class Config:
        from_attributes = True


# ==========================
# PEDIDO  —  CRIAÇÃO PÚBLICA (sem login)
# ==========================
class PedidoSchema(BaseModel):
    nome_cliente: str
    telefone:     str
    endereco:     Optional[str] = None
    bairro_id:    Optional[int] = None
    tipo_pedido:  str
    observacoes:  Optional[str] = None
    id_usuario:   Optional[int] = None

    @field_validator("nome_cliente")
    @classmethod
    def nome_nao_vazio(cls, v):
        if not v or not v.strip():
            raise ValueError("Nome do cliente é obrigatório")
        return v.strip()

    @field_validator("telefone")
    @classmethod
    def telefone_nao_vazio(cls, v):
        if not v or not v.strip():
            raise ValueError("Telefone é obrigatório")
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 8:
            raise ValueError("Telefone inválido — informe pelo menos 8 dígitos")
        return v.strip()

    @field_validator("tipo_pedido")
    @classmethod
    def tipo_valido(cls, v):
        v = v.upper()
        validos = {t.value for t in TipoPedido}
        if v not in validos:
            raise ValueError(f"tipo_pedido deve ser: {', '.join(validos)}")
        return v

    @model_validator(mode="after")
    def endereco_obrigatorio_para_entrega(self):
        if self.tipo_pedido == TipoPedido.ENTREGA.value:
            if not self.endereco or not self.endereco.strip():
                raise ValueError("endereco é obrigatório para pedidos do tipo ENTREGA")
        return self

    class Config:
        from_attributes = True


class FinalizarPedidoSchema(BaseModel):
    forma_pagamento: str
    troco_para:      Optional[float] = None

    @field_validator("forma_pagamento")
    @classmethod
    def forma_valida(cls, v):
        v = v.upper().strip()
        validas = {f.value for f in FormaPagamento}
        if v not in validas:
            raise ValueError(f"Forma de pagamento inválida. Use: {', '.join(validas)}")
        return v


class ResponsePedidoSchema(BaseModel):
    id:              int
    codigo:          Optional[str]
    status:          str
    tipo_pedido:     str
    nome_cliente:    str
    telefone:        str
    endereco:        Optional[str]
    preco_total:     float
    valor_entrega:   float
    forma_pagamento: Optional[str]
    troco_para:      Optional[float]
    observacoes:     Optional[str]

    impresso_cozinha:       bool
    impresso_motoboy:       bool
    data_impressao_cozinha: Optional[datetime]
    data_impressao_motoboy: Optional[datetime]

    criado_em:     datetime
    atualizado_em: datetime
    usuario_id:    Optional[int]
    bairro_id:     Optional[int]
    itens:         List[ResponseItemPedidoSchema] = []

    class Config:
        from_attributes = True


class ResponsePedidoDetalhadoSchema(ResponsePedidoSchema):
    bairro: Optional[ResponseBairroSchema]

    class Config:
        from_attributes = True


# ==========================
# CONFIGURAÇÃO DA LOJA
# ==========================
class ConfiguracaoLojaSchema(BaseModel):
    nome_loja:             Optional[str]  = None
    loja_aberta:           Optional[bool] = None
    endereco_loja:         Optional[str]  = None
    telefone:              Optional[str]  = None
    horario_funcionamento: Optional[str]  = None
    logo_url:              Optional[str]  = None
    instagram:             Optional[str]  = None


class ResponseConfiguracaoLojaSchema(BaseModel):
    id:                    int
    nome_loja:             str
    loja_aberta:           bool
    endereco_loja:         Optional[str]
    telefone:              Optional[str]
    horario_funcionamento: Optional[str]
    logo_url:              Optional[str]
    instagram:             Optional[str]

    class Config:
        from_attributes = True


# ==========================
# LOG DE IMPRESSÃO
# ==========================
class ResponseLogImpressaoSchema(BaseModel):
    id:            int
    tipo_comanda:  str
    sucesso:       bool
    erro:          Optional[str]
    tentativas:    int
    criado_em:     datetime
    pedido_id:     int
    impressora_id: Optional[int]

    class Config:
        from_attributes = True


# ==========================
# VENDAS / RELATÓRIOS
# ==========================
class ResumoFormasPagamentoSchema(BaseModel):
    dinheiro:      float
    pix:           float
    cartao:        float
    nao_informado: float


class ResponseVendasSchema(BaseModel):
    periodo:       str
    total_pedidos: int
    receita_total: float
    ticket_medio:  float
    por_pagamento: ResumoFormasPagamentoSchema


# ==========================
# UPLOAD DE IMAGEM (Cloudinary)
# ==========================
class ResponseUploadImagemSchema(BaseModel):
    """Retorno padronizado após upload bem-sucedido."""
    mensagem:   str
    imagem_url: str


# ==========================
# REORDENAÇÃO DE CATEGORIAS
# ==========================
class ReordenarCategoriasSchema(BaseModel):
    """
    Lista de IDs na nova ordem desejada.
    Exemplo: {"ids": [3, 1, 2, 5]}
    A posição na lista define o valor de `ordem` de cada categoria.
    """
    ids: List[int]
