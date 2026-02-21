# =============================================================================
# Dockerfile — Live Memory MCP Server
# =============================================================================
# Image Python 3.11 slim avec le serveur MCP Live Memory.
# Le code source est dans src/live_mem/, lancé via python -m live_mem.
#
# Usage :
#   docker compose build
#   docker compose up -d
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Dépendances Python (en premier pour profiter du cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source
COPY src/ src/
COPY scripts/ scripts/
COPY VERSION .

# Le module live_mem est dans src/ → ajouter au PYTHONPATH
ENV PYTHONPATH=/app/src

# Sécurité : utilisateur non-root
RUN useradd -r -s /bin/false mcp
USER mcp

EXPOSE 8002

# Point d'entrée : le serveur MCP
# Équivalent de : cd src && python -m live_mem
CMD ["python", "-m", "live_mem"]
