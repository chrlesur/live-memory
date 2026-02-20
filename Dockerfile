FROM python:3.11-slim

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY src/ src/
COPY scripts/ scripts/
COPY VERSION .

# Sécurité : utilisateur non-root
RUN useradd -r -s /bin/false mcp
USER mcp

EXPOSE 8002

# Point d'entrée : le serveur MCP
# Adapter "live_mem" au nom réel de votre package
CMD ["python", "-m", "src.live_mem.server"]
