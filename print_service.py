"""
Service de Impressão para Comandas Térmicas
Suporta impressoras USB e REDE usando protocolo ESC/POS
"""

from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
import socket

from models import Pedido, Impressora, LogImpressao, ConfiguracaoLoja


# ==========================
# COMANDOS ESC/POS
# ==========================
class ESC:
    """Comandos ESC/POS para impressoras térmicas"""
    
    INIT       = b'\x1B\x40'          # Inicializar impressora
    CUT        = b'\x1D\x56\x00'      # Cortar papel
    ALIGN_LEFT = b'\x1B\x61\x00'      # Alinhar à esquerda
    ALIGN_CENTER = b'\x1B\x61\x01'    # Alinhar ao centro
    ALIGN_RIGHT = b'\x1B\x61\x02'     # Alinhar à direita
    BOLD_ON    = b'\x1B\x45\x01'      # Negrito ON
    BOLD_OFF   = b'\x1B\x45\x00'      # Negrito OFF
    SIZE_NORMAL = b'\x1D\x21\x00'     # Tamanho normal
    SIZE_DOUBLE = b'\x1D\x21\x11'     # Tamanho 2x (largura e altura)
    SIZE_WIDE   = b'\x1D\x21\x10'     # Largura 2x
    SIZE_TALL   = b'\x1D\x21\x01'     # Altura 2x
    FEED       = b'\x0A'              # Line feed
    FEED_REVERSE = b'\x1B\x65\x01'    # Feed reverso


