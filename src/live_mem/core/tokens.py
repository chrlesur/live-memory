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

# Permissions reconnues par le système d'authentification
VALID_PERMISSIONS = {"read", "write", "admin"}


class TokenService:
    """
    Service de gestion des tokens d'authentification.

    Toutes les opérations de modification (create, revoke, update)
    sont protégées par un asyncio.Lock pour éviter les conflits.
    """

    def __init__(self):
        # VULN-01 fix : cache en mémoire pour last_used_at
        # Évite la race condition d'écriture S3 dans validate_token()
        self._last_used_cache: dict[str, str] = {}

    def _find_token_by_hash(self, store: "TokensStore", token_hash: str) -> tuple:
        """
        Trouve un token par préfixe de hash (VULN-03 fix).

        Retourne (index, token) ou (-1, None) si introuvable.
        Retourne (-2, None) si le préfixe est ambigu (multiple matches).

        Exige un minimum de 16 caractères pour le préfixe.
        """
        if len(token_hash) < 16:
            return (-3, None)  # Préfixe trop court

        matches = [(i, t) for i, t in enumerate(store.tokens) if t.hash.startswith(token_hash)]

        if len(matches) == 0:
            return (-1, None)
        if len(matches) > 1:
            return (-2, None)
        return matches[0]

    def _token_not_found_or_ambiguous(self, idx: int, token_hash: str) -> dict | None:
        """Retourne un message d'erreur si le token n'est pas trouvé, ou None si OK."""
        if idx == -3:
            return {"status": "error", "message": f"Hash trop court ({len(token_hash)} chars). Minimum 16 caractères requis."}
        if idx == -2:
            return {"status": "error", "message": "Préfixe de hash ambigu — plusieurs tokens correspondent. Fournissez un hash plus long."}
        if idx == -1:
            return {"status": "not_found", "message": "Token introuvable"}
        return None

    async def create_token(
        self,
        name: str,
        permissions: str,
        space_ids: str = "",
        expires_in_days: int = 0,
        email: str = "",
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

        # Parser et valider les permissions
        perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
        if not perm_list:
            return {"status": "error", "message": "Permissions requises"}
        invalid = [p for p in perm_list if p not in VALID_PERMISSIONS]
        if invalid:
            return {
                "status": "error",
                "message": (
                    f"Permissions invalides : {invalid}. "
                    f"Valeurs acceptées : {sorted(VALID_PERMISSIONS)}"
                ),
            }

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
            email=email,
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
                "hash": t.hash,  # Hash complet pour identification
                "name": t.name,
                "email": t.email,
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

        VULN-03 fix : utilise _find_token_by_hash pour une correspondance
        sécurisée (min 16 chars, détection d'ambiguïté).

        Args:
            token_hash: Hash SHA-256 du token (min 16 chars de préfixe)

        Returns:
            {"status": "ok"} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()
            idx, token = self._find_token_by_hash(store, token_hash)
            err = self._token_not_found_or_ambiguous(idx, token_hash)
            if err:
                return err

            token.revoked = True
            await self._save_store(store)

        return {"status": "ok", "message": f"Token '{token.name}' révoqué"}

    async def delete_token(self, token_hash: str) -> dict:
        """
        Supprime physiquement un token du registre.

        VULN-03 fix : utilise _find_token_by_hash pour une correspondance
        sécurisée (min 16 chars, détection d'ambiguïté).

        Args:
            token_hash: Hash SHA-256 du token (min 16 chars de préfixe)

        Returns:
            {"status": "deleted", "name": "..."} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()
            idx, token = self._find_token_by_hash(store, token_hash)
            err = self._token_not_found_or_ambiguous(idx, token_hash)
            if err:
                return err

            deleted_name = token.name
            store.tokens.pop(idx)
            await self._save_store(store)

        return {
            "status": "deleted",
            "name": deleted_name,
            "message": f"Token '{deleted_name}' supprimé physiquement",
            "remaining": len(store.tokens),
        }

    async def purge_tokens(self, revoked_only: bool = True) -> dict:
        """
        Supprime physiquement plusieurs tokens du registre.

        Args:
            revoked_only: Si True, ne supprime que les tokens révoqués.
                         Si False, supprime TOUS les tokens.

        Returns:
            {"status": "ok", "deleted": N, "remaining": M}
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()
            original_count = len(store.tokens)

            if revoked_only:
                store.tokens = [t for t in store.tokens if not t.revoked]
            else:
                store.tokens = []

            deleted_count = original_count - len(store.tokens)
            await self._save_store(store)

        return {
            "status": "ok",
            "deleted": deleted_count,
            "remaining": len(store.tokens),
            "mode": "revoked_only" if revoked_only else "all",
            "message": f"{deleted_count} token(s) supprimé(s) physiquement",
        }

    async def update_token(
        self,
        token_hash: str,
        space_ids: str = "",
        permissions: str = "",
        email: str = "",
    ) -> dict:
        """
        Met à jour les permissions ou space_ids d'un token.

        VULN-03 fix : utilise _find_token_by_hash pour une correspondance
        sécurisée (min 16 chars, détection d'ambiguïté).

        Args:
            token_hash: Hash du token (min 16 chars de préfixe)
            space_ids: Nouveaux espaces autorisés (vide = pas de changement)
            permissions: Nouvelles permissions (vide = pas de changement)

        Returns:
            {"status": "ok"} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()

            # Valider les permissions avant modification
            if permissions:
                perm_list = [p.strip() for p in permissions.split(",") if p.strip()]
                invalid = [p for p in perm_list if p not in VALID_PERMISSIONS]
                if invalid:
                    return {
                        "status": "error",
                        "message": (
                            f"Permissions invalides : {invalid}. "
                            f"Valeurs acceptées : {sorted(VALID_PERMISSIONS)}"
                        ),
                    }

            idx, token = self._find_token_by_hash(store, token_hash)
            err = self._token_not_found_or_ambiguous(idx, token_hash)
            if err:
                return err

            if permissions:
                token.permissions = [p.strip() for p in permissions.split(",") if p.strip()]
            if space_ids:
                token.space_ids = [s.strip() for s in space_ids.split(",")]
            if email:
                token.email = email

            await self._save_store(store)

        return {"status": "ok", "message": f"Token '{token.name}' mis à jour"}

    async def add_space_to_token(self, token_hash: str, space_id: str) -> dict:
        """
        Ajoute un space_id à la liste des espaces autorisés d'un token.

        Appelé automatiquement par space_create quand un client restreint
        crée un nouvel espace. Sans cet ajout, le client ne pourrait pas
        accéder au space qu'il vient de créer (deadlock UX).

        Si le token a space_ids=[] (accès à tous), cette méthode ne fait rien
        car le token a déjà accès à tous les espaces.

        Args:
            token_hash: Hash SHA-256 du token courant
            space_id: ID du space à ajouter

        Returns:
            {"status": "ok"} ou {"status": "skipped"} ou erreur
        """
        async with get_lock_manager().tokens:
            store = await self._load_store()

            for t in store.tokens:
                if t.hash == token_hash:
                    # Si le token a déjà accès à tous les espaces, rien à faire
                    if not t.space_ids:
                        return {
                            "status": "skipped",
                            "message": "Token has access to all spaces",
                        }
                    # Si le space est déjà dans la liste, rien à faire
                    if space_id in t.space_ids:
                        return {
                            "status": "skipped",
                            "message": f"Space '{space_id}' already in token",
                        }
                    # Ajouter le space
                    t.space_ids.append(space_id)
                    await self._save_store(store)
                    return {
                        "status": "ok",
                        "message": f"Space '{space_id}' added to token",
                        "space_ids": t.space_ids,
                    }

            return {"status": "not_found", "message": "Token not found"}

    async def validate_token(self, raw_token: str) -> Optional[dict]:
        """
        Valide un token brut et retourne ses infos.

        Appelé par le middleware d'authentification à chaque requête.

        VULN-01 (audit v1.0.0) : l'écriture de last_used_at a été supprimée
        de cette méthode pour éliminer la race condition avec les opérations
        sous lock (create/revoke/update). last_used_at est désormais mis à
        jour de manière différée via _update_last_used().

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

            # Token valide — mise à jour last_used_at différée (en mémoire)
            # VULN-01 fix : on ne fait plus _save_store() ici pour éviter
            # la race condition avec create/revoke/update qui sont sous lock.
            self._last_used_cache[token_hash] = now

            return {
                "type": "token",
                "client_name": t.name,
                "permissions": t.permissions,
                "allowed_resources": t.space_ids,
                "token_hash": t.hash,
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
