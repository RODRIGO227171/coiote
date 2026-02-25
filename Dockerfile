# =============================================================================
# Dockerfile completo e corrigido para bot Telegram + Playwright
# Resolve erro: "Executable doesn't exist at /ms-playwright/chromium_headless_shell-..."
# =============================================================================

# Imagem base leve: Python 3.11 + Debian Bookworm slim
FROM python:3.11-slim-bookworm

# Define diretório de trabalho
WORKDIR /app

# Instala dependências do sistema necessárias para o Chromium/Playwright
# (essencial para evitar erro de executável faltando)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    libxshmfence1 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements.txt primeiro (para melhor cache de layers)
COPY requirements.txt .

# Atualiza pip e instala as dependências Python
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Instala Playwright e força o download + instalação do Chromium com dependências
RUN pip install playwright && \
    playwright install --with-deps chromium

# Copia todo o código do projeto (seu bot.py / docker.py / etc.)
COPY . .

# (Opcional) Define variáveis de ambiente úteis para Playwright em containers
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright/ms-playwright

# Expõe porta (não obrigatório para bots polling, mas bom ter)
EXPOSE 8000

# Comando para iniciar o bot
# Ajuste o nome do arquivo principal conforme o seu!
# Exemplos:
# - Se o arquivo se chama docker.py: CMD ["python", "docker.py"]
# - Se se chama bot.py: CMD ["python", "bot.py"]
# - Se se chama gate_deep_js_server.py: CMD ["python", "gate_deep_js_server.py"]
CMD ["python", "app.py"]
