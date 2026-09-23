## 📋 Modelos de Mensagem Monitorados

O script identifica mensagens com ou sem o campo **`Parada`**:

```text
Data: 29/07/2026
Horário: 14:45 horas 
Funcionário: Gaby (Apontadora) / colaborador do St. Lúcia
Motivo: Retorno - Atend. RH/DP / Retorno de atividade 
Origem: Grand View Residence
Parada: Escritório - AC Engenharia  
Destino: Santa Lúcia Park Residence
Valor da viagem: R$ 20,65
Centro de custo: Obra
```

---

## 🎨 Ordem Atualizada das Colunas no Google Sheets

As colunas são inseridas na seguinte ordem na planilha:

1. **Motivo**
2. **Data**
3. **Horário**
4. **Funcionário**
5. **Origem**
6. **Parada** *(deixado em branco caso a viagem não possua parada)*
7. **Destino**
8. **Valor da Viagem**
9. **Centro de Custo**
10. **Data de Registro** *(Timestamp automático)*

---

## 🐳 Executando com Docker & Docker Compose

### Opção 1: Usando Docker Compose (Recomendado)

```bash
docker compose up -d
```

### Opção 2: Construindo a imagem manualmente

```bash
# 1. Construir a imagem
docker build -t uber-webhook .

# 2. Executar o container
docker run -d -p 8000:8000 --env-file .env --name uber_webhook uber-webhook
```

---

## 🚀 Como Configurar e Executar Sem Docker

### 1. Requisitos Prévios
- Python 3.9 ou superior instalado.
- Instância ativa da **Evolution API** (v1 ou v2).
- Conta no Google Cloud com permissão para criar Service Account.

### 2. Instalação das Dependências

No terminal do projeto, execute:

```bash
pip install -r requirements.txt
```

---

### 3. Obtenção das Credenciais do Google Sheets

1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um projeto ou selecione um existente.
3. No menu lateral, acesse **APIs e Serviços > Biblioteca** e ative as seguintes APIs:
   - **Google Sheets API**
   - **Google Drive API**
4. Vá em **APIs e Serviços > Credenciais > Criar Credenciais > Conta de Serviço**.
5. Preencha o nome da conta de serviço e conclua a criação.
6. Clique na Conta de Serviço criada, vá na aba **Chaves > Adicionar Chave > Criar nova chave (JSON)**.
7. O download de um arquivo JSON será feito. Abra este arquivo no seu editor de texto:
   - Copie o valor de `client_email` para a variável `GOOGLE_SERVICE_ACCOUNT_EMAIL` no `.env`.
   - Copie o valor de `private_key` para a variável `GOOGLE_PRIVATE_KEY` no `.env` (mantenha entre aspas duplas com os `\n`).
   - Copie o `project_id` para `GOOGLE_PROJECT_ID`.

---

### 4. Compartilhamento da Planilha

1. Crie uma nova planilha no seu [Google Sheets](https://sheets.google.com).
2. Copie o **ID da Planilha** presente na URL:
   - Exemplo de URL: `https://docs.google.com/spreadsheets/d/1A2B3C4D5E6F7G8H9I0J/edit`
   - O ID é `1A2B3C4D5E6F7G8H9I0J`.
3. Clique no botão **Compartilhar** no canto superior direito da planilha e adicione o e-mail da sua Conta de Serviço (o mesmo `GOOGLE_SERVICE_ACCOUNT_EMAIL`) como **Editor**.

---

### 5. Configuração do Arquivo `.env`

Crie um arquivo `.env` na raiz do projeto (ou copie do modelo `.env.example`):

```bash
cp .env.example .env
```

Preencha as variáveis no arquivo `.env`:

```env
# Servidor Webhook
HOST=0.0.0.0
PORT=8000
WEBHOOK_TOKEN=seu_token_secreto_opcional

# Credenciais do Google Cloud
GOOGLE_SERVICE_ACCOUNT_EMAIL=seu-servico@seu-projeto.iam.gserviceaccount.com
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nSUA_CHAVE_PRIVADA_AQUI\n-----END PRIVATE KEY-----\n"
GOOGLE_PROJECT_ID=seu-projeto-id

# Planilha
SPREADSHEET_ID=seu_spreadsheet_id_aqui
SHEET_NAME=Página1

# Filtro de Grupo (Opcional - deixe em branco para aceitar qualquer grupo)
TARGET_GROUP_JID=12036301234567890@g.us
```

---

### 6. Execução do Servidor Webhook

Execute o servidor localmente:

```bash
python main.py
```

Ou usando `uvicorn`:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 7. Configuração da Evolution API

Na sua instância da Evolution API, configure a URL do Webhook apontando para o seu servidor na rota `/webhook`:

- **URL do Webhook**: `http://seu-servidor-ou-ip:8000/webhook` (ou usando **ngrok**: `https://xxxx.ngrok-free.app/webhook`)
- **Eventos ativos**: `MESSAGES_UPSERT`

---

## 🧪 Testando Localmente

Para validar o funcionamento da extração de dados sem precisar acionar a Evolution API, rode o script de teste:

```bash
python test_local.py
```

---

## 📁 Estrutura de Arquivos

```text
Uber/
├── config.py           # Carregador de configurações do .env
├── google_sheets.py    # Cliente do Google Sheets com estilização e inserção de dados
├── parser.py           # Regex Parser e extrator do payload da Evolution API
├── main.py             # Servidor Webhook FastAPI
├── test_local.py       # Script de teste de parsing local
├── requirements.txt    # Dependências do projeto
├── .env.example        # Modelo de variáveis de ambiente
└── README.md           # Guia do usuário
```
