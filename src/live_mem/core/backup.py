# -*- coding: utf-8 -*-
"""
Service Backup — Sauvegarde et restauration d'espaces.

Les backups sont des snapshots complets stockés dans _backups/ sur S3.
Chaque backup copie tous les fichiers d'un espace dans un sous-dossier
horodaté.

Architecture :
    tools/backup.py → BackupService (ce fichier) → StorageService (S3)

Arborescence S3 :
    _backups/{space_id}/{timestamp}/
        ├── _meta.json
        ├── _rules.md
        ├── _synthesis.md
        ├── bank/...
        └── live/...

Voir S3_DATA_MODEL.md pour les détails.
"""

import base64
import io
import tarfile
from datetime import datetime, timezone

from .storage import get_storage


class BackupService:
    """
    Service de sauvegarde et restauration d'espaces mémoire.
    """

    async def create(self, space_id: str, description: str = "") -> dict:
        """
        Crée un snapshot complet de l'espace sur S3.

        Copie tous les fichiers de {space_id}/ vers _backups/{space_id}/{timestamp}/.

        Args:
            space_id: Espace à sauvegarder
            description: Description du backup (optionnel)

        Returns:
            {"status": "created", "backup_id": "...", ...}
        """
        storage = get_storage()

        # Vérifier l'existence de l'espace
        if not await storage.exists(f"{space_id}/_meta.json"):
            return {"status": "not_found", "message": f"Espace '{space_id}' introuvable"}

        # Générer le timestamp pour le backup
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y-%m-%dT%H-%M-%S")
        backup_prefix = f"_backups/{space_id}/{ts}/"
        backup_id = f"{space_id}/{ts}"

        # Lister et copier tous les fichiers
        objects = await storage.list_objects(f"{space_id}/")
        total_size = 0

        for obj in objects:
            source_key = obj["Key"]
            # Chemin relatif dans l'espace
            relative = source_key[len(space_id) + 1:]
            dest_key = backup_prefix + relative

            await storage.copy_object(source_key, dest_key)
            total_size += obj["Size"]

        return {
            "status": "created",
            "backup_id": backup_id,
            "space_id": space_id,
            "timestamp": now.isoformat(),
            "description": description,
            "files_backed_up": len(objects),
            "total_size": total_size,
        }

    async def list_backups(self, space_id: str = "") -> dict:
        """
        Liste les backups disponibles.

        Args:
            space_id: Filtrer par espace (vide = tous)

        Returns:
            {"status": "ok", "backups": [...], "total": N}
        """
        storage = get_storage()

        prefix = f"_backups/{space_id}/" if space_id else "_backups/"
        prefixes = await storage.list_prefixes(prefix, delimiter="/")

        backups = []
        if space_id:
            # Lister les timestamps pour cet espace
            for p in prefixes:
                parts = p.rstrip("/").split("/")
                ts = parts[-1] if len(parts) >= 3 else "?"
                backups.append({
                    "backup_id": f"{space_id}/{ts}",
                    "space_id": space_id,
                    "timestamp": ts,
                })
        else:
            # Lister les espaces qui ont des backups
            space_prefixes = await storage.list_prefixes("_backups/", delimiter="/")
            for sp in space_prefixes:
                sid = sp.rstrip("/").split("/")[-1]
                ts_prefixes = await storage.list_prefixes(sp, delimiter="/")
                for tp in ts_prefixes:
                    ts = tp.rstrip("/").split("/")[-1]
                    backups.append({
                        "backup_id": f"{sid}/{ts}",
                        "space_id": sid,
                        "timestamp": ts,
                    })

        return {"status": "ok", "backups": backups, "total": len(backups)}

    async def restore(self, backup_id: str) -> dict:
        """
        Restaure un espace depuis un backup.

        L'espace NE DOIT PAS exister (supprimer d'abord).

        Args:
            backup_id: Format "space_id/timestamp"

        Returns:
            {"status": "ok", "files_restored": N}
        """
        storage = get_storage()

        # Parser le backup_id
        parts = backup_id.split("/", 1)
        if len(parts) != 2:
            return {"status": "error", "message": "backup_id invalide (format: space_id/timestamp)"}

        space_id, timestamp = parts
        backup_prefix = f"_backups/{space_id}/{timestamp}/"

        # Vérifier que le backup existe
        backup_objects = await storage.list_objects(backup_prefix)
        if not backup_objects:
            return {"status": "not_found", "message": f"Backup '{backup_id}' introuvable"}

        # Vérifier que l'espace N'existe PAS
        if await storage.exists(f"{space_id}/_meta.json"):
            return {
                "status": "error",
                "message": f"L'espace '{space_id}' existe déjà. Supprimez-le d'abord.",
            }

        # Copier tous les fichiers du backup vers l'espace
        for obj in backup_objects:
            source_key = obj["Key"]
            relative = source_key[len(backup_prefix):]
            dest_key = f"{space_id}/{relative}"
            await storage.copy_object(source_key, dest_key)

        return {
            "status": "ok",
            "backup_id": backup_id,
            "space_id": space_id,
            "files_restored": len(backup_objects),
        }

    async def download(self, backup_id: str) -> dict:
        """
        Télécharge un backup en archive tar.gz (base64).

        Args:
            backup_id: Format "space_id/timestamp"

        Returns:
            {"status": "ok", "archive_base64": "...", ...}
        """
        storage = get_storage()

        parts = backup_id.split("/", 1)
        if len(parts) != 2:
            return {"status": "error", "message": "backup_id invalide"}

        space_id, timestamp = parts
        backup_prefix = f"_backups/{space_id}/{timestamp}/"

        all_objects = await storage.list_and_get(backup_prefix, exclude_keep=False)
        if not all_objects:
            return {"status": "not_found", "message": f"Backup '{backup_id}' introuvable"}

        # Créer l'archive tar.gz
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for obj in all_objects:
                arcname = obj["key"][len(backup_prefix):]
                data = obj["content"].encode("utf-8")
                info = tarfile.TarInfo(name=arcname)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        archive_bytes = buf.getvalue()

        return {
            "status": "ok",
            "backup_id": backup_id,
            "archive_base64": base64.b64encode(archive_bytes).decode("ascii"),
            "archive_size": len(archive_bytes),
            "files_count": len(all_objects),
        }

    async def delete(self, backup_id: str) -> dict:
        """
        Supprime un backup.

        Args:
            backup_id: Format "space_id/timestamp"

        Returns:
            {"status": "deleted", "files_deleted": N}
        """
        storage = get_storage()

        parts = backup_id.split("/", 1)
        if len(parts) != 2:
            return {"status": "error", "message": "backup_id invalide"}

        space_id, timestamp = parts
        backup_prefix = f"_backups/{space_id}/{timestamp}/"

        objects = await storage.list_objects(backup_prefix)
        if not objects:
            return {"status": "not_found", "message": f"Backup '{backup_id}' introuvable"}

        keys = [o["Key"] for o in objects]
        deleted = await storage.delete_many(keys)

        return {
            "status": "deleted",
            "backup_id": backup_id,
            "files_deleted": deleted,
        }


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_backup_service: BackupService | None = None


def get_backup_service() -> BackupService:
    """Retourne le singleton BackupService."""
    global _backup_service
    if _backup_service is None:
        _backup_service = BackupService()
    return _backup_service
