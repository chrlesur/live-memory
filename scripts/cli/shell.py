# -*- coding: utf-8 -*-
"""
Shell interactif — Interface interactive avec autocomplétion.

Utilise prompt_toolkit pour l'autocomplétion et l'historique,
et Rich pour l'affichage coloré.

Commandes : help, health, about, space, live, bank, token, backup, quit.
"""

import asyncio
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from pathlib import Path

from .client import MCPClient
from .display import (
    console, show_error, show_success, show_warning, show_json,
    show_health_result, show_about_result,
    show_space_created, show_space_list, show_space_info, show_rules, show_notes,
    show_bank_list, show_bank_content, show_consolidation_result,
    show_graph_connected, show_graph_status, show_graph_push_result, show_graph_disconnected,
    show_token_created, show_token_list,
    show_backup_created, show_backup_list,
)


# =============================================================================
# Commandes disponibles (pour autocomplétion)
# =============================================================================

SHELL_COMMANDS = {
    "help": "Afficher l'aide",
    "health": "État de santé",
    "about": "Informations sur le service",
    "space create": "Créer un espace (space create <id> <desc> <rules>)",
    "space list": "Lister les espaces",
    "space info": "Infos d'un espace (space info <id>)",
    "space rules": "Rules d'un espace (space rules <id>)",
    "space delete": "Supprimer un espace (space delete <id> --confirm)",
    "live note": "Écrire une note (live note <space> <cat> <contenu>)",
    "live read": "Lire les notes (live read <space>)",
    "live search": "Rechercher (live search <space> <query>)",
    "bank list": "Lister les fichiers bank (bank list <space>)",
    "bank read": "Lire un fichier bank (bank read <space> <file>)",
    "bank read-all": "Lire toute la bank (bank read-all <space>)",
    "bank consolidate": "Consolider via LLM (bank consolidate <space>)",
    "token create": "Créer un token (token create <name> <perms>)",
    "token list": "Lister les tokens",
    "token revoke": "Révoquer un token (token revoke <hash>)",
    "graph connect": "Connecter à Graph Memory (graph connect <space> <url> <token> <memory_id> [ontology])",
    "graph push": "Pousser la bank dans le graphe (graph push <space>)",
    "graph status": "Statut connexion Graph Memory (graph status <space>)",
    "graph disconnect": "Déconnecter de Graph Memory (graph disconnect <space>)",
    "backup create": "Créer un backup (backup create <space>)",
    "backup list": "Lister les backups",
    "backup restore": "Restaurer (backup restore <id> --confirm)",
    "backup delete": "Supprimer (backup delete <id> --confirm)",
    "quit": "Quitter",
}


# =============================================================================
# Dispatcher de commandes
# =============================================================================

# Sous-commandes par verbe (pour help contextuel)
VERB_SUBCOMMANDS = {
    "space":  {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("space ")},
    "live":   {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("live ")},
    "bank":   {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("bank ")},
    "token":  {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("token ")},
    "graph":  {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("graph ")},
    "backup": {k.split(" ",1)[1]: v for k, v in SHELL_COMMANDS.items() if k.startswith("backup ")},
}


async def dispatch(client: MCPClient, user_input: str, json_output: bool):
    """Route une commande vers le bon handler."""
    parts = user_input.strip().split()
    if not parts:
        return

    cmd = parts[0].lower()
    args = parts[1:]

    # ── Help (global ou contextuel) ──
    if cmd == "help":
        if args and args[0] in VERB_SUBCOMMANDS:
            _show_verb_help(args[0])
        else:
            _show_help()
        return

    # ── System ──
    if cmd == "health":
        result = await client.call_tool("system_health", {})
        (show_json if json_output else show_health_result)(result)

    elif cmd == "about":
        result = await client.call_tool("system_about", {})
        (show_json if json_output else show_about_result)(result)

    # ── Verbes avec sous-commandes ──
    elif cmd == "space":
        if not args or args[0] == "help":
            _show_verb_help("space")
        else:
            await _handle_space(client, args, json_output)

    elif cmd == "live":
        if not args or args[0] == "help":
            _show_verb_help("live")
        else:
            await _handle_live(client, args, json_output)

    elif cmd == "bank":
        if not args or args[0] == "help":
            _show_verb_help("bank")
        else:
            await _handle_bank(client, args, json_output)

    elif cmd == "graph":
        if not args or args[0] == "help":
            _show_verb_help("graph")
        else:
            await _handle_graph(client, args, json_output)

    elif cmd == "token":
        if not args or args[0] == "help":
            _show_verb_help("token")
        else:
            await _handle_token(client, args, json_output)

    elif cmd == "backup":
        if not args or args[0] == "help":
            _show_verb_help("backup")
        else:
            await _handle_backup(client, args, json_output)

    else:
        show_warning(f"Commande inconnue: '{user_input}'. Tapez 'help'.")