# ==========================
# GERADOR DE COMANDAS
# ==========================
class ComandaGenerator:
    """Gera o texto formatado das comandas para impressão"""
    
    LARGURA = 48  # Largura em caracteres (impressora 80mm)
    
    @staticmethod
    def _linha(char="-"):
        """Linha separadora"""
        return (char * ComandaGenerator.LARGURA) + "\n"
    
    @staticmethod
    def _centralizar(texto: str) -> str:
        """Centraliza texto"""
        if len(texto) >= ComandaGenerator.LARGURA:
            return texto + "\n"
        espacos = (ComandaGenerator.LARGURA - len(texto)) // 2
        return (" " * espacos) + texto + "\n"
    
    @staticmethod
    def _duas_colunas(esq: str, dir: str, espacamento: int = 2) -> str:
        """Formata em duas colunas"""
        tam_esq = len(esq)
        tam_dir = len(dir)
        espacos = ComandaGenerator.LARGURA - tam_esq - tam_dir - espacamento
        
        if espacos < 0:
            return esq + "\n" + (" " * (ComandaGenerator.LARGURA - tam_dir)) + dir + "\n"
        
        return esq + (" " * espacos) + dir + "\n"
    
    @staticmethod
    def gerar_comanda_cozinha(pedido: Pedido, config: ConfiguracaoLoja) -> bytes:
        """
        Gera comanda para a COZINHA
        
        Contém APENAS:
        - Nome do cliente
        - Tipo: ENTREGA ou BALCÃO
        - Lista de produtos
        - Quantidade
        """
        cmd = ESC.INIT
        
        # Header
        cmd += ESC.ALIGN_CENTER + ESC.SIZE_DOUBLE + ESC.BOLD_ON
        cmd += "COZINHA\n".encode('cp860')
        cmd += ESC.BOLD_OFF + ESC.SIZE_NORMAL
        
        cmd += ESC.ALIGN_CENTER
        cmd += f"{config.nome_loja}\n".encode('cp860')
        cmd += ESC.ALIGN_LEFT
        
        cmd += ComandaGenerator._linha("=").encode('cp860')
        
        # Data e hora
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cmd += f"Data: {agora}\n".encode('cp860')
        cmd += f"Pedido: #{pedido.id:04d}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Cliente e tipo
        cmd += ESC.BOLD_ON
        cmd += f"Cliente: {pedido.nome_cliente}\n".encode('cp860')
        cmd += ESC.BOLD_OFF
        
        cmd += ESC.SIZE_WIDE + ESC.BOLD_ON
        tipo_texto = f"*** {pedido.tipo_pedido} ***"
        cmd += ComandaGenerator._centralizar(tipo_texto).encode('cp860')
        cmd += ESC.BOLD_OFF + ESC.SIZE_NORMAL
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Itens
        cmd += ESC.BOLD_ON
        cmd += "ITENS DO PEDIDO:\n".encode('cp860')
        cmd += ESC.BOLD_OFF
        cmd += ComandaGenerator._linha().encode('cp860')
        
        for item in pedido.itens:
            # Nome do produto
            nome_completo = item.nomedoproduto
            if item.variacao_nome:
                nome_completo += f" - {item.variacao_nome}"
            
            # Quantidade
            qtd_texto = f"{item.quantidade}x"
            
            cmd += ESC.BOLD_ON
            cmd += f"{qtd_texto} {nome_completo}\n".encode('cp860')
            cmd += ESC.BOLD_OFF
            
            # Observações do item
            if item.observacoes:
                cmd += f"   OBS: {item.observacoes}\n".encode('cp860')
            
            cmd += "\n".encode('cp860')
        
        # Observações gerais do pedido
        if pedido.observacoes:
            cmd += ComandaGenerator._linha().encode('cp860')
            cmd += ESC.BOLD_ON
            cmd += "OBSERVACOES GERAIS:\n".encode('cp860')
            cmd += ESC.BOLD_OFF
            cmd += f"{pedido.observacoes}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha("=").encode('cp860')
        cmd += "\n\n\n"
        
        # Cortar papel
        cmd += ESC.CUT
        
        return cmd
    
    @staticmethod
    def gerar_comanda_motoboy(pedido: Pedido, config: ConfiguracaoLoja) -> bytes:
        """
        Gera comanda para o MOTOBOY (somente se for ENTREGA)
        
        Contém:
        - Nome do cliente
        - Telefone
        - Endereço completo
        - Bairro
        - Valor da entrega
        - Lista de produtos
        - Valor total
        """
        cmd = ESC.INIT
        
        # Header
        cmd += ESC.ALIGN_CENTER + ESC.SIZE_DOUBLE + ESC.BOLD_ON
        cmd += "ENTREGA\n".encode('cp860')
        cmd += ESC.BOLD_OFF + ESC.SIZE_NORMAL
        
        cmd += ESC.ALIGN_CENTER
        cmd += f"{config.nome_loja}\n".encode('cp860')
        if config.telefone:
            cmd += f"{config.telefone}\n".encode('cp860')
        cmd += ESC.ALIGN_LEFT
        
        cmd += ComandaGenerator._linha("=").encode('cp860')
        
        # Data e hora
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        cmd += f"Data: {agora}\n".encode('cp860')
        cmd += f"Pedido: #{pedido.id:04d}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Dados do cliente
        cmd += ESC.BOLD_ON + ESC.SIZE_WIDE
        cmd += f"{pedido.nome_cliente}\n".encode('cp860')
        cmd += ESC.BOLD_OFF + ESC.SIZE_NORMAL
        
        if pedido.telefone:
            cmd += f"Tel: {pedido.telefone}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Endereço
        cmd += ESC.BOLD_ON
        cmd += "ENDERECO DE ENTREGA:\n".encode('cp860')
        cmd += ESC.BOLD_OFF
        
        if pedido.endereco:
            cmd += f"{pedido.endereco}\n".encode('cp860')
        
        if pedido.bairro:
            cmd += f"Bairro: {pedido.bairro.nome}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Itens
        cmd += ESC.BOLD_ON
        cmd += "ITENS:\n".encode('cp860')
        cmd += ESC.BOLD_OFF
        
        for item in pedido.itens:
            nome = item.nomedoproduto
            if item.variacao_nome:
                nome += f" - {item.variacao_nome}"
            
            qtd = f"{item.quantidade}x"
            valor = f"R$ {item.preco_unitario * item.quantidade:.2f}"
            
            # Linha do item
            cmd += ComandaGenerator._duas_colunas(
                f"{qtd} {nome}", 
                valor
            ).encode('cp860')
            
            if item.observacoes:
                cmd += f"   Obs: {item.observacoes}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Valores
        subtotal = pedido.preco_total - pedido.valor_entrega
        
        cmd += ComandaGenerator._duas_colunas(
            "Subtotal:", 
            f"R$ {subtotal:.2f}"
        ).encode('cp860')
        
        cmd += ComandaGenerator._duas_colunas(
            "Taxa de entrega:", 
            f"R$ {pedido.valor_entrega:.2f}"
        ).encode('cp860')
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        cmd += ESC.SIZE_WIDE + ESC.BOLD_ON
        cmd += ComandaGenerator._duas_colunas(
            "TOTAL:", 
            f"R$ {pedido.preco_total:.2f}"
        ).encode('cp860')
        cmd += ESC.BOLD_OFF + ESC.SIZE_NORMAL
        
        cmd += ComandaGenerator._linha().encode('cp860')
        
        # Forma de pagamento
        if pedido.forma_pagamento:
            cmd += f"Pagamento: {pedido.forma_pagamento}\n".encode('cp860')
            
            if pedido.forma_pagamento == "DINHEIRO" and pedido.troco_para:
                troco = pedido.troco_para - pedido.preco_total
                cmd += f"Troco para: R$ {pedido.troco_para:.2f}\n".encode('cp860')
                cmd += f"Troco: R$ {troco:.2f}\n".encode('cp860')
        
        # Observações
        if pedido.observacoes:
            cmd += ComandaGenerator._linha().encode('cp860')
            cmd += ESC.BOLD_ON
            cmd += "OBS:\n".encode('cp860')
            cmd += ESC.BOLD_OFF
            cmd += f"{pedido.observacoes}\n".encode('cp860')
        
        cmd += ComandaGenerator._linha("=").encode('cp860')
        cmd += "\n\n\n"
        
        # Cortar papel
        cmd += ESC.CUT
        
        return cmd


