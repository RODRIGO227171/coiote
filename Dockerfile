# =============================================================================
# Dockerfile FINAL - Usa imagem oficial Playwright Python (resolve missing executable)
# =============================================================================

# Imagem oficial com Python + Playwright + Chromium headless + deps já instalados
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Define diretório de trabalho
WORKDIR /app

# Copia requirements.txt primeiro para cache eficiente
COPY requirements.txt .

# Instala dependências Python (sem cache para reduzir tamanho)
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do bot
COPY . .

# (Opcional) Define variável para garantir path dos browsers (já vem certo na imagem)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Comando para iniciar o bot
# Ajuste o nome do arquivo principal se NÃO for docker.py
CMD ["python", "app.py"]
