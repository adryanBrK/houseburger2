from pydantic import BaseModel, field_validator, model_validator
from typing import Optional
from models import TipoPedido


class PedidoSchema(BaseModel):
    nome_cliente: str
    telefone: Optional[str] = None  # agora opcional
    endereco: Optional[str] = None
    bairro_id: Optional[int] = None
    tipo_pedido: str
    observacoes: Optional[str] = None
    id_usuario: Optional[int] = None
    forma_pagamento: Optional[str] = None  # adicionado

    # ─────────────────────────────────────
    # VALIDAÇÕES
    # ─────────────────────────────────────

    @field_validator("nome_cliente")
    @classmethod
    def nome_nao_vazio(cls, v):
        if not v or not v.strip():
            raise ValueError("Nome do cliente é obrigatório")
        return v.strip()

    @field_validator("telefone")
    @classmethod
    def telefone_tratado(cls, v):
        # permite vazio
        if not v or not v.strip():
            return None

        digits = "".join(c for c in v if c.isdigit())

        if len(digits) < 8:
            raise ValueError("Telefone inválido — mínimo 8 dígitos")

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
                raise ValueError("Endereço é obrigatório para ENTREGA")
        return self

    class Config:
        from_attributes = True
