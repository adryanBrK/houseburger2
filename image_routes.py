"""
image_routes.py
===============
Módulo dedicado a:
  1. Configuração do Cloudinary via variáveis de ambiente
  2. Função reutilizável de upload de imagem
  3. Rotas de upload para Categoria e Produto
  4. Rota de reordenação de Categorias (drag-and-drop)

Registro no main.py:
    from image_routes import image_router
    app.include_router(image_router)

Dependências extras a instalar:
    pip install cloudinary python-multipart
"""

import os
import logging
from typing import List

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Categoria, Produto, Usuario
from schemas import (
    ResponseCategoriaSchema,
    ResponseUploadImagemSchema,
    ReordenarCategoriasSchema,
)

logger = logging.getLogger("image_routes")

# ══════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO CLOUDINARY
# Variáveis obrigatórias no .env:
#   CLOUD_NAME=seu_cloud_name
#   API_KEY=sua_api_key
#   API_SECRET=seu_api_secret
# ══════════════════════════════════════════════════════════════════
_CLOUD_NAME  = os.getenv("CLOUD_NAME",  "").strip()
_API_KEY     = os.getenv("API_KEY",     "").strip()
_API_SECRET  = os.getenv("API_SECRET",  "").strip()

if not all([_CLOUD_NAME, _API_KEY, _API_SECRET]):
    logger.warning(
        "⚠️  Cloudinary não configurado — defina CLOUD_NAME, API_KEY e API_SECRET no .env. "
        "As rotas de upload estarão desabilitadas até isso ser feito."
    )
else:
    cloudinary.config(
        cloud_name = _CLOUD_NAME,
        api_key    = _API_KEY,
        api_secret = _API_SECRET,
        secure     = True,   # sempre retorna URLs https://
    )
    logger.info("Cloudinary configurado com sucesso — cloud: %s", _CLOUD_NAME)


# ══════════════════════════════════════════════════════════════════
# FUNÇÃO REUTILIZÁVEL DE UPLOAD
# ══════════════════════════════════════════════════════════════════

# Tipos de arquivo aceitos
_TIPOS_PERMITIDOS = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
# Extensões aceitas (fallback quando content_type não é confiável)
_EXTENSOES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
# Limite de tamanho: 5 MB
_TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024


def upload_imagem_cloudinary(file: UploadFile, pasta: str = "hamburgueria") -> str:
    """
    Valida e faz upload de uma imagem para o Cloudinary.

    Parâmetros:
        file   — UploadFile recebido pela rota FastAPI
        pasta  — subpasta no Cloudinary onde a imagem será armazenada

    Retorna:
        URL segura (https) da imagem hospedada no Cloudinary.

    Lança:
        HTTPException 400 — arquivo inválido ou muito grande
        HTTPException 500 — falha no upload
        HTTPException 503 — Cloudinary não configurado
    """
    # 1. Verificar se Cloudinary está configurado
    if not all([_CLOUD_NAME, _API_KEY, _API_SECRET]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Serviço de upload indisponível. "
                "Configure CLOUD_NAME, API_KEY e API_SECRET no servidor."
            ),
        )

    # 2. Validar tipo pelo content_type
    content_type = (file.content_type or "").lower()
    if content_type not in _TIPOS_PERMITIDOS:
        # Fallback: validar pela extensão do nome do arquivo
        extensao = os.path.splitext(file.filename or "")[1].lower()
        if extensao not in _EXTENSOES_PERMITIDAS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Tipo de arquivo não permitido: '{file.content_type}'. "
                    "Envie uma imagem JPG, JPEG, PNG ou WEBP."
                ),
            )

    # 3. Ler conteúdo e validar tamanho
    try:
        conteudo = file.file.read()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Não foi possível ler o arquivo: {exc}",
        )
    finally:
        file.file.seek(0)  # reset para eventual reuso

    if len(conteudo) > _TAMANHO_MAXIMO_BYTES:
        tamanho_mb = len(conteudo) / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Imagem muito grande: {tamanho_mb:.1f} MB. Máximo permitido: 5 MB.",
        )

    # 4. Fazer upload para o Cloudinary
    try:
        resultado = cloudinary.uploader.upload(
            conteudo,
            folder          = pasta,
            resource_type   = "image",
            overwrite        = True,
            # Transformação automática para otimizar entrega
            transformation  = [{"quality": "auto", "fetch_format": "auto"}],
        )
        url = resultado.get("secure_url", "")
        if not url:
            raise ValueError("Cloudinary não retornou uma URL válida.")
        logger.info("Upload OK — public_id=%s | url=%s", resultado.get("public_id"), url)
        return url

    except HTTPException:
        raise  # re-lança erros já formatados
    except Exception as exc:
        logger.error("Erro no upload para Cloudinary: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha no upload da imagem: {exc}",
        )


