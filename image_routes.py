"""
image_routes.py — corrigido
============================
Removido o endpoint PUT /Pedidos/categorias/reordenar daqui.
Ele foi movido para order_routes.py (onde o prefixo /Pedidos já existe),
eliminando o conflito de rota que causava o erro 422.

Rotas deste arquivo:
  POST /Pedidos/categorias/{categoria_id}/upload-imagem
  POST /Produto/produtos/{produto_id}/upload-imagem
"""

import os
import logging

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from dependencias import pegar_sessao, verificar_admin
from models import Categoria, Produto, Usuario
from schemas import ResponseUploadImagemSchema

logger = logging.getLogger("image_routes")

_CLOUD_NAME  = os.getenv("CLOUD_NAME",  "").strip()
_API_KEY     = os.getenv("API_KEY",     "").strip()
_API_SECRET  = os.getenv("API_SECRET",  "").strip()

if not all([_CLOUD_NAME, _API_KEY, _API_SECRET]):
    logger.warning(
        "Cloudinary nao configurado - defina CLOUD_NAME, API_KEY e API_SECRET no .env. "
        "As rotas de upload estarao desabilitadas ate isso ser feito."
    )
else:
    cloudinary.config(
        cloud_name = _CLOUD_NAME,
        api_key    = _API_KEY,
        api_secret = _API_SECRET,
        secure     = True,
    )
    logger.info("Cloudinary configurado - cloud: %s", _CLOUD_NAME)


_TIPOS_PERMITIDOS     = {"image/jpeg", "image/png", "image/webp", "image/jpg"}
_EXTENSOES_PERMITIDAS = {".jpg", ".jpeg", ".png", ".webp"}
_TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024


def upload_imagem_cloudinary(file: UploadFile, pasta: str = "hamburgueria") -> str:
    if not all([_CLOUD_NAME, _API_KEY, _API_SECRET]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servico de upload indisponivel. Configure CLOUD_NAME, API_KEY e API_SECRET no servidor.",
        )

    content_type = (file.content_type or "").lower()
    if content_type not in _TIPOS_PERMITIDOS:
        extensao = os.path.splitext(file.filename or "")[1].lower()
        if extensao not in _EXTENSOES_PERMITIDAS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo de arquivo nao permitido: '{file.content_type}'. Envie JPG, PNG ou WEBP.",
            )

    try:
        conteudo = file.file.read()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Nao foi possivel ler o arquivo: {exc}")
    finally:
        file.file.seek(0)

    if len(conteudo) > _TAMANHO_MAXIMO_BYTES:
        tamanho_mb = len(conteudo) / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Imagem muito grande: {tamanho_mb:.1f} MB. Maximo: 5 MB.",
        )

    try:
        resultado = cloudinary.uploader.upload(
            conteudo,
            folder         = pasta,
            resource_type  = "image",
            overwrite      = True,
            transformation = [{"quality": "auto", "fetch_format": "auto"}],
        )
        url = resultado.get("secure_url", "")
        if not url:
            raise ValueError("Cloudinary nao retornou URL valida.")
        logger.info("Upload OK - public_id=%s | url=%s", resultado.get("public_id"), url)
        return url
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Erro no upload: %s", exc, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Falha no upload: {exc}")


# ══════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════
image_router = APIRouter(tags=["Upload de Imagens"])


@image_router.post(
    "/Pedidos/categorias/{categoria_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Upload de imagem para uma categoria (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_categoria(
    categoria_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP - max. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    categoria = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail=f"Categoria id={categoria_id} nao encontrada.")

    url = upload_imagem_cloudinary(file, pasta="hamburgueria/categorias")
    categoria.imagem_url = url
    try:
        session.commit()
        session.refresh(categoria)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=500, detail="Upload OK, mas falhou ao salvar no banco.")

    logger.info("Imagem salva - categoria id=%s | url=%s", categoria_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem da categoria '{categoria.nome}' atualizada com sucesso.",
        imagem_url = url,
    )


@image_router.post(
    "/Produto/produtos/{produto_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
    summary="Upload de imagem para um produto (somente admin)",
    status_code=status.HTTP_200_OK,
)
async def upload_imagem_produto(
    produto_id: int,
    file:    UploadFile = File(..., description="Imagem JPG, PNG ou WEBP - max. 5 MB"),
    session: Session    = Depends(pegar_sessao),
    _:       Usuario    = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail=f"Produto id={produto_id} nao encontrado.")

    url = upload_imagem_cloudinary(file, pasta="hamburgueria/produtos")
    produto.imagem_url = url
    try:
        session.commit()
        session.refresh(produto)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=500, detail="Upload OK, mas falhou ao salvar no banco.")

    logger.info("Imagem salva - produto id=%s | url=%s", produto_id, url)
    return ResponseUploadImagemSchema(
        mensagem   = f"Imagem do produto '{produto.nome}' atualizada com sucesso.",
        imagem_url = url,
    )
