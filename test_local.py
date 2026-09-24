import json
from parser import parse_reimbursement_message, extract_message_info

# Mensagem de teste 1: Sem parada
SAMPLE_MESSAGE_1 = """Data: 21/09/2026
Horário: 08:38 horas 
Funcionário: Luiz Fernando
Motivo: Ida ao Galpão para realização de atividades de manutenção.
Origem: Grand View 
Destino: Galpão - AC Engenharia 
Valor da viagem: R$ 28,96
Centro de custo: Assistência Técnica"""

# Mensagem de teste 2: Com parada
SAMPLE_MESSAGE_2 = """Data: 29/07/2026
Horário: 14:45 horas 
Funcionário: Gaby (Apontadora) / colaborador do St. Lúcia
Motivo: Retorno - Atend. RH/DP / Retorno de atividade 
Origem: Grand View Residence
Parada: Escritório - AC Engenharia  
Destino: Santa Lúcia Park Residence
Valor da viagem: R$ 20,65
Centro de custo: Obra"""

SAMPLE_WEBHOOK_PAYLOAD = {
    "event": "messages.upsert",
    "instance": "instancia_teste",
    "data": {
        "key": {
            "remoteJid": "12036301234567890@g.us",
            "fromMe": False,
            "id": "3EB0ABC123456"
        },
        "pushName": "Luiz Fernando",
        "message": {
            "extendedTextMessage": {
                "text": SAMPLE_MESSAGE_2
            }
        }
    }
}


# Mensagem de teste 3: Formatada em negrito pelo WhatsApp (*Data:*, *Valor da viagem:*, etc)
SAMPLE_MESSAGE_3 = """*Data:* 21/09/2026
*Horário:* 08:38 horas 
*Funcionário:* Carlos Alberto
*Motivo:* Visita técnica ao cliente.
*Origem:* Matriz
*Destino:* Filial Sul
*Valor da viagem:* R$ 45,50
*Centro de custo:* Engenharia"""


def run_tests():
    print("=" * 65)
    print("TESTANDO PARSER DE MENSAGENS E REGRAS DE CONCORRÊNCIA")
    print("=" * 65)

    # 1. Teste da Mensagem 1 (Sem Parada)
    print("\n1. Teste da Mensagem Sem Parada:")
    parsed1 = parse_reimbursement_message(SAMPLE_MESSAGE_1)
    assert parsed1 is not None, "Falha ao parsear mensagem 1!"
    assert parsed1["parada"] == "", f"Esperava parada vazia, obteve: {parsed1['parada']}"
    print("   [OK] Mensagem sem parada parseada corretamente. Parada = ''")

    # 2. Teste da Mensagem 2 (Com Parada)
    print("\n2. Teste da Mensagem Com Parada:")
    parsed2 = parse_reimbursement_message(SAMPLE_MESSAGE_2)
    assert parsed2 is not None, "Falha ao parsear mensagem 2!"
    assert parsed2["parada"] == "Escritório - AC Engenharia", f"Erro no campo parada: {parsed2['parada']}"
    assert parsed2["funcionario"] == "Gaby (Apontadora) / colaborador do St. Lúcia"
    assert parsed2["origem"] == "Grand View Residence"
    assert parsed2["destino"] == "Santa Lúcia Park Residence"
    assert parsed2["valor"] == "R$ 20,65"
    assert parsed2["centro_custo"] == "Obra"
    
    print("   [OK] Mensagem com parada parseada com sucesso:")
    for k, v in parsed2.items():
        print(f"     * {k.upper()}: '{v}'")

    # 3. Teste da Mensagem 3 (Com Negrito do WhatsApp)
    print("\n3. Teste da Mensagem Com Negrito (*Campo:*):")
    parsed3 = parse_reimbursement_message(SAMPLE_MESSAGE_3)
    assert parsed3 is not None, "Falha ao parsear mensagem com negrito!"
    assert parsed3["funcionario"] == "Carlos Alberto", f"Erro no funcionário: {parsed3['funcionario']}"
    assert parsed3["valor"] == "R$ 45,50", f"Erro no valor: {parsed3['valor']}"
    assert parsed3["data"] == "21/09/2026", f"Erro na data: {parsed3['data']}"
    print("   [OK] Mensagem formatada em negrito parseada com sucesso!")

    print("\n TODOS OS TESTES PASSARAM COM SUCESSO!")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()

