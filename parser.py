import re
from typing import Dict, Optional, Tuple


def extract_message_info(payload: dict) -> Tuple[Optional[str], Optional[str], bool, dict, dict]:
    """
    Extrai o texto da mensagem, o JID do remetente/grupo, a flag fromMe, 
    a chave da mensagem (key) e o objeto da mensagem (message_obj)
    a partir do payload do webhook da Evolution API (v1 e v2).
    """
    if not isinstance(payload, dict):
        return None, None, False, {}, {}

    # Extrai o bloco de dados do evento
    data = payload.get("data", {})
    if not data and "message" in payload:
        # Suporte para variação direta de payload
        data = payload

    key = data.get("key", {})
    remote_jid = key.get("remoteJid") or data.get("remoteJid")
    from_me = key.get("fromMe", False)

    message_obj = data.get("message", {})
    if not isinstance(message_obj, dict):
        message_obj = {}

    # O texto pode vir em diferentes estruturas dependendo do tipo da mensagem
    text = (
        message_obj.get("conversation")
        or message_obj.get("extendedTextMessage", {}).get("text")
        or message_obj.get("imageMessage", {}).get("caption")
        or message_obj.get("videoMessage", {}).get("caption")
        or data.get("body")
    )

    return text, remote_jid, from_me, key, message_obj


def parse_reimbursement_message(text: str) -> Optional[Dict[str, str]]:
    """
    Analisa o texto recebido e extrai os campos de acordo com o modelo de viagem/reembolso.
    Suporta negrito do WhatsApp (*campo:*), variações de maiúsculas/minúsculas e acentuação.

    Campos aceitos:
    - Data
    - Horário / Horario
    - Funcionário / Funcionario / Colaborador
    - Motivo
    - Origem
    - Parada
    - Destino
    - Valor da viagem / Valor
    - Centro de custo / Centro de Custo

    Retorna um dicionário com os dados extraídos ou None se a mensagem não corresponder ao modelo.
    """
    if not text or not isinstance(text, str):
        return None

    patterns = {
        "data": r"(?:\*?\s*)Data(?:\s*\*?):\s*(.+)",
        "horario": r"(?:\*?\s*)Hor[áa]rio(?:\s*\*?):\s*(.+)",
        "funcionario": r"(?:\*?\s*)(?:Funcion[áa]rio|Colaborador)(?:\s*\*?):\s*(.+)",
        "motivo": r"(?:\*?\s*)Motivo(?:\s*\*?):\s*(.+)",
        "origem": r"(?:\*?\s*)Origem(?:\s*\*?):\s*(.+)",
        "parada": r"(?:\*?\s*)Parada(?:\s*\*?):\s*(.+)",
        "destino": r"(?:\*?\s*)Destino(?:\s*\*?):\s*(.+)",
        "valor": r"(?:\*?\s*)Valor(?:\s+da\s+viagem)?(?:\s*\*?):\s*(.+)",
        "centro_custo": r"(?:\*?\s*)Centro\s+de\s+custo(?:\s*\*?):\s*(.+)",
    }

    extracted = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Limpa asteriscos, sublinhados e espaços extras no valor extraído
            value = match.group(1).strip().strip("*_").strip()
            extracted[key] = value
        else:
            extracted[key] = ""

    # Validação mínima: Data, Funcionário e Valor da viagem são obrigatórios para confirmar o padrão
    if extracted["data"] and extracted["funcionario"] and extracted["valor"]:
        return extracted

    return None

