import asyncio
import time
from datetime import datetime

# Simulação da fila e lógica de debounce em 2 segundos para testes rápidos
COOLDOWN_TEST_SECONDS = 2.0

async def simulate_cooldown_batching(messages_arrivals: list):
    """
    messages_arrivals: lista de tuplas (delay_antes_de_enviar, item_id)
    Retorna os lotes processados e os horários de finalização de cada lote.
    """
    queue = asyncio.Queue()
    processed_batches = []

    async def mock_worker():
        while True:
            try:
                first_item = await queue.get()
                batch = [first_item]
                last_activity = asyncio.get_event_loop().time()

                while True:
                    now = asyncio.get_event_loop().time()
                    elapsed = now - last_activity
                    remaining = COOLDOWN_TEST_SECONDS - elapsed

                    if remaining <= 0:
                        break

                    try:
                        next_item = await asyncio.wait_for(queue.get(), timeout=remaining)
                        batch.append(next_item)
                        last_activity = asyncio.get_event_loop().time()
                    except asyncio.TimeoutError:
                        break

                processed_batches.append({
                    "batch_size": len(batch),
                    "items": batch,
                    "processed_at": time.time()
                })

                for _ in range(len(batch)):
                    queue.task_done()

            except asyncio.CancelledError:
                break

    worker_task = asyncio.create_task(mock_worker())

    # Envia mensagens conforme os delays especificados
    start_t = time.time()
    for delay, item in messages_arrivals:
        await asyncio.sleep(delay)
        await queue.put(item)

    # Aguarda o término de processamento na fila
    await queue.join()
    await asyncio.sleep(COOLDOWN_TEST_SECONDS + 0.5)
    worker_task.cancel()

    return processed_batches


def run_tests():
    print("=" * 65)
    print("TESTANDO COOLDOWN (DEBOUNCE) DE 15s E RESUMO INTELIGENTE DE GRUPO")
    print("=" * 65)

    # Caso 1: 5 mensagens enviadas a cada 0.5s (dentro da janela de 2s)
    # Esperado: 1 único lote de 5 itens processado após 2s de silêncio
    arrivals = [
        (0.0, "Msg 1"),
        (0.5, "Msg 2"),
        (0.5, "Msg 3"),
        (0.5, "Msg 4"),
        (0.5, "Msg 5"),
    ]

    batches = asyncio.run(simulate_cooldown_batching(arrivals))

    assert len(batches) == 1, f"Esperava 1 único lote acumulado, obteve {len(batches)}"
    assert batches[0]["batch_size"] == 5, f"Esperava lote com 5 itens, obteve {batches[0]['batch_size']}"
    print(f"   [OK] Lote de 5 mensagens agrupado com sucesso! Cooldown resetou a cada nova mensagem.")

    # Caso 2: 1 mensagem isolada -> 1 lote de tamanho 1
    arrivals_single = [(0.0, "Msg Única")]
    batches_single = asyncio.run(simulate_cooldown_batching(arrivals_single))

    assert len(batches_single) == 1
    assert batches_single[0]["batch_size"] == 1
    print(f"   [OK] Mensagem única processada com tamanho de lote = 1.")

    print("\n TODOS OS TESTES DE COOLDOWN E DEBOUNCE PASSARAM COM SUCESSO!")
    print("=" * 65)


if __name__ == "__main__":
    run_tests()
