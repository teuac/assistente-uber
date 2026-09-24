import asyncio
from datetime import datetime
from parser import parse_reimbursement_message

# Gerar 60 mensagens de teste variando funcionário e valor
MOCK_MESSAGES = [
    f"""Data: 24/09/2026
Horário: 10:{i:02d}
Funcionário: Funcionário Teste #{i+1}
Motivo: Viagem em lote #{i+1}
Origem: Ponto A
Destino: Ponto B
Valor da viagem: R$ {10 + i},50
Centro de custo: Teste Lote"""
    for i in range(60)
]


def test_batch_parsing():
    print("=" * 65)
    print("TESTANDO PARSER COM LOTE DE 60 MENSAGENS")
    print("=" * 65)

    parsed_count = 0
    for idx, msg in enumerate(MOCK_MESSAGES, 1):
        parsed = parse_reimbursement_message(msg)
        if parsed:
            parsed_count += 1

    assert parsed_count == 60, f"Esperava 60 mensagens parseadas com sucesso, obteve {parsed_count}"
    print(f"   [OK] Todas as {parsed_count} de 60 mensagens foram validadas e parseadas com SUCESSO!")
    print("=" * 65)


if __name__ == "__main__":
    test_batch_parsing()
