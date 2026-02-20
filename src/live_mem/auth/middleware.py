# -*- coding: utf-8 -*-
"""
Middlewares ASGI : authentification, logging, normalisation Host.

Pile d'exécution (ordre) :
    AuthMiddleware → LoggingMiddleware → HostNormalizerMiddleware → mcp.sse_app()

L'AuthMiddleware :
    1. Extrait le Bearer token du header Authorization (ou query string)
    2. Vérifie d'abord le bootstrap key (accès admin direct)
    3. Sinon, valide le token via TokenService (lookup SHA-256 dans S3)
    4. Injecte les infos du token dans les contextvars
"""

import sys
import time
import hashlib
from typing import Optional
from .context import current_token_info
from ..config import get_settings


class AuthMiddleware:
    """
    Middleware ASGI d'authentification par Bearer token.

    Supporte deux modes de validation :
    1. Bootstrap key (variable d'env) → admin total
    2. Tokens S3 (via TokenService) → permissions granulaires
    """

    # Routes qui ne nécessitent pas d'authentification
    PUBLIC_PATHS = {"/health", "/favicon.ico"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        path = scope.get("path", "")

        # Routes publiques → pas d'auth
        if path in self.PUBLIC_PATHS:
            return await self.app(scope, receive, send)

        # Extraire le Bearer token
        token = self._extract_token(scope)
        token_info = None

        if token:
            # Valider le token (bootstrap key puis TokenService S3)
            token_info = await self._validate_token(token)

        # Injecter dans le contextvar (même si None → les outils vérifieront)
        tok = current_token_info.set(token_info)
        try:
            await self.app(scope, receive, send)
        finally:
            current_token_info.reset(tok)

    def _extract_token(self, scope) -> Optional[str]:
        """Extrait le token depuis le header Authorization ou query string."""
        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", b"").decode()
        if auth.startswith("Bearer "):
            return auth[7:]

        # Fallback: query string ?token=xxx (pour SSE dans les navigateurs)
        qs = scope.get("query_string", b"").decode()
        for param in qs.split("&"):
            if param.startswith("token="):
                return param[6:]
        return None

    async def _validate_token(self, token: str) -> Optional[dict]:
        """
        Valide un token et retourne ses infos.

        Deux modes de validation :
        1. Bootstrap key → admin total (pour le premier démarrage)
        2. TokenService → lookup SHA-256 dans _system/tokens.json sur S3

        Args:
            token: Token brut (ex: "lm_a1B2c3..." ou bootstrap key)

        Returns:
            Dict {client_name, permissions, allowed_resources} ou None
        """
        settings = get_settings()

        # Mode 1 : Bootstrap key → admin total
        if token == settings.admin_bootstrap_key:
            return {
                "client_name": "admin",
                "permissions": ["admin", "read", "write"],
                "allowed_resources": [],  # vide = accès total
            }

        # Mode 2 : Validation via TokenService (tokens stockés sur S3)
        try:
            from ..core.tokens import get_token_service
            token_info = await get_token_service().validate_token(token)
            if token_info:
                return token_info
        except Exception as e:
            # Si S3 n'est pas configuré ou tokens.json n'existe pas,
            # on continue silencieusement (le token sera invalide)
            print(f"⚠️  Auth: TokenService error: {e}", file=sys.stderr)

        return None  # Token invalide


class LoggingMiddleware:
    """
    Middleware ASGI de logging des requêtes HTTP.

    Log sur stderr : méthode, path, status, durée.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        method = scope.get("method", "?")
        t0 = time.monotonic()
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = round((time.monotonic() - t0) * 1000, 1)
            # Ne pas logger les health checks pour éviter le bruit
            if path not in ("/health",):
                print(
                    f"📡 {method} {path} → {status_code} ({elapsed}ms)",
                    file=sys.stderr,
                )


class HostNormalizerMiddleware:
    """
    Middleware ASGI qui normalise le header Host.

    Utile quand un reverse proxy (nginx/Caddy) transmet le Host public
    alors que le SDK MCP/Starlette n'accepte que localhost.
    """

    def __init__(self, app, target_host: str = "localhost"):
        self.app = app
        self.target_host = target_host.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            new_headers = []
            for key, value in scope.get("headers", []):
                if key == b"host":
                    value = self.target_host
                new_headers.append((key, value))
            scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)
