import os
import re
import tempfile
from typing import List, Dict
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

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


def _clean_price_value(val_str: str) -> float:
    """Converte strings como 'R$ 28,96' ou '28.96' para float."""
    if not val_str:
        return 0.0
    try:
        cleaned = re.sub(r"[^\d,\.]", "", val_str)
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        return float(cleaned)
    except Exception:
        return 0.0


def create_styled_reimbursement_excel(
    records: List[Dict[str, str]], 
    start_str: str, 
    end_str: str,
    output_dir: str = None
) -> str:
    """
    Gera uma planilha Excel altamente estilizada e profissional (.xlsx) contendo os registros filtrados.
    Retorna o caminho absoluto do arquivo salvo.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Relatório de Viagens"
    ws.views.sheetView[0].showGridLines = True

    # Paleta de Cores (Estilo Dark Slate & Modern Corporate)
    TITLE_BG = "0F172A"       # Azul Escuro Escuro
    SUBTITLE_BG = "1E293B"    # Azul Grafite
    HEADER_BG = "1E293B"      # Cabeçalho da Tabela
    ZEBRA_EVEN = "F8FAFC"     # Linhas pares (Cinza muito claro)
    ZEBRA_ODD = "FFFFFF"      # Linhas ímpares (Branco)
    TOTAL_BG = "E2E8F0"       # Linha de Totais
    CARD_BG = "F1F5F9"        # Card KPI
    FONT_FAMILY = "Segoe UI"

    # EstilosReutilizáveis
    font_title = Font(name=FONT_FAMILY, size=16, bold=True, color="FFFFFF")
    font_subtitle = Font(name=FONT_FAMILY, size=11, italic=True, color="E2E8F0")
    font_kpi_label = Font(name=FONT_FAMILY, size=9, bold=True, color="475569")
    font_kpi_val = Font(name=FONT_FAMILY, size=14, bold=True, color="0F172A")
    font_header = Font(name=FONT_FAMILY, size=10, bold=True, color="FFFFFF")
    font_data = Font(name=FONT_FAMILY, size=10, color="1E293B")
    font_total = Font(name=FONT_FAMILY, size=11, bold=True, color="0F172A")

    fill_title = PatternFill(start_color=TITLE_BG, end_color=TITLE_BG, fill_type="solid")
    fill_subtitle = PatternFill(start_color=SUBTITLE_BG, end_color=SUBTITLE_BG, fill_type="solid")
    fill_header = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type="solid")
    fill_even = PatternFill(start_color=ZEBRA_EVEN, end_color=ZEBRA_EVEN, fill_type="solid")
    fill_odd = PatternFill(start_color=ZEBRA_ODD, end_color=ZEBRA_ODD, fill_type="solid")
    fill_total = PatternFill(start_color=TOTAL_BG, end_color=TOTAL_BG, fill_type="solid")
    fill_card = PatternFill(start_color=CARD_BG, end_color=CARD_BG, fill_type="solid")

    thin_border_side = Side(border_style="thin", color="CBD5E1")
    border_data = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    border_total = Border(
        top=Side(border_style="thin", color="0F172A"),
        bottom=Side(border_style="double", color="0F172A"),
        left=thin_border_side,
        right=thin_border_side
    )

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    align_right = Alignment(horizontal="right", vertical="center")

    # 1. Título Principal (Linhas 1 e 2)
    ws.merge_cells("A1:J1")
    title_cell = ws["A1"]
    title_cell.value = "RELATÓRIO MENSAL DE VIAGENS E REEMBOLSOS"
    title_cell.font = font_title
    title_cell.fill = fill_title
    title_cell.alignment = align_center
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:J2")
    sub_cell = ws["A2"]
    sub_cell.value = f"Período de Referência: {start_str} até {end_str}"
    sub_cell.font = font_subtitle
    sub_cell.fill = fill_subtitle
    sub_cell.alignment = align_center
    ws.row_dimensions[2].height = 22

    # 2. Seção de Cards KPI (Linhas 4 e 5)
    total_viagens = len(records)
    total_valor = sum(_clean_price_value(r.get("Valor da Viagem", r.get("valor", ""))) for r in records)

    # Card 1: Total Viagens (B4:C5)
    ws.merge_cells("B4:C4")
    ws["B4"].value = "TOTAL DE VIAGENS"
    ws["B4"].font = font_kpi_label
    ws["B4"].alignment = align_center
    ws["B4"].fill = fill_card

    ws.merge_cells("B5:C5")
    ws["B5"].value = total_viagens
    ws["B5"].font = font_kpi_val
    ws["B5"].alignment = align_center
    ws["B5"].fill = fill_card

    # Card 2: Valor Total (H4:I5)
    ws.merge_cells("H4:I4")
    ws["H4"].value = "VALOR TOTAL REEMBOLSADO"
    ws["H4"].font = font_kpi_label
    ws["H4"].alignment = align_center
    ws["H4"].fill = fill_card

    ws.merge_cells("H5:I5")
    ws["H5"].value = total_valor
    ws["H5"].font = font_kpi_val
    ws["H5"].number_format = 'R$ #,##0.00'
    ws["H5"].alignment = align_center
    ws["H5"].fill = fill_card

    ws.row_dimensions[4].height = 18
    ws.row_dimensions[5].height = 24

    # 3. Cabeçalhos da Tabela (Linha 7)
    header_row_idx = 7
    ws.row_dimensions[header_row_idx].height = 28
    for col_idx, h_text in enumerate(HEADERS, 1):
        cell = ws.cell(row=header_row_idx, column=col_idx, value=h_text)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = align_center
        cell.border = border_data

    # 4. Inserção das Linhas de Dados (Linha 8 em diante)
    current_row = 8
    for r_idx, record in enumerate(records):
        ws.row_dimensions[current_row].height = 22
        row_fill = fill_even if r_idx % 2 == 0 else fill_odd

        # Extração de valores
        motivo = record.get("Motivo", record.get("motivo", ""))
        data = record.get("Data", record.get("data", ""))
        horario = record.get("Horário", record.get("horario", ""))
        funcionario = record.get("Funcionário", record.get("funcionario", ""))
        origem = record.get("Origem", record.get("origem", ""))
        parada = record.get("Parada", record.get("parada", ""))
        destino = record.get("Destino", record.get("destino", ""))
        valor_raw = record.get("Valor da Viagem", record.get("valor", ""))
        valor_float = _clean_price_value(valor_raw)
        centro_custo = record.get("Centro de Custo", record.get("centro_custo", ""))
        data_reg = record.get("Data de Registro", "")

        row_values = [
            (motivo, align_left, "@"),
            (data, align_center, "@"),
            (horario, align_center, "@"),
            (funcionario, align_left, "@"),
            (origem, align_left, "@"),
            (parada, align_left, "@"),
            (destino, align_left, "@"),
            (valor_float, align_right, 'R$ #,##0.00'),
            (centro_custo, align_left, "@"),
            (data_reg, align_center, "@"),
        ]

        for c_idx, (val, alignment, num_fmt) in enumerate(row_values, 1):
            cell = ws.cell(row=current_row, column=c_idx, value=val)
            cell.font = font_data
            cell.fill = row_fill
            cell.alignment = alignment
            cell.border = border_data
            if num_fmt and num_fmt != "@":
                cell.number_format = num_fmt

        current_row += 1

    # 5. Linha de Totalização
    ws.row_dimensions[current_row].height = 26
    for c_idx in range(1, len(HEADERS) + 1):
        cell = ws.cell(row=current_row, column=c_idx)
        cell.font = font_total
        cell.fill = fill_total
        cell.border = border_total

    ws.cell(row=current_row, column=1, value="TOTAL GERAL").alignment = align_left
    sum_col_letter = get_column_letter(8) # Coluna H (Valor)
    if records:
        start_cell = f"{sum_col_letter}8"
        end_cell = f"{sum_col_letter}{current_row - 1}"
        val_cell = ws.cell(row=current_row, column=8, value=f"=SUM({start_cell}:{end_cell})")
    else:
        val_cell = ws.cell(row=current_row, column=8, value=0.0)

    val_cell.number_format = 'R$ #,##0.00'
    val_cell.alignment = align_right

    # 6. Ajuste Automático de Largura das Colunas
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # Ignora células mescladas no título e cards para o cálculo da largura
            if cell.row in (1, 2, 4, 5):
                continue
            if cell.value:
                val_str = str(cell.value)
                max_len = max(max_len, len(val_str))
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    # Definir diretório de saída
    if not output_dir:
        output_dir = os.path.join(tempfile.gettempdir(), "uber_exports")
    os.makedirs(output_dir, exist_ok=True)

    safe_start = start_str.replace("/", "-")
    safe_end = end_str.replace("/", "-")
    filename = f"Relatorio_Viagens_{safe_start}_a_{safe_end}.xlsx"
    filepath = os.path.join(output_dir, filename)

    wb.save(filepath)
    return filepath
