# -*- coding: utf-8 -*-
"""
Outils MCP — Catégorie Admin (4 outils).

Gestion des tokens d'authentification.

Permissions :
    - admin_create_token 👑 (admin) — Crée un token
    - admin_list_tokens  👑 (admin) — Liste les tokens
    - admin_revoke_token 👑 (admin) — Révoque un token
    - admin_update_token 👑 (admin) — Modifie un token

Tous les outils admin requièrent la permission "admin".
Voir AUTH_AND_COLLABORATION.md pour le modèle de tokens.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> int:
    """
    Enregistre les 4 outils admin sur l'instance MCP.

    Args:
        mcp: Instance FastMCP

    Returns:
        Nombre d'outils enregistrés (4)
    """

    @mcp.tool()
    async def admin_create_token(
        name: str,
        permissions: str,
        space_ids: str = "",
        expires_in_days: int = 0,
    ) -> dict:
        """
        Crée un nouveau token d'authentification.

        ⚠️ Le token en clair ne sera affiché qu'UNE SEULE FOIS.
        Seul le hash SHA-256 est stocké.

        Args:
            name: Nom descriptif (ex: "agent-cline")
            permissions: "read", "read,write", ou "read,write,admin"
            space_ids: Espaces autorisés, séparés par virgules (vide = tous)
            expires_in_days: Durée en jours (0 = jamais)

        Returns:
            Token en clair (à sauvegarder !), permissions, expiration
        """
        from ..auth.context import check_admin_permission
        from ..core.tokens import get_token_service

        try:
            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            return await get_token_service().create_token(
                name=name,
                permissions=permissions,
                space_ids=space_ids,
                expires_in_days=expires_in_days,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def admin_list_tokens() -> dict:
        """
        Liste tous les tokens (métadonnées seulement, jamais en clair).

        Retourne le nom, les permissions, les espaces autorisés,
        le hash tronqué, et le statut (révoqué, expiré).

        Returns:
            Liste des tokens avec métadonnées
        """
        from ..auth.context import check_admin_permission
        from ..core.tokens import get_token_service

        try:
            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            return await get_token_service().list_tokens()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def admin_revoke_token(token_hash: str) -> dict:
        """
        Révoque un token (le rend définitivement inutilisable).

        Args:
            token_hash: Hash tronqué du token (depuis admin_list_tokens)

        Returns:
            Confirmation de révocation
        """
        from ..auth.context import check_admin_permission
        from ..core.tokens import get_token_service

        try:
            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            return await get_token_service().revoke_token(token_hash)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def admin_update_token(
        token_hash: str,
        space_ids: str = "",
        permissions: str = "",
    ) -> dict:
        """
        Met à jour les permissions ou espaces autorisés d'un token.

        Args:
            token_hash: Hash tronqué du token (depuis admin_list_tokens)
            space_ids: Nouveaux espaces (vide = pas de changement)
            permissions: Nouvelles permissions (vide = pas de changement)

        Returns:
            Confirmation de mise à jour
        """
        from ..auth.context import check_admin_permission
        from ..core.tokens import get_token_service

        try:
            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            return await get_token_service().update_token(
                token_hash=token_hash,
                space_ids=space_ids,
                permissions=permissions,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return 4  # Nombre d'outils enregistrés
