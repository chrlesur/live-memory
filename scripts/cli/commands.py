# -*- coding: utf-8 -*-
"""
CLI Click — Couche 2 : commandes scriptables.

Point d'entrée : le groupe `cli` est importé par mcp_cli.py.
Chaque commande appelle un outil MCP via MCPClient puis affiche via display.py.

Usage :
    python scripts/mcp_cli.py health
    python scripts/mcp_cli.py about
    python scripts/mcp_cli.py shell
"""

import asyncio
import click
from . import BASE_URL, TOKEN
from .client import MCPClient
from .display import (
    console, show_error, show_success,
    show_health_result, show_about_result, show_json,
)


@click.group()
@click.option(
    "--url", "-u",
    envvar=["MCP_URL"],
    default=BASE_URL,
    help="URL du serveur MCP",
)
@click.option(
    "--token", "-t",
    envvar=["MCP_TOKEN"],
    default=TOKEN,
    help="Token d'authentification",
)
@click.pass_context
def cli(ctx, url, token):
    """🔧 CLI pour le service MCP."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["token"] = token


# =============================================================================
# Commandes système (incluses dans le boilerplate)
# =============================================================================

@cli.command("health")
@click.option("--json", "-j", "output_json", is_flag=True, help="Sortie JSON brute")
@click.pass_context
def health_cmd(ctx, output_json):
    """❤️  Vérifier l'état de santé du service."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await client.call_tool("system_health", {})
            if output_json:
                show_json(result)
            elif result.get("status") == "ok":
                show_health_result(result)
            else:
                show_error(result.get("message", "Service indisponible"))
        except Exception as e:
            show_error(f"Connexion impossible: {e}")
    asyncio.run(_run())


@cli.command("about")
@click.option("--json", "-j", "output_json", is_flag=True, help="Sortie JSON brute")
@click.pass_context
def about_cmd(ctx, output_json):
    """ℹ️  Informations sur le service MCP."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await client.call_tool("system_about", {})
            if output_json:
                show_json(result)
            elif result.get("status") == "ok":
                show_about_result(result)
            else:
                show_error(result.get("message", "Erreur"))
        except Exception as e:
            show_error(f"Connexion impossible: {e}")
    asyncio.run(_run())


@cli.command("shell")
@click.pass_context
def shell_cmd(ctx):
    """🐚 Lancer le shell interactif."""
    from .shell import run_shell
    asyncio.run(run_shell(ctx.obj["url"], ctx.obj["token"]))


# =============================================================================
# Ajouter vos commandes métier ici
# =============================================================================
# Exemple :
#
# @cli.command("mon-outil")
# @click.argument("resource_id")
# @click.option("--param", "-p", required=True)
# @click.pass_context
# def mon_outil_cmd(ctx, resource_id, param):
#     """🔧 Description courte."""
#     async def _run():
#         client = MCPClient(ctx.obj["url"], ctx.obj["token"])
#         result = await client.call_tool("mon_outil", {
#             "resource_id": resource_id, "param": param
#         })
#         if result.get("status") == "ok":
#             show_mon_outil_result(result)
#         else:
#             show_error(result.get("message", "Erreur"))
#     asyncio.run(_run())
