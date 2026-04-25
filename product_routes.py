from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional

from dependencias import pegar_sessao, verificar_token, verificar_admin
from schemas import (
    ProdutoSchema, ResponseProdutoSchema, ResponseProdutoDetalhadoSchema,
    VariacaoSchema, ResponseVariacaoSchema, ResponseAdicionalSchema
)
from models import Produto, Categoria, Porcao, VariacaoProduto, Usuario, Adicional

product_router = APIRouter(prefix="/Produto", tags=["Produtos"])


def _get_produto(produto_id: int, session: Session) -> Produto:
    """Helper para buscar produto ou retornar 404"""
    p = session.query(Produto).filter(Produto.id == produto_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return p


# ============================================================
# PRODUTOS — CRUD
# ============================================================

@product_router.get(
    "/produtos",
    response_model=List[ResponseProdutoDetalhadoSchema],
    summary="Lista todos os produtos (com filtros opcionais)"
)
async def listar_produtos(
    categoria_id: Optional[int]  = None,
    disponivel:   Optional[bool] = None,
    session:      Session        = Depends(pegar_sessao),
):
    """
    Lista produtos com filtros opcionais:
    - categoria_id: filtra por categoria
    - disponivel: filtra por disponibilidade (true/false)
    """
    q = session.query(Produto)
    if categoria_id is not None:
        q = q.filter(Produto.categoria_id == categoria_id)
    if disponivel is not None:
        q = q.filter(Produto.disponivel == disponivel)
    return q.all()


@product_router.post(
    "/produtos",
    response_model=ResponseProdutoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cria produto (somente admin). Para imagens, use URL externa (Cloudinary, ImgBB, etc.)"
)
async def criar_produto(
    dados:   ProdutoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """
    Cria um novo produto. 
    
    IMPORTANTE:
    - categoria_id é obrigatório
    - porcao_id é opcional (None se não tiver porção)
    - Para imagens, use imagem_url com link externo (ex: Cloudinary, ImgBB)
    - A Vercel não permite salvar arquivos localmente
    """
    # Categoria é obrigatória
    if not session.query(Categoria).filter(Categoria.id == dados.categoria_id).first():
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    # Porção é OPCIONAL — só valida se o admin enviou porcao_id
    if dados.porcao_id is not None:
        if not session.query(Porcao).filter(Porcao.id == dados.porcao_id).first():
            raise HTTPException(status_code=404, detail="Porção não encontrada")

    produto = Produto(
        nome=dados.nome,
        descricao=dados.descricao,
        preco=dados.preco,
        categoria_id=dados.categoria_id,
        porcao_id=dados.porcao_id,
        imagem_url=dados.imagem_url,  # URL externa
        disponivel=dados.disponivel if dados.disponivel is not None else True,
    )
    session.add(produto)
    try:
        session.commit()
        session.refresh(produto)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=400, detail="Já existe um produto com esse nome")
    return produto


@product_router.get(
    "/produtos/{produto_id}",
    response_model=ResponseProdutoDetalhadoSchema,
    summary="Busca um produto pelo ID"
)
async def buscar_produto(produto_id: int, session: Session = Depends(pegar_sessao)):
    """Retorna detalhes completos de um produto incluindo categoria, porção e variações"""
    return _get_produto(produto_id, session)


@product_router.put(
    "/produtos/{produto_id}",
    response_model=ResponseProdutoSchema,
    summary="Edita um produto (somente admin)"
)
async def editar_produto(
    produto_id: int,
    dados:   ProdutoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """
    Atualiza um produto existente.
    Pode atualizar todos os campos incluindo a imagem_url.
    """
    produto = _get_produto(produto_id, session)

    # Valida categoria
    if not session.query(Categoria).filter(Categoria.id == dados.categoria_id).first():
        raise HTTPException(status_code=404, detail="Categoria não encontrada")
    produto.categoria_id = dados.categoria_id

    # Porção: se enviou None, remove; se enviou um id, valida e atualiza
    if dados.porcao_id is not None:
        if not session.query(Porcao).filter(Porcao.id == dados.porcao_id).first():
            raise HTTPException(status_code=404, detail="Porção não encontrada")
    produto.porcao_id = dados.porcao_id

    produto.nome       = dados.nome
    produto.descricao  = dados.descricao
    produto.preco      = dados.preco
    produto.imagem_url = dados.imagem_url
    
    if dados.disponivel is not None:
        produto.disponivel = dados.disponivel

    session.commit()
    session.refresh(produto)
    return produto


@product_router.patch(
    "/produtos/{produto_id}/disponibilidade",
    summary="Ativa ou desativa um produto (somente admin)"
)
async def alterar_disponibilidade(
    produto_id: int,
    disponivel: bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    """Altera apenas a disponibilidade do produto sem modificar outros campos"""
    produto = _get_produto(produto_id, session)
    produto.disponivel = disponivel
    session.commit()
    return {
        "mensagem": f"Produto '{produto.nome}' marcado como {'disponível' if disponivel else 'indisponível'}"
    }


@product_router.delete(
    "/produtos/deletar/{produto_id}",
    summary="Remove um produto (somente admin)"
)
async def deletar_produto(
    produto_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    """
    Remove um produto do sistema.
    Falha se o produto estiver vinculado a pedidos existentes.
    """
    produto = _get_produto(produto_id, session)
    session.delete(produto)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Não é possível deletar produto vinculado a pedidos"
        )
    return {"mensagem": f"Produto '{produto.nome}' removido com sucesso"}


# ============================================================
# VARIAÇÕES DE PRODUTO
# Rota: /Produto/produtos/{produto_id}/variacoes
#
# Use para cadastrar: House Simples, House Pro, House Pro Max
# Cada variação tem um acréscimo sobre o preço base do produto.
# ============================================================

@product_router.get(
    "/produtos/{produto_id}/variacoes",
    response_model=List[ResponseVariacaoSchema],
    summary="Lista todas as variações de um produto"
)
async def listar_variacoes(produto_id: int, session: Session = Depends(pegar_sessao)):
    """Retorna todas as variações cadastradas para um produto"""
    _get_produto(produto_id, session)
    return session.query(VariacaoProduto).filter(
        VariacaoProduto.produto_id == produto_id
    ).all()


@product_router.post(
    "/produtos/{produto_id}/variacoes",
    response_model=ResponseVariacaoSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona uma variação ao produto (somente admin)"
)
async def criar_variacao(
    produto_id: int,
    dados:   VariacaoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """
    Cria uma nova variação para o produto.
    Ex: House Pro com acréscimo de R$ 5,00
    """
    produto = _get_produto(produto_id, session)
    variacao = VariacaoProduto(
        nome=dados.nome,
        descricao=dados.descricao,
        acrescimo=dados.acrescimo,
        disponivel=dados.disponivel if dados.disponivel is not None else True,
        produto_id=produto.id,
    )
    session.add(variacao)
    session.commit()
    session.refresh(variacao)
    return variacao


@product_router.put(
    "/produtos/{produto_id}/variacoes/{variacao_id}",
    response_model=ResponseVariacaoSchema,
    summary="Edita uma variação (somente admin)"
)
async def editar_variacao(
    produto_id:  int,
    variacao_id: int,
    dados:   VariacaoSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """Atualiza os dados de uma variação existente"""
    _get_produto(produto_id, session)
    variacao = session.query(VariacaoProduto).filter(
        VariacaoProduto.id == variacao_id,
        VariacaoProduto.produto_id == produto_id,
    ).first()
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")

    variacao.nome      = dados.nome
    variacao.descricao = dados.descricao
    variacao.acrescimo = dados.acrescimo
    if dados.disponivel is not None:
        variacao.disponivel = dados.disponivel

    session.commit()
    session.refresh(variacao)
    return variacao


@product_router.patch(
    "/produtos/{produto_id}/variacoes/{variacao_id}/disponibilidade",
    summary="Ativa ou desativa uma variação (somente admin)"
)
async def alterar_disponibilidade_variacao(
    produto_id:  int,
    variacao_id: int,
    disponivel:  bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    """Altera apenas a disponibilidade da variação"""
    _get_produto(produto_id, session)
    variacao = session.query(VariacaoProduto).filter(
        VariacaoProduto.id == variacao_id,
        VariacaoProduto.produto_id == produto_id,
    ).first()
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")
    
    variacao.disponivel = disponivel
    session.commit()
    return {
        "mensagem": f"Variação '{variacao.nome}' marcada como {'disponível' if disponivel else 'indisponível'}"
    }


@product_router.delete(
    "/produtos/{produto_id}/variacoes/{variacao_id}",
    summary="Remove uma variação (somente admin)"
)
async def deletar_variacao(
    produto_id:  int,
    variacao_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    """Remove uma variação do produto"""
    _get_produto(produto_id, session)
    variacao = session.query(VariacaoProduto).filter(
        VariacaoProduto.id == variacao_id,
        VariacaoProduto.produto_id == produto_id,
    ).first()
    if not variacao:
        raise HTTPException(status_code=404, detail="Variação não encontrada")
    
    session.delete(variacao)
    session.commit()
    return {"mensagem": f"Variação '{variacao.nome}' removida com sucesso"}

# ============================================================
# ADICIONAIS DO PRODUTO
# Rota: /Produto/produtos/{produto_id}/adicionais
# ============================================================

@product_router.get(
    "/produtos/{produto_id}/adicionais",
    response_model=List[ResponseAdicionalSchema],
    summary="Lista adicionais de um produto"
)
async def listar_adicionais_produto(
    produto_id: int,
    session: Session = Depends(pegar_sessao),
):
    """
    Retorna todos os adicionais vinculados ao produto.
    """
    _get_produto(produto_id, session)

    adicionais = session.query(Adicional).filter(
        Adicional.produto_id == produto_id,
        Adicional.ativo == True
    ).all()

    return adicionais
