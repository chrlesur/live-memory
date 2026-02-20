# -*- coding: utf-8 -*-
"""
Outils MCP — Catégorie Space (7 outils).

Gestion des espaces mémoire : créer, lister, inspecter, exporter, supprimer.

Permissions :
    - space_create  ✏️ (write)  — Crée un nouvel espace
    - space_list    🔑 (read)   — Liste les espaces accessibles
    - space_info    🔑 (read)   — Infos détaillées d'un espace
    - space_rules   🔑 (read)   — Lit les rules immuables
    - space_summary 🔑 (read)   — Synthèse complète (rules + bank)
    - space_export  🔑 (read)   — Export tar.gz en base64
    - space_delete  👑 (admin)  — Supprime un espace (irréversible)

Chaque outil délègue au SpaceService (core/space.py) après vérification
des permissions via les helpers auth/context.py.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> int:
    """
    Enregistre les 7 outils space sur l'instance MCP.

    Args:
        mcp: Instance FastMCP

    Returns:
        Nombre d'outils enregistrés (7)
    """

    @mcp.tool()
    async def space_create(
        space_id: str,
        description: str,
        rules: str,
        owner: str = "",
    ) -> dict:
        """
        Crée un nouvel espace mémoire avec ses rules.

        Les rules définissent la structure de la Memory Bank (quels fichiers,
        quel contenu). Elles sont immuables après création.

        Args:
            space_id: Identifiant unique (alphanum + tirets, max 64 chars)
            description: Description courte de l'espace
            rules: Contenu Markdown des rules (structure de la bank)
            owner: Propriétaire (optionnel, informatif)

        Returns:
            Détails de l'espace créé
        """
        from ..auth.context import check_write_permission
        from ..core.space import get_space_service

        try:
            # Vérifier la permission write
            write_err = check_write_permission()
            if write_err:
                return write_err

            return await get_space_service().create(
                space_id=space_id,
                description=description,
                rules=rules,
                owner=owner,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_list() -> dict:
        """
        Liste tous les espaces mémoire accessibles par le token courant.

        Retourne les métadonnées, le nombre de notes live et de fichiers bank
        pour chaque espace.

        Returns:
            Liste des espaces avec statistiques
        """
        from ..auth.context import current_token_info
        from ..core.space import get_space_service

        try:
            # Récupérer les space_ids autorisés depuis le token
            token_info = current_token_info.get()
            if token_info is None:
                return {"status": "error", "message": "Authentification requise"}

            allowed = token_info.get("allowed_resources", [])
            # allowed vide = accès à tous les espaces
            allowed_ids = allowed if allowed else None

            return await get_space_service().list_spaces(
                allowed_space_ids=allowed_ids
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_info(space_id: str) -> dict:
        """
        Informations détaillées sur un espace mémoire.

        Retourne les métadonnées, les stats des notes live (nombre, taille),
        les stats de la bank (fichiers, taille), et le statut de consolidation.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Infos complètes de l'espace
        """
        from ..auth.context import check_access
        from ..core.space import get_space_service

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            return await get_space_service().get_info(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_rules(space_id: str) -> dict:
        """
        Lit les rules de l'espace (immuables après création).

        Les rules définissent la structure souhaitée de la Memory Bank.
        Le LLM les utilise lors de la consolidation pour créer/maintenir
        les fichiers bank correspondants.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Contenu Markdown des rules
        """
        from ..auth.context import check_access
        from ..core.space import get_space_service

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            return await get_space_service().get_rules(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_summary(space_id: str) -> dict:
        """
        Synthèse complète d'un espace : rules + bank + stats.

        C'est l'outil idéal pour qu'un agent charge TOUT le contexte
        d'un projet en une seule requête au démarrage.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Rules, fichiers bank complets, synthèse résiduelle
        """
        from ..auth.context import check_access
        from ..core.space import get_space_service

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            return await get_space_service().get_summary(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_export(space_id: str) -> dict:
        """
        Exporte un espace complet en archive tar.gz (base64).

        L'archive contient tous les fichiers de l'espace : _meta.json,
        _rules.md, notes live, fichiers bank, synthèse.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Archive base64, taille et nombre de fichiers
        """
        from ..auth.context import check_access
        from ..core.space import get_space_service

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            return await get_space_service().export_space(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def space_delete(space_id: str, confirm: bool = False) -> dict:
        """
        Supprime un espace et TOUTES ses données (irréversible).

        ⚠️ ATTENTION : cette opération est destructive et ne peut pas être annulée.
        Le paramètre confirm doit être True pour confirmer la suppression.
        Seuls les tokens admin peuvent utiliser cet outil.

        Args:
            space_id: Identifiant de l'espace à supprimer
            confirm: Doit être True pour confirmer (sécurité)

        Returns:
            Confirmation de suppression avec nombre de fichiers supprimés
        """
        from ..auth.context import check_access, check_admin_permission
        from ..core.space import get_space_service

        try:
            # Double vérification : accès + admin
            access_err = check_access(space_id)
            if access_err:
                return access_err

            admin_err = check_admin_permission()
            if admin_err:
                return admin_err

            # Sécurité : confirm obligatoire
            if not confirm:
                return {
                    "status": "error",
                    "message": (
                        "Suppression refusée : confirm=True requis. "
                        "⚠️ Cette opération est irréversible !"
                    ),
                }

            return await get_space_service().delete(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return 7  # Nombre d'outils enregistrés
