import logging
from typing import Dict, Any, Optional
import base64
import json
import urllib.request
import time
import asyncio

from fastapi import FastAPI, Request, HTTPException, Header
from starlette.background import BackgroundTask
from fastapi.responses import JSONResponse
import uvicorn

import config
from parser import extract_message_info, parse_reimbursement_message, parse_export_command
from google_sheets import GoogleSheetsClient, filter_records_by_date_range
import excel_generator
from excel_generator import create_styled_reimbursement_excel

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("evolution_webhook")

from contextlib import asynccontextmanager


# Instância Global do Cliente Google Sheets
sheets_client = GoogleSheetsClient()

# Fila assíncrona em memória (inicializada lazily dentro do event loop do servidor)
reimbursement_queue: Optional[asyncio.Queue] = None



def get_reimbursement_queue() -> asyncio.Queue:
    """Garante que a fila asyncio.Queue esteja vinculada ao event loop ativo do Uvicorn/FastAPI."""
    global reimbursement_queue
    if reimbursement_queue is None:
        reimbursement_queue = asyncio.Queue()
    return reimbursement_queue


async def reimbursement_worker():
    """
    Worker assíncrono com Cooldown (Debounce) de 15 segundos (configurável via config.COOLDOWN_SECONDS).
    Toda vez que uma nova mensagem chega na fila, o temporizador de 15s é resetado.
    Quando se passam 15 segundos sem nenhuma mensagem nova, o worker envia todo o lote acumulado ao Google Sheets 
    em 1 única requisição HTTP.
    
    Regra de Resposta no WhatsApp:
    - Se o lote contiver 1 mensagem: Responde citando/marcando a mensagem original com 'Viagem Registrada na Planilha ✅'.
    - Se o lote contiver mais de 1 mensagem: Em vez de marcar 1 por 1, envia 1 ÚNICA mensagem no grupo confirmando a quantidade total.
    """
    cooldown = config.COOLDOWN_SECONDS
    logger.info(f"Worker assíncrono iniciado com Cooldown de {cooldown}s (reset dinâmico por nova mensagem).")
    queue = get_reimbursement_queue()

    while True:
        try:
            # 1. Aguarda a primeira mensagem da rajada chegar na fila
            first_item = await queue.get()
            batch = [first_item]
            loop = asyncio.get_running_loop()
            last_activity = loop.time()

            logger.info(f"Primeira mensagem do lote recebida. Iniciando contagem de {cooldown}s de cooldown...")

            # 2. Loop de Debounce: Reseta o temporizador toda vez que uma nova mensagem entra na fila
            while True:
                now = loop.time()
                elapsed = now - last_activity
                remaining = cooldown - elapsed

                if remaining <= 0:
                    # Se passaram 15s sem nenhuma mensagem nova, encerra a espera
                    break

                try:
                    # Aguarda a próxima mensagem por no máximo 'remaining' segundos
                    next_item = await asyncio.wait_for(queue.get(), timeout=remaining)
                    batch.append(next_item)
                    last_activity = loop.time()  # Reseta os 15 segundos!
                    logger.info(f"Nova mensagem recebida no lote (Total acumulado: {len(batch)}). Cooldown de {cooldown}s resetado!")
                except asyncio.TimeoutError:
                    # Estourou o tempo de 15s sem novas mensagens
                    break

            logger.info(f"Cooldown de {cooldown}s finalizado! Processando lote com {len(batch)} mensagem(ns) no Google Sheets...")

            # 3. Insere todas as mensagens na planilha em 1 única requisição HTTP em thread pool separada
            data_list = [item["parsed_data"] for item in batch]
            success = False
            try:
                await asyncio.to_thread(sheets_client.append_reimbursements_batch, data_list)
                success = True
            except Exception as e:
                logger.error(f"Erro ao inserir lote de {len(batch)} mensagens no Google Sheets: {e}", exc_info=True)
                # Fallback: Tenta salvar individualmente se o lote falhar por qualquer motivo
                for item in batch:
                    try:
                        await asyncio.to_thread(sheets_client.append_reimbursement, item["parsed_data"])
                        success = True
                    except Exception as ex:
                        logger.error(f"Erro no fallback individual para {item['parsed_data'].get('funcionario')}: {ex}")

            # 4. Envio de Confirmação no WhatsApp
            if success:
                remote_jid = batch[0].get("remote_jid")

                if len(batch) == 1:
                    # Apenas 1 mensagem recebida: marca/cita a mensagem original no WhatsApp
                    item = batch[0]
                    message_key = item.get("message_key")
                    message_obj = item.get("message_obj")
                    if remote_jid and message_key:
                        try:
                            await asyncio.to_thread(send_whatsapp_confirmation, remote_jid, message_key, message_obj)
                        except Exception as e:
                            logger.warning(f"Erro ao enviar confirmação citada no WhatsApp: {e}")
                else:
                    # Múltiplas mensagens (2 ou mais): envia UMA ÚNICA mensagem no grupo confirmando a quantidade enviada
                    count = len(batch)
                    total_val = sum(
                        excel_generator._clean_price_value(r["parsed_data"].get("valor", ""))
                        for r in batch
                    )
                    val_formatted = f"R$ {total_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    group_summary = (
                        f"✅ *{count} viagens foram registradas com sucesso na planilha!*\n\n"
                        f"📊 *Lote Processado:* {count} lançamentos\n"
                        f"💰 *Valor Total do Lote:* {val_formatted}"
                    )
                    if remote_jid:
                        try:
                            await asyncio.to_thread(send_whatsapp_text, remote_jid, group_summary)
                            logger.info(f"Mensagem resumida enviada ao grupo para o lote de {count} mensagens.")
                        except Exception as e:
                            logger.warning(f"Erro ao enviar mensagem de resumo do lote no WhatsApp: {e}")

            # Desmarca as tarefas da fila
            for _ in range(len(batch)):
                queue.task_done()

        except Exception as e:
            logger.error(f"Erro inesperado no worker de reembolso: {e}", exc_info=True)
            await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciador do ciclo de vida da aplicação FastAPI."""
    logger.info("Iniciando servidor Webhook da Evolution API...")
    if not config.SPREADSHEET_ID:
        logger.warning(
            "ATENÇÃO: SPREADSHEET_ID não está configurado no arquivo .env. Configure para habilitar o registro na planilha."
        )

    # Inicializa a fila dentro do event loop ativo do servidor
    get_reimbursement_queue()
    worker_task = asyncio.create_task(reimbursement_worker())

    yield

    worker_task.cancel()


app = FastAPI(
    title="Evolution API -> Google Sheets Monitor",
    description="Servidor Webhook para monitorar mensagens de reembolso/viagem no WhatsApp via Evolution API e registrar no Google Sheets",
    version="1.2.0",
    lifespan=lifespan
)


def send_whatsapp_text(remote_jid: str, text: str, max_retries: int = 3) -> bool:
    """Envia uma mensagem de texto direta para o WhatsApp via Evolution API."""
    if not (config.EVOLUTION_API_URL and config.EVOLUTION_API_KEY and config.EVOLUTION_INSTANCE_NAME):
        logger.warning("Credenciais da Evolution API não estão totalmente configuradas no .env. Não foi possível enviar texto.")
        return False

    endpoint = f"{config.EVOLUTION_API_URL}/message/sendText/{config.EVOLUTION_INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": config.EVOLUTION_API_KEY
    }

    payload = {
        "number": remote_jid,
        "text": text
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in (200, 201):
                    return True
        except Exception as e:
            logger.warning(f"Tentativa {attempt}/{max_retries} de enviar texto via WhatsApp falhou: {e}")
            if attempt < max_retries:
                time.sleep(1.0)
    return False


def send_whatsapp_file(remote_jid: str, file_path: str, filename: str, caption: str, max_retries: int = 3) -> bool:
    """Envia um arquivo (documento Excel) em anexo para o WhatsApp via Evolution API."""
    if not (config.EVOLUTION_API_URL and config.EVOLUTION_API_KEY and config.EVOLUTION_INSTANCE_NAME):
        logger.warning("Credenciais da Evolution API não estão totalmente configuradas. Não foi possível enviar o arquivo.")
        return False

    try:
        with open(file_path, "rb") as f:
            encoded_media = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Erro ao ler arquivo para envio no WhatsApp: {e}")
        return False

    media_data = f"data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{encoded_media}"
    endpoint = f"{config.EVOLUTION_API_URL}/message/sendMedia/{config.EVOLUTION_INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": config.EVOLUTION_API_KEY
    }

    payload = {
        "number": remote_jid,
        "media": media_data,
        "mediatype": "document",
        "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "fileName": filename,
        "caption": caption
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status in (200, 201):
                    logger.info(f"Arquivo '{filename}' enviado com sucesso via WhatsApp para {remote_jid}")
                    return True
        except Exception as e:
            logger.warning(f"Tentativa {attempt}/{max_retries} de enviar arquivo via Evolution API falhou: {e}")
            if attempt < max_retries:
                time.sleep(1.5)
            else:
                logger.error(f"Erro ao enviar arquivo via Evolution API após {max_retries} tentativas: {e}")

    return False


def send_whatsapp_confirmation(remote_jid: str, message_key: dict, message_obj: dict, max_retries: int = 3):
    """Envia a mensagem 'Viagem Registrada na Planilha' marcando/citando a mensagem original via Evolution API com retries."""
    if not (config.EVOLUTION_API_URL and config.EVOLUTION_API_KEY and config.EVOLUTION_INSTANCE_NAME):
        logger.warning("Credenciais da Evolution API não estão totalmente configuradas no .env. Não será possível enviar a resposta no grupo.")
        return

    endpoint = f"{config.EVOLUTION_API_URL}/message/sendText/{config.EVOLUTION_INSTANCE_NAME}"
    headers = {
        "Content-Type": "application/json",
        "apikey": config.EVOLUTION_API_KEY
    }

    payload = {
        "number": remote_jid,
        "text": "Viagem Registrada na Planilha ✅",
        "quoted": {
            "key": message_key,
            "message": message_obj
        }
    }

    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status in (200, 201):
                    logger.info(f"Resposta 'Viagem Registrada na Planilha' enviada marcando a mensagem original em {remote_jid}")
                    return
        except Exception as e:
            logger.warning(f"Tentativa {attempt}/{max_retries} de enviar confirmação no WhatsApp falhou: {e}")
            if attempt < max_retries:
                time.sleep(1.0)
            else:
                logger.error(f"Erro ao enviar resposta citada via Evolution API após {max_retries} tentativas: {e}")


def process_and_send_export(remote_jid: str, export_info: dict):
    """
    Função executada em background para gerar e enviar a planilha mensal filtrada por data.
    """
    start_str = export_info.get("start_str", "")
    end_str = export_info.get("end_str", "")
    start_date = export_info.get("start_date")
    end_date = export_info.get("end_date")

    try:
        send_whatsapp_text(
            remote_jid, 
            f"⏳ Gerando planilha de viagens para o período *{start_str} até {end_str}*...\nAguarde um instante."
        )

        all_records = sheets_client.fetch_all_records()
        filtered_records = filter_records_by_date_range(all_records, start_date, end_date)

        xlsx_path = create_styled_reimbursement_excel(filtered_records, start_str, end_str)

        total_viagens = len(filtered_records)
        total_valor = sum(
            excel_generator._clean_price_value(r.get("Valor da Viagem", r.get("valor", ""))) 
            for r in filtered_records
        )
        valor_formatted = f"R$ {total_valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

        caption = (
            f"📊 *Planilha Mensal de Viagens e Reembolsos*\n\n"
            f"📅 *Período:* {start_str} a {end_str}\n"
            f"🚗 *Total de Viagens:* {total_viagens}\n"
            f"💰 *Valor Total:* {valor_formatted}\n\n"
            f"Segue em anexo a planilha estilizada para download."
        )

        safe_start = start_str.replace("/", "-")
        safe_end = end_str.replace("/", "-")
        filename = f"Planilha_Viagens_{safe_start}_a_{safe_end}.xlsx"

        send_whatsapp_file(remote_jid, xlsx_path, filename, caption)

    except Exception as e:
        logger.error(f"Erro ao processar exportação de planilha para {remote_jid}: {e}", exc_info=True)
        send_whatsapp_text(
            remote_jid,
            f"❌ Erro ao gerar planilha do período {start_str} a {end_str}: {e}"
        )


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Evolution API -> Google Sheets Monitor",
        "version": "1.2.0"
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/")
@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="x-api-key")
):
    """
    Endpoint chamado pela Evolution API quando novas mensagens chegam.
    """
    # Validação opcional de Token de segurança
    if config.WEBHOOK_TOKEN:
        if x_api_key != config.WEBHOOK_TOKEN and request.query_params.get("token") != config.WEBHOOK_TOKEN:
            logger.warning("Tentativa de acesso ao Webhook com token inválido!")
            raise HTTPException(status_code=401, detail="Token de autorização inválido.")

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Erro ao ler corpo da requisição JSON: {e}")
        raise HTTPException(status_code=400, detail="JSON inválido")

    # Extrai informações da mensagem
    text, remote_jid, from_me, message_key, message_obj = extract_message_info(payload)

    if not text:
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Mensagem vazia ou tipo não suportado"}
        )

    # Ignora mensagens enviadas pelo próprio bot (opcional)
    if from_me:
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Mensagem enviada pelo próprio usuário/bot"}
        )

    # Filtra por grupo específico se configurado
    if config.TARGET_GROUP_JID and remote_jid != config.TARGET_GROUP_JID:
        logger.info(f"Mensagem recebida de {remote_jid}, ignorando pois o grupo alvo é {config.TARGET_GROUP_JID}")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Mensagem fora do grupo alvo"}
        )

    # 1. Verifica se a mensagem é um comando de EXPORTAÇÃO DE PLANILHA (ex: "K/ planilha mensal 02/02/2026 - 02/03/2026")
    export_info = parse_export_command(text)
    if export_info:
        logger.info(f"Comando de exportação recebido de {remote_jid}! Intervalo: {export_info['start_str']} a {export_info['end_str']}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Solicitação de exportação de planilha recebida com sucesso",
                "export": {
                    "start": export_info["start_str"],
                    "end": export_info["end_str"]
                }
            },
            background=BackgroundTask(process_and_send_export, remote_jid, export_info)
        )

    # 2. Tenta fazer o parsing da mensagem de acordo com o modelo de viagem/reembolso
    parsed_data = parse_reimbursement_message(text)

    if not parsed_data:
        snippet = text.replace('\n', ' ')[:100]
        logger.warning(f"Mensagem ignorada por formato não reconhecido (Primeiros 100 caracteres): '{snippet}'")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Formato de mensagem não reconhecido"}
        )

    logger.info(f"Mensagem válida identificada! Funcionário: {parsed_data.get('funcionario')}, Valor: {parsed_data.get('valor')}")

    # Adiciona a mensagem na fila do worker assíncrono para processamento em lote
    queue = get_reimbursement_queue()
    await queue.put({
        "remote_jid": remote_jid,
        "message_key": message_key,
        "message_obj": message_obj,
        "parsed_data": parsed_data
    })
    logger.info(f"Mensagem enfileirada com sucesso! Tamanho atual da fila de lote: {queue.qsize()}")

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Mensagem de viagem enfileirada com sucesso",
            "data": parsed_data
        }
    )


if __name__ == "__main__":
    logger.info(f"Servidor rodando em http://{config.HOST}:{config.PORT}")
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=False)


