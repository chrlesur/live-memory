# Spécification des Outils MCP — Live Memory

> **Version** : 0.8.0 | **Date** : 2026-03-13 | **Auteur** : Cloud Temple

---

## Vue d'ensemble

Live Memory expose **35 outils MCP** répartis en 7 catégories :

| Catégorie       | Outils | Description                                      |
| --------------- | ------ | ------------------------------------------------ |
| **System** (2)  | 2      | Santé & identité du service                      |
| **Space** (7)   | 7      | CRUD des espaces mémoire                         |
| **Live** (3)    | 3      | Notes en temps réel                              |
| **Bank** (5)    | 4      | Memory Bank consolidée via LLM                   |
| **Graph** (4)   | 4      | Pont vers Graph Memory (mémoire long terme)      |
| **Backup** (5)  | 5      | Sauvegarde & restauration                        |
| **Admin** (5)   | 5      | Gestion des tokens + maintenance (GC)            |

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
{"status": "conflict", ...}             # Conflit (consolidation en cours)
```

### Permissions

| Symbole | Permission | Description                                      |
| ------- | ---------- | ------------------------------------------------ |
| 🔓      | Public     | Aucune auth requise                              |
| 🔑      | Read       | Token avec permission `read` + accès à l'espace  |
| ✏️      | Write      | Token avec permission `write` + accès à l'espace |
| 👑      | Admin      | Token avec permission `admin`                    |

---

## 1. System — Santé & identité

### `system_health` 🔓

Vérifie l'état de santé du service (S3, LLMaaS, nombre d'espaces).

```python
@mcp.tool()
async def system_health() -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "service_name": "Live Memory",
  "version": "0.8.0",
  "uptime_seconds": 3600,
  "services": {
    "s3": {"status": "ok", "latency_ms": 45},
    "llmaas": {"status": "ok", "model": "qwen3-2507:235b", "latency_ms": 120}
  },
  "spaces_count": 3
}
```

---

### `system_about` 🔓

Informations sur le service, version, outils disponibles.

```python
@mcp.tool()
async def system_about() -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "name": "Live Memory",
  "version": "0.8.0",
  "description": "Mémoire de travail partagée pour agents IA collaboratifs",
  "author": "Cloud Temple",
  "documentation": "https://github.com/chrlesur/live-memory",
  "python_version": "3.14.3",
  "tools_count": 35,
  "tools": [
    {"name": "system_health", "description": "Vérifie l'état de santé..."},
    ...
  ]
}
```

---

## 2. Space — Gestion des espaces mémoire

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
    "files": ["activeContext.md", "progress.md", "projectbrief.md"]
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

---

### `space_summary` 🔑

Synthèse complète d'un espace (rules + bank + stats live). Utile pour qu'un agent charge tout le contexte d'un coup au démarrage.

```python
@mcp.tool()
async def space_summary(space_id: str) -> dict:
```

---

### `space_export` 🔑

Exporte un espace complet en archive tar.gz (retourne en base64).

```python
@mcp.tool()
async def space_export(space_id: str) -> dict:
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

## 3. Live — Notes en temps réel

### `live_note` ✏️

Écrit une note dans l'espace. C'est l'outil principal utilisé par les agents pendant leur travail.

```python
@mcp.tool()
async def live_note(
    space_id: str,
    category: str,          # observation | decision | todo | insight | question | progress | issue
    content: str,           # Contenu de la note (texte libre)
    tags: str = ""          # Tags séparés par des virgules (optionnel)
) -> dict:
```

> **v0.8.1** : Le paramètre `agent` a été supprimé. L'identité de l'agent est toujours
> le `client_name` du token d'authentification (Token = Agent).

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
- L'agent est toujours le `client_name` du token (Token = Agent, v0.8.1)

**Catégories standard** :

| Catégorie     | Usage                           | Exemples                               |
| ------------- | ------------------------------- | -------------------------------------- |
| `observation` | Constat factuel                 | "Le build passe", "L'API retourne 200" |
| `decision`    | Choix technique/organisationnel | "On part sur S3 au lieu de SQLite"     |
| `todo`        | Tâche à faire                   | "Implémenter le module backup"         |
| `insight`     | Analyse, pattern découvert      | "Le pattern X est pertinent ici"       |
| `question`    | Question ouverte                | "Faut-il supporter le format CSV ?"    |
| `progress`    | Avancement                      | "Module auth : 80% terminé"            |
| `issue`       | Problème, bug                   | "Le timeout LLM dépasse 60s"          |

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

---

### `live_search` 🔑

Recherche texte dans les notes live (case-insensitive).

