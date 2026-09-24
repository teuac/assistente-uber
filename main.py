import logging
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, Header
from starlette.background import BackgroundTask
from fastapi.responses import JSONResponse
import uvicorn

import config
from parser import extract_message_info, parse_reimbursement_message
from google_sheets import GoogleSheetsClient

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("evolution_webhook")

app = FastAPI(
    title="Evolution API -> Google Sheets Monitor",
    description="Servidor Webhook para monitorar mensagens de reembolso/viagem no WhatsApp via Evolution API e registrar no Google Sheets",
    version="1.0.0"
)

# Instância Global do Cliente Google Sheets
sheets_client = GoogleSheetsClient()


@app.on_event("startup")
def startup_event():
    logger.info("Iniciando servidor Webhook da Evolution API...")
    if not config.SPREADSHEET_ID:
        logger.warning(
            "ATENÇÃO: SPREADSHEET_ID não está configurado no arquivo .env. Configure para habilitar o registro na planilha."
        )


def send_whatsapp_confirmation(remote_jid: str, message_key: dict, message_obj: dict, max_retries: int = 3):
    """Envia a mensagem 'Viagem Registrada na Planilha' marcando/citando a mensagem original via Evolution API com retries."""
    if not (config.EVOLUTION_API_URL and config.EVOLUTION_API_KEY and config.EVOLUTION_INSTANCE_NAME):
        logger.warning("Credenciais da Evolution API não estão totalmente configuradas no .env. Não será possível enviar a resposta no grupo.")
        return

    import json
    import urllib.request
    import time

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


def process_and_log_message(remote_jid: str, message_key: dict, message_obj: dict, parsed_data: dict):
    """Função executada em background para enviar os dados à planilha e responder marcando a mensagem."""
    try:
        sheets_client.append_reimbursement(parsed_data)
        if remote_jid and message_key:
            send_whatsapp_confirmation(remote_jid, message_key, message_obj)
    except Exception as e:
        logger.error(f"Erro ao processar e registrar mensagem na planilha Google Sheets: {e}", exc_info=True)


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "Evolution API -> Google Sheets Monitor",
        "version": "1.0.0"
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

    # Tenta fazer o parsing da mensagem de acordo com o modelo de viagem/reembolso
    parsed_data = parse_reimbursement_message(text)

    if not parsed_data:
        snippet = text.replace('\n', ' ')[:100]
        logger.warning(f"Mensagem ignorada por formato não reconhecido (Primeiros 100 caracteres): '{snippet}'")
        return JSONResponse(
            status_code=200,
            content={"status": "ignored", "reason": "Formato de mensagem não reconhecido"}
        )

    logger.info(f"Mensagem válida identificada! Funcionário: {parsed_data.get('funcionario')}, Valor: {parsed_data.get('valor')}")

    # Processa, registra na planilha e responde no WhatsApp citando a mensagem original
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Mensagem de viagem processada com sucesso",
            "data": parsed_data
        },
        background=BackgroundTask(process_and_log_message, remote_jid, message_key, message_obj, parsed_data)
    )


if __name__ == "__main__":
    logger.info(f"Servidor rodando em http://{config.HOST}:{config.PORT}")
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)