# =============================================================================
# Handlers par catégorie
# =============================================================================

async def _handle_space(client, args, json_out):
    """Handler pour les commandes space."""
    sub = args[0] if args else ""

    if sub == "create" and len(args) >= 4:
        result = await client.call_tool("space_create", {
            "space_id": args[1], "description": args[2], "rules": " ".join(args[3:]),
        })
        (show_json if json_out else show_space_created)(result) if result.get("status") == "created" else show_error(result.get("message", "?"))

    elif sub == "list":
        result = await client.call_tool("space_list", {})
        (show_json if json_out else show_space_list)(result)

    elif sub == "info" and len(args) >= 2:
        result = await client.call_tool("space_info", {"space_id": args[1]})
        (show_json if json_out else show_space_info)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "rules" and len(args) >= 2:
        result = await client.call_tool("space_rules", {"space_id": args[1]})
        (show_json if json_out else show_rules)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "delete" and len(args) >= 2:
        confirm = "--confirm" in args
        result = await client.call_tool("space_delete", {"space_id": args[1], "confirm": confirm})
        show_success(f"Supprimé") if result.get("status") == "deleted" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: space [create|list|info|rules|delete] ...")


async def _handle_live(client, args, json_out):
    """Handler pour les commandes live."""
    sub = args[0] if args else ""

    if sub == "note" and len(args) >= 4:
        result = await client.call_tool("live_note", {
            "space_id": args[1], "category": args[2], "content": " ".join(args[3:]),
        })
        show_success(f"Note: {result.get('filename', '?')}") if result.get("status") == "created" else show_error(result.get("message", "?"))

    elif sub == "read" and len(args) >= 2:
        result = await client.call_tool("live_read", {"space_id": args[1], "limit": 20})
        (show_json if json_out else show_notes)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "search" and len(args) >= 3:
        result = await client.call_tool("live_search", {
            "space_id": args[1], "query": " ".join(args[2:]),
        })
        (show_json if json_out else show_notes)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: live [note|read|search] ...")


async def _handle_bank(client, args, json_out):
    """Handler pour les commandes bank."""
    sub = args[0] if args else ""

    if sub == "list" and len(args) >= 2:
        result = await client.call_tool("bank_list", {"space_id": args[1]})
        (show_json if json_out else show_bank_list)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "read" and len(args) >= 3:
        result = await client.call_tool("bank_read", {"space_id": args[1], "filename": args[2]})
        (show_json if json_out else show_bank_content)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "read-all" and len(args) >= 2:
        result = await client.call_tool("bank_read_all", {"space_id": args[1]})
        if json_out:
            show_json(result)
        elif result.get("status") == "ok":
            for f in result.get("files", []):
                show_bank_content(f)
        else:
            show_error(result.get("message", "?"))

    elif sub == "consolidate" and len(args) >= 2:
        console.print("[dim]Consolidation en cours...[/dim]")
        result = await client.call_tool("bank_consolidate", {"space_id": args[1]})
        (show_json if json_out else show_consolidation_result)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: bank [list|read|read-all|consolidate] ...")


async def _handle_token(client, args, json_out):
    """Handler pour les commandes token."""
    sub = args[0] if args else ""

    if sub == "create" and len(args) >= 3:
        result = await client.call_tool("admin_create_token", {
            "name": args[1], "permissions": args[2],
        })
        (show_json if json_out else show_token_created)(result) if result.get("status") == "created" else show_error(result.get("message", "?"))

    elif sub == "list":
        result = await client.call_tool("admin_list_tokens", {})
        (show_json if json_out else show_token_list)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "revoke" and len(args) >= 2:
        result = await client.call_tool("admin_revoke_token", {"token_hash": args[1]})
        show_success("Token révoqué") if result.get("status") == "ok" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: token [create|list|revoke] ...")


