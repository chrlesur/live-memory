# -*- coding: utf-8 -*-
"""
Helpers d'authentification basés sur contextvars.

Le middleware ASGI injecte les infos du token dans les contextvars.
Les outils MCP appellent check_access(), check_write_permission()
et check_admin_permission() pour vérifier les permissions sans
dépendre du framework HTTP.

Architecture :
    Middleware ASGI → injecte current_token_info (contextvar)
    Outils MCP → appellent check_xxx() → lisent le contextvar

Voir AUTH_AND_COLLABORATION.md pour la matrice des permissions.

3 niveaux de permission :
    - read  (🔑) : lecture des espaces et notes
    - write (✏️) : écriture de notes + consolidation
    - admin (👑) : suppression d'espaces, backup restore, gestion tokens
"""

from contextvars import ContextVar
from typing import Optional

# ─────────────────────────────────────────────────────────────
# Context variable injectée par le middleware AuthMiddleware
# ─────────────────────────────────────────────────────────────
# Contient un dict avec les champs :
#   - client_name: str (nom du token)
#   - permissions: list[str] (["read"], ["read", "write"], etc.)
#   - allowed_resources: list[str] (space_ids autorisés, [] = tous)
# Ou None si pas de token / token invalide.
current_token_info: ContextVar[Optional[dict]] = ContextVar(
    "current_token_info", default=None
)


def check_access(resource_id: str) -> Optional[dict]:
    """
    Vérifie que le token courant a accès à la ressource (espace).

    Un token peut être restreint à certains space_ids.
    Si allowed_resources est vide → accès à tous les espaces.

    Args:
        resource_id: ID de l'espace à vérifier

    Returns:
        None si OK, dict {"status": "error", ...} si refusé
    """
    token_info = current_token_info.get()

    # Pas de token → accès refusé
    if token_info is None:
        return {"status": "error", "message": "Authentification requise"}

    # Admin → accès total (pas de restriction par espace)
    if "admin" in token_info.get("permissions", []):
        return None

    # Vérifier que l'espace est dans la liste autorisée
    allowed = token_info.get("allowed_resources", [])
    if allowed and resource_id not in allowed:
        return {
            "status": "error",
            "message": f"Accès refusé à l'espace '{resource_id}'",
        }

    return None  # OK


def check_write_permission() -> Optional[dict]:
    """
    Vérifie que le token courant a la permission d'écriture.

    Nécessaire pour : live_note, bank_consolidate, space_create,
    backup_create.

    Returns:
        None si OK, dict {"status": "error", ...} si refusé
    """
    token_info = current_token_info.get()

    if token_info is None:
        return {"status": "error", "message": "Authentification requise"}

    permissions = token_info.get("permissions", [])
    if "write" in permissions or "admin" in permissions:
        return None

    return {
        "status": "error",
        "message": "Permission 'write' requise pour cette opération",
    }


def check_admin_permission() -> Optional[dict]:
    """
    Vérifie que le token courant a la permission admin.

    Nécessaire pour : space_delete, backup_restore, backup_delete,
    admin_create_token, admin_list_tokens, admin_revoke_token,
    admin_update_token.

    Returns:
        None si OK, dict {"status": "error", ...} si refusé
    """
    token_info = current_token_info.get()

    if token_info is None:
        return {"status": "error", "message": "Authentification requise"}

    permissions = token_info.get("permissions", [])
    if "admin" in permissions:
        return None

    return {
        "status": "error",
        "message": "Permission 'admin' requise pour cette opération",
    }


def get_current_agent_name() -> str:
    """
    Retourne le nom de l'agent (client_name du token courant).

    Utile pour identifier automatiquement l'auteur d'une note live
    quand le paramètre agent n'est pas fourni.

    Returns:
        Nom de l'agent, ou "anonymous" si pas de token
    """
    token_info = current_token_info.get()
    if token_info is None:
        return "anonymous"
    return token_info.get("client_name", "anonymous")
