# -*- coding: utf-8 -*-
"""
Service Tokens — Gestion des tokens d'authentification.

Les tokens sont stockés dans _system/tokens.json sur S3.
Chaque token est hashé en SHA-256 avant stockage (jamais en clair).

Architecture :
    tools/admin.py → TokenService (ce fichier) → StorageService (S3)
    auth/middleware.py → TokenService.validate_token()

Concurrence :
    Protégé par asyncio.Lock (via LockManager.tokens) pour les
    opérations read-modify-write sur tokens.json.

Voir AUTH_AND_COLLABORATION.md pour le modèle complet.
"""

import secrets
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from .storage import get_storage
from .locks import get_lock_manager
from .models import TokenInfo, TokensStore


# Préfixe des tokens générés
TOKEN_PREFIX = "lm_"

# Chemin S3 du registre de tokens
TOKENS_KEY = "_system/tokens.json"


class TokenService:
    """
    Service de gestion des tokens d'authentification.

    Toutes les opérations de modification (create, revoke, update)
    sont protégées par un asyncio.Lock pour éviter les conflits.
    """

    async def create_token(
        self,
        name: str,
        permissions: str,
        space_ids: str = "",
        expires_in_days: int = 0,
    ) -> dict:
        """
        Crée un nouveau token d'authentification.

        Le token en clair est retourné UNE SEULE FOIS. Seul le hash
        SHA-256 est stocké dans tokens.json.

        Args:
            name: Nom descriptif (ex: "agent-cline")
            permissions: "read", "read,write", ou "read,write,admin"
            space_ids: Espaces autorisés séparés par virgules (vide = tous)
            expires_in_days: Durée en jours (0 = jamais)

        Returns:
            {"status": "created", "token": "lm_...", ...}
        """
        # Générer le token : préfixe + 32 bytes base64url = 46 chars
        raw_token = TOKEN_PREFIX + secrets.token_urlsafe(32)

        # Hasher le token
        token_hash = "sha256:" + hashlib.sha256(raw_token.encode()).hexdigest()

        # Parser les permissions
        perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
        if not perm_list:
            return {"status": "error", "message": "Permissions requises"}

        # Parser les space_ids
        sid_list = [s.strip() for s in space_ids.split(",") if s.strip()]

        # Calculer l'expiration
        now = datetime.now(timezone.utc)
        expires_at = None
        if expires_in_days > 0:
            expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        # Créer l'entrée token
        token_info = TokenInfo(
            hash=token_hash,
            name=name,
            permissions=perm_list,
            space_ids=sid_list,
            created_at=now.isoformat(),
            expires_at=expires_at,
        )

        # Sauvegarder sous lock
        async with get_lock_manager().tokens:
            store = await self._load_store()
            store.tokens.append(token_info)
            await self._save_store(store)

        return {
            "status": "created",
            "name": name,
            "token": raw_token,
            "permissions": perm_list,
            "space_ids": sid_list,
            "expires_at": expires_at,
            "warning": "⚠️ Ce token ne sera PLUS JAMAIS affiché !",
        }

    async def list_tokens(self) -> dict:
        """
        Liste tous les tokens (métadonnées seulement, jamais le hash complet).

        Returns:
            {"status": "ok", "tokens": [...], "total": N}
        """
        store = await self._load_store()
        tokens_list = []
        for t in store.tokens:
            tokens_list.append({
                "hash": t.hash[:20] + "...",  # Tronqué pour la sécurité
                "name": t.name,
                "permissions": t.permissions,
                "space_ids": t.space_ids,
                "created_at": t.created_at,
                "expires_at": t.expires_at,
                "last_used_at": t.last_used_at,
                "revoked": t.revoked,
            })

        return {"status": "ok", "tokens": tokens_list, "total": len(tokens_list)}

    async def revoke_token(self, token_hash: str) -> dict:
        """
        Révoque un token (le rend inutilisable).

        Args:
            token_hash: Hash SHA-256 du token (préfixe "sha256:" ou tronqué)

        Returns:
            {"status": "ok"} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()
            found = False
            for t in store.tokens:
                if t.hash.startswith(token_hash) or token_hash.startswith(t.hash[:20]):
                    t.revoked = True
                    found = True
                    break

            if not found:
                return {"status": "not_found", "message": "Token introuvable"}

            await self._save_store(store)

        return {"status": "ok", "message": "Token révoqué"}

    async def update_token(
        self,
        token_hash: str,
        space_ids: str = "",
        permissions: str = "",
    ) -> dict:
        """
        Met à jour les permissions ou space_ids d'un token.

        Args:
            token_hash: Hash du token (préfixe ou tronqué)
            space_ids: Nouveaux espaces autorisés (vide = pas de changement)
            permissions: Nouvelles permissions (vide = pas de changement)

        Returns:
            {"status": "ok"} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()
            found = False
            for t in store.tokens:
                if t.hash.startswith(token_hash) or token_hash.startswith(t.hash[:20]):
                    if permissions:
                        t.permissions = [p.strip() for p in permissions.split(",")]
                    if space_ids:
                        t.space_ids = [s.strip() for s in space_ids.split(",")]
                    found = True
                    break

            if not found:
                return {"status": "not_found", "message": "Token introuvable"}

            await self._save_store(store)

        return {"status": "ok", "message": "Token mis à jour"}

    async def validate_token(self, raw_token: str) -> Optional[dict]:
        """
        Valide un token brut et retourne ses infos.

        Appelé par le middleware d'authentification à chaque requête.

        Args:
            raw_token: Token en clair (ex: "lm_a1B2c3...")

        Returns:
            Dict avec client_name, permissions, allowed_resources
            ou None si le token est invalide/révoqué/expiré
        """
        # Calculer le hash
        token_hash = "sha256:" + hashlib.sha256(raw_token.encode()).hexdigest()

        # Charger le store
        store = await self._load_store()
        now = datetime.now(timezone.utc).isoformat()

        for t in store.tokens:
            if t.hash != token_hash:
                continue

            # Vérifier révocation
            if t.revoked:
                return None

            # Vérifier expiration
            if t.expires_at and t.expires_at < now:
                return None

            # Token valide — mettre à jour last_used_at (best effort)
            t.last_used_at = now
            # Note: pas de lock ici pour la perf, c'est du best-effort
            try:
                await self._save_store(store)
            except Exception:
                pass  # last_used_at est informatif, pas critique

            return {
                "client_name": t.name,
                "permissions": t.permissions,
                "allowed_resources": t.space_ids,
            }

        return None  # Token inconnu

    # ─────────────────────────────────────────────────────────
    # Helpers internes
    # ─────────────────────────────────────────────────────────

    async def _load_store(self) -> TokensStore:
        """Charge le registre de tokens depuis S3."""
        storage = get_storage()
        data = await storage.get_json(TOKENS_KEY)
        if data is None:
            return TokensStore()
        return TokensStore(**data)

    async def _save_store(self, store: TokensStore) -> None:
        """Sauvegarde le registre de tokens sur S3."""
        storage = get_storage()
        await storage.put_json(TOKENS_KEY, store.model_dump())


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_token_service: TokenService | None = None


def get_token_service() -> TokenService:
    """Retourne le singleton TokenService."""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
