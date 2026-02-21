# -*- coding: utf-8 -*-
"""
CLI Click — Commandes scriptables pour Live Memory.

Chaque commande appelle un outil MCP via MCPClient puis affiche via display.py.

Usage :
    python scripts/mcp_cli.py health
    python scripts/mcp_cli.py space list
    python scripts/mcp_cli.py live note <space_id> <category> <content>
    python scripts/mcp_cli.py bank consolidate <space_id>
    python scripts/mcp_cli.py shell
"""

import asyncio
import click
from . import BASE_URL, TOKEN
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


# ─────────────────────────────────────────────────────────────
# Helper pour exécuter les commandes async
# ─────────────────────────────────────────────────────────────

def _run_tool(ctx, tool_name, args, on_success, json_flag=False):
    """Helper commun : appelle un outil MCP et affiche le résultat."""
    async def _run():
        try:
            client = MCPClient(ctx.obj["url"], ctx.obj["token"])
            result = await client.call_tool(tool_name, args)
            if json_flag:
                show_json(result)
            elif result.get("status") in ("ok", "created", "deleted", "connected", "disconnected"):
                on_success(result)
            else:
                show_error(result.get("message", f"Erreur: {result.get('status', '?')}"))
        except Exception as e:
            show_error(f"Connexion impossible: {e}")
    asyncio.run(_run())


# ─────────────────────────────────────────────────────────────
# Groupe racine
# ─────────────────────────────────────────────────────────────

@click.group()
@click.option("--url", "-u", envvar=["MCP_URL"], default=BASE_URL, help="URL du serveur MCP")
@click.option("--token", "-t", envvar=["MCP_TOKEN"], default=TOKEN, help="Token d'authentification")
@click.pass_context
def cli(ctx, url, token):
    """🧠 Live Memory — CLI pour le serveur MCP."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url
    ctx.obj["token"] = token


# ─────────────────────────────────────────────────────────────
# System
# ─────────────────────────────────────────────────────────────

@cli.command("health")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def health_cmd(ctx, jflag):
    """❤️  État de santé du service."""
    _run_tool(ctx, "system_health", {}, show_health_result, jflag)


@cli.command("about")
@click.option("--json", "-j", "jflag", is_flag=True, help="JSON brut")
@click.pass_context
def about_cmd(ctx, jflag):
    """ℹ️  Informations sur le service."""
    _run_tool(ctx, "system_about", {}, show_about_result, jflag)


# ─────────────────────────────────────────────────────────────
# Space (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("space")
def space_grp():
    """📂 Gestion des espaces mémoire."""
    pass


@space_grp.command("create")
@click.argument("space_id")
@click.option("--description", "-d", default="", help="Description de l'espace")
@click.option("--rules-file", "-r", type=click.Path(exists=True), help="Fichier rules (.md)")
@click.option("--rules", default="", help="Contenu rules en ligne")
@click.option("--owner", "-o", default="", help="Propriétaire")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def space_create_cmd(ctx, space_id, description, rules_file, rules, owner, jflag):
    """Créer un espace mémoire."""
    if rules_file:
        rules = open(rules_file).read()
    if not rules:
        show_error("Rules requises (--rules-file ou --rules)")
        return
    _run_tool(ctx, "space_create", {
        "space_id": space_id, "description": description, "rules": rules, "owner": owner,
    }, show_space_created, jflag)


@space_grp.command("list")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def space_list_cmd(ctx, jflag):
    """Lister les espaces."""
    _run_tool(ctx, "space_list", {}, show_space_list, jflag)


@space_grp.command("info")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def space_info_cmd(ctx, space_id, jflag):
    """Infos détaillées d'un espace."""
    _run_tool(ctx, "space_info", {"space_id": space_id}, show_space_info, jflag)


@space_grp.command("rules")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def space_rules_cmd(ctx, space_id, jflag):
    """Lire les rules d'un espace."""
    _run_tool(ctx, "space_rules", {"space_id": space_id}, show_rules, jflag)