# ==========================
# SERVIÇO DE IMPRESSÃO
# ==========================
class PrintService:
    """Serviço principal de impressão"""
    
    @staticmethod
    def enviar_para_impressora_rede(ip: str, porta: int, dados: bytes) -> Tuple[bool, Optional[str]]:
        """
        Envia dados para impressora de REDE
        
        Returns:
            (sucesso, erro)
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((ip, porta))
            sock.sendall(dados)
            sock.close()
            return (True, None)
        except Exception as e:
            return (False, str(e))
    
    @staticmethod
    def enviar_para_impressora_usb(vendor: str, product: str, dados: bytes) -> Tuple[bool, Optional[str]]:
        """
        Envia dados para impressora USB
        
        Requer biblioteca python-escpos
        
        Returns:
            (sucesso, erro)
        """
        try:
            from escpos import printer
            
            # Converter vendor e product para int
            vendor_id = int(vendor, 16) if vendor.startswith('0x') else int(vendor)
            product_id = int(product, 16) if product.startswith('0x') else int(product)
            
            p = printer.Usb(vendor_id, product_id)
            p._raw(dados)
            p.close()
            
            return (True, None)
        except ImportError:
            return (False, "Biblioteca python-escpos não instalada")
        except Exception as e:
            return (False, str(e))
    
    @staticmethod
    def imprimir(
        pedido: Pedido,
        impressora: Impressora,
        tipo_comanda: str,
        session: Session
    ) -> Tuple[bool, Optional[str]]:
        """
        Imprime uma comanda
        
        Args:
            pedido: Pedido a ser impresso
            impressora: Impressora a usar
            tipo_comanda: 'COZINHA' ou 'MOTOBOY'
            session: Sessão do banco
        
        Returns:
            (sucesso, erro)
        """
        # Buscar configurações
        config = session.query(ConfiguracaoLoja).filter(ConfiguracaoLoja.id == 1).first()
        if not config:
            config = ConfiguracaoLoja(id=1)
            session.add(config)
            session.commit()
        
        # Gerar comanda
        if tipo_comanda == "COZINHA":
            dados = ComandaGenerator.gerar_comanda_cozinha(pedido, config)
        elif tipo_comanda == "MOTOBOY":
            dados = ComandaGenerator.gerar_comanda_motoboy(pedido, config)
        else:
            return (False, "Tipo de comanda inválido")
        
        # Enviar para impressora
        if impressora.tipo == "REDE":
            if not impressora.ip_address or not impressora.porta:
                return (False, "Impressora de rede sem IP/porta configurados")
            
            sucesso, erro = PrintService.enviar_para_impressora_rede(
                impressora.ip_address,
                impressora.porta,
                dados
            )
        elif impressora.tipo == "USB":
            if not impressora.usb_vendor or not impressora.usb_product:
                return (False, "Impressora USB sem vendor/product configurados")
            
            sucesso, erro = PrintService.enviar_para_impressora_usb(
                impressora.usb_vendor,
                impressora.usb_product,
                dados
            )
        else:
            return (False, "Tipo de impressora inválido")
        
        # Registrar log
        log = LogImpressao(
            tipo_comanda=tipo_comanda,
            sucesso=sucesso,
            erro=erro,
            tentativas=1,
            pedido_id=pedido.id,
            impressora_id=impressora.id
        )
        session.add(log)
        
        # Atualizar pedido
        if sucesso:
            if tipo_comanda == "COZINHA":
                pedido.impresso_cozinha = True
                pedido.data_impressao_cozinha = datetime.now(timezone.utc)
            elif tipo_comanda == "MOTOBOY":
                pedido.impresso_motoboy = True
                pedido.data_impressao_motoboy = datetime.now(timezone.utc)
        
        session.commit()
        
        return (sucesso, erro)
    
    @staticmethod
    def imprimir_pedido_completo(pedido: Pedido, session: Session) -> dict:
        """
        Imprime todas as comandas necessárias para um pedido
        
        - BALCÃO: imprime apenas COZINHA
        - ENTREGA: imprime COZINHA + MOTOBOY
        
        Returns:
            dict com status de cada impressão
        """
        resultado = {
            "cozinha": {"sucesso": False, "erro": None},
            "motoboy": {"sucesso": False, "erro": None, "necessario": False}
        }
        
        # Buscar impressoras ativas
        impressora_cozinha = session.query(Impressora).filter(
            Impressora.finalidade == "COZINHA",
            Impressora.ativo == True
        ).first()
        
        impressora_motoboy = session.query(Impressora).filter(
            Impressora.finalidade == "MOTOBOY",
            Impressora.ativo == True
        ).first()
        
        # Imprimir cozinha (SEMPRE)
        if not pedido.impresso_cozinha:
            if impressora_cozinha:
                sucesso, erro = PrintService.imprimir(
                    pedido, impressora_cozinha, "COZINHA", session
                )
                resultado["cozinha"]["sucesso"] = sucesso
                resultado["cozinha"]["erro"] = erro
            else:
                resultado["cozinha"]["erro"] = "Nenhuma impressora de cozinha configurada"
        else:
            resultado["cozinha"]["sucesso"] = True
            resultado["cozinha"]["erro"] = "Já impresso"
        
        # Imprimir motoboy (apenas se ENTREGA)
        if pedido.tipo_pedido == "ENTREGA":
            resultado["motoboy"]["necessario"] = True
            
            if not pedido.impresso_motoboy:
                if impressora_motoboy:
                    sucesso, erro = PrintService.imprimir(
                        pedido, impressora_motoboy, "MOTOBOY", session
                    )
                    resultado["motoboy"]["sucesso"] = sucesso
                    resultado["motoboy"]["erro"] = erro
                else:
                    resultado["motoboy"]["erro"] = "Nenhuma impressora de motoboy configurada"
            else:
                resultado["motoboy"]["sucesso"] = True
                resultado["motoboy"]["erro"] = "Já impresso"
        
        return resultado
    
    @staticmethod
    def reimprimir_comanda(
        pedido_id: int,
        tipo_comanda: str,
        session: Session
    ) -> Tuple[bool, Optional[str]]:
        """
        Reimprime uma comanda específica
        Não verifica se já foi impressa (força reimpressão)
        """
        pedido = session.query(Pedido).filter(Pedido.id == pedido_id).first()
        if not pedido:
            return (False, "Pedido não encontrado")
        
        # Buscar impressora
        impressora = session.query(Impressora).filter(
            Impressora.finalidade == tipo_comanda,
            Impressora.ativo == True
        ).first()
        
        if not impressora:
            return (False, f"Nenhuma impressora de {tipo_comanda} configurada")
        
        # Temporariamente marcar como não impresso para forçar impressão
        if tipo_comanda == "COZINHA":
            impresso_anterior = pedido.impresso_cozinha
            pedido.impresso_cozinha = False
        else:
            impresso_anterior = pedido.impresso_motoboy
            pedido.impresso_motoboy = False
        
        sucesso, erro = PrintService.imprimir(pedido, impressora, tipo_comanda, session)
        
        # Se falhou, restaurar estado anterior
        if not sucesso:
            if tipo_comanda == "COZINHA":
                pedido.impresso_cozinha = impresso_anterior
            else:
                pedido.impresso_motoboy = impresso_anterior
            session.commit()
        
        return (sucesso, erro)
