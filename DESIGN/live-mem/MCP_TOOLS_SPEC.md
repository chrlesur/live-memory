# Spécification des Outils MCP — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

---

## Vue d'ensemble

Live Memory expose **24 outils MCP** répartis en 6 catégories :

| Catégorie      | Outils                    | Description                                      |
| -------------- | ------------------------- | ------------------------------------------------ |
| **Space** (7)  | CRUD des espaces mémoire  | Créer, lister, inspecter, exporter, supprimer    |
| **Live** (3)   | Notes en temps réel       | Écrire, lire, rechercher des notes               |
| **Bank** (4)   | Memory Bank consolidée    | Lire, lister, lire tout, consolider via LLM      |
| **Backup** (5) | Sauvegarde & restauration | Créer, lister, restaurer, télécharger, supprimer |
| **Admin** (4)  | Gestion des tokens        | Créer, lister, révoquer, modifier                |
| **System** (2) | Santé & identité          | Health check, informations serveur               |

---

## Conventions

### Format de retour standardisé

Chaque outil retourne un `dict` avec un champ `status` :

```python
{"status": "ok", "data": ...}           # Succès
{"status": "error", "message": "..."}   # Erreur
{"status": "created", ...}              # Ressource créée
{"status": "deleted", ...}              # Ressource supprimée
{"status": "not_found", ...}            # Ressource introuvable
{"status": "forbidden", ...}            # Accès refusé
{"status": "conflict", ...}             # Conflit d'écriture
```

### Permissions

| Symbole | Permission | Description                                      |
| ------- | ---------- | ------------------------------------------------ |
| 🔓      | Public     | Aucune auth requise                              |
| 🔑      | Read       | Token avec permission `read` + accès à l'espace  |
| ✏️      | Write      | Token avec permission `write` + accès à l'espace |
| 👑      | Admin      | Token avec permission `admin`                    |

---

## 1. Space — Gestion des espaces mémoire

### `space_create` ✏️

Crée un nouvel espace mémoire avec ses rules.

```python
@mcp.tool()
async def space_create(
    space_id: str,          # Identifiant unique (alphanum + tirets, max 64 chars)
    description: str,       # Description courte de l'espace
    rules: str,             # Contenu Markdown des rules (structure de la bank)
    owner: str = ""         # Propriétaire (optionnel, informatif)
) -> dict:
```

**Retour** :
```json
{
  "status": "created",
  "space_id": "projet-alpha",
  "description": "Projet de refonte API",
  "rules_size": 2450,
  "created_at": "2026-02-20T18:00:00Z"
}
```

**Comportement** :
- Valide `space_id` : regex `^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`
- Crée `{space_id}/_meta.json` sur S3
- Crée `{space_id}/_rules.md` sur S3 (immuable après création)
- Crée les dossiers `{space_id}/live/` et `{space_id}/bank/` (via un fichier sentinelle `.keep`)
- Erreur si l'espace existe déjà (`status: "already_exists"`)

---

### `space_list` 🔑

Liste tous les espaces accessibles par le token courant.

```python
@mcp.tool()
async def space_list() -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "spaces": [
    {
      "space_id": "projet-alpha",
      "description": "Projet de refonte API",
      "owner": "cline-dev",
      "created_at": "2026-02-20T18:00:00Z",
      "live_notes_count": 42,
      "bank_files_count": 6
    }
  ],
  "total": 1
}
```

---

### `space_info` 🔑

Informations détaillées sur un espace.

```python
@mcp.tool()
async def space_info(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "description": "Projet de refonte API",
  "owner": "cline-dev",
  "created_at": "2026-02-20T18:00:00Z",
  "rules_size": 2450,
  "live": {
    "notes_count": 42,
    "total_size": 15600,
    "oldest_note": "2026-02-20T14:00:00Z",
    "newest_note": "2026-02-20T17:55:00Z"
  },
  "bank": {
    "files_count": 6,
    "total_size": 8900,
    "files": ["activeContext.md", "progress.md", "projectbrief.md", "systemPatterns.md", "techContext.md", "productContext.md"]
  },
  "last_consolidation": "2026-02-20T16:00:00Z",
  "synthesis_exists": true
}
```

---

