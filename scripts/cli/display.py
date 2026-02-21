# -*- coding: utf-8 -*-
"""
Fonctions d'affichage Rich — partagées entre CLI Click et Shell interactif.

Chaque outil MCP a sa fonction show_xxx_result() pour un rendu coloré.
Ces fonctions sont importées dans commands.py ET shell.py (DRY).
"""

import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()


# =============================================================================
# Utilitaires communs
# =============================================================================

def show_error(msg: str):
    """Affiche un message d'erreur."""
    console.print(f"[red]❌ {msg}[/red]")


def show_success(msg: str):
    """Affiche un message de succès."""
    console.print(f"[green]✅ {msg}[/green]")


def show_warning(msg: str):
    """Affiche un avertissement."""
    console.print(f"[yellow]⚠️  {msg}[/yellow]")


def show_json(data: dict):
    """Affiche un dict en JSON coloré."""
    console.print(Syntax(
        json.dumps(data, indent=2, ensure_ascii=False), "json"
    ))


# =============================================================================
# System
# =============================================================================

def show_health_result(result: dict):
    """Affiche le résultat de system_health."""
    status = result.get("status", "?")
    services = result.get("services", {})
    icon = "✅" if status == "ok" else "⚠️"

    table = Table(title=f"{icon} Health — {result.get('service_name', '?')}", show_header=True)
    table.add_column("Service", style="cyan bold")
    table.add_column("Statut")
    table.add_column("Détails", style="dim")

    for name, info in services.items():
        if isinstance(info, dict):
            s = info.get("status", "?")
            s_icon = "✅" if s == "ok" else "❌"
            details = info.get("message", info.get("latency_ms", ""))
            table.add_row(name, f"{s_icon} {s}", str(details))

    console.print(table)


def show_about_result(result: dict):
    """Affiche le résultat de system_about."""
    console.print(Panel.fit(
        f"[bold]Service :[/bold] [cyan]{result.get('name', '?')}[/cyan]\n"
        f"[bold]Version :[/bold] [green]{result.get('version', '?')}[/green]\n"
        f"[bold]Python  :[/bold] {result.get('python_version', '?')}\n"
        f"[bold]Outils  :[/bold] {result.get('tools_count', 0)}",
        title="ℹ️  À propos", border_style="blue",
    ))
    tools = result.get("tools", [])
    if tools:
        # Grouper par catégorie (préfixe avant le _)
        categories = {}
        for t in tools:
            name = t.get("name", "?")
            cat = name.split("_")[0].capitalize() if "_" in name else "Other"
            categories.setdefault(cat, []).append(t)

        table = Table(show_header=True, title="Outils MCP", title_style="bold")
        table.add_column("Cat.", style="bold", width=8)
        table.add_column("Outil", style="cyan bold", width=20)
        table.add_column("Description", style="dim", max_width=55)

        for cat, cat_tools in categories.items():
            for i, t in enumerate(cat_tools):
                # Extraire la première ligne non-vide de la description
                desc = t.get("description", "")
                first_line = ""
                for line in desc.strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("Args:") and not line.startswith("Returns:"):
                        first_line = line[:55]
                        break
                cat_label = f"[magenta]{cat}[/magenta]" if i == 0 else ""
                table.add_row(cat_label, t.get("name", "?"), first_line)

        console.print(table)


# =============================================================================
# Space
# =============================================================================

def show_space_created(result: dict):
    """Affiche un espace créé."""
    console.print(Panel.fit(
        f"[bold]Space ID :[/bold] [cyan]{result.get('space_id', '?')}[/cyan]\n"
        f"[bold]Description :[/bold] {result.get('description', '')}\n"
        f"[bold]Rules :[/bold] {result.get('rules_size', 0)} octets\n"
        f"[bold]Créé le :[/bold] {result.get('created_at', '')}",
        title="✅ Espace créé", border_style="green",
    ))


def show_space_list(result: dict):
    """Affiche la liste des espaces."""
    spaces = result.get("spaces", [])
    table = Table(title=f"📂 {result.get('total', 0)} espaces", show_header=True)
    table.add_column("Space ID", style="cyan bold")
    table.add_column("Description")
    table.add_column("Notes", justify="right")
    table.add_column("Bank", justify="right")
    for s in spaces:
        table.add_row(
            s.get("space_id", "?"), s.get("description", ""),
            str(s.get("live_notes_count", 0)), str(s.get("bank_files_count", 0)),
        )
    console.print(table)


def show_space_info(result: dict):
    """Affiche les infos détaillées d'un espace."""
    live = result.get("live", {})
    bank = result.get("bank", {})
    console.print(Panel.fit(
        f"[bold]Space ID :[/bold] [cyan]{result.get('space_id', '?')}[/cyan]\n"
        f"[bold]Description :[/bold] {result.get('description', '')}\n"
        f"[bold]Notes live :[/bold] {live.get('notes_count', 0)} ({live.get('total_size', 0)} octets)\n"
        f"[bold]Bank files :[/bold] {bank.get('files_count', 0)} ({bank.get('total_size', 0)} octets)\n"
        f"[bold]Consolidations :[/bold] {result.get('consolidation_count', 0)}\n"
        f"[bold]Dernière :[/bold] {result.get('last_consolidation', 'jamais')}",
        title="📋 Espace", border_style="blue",
    ))


