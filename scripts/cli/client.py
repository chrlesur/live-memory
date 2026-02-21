# -*- coding: utf-8 -*-
"""
Client HTTP/SSE pour communiquer avec le serveur MCP.

Ce client gère :
- La connexion SSE (Server-Sent Events)
- L'envoi de requêtes JSON-RPC via HTTP POST
- La réception des notifications de progression
- La gestion des erreurs et reconnexion
"""

import json
import asyncio
from typing import Optional, Callable, Any

import httpx
from httpx_sse import aconnect_sse


class MCPClient:
    """Client MCP générique via HTTP/SSE."""

    def __init__(self, base_url: str, token: str = "", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session_url: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0

    @property
    def headers(self) -> dict:
        """Headers HTTP avec auth."""
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def connect(self) -> str:
        """
        Établit la connexion SSE et récupère l'URL de session.

        Returns:
            L'URL de session pour envoyer les messages
        """
        self._client = httpx.AsyncClient(timeout=self.timeout, headers=self.headers)

        async with aconnect_sse(
            self._client, "GET", f"{self.base_url}/sse",
            headers=self.headers,
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.event == "endpoint":
                    endpoint = sse.data
                    # L'endpoint peut être relatif ou absolu
                    if endpoint.startswith("http"):
                        self._session_url = endpoint
                    else:
                        self._session_url = f"{self.base_url}{endpoint}"
                    return self._session_url

        raise ConnectionError("Impossible d'obtenir l'URL de session SSE")

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Appelle un outil MCP avec handshake initialize complet.

        Le protocole MCP exige :
        1. Client → initialize (capabilities + clientInfo)
        2. Serveur → réponse initialize
        3. Client → notifications/initialized
        4. Client → tools/call

        Args:
            tool_name: Nom de l'outil (ex: "system_health")
            arguments: Paramètres de l'outil
            on_progress: Callback optionnel pour les notifications

        Returns:
            Le résultat de l'outil (dict)
        """
        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
        ) as client:
            # ── Variables partagées entre SSE listener et requêtes ──
            session_url = None
            responses = asyncio.Queue()
            init_done = asyncio.Event()

            async def _listen_sse():
                nonlocal session_url
                try:
                    async with aconnect_sse(
                        client, "GET", f"{self.base_url}/sse",
                        headers=self.headers,
                    ) as event_source:
                        async for sse in event_source.aiter_sse():
                            if sse.event == "endpoint":
                                endpoint = sse.data
                                if endpoint.startswith("http"):
                                    session_url = endpoint
                                else:
                                    session_url = f"{self.base_url}{endpoint}"
                                continue

                            if sse.event == "message":
                                try:
                                    data = json.loads(sse.data)
                                except json.JSONDecodeError:
                                    continue

                                # Notification de progression
                                if data.get("method") == "notifications/message":
                                    if on_progress:
                                        msg = data.get("params", {}).get(
                                            "data", data.get("params", {})
                                        )
                                        await on_progress(msg)
                                    continue

                                # Réponse (initialize ou tools/call)
                                if "result" in data or "error" in data:
                                    await responses.put(data)

                except Exception as e:
                    await responses.put({"error": {"message": str(e)}})

            # ── Lancer l'écoute SSE en tâche de fond ──
            sse_task = asyncio.create_task(_listen_sse())

            # Attendre l'endpoint
            for _ in range(50):
                if session_url:
                    break
                await asyncio.sleep(0.1)

            if not session_url:
                sse_task.cancel()
                raise ConnectionError(
                    f"Timeout: pas d'endpoint SSE depuis {self.base_url}/sse"
                )

            # ── 1. Handshake : initialize ──
            self._request_id += 1
            init_request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "live-mem-recette",
                        "version": "1.0.0",
                    },
                },
            }
            await client.post(session_url, json=init_request, headers=self.headers)

            # Attendre la réponse initialize
            try:
                init_resp = await asyncio.wait_for(responses.get(), timeout=10)
            except asyncio.TimeoutError:
                sse_task.cancel()
                raise ConnectionError("Timeout handshake initialize")

            # ── 2. Notification initialized ──
            notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            await client.post(session_url, json=notif, headers=self.headers)
            await asyncio.sleep(0.1)  # Laisser le serveur traiter

            # ── 3. Appel de l'outil ──
            self._request_id += 1
            tool_request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }
            await client.post(session_url, json=tool_request, headers=self.headers)

            # ── 4. Attendre la réponse ──
            try:
                response = await asyncio.wait_for(responses.get(), timeout=self.timeout)
            except asyncio.TimeoutError:
                sse_task.cancel()
                raise TimeoutError(f"Timeout après {self.timeout}s pour '{tool_name}'")

            sse_task.cancel()

            # ── 5. Extraire le résultat ──
            if "error" in response:
                return {
                    "status": "error",
                    "message": response["error"].get("message", str(response["error"])),
                }

            result = response.get("result", {})

            # Le SDK MCP encapsule le résultat dans content[0].text
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
                if isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "")
                    try:
                        return json.loads(text)
                    except (json.JSONDecodeError, TypeError):
                        return {"status": "ok", "raw": text}

            return result

    async def list_tools(self) -> list:
        """
        Liste les outils MCP disponibles sur le serveur.

        Returns:
            Liste des outils avec nom et description
        """
        result = await self.call_tool("system_about", {})
        return result.get("tools", [])