@space_grp.command("delete")
@click.argument("space_id")
@click.option("--confirm", is_flag=True, help="Confirmer la suppression")
@click.pass_context
def space_delete_cmd(ctx, space_id, confirm):
    """⚠️ Supprimer un espace (irréversible)."""
    _run_tool(ctx, "space_delete", {
        "space_id": space_id, "confirm": confirm,
    }, lambda r: show_success(f"Espace '{space_id}' supprimé ({r.get('files_deleted', 0)} fichiers)"))


# ─────────────────────────────────────────────────────────────
# Live (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("live")
def live_grp():
    """📝 Notes en temps réel."""
    pass


@live_grp.command("note")
@click.argument("space_id")
@click.argument("category")
@click.argument("content")
@click.option("--agent", "-a", default="", help="Nom de l'agent")
@click.option("--tags", default="", help="Tags séparés par virgules")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def live_note_cmd(ctx, space_id, category, content, agent, tags, jflag):
    """Écrire une note."""
    _run_tool(ctx, "live_note", {
        "space_id": space_id, "category": category, "content": content,
        "agent": agent, "tags": tags,
    }, lambda r: show_success(f"Note créée: {r.get('filename', '?')}"), jflag)


@live_grp.command("read")
@click.argument("space_id")
@click.option("--limit", "-l", default=50, help="Nombre max")
@click.option("--category", "-c", default="", help="Filtrer par catégorie")
@click.option("--agent", "-a", default="", help="Filtrer par agent")
@click.option("--since", default="", help="Notes après cette date ISO")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def live_read_cmd(ctx, space_id, limit, category, agent, since, jflag):
    """Lire les notes live."""
    _run_tool(ctx, "live_read", {
        "space_id": space_id, "limit": limit, "category": category,
        "agent": agent, "since": since,
    }, show_notes, jflag)


@live_grp.command("search")
@click.argument("space_id")
@click.argument("query")
@click.option("--limit", "-l", default=20)
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def live_search_cmd(ctx, space_id, query, limit, jflag):
    """Rechercher dans les notes."""
    _run_tool(ctx, "live_search", {
        "space_id": space_id, "query": query, "limit": limit,
    }, show_notes, jflag)


# ─────────────────────────────────────────────────────────────
# Bank (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("bank")
def bank_grp():
    """📘 Memory Bank consolidée."""
    pass


@bank_grp.command("read")
@click.argument("space_id")
@click.argument("filename")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def bank_read_cmd(ctx, space_id, filename, jflag):
    """Lire un fichier bank."""
    _run_tool(ctx, "bank_read", {"space_id": space_id, "filename": filename}, show_bank_content, jflag)


@bank_grp.command("read-all")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def bank_read_all_cmd(ctx, space_id, jflag):
    """Lire toute la bank."""
    def _show(r):
        for f in r.get("files", []):
            show_bank_content(f)
    _run_tool(ctx, "bank_read_all", {"space_id": space_id}, _show, jflag)


@bank_grp.command("list")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def bank_list_cmd(ctx, space_id, jflag):
    """Lister les fichiers bank."""
    _run_tool(ctx, "bank_list", {"space_id": space_id}, show_bank_list, jflag)


@bank_grp.command("consolidate")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def bank_consolidate_cmd(ctx, space_id, jflag):
    """🧠 Consolider les notes via LLM."""
    _run_tool(ctx, "bank_consolidate", {"space_id": space_id}, show_consolidation_result, jflag)


# ─────────────────────────────────────────────────────────────
# Token (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("token")
def token_grp():
    """🔑 Gestion des tokens."""
    pass


@token_grp.command("create")
@click.argument("name")
@click.argument("permissions")
@click.option("--space-ids", default="", help="Espaces autorisés (virgules)")
@click.option("--expires-in-days", default=0, help="Expiration (0=jamais)")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def token_create_cmd(ctx, name, permissions, space_ids, expires_in_days, jflag):
    """Créer un token."""
    _run_tool(ctx, "admin_create_token", {
        "name": name, "permissions": permissions,
        "space_ids": space_ids, "expires_in_days": expires_in_days,
    }, show_token_created, jflag)


@token_grp.command("list")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def token_list_cmd(ctx, jflag):
    """Lister les tokens."""
    _run_tool(ctx, "admin_list_tokens", {}, show_token_list, jflag)


