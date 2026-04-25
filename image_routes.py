"""
image_routes.py corrigido
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
    finally:
        file.file.seek(0)

    if len(conteudo) > _TAMANHO_MAXIMO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Imagem muito grande. Máximo: 5 MB.",
        )

    try:
        resultado = cloudinary.uploader.upload(
            conteudo,
            folder="hamburgueria",
            resource_type="image",
            transformation=[{"quality": "auto", "fetch_format": "auto"}],
        )
        return resultado.get("secure_url")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha no upload: {exc}")


image_router = APIRouter(tags=["Upload de Imagens"])


@image_router.post(
    "/Pedidos/categorias/{categoria_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
)
async def upload_imagem_categoria(
    categoria_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    categoria = session.query(Categoria).filter(Categoria.id == categoria_id).first()
    if not categoria:
        raise HTTPException(status_code=404, detail="Categoria não encontrada")

    url = upload_imagem_cloudinary(file, "hamburgueria/categorias")
    categoria.imagem_url = url
    session.commit()

    return {"mensagem": "Imagem atualizada", "imagem_url": url}


@image_router.post(
    "/Produto/produtos/{produto_id}/upload-imagem",
    response_model=ResponseUploadImagemSchema,
)
async def upload_imagem_produto(
    produto_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin),
):
    produto = session.query(Produto).filter(Produto.id == produto_id).first()
    if not produto:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    url = upload_imagem_cloudinary(file, "hamburgueria/produtos")
    produto.imagem_url = url
    session.commit()

    return {"mensagem": "Imagem atualizada", "imagem_url": url}