def show_rules(result: dict):
    """Affiche les rules d'un espace."""
    rules = result.get("rules", "")
    console.print(Panel(Syntax(rules, "markdown"), title="📐 Rules", border_style="blue"))


def show_notes(result: dict):
    """Affiche les notes live."""
    notes = result.get("notes", [])
    # Couleurs par catégorie
    colors = {
        "observation": "green", "decision": "yellow", "todo": "red",
        "insight": "magenta", "question": "cyan", "progress": "blue", "issue": "red",
    }
    table = Table(title=f"📝 {result.get('total', 0)} notes", show_header=True)
    table.add_column("Agent", style="cyan")
    table.add_column("Catégorie")
    table.add_column("Contenu", max_width=60)
    table.add_column("Timestamp", style="dim")
    for n in notes:
        cat = n.get("category", "?")
        color = colors.get(cat, "white")
        table.add_row(
            n.get("agent", "?"), f"[{color}]{cat}[/{color}]",
            n.get("content", "")[:60], n.get("timestamp", "")[:19],
        )
    console.print(table)


# =============================================================================
# Bank
# =============================================================================

def show_bank_list(result: dict):
    """Affiche la liste des fichiers bank."""
    files = result.get("files", [])
    table = Table(title=f"📘 Bank — {result.get('file_count', 0)} fichiers", show_header=True)
    table.add_column("Fichier", style="cyan bold")
    table.add_column("Taille", justify="right")
    for f in files:
        table.add_row(f.get("filename", "?"), f"{f.get('size', 0)} oct")
    console.print(table)


def show_bank_content(result: dict):
    """Affiche le contenu d'un fichier bank."""
    console.print(Panel(
        Syntax(result.get("content", ""), "markdown"),
        title=f"📄 {result.get('filename', '?')}",
        border_style="blue",
    ))


def show_consolidation_result(result: dict):
    """Affiche le résultat d'une consolidation."""
    console.print(Panel.fit(
        f"[bold]Notes traitées :[/bold] {result.get('notes_processed', 0)}\n"
        f"[bold]Fichiers créés :[/bold] {result.get('bank_files_created', 0)}\n"
        f"[bold]Fichiers MAJ :[/bold] {result.get('bank_files_updated', 0)}\n"
        f"[bold]Synthèse :[/bold] {result.get('synthesis_size', 0)} chars\n"
        f"[bold]Tokens LLM :[/bold] {result.get('llm_tokens_used', 0)}\n"
        f"[bold]Durée :[/bold] {result.get('duration_seconds', 0)}s",
        title="🧠 Consolidation terminée", border_style="green",
    ))


# =============================================================================
# Admin tokens
# =============================================================================

def show_token_created(result: dict):
    """Affiche un token créé (avec avertissement)."""
    console.print(Panel.fit(
        f"[bold]Nom :[/bold] {result.get('name', '?')}\n"
        f"[bold red]Token :[/bold red] [red]{result.get('token', '?')}[/red]\n"
        f"[bold]Permissions :[/bold] {', '.join(result.get('permissions', []))}\n"
        f"[bold]Espaces :[/bold] {', '.join(result.get('space_ids', [])) or 'tous'}\n"
        f"[bold]Expire :[/bold] {result.get('expires_at', 'jamais')}\n\n"
        f"[bold yellow]{result.get('warning', '')}[/bold yellow]",
        title="🔑 Token créé", border_style="red",
    ))


def show_token_list(result: dict):
    """Affiche la liste des tokens."""
    tokens = result.get("tokens", [])
    table = Table(title=f"🔑 {result.get('total', 0)} tokens", show_header=True)
    table.add_column("Nom", style="cyan bold")
    table.add_column("Permissions")
    table.add_column("Espaces")
    table.add_column("Révoqué")
    table.add_column("Hash", style="dim")
    for t in tokens:
        revoked = "❌ oui" if t.get("revoked") else "✅ non"
        table.add_row(
            t.get("name", "?"), ", ".join(t.get("permissions", [])),
            ", ".join(t.get("space_ids", [])) or "tous",
            revoked, t.get("hash", "?")[:15],
        )
    console.print(table)


# =============================================================================
# Backup
# =============================================================================

def show_backup_created(result: dict):
    """Affiche un backup créé."""
    show_success(
        f"Backup '{result.get('backup_id', '?')}' — "
        f"{result.get('files_backed_up', 0)} fichiers, "
        f"{result.get('total_size', 0)} octets"
    )


def show_backup_list(result: dict):
    """Affiche la liste des backups."""
    backups = result.get("backups", [])
    table = Table(title=f"💾 {result.get('total', 0)} backups", show_header=True)
    table.add_column("Backup ID", style="cyan bold")
    table.add_column("Space", style="dim")
    table.add_column("Timestamp")
    for b in backups:
        table.add_row(b.get("backup_id", "?"), b.get("space_id", "?"), b.get("timestamp", "?"))
    console.print(table)
