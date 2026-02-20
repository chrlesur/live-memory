# -*- coding: utf-8 -*-
"""
Serveur MCP — Point d'entrée principal.

Ce fichier :
1. Crée l'instance FastMCP
2. Déclare les outils MCP (@mcp.tool())
3. Assemble la chaîne de middlewares ASGI
4. Démarre le serveur Uvicorn

Usage :
    python -m live_mem.server
"""

import sys
import time
import platform
from typing import Optional
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Context

from .config import get_settings
from .auth.context import check_access, check_write_permission

# =============================================================================
# Instance FastMCP
# =============================================================================

settings = get_settings()

mcp = FastMCP(
    name=settings.mcp_server_name,
    host=settings.mcp_server_host,
    port=settings.mcp_server_port,
)


# =============================================================================
# Getters lazy-load pour les services métier
# =============================================================================
# Ajouter ici vos services (base de données, APIs externes, etc.)
# Ne JAMAIS instancier au top-level — toujours via getter singleton.

# _my_db = None
# def get_db():
#     global _my_db
#     if _my_db is None:
#         from .core.database import DatabaseService
#         _my_db = DatabaseService()
#     return _my_db


# =============================================================================
# Outils MCP — Système (inclus dans le boilerplate)
# =============================================================================

@mcp.tool()
async def system_health() -> dict:
    """
    Vérifie l'état de santé du service.

    Retourne le statut de chaque service backend.
    Cet outil ne nécessite aucune authentification.

    Returns:
        État global du système et détails par service
    """
    results = {}

    # TODO: Ajouter vos checks de services métier ici
    # Exemple :
    # try:
    #     results["database"] = await get_db().test_connection()
    # except Exception as e:
    #     results["database"] = {"status": "error", "message": str(e)}

    # Service factice pour le boilerplate
    results["server"] = {"status": "ok", "uptime": "running"}

    all_ok = all(r.get("status") == "ok" for r in results.values())

    return {
        "status": "ok" if all_ok else "error",
        "service_name": settings.mcp_server_name,
        "services": results,
    }


@mcp.tool()
async def system_about() -> dict:
    """
    Informations sur le service MCP.

    Retourne la version, les outils disponibles, et les infos système.
    Cet outil ne nécessite aucune authentification.

    Returns:
        Métadonnées du service
    """
    # Lire la version depuis le fichier VERSION
    version = "dev"
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    if version_file.exists():
        version = version_file.read_text().strip()

    # Lister les outils MCP disponibles
    tools = []
    for tool in mcp._tool_manager.list_tools():
        tools.append({
            "name": tool.name,
            "description": (tool.description or "")[:100],
        })

    return {
        "status": "ok",
        "service_name": settings.mcp_server_name,
        "version": version,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "tools_count": len(tools),
        "tools": tools,
    }


# =============================================================================
# Outils MCP — Votre domaine métier
# =============================================================================
# Ajouter vos outils ici. Chaque outil suit le pattern :
#
# @mcp.tool()
# async def mon_outil(param: str, ctx: Optional[Context] = None) -> dict:
#     """Docstring visible par les agents IA."""
#     try:
#         access_err = check_access(resource_id)
#         if access_err:
#             return access_err
#         result = await get_my_service().do_something(param)
#         return {"status": "ok", "data": result}
#     except Exception as e:
#         return {"status": "error", "message": str(e)}


# =============================================================================
# Assemblage ASGI — Chaîne de middlewares
# =============================================================================

def create_app():
    """
    Crée l'application ASGI complète avec les middlewares.

    Pile d'exécution :
        AuthMiddleware → LoggingMiddleware → HostNormalizerMiddleware → mcp.sse_app()
    """
    from .auth.middleware import AuthMiddleware, LoggingMiddleware, HostNormalizerMiddleware

    # L'app de base est le SSE handler du SDK MCP
    app = mcp.sse_app()

    # Empiler les middlewares (dernier ajouté = premier exécuté)
    app = HostNormalizerMiddleware(app)
    app = LoggingMiddleware(app)
    app = AuthMiddleware(app)

    return app


# =============================================================================
# Point d'entrée
# =============================================================================

def main():
    """Démarre le serveur MCP."""
    import uvicorn

    print(f"""
╔══════════════════════════════════════════════╗
║   {settings.mcp_server_name:^40s}   ║
╠══════════════════════════════════════════════╣
║                                              ║
║  🔧 Outils disponibles :                    ║
║    - system_health                           ║
║    - system_about                            ║
║                                              ║
║  🌐 Serveur : http://{settings.mcp_server_host}:{settings.mcp_server_port:<5d}             ║
║  📡 SSE     : http://{settings.mcp_server_host}:{settings.mcp_server_port:<5d}/sse          ║
║                                              ║
╚══════════════════════════════════════════════╝
""", file=sys.stderr)

    app = create_app()

    uvicorn.run(
        app,
        host=settings.mcp_server_host,
        port=settings.mcp_server_port,
        log_level="warning",  # Uvicorn en mode silencieux (on log via middleware)
    )


if __name__ == "__main__":
    main()