### `space_rules` 🔑

Lit les rules de l'espace (immuables).

```python
@mcp.tool()
async def space_rules(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "rules": "# Memory Bank Rules\n\n## Structure\n..."
}
```

---

### `space_summary` 🔑

Synthèse complète d'un espace (rules + bank + stats live).

```python
@mcp.tool()
async def space_summary(space_id: str) -> dict:
```

**Retour** : Combine `space_info` + `space_rules` + `bank_read_all` en une seule réponse. Utile pour qu'un agent charge tout le contexte d'un coup.

---

### `space_export` 🔑

Exporte un espace complet en archive tar.gz (retourne en base64).

```python
@mcp.tool()
async def space_export(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "archive_base64": "H4sIAAAAAAAAA...",
  "archive_size": 45000,
  "files_count": 52
}
```

---

### `space_delete` 👑

Supprime un espace et TOUTES ses données (irréversible).

```python
@mcp.tool()
async def space_delete(
    space_id: str,
    confirm: bool = False    # Doit être True pour confirmer
) -> dict:
```

---

## 2. Live — Notes en temps réel

### `live_note` ✏️

Écrit une note dans l'espace. C'est l'outil principal utilisé par les agents pendant leur travail.

```python
@mcp.tool()
async def live_note(
    space_id: str,
    category: str,          # observation | decision | todo | insight | question | progress | issue
    content: str,           # Contenu de la note (texte libre ou JSON)
    agent: str = "",        # Identifiant de l'agent (auto-détecté si vide)
    tags: str = ""          # Tags séparés par des virgules (optionnel)
) -> dict:
```

**Retour** :
```json
{
  "status": "created",
  "space_id": "projet-alpha",
  "filename": "20260220T180512_cline-dev_observation_a3f8b2c1.md",
  "category": "observation",
  "agent": "cline-dev",
  "size": 350,
  "timestamp": "2026-02-20T18:05:12Z"
}
```

**Comportement** :
- Génère un nom de fichier unique : `{timestamp}_{agent}_{category}_{uuid8}.md`
- Crée le fichier avec front-matter YAML + contenu
- Aucun conflit possible (append-only, nom unique)
- Aucun lock nécessaire

**Format du fichier créé** :
```markdown
---
timestamp: "2026-02-20T18:05:12Z"
agent: "cline-dev"
category: "observation"
tags: ["auth", "module"]
space_id: "projet-alpha"
---

Le module d'authentification fonctionne correctement.
Les tests passent avec les tokens Bearer.
```

**Catégories standard** :

| Catégorie     | Usage                           | Exemples                               |
| ------------- | ------------------------------- | -------------------------------------- |
| `observation` | Constat factuel                 | "Le build passe", "L'API retourne 200" |
| `decision`    | Choix technique/organisationnel | "On part sur S3 au lieu de SQLite"     |
| `todo`        | Tâche à faire                   | "Implémenter le module backup"         |
| `insight`     | Analyse, pattern découvert      | "Le pattern X est pertinent ici"       |
| `question`    | Question ouverte                | "Faut-il supporter le format CSV ?"    |
| `progress`    | Avancement                      | "Module auth : 80% terminé"            |
| `issue`       | Problème, bug                   | "Le timeout LLM dépasse 60s"           |

---

### `live_read` 🔑

Lit les notes live récentes.

```python
@mcp.tool()
async def live_read(
    space_id: str,
    limit: int = 50,         # Nombre max de notes (défaut 50)
    category: str = "",      # Filtrer par catégorie (optionnel)
    agent: str = "",         # Filtrer par agent (optionnel)
    since: str = ""          # ISO datetime : notes après cette date (optionnel)
) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "notes": [
    {
      "filename": "20260220T180512_cline-dev_observation_a3f8b2c1.md",
      "timestamp": "2026-02-20T18:05:12Z",
      "agent": "cline-dev",
      "category": "observation",
      "tags": ["auth", "module"],
      "content": "Le module d'authentification fonctionne correctement."
    }
  ],
  "total": 1,
  "has_more": false
}
```

---

### `live_search` 🔑

Recherche texte dans les notes live.

```python
@mcp.tool()
async def live_search(
    space_id: str,
    query: str,              # Texte à chercher (case-insensitive)
    limit: int = 20
) -> dict:
```

