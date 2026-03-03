# -*- coding: utf-8 -*-
"""
Outils MCP — Catégorie Admin (5 outils).

Gestion des tokens d'authentification et maintenance.

Permissions :
    - admin_create_token 👑 (admin) — Crée un token
    - admin_list_tokens  👑 (admin) — Liste les tokens
    - admin_revoke_token 👑 (admin) — Révoque un token
    - admin_update_token 👑 (admin) — Modifie un token
    - admin_gc_notes     👑 (admin) — GC des notes orphelines

Tous les outils admin requièrent la permission "admin".
Voir AUTH_AND_COLLABORATION.md pour le modèle de tokens.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> int:
    """
    Enregistre les 5 outils admin sur l'instance MCP.

    Args:
        mcp: Instance FastMCP

    Returns:
        Nombre d'outils enregistrés (5)
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

    @mcp.tool()
    async def admin_gc_notes(
        space_id: str = "",
        max_age_days: int = 7,
        confirm: bool = False,
        delete_only: bool = False,
    ) -> dict:
        """
        Garbage Collector : consolide ou supprime les notes orphelines.

        Les notes live non consolidées par un agent disparu s'accumulent.
        Cet outil les identifie (plus vieilles que max_age_days).

        3 modes :
        - confirm=False (défaut) : DRY-RUN — scanne et rapporte
        - confirm=True : CONSOLIDE les notes dans la bank via LLM
          (ajoute une notice "⚠️ GC consolidation forcée" dans chaque bank)
        - confirm=True, delete_only=True : SUPPRIME sans consolider

        Args:
            space_id: Espace cible (vide = scanner TOUS les espaces)
            max_age_days: Seuil en jours (défaut 7)
            confirm: False = dry-run, True = exécution
            delete_only: Si True + confirm, supprime SANS consolider

        Returns:
            Rapport : nombre de notes, taille, répartition par agent
        """
        from ..auth.context import check_admin_permission
        from ..core.gc import get_gc_service

        try:
            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            gc = get_gc_service()

            if confirm and delete_only:
                # Mode suppression sans consolidation (perte de données)
                return await gc.delete_old_notes(
                    space_id=space_id,
                    max_age_days=max_age_days,
                )
            elif confirm:
                # Mode consolidation (défaut avec confirm)
                return await gc.consolidate_old_notes(
                    space_id=space_id,
                    max_age_days=max_age_days,
                )
            else:
                # Mode dry-run : scanner seulement
                result = await gc.scan_old_notes(
                    space_id=space_id,
                    max_age_days=max_age_days,
                )
                for sid in result.get("spaces", {}):
                    if "keys" in result["spaces"][sid]:
                        count = len(result["spaces"][sid]["keys"])
                        del result["spaces"][sid]["keys"]
                        result["spaces"][sid]["keys_count"] = count
                result["mode"] = "dry-run"
                result["message"] = (
                    f"Dry-run : {result['total_old_notes']} notes orphelines "
                    f"trouvées. confirm=True pour consolider, "
                    f"confirm=True+delete_only=True pour supprimer."
                )
                return result

        except Exception as e:
            return {"status": "error", "message": str(e)}

    return 5  # Nombre d'outils enregistrés
