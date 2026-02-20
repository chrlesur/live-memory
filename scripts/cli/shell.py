# -*- coding: utf-8 -*-
"""
Shell interactif — Couche 3 : interface interactive avec autocomplétion.

Utilise prompt_toolkit pour l'autocomplétion et l'historique,
et Rich pour l'affichage coloré.
"""

import json
import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from pathlib import Path

from .client import MCPClient
from .display import (
    console, show_error, show_success, show_warning,
    show_health_result, show_about_result, show_json,
)


# =============================================================================
# Commandes disponibles dans le shell (pour autocomplétion)
# =============================================================================

SHELL_COMMANDS = {
    "help":    "Afficher l'aide",
    "health":  "Vérifier l'état de santé",
    "about":   "Informations sur le service",
    "quit":    "Quitter le shell",
    "exit":    "Quitter le shell",
    # Ajouter vos commandes métier ici :
    # "mon-outil": "Description courte",
}


# =============================================================================
# Handlers de commandes
# =============================================================================

async def cmd_health(client: MCPClient, state: dict, args: str = "",
                      json_output: bool = False):
    """Health check."""
    result = await client.call_tool("system_health", {})
    if json_output:
        show_json(result)
    elif result.get("status") == "ok":
        show_health_result(result)
    else:
        show_error(result.get("message", "Erreur"))


async def cmd_about(client: MCPClient, state: dict, args: str = "",
                     json_output: bool = False):
    """Informations sur le service."""
    result = await client.call_tool("system_about", {})
    if json_output:
        show_json(result)
    elif result.get("status") == "ok":
        show_about_result(result)
    else:
        show_error(result.get("message", "Erreur"))


def cmd_help():
    """Affiche l'aide du shell."""
    from rich.table import Table

    table = Table(title="🐚 Commandes disponibles", show_header=True)
    table.add_column("Commande", style="cyan bold", min_width=20)
    table.add_column("Description", style="white")

    for cmd, desc in SHELL_COMMANDS.items():
        table.add_row(cmd, desc)

    table.add_row("", "")
    table.add_row("[dim]--json[/dim]", "[dim]Ajouter après une commande pour la sortie JSON[/dim]")

    console.print(table)


# =============================================================================
# Ajouter vos handlers métier ici
# =============================================================================
# Exemple :
#
# async def cmd_mon_outil(client: MCPClient, state: dict, args: str = "",
#                          json_output: bool = False):
#     """Mon outil."""
#     if not args.strip():
#         show_warning("Usage: mon-outil <param>")
#         return
#     result = await client.call_tool("mon_outil", {
#         "resource_id": state.get("current_resource", ""),
#         "param": args.strip(),
#     })
#     if json_output:
#         show_json(result)
#     elif result.get("status") == "ok":
#         show_mon_outil_result(result)
#     else:
#         show_error(result.get("message", "Erreur"))


# =============================================================================
# Boucle principale du shell
# =============================================================================

async def run_shell(url: str, token: str):
    """Lance le shell interactif."""

    client = MCPClient(url, token)
    state = {}  # État du shell (ressource courante, préférences, etc.)

    # Autocomplétion
    completer = WordCompleter(
        list(SHELL_COMMANDS.keys()) + ["--json"],
        ignore_case=True,
    )

    # Historique persistant
    history_path = Path.home() / ".mcp_shell_history"
    session = PromptSession(
        history=FileHistory(str(history_path)),
        completer=completer,
    )

    console.print(f"\n[bold cyan]🐚 Shell MCP[/bold cyan] — connecté à [green]{url}[/green]")
    console.print("[dim]Tapez 'help' pour l'aide, 'quit' pour quitter.[/dim]\n")

    while True:
        try:
            # Prompt avec contexte
            prompt_text = "mcp> "
            if state.get("current_resource"):
                prompt_text = f"mcp [{state['current_resource']}]> "

            user_input = await session.prompt_async(prompt_text)

            if not user_input.strip():
                continue

            # Parser la commande
            parts = user_input.strip().split(None, 1)
            command = parts[0].lower()
            args = parts[1] if len(parts) > 1 else ""

            # Détecter --json
            json_output = "--json" in args
            if json_output:
                args = args.replace("--json", "").strip()

            # Dispatch
            if command in ("quit", "exit"):
                console.print("[dim]Au revoir 👋[/dim]")
                break

            elif command == "help":
                cmd_help()

            elif command == "health":
                await cmd_health(client, state, args, json_output)

            elif command == "about":
                await cmd_about(client, state, args, json_output)

            # Ajouter vos commandes métier ici :
            # elif command == "mon-outil":
            #     await cmd_mon_outil(client, state, args, json_output)

            else:
                show_warning(f"Commande inconnue: '{command}'. Tapez 'help'.")

        except KeyboardInterrupt:
            console.print("\n[dim]Ctrl+C — tapez 'quit' pour quitter[/dim]")
        except EOFError:
            console.print("[dim]Au revoir 👋[/dim]")
            break
        except Exception as e:
            show_error(f"Erreur: {e}")