**Retour** : Même format que `live_read`, filtré par correspondance texte.

---

## 3. Bank — Memory Bank consolidée

### `bank_read` 🔑

Lit un fichier spécifique de la bank.

```python
@mcp.tool()
async def bank_read(
    space_id: str,
    filename: str            # Nom du fichier (ex: "activeContext.md")
) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "filename": "activeContext.md",
  "content": "# Active Context\n\n## Current Focus\n...",
  "size": 2300,
  "last_modified": "2026-02-20T16:00:00Z"
}
```

---

### `bank_read_all` 🔑

Lit l'ensemble de la memory bank en une seule requête. C'est l'outil qu'un agent appelle au démarrage pour charger tout son contexte mémoire.

```python
@mcp.tool()
async def bank_read_all(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "files": [
    {"filename": "projectbrief.md", "content": "# Project Brief\n...", "size": 1200},
    {"filename": "activeContext.md", "content": "# Active Context\n...", "size": 2300},
    {"filename": "progress.md", "content": "# Progress\n...", "size": 1800}
  ],
  "total_size": 5300,
  "file_count": 3
}
```

**Note** : L'ordre des fichiers n'est PAS garanti. Le MCP retourne ce qui existe dans `bank/`, sans ordre prédéfini. C'est l'agent qui interprète les fichiers selon les rules.

---

### `bank_list` 🔑

Liste les fichiers de la bank (sans leur contenu).

```python
@mcp.tool()
async def bank_list(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "files": [
    {"filename": "activeContext.md", "size": 2300, "last_modified": "2026-02-20T16:00:00Z"},
    {"filename": "progress.md", "size": 1800, "last_modified": "2026-02-20T16:00:00Z"},
    {"filename": "projectbrief.md", "size": 1200, "last_modified": "2026-02-20T14:00:00Z"}
  ],
  "file_count": 3
}
```

---

### `bank_consolidate` ✏️

**Déclenche la consolidation** : le MCP lit les notes live, les rules et la bank actuelle, puis utilise le LLM pour produire les fichiers bank mis à jour. Ensuite les notes live sont supprimées et remplacées par une synthèse résiduelle.

```python
@mcp.tool()
async def bank_consolidate(
    space_id: str,
    ctx: Optional[Context] = None    # Pour notifications progression
) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "notes_processed": 42,
  "bank_files_updated": 4,
  "bank_files_created": 2,
  "bank_files_unchanged": 0,
  "synthesis_size": 1200,
  "llm_tokens_used": 45000,
  "duration_seconds": 35.2
}
```

**Comportement détaillé** : voir `CONSOLIDATION_LLM.md`

**⚠️ Restrictions** :
- Un seul `bank_consolidate` peut s'exécuter à la fois par espace (lock global par espace)
- Si aucune note live n'existe, retourne `{"status": "ok", "notes_processed": 0, "message": "No new notes to consolidate"}`
- Timeout configurable (`CONSOLIDATION_TIMEOUT`, défaut 600s)

---

## 4. Backup — Sauvegarde & restauration

### `backup_create` ✏️

Crée un snapshot complet de l'espace sur S3.

```python
@mcp.tool()
async def backup_create(
    space_id: str,
    description: str = ""
) -> dict:
```

**Retour** :
```json
{
  "status": "created",
  "backup_id": "projet-alpha/2026-02-20T18-00-00",
  "space_id": "projet-alpha",
  "files_backed_up": 52,
  "total_size": 45000,
  "description": "Backup avant refactoring"
}
```

**Stockage S3** : `_backups/{space_id}/{timestamp}/` contient une copie de `_meta.json`, `_rules.md`, `live/`, `bank/`, `_synthesis.md`.

---

### `backup_list` 🔑

```python
@mcp.tool()
async def backup_list(space_id: str = "") -> dict:
```

Si `space_id` vide → liste tous les backups de tous les espaces accessibles.

---

### `backup_restore` 👑

Restaure un espace depuis un backup. L'espace NE DOIT PAS exister (supprimer d'abord).

```python
@mcp.tool()
async def backup_restore(
    backup_id: str,          # Format : "space_id/timestamp"
    confirm: bool = False
) -> dict:
```

