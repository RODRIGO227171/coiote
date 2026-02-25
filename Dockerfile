# Imagem oficial com Python 3.11 + Playwright + Chromium headless já instalados
# Isso resolve a maioria dos problemas com playwright em containers
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Copia requirements.txt primeiro (para cache de layers no build)
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto (incluindo seu .py principal)
COPY . .

# Comando para iniciar o bot - AJUSTE O NOME DO ARQUIVO AQUI!
# Se seu script se chama gate_deep_js_server.py, use isso:
CMD ["python", "app.py"]
# Se for app.py (como no log), use: CMD ["python", "app.py"]]
