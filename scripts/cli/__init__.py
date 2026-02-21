# -*- coding: utf-8 -*-
"""
Configuration globale du CLI.

Variables d'environnement :
    MCP_URL   — URL du serveur MCP (défaut: http://localhost:8080 via WAF)
    MCP_TOKEN — Token d'authentification (ou ADMIN_BOOTSTRAP_KEY)

Priorité pour le token :
    1. Paramètre --token
    2. Variable MCP_TOKEN
    3. Variable ADMIN_BOOTSTRAP_KEY
    4. Lecture depuis .env (ADMIN_BOOTSTRAP_KEY=...)
"""

import os
from pathlib import Path

BASE_URL = os.environ.get("MCP_URL", "http://localhost:8080")


def _resolve_token() -> str:
    """Résout le token par ordre de priorité."""
    # 1. Variable MCP_TOKEN
    token = os.environ.get("MCP_TOKEN", "")
    if token:
        return token

    # 2. Variable ADMIN_BOOTSTRAP_KEY
    token = os.environ.get("ADMIN_BOOTSTRAP_KEY", "")
    if token:
        return token

    # 3. Lecture depuis .env
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ADMIN_BOOTSTRAP_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()

    return ""


TOKEN = _resolve_token()
