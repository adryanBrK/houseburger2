from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from dependencias import pegar_sessao, verificar_admin
from schemas import ImpressoraSchema, ResponseImpressoraSchema
from models import Impressora, Usuario

impressora_router = APIRouter(prefix="/Impressoras", tags=["Impressoras"])


@impressora_router.get("/", response_model=List[ResponseImpressoraSchema], summary="Lista impressoras")
async def listar_impressoras(
    apenas_ativas: bool = True,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Lista todas as impressoras cadastradas"""
    q = session.query(Impressora)
    if apenas_ativas:
        q = q.filter(Impressora.ativo == True)
    return q.order_by(Impressora.finalidade, Impressora.nome).all()


@impressora_router.post(
    "/",
    response_model=ResponseImpressoraSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra impressora (admin)"
)
async def criar_impressora(
    dados: ImpressoraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """
    Cadastra uma nova impressora térmica
    
    Para REDE: informar ip_address e porta (ex: 9100)
    Para USB: informar usb_vendor e usb_product (IDs hexadecimais)
    """
    # Validar campos obrigatórios
    if dados.tipo == "REDE":
        if not dados.ip_address or not dados.porta:
            raise HTTPException(
                status_code=400,
                detail="Impressora de REDE precisa de ip_address e porta"
            )
    elif dados.tipo == "USB":
        if not dados.usb_vendor or not dados.usb_product:
            raise HTTPException(
                status_code=400,
                detail="Impressora USB precisa de usb_vendor e usb_product"
            )
    
    impressora = Impressora(
        nome=dados.nome,
        tipo=dados.tipo.upper(),
        finalidade=dados.finalidade.upper(),
        ip_address=dados.ip_address,
        porta=dados.porta,
        usb_vendor=dados.usb_vendor,
        usb_product=dados.usb_product,
        ativo=dados.ativo if dados.ativo is not None else True
    )
    
    session.add(impressora)
    session.commit()
    session.refresh(impressora)
    return impressora


@impressora_router.put("/{impressora_id}", response_model=ResponseImpressoraSchema, summary="Atualiza impressora (admin)")
async def atualizar_impressora(
    impressora_id: int,
    dados: ImpressoraSchema,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Atualiza dados de uma impressora"""
    impressora = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not impressora:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    
    # Validar campos
    if dados.tipo == "REDE" and (not dados.ip_address or not dados.porta):
        raise HTTPException(status_code=400, detail="Impressora de REDE precisa de IP e porta")
    if dados.tipo == "USB" and (not dados.usb_vendor or not dados.usb_product):
        raise HTTPException(status_code=400, detail="Impressora USB precisa de vendor e product")
    
    impressora.nome = dados.nome
    impressora.tipo = dados.tipo.upper()
    impressora.finalidade = dados.finalidade.upper()
    impressora.ip_address = dados.ip_address
    impressora.porta = dados.porta
    impressora.usb_vendor = dados.usb_vendor
    impressora.usb_product = dados.usb_product
    
    if dados.ativo is not None:
        impressora.ativo = dados.ativo
    
    session.commit()
    session.refresh(impressora)
    return impressora


@impressora_router.delete("/{impressora_id}", summary="Remove impressora (admin)")
async def deletar_impressora(
    impressora_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Remove uma impressora"""
    impressora = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not impressora:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    
    session.delete(impressora)
    session.commit()
    
    return {"mensagem": f"Impressora '{impressora.nome}' removida com sucesso"}


@impressora_router.patch("/{impressora_id}/ativar", summary="Ativa/desativa impressora (admin)")
async def toggle_impressora(
    impressora_id: int,
    ativo: bool,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Ativa ou desativa uma impressora"""
    impressora = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not impressora:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    
    impressora.ativo = ativo
    session.commit()
    
    return {"mensagem": f"Impressora '{impressora.nome}' {'ativada' if ativo else 'desativada'}"}


@impressora_router.post("/{impressora_id}/testar", summary="Testa impressora (admin)")
async def testar_impressora(
    impressora_id: int,
    session: Session = Depends(pegar_sessao),
    _: Usuario = Depends(verificar_admin)
):
    """Envia uma página de teste para a impressora"""
    from print_service import PrintService, ESC
    
    impressora = session.query(Impressora).filter(Impressora.id == impressora_id).first()
    if not impressora:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    
    # Gerar página de teste
    teste = ESC.INIT
    teste += ESC.ALIGN_CENTER + ESC.SIZE_DOUBLE + ESC.BOLD_ON
    teste += b"TESTE\n"
    teste += ESC.BOLD_OFF + ESC.SIZE_NORMAL
    teste += b"\n"
    teste += f"Impressora: {impressora.nome}\n".encode('cp860')
    teste += f"Tipo: {impressora.tipo}\n".encode('cp860')
    teste += f"Finalidade: {impressora.finalidade}\n".encode('cp860')
    teste += b"\n" * 3
    teste += ESC.CUT
    
    # Enviar
    if impressora.tipo == "REDE":
        sucesso, erro = PrintService.enviar_para_impressora_rede(
            impressora.ip_address,
            impressora.porta,
            teste
        )
    else:
        sucesso, erro = PrintService.enviar_para_impressora_usb(
            impressora.usb_vendor,
            impressora.usb_product,
            teste
        )
    
    if not sucesso:
        raise HTTPException(status_code=500, detail=f"Erro ao imprimir: {erro}")
    
    return {"mensagem": "Página de teste enviada com sucesso"}
