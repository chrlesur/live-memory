# -*- coding: utf-8 -*-
"""
Client MCP Streamable HTTP pour communiquer avec le serveur MCP.

Ce client utilise le SDK MCP officiel (mcp>=1.8.0) avec le transport
Streamable HTTP. Il gère :
- La connexion Streamable HTTP (endpoint unique /mcp)
- Le handshake MCP (initialize + notifications/initialized) via le SDK
- L'appel d'outils avec notifications de progression
- La gestion des erreurs et timeouts

Migration SSE → Streamable HTTP (issue #1) :
- Import : mcp.client.sse → mcp.client.streamable_http
- Fonction : sse_client → streamablehttp_client
- URL : /sse → /mcp
- Context manager : (read, write) → (read, write, _)
"""

import json
import asyncio
import logging
from typing import Optional, Callable, Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger("live_mem.cli")


class MCPClient:
    """
    Client MCP via Streamable HTTP (SDK officiel).

    Utilise le SDK MCP pour gérer le protocole complet :
    - Transport Streamable HTTP (POST/GET /mcp)
    - Handshake automatique (initialize + notifications/initialized)
    - Appel d'outils avec parsing des résultats
    """

    def __init__(self, base_url: str, token: str = "", timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    @property
    def headers(self) -> dict:
        """Headers HTTP avec auth."""
        h = {}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        on_progress: Optional[Callable] = None,
    ) -> dict:
        """
        Appelle un outil MCP via Streamable HTTP.

        Le SDK MCP gère automatiquement :
        1. Connexion Streamable HTTP vers /mcp
        2. Handshake initialize + notifications/initialized
        3. Appel tools/call
        4. Parsing de la réponse

        Args:
            tool_name: Nom de l'outil (ex: "system_health")
            arguments: Paramètres de l'outil
            on_progress: Callback optionnel pour les notifications

        Returns:
            Le résultat de l'outil (dict)
        """
        mcp_url = f"{self.base_url}/mcp"

        try:
            async with streamablehttp_client(
                mcp_url,
                headers=self.headers,
                timeout=self.timeout,
                sse_read_timeout=self.timeout,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    # Le SDK gère le handshake initialize automatiquement
                    await session.initialize()

                    # Appeler l'outil
                    result = await session.call_tool(tool_name, arguments)

                    # Extraire le résultat texte
                    if result.content and len(result.content) > 0:
                        text = result.content[0].text
                        try:
                            return json.loads(text)
                        except (json.JSONDecodeError, TypeError):
                            return {"status": "ok", "raw": text}

                    return {"status": "ok", "raw": ""}

        except Exception as e:
            return {
                "status": "error",
                "message": f"Erreur MCP : {e}",
            }

    async def list_tools(self) -> list:
        """
        Liste les outils MCP disponibles sur le serveur.

        Returns:
            Liste des outils avec nom et description
        """
        result = await self.call_tool("system_about", {})
        return result.get("tools", [])
