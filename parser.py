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
    Suporta negrito do WhatsApp (*campo:*), traços, variações de maiúsculas/minúsculas e acentuação.

    Campos aceitos:
    - Data
    - Horário / Horario
    - Funcionário / Funcionario / Colaborador / Nome
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
        "data": r"(?:\*?\s*)Data(?:\s*\*?)[\s:-]+([^\n]+)",
        "horario": r"(?:\*?\s*)Hor[áa]rio(?:\s*\*?)[\s:-]+([^\n]+)",
        "funcionario": r"(?:\*?\s*)(?:Funcion[áa]rio|Funcionario|Colaborador|Nome)(?:\s*\*?)[\s:-]+([^\n]+)",
        "motivo": r"(?:\*?\s*)Motivo(?:\s*\*?)[\s:-]+([^\n]+)",
        "origem": r"(?:\*?\s*)Origem(?:\s*\*?)[\s:-]+([^\n]+)",
        "parada": r"(?:\*?\s*)Parada(?:\s*\*?)[\s:-]+([^\n]+)",
        "destino": r"(?:\*?\s*)Destino(?:\s*\*?)[\s:-]+([^\n]+)",
        "valor": r"(?:\*?\s*)Valor(?:\s+da\s+viagem|\s+viagem)?(?:\s*\*?)[\s:-]+([^\n]+)",
        "centro_custo": r"(?:\*?\s*)Centro\s+de\s+custo(?:\s*\*?)[\s:-]+([^\n]+)",
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

    # Fallback para Data: procura formato DD/MM/YYYY se o campo Data não foi capturado diretamente
    if not extracted["data"]:
        date_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", text)
        if date_match:
            extracted["data"] = date_match.group(1).strip()

    # Fallback para Valor: procura R$ XX,XX se o campo Valor não foi capturado diretamente
    if not extracted["valor"]:
        val_match = re.search(r"(R\$\s*\d+(?:[\.,]\d{2})?)", text, re.IGNORECASE)
        if val_match:
            extracted["valor"] = val_match.group(1).strip()

    # Validação mínima: Data, Funcionário e Valor são obrigatórios
    if extracted["data"] and extracted["funcionario"] and extracted["valor"]:
        return extracted

    return None



def parse_export_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Identifica comandos de exportação de planilha enviados via WhatsApp.
    Exemplo: "K/ planilha mensal 02/02/2026 - 02/03/2026"
    Exemplo: "K/ planilha 15/01/2026 a 20/02/2026"
    Exemplo: "K/ relatorio mensal"

    Retorna um dicionário com os dados do comando ou None se não for um comando de exportação.
    """
    if not text or not isinstance(text, str):
        return None

    import calendar
    from datetime import datetime, date
    from typing import Any

    text_stripped = text.strip()

    # Verifica se começa com o prefixo K/ ou k/ (com ou sem espaço)
    prefix_match = re.match(r"^[kK]\s*/\s*(.*)", text_stripped, re.DOTALL | re.IGNORECASE)
    if not prefix_match:
        return None

    command_body = prefix_match.group(1).strip()

    # Palavras-chave esperadas: planilha, relatorio, relatório, exportar, excel
    keywords_pattern = r"(?:planilha(?:\s+mensal)?|relat[óo]rio(?:\s+mensal)?|exportar|excel)"
    if not re.search(keywords_pattern, command_body, re.IGNORECASE):
        return None

    # Tenta encontrar o intervalo de datas: DD/MM/YYYY até DD/MM/YYYY ou DD/MM/YY
    date_range_pattern = (
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:-|a|at[ée])\s*(\d{1,2}/\d{1,2}/\d{2,4})"
    )
    range_match = re.search(date_range_pattern, command_body, re.IGNORECASE)

    start_date = None
    end_date = None

    def parse_date_str(d_str: str) -> Optional[date]:
        d_str = d_str.strip()
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(d_str, fmt).date()
            except ValueError:
                pass
        return None

    if range_match:
        raw_start, raw_end = range_match.group(1), range_match.group(2)
        start_date = parse_date_str(raw_start)
        end_date = parse_date_str(raw_end)

    if not start_date or not end_date:
        # Se não informou intervalo explícito, verifica se informou um único mês (ex: 02/2026)
        month_match = re.search(r"(\d{1,2})/(\d{4})", command_body)
        if month_match:
            m = int(month_match.group(1))
            y = int(month_match.group(2))
            if 1 <= m <= 12:
                last_day = calendar.monthrange(y, m)[1]
                start_date = date(y, m, 1)
                end_date = date(y, m, last_day)

    if not start_date or not end_date:
        # Padrão: Mês atual
        today = date.today()
        start_date = date(today.year, today.month, 1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_date = date(today.year, today.month, last_day)

    start_str = start_date.strftime("%d/%m/%Y")
    end_str = end_date.strftime("%d/%m/%Y")

    return {
        "is_export": True,
        "start_date": start_date,
        "end_date": end_date,
        "start_str": start_str,
        "end_str": end_str,
        "raw_text": text
    }


