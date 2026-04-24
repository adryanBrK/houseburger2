"""
image_routes.py corrigido
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
        secure     = True,
    )
    logger.info("Cloudinary configurado — cloud: %s", _CLOUD_NAME)


_TIPOS_PERMITIDOS     = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
_EXTENSOES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
_TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024


def upload_imagem_cloudinary(file: UploadFile, pasta: str = "hamburgueria") -> str:
    if not all([_CLOUD_NAME, _API_KEY, _API_SECRET]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de upload indisponível. Configure CLOUD_NAME, API_KEY e API_SECRET no servidor.",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in _TIPOS_PERMITIDOS:
        extensao = os.path.splitext(file.filename or "")[1].lower()
        if extensao not in _EXTENSOES_PERMITIDAS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de arquivo não permitido: '{file.content_type}'. Envie JPG, PNG ou WEBP.",
            )

    try:
        conteudo = file.file.read()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Não foi possível ler o arquivo: {exc}")
    finally:
        file.file.seek(0)

    if len(conteudo) > _TAMANHO_MAXIMO_BYTES:
        tamanho_mb = len(conteudo) / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Imagem muito grande: {tamanho_mb:.1f} MB. Máximo: 5 MB.",
        )

    try:
        resultado = cloudinary.uploader.upload(
            conteudo,
            folder         = pasta,
            resource_type  = "image",
            overwrite       = True,
            transformation = [{"quality": "auto", "fetch_format": "auto"}],
        )
        url = resultado.get("secure_url", "")
        if not url:
            raise ValueError("Cloudinary não retornou URL válida.")
        logger.info("Upload OK — public_id=%s | url=%s", resultado.get("public_id"), url)
        return url
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro no upload: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha no upload: {exc}")


# ══════════════════════════════════════════════════════════════════
# ROUTER — sem prefixo; os paths já incluem o prefixo correto
# ══════════════════════════════════════════════════════════════════
image_router = APIRouter(tags=["Upload de Imagens"])


# ─── UPLOAD CATEGORIA ────────────────────────────────────────────
# Path alinhado com order_router (prefixo /Pedidos):
#   POST /Pedidos/categorias/{categoria_id}/upload-imagem
@image_router.post(
    "/Pedidos/categorias/{categoria_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Upload de imagem para uma categoria (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_categoria(
    categoria_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP — máx. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    categoria = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Categoria id={categoria_id} não encontrada.")

    url = upload_imagem_cloudinary(file, pasta="hamburgueria/categorias")

    categoria.imagem_url = url
    try:
        session.commit()
        session.refresh(categoria)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload OK, mas falhou ao salvar no banco.")

    logger.info("Imagem salva — categoria id=%s | url=%s", categoria_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem da categoria '{categoria.nome}' atualizada com sucesso.",
        imagem_url = url,
    )


# ─── UPLOAD PRODUTO ──────────────────────────────────────────────
# Path alinhado com product_router (prefixo /Produto):
#   POST /Produto/produtos/{produto_id}/upload-imagem
@image_router.post(
    "/Produto/produtos/{produto_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Upload de imagem para um produto (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_produto(
    produto_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP — máx. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Produto id={produto_id} não encontrado.")

    url = upload_imagem_cloudinary(file, pasta="hamburgueria/produtos")

    produto.imagem_url = url
    try:
        session.commit()
        session.refresh(produto)
    except Exception as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload OK, mas falhou ao salvar no banco.")

    logger.info("Imagem salva — produto id=%s | url=%s", produto_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem do produto '{produto.nome}' atualizada com sucesso.",
        imagem_url = url,
    )


# ─── REORDENAÇÃO DE CATEGORIAS ────────────────────────────────────
# Path alinhado com order_router (prefixo /Pedidos):
#   PUT /Pedidos/categorias/reordenar
@image_router.put(
    "/Pedidos/categorias/reordenar",
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
    Recebe lista de IDs na nova ordem. Ex: { "ids": [3, 1, 2, 5] }
    IDs inexistentes são ignorados silenciosamente.
    """
    if not dados.ids:
        return session.query(Categoria).order_by(Categoria.ordem).all()

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

    return session.query(Categoria).order_by(Categoria.ordem).all()