```python
@mcp.tool()
async def live_search(
    space_id: str,
    query: str,              # Texte à chercher
    limit: int = 20
) -> dict:
```

---

## 4. Bank — Memory Bank consolidée

### `bank_read` 🔑

Lit un fichier spécifique de la bank.

```python
@mcp.tool()
async def bank_read(
    space_id: str,
    filename: str            # Nom du fichier (ex: "activeContext.md")
) -> dict:
```

---

### `bank_read_all` 🔑

Lit l'ensemble de la memory bank en une seule requête. C'est l'outil qu'un agent appelle au démarrage pour charger tout son contexte mémoire.

```python
@mcp.tool()
async def bank_read_all(space_id: str) -> dict:
```

---

### `bank_list` 🔑

Liste les fichiers de la bank (sans leur contenu).

```python
@mcp.tool()
async def bank_list(space_id: str) -> dict:
```

---

### `bank_consolidate` ✏️/👑

Déclenche la consolidation LLM : lit les notes live, les rules et la bank actuelle, puis utilise le LLM pour produire les fichiers bank mis à jour.

```python
@mcp.tool()
async def bank_consolidate(
    space_id: str,
    agent: str = ""          # Filtre par agent (voir permissions ci-dessous)
) -> dict:
```

**Paramètre `agent`** (ajouté en v0.2.0, modifié en v0.7.4) :
- `agent=""` (vide) + **admin** : consolide **TOUTES** les notes
- `agent=""` (vide) + **write** : auto-détecte le caller → consolide **ses propres notes** uniquement
- `agent="mon-agent"` (= nom du caller) : consolide uniquement les notes de cet agent → permission write suffit
- `agent="autre-agent"` (≠ caller) : consolide les notes d'un autre agent → permission admin requise

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
  "llm_prompt_tokens": 17000,
  "llm_completion_tokens": 28000,
  "duration_seconds": 35.2
}
```

**⚠️ Restrictions** :
- Un seul `bank_consolidate` peut s'exécuter à la fois par espace (lock global par espace)
- Si aucune note live n'existe, retourne `{"status": "ok", "notes_processed": 0, "message": "No new notes to consolidate"}`
- Timeout configurable (`CONSOLIDATION_TIMEOUT`, défaut 600s)

---

## 5. Graph — Pont vers Graph Memory

### `graph_connect` ✏️

Connecte un space Live Memory à une instance Graph Memory. Teste la connexion, crée la mémoire si besoin.

```python
@mcp.tool()
async def graph_connect(
    space_id: str,
    url: str,                # URL de Graph Memory (ex: "http://localhost:8080/mcp")
    token: str,              # Bearer token pour Graph Memory
    memory_id: str,          # Identifiant de la mémoire cible
    ontology: str = "general"  # general | legal | cloud | managed-services | presales
) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "graph_memory": {
    "url": "https://graph-mem.mcp.cloud-temple.app/mcp",
    "memory_id": "projet-alpha-mem",
    "ontology": "general",
    "memory_status": "created"
  }
}
```

**Comportement** :
- Normalise l'URL (ajoute `/mcp` si absent)
- Teste la connexion MCP Streamable HTTP
- Crée la mémoire dans Graph Memory si elle n'existe pas
- Sauvegarde la config dans `_meta.json` (champ `graph_memory`)

---

### `graph_push` ✏️

Synchronise la bank dans Graph Memory. Supprime les anciens documents et ré-ingère les fichiers bank à jour.

```python
@mcp.tool()
async def graph_push(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "files_pushed": 6,
  "files_cleaned": 0,
  "files_failed": 0,
  "duration_seconds": 45.2,
  "details": [
    {"filename": "activeContext.md", "action": "re-ingested", "duration": 8.1},
    ...
  ]
}
```

**Comportement** :
- Le space doit d'abord être connecté via `graph_connect`
- Suppression + ré-ingestion intelligente (recalcul du graphe)
- Nettoyage des orphelins (fichiers supprimés de la bank)
- ~10-30s par fichier (extraction LLM d'entités/relations + embeddings)
- Met à jour les métriques dans `_meta.json`

---

### `graph_status` 🔑

Vérifie le statut de la connexion Graph Memory et récupère les stats du graphe.

```python
@mcp.tool()
async def graph_status(space_id: str) -> dict:
```

**Retour** :
```json
{
  "status": "ok",
  "connected": true,
  "graph_memory": {
    "url": "https://graph-mem.mcp.cloud-temple.app/mcp",
    "memory_id": "projet-alpha-mem",
    "last_push": "2026-03-01T14:00:00Z",
    "push_count": 3,
    "files_pushed": 6
  },
  "graph_stats": {
    "documents": 6,
    "entities": 45,
    "relations": 82,
    "top_entities": [...]
  }
}
```

---

### `graph_disconnect` ✏️

Déconnecte un space de Graph Memory. Les données déjà poussées restent dans le graphe.

```python
@mcp.tool()
async def graph_disconnect(space_id: str) -> dict:
```

---

## 6. Backup — Sauvegarde & restauration

### `backup_create` ✏️

Crée un snapshot complet de l'espace sur S3.

```python
@mcp.tool()
async def backup_create(
    space_id: str,
    description: str = ""
) -> dict:
```

---

### `backup_list` 🔑

Liste les backups disponibles. Si `space_id` vide → liste tous les backups accessibles.

```python
@mcp.tool()
async def backup_list(space_id: str = "") -> dict:
```

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

## 7. Admin — Gestion des tokens & maintenance

### `admin_create_token` 👑

Crée un nouveau token d'authentification.

```python
@mcp.tool()
async def admin_create_token(
    name: str,               # Nom descriptif du token
    permissions: str,         # "read", "read,write", ou "read,write,admin"
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

Liste les métadonnées de tous les tokens (jamais le token en clair).

```python
@mcp.tool()
async def admin_list_tokens() -> dict:
```

---

### `admin_revoke_token` 👑

Révoque un token (le rend définitivement inutilisable).

```python
@mcp.tool()
async def admin_revoke_token(token_hash: str) -> dict:
```

---

### `admin_update_token` 👑

Met à jour les permissions ou espaces autorisés d'un token.

```python
@mcp.tool()
async def admin_update_token(
    token_hash: str,
    space_ids: str = "",     # Nouveaux espaces (vide = pas de changement)
    permissions: str = ""    # Nouvelles permissions (vide = pas de changement)
) -> dict:
```

---

### `admin_gc_notes` 👑

Garbage Collector : identifie et traite les notes orphelines (plus vieilles que `max_age_days`).

```python
@mcp.tool()
async def admin_gc_notes(
    space_id: str = "",       # Espace cible (vide = tous les espaces)
    max_age_days: int = 7,    # Seuil en jours
    confirm: bool = False,    # False = dry-run, True = exécution
    delete_only: bool = False # Si True + confirm : supprime SANS consolider
) -> dict:
```

**3 modes** :
1. `confirm=False` (défaut) : **DRY-RUN** — scanne et rapporte le nombre de notes orphelines
2. `confirm=True` : **CONSOLIDE** les notes orphelines via LLM (avec notice "⚠️ GC consolidation forcée")
3. `confirm=True, delete_only=True` : **SUPPRIME** les notes sans consolider (perte de données)

**Retour (dry-run)** :
```json
{
  "status": "ok",
  "mode": "dry-run",
  "total_old_notes": 15,
  "spaces": {
    "projet-alpha": {
      "old_notes": 10,
      "agents": {"agent-disparu": 7, "agent-crash": 3},
      "total_size": 12500
    }
  },
  "message": "Dry-run : 15 notes orphelines trouvées. confirm=True pour consolider."
}
```

---

## Matrice complète — Outils × Permissions

| Outil                | Read | Write | Admin | Public |
| -------------------- | :--: | :---: | :---: | :----: |
| `system_health`      |      |       |       |   ✅   |
| `system_about`       |      |       |       |   ✅   |
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
| `bank_consolidate`   |      |  ✅*  |       |        |
| `graph_connect`      |      |  ✅   |       |        |
| `graph_push`         |      |  ✅   |       |        |
| `graph_status`       |  ✅  |       |       |        |
| `graph_disconnect`   |      |  ✅   |       |        |
| `backup_create`      |      |  ✅   |       |        |
| `backup_list`        |  ✅  |       |       |        |
| `backup_restore`     |      |       |  ✅   |        |
| `backup_download`    |  ✅  |       |       |        |
| `backup_delete`      |      |       |  ✅   |        |
| `admin_create_token` |      |       |  ✅   |        |
| `admin_list_tokens`  |      |       |  ✅   |        |
| `admin_revoke_token` |      |       |  ✅   |        |
| `admin_update_token` |      |       |  ✅   |        |
| `admin_gc_notes`     |      |       |  ✅   |        |

\* `bank_consolidate` : write suffit pour consolider ses propres notes (`agent=caller` ou `agent=""` auto-détecté). Admin requis pour consolider TOUTES les notes ou celles d'un autre agent (`agent=autre`).

---

*Document mis à jour le 8 mars 2026 — Live Memory v0.8.0*
