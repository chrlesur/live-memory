# -*- coding: utf-8 -*-
"""
Outils MCP — Catégorie Bank (4 outils).

Memory Bank consolidée : lire, lister, consolider via LLM.

Permissions :
    - bank_read        🔑 (read)  — Lit un fichier bank spécifique
    - bank_read_all    🔑 (read)  — Lit toute la bank (démarrage agent)
    - bank_list        🔑 (read)  — Liste les fichiers bank (sans contenu)
    - bank_consolidate ✏️ (write) — Déclenche la consolidation LLM

La consolidation est l'opération qui transforme les notes live en
fichiers bank structurés. Un seul consolidate à la fois par espace
(protégé par asyncio.Lock).

Voir CONSOLIDATION_LLM.md pour le pipeline détaillé.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field


def register(mcp: FastMCP) -> int:
    """
    Enregistre les 4 outils bank sur l'instance MCP.

    Args:
        mcp: Instance FastMCP

    Returns:
        Nombre d'outils enregistrés (4)
    """

    @mcp.tool()
    async def bank_read(
        space_id: Annotated[str, Field(description="Identifiant de l'espace")],
        filename: Annotated[str, Field(description="Nom du fichier bank (ex: 'activeContext.md', 'progress.md')")],
    ) -> dict:
        """
        Lit un fichier spécifique de la Memory Bank.

        Les fichiers bank sont du Markdown pur, créés et maintenus
        par le LLM lors de la consolidation.

        Args:
            space_id: Identifiant de l'espace
            filename: Nom du fichier (ex: "activeContext.md")

        Returns:
            Contenu du fichier, taille, date de modification
        """
        from ..auth.context import check_access
        from ..core.storage import get_storage

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            storage = get_storage()
            key = f"{space_id}/bank/{filename}"
            content = await storage.get(key)

            if content is None:
                return {
                    "status": "not_found",
                    "message": f"Fichier '{filename}' introuvable dans '{space_id}'",
                }

            return {
                "status": "ok",
                "space_id": space_id,
                "filename": filename,
                "content": content,
                "size": len(content.encode("utf-8")),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def bank_read_all(
        space_id: Annotated[str, Field(description="Identifiant de l'espace")],
    ) -> dict:
        """
        Lit l'ensemble de la Memory Bank en une seule requête.

        C'est l'outil qu'un agent appelle au démarrage pour charger
        tout son contexte mémoire d'un coup.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Tous les fichiers bank avec leur contenu
        """
        from ..auth.context import check_access
        from ..core.storage import get_storage

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            storage = get_storage()

            # Vérifier l'existence de l'espace
            if not await storage.exists(f"{space_id}/_meta.json"):
                return {
                    "status": "not_found",
                    "message": f"Espace '{space_id}' introuvable",
                }

            # Lire tous les fichiers bank
            bank_data = await storage.list_and_get(f"{space_id}/bank/")
            files = [
                {
                    "filename": item["key"].split("/")[-1],
                    "content": item["content"],
                    "size": item["size"],
                }
                for item in bank_data
            ]

            total_size = sum(f["size"] for f in files)

            return {
                "status": "ok",
                "space_id": space_id,
                "files": files,
                "total_size": total_size,
                "file_count": len(files),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def bank_list(
        space_id: Annotated[str, Field(description="Identifiant de l'espace")],
    ) -> dict:
        """
        Liste les fichiers de la Memory Bank (sans leur contenu).

        Utile pour connaître la structure de la bank avant de lire
        des fichiers spécifiques.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Liste des fichiers avec taille et date de modification
        """
        from ..auth.context import check_access
        from ..core.storage import get_storage

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            storage = get_storage()

            if not await storage.exists(f"{space_id}/_meta.json"):
                return {
                    "status": "not_found",
                    "message": f"Espace '{space_id}' introuvable",
                }

            # Lister les objets bank (sans les .keep)
            objects = await storage.list_objects(f"{space_id}/bank/")
            files = [
                {
                    "filename": o["Key"].split("/")[-1],
                    "size": o["Size"],
                    "last_modified": str(o.get("LastModified", "")),
                }
                for o in objects
                if not o["Key"].endswith(".keep")
            ]

            return {
                "status": "ok",
                "space_id": space_id,
                "files": files,
                "file_count": len(files),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def bank_consolidate(
        space_id: Annotated[str, Field(description="Identifiant de l'espace à consolider")],
        agent: Annotated[str, Field(default="", description="Nom de l'agent dont consolider les notes (vide = toutes, admin requis)")] = "",
    ) -> dict:
        """
        Déclenche la consolidation : le LLM lit les notes live et produit
        les fichiers bank mis à jour selon les rules.

        ⚠️ Un seul consolidate peut s'exécuter à la fois par espace.
        Si une consolidation est déjà en cours, retourne "conflict".

        Le pipeline :
        1. Lit les rules, synthèse, notes live, bank actuelle
        2. Envoie tout au LLM (qwen3-2507:235b)
        3. Écrit les fichiers bank mis à jour
        4. Supprime les notes live traitées
        5. Met à jour la synthèse résiduelle

        Args:
            space_id: Identifiant de l'espace à consolider
            agent: Nom de l'agent dont consolider les notes.
                   Vide + admin = consolide TOUTES les notes.
                   Vide + write = auto-détecte le caller (ses propres notes).
                   Si l'agent correspond au token → write suffit.
                   Si l'agent est différent → admin requis.

        Returns:
            Métriques de consolidation (notes traitées, fichiers MAJ, tokens)
        """
        from ..auth.context import (
            check_access, check_write_permission,
            check_admin_permission, get_current_agent_name,
        )
        from ..core.locks import get_lock_manager
        from ..core.consolidator import get_consolidator

        try:
            # Vérifier accès à l'espace
            access_err = check_access(space_id)
            if access_err:
                return access_err

            # Identifier le caller (client_name du token)
            caller = get_current_agent_name()

            # Règles de permissions pour bank_consolidate :
            #
            # 1. admin → peut consolider tout (agent="" = toutes les notes)
            #    ou les notes d'un agent spécifique (agent="xxx")
            #
            # 2. write (pas admin) → ne peut consolider QUE ses propres notes
            #    - agent="" → auto-set à caller (on consolide ses propres notes)
            #    - agent=caller → OK
            #    - agent=autre → REFUSÉ (admin requis)
            #
            # 3. read → REFUSÉ (write minimum requis)

            admin_err = check_admin_permission()
            is_admin = admin_err is None

            if is_admin:
                # Admin : peut tout consolider, pas de restriction
                pass
            else:
                # Vérifier au minimum la permission write
                write_err = check_write_permission()
                if write_err:
                    return write_err

                # Write sans admin : on ne peut consolider que ses notes
                if agent and agent != caller:
                    return {
                        "status": "error",
                        "message": (
                            f"Permission 'admin' requise pour consolider "
                            f"les notes de l'agent '{agent}'. "
                            f"Vous pouvez consolider vos propres notes "
                            f"avec agent='{caller}' ou agent='' (auto-détection)."
                        ),
                    }
                # Auto-détection : agent vide → consolider ses propres notes
                if not agent:
                    agent = caller

            # Vérifier le lock de consolidation
            lock = get_lock_manager().consolidation(space_id)
            if lock.locked():
                return {
                    "status": "conflict",
                    "message": (
                        f"Consolidation déjà en cours pour '{space_id}'. "
                        "Réessayez dans quelques minutes."
                    ),
                }

            # Exécuter la consolidation sous lock
            # agent="" → consolide TOUTES les notes (pas de filtre)
            # agent="mon-agent" → consolide uniquement les notes de cet agent
            async with lock:
                return await get_consolidator().consolidate(space_id, agent=agent)

        except Exception as e:
            return {"status": "error", "message": str(e)}

    return 4  # Nombre d'outils enregistrés