# ══════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════
image_router = APIRouter(tags=["Upload de Imagens"])


# ──────────────────────────────────────────────────────────────────
# UPLOAD — CATEGORIA
# ──────────────────────────────────────────────────────────────────
@image_router.post(
    "/categorias/{categoria_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Faz upload de imagem para uma categoria (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_categoria(
    categoria_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP — máx. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    """
    Faz upload de uma imagem para o Cloudinary e salva a URL
    no campo `imagem_url` da categoria informada.
    """
    # 1. Buscar categoria
    categoria = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not categoria:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Categoria id={categoria_id} não encontrada.",
        )

    # 2. Upload
    url = upload_imagem_cloudinary(file, pasta="hamburgueria/categorias")

    # 3. Salvar no banco
    categoria.imagem_url = url
    try:
        session.commit()
        session.refresh(categoria)
    except Exception as exc:
        session.rollback()
        logger.error("Erro ao salvar imagem_url na categoria %s: %s", categoria_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload realizado, mas falhou ao salvar no banco de dados.",
        )

    logger.info("Imagem salva — categoria id=%s | url=%s", categoria_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem da categoria '{categoria.nome}' atualizada com sucesso.",
        imagem_url = url,
    )


# ──────────────────────────────────────────────────────────────────
# UPLOAD — PRODUTO
# ──────────────────────────────────────────────────────────────────
@image_router.post(
    "/produtos/{produto_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Faz upload de imagem para um produto (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_produto(
    produto_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP — máx. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    """
    Faz upload de uma imagem para o Cloudinary e salva a URL
    no campo `imagem_url` do produto informado.
    """
    # 1. Buscar produto
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Produto id={produto_id} não encontrado.",
        )

    # 2. Upload
    url = upload_imagem_cloudinary(file, pasta="hamburgueria/produtos")

    # 3. Salvar no banco
    produto.imagem_url = url
    try:
        session.commit()
        session.refresh(produto)
    except Exception as exc:
        session.rollback()
        logger.error("Erro ao salvar imagem_url no produto %s: %s", produto_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Upload realizado, mas falhou ao salvar no banco de dados.",
        )

    logger.info("Imagem salva — produto id=%s | url=%s", produto_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem do produto '{produto.nome}' atualizada com sucesso.",
        imagem_url = url,
    )


# ──────────────────────────────────────────────────────────────────
# REORDENAÇÃO DE CATEGORIAS
# ──────────────────────────────────────────────────────────────────
@image_router.put(
    "/categorias/reordenar",
    response_model=List[ResponseCategoriaSchema],
    summary="Reordena categorias por drag-and-drop (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def reordenar_categorias(
    dados:   ReordenarCategoriasSchema,
    session: Session = Depends(pegar_sessao),
    _:       Usuario = Depends(verificar_admin),
):
    """
    Recebe uma lista de IDs na nova ordem desejada.

    Exemplo de body:
        { "ids": [3, 1, 2, 5] }

    A categoria com id=3 recebe ordem=0, id=1 → ordem=1, etc.
    IDs inexistentes são silenciosamente ignorados.
    Retorna a lista completa de categorias já na nova ordem.
    """
    if not dados.ids:
        # Lista vazia — retorna categorias sem alterar nada
        return session.query(Categoria).order_by(Categoria.ordem).all()

    # Atualiza `ordem` de cada categoria de acordo com a posição na lista
    for posicao, categoria_id in enumerate(dados.ids):
        categoria = session.query(Categoria).filter(Categoria.id == categoria_id).first()
        if categoria is None:
            logger.warning("reordenar_categorias: id=%s não encontrado — ignorado", categoria_id)
            continue
        categoria.ordem = posicao

    try:
        session.commit()
        logger.info("Categorias reordenadas: %s", dados.ids)
    except Exception as exc:
        session.rollback()
        logger.error("Erro ao salvar nova ordem: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Falha ao salvar a nova ordem: {exc}",
        )

    # Retorna lista já ordenada
    return session.query(Categoria).order_by(Categoria.ordem).all()
