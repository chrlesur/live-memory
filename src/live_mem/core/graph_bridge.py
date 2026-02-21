# -*- coding: utf-8 -*-
"""
Service Graph Bridge — Pont entre Live Memory et Graph Memory.

Ce service permet à un space de pousser ses fichiers bank consolidés
dans une instance Graph Memory (graphe de connaissances) pour la
mémoire long terme.

Flux de push :
    1. Connexion MCP SSE à graph-memory
    2. Vérification/création de la mémoire cible
    3. Synchronisation : delete + re-ingest pour chaque fichier bank
    4. Nettoyage des fichiers obsolètes dans graph-memory
    5. Mise à jour des métadonnées du space

Communication : protocole MCP via HTTP/SSE (httpx + httpx-sse).
Graph Memory est un service externe, on utilise son API MCP telle quelle.

Voir le README de graph-memory pour les outils disponibles :
    - memory_create, memory_list, memory_stats
    - memory_ingest, document_list, document_delete
"""

import json
import time
import base64
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone

import httpx
from httpx_sse import aconnect_sse

from .storage import get_storage
from .models import GraphMemoryConfig

logger = logging.getLogger("live_mem.graph_bridge")


# ─────────────────────────────────────────────────────────────
# Client MCP léger pour communiquer avec Graph Memory
# ─────────────────────────────────────────────────────────────

