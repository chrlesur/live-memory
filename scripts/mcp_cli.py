#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Point d'entrée CLI du service MCP.

Usage :
    python scripts/mcp_cli.py --help
    python scripts/mcp_cli.py health
    python scripts/mcp_cli.py about
    python scripts/mcp_cli.py shell

Variables d'environnement :
    MCP_URL   — URL du serveur (défaut: http://localhost:8002)
    MCP_TOKEN — Token d'authentification
"""

import sys
from pathlib import Path

# Ajouter le répertoire parent au path pour les imports relatifs
sys.path.insert(0, str(Path(__file__).parent))

from cli.commands import cli

if __name__ == "__main__":
    cli()