async def _handle_graph(client, args, json_out):
    """Handler pour les commandes graph."""
    sub = args[0] if args else ""

    if sub == "connect" and len(args) >= 5:
        ontology = args[5] if len(args) >= 6 else "general"
        result = await client.call_tool("graph_connect", {
            "space_id": args[1], "url": args[2], "token": args[3],
            "memory_id": args[4], "ontology": ontology,
        })
        (show_json if json_out else show_graph_connected)(result) if result.get("status") == "connected" else show_error(result.get("message", "?"))

    elif sub == "push" and len(args) >= 2:
        console.print("[dim]Push en cours... (peut prendre plusieurs minutes)[/dim]")
        result = await client.call_tool("graph_push", {"space_id": args[1]})
        (show_json if json_out else show_graph_push_result)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "status" and len(args) >= 2:
        result = await client.call_tool("graph_status", {"space_id": args[1]})
        (show_json if json_out else show_graph_status)(result) if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "disconnect" and len(args) >= 2:
        result = await client.call_tool("graph_disconnect", {"space_id": args[1]})
        (show_json if json_out else show_graph_disconnected)(result) if result.get("status") == "disconnected" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: graph [connect|push|status|disconnect] ...")


async def _handle_backup(client, args, json_out):
    """Handler pour les commandes backup."""
    sub = args[0] if args else ""

    if sub == "create" and len(args) >= 2:
        result = await client.call_tool("backup_create", {"space_id": args[1]})
        (show_json if json_out else show_backup_created)(result) if result.get("status") == "created" else show_error(result.get("message", "?"))

    elif sub == "list":
        result = await client.call_tool("backup_list", {"space_id": args[1] if len(args) >= 2 else ""})
        (show_json if json_out else show_backup_list)(result)

    elif sub == "restore" and len(args) >= 2:
        confirm = "--confirm" in args
        result = await client.call_tool("backup_restore", {"backup_id": args[1], "confirm": confirm})
        show_success(f"Restauré") if result.get("status") == "ok" else show_error(result.get("message", "?"))

    elif sub == "delete" and len(args) >= 2:
        confirm = "--confirm" in args
        result = await client.call_tool("backup_delete", {"backup_id": args[1], "confirm": confirm})
        show_success(f"Supprimé") if result.get("status") == "deleted" else show_error(result.get("message", "?"))

    else:
        show_warning("Usage: backup [create|list|restore|delete] ...")


# =============================================================================
# Aide
# =============================================================================

def _show_help():
    """Affiche l'aide globale du shell."""
    from rich.table import Table
    table = Table(title="🐚 Commandes Live Memory", show_header=True)
    table.add_column("Commande", style="cyan bold", min_width=25)
    table.add_column("Description")
    for cmd, desc in SHELL_COMMANDS.items():
        table.add_row(cmd, desc)
    table.add_row("", "")
    table.add_row("[dim]--json[/dim]", "[dim]Ajouter pour la sortie JSON[/dim]")
    table.add_row("[dim]help <verbe>[/dim]", "[dim]Aide d'un verbe (ex: help space)[/dim]")
    console.print(table)


def _show_verb_help(verb: str):
    """Affiche l'aide d'un verbe spécifique (sous-commandes)."""
    from rich.table import Table
    subs = VERB_SUBCOMMANDS.get(verb, {})
    if not subs:
        show_warning(f"Pas de sous-commandes pour '{verb}'.")
        return
    table = Table(title=f"📖 {verb} — sous-commandes", show_header=True)
    table.add_column("Commande", style="cyan bold", min_width=15)
    table.add_column("Usage")
    for sub, desc in subs.items():
        table.add_row(f"{verb} {sub}", desc)
    console.print(table)


# =============================================================================
# Boucle principale
# =============================================================================

async def run_shell(url: str, token: str):
    """Lance le shell interactif Live Memory."""
    client = MCPClient(url, token)

    # Autocomplétion avec tous les mots-clés
    words = list(SHELL_COMMANDS.keys()) + ["--json", "--confirm"]
    completer = WordCompleter(words, ignore_case=True)

    history_path = Path.home() / ".live_mem_shell_history"
    session = PromptSession(
        history=FileHistory(str(history_path)),
        completer=completer,
    )

    console.print(f"\n[bold cyan]🧠 Live Memory Shell[/bold cyan] — [green]{url}[/green]")
    console.print("[dim]Tapez 'help' pour l'aide, 'quit' pour quitter.[/dim]\n")

    while True:
        try:
            user_input = await session.prompt_async("live-mem> ")
            if not user_input.strip():
                continue

            # Détecter --json
            json_output = "--json" in user_input
            clean_input = user_input.replace("--json", "").strip()

            # Quitter
            if clean_input.lower() in ("quit", "exit"):
                console.print("[dim]Au revoir 👋[/dim]")
                break

            await dispatch(client, clean_input, json_output)

        except KeyboardInterrupt:
            console.print("\n[dim]Ctrl+C — tapez 'quit' pour quitter[/dim]")
        except EOFError:
            console.print("[dim]Au revoir 👋[/dim]")
            break
        except Exception as e:
            show_error(f"Erreur: {e}")