class GraphMemoryClient:
    """
    Client MCP SSE minimaliste pour appeler les outils de Graph Memory.

    Gère le handshake MCP complet (initialize + notifications/initialized)
    puis permet d'appeler les outils par nom.

    Ce client est conçu pour être utilisé dans un context manager async :
        async with GraphMemoryClient(url, token) as gm:
            result = await gm.call_tool("memory_list", {})
    """

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        """
        Args:
            base_url: URL de base de graph-memory (ex: "http://localhost:8080")
            token: Bearer token pour l'authentification
            timeout: Timeout par appel d'outil en secondes
        """
        # Normaliser l'URL : retirer /sse si présent en fin
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/sse"):
            self._base_url = self._base_url[:-4]
        self._token = token
        self._timeout = timeout
        self._request_id = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._session_url: Optional[str] = None
        self._sse_task: Optional[asyncio.Task] = None
        self._responses: asyncio.Queue = asyncio.Queue()
        self._initialized = False

    @property
    def _headers(self) -> dict:
        """Headers HTTP avec authentification Bearer."""
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def __aenter__(self):
        """Ouvre la connexion SSE et effectue le handshake MCP."""
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ferme proprement la connexion."""
        await self._disconnect()

    async def _connect(self):
        """
        Établit la connexion SSE et effectue le handshake MCP.

        Étapes :
        1. Ouvre le client HTTP
        2. Lance l'écoute SSE en tâche de fond
        3. Attend l'endpoint de session
        4. Envoie initialize + notifications/initialized
        """
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=self._headers,
        )
        self._responses = asyncio.Queue()

        # Lancer l'écoute SSE en background
        self._sse_task = asyncio.create_task(self._listen_sse())

        # Attendre l'endpoint (max 10s)
        for _ in range(100):
            if self._session_url:
                break
            await asyncio.sleep(0.1)

        if not self._session_url:
            await self._disconnect()
            raise ConnectionError(
                f"Timeout : pas d'endpoint SSE depuis {self._base_url}/sse. "
                f"Graph Memory est-il démarré ?"
            )

        # Handshake : initialize
        self._request_id += 1
        init_req = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "live-memory-bridge",
                    "version": "0.2.0",
                },
            },
        }
        await self._client.post(
            self._session_url, json=init_req, headers=self._headers
        )

        # Attendre la réponse initialize
        try:
            await asyncio.wait_for(self._responses.get(), timeout=10)
        except asyncio.TimeoutError:
            await self._disconnect()
            raise ConnectionError("Timeout handshake initialize avec Graph Memory")

        # Notification initialized
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        await self._client.post(
            self._session_url, json=notif, headers=self._headers
        )
        await asyncio.sleep(0.1)

        self._initialized = True
        logger.info("Connecté à Graph Memory : %s", self._base_url)

    async def _disconnect(self):
        """Ferme proprement la connexion SSE et le client HTTP."""
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False
        self._session_url = None

    async def _listen_sse(self):
        """Écoute les événements SSE en arrière-plan."""
        assert self._client is not None
        try:
            async with aconnect_sse(
                self._client, "GET", f"{self._base_url}/sse",
                headers=self._headers,
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    if sse.event == "endpoint":
                        endpoint = sse.data
                        if endpoint.startswith("http"):
                            self._session_url = endpoint
                        else:
                            self._session_url = f"{self._base_url}{endpoint}"
                        continue

                    if sse.event == "message":
                        try:
                            data = json.loads(sse.data)
                        except json.JSONDecodeError:
                            continue

                        # Ignorer les notifications de progression
                        if data.get("method") == "notifications/message":
                            continue

                        # Réponse (result ou error)
                        if "result" in data or "error" in data:
                            await self._responses.put(data)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("SSE listener fermé : %s", e)
            await self._responses.put({"error": {"message": str(e)}})

    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        Appelle un outil MCP sur Graph Memory.

        Args:
            tool_name: Nom de l'outil (ex: "memory_create")
            arguments: Paramètres de l'outil

        Returns:
            Résultat de l'outil (dict)

        Raises:
            ConnectionError: Si pas connecté
            TimeoutError: Si timeout dépassé
        """
        if not self._initialized or not self._client or not self._session_url:
            raise ConnectionError("Client non connecté à Graph Memory")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        await self._client.post(
            self._session_url, json=request, headers=self._headers
        )

        # Attendre la réponse
        try:
            response = await asyncio.wait_for(
                self._responses.get(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Timeout après {self._timeout}s pour '{tool_name}' "
                f"sur Graph Memory"
            )

        # Erreur JSON-RPC
        if "error" in response:
            err = response["error"]
            return {
                "status": "error",
                "message": err.get("message", str(err)),
            }

        # Extraire le résultat (le SDK MCP encapsule dans content[0].text)
        result = response.get("result", {})
        if isinstance(result, dict) and "content" in result:
            content = result["content"]
            if isinstance(content, list) and len(content) > 0:
                text = content[0].get("text", "")
                try:
                    return json.loads(text)
                except (json.JSONDecodeError, TypeError):
                    return {"status": "ok", "raw": text}

        return result


# ─────────────────────────────────────────────────────────────
# Service Graph Bridge
# ─────────────────────────────────────────────────────────────

class GraphBridgeService:
    """
    Service orchestrateur pour le pont live-memory → graph-memory.

    Gère la configuration de connexion, la synchronisation des fichiers
    bank, et les métriques de push.
    """

    # ─────────────────────────────────────────────────────────
    # CONNECT — Configurer la connexion graph-memory
    # ─────────────────────────────────────────────────────────

    async def connect(
        self,
        space_id: str,
        url: str,
        token: str,
        memory_id: str,
        ontology: str = "general",
    ) -> dict:
        """
        Connecte un space à une instance Graph Memory.

        Opérations :
        1. Vérifie que le space existe
        2. Teste la connexion à graph-memory (health check)
        3. Vérifie/crée la mémoire cible dans graph-memory
        4. Sauvegarde la config dans _meta.json

        Args:
            space_id: Identifiant du space live-memory
            url: URL SSE de graph-memory (ex: "http://localhost:8080/sse")
            token: Bearer token pour graph-memory
            memory_id: Memory cible dans graph-memory
            ontology: Ontologie à utiliser (défaut: "general")

        Returns:
            {"status": "connected", ...} ou erreur
        """
        storage = get_storage()

        # Vérifier que le space existe
        meta_data = await storage.get_json(f"{space_id}/_meta.json")
        if meta_data is None:
            return {
                "status": "not_found",
                "message": f"Espace '{space_id}' introuvable",
            }

        # Tester la connexion à graph-memory
        try:
            async with GraphMemoryClient(url, token) as gm:
                # Vérifier la santé
                health = await gm.call_tool("system_health", {})
                if health.get("status") == "error":
                    return {
                        "status": "error",
                        "message": (
                            f"Graph Memory non disponible : "
                            f"{health.get('message', 'erreur inconnue')}"
                        ),
                    }

                # Vérifier si la mémoire existe déjà
                memories = await gm.call_tool("memory_list", {})
                existing_ids = []
                if memories.get("status") == "ok":
                    existing_ids = [
                        m.get("memory_id", m.get("id", ""))
                        for m in memories.get("memories", [])
                    ]

                memory_created = False
                if memory_id not in existing_ids:
                    # Créer la mémoire dans graph-memory
                    create_result = await gm.call_tool("memory_create", {
                        "memory_id": memory_id,
                        "name": f"Live Memory — {space_id}",
                        "description": (
                            f"Memory Bank synchronisée depuis live-memory "
                            f"space '{space_id}'"
                        ),
                        "ontology": ontology,
                    })

                    if create_result.get("status") == "error":
                        return {
                            "status": "error",
                            "message": (
                                f"Impossible de créer la mémoire '{memory_id}' "
                                f"dans Graph Memory : "
                                f"{create_result.get('message', '')}"
                            ),
                        }
                    memory_created = True
                    logger.info(
                        "Mémoire '%s' créée dans Graph Memory (ontologie: %s)",
                        memory_id, ontology,
                    )

        except ConnectionError as e:
            return {
                "status": "error",
                "message": f"Connexion impossible à Graph Memory : {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erreur lors du test de connexion : {e}",
            }

        # Sauvegarder la config dans _meta.json
        graph_config = GraphMemoryConfig(
            url=url,
            token=token,
            memory_id=memory_id,
            ontology=ontology,
        )
        meta_data["graph_memory"] = graph_config.model_dump()
        await storage.put_json(f"{space_id}/_meta.json", meta_data)

        logger.info(
            "Space '%s' connecté à Graph Memory '%s' (%s)",
            space_id, memory_id, url,
        )

        return {
            "status": "connected",
            "space_id": space_id,
            "graph_memory": {
                "url": url,
                "memory_id": memory_id,
                "ontology": ontology,
                "memory_created": memory_created,
            },
        }

    # ─────────────────────────────────────────────────────────
    # PUSH — Pousser la bank dans graph-memory
    # ─────────────────────────────────────────────────────────

    async def push(self, space_id: str) -> dict:
        """
        Pousse les fichiers bank du space dans graph-memory.

        Synchronisation intelligente (delete + re-ingest) :
        1. Liste les documents existants dans graph-memory
        2. Pour chaque fichier bank :
           - Si existe dans graph-memory → delete puis re-ingest
           - Sinon → ingest
        3. Supprime les documents dans graph-memory qui ne sont
           plus dans la bank (nettoyage)
        4. Met à jour _meta.json avec les métriques de push

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            {"status": "ok", "pushed": N, "deleted": N, "errors": N, ...}
        """
        storage = get_storage()
        t0 = time.monotonic()

        # Lire la config
        meta_data = await storage.get_json(f"{space_id}/_meta.json")
        if meta_data is None:
            return {
                "status": "not_found",
                "message": f"Espace '{space_id}' introuvable",
            }

        gm_config = meta_data.get("graph_memory")
        if not gm_config:
            return {
                "status": "error",
                "message": (
                    f"Espace '{space_id}' non connecté à Graph Memory. "
                    f"Utilisez graph_connect d'abord."
                ),
            }

        config = GraphMemoryConfig(**gm_config)
        memory_id = config.memory_id

        # Lire tous les fichiers bank depuis S3
        bank_data = await storage.list_and_get(f"{space_id}/bank/")
        bank_files = {
            item["key"].split("/")[-1]: item["content"]
            for item in bank_data
        }

        if not bank_files:
            return {
                "status": "ok",
                "space_id": space_id,
                "message": "Aucun fichier bank à pousser",
                "pushed": 0,
                "deleted": 0,
                "errors": 0,
            }

        # Connexion à graph-memory
        try:
            async with GraphMemoryClient(
                config.url, config.token, timeout=180.0
            ) as gm:
                # 1. Lister les documents existants dans graph-memory
                doc_list = await gm.call_tool("document_list", {
                    "memory_id": memory_id,
                })
                existing_docs = set()
                if doc_list.get("status") == "ok":
                    for doc in doc_list.get("documents", []):
                        existing_docs.add(doc.get("filename", ""))

                logger.info(
                    "Push '%s' → '%s' : %d fichiers bank, %d docs existants",
                    space_id, memory_id, len(bank_files), len(existing_docs),
                )

                pushed = 0
                deleted_before_reingest = 0
                errors = 0
                error_details = []

                # 2. Pour chaque fichier bank : delete si existe + ingest
                for filename, content in bank_files.items():
                    try:
                        # Si le document existe → supprimer d'abord
                        if filename in existing_docs:
                            del_result = await gm.call_tool(
                                "document_delete", {
                                    "memory_id": memory_id,
                                    "filename": filename,
                                }
                            )
                            if del_result.get("status") == "error":
                                logger.warning(
                                    "Échec suppression '%s' : %s",
                                    filename, del_result.get("message", ""),
                                )
                            else:
                                deleted_before_reingest += 1
                                logger.info("Supprimé '%s' (pré-réingestion)", filename)

                        # Encoder le contenu en base64 pour memory_ingest
                        content_bytes = content.encode("utf-8")
                        content_b64 = base64.b64encode(content_bytes).decode("ascii")

                        # Ingérer dans graph-memory
                        ingest_result = await gm.call_tool(
                            "memory_ingest", {
                                "memory_id": memory_id,
                                "content_base64": content_b64,
                                "filename": filename,
                            }
                        )

                        if ingest_result.get("status") == "error":
                            errors += 1
                            error_details.append({
                                "filename": filename,
                                "error": ingest_result.get("message", ""),
                            })
                            logger.error(
                                "Échec ingestion '%s' : %s",
                                filename, ingest_result.get("message", ""),
                            )
                        else:
                            pushed += 1
                            logger.info(
                                "Ingéré '%s' (%d octets)",
                                filename, len(content_bytes),
                            )

                    except Exception as e:
                        errors += 1
                        error_details.append({
                            "filename": filename,
                            "error": str(e),
                        })
                        logger.error("Erreur push '%s' : %s", filename, e)

                # 3. Nettoyage : supprimer les docs dans graph-memory
                #    qui ne sont plus dans la bank
                cleaned = 0
                orphan_docs = existing_docs - set(bank_files.keys())
                for orphan in orphan_docs:
                    try:
                        del_result = await gm.call_tool(
                            "document_delete", {
                                "memory_id": memory_id,
                                "filename": orphan,
                            }
                        )
                        if del_result.get("status") != "error":
                            cleaned += 1
                            logger.info(
                                "Nettoyé document orphelin '%s'", orphan
                            )
                    except Exception as e:
                        logger.warning(
                            "Échec nettoyage orphelin '%s' : %s", orphan, e
                        )

        except ConnectionError as e:
            return {
                "status": "error",
                "message": f"Connexion impossible à Graph Memory : {e}",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Erreur lors du push : {e}",
            }

        duration = round(time.monotonic() - t0, 1)

        # 4. Mettre à jour _meta.json avec les métriques
        now = datetime.now(timezone.utc).isoformat()
        gm_config["last_push"] = now
        gm_config["push_count"] = gm_config.get("push_count", 0) + 1
        gm_config["files_pushed"] = pushed
        meta_data["graph_memory"] = gm_config
        await storage.put_json(f"{space_id}/_meta.json", meta_data)

        result = {
            "status": "ok",
            "space_id": space_id,
            "memory_id": memory_id,
            "pushed": pushed,
            "deleted_before_reingest": deleted_before_reingest,
            "cleaned_orphans": cleaned,
            "errors": errors,
            "duration_seconds": duration,
        }

        if error_details:
            result["error_details"] = error_details

        logger.info(
            "Push terminé '%s' → '%s' : %d poussés, %d nettoyés, "
            "%d erreurs (%.1fs)",
            space_id, memory_id, pushed, cleaned, errors, duration,
        )

        return result

    # ─────────────────────────────────────────────────────────
    # STATUS — Vérifier la connexion et les stats
    # ─────────────────────────────────────────────────────────

    async def status(self, space_id: str) -> dict:
        """
        Vérifie le statut de la connexion graph-memory d'un space.

        Récupère :
        - Statistiques de la mémoire (documents, entités, relations)
        - Liste des documents ingérés avec leurs métadonnées
        - Top entités du graphe de connaissances
        - Historique des pushs

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            {"status": "ok", "connected": bool, "graph_stats": {...},
             "graph_documents": [...], "top_entities": [...], ...}
        """
        storage = get_storage()

        meta_data = await storage.get_json(f"{space_id}/_meta.json")
        if meta_data is None:
            return {
                "status": "not_found",
                "message": f"Espace '{space_id}' introuvable",
            }

        gm_config = meta_data.get("graph_memory")
        if not gm_config:
            return {
                "status": "ok",
                "space_id": space_id,
                "connected": False,
                "message": "Aucune connexion Graph Memory configurée",
            }

        config = GraphMemoryConfig(**gm_config)

        # Tester la connexion et récupérer les stats + documents
        try:
            async with GraphMemoryClient(config.url, config.token) as gm:
                # 1. Statistiques de la mémoire
                stats = await gm.call_tool("memory_stats", {
                    "memory_id": config.memory_id,
                })

                graph_stats = None
                top_entities = []
                if stats.get("status") == "ok":
                    graph_stats = {
                        "document_count": stats.get("document_count", 0),
                        "entity_count": stats.get("entity_count", 0),
                        "relation_count": stats.get("relation_count", 0),
                    }
                    top_entities = stats.get("top_entities", [])

                # 2. Liste des documents ingérés
                doc_list = await gm.call_tool("document_list", {
                    "memory_id": config.memory_id,
                })

                graph_documents = []
                if doc_list.get("status") == "ok":
                    for doc in doc_list.get("documents", []):
                        graph_documents.append({
                            "filename": doc.get("filename", "?"),
                            "entity_count": doc.get("entity_count", 0),
                            "ingested_at": doc.get("ingested_at", ""),
                            "size": doc.get("size_bytes", doc.get("size", 0)),
                        })

        except ConnectionError as e:
            return {
                "status": "ok",
                "space_id": space_id,
                "connected": True,
                "reachable": False,
                "config": {
                    "url": config.url,
                    "memory_id": config.memory_id,
                    "ontology": config.ontology,
                },
                "last_push": config.last_push,
                "push_count": config.push_count,
                "files_pushed": config.files_pushed,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status": "ok",
                "space_id": space_id,
                "connected": True,
                "reachable": False,
                "config": {
                    "url": config.url,
                    "memory_id": config.memory_id,
                    "ontology": config.ontology,
                },
                "error": str(e),
            }

        return {
            "status": "ok",
            "space_id": space_id,
            "connected": True,
            "reachable": True,
            "config": {
                "url": config.url,
                "memory_id": config.memory_id,
                "ontology": config.ontology,
            },
            "last_push": config.last_push,
            "push_count": config.push_count,
            "files_pushed": config.files_pushed,
            "graph_stats": graph_stats,
            "graph_documents": graph_documents,
            "top_entities": top_entities,
        }

    # ─────────────────────────────────────────────────────────
    # DISCONNECT — Retirer la connexion graph-memory
    # ─────────────────────────────────────────────────────────

    async def disconnect(self, space_id: str) -> dict:
        """
        Déconnecte un space de Graph Memory.

        Retire la configuration graph_memory de _meta.json.
        Ne supprime PAS les données dans graph-memory.

        Args:
            space_id: Identifiant du space live-memory

        Returns:
            {"status": "disconnected", ...}
        """
        storage = get_storage()

        meta_data = await storage.get_json(f"{space_id}/_meta.json")
        if meta_data is None:
            return {
                "status": "not_found",
                "message": f"Espace '{space_id}' introuvable",
            }

        if "graph_memory" not in meta_data or meta_data["graph_memory"] is None:
            return {
                "status": "ok",
                "message": (
                    f"Espace '{space_id}' n'est pas connecté "
                    f"à Graph Memory"
                ),
            }

        old_config = meta_data["graph_memory"]
        meta_data["graph_memory"] = None
        await storage.put_json(f"{space_id}/_meta.json", meta_data)

        logger.info(
            "Space '%s' déconnecté de Graph Memory '%s'",
            space_id, old_config.get("memory_id", ""),
        )

        return {
            "status": "disconnected",
            "space_id": space_id,
            "was_connected_to": {
                "url": old_config.get("url", ""),
                "memory_id": old_config.get("memory_id", ""),
                "push_count": old_config.get("push_count", 0),
            },
        }


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_graph_bridge: GraphBridgeService | None = None


def get_graph_bridge() -> GraphBridgeService:
    """Retourne le singleton GraphBridgeService."""
    global _graph_bridge
    if _graph_bridge is None:
        _graph_bridge = GraphBridgeService()
    return _graph_bridge
