# -*- coding: utf-8 -*-
"""
Configuration globale du CLI.

Variables d'environnement :
    MCP_URL   — URL du serveur MCP (défaut: http://localhost:8002)
    MCP_TOKEN — Token d'authentification
"""

import os

BASE_URL = os.environ.get("MCP_URL", "http://localhost:8002")
TOKEN = os.environ.get("MCP_TOKEN", "")
