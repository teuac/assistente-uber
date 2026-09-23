import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "")

# Configurações opcionais da Evolution API (para envio de resposta automática)
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
EVOLUTION_INSTANCE_NAME = os.getenv("EVOLUTION_INSTANCE_NAME", "")

# Configurações do Google Sheets
GOOGLE_SERVICE_ACCOUNT_EMAIL = os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL", "")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "")
SHEET_NAME = os.getenv("SHEET_NAME", "Página1")

# Filtro de grupo opcional (ex: 12036301234567890@g.us)
TARGET_GROUP_JID = os.getenv("TARGET_GROUP_JID", "").strip()


def get_google_credentials_dict() -> dict:
    """
    Retorna o dicionário de credenciais da Service Account do Google Cloud.
    Gera o formato exigido pela biblioteca google-auth a partir do .env.
    """
    if not GOOGLE_SERVICE_ACCOUNT_EMAIL or not GOOGLE_PRIVATE_KEY:
        raise ValueError(
            "As variáveis GOOGLE_SERVICE_ACCOUNT_EMAIL e GOOGLE_PRIVATE_KEY devem estar preenchidas no .env!"
        )

    return {
        "type": "service_account",
        "project_id": GOOGLE_PROJECT_ID or "default-project",
        "private_key_id": "env_private_key",
        "private_key": GOOGLE_PRIVATE_KEY,
        "client_email": GOOGLE_SERVICE_ACCOUNT_EMAIL,
        "client_id": "",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{GOOGLE_SERVICE_ACCOUNT_EMAIL}",
    }
