# Use uma imagem base Debian com Python e Playwright pré-configurada
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Define diretório de trabalho
WORKDIR /app

# Copia requirements primeiro (para cache)
COPY requirements.txt .

# Atualiza pip e instala dependências Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instala os browsers do Playwright explicitamente (essencial!)
RUN playwright install --with-deps chromium

# Copia o código do bot
COPY . .

# Comando para rodar o bot (ajuste o nome do arquivo se necessário)
CMD ["python", "app.py"]
