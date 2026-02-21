# -*- coding: utf-8 -*-
"""
Outils MCP — Catégorie Graph (4 outils).

Pont entre Live Memory et Graph Memory : connecter un space à une
instance de graphe de connaissances et y pousser la memory bank.

Permissions :
    - graph_connect     ✏️ (write) — Connecte un space à Graph Memory
    - graph_push        ✏️ (write) — Pousse la bank dans Graph Memory
    - graph_status      🔑 (read)  — Statut de la connexion + stats graphe
    - graph_disconnect  ✏️ (write) — Déconnecte le space de Graph Memory

Le push utilise une synchronisation intelligente :
    - Les fichiers existants sont supprimés puis ré-ingérés (recalcul du graphe)
    - Les fichiers disparus de la bank sont nettoyés dans le graphe
    - Les métriques de push sont tracées dans _meta.json

Voir core/graph_bridge.py pour la logique métier et le client MCP SSE.
"""

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> int:
    """
    Enregistre les 4 outils graph sur l'instance MCP.

    Args:
        mcp: Instance FastMCP

    Returns:
        Nombre d'outils enregistrés (4)
    """

    @mcp.tool()
    async def graph_connect(
        space_id: str,
        url: str,
        token: str,
        memory_id: str,
        ontology: str = "general",
    ) -> dict:
        """
        Connecte un space Live Memory à une instance Graph Memory.

        Teste la connexion, crée la mémoire dans Graph Memory si elle
        n'existe pas encore, puis sauvegarde la configuration dans le space.

        Une fois connecté, utilisez graph_push pour synchroniser la bank.

        Args:
            space_id: Identifiant du space live-memory
            url: URL de Graph Memory (ex: "http://localhost:8080/sse"
                 ou "http://localhost:8080")
            token: Bearer token pour Graph Memory
            memory_id: Identifiant de la mémoire cible dans Graph Memory
            ontology: Ontologie à utiliser pour l'extraction
                      (défaut: "general"). Ontologies disponibles :
                      general, legal, cloud, managed-services, presales

        Returns:
            Statut de connexion, détails de la mémoire Graph Memory
        """
        from ..auth.context import check_access, check_write_permission
        from ..core.graph_bridge import get_graph_bridge

        try:
            # Vérifier accès au space + permission write
            access_err = check_access(space_id)
            if access_err:
                return access_err

            write_err = check_write_permission()
            if write_err:
                return write_err

            return await get_graph_bridge().connect(
                space_id=space_id,
                url=url,
                token=token,
                memory_id=memory_id,
                ontology=ontology,
            )
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def graph_push(space_id: str) -> dict:
        """
        Pousse la Memory Bank dans Graph Memory.

        Synchronisation intelligente :
        1. Les fichiers bank déjà présents dans le graphe sont supprimés
           puis ré-ingérés (le graphe est recalculé avec le contenu à jour)
        2. Les nouveaux fichiers sont simplement ingérés
        3. Les fichiers supprimés de la bank sont nettoyés du graphe

        ⚠️ L'ingestion dans Graph Memory prend du temps (extraction LLM
        d'entités/relations + embeddings). Comptez ~10-30s par fichier.

        Le space doit d'abord être connecté via graph_connect.

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            Métriques de push : fichiers poussés, nettoyés, erreurs, durée
        """
        from ..auth.context import check_access, check_write_permission
        from ..core.graph_bridge import get_graph_bridge

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            write_err = check_write_permission()
            if write_err:
                return write_err

            return await get_graph_bridge().push(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def graph_status(space_id: str) -> dict:
        """
        Vérifie le statut de la connexion Graph Memory d'un space.

        Teste la connectivité vers Graph Memory et récupère les
        statistiques de la mémoire cible (documents, entités, relations).

        Retourne aussi l'historique des pushs (dernier push, compteur).

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            Statut connexion, config, stats graphe, historique pushs
        """
        from ..auth.context import check_access
        from ..core.graph_bridge import get_graph_bridge

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            return await get_graph_bridge().status(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    async def graph_disconnect(space_id: str) -> dict:
        """
        Déconnecte un space de Graph Memory.

        Retire la configuration de connexion du space.
        ⚠️ Les données déjà poussées dans Graph Memory ne sont PAS
        supprimées — elles restent dans le graphe de connaissances.

        Pour supprimer aussi les données dans Graph Memory, utilisez
        les outils de Graph Memory directement (memory_delete).

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            Confirmation de déconnexion, ancienne config
        """
        from ..auth.context import check_access, check_write_permission
        from ..core.graph_bridge import get_graph_bridge

        try:
            access_err = check_access(space_id)
            if access_err:
                return access_err

            write_err = check_write_permission()
            if write_err:
                return write_err

            return await get_graph_bridge().disconnect(space_id)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return 4  # Nombre d'outils enregistrés
