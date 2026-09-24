from datetime import datetime
import logging
from typing import Dict, Any, List

import gspread
from google.oauth2.service_account import Credentials

try:
    from gspread_formatting import (
        CellFormat, Color, TextFormat, format_cell_range,
        set_frozen, set_column_widths, set_row_height
    )
    HAS_FORMATTING = True
except ImportError:
    HAS_FORMATTING = False

import config

logger = logging.getLogger("google_sheets")
logger.setLevel(logging.INFO)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Motivo",
    "Data",
    "Horário",
    "Funcionário",
    "Origem",
    "Parada",
    "Destino",
    "Valor da Viagem",
    "Centro de Custo",
    "Data de Registro",
]


import time
import threading

class GoogleSheetsClient:
    _lock = threading.Lock()

    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.worksheet = None

    def connect(self):
        """Autentica com as credenciais do .env e abre a planilha configurada."""
        cred_dict = config.get_google_credentials_dict()
        credentials = Credentials.from_service_account_info(cred_dict, scopes=SCOPES)
        self.client = gspread.authorize(credentials)

        if not config.SPREADSHEET_ID:
            raise ValueError("SPREADSHEET_ID não está configurado no arquivo .env!")

        self.spreadsheet = self.client.open_by_key(config.SPREADSHEET_ID)

        # Seleciona ou cria a aba especificada
        try:
            self.worksheet = self.spreadsheet.worksheet(config.SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Aba '{config.SHEET_NAME}' não encontrada. Criando nova aba...")
            self.worksheet = self.spreadsheet.add_worksheet(
                title=config.SHEET_NAME, rows=1000, cols=11
            )

        self.ensure_header_and_styles()

    def ensure_header_and_styles(self):
        """Garante que a linha 1 contenha os cabeçalhos corretos e aplica estilos visuais."""
        existing_values = self.worksheet.row_values(1)

        if not existing_values:
            logger.info("Adicionando cabeçalho na planilha...")
            self.worksheet.insert_row(HEADERS, index=1)

        if HAS_FORMATTING:
            try:
                # Estilo do Cabeçalho: Fundo escuro (#1E293B), texto branco em negrito
                header_format = CellFormat(
                    backgroundColor=Color(0.12, 0.16, 0.23),  # RGB de #1E293B
                    textFormat=TextFormat(bold=True, foregroundColor=Color(1, 1, 1), fontSize=11),
                    horizontalAlignment="CENTER"
                )
                format_cell_range(self.worksheet, "A1:J1", header_format)
                set_frozen(self.worksheet, rows=1)
                set_row_height(self.worksheet, "1", 36)

                # Definindo larguras adequadas para cada coluna
                column_widths = [
                    ("A", 300),  # Motivo
                    ("B", 120),  # Data
                    ("C", 120),  # Horário
                    ("D", 220),  # Funcionário
                    ("E", 200),  # Origem
                    ("F", 200),  # Parada
                    ("G", 200),  # Destino
                    ("H", 150),  # Valor da Viagem
                    ("I", 200),  # Centro de Custo
                    ("J", 170),  # Data de Registro
                ]
                for col_letter, width in column_widths:
                    set_column_widths(self.worksheet, [(col_letter, width)])

                logger.info("Estilização da planilha aplicada com sucesso.")
            except Exception as e:
                logger.warning(f"Não foi possível aplicar estilização avançada: {e}")

    def append_reimbursement(self, data: Dict[str, str], max_retries: int = 5) -> bool:
        """
        Insere uma nova linha na planilha com os dados formatados.
        Possui trava de concorrência (thread-safe) e sistema de tentativas (retries) com backoff exponencial 
        para tratar de forma transparente os limites de taxa (Rate Limit / 429) da Google Sheets API.
        """
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        row = [
            data.get("motivo", ""),
            data.get("data", ""),
            data.get("horario", ""),
            data.get("funcionario", ""),
            data.get("origem", ""),
            data.get("parada", ""),
            data.get("destino", ""),
            data.get("valor", ""),
            data.get("centro_custo", ""),
            now_str,
        ]

        delay = 1.5
        for attempt in range(1, max_retries + 1):
            try:
                with self._lock:
                    if not self.worksheet:
                        self.connect()
                    
                    self.worksheet.append_row(row, value_input_option="USER_ENTERED")
                    # Pequena pausa estratégica para respeitar a cota por segundo do Google Sheets API
                    time.sleep(0.3)
                
                logger.info(f"Linha registrada com sucesso no Google Sheets para: {data.get('funcionario')}")
                return True

            except Exception as e:
                logger.warning(f"Tentativa {attempt}/{max_retries} falhou ao inserir no Google Sheets ({data.get('funcionario')}): {e}")
                # Força reconexão na próxima tentativa se tiver sido erro de autenticação ou socket drop
                self.worksheet = None
                if attempt == max_retries:
                    logger.error(f"Todas as {max_retries} tentativas no Google Sheets falharam para {data.get('funcionario')}: {e}")
                    raise e
                time.sleep(delay)
                delay *= 2  # Backoff exponencial: 1.5s, 3s, 6s, 12s...

    def append_reimbursements_batch(self, data_list: List[Dict[str, str]], max_retries: int = 5) -> bool:
        """
        Insere MÚLTIPLAS linhas na planilha em UMA ÚNICA REQUISIÇÃO HTTP à API do Google Sheets.
        Reduz drasticamente o número de chamadas de API de N para 1, evitando estourar cotas ou rate limits.
        """
        if not data_list:
            return True

        rows = []
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        for data in data_list:
            row = [
                data.get("motivo", ""),
                data.get("data", ""),
                data.get("horario", ""),
                data.get("funcionario", ""),
                data.get("origem", ""),
                data.get("parada", ""),
                data.get("destino", ""),
                data.get("valor", ""),
                data.get("centro_custo", ""),
                now_str,
            ]
            rows.append(row)

        delay = 1.5
        for attempt in range(1, max_retries + 1):
            try:
                with self._lock:
                    if not self.worksheet:
                        self.connect()

                    self.worksheet.append_rows(rows, value_input_option="USER_ENTERED")
                    time.sleep(0.3)

                logger.info(f"Lote de {len(rows)} linhas registrado com SUCESSO no Google Sheets em 1 única requisição!")
                return True

            except Exception as e:
                logger.warning(f"Tentativa {attempt}/{max_retries} falhou ao inserir lote ({len(rows)} itens) no Google Sheets: {e}")
                self.worksheet = None
                if attempt == max_retries:
                    logger.error(f"Todas as {max_retries} tentativas de inserção em lote falharam: {e}")
                    raise e
                time.sleep(delay)
                delay *= 2

        return False


    def fetch_all_records(self) -> List[Dict[str, str]]:
        """Lê todas as linhas salvas na planilha do Google Sheets e retorna como uma lista de dicionários."""
        with self._lock:
            if not self.worksheet:
                self.connect()

            all_values = self.worksheet.get_all_values()

        if not all_values or len(all_values) <= 1:
            return []

        headers = [h.strip() for h in all_values[0]]
        records = []
        for row in all_values[1:]:
            padded_row = row + [""] * (len(headers) - len(row))
            record = {headers[i]: padded_row[i].strip() for i in range(len(headers))}
            records.append(record)

        return records


def filter_records_by_date_range(
    records: List[Dict[str, str]], 
    start_date: Any, 
    end_date: Any
) -> List[Dict[str, str]]:
    """Filtra os registros onde a coluna 'Data' se encontra dentro do intervalo especificado [start_date, end_date]."""
    filtered = []
    for r in records:
        raw_date_str = r.get("Data", "").strip()
        if not raw_date_str:
            reg_str = r.get("Data de Registro", "")
            raw_date_str = reg_str.split()[0] if reg_str else ""

        parsed_d = None
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                parsed_d = datetime.strptime(raw_date_str, fmt).date()
                break
            except (ValueError, TypeError):
                pass

        if parsed_d:
            if start_date <= parsed_d <= end_date:
                filtered.append(r)

    return filtered


