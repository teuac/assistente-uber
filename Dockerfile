# Usar imagem oficial leve do Python
FROM python:3.11-slim

# Garante saída limpa de logs e impede geração de arquivos bytecode .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Define o diretório de trabalho no container
WORKDIR /app

# Copia e instala as dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código fonte do projeto
COPY . .

# Expõe a porta 8000
EXPOSE 8000

# Comando para iniciar a aplicação
CMD ["python", "main.py"]
