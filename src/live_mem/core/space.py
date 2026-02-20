# -*- coding: utf-8 -*-
"""
Service Space — Gestion des espaces mémoire et des notes live.

Ce service encapsule toutes les opérations sur les espaces :
    - CRUD espaces (create, list, info, rules, summary, export, delete)
    - Notes live (write, read, search)

Chaque méthode traduit l'opération en appels S3 via StorageService.
Les outils MCP (tools/space.py, tools/live.py) délèguent ici.

Voir S3_DATA_MODEL.md pour l'arborescence S3 des espaces.
Voir MCP_TOOLS_SPEC.md pour les signatures et retours attendus.
"""

import re
import json
import base64
import tarfile
import io
from datetime import datetime, timezone
from typing import Optional

from .storage import get_storage
from .models import SpaceMeta


# ─────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────

# Regex de validation du space_id (alphanumérique + tirets/underscores)
SPACE_ID_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")


class SpaceService:
    """
    Service de gestion des espaces mémoire et des notes live.

    Toutes les méthodes sont async et retournent un dict
    avec un champ "status" conforme à la convention MCP.
    """

    # ─────────────────────────────────────────────────────────
    # SPACES — CRUD
    # ─────────────────────────────────────────────────────────

    async def create(
        self,
        space_id: str,
        description: str,
        rules: str,
        owner: str = "",
    ) -> dict:
        """
        Crée un nouvel espace mémoire avec ses rules.

        Opérations S3 : 4 PUTs (_meta.json, _rules.md, live/.keep, bank/.keep)

        Args:
            space_id: Identifiant unique (alphanum + tirets, max 64 chars)
            description: Description courte de l'espace
            rules: Contenu Markdown des rules (structure de la bank)
            owner: Propriétaire (optionnel, informatif)

        Returns:
            {"status": "created", "space_id": ..., ...} ou erreur
        """
        # Valider le space_id
        if not SPACE_ID_REGEX.match(space_id):
            return {
                "status": "error",
                "message": (
                    f"space_id invalide : '{space_id}'. "
                    "Attendu : alphanumérique + tirets/underscores, 1-64 chars."
                ),
            }

        storage = get_storage()

        # Vérifier que l'espace n'existe pas déjà
        if await storage.exists(f"{space_id}/_meta.json"):
            return {
                "status": "already_exists",
                "message": f"L'espace '{space_id}' existe déjà",
            }

        # Créer les métadonnées
        now = datetime.now(timezone.utc).isoformat()
        meta = SpaceMeta(
            space_id=space_id,
            description=description,
            owner=owner,
            created_at=now,
        )

        # Écrire les 4 fichiers constitutifs de l'espace
        await storage.put_json(f"{space_id}/_meta.json", meta.model_dump())
        await storage.put(f"{space_id}/_rules.md", rules)
        await storage.put(f"{space_id}/live/.keep", "")
        await storage.put(f"{space_id}/bank/.keep", "")

        return {
            "status": "created",
            "space_id": space_id,
            "description": description,
            "rules_size": len(rules.encode("utf-8")),
            "created_at": now,
        }

    async def list_spaces(self, allowed_space_ids: Optional[list[str]] = None) -> dict:
        """
        Liste tous les espaces accessibles.

        Opérations S3 : LIST préfixes racine + N GETs _meta.json

        Args:
            allowed_space_ids: Liste des space_ids autorisés (None = tous)

        Returns:
            {"status": "ok", "spaces": [...], "total": N}
        """
        storage = get_storage()

        # Lister les préfixes racine (chaque espace = un préfixe)
        prefixes = await storage.list_prefixes("")

        spaces = []
        for prefix in prefixes:
            # Exclure les préfixes système (_system/, _backups/)
            if prefix.startswith("_"):
                continue

            # Extraire le space_id (retirer le / final)
            sid = prefix.rstrip("/")

            # Filtrer par permissions du token
            if allowed_space_ids is not None and sid not in allowed_space_ids:
                continue

            # Lire les métadonnées
            meta = await storage.get_json(f"{sid}/_meta.json")
            if meta is None:
                continue  # Préfixe sans _meta.json → pas un espace valide

            # Compter les notes live et fichiers bank
            live_objects = await storage.list_objects(f"{sid}/live/")
            bank_objects = await storage.list_objects(f"{sid}/bank/")
            live_count = len([o for o in live_objects if not o["Key"].endswith(".keep")])
            bank_count = len([o for o in bank_objects if not o["Key"].endswith(".keep")])

            spaces.append({
                "space_id": sid,
                "description": meta.get("description", ""),
                "owner": meta.get("owner", ""),
                "created_at": meta.get("created_at", ""),
                "live_notes_count": live_count,
                "bank_files_count": bank_count,
            })

        return {"status": "ok", "spaces": spaces, "total": len(spaces)}

    async def get_info(self, space_id: str) -> dict:
        """
        Informations détaillées sur un espace.

        Opérations S3 : GET _meta.json + LIST live/* + LIST bank/*

        Args:
            space_id: Identifiant de l'espace

        Returns:
            {"status": "ok", "space_id": ..., "live": {...}, "bank": {...}}
        """
        storage = get_storage()

        # Lire les métadonnées
        meta = await storage.get_json(f"{space_id}/_meta.json")
        if meta is None:
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        # Stats des notes live
        live_objects = await storage.list_objects(f"{space_id}/live/")
        live_files = [o for o in live_objects if not o["Key"].endswith(".keep")]

        # Stats des fichiers bank
        bank_objects = await storage.list_objects(f"{space_id}/bank/")
        bank_files = [o for o in bank_objects if not o["Key"].endswith(".keep")]

        # Vérifier l'existence de la synthèse
        synthesis_exists = await storage.exists(f"{space_id}/_synthesis.md")

        return {
            "status": "ok",
            "space_id": space_id,
            "description": meta.get("description", ""),
            "owner": meta.get("owner", ""),
            "created_at": meta.get("created_at", ""),
            "live": {
                "notes_count": len(live_files),
                "total_size": sum(o["Size"] for o in live_files),
            },
            "bank": {
                "files_count": len(bank_files),
                "total_size": sum(o["Size"] for o in bank_files),
                "files": [o["Key"].split("/")[-1] for o in bank_files],
            },
            "last_consolidation": meta.get("last_consolidation"),
            "consolidation_count": meta.get("consolidation_count", 0),
            "synthesis_exists": synthesis_exists,
        }

    async def get_rules(self, space_id: str) -> dict:
        """
        Lit les rules immuables de l'espace.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            {"status": "ok", "rules": "..."} ou not_found
        """
        storage = get_storage()
        rules = await storage.get(f"{space_id}/_rules.md")
        if rules is None:
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        return {"status": "ok", "space_id": space_id, "rules": rules}

    async def get_summary(self, space_id: str) -> dict:
        """
        Synthèse complète : info + rules + bank. L'outil de démarrage des agents.

        Args:
            space_id: Identifiant de l'espace

        Returns:
            Dict combinant info, rules et contenu bank complet
        """
        storage = get_storage()

        # Lire meta + rules
        meta = await storage.get_json(f"{space_id}/_meta.json")
        if meta is None:
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        rules = await storage.get(f"{space_id}/_rules.md") or ""

        # Lire tous les fichiers bank
        bank_data = await storage.list_and_get(f"{space_id}/bank/")
        bank_files = [
            {
                "filename": item["key"].split("/")[-1],
                "content": item["content"],
                "size": item["size"],
            }
            for item in bank_data
        ]

        # Lire la synthèse si elle existe
        synthesis = await storage.get(f"{space_id}/_synthesis.md")

        return {
            "status": "ok",
            "space_id": space_id,
            "description": meta.get("description", ""),
            "rules": rules,
            "bank_files": bank_files,
            "bank_file_count": len(bank_files),
            "synthesis": synthesis,
        }

    async def export_space(self, space_id: str) -> dict:
        """
        Exporte un espace complet en archive tar.gz (base64).

        Args:
            space_id: Identifiant de l'espace

        Returns:
            {"status": "ok", "archive_base64": "...", "files_count": N}
        """
        storage = get_storage()

        # Vérifier l'existence
        if not await storage.exists(f"{space_id}/_meta.json"):
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        # Lire tous les fichiers de l'espace
        all_objects = await storage.list_and_get(f"{space_id}/", exclude_keep=False)

        # Créer l'archive tar.gz en mémoire
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for obj in all_objects:
                # Nom relatif dans l'archive (sans le space_id/ prefix)
                arcname = obj["key"][len(space_id) + 1:]
                data = obj["content"].encode("utf-8")
                info = tarfile.TarInfo(name=arcname)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        archive_bytes = buf.getvalue()

        return {
            "status": "ok",
            "space_id": space_id,
            "archive_base64": base64.b64encode(archive_bytes).decode("ascii"),
            "archive_size": len(archive_bytes),
            "files_count": len(all_objects),
        }

    async def delete(self, space_id: str) -> dict:
        """
        Supprime un espace et TOUTES ses données (irréversible).

        Args:
            space_id: Identifiant de l'espace

        Returns:
            {"status": "deleted", "files_deleted": N}
        """
        storage = get_storage()

        # Vérifier l'existence
        if not await storage.exists(f"{space_id}/_meta.json"):
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        # Lister TOUS les fichiers de l'espace
        all_objects = await storage.list_objects(f"{space_id}/")
        all_keys = [o["Key"] for o in all_objects]

        # Supprimer en batch
        deleted = await storage.delete_many(all_keys)

        return {
            "status": "deleted",
            "space_id": space_id,
            "files_deleted": deleted,
        }


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_space_service: SpaceService | None = None


def get_space_service() -> SpaceService:
    """Retourne le singleton SpaceService."""
    global _space_service
    if _space_service is None:
        _space_service = SpaceService()
    return _space_service
