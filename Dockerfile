# =============================================================================
# Dockerfile — Live Memory MCP Server (rootless)
# =============================================================================
# Image Python 3.11 slim avec le serveur MCP Live Memory.
# Le conteneur tourne en utilisateur non-root (mcp, UID 10001).
# Aucune opération root après le USER — 100% rootless.
#
# Usage :
#   docker compose build
#   docker compose up -d
# =============================================================================

FROM python:3.11-slim

WORKDIR /app

# Créer l'utilisateur non-root AVANT tout COPY
RUN useradd -r -u 10001 -s /bin/false mcp

# Dépendances Python (en premier pour profiter du cache Docker)
COPY --chown=mcp:mcp requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code source — copié directement avec les bons droits
COPY --chown=mcp:mcp src/ src/
COPY --chown=mcp:mcp scripts/ scripts/
COPY --chown=mcp:mcp RULES/ RULES/
COPY --chown=mcp:mcp VERSION .

# Le module live_mem est dans src/ → ajouter au PYTHONPATH
ENV PYTHONPATH=/app/src

# Basculer sur l'utilisateur non-root (rootless)
USER mcp

EXPOSE 8002

# Healthcheck : vérifier que le serveur répond sur /health
# (pas de curl dans slim → utiliser python)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health', timeout=2)" || exit 1

# Point d'entrée : le serveur MCP
CMD ["python", "-m", "live_mem"]
