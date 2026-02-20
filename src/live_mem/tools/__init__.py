# -*- coding: utf-8 -*-
"""
Package tools — Enregistrement des outils MCP par catégorie.

Chaque module (system, space, live, bank, backup, admin) expose
une fonction `register(mcp)` qui déclare ses outils via @mcp.tool().

Cette architecture maintient chaque fichier sous 500 lignes
tout en gardant une organisation claire par domaine fonctionnel.

Usage dans server.py :
    from .tools import register_all_tools
    register_all_tools(mcp)
"""

from mcp.server.fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> int:
    """
    Enregistre tous les outils MCP depuis les modules de catégorie.

    Args:
        mcp: Instance FastMCP sur laquelle enregistrer les outils

    Returns:
        Nombre total d'outils enregistrés
    """
    # Importer et enregistrer chaque catégorie
    from .system import register as register_system
    from .space import register as register_space
    from .live import register as register_live
    from .bank import register as register_bank
    from .backup import register as register_backup
    from .admin import register as register_admin

    count = 0
    count += register_system(mcp)
    count += register_space(mcp)
    count += register_live(mcp)
    count += register_bank(mcp)
    count += register_backup(mcp)
    count += register_admin(mcp)

    return count
