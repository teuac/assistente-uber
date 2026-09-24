import os
from datetime import date
import openpyxl
from parser import parse_export_command
from google_sheets import filter_records_by_date_range
from excel_generator import create_styled_reimbursement_excel

MOCK_RECORDS = [
    {
        "Motivo": "Ida ao Galpão",
        "Data": "05/02/2026",
        "Horário": "08:30 horas",
        "Funcionário": "Luiz Fernando",
        "Origem": "Grand View",
        "Parada": "",
        "Destino": "Galpão",
        "Valor da Viagem": "R$ 28,96",
        "Centro de Custo": "Assistência Técnica",
        "Data de Registro": "05/02/2026 08:35:00"
    },
    {
        "Motivo": "Visita Obra",
        "Data": "20/02/2026",
        "Horário": "14:15 horas",
        "Funcionário": "Gaby Apontadora",
        "Origem": "Escritório Central",
        "Parada": "Almoxarifado",
        "Destino": "Obra Santa Lúcia",
        "Valor da Viagem": "R$ 45,50",
        "Centro de Custo": "Engenharia",
        "Data de Registro": "20/02/2026 14:20:00"
    },
    {
        "Motivo": "Reunião Diretoria",
        "Data": "10/03/2026",
        "Horário": "09:00 horas",
        "Funcionário": "Carlos Eduardo",
        "Origem": "Filial",
        "Parada": "",
        "Destino": "Sede",
        "Valor da Viagem": "R$ 110,00",
        "Centro de Custo": "Administração",
        "Data de Registro": "10/03/2026 09:05:00"
    }
]


def test_export_workflow():
    print("=" * 65)
    print("TESTANDO COMANDO DE EXPORTAÇÃO E GERAÇÃO DE EXCEL ESTILIZADO")
    print("=" * 65)

    # 1. Teste de Parsing de Comandos de Exportação
    cmd1 = "K/ planilha mensal 02/02/2026 - 02/03/2026"
    res1 = parse_export_command(cmd1)
    assert res1 is not None, f"Falha ao identificar comando: {cmd1}"
    assert res1["start_str"] == "02/02/2026", f"Erro start_str: {res1['start_str']}"
    assert res1["end_str"] == "02/03/2026", f"Erro end_str: {res1['end_str']}"
    print(f"   [OK] Comando 1 ('{cmd1}'): {res1['start_str']} a {res1['end_str']}")

    cmd2 = "k/ relatorio 15/01/2026 a 28/02/2026"
    res2 = parse_export_command(cmd2)
    assert res2 is not None, f"Falha ao identificar comando: {cmd2}"
    assert res2["start_str"] == "15/01/2026"
    assert res2["end_str"] == "28/02/2026"
    print(f"   [OK] Comando 2 ('{cmd2}'): {res2['start_str']} a {res2['end_str']}")

    cmd3 = "K / exportar excel"
    res3 = parse_export_command(cmd3)
    assert res3 is not None, f"Falha ao identificar comando sem data: {cmd3}"
    print(f"   [OK] Comando 3 sem data (padrão mês atual): {res3['start_str']} a {res3['end_str']}")

    # 2. Teste de Filtragem por Intervalo de Data
    start_d = date(2026, 2, 1)
    end_d = date(2026, 2, 28)
    filtered = filter_records_by_date_range(MOCK_RECORDS, start_d, end_d)
    assert len(filtered) == 2, f"Esperava 2 registros no mês de Fevereiro, obteve {len(filtered)}"
    print(f"   [OK] Filtragem por data: {len(filtered)} de {len(MOCK_RECORDS)} registros correspondem a Fevereiro/2026.")

    # 3. Teste de Geração do Arquivo Excel Estilizado (.xlsx)
    xlsx_path = create_styled_reimbursement_excel(filtered, "01/02/2026", "28/02/2026")
    assert os.path.exists(xlsx_path), f"Arquivo Excel não foi criado em: {xlsx_path}"
    print(f"   [OK] Planilha Excel gerada com sucesso em: {xlsx_path}")

    # Valida estrutura do arquivo Excel com openpyxl
    wb = openpyxl.load_workbook(xlsx_path)
    sheet = wb.active
    assert sheet.title == "Relatório de Viagens"
    assert sheet["A1"].value == "RELATÓRIO MENSAL DE VIAGENS E REEMBOLSOS"
    assert sheet["A7"].value == "Motivo"
    assert sheet["H7"].value == "Valor da Viagem"
    wb.close()

    print("\n TODOS OS TESTES DE EXPORTAÇÃO PASSARAM COM SUCESSO!")
    print("=" * 65)


if __name__ == "__main__":
    test_export_workflow()