---

### `backup_download` 🔑

Télécharge un backup en archive tar.gz (base64).

```python
@mcp.tool()
async def backup_download(backup_id: str) -> dict:
```

---

### `backup_delete` 👑

Supprime un backup.

```python
@mcp.tool()
async def backup_delete(
    backup_id: str,
    confirm: bool = False
) -> dict:
```

---

## 5. Admin — Gestion des tokens

### `admin_create_token` 👑

```python
@mcp.tool()
async def admin_create_token(
    name: str,               # Nom descriptif du token
    permissions: str,         # "read", "read,write", "read,write,admin"
    space_ids: str = "",     # Espaces autorisés (vide = tous)
    expires_in_days: int = 0  # 0 = pas d'expiration
) -> dict:
```

**Retour** :
```json
{
  "status": "created",
  "name": "agent-cline",
  "token": "lm_a1b2c3d4e5f6...",
  "permissions": ["read", "write"],
  "space_ids": ["projet-alpha"],
  "expires_at": null,
  "warning": "⚠️ Ce token ne sera PLUS JAMAIS affiché !"
}
```

Le token est hashé en SHA-256 avant stockage dans `_system/tokens.json`.

---

### `admin_list_tokens` 👑

```python
@mcp.tool()
async def admin_list_tokens() -> dict:
```

Retourne les métadonnées (nom, permissions, hash tronqué) — jamais le token en clair.

---

### `admin_revoke_token` 👑

```python
@mcp.tool()
async def admin_revoke_token(token_hash: str) -> dict:
```

---

### `admin_update_token` 👑

```python
@mcp.tool()
async def admin_update_token(
    token_hash: str,
    space_ids: str = "",     # Nouveaux espaces autorisés
    permissions: str = ""    # Nouvelles permissions
) -> dict:
```

---

## 6. System — Santé & identité

### `system_health` 🔓

```python
@mcp.tool()
async def system_health() -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "services": {
    "s3": {"status": "ok", "latency_ms": 45},
    "llmaas": {"status": "ok", "model": "qwen3-2507:235b", "latency_ms": 120}
  },
  "version": "0.1.0",
  "uptime_seconds": 3600,
  "spaces_count": 3
}
```

---

### `system_about` 🔓

```python
@mcp.tool()
async def system_about() -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "name": "Live Memory MCP Server",
  "version": "0.1.0",
  "description": "Mémoire de travail partagée pour agents IA collaboratifs",
  "tools_count": 24,
  "author": "Cloud Temple",
  "documentation": "https://github.com/chrlesur/live-mem"
}
```

---

## Matrice complète — Outils × Permissions

| Outil                | Read | Write | Admin | Public |
| -------------------- | :--: | :---: | :---: | :----: |
| `space_create`       |      |  ✅   |       |        |
| `space_list`         |  ✅  |       |       |        |
| `space_info`         |  ✅  |       |       |        |
| `space_rules`        |  ✅  |       |       |        |
| `space_summary`      |  ✅  |       |       |        |
| `space_export`       |  ✅  |       |       |        |
| `space_delete`       |      |       |  ✅   |        |
| `live_note`          |      |  ✅   |       |        |
| `live_read`          |  ✅  |       |       |        |
| `live_search`        |  ✅  |       |       |        |
| `bank_read`          |  ✅  |       |       |        |
| `bank_read_all`      |  ✅  |       |       |        |
| `bank_list`          |  ✅  |       |       |        |
| `bank_consolidate`   |      |  ✅   |       |        |
| `backup_create`      |      |  ✅   |       |        |
| `backup_list`        |  ✅  |       |       |        |
| `backup_restore`     |      |       |  ✅   |        |
| `backup_download`    |  ✅  |       |       |        |
| `backup_delete`      |      |       |  ✅   |        |
| `admin_create_token` |      |       |  ✅   |        |
| `admin_list_tokens`  |      |       |  ✅   |        |
| `admin_revoke_token` |      |       |  ✅   |        |
| `admin_update_token` |      |       |  ✅   |        |
| `system_health`      |      |       |       |   ✅   |
| `system_about`       |      |       |       |   ✅   |

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