@token_grp.command("revoke")
@click.argument("token_hash")
@click.pass_context
def token_revoke_cmd(ctx, token_hash):
    """Révoquer un token."""
    _run_tool(ctx, "admin_revoke_token", {"token_hash": token_hash},
              lambda r: show_success(r.get("message", "Token révoqué")))


# ─────────────────────────────────────────────────────────────
# Backup (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("backup")
def backup_grp():
    """💾 Sauvegarde & restauration."""
    pass


@backup_grp.command("create")
@click.argument("space_id")
@click.option("--description", "-d", default="")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def backup_create_cmd(ctx, space_id, description, jflag):
    """Créer un backup."""
    _run_tool(ctx, "backup_create", {
        "space_id": space_id, "description": description,
    }, show_backup_created, jflag)


@backup_grp.command("list")
@click.option("--space-id", default="", help="Filtrer par espace")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def backup_list_cmd(ctx, space_id, jflag):
    """Lister les backups."""
    _run_tool(ctx, "backup_list", {"space_id": space_id}, show_backup_list, jflag)


@backup_grp.command("restore")
@click.argument("backup_id")
@click.option("--confirm", is_flag=True)
@click.pass_context
def backup_restore_cmd(ctx, backup_id, confirm):
    """Restaurer depuis un backup."""
    _run_tool(ctx, "backup_restore", {"backup_id": backup_id, "confirm": confirm},
              lambda r: show_success(f"Restauré: {r.get('files_restored', 0)} fichiers"))


@backup_grp.command("delete")
@click.argument("backup_id")
@click.option("--confirm", is_flag=True)
@click.pass_context
def backup_delete_cmd(ctx, backup_id, confirm):
    """Supprimer un backup."""
    _run_tool(ctx, "backup_delete", {"backup_id": backup_id, "confirm": confirm},
              lambda r: show_success(f"Supprimé: {r.get('files_deleted', 0)} fichiers"))


# ─────────────────────────────────────────────────────────────
# Graph Bridge (sous-groupe)
# ─────────────────────────────────────────────────────────────

@cli.group("graph")
def graph_grp():
    """🌉 Pont vers Graph Memory (mémoire long terme)."""
    pass


@graph_grp.command("connect")
@click.argument("space_id")
@click.argument("url")
@click.argument("graph_token")
@click.argument("memory_id")
@click.option("--ontology", "-o", default="general",
              help="Ontologie Graph Memory (general, legal, cloud, managed-services, presales)")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def graph_connect_cmd(ctx, space_id, url, graph_token, memory_id, ontology, jflag):
    """Connecter un space à Graph Memory."""
    _run_tool(ctx, "graph_connect", {
        "space_id": space_id, "url": url, "token": graph_token,
        "memory_id": memory_id, "ontology": ontology,
    }, show_graph_connected, jflag)


@graph_grp.command("push")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def graph_push_cmd(ctx, space_id, jflag):
    """📤 Pousser la bank dans Graph Memory (delete + re-ingest)."""
    console.print("[dim]Push en cours... (peut prendre plusieurs minutes)[/dim]")
    _run_tool(ctx, "graph_push", {"space_id": space_id}, show_graph_push_result, jflag)


@graph_grp.command("status")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def graph_status_cmd(ctx, space_id, jflag):
    """📊 Statut de la connexion Graph Memory (stats, documents, entités)."""
    _run_tool(ctx, "graph_status", {"space_id": space_id}, show_graph_status, jflag)


@graph_grp.command("disconnect")
@click.argument("space_id")
@click.option("--json", "-j", "jflag", is_flag=True)
@click.pass_context
def graph_disconnect_cmd(ctx, space_id, jflag):
    """🔌 Déconnecter un space de Graph Memory."""
    _run_tool(ctx, "graph_disconnect", {"space_id": space_id}, show_graph_disconnected, jflag)


# ─────────────────────────────────────────────────────────────
# Shell
# ─────────────────────────────────────────────────────────────

@cli.command("shell")
@click.pass_context
def shell_cmd(ctx):
    """🐚 Lancer le shell interactif."""
    from .shell import run_shell
    asyncio.run(run_shell(ctx.obj["url"], ctx.obj["token"]))
