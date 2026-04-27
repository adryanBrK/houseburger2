"""
product_routes.py — COMPLETO
==============================
CRUD de produtos, variações e adicionais.

Adicionais:
  - Usam APENAS o model global Adicional (N:N via produto_adicional)
  - Nenhuma referência a ProdutoAdicional (removido)
  - Vínculo: produto.adicionais.append(adicional)
  - Desvínculo: produto.adicionais.remove(adicional)

Campo `disponivel` (Produto) vs `ativo` (Categoria/Adicional):
  - Produto usa `disponivel` — mantido para compatibilidade
  - Categoria e Adicional usam `ativo`
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from dependencias import pegar_sessao, verificar_admin
from schemas import (
    ProdutoSchema, ResponseProdutoSchema, ResponseProdutoDetalhadoSchema,
    VariacaoSchema, ResponseVariacaoSchema,
    AdicionalSchema, ResponseAdicionalSchema,
)
from models import Adicional, Categoria, Produto, Porcao, VariacaoProduto, Usuario

log = logging.getLogger("product_routes")
product_router = APIRouter(prefix="/Produto", tags=["Produtos"])


# ══════════════════════════════════════════════════════════════════
# PRODUTOS
# ══════════════════════════════════════════════════════════════════

@product_router.get(
    "/produtos",
    response_model=List[ResponseProdutoSchema],
    summary="Lista produtos (público)",
)
async def listar_produtos(
    categoria_id:  int | None = None,
    apenas_disponíveis: bool  = True,
    session: Session          = Depends(pegar_sessao),
):
    q = (
        session.query(Produto)
        .options(
            joinedload(Produto.variacoes),
            joinedload(Produto.adicionais),
        )
    )
    if apenas_disponíveis:
        q = q.filter(Produto.disponivel == True)
    if categoria_id is not None:
        q = q.filter(Produto.categoria_id == categoria_id)
    return q.order_by(Produto.nome).all()


@product_router.get(
    "/produtos/{produto_id}",
    response_model=ResponseProdutoDetalhadoSchema,
    summary="Detalhe do produto com categoria e porção (público)",
)
async def buscar_produto(
    produto_id: int,
    session:    Session = Depends(pegar_sessao),
):
    produto = (
        session.query(Produto)
        .options(
            joinedload(Produto.categoria),
            joinedload(Produto.porcao),
            joinedload(Produto.variacoes),
            joinedload(Produto.adicionais),
        )
        .filter(Produto.id == produto_id)
        .first()
    )
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return produto


@product_router.post(
    "/produtos",
    response_model=ResponseProdutoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria produto (admin)",
)
async def criar_produto(
    dados:   ProdutoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    # Validar categoria
    cat = session.query(Categoria).filter(Categoria.id == dados.categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail=f"Categoria id={dados.categoria_id} não encontrada")

    # Validar porção (opcional)
    if dados.porcao_id:
        porcao = session.query(Porcao).filter(Porcao.id == dados.porcao_id).first()
        if not porcao:
            raise HTTPException(status_code=404, detail=f"Porção id={dados.porcao_id} não encontrada")

    produto = Produto(
        nome         = dados.nome.strip(),
        descricao    = dados.descricao,
        preco        = dados.preco,
        categoria_id = dados.categoria_id,
        porcao_id    = dados.porcao_id,
        imagem_url   = dados.imagem_url,
        disponivel   = dados.disponivel if dados.disponivel is not None else True,
    )
    session.add(produto)
    try:
        session.commit()
        session.refresh(produto)
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao criar produto: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Produto com esse nome já existe")

    log.info("[product] Criado produto id=%s nome=%s", produto.id, produto.nome)
    return produto


@product_router.put(
    "/produtos/{produto_id}",
    response_model=ResponseProdutoSchema,
    summary="Atualiza produto (admin)",
)
async def atualizar_produto(
    produto_id: int,
    dados:   ProdutoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Validar categoria
    cat = session.query(Categoria).filter(Categoria.id == dados.categoria_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail=f"Categoria id={dados.categoria_id} não encontrada")

    produto.nome         = dados.nome.strip()
    produto.descricao    = dados.descricao
    produto.preco        = dados.preco
    produto.categoria_id = dados.categoria_id
    produto.porcao_id    = dados.porcao_id
    if dados.imagem_url is not None:
        produto.imagem_url = dados.imagem_url
    if dados.disponivel is not None:
        produto.disponivel = dados.disponivel

    try:
        session.commit()
        session.refresh(produto)
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao atualizar produto %s: %s", produto_id, exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Nome já usado por outro produto")
    return produto


@product_router.patch(
    "/produtos/{produto_id}/disponivel",
    summary="Ativa/desativa produto (admin)",
)
async def toggle_produto(
    produto_id: int,
    disponivel: bool,
    session:    Session = Depends(pegar_sessao),
    _: Usuario          = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    produto.disponivel = disponivel
    session.commit()
    return {"mensagem": f"Produto '{produto.nome}' {'disponível' if disponivel else 'indisponível'}"}


@product_router.delete(
    "/produtos/{produto_id}",
    summary="Remove produto (admin)",
)
async def deletar_produto(
    produto_id: int,
    session:    Session = Depends(pegar_sessao),
    _: Usuario          = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    nome = produto.nome
    session.delete(produto)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Não é possível remover '{nome}' — possui vínculos ativos.",
        )
    return {"mensagem": f"Produto '{nome}' removido"}


# ══════════════════════════════════════════════════════════════════
# VARIAÇÕES
# ══════════════════════════════════════════════════════════════════

@product_router.get(
    "/produtos/{produto_id}/variacoes",
    response_model=List[ResponseVariacaoSchema],
    summary="Lista variações do produto (público)",
)
async def listar_variacoes(
    produto_id: int,
    session:    Session = Depends(pegar_sessao),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return session.query(VariacaoProduto).filter(
        VariacaoProduto.produto_id == produto_id
    ).all()


@product_router.post(
    "/produtos/{produto_id}/variacoes",
    response_model=ResponseVariacaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria variação para produto (admin)",
)
async def criar_variacao(
    produto_id: int,
    dados:   VariacaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    variacao = VariacaoProduto(
        nome       = dados.nome.strip(),
        descricao  = dados.descricao,
        acrescimo  = dados.acrescimo,
        disponivel = dados.disponivel if dados.disponivel is not None else True,
        produto_id = produto_id,
    )
    session.add(variacao)
    try:
        session.commit()
        session.refresh(variacao)
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao criar variação: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Erro ao criar variação")
    return variacao


@product_router.put(
    "/produtos/{produto_id}/variacoes/{variacao_id}",
    response_model=ResponseVariacaoSchema,
    summary="Atualiza variação (admin)",
)
async def atualizar_variacao(
    produto_id:  int,
    variacao_id: int,
    dados:   VariacaoSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    variacao = session.query(VariacaoProduto).filter(
        VariacaoProduto.id         == variacao_id,
        VariacaoProduto.produto_id == produto_id,
    ).first()
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")

    variacao.nome      = dados.nome.strip()
    variacao.descricao = dados.descricao
    variacao.acrescimo = dados.acrescimo
    if dados.disponivel is not None:
        variacao.disponivel = dados.disponivel

    session.commit()
    session.refresh(variacao)
    return variacao


@product_router.delete(
    "/produtos/{produto_id}/variacoes/{variacao_id}",
    summary="Remove variação (admin)",
)
async def deletar_variacao(
    produto_id:  int,
    variacao_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    variacao = session.query(VariacaoProduto).filter(
        VariacaoProduto.id         == variacao_id,
        VariacaoProduto.produto_id == produto_id,
    ).first()
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")
    session.delete(variacao)
    session.commit()
    return {"mensagem": f"Variação '{variacao.nome}' removida"}


# ══════════════════════════════════════════════════════════════════
# ADICIONAIS GLOBAIS — CRUD
# Sem vínculo a produto aqui — são globais e reutilizáveis.
# ══════════════════════════════════════════════════════════════════

@product_router.get(
    "/adicionais",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista todos os adicionais globais (público)",
)
async def listar_adicionais(
    apenas_ativos: bool    = True,
    session: Session       = Depends(pegar_sessao),
):
    q = session.query(Adicional)
    if apenas_ativos:
        q = q.filter(Adicional.ativo == True)
    return q.order_by(Adicional.nome).all()


@product_router.get(
    "/adicionais/{adicional_id}",
    response_model=ResponseAdicionalSchema,
    summary="Busca adicional por ID (público)",
)
async def buscar_adicional(
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
):
    a = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")
    return a


@product_router.post(
    "/adicionais",
    response_model=ResponseAdicionalSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria adicional global (admin)",
)
async def criar_adicional(
    dados:   AdicionalSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    existe = session.query(Adicional).filter(Adicional.nome == dados.nome.strip()).first()
    if existe:
        raise HTTPException(
            status_code=400,
            detail=f"Adicional '{dados.nome}' já existe (id={existe.id})",
        )
    adicional = Adicional(
        nome       = dados.nome.strip(),
        descricao  = dados.descricao,
        preco      = dados.preco,
        ativo      = dados.ativo if dados.ativo is not None else True,
        limite_qtd = dados.limite_qtd,
    )
    session.add(adicional)
    try:
        session.commit()
        session.refresh(adicional)
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao criar adicional: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Erro ao criar adicional")
    log.info("[product] Adicional criado id=%s nome=%s", adicional.id, adicional.nome)
    return adicional


@product_router.put(
    "/adicionais/{adicional_id}",
    response_model=ResponseAdicionalSchema,
    summary="Atualiza adicional (admin)",
)
async def atualizar_adicional(
    adicional_id: int,
    dados:   AdicionalSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    # Checar conflito de nome
    conflito = session.query(Adicional).filter(
        Adicional.nome == dados.nome.strip(),
        Adicional.id   != adicional_id,
    ).first()
    if conflito:
        raise HTTPException(
            status_code=400,
            detail=f"Nome '{dados.nome}' já usado por outro adicional (id={conflito.id})",
        )

    adicional.nome       = dados.nome.strip()
    adicional.descricao  = dados.descricao
    adicional.preco      = dados.preco
    adicional.limite_qtd = dados.limite_qtd
    if dados.ativo is not None:
        adicional.ativo = dados.ativo

    try:
        session.commit()
        session.refresh(adicional)
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao atualizar adicional %s: %s", adicional_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao atualizar adicional")
    return adicional


@product_router.patch(
    "/adicionais/{adicional_id}/ativar",
    response_model=ResponseAdicionalSchema,
    summary="Ativa/desativa adicional (admin)",
)
async def toggle_adicional(
    adicional_id: int,
    ativo:   bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")
    adicional.ativo = ativo
    session.commit()
    session.refresh(adicional)
    return adicional


@product_router.delete(
    "/adicionais/{adicional_id}",
    summary="Remove adicional (admin)",
)
async def deletar_adicional(
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")
    nome = adicional.nome
    session.delete(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao deletar adicional %s: %s", adicional_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao remover adicional")
    return {"mensagem": f"Adicional '{nome}' removido"}


# ══════════════════════════════════════════════════════════════════
# VÍNCULOS PRODUTO ↔ ADICIONAL  (N:N via produto_adicional)
# ══════════════════════════════════════════════════════════════════

@product_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista adicionais disponíveis para um produto (público)",
)
async def listar_adicionais_produto(
    produto_id:    int,
    apenas_ativos: bool    = True,
    session: Session       = Depends(pegar_sessao),
):
    produto = session.query(Produto).options(
        joinedload(Produto.adicionais)
    ).filter(Produto.id == produto_id).first()

    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicionais = produto.adicionais
    if apenas_ativos:
        adicionais = [a for a in adicionais if a.ativo]
    return adicionais


@product_router.post(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    status_code=status.HTTP_201_CREATED,
    summary="Vincula adicional ao produto (admin)",
)
async def vincular_adicional(
    produto_id:   int,
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    produto = session.query(Produto).options(
        joinedload(Produto.adicionais)
    ).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    if adicional in produto.adicionais:
        raise HTTPException(
            status_code=400,
            detail=f"Adicional '{adicional.nome}' já está vinculado a '{produto.nome}'",
        )

    produto.adicionais.append(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao vincular adicional: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao vincular adicional")

    log.info("[product] Adicional #%s vinculado ao produto #%s", adicional_id, produto_id)
    return {
        "mensagem":     f"Adicional '{adicional.nome}' vinculado a '{produto.nome}'",
        "produto_id":   produto_id,
        "adicional_id": adicional_id,
    }


@product_router.delete(
    "/produtos/{produto_id}/adicionais/{adicional_id}",
    summary="Remove vínculo adicional ↔ produto (admin)",
)
async def desvincular_adicional(
    produto_id:   int,
    adicional_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario       = Depends(verificar_admin),
):
    produto = session.query(Produto).options(
        joinedload(Produto.adicionais)
    ).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    adicional = session.query(Adicional).filter(Adicional.id == adicional_id).first()
    if not adicional:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")

    if adicional not in produto.adicionais:
        raise HTTPException(
            status_code=400,
            detail=f"Adicional '{adicional.nome}' não está vinculado a '{produto.nome}'",
        )

    produto.adicionais.remove(adicional)
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        log.error("[product] Erro ao desvincular adicional: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Erro ao desvincular adicional")

    return {
        "mensagem":     f"Adicional '{adicional.nome}' desvinculado de '{produto.nome}'",
        "produto_id":   produto_id,
        "adicional_id": adicional_id,
    }
