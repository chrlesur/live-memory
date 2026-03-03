# Modèle de Données S3 — Live Memory

> **Version** : 0.4.0 | **Date** : 2026-03-03 | **Auteur** : Cloud Temple

---

## 1. Principes

- **S3 est la seule source de vérité** : pas de base de données, tout est fichier
- **Un bucket unique** pour tout le service (`S3_BUCKET_NAME`)
- **Un préfixe par espace** : `{space_id}/`
- **Système de fichiers** : `_system/` pour les données transversales (tokens, etc.)
- **Backups** : `_backups/` pour les snapshots

---

## 2. Arborescence S3 complète

```
{bucket}/
│
├── _system/                              # Données transversales
│   └── tokens.json                       # Registre des tokens d'authentification
│
├── _backups/                             # Snapshots des espaces
│   └── {space_id}/
│       └── {timestamp}/                  # Ex: 2026-02-20T18-00-00
│           ├── _meta.json
│           ├── _rules.md
│           ├── _synthesis.md
│           ├── bank/
│           │   ├── activeContext.md
│           │   ├── progress.md
│           │   └── ...
│           └── live/
│               ├── note_001.md
│               └── ...
│
├── {space_id}/                           # Un espace mémoire
│   ├── _meta.json                        # Métadonnées de l'espace
│   ├── _rules.md                         # Rules immuables (structure bank)
│   ├── _synthesis.md                     # Synthèse résiduelle (dernière consolidation)
│   │
│   ├── live/                             # Notes en temps réel
│   │   ├── .keep                         # Sentinelle (pour que le "dossier" existe)
│   │   ├── 20260220T140000_cline_observation_a1b2c3d4.md
│   │   ├── 20260220T140130_claude_decision_e5f6a7b8.md
│   │   ├── 20260220T141500_cline_todo_c9d0e1f2.md
│   │   └── ...
│   │
│   └── bank/                             # Memory Bank consolidée
│       ├── .keep                         # Sentinelle
│       ├── projectbrief.md               # ← Créés et maintenus
│       ├── activeContext.md              # ← par le LLM
│       ├── progress.md                   # ← selon les rules
│       └── ...                           # ← (noms dynamiques)
│
└── {autre_space_id}/                     # Autre espace (même structure)
    ├── _meta.json
    ├── _rules.md
    └── ...
```

---

## 3. Fichiers système

### 3.1 `_system/tokens.json`

Registre de tous les tokens d'authentification.

```json
{
  "version": 1,
  "tokens": [
    {
      "hash": "sha256:a1b2c3d4e5f6...",
      "name": "admin-ops",
      "permissions": ["read", "write", "admin"],
      "space_ids": [],
      "created_at": "2026-02-20T14:00:00Z",
      "expires_at": null,
      "last_used_at": "2026-02-20T17:55:00Z",
      "revoked": false
    },
    {
      "hash": "sha256:f7e8d9c0b1a2...",
      "name": "agent-cline",
      "permissions": ["read", "write"],
      "space_ids": ["projet-alpha", "projet-beta"],
      "created_at": "2026-02-20T14:05:00Z",
      "expires_at": "2027-02-20T14:05:00Z",
      "last_used_at": "2026-02-20T18:00:00Z",
      "revoked": false
    }
  ]
}
```

**Concurrence** : Protégé par un `asyncio.Lock` dédié (`LockManager.tokens`).

---

## 4. Fichiers d'un espace

### 4.1 `{space_id}/_meta.json`

Métadonnées de l'espace. Créé par `space_create`, mis à jour par `bank_consolidate` et `graph_push`.

```json
{
  "space_id": "projet-alpha",
  "description": "Projet de refonte API v3",
  "owner": "cline-dev",
  "created_at": "2026-02-20T14:00:00Z",
  "last_consolidation": "2026-02-20T16:00:00Z",
  "consolidation_count": 3,
  "total_notes_processed": 127,
  "graph_memory": {
    "url": "https://graph-mem.mcp.cloud-temple.app/sse",
    "token": "gm_xxx...",
    "memory_id": "projet-alpha-mem",
    "ontology": "general",
    "last_push": "2026-03-01T14:00:00Z",
    "push_count": 3,
    "files_pushed": 6
  },
  "version": 1
}
```

**Champs ajoutés en v0.3.0** : `graph_memory` (objet optionnel) contenant la configuration de connexion vers Graph Memory et les métriques de push.

---

### 4.2 `{space_id}/_rules.md`

Les rules définissent la **structure souhaitée** de la memory bank. Elles sont **immuables** après création de l'espace.

> **Point clé** : Le MCP ne sait pas quels fichiers bank existent ni n'existeront. C'est le LLM qui lit les rules et crée/maintient les fichiers correspondants.

---

### 4.3 `{space_id}/_synthesis.md`

Synthèse résiduelle produite par la dernière consolidation. Sert de **pont de contexte** entre deux consolidations.

```markdown
---
consolidated_at: "2026-02-20T16:00:00Z"
notes_processed: 42
---

## Synthèse de la consolidation #3

### Faits principaux
- Le module d'authentification a été implémenté et testé
- Décision : utiliser S3 comme unique backend

### Points d'attention
- Le timeout LLM de 60s est trop court
```

Ce fichier est **écrasé** à chaque consolidation.

---

### 4.4 Notes live : `{space_id}/live/{filename}.md`

Chaque note est un fichier Markdown avec front-matter YAML.

**Convention de nommage** :
```
{YYYYMMDD}T{HHMMSS}_{agent}_{category}_{uuid8}.md
```

**Format du contenu** :

```markdown
---
timestamp: "2026-02-20T14:00:00Z"
agent: "cline-dev"
category: "observation"
tags: ["auth", "bearer", "test"]
space_id: "projet-alpha"
---

Le module d'authentification Bearer token fonctionne correctement.
```

---

### 4.5 Fichiers bank : `{space_id}/bank/{filename}.md`

Les fichiers bank sont des Markdown purs, **sans front-matter**. Leur contenu est intégralement géré par le LLM lors de la consolidation.

Les noms de fichiers sont **décidés par le LLM** en se basant sur les rules.

---

## 5. Opérations S3 par outil MCP

| Outil | Opérations S3 | Pattern |
|---|---|---|
| `space_create` | PUT `_meta.json`, PUT `_rules.md`, PUT `live/.keep`, PUT `bank/.keep` | 4 PUTs |
| `space_list` | LIST `*/` (préfixes top-level), GET `*/_meta.json` | N GETs |
| `space_info` | GET `_meta.json`, LIST `live/*`, LIST `bank/*` | 1 GET + 2 LISTs |
| `space_rules` | GET `_rules.md` | 1 GET |
| `space_summary` | GET `_meta.json`, GET `_rules.md`, GET `bank/*` | N GETs |
| `space_export` | LIST + GET de tous les fichiers | N GETs |
| `space_delete` | LIST + DELETE de tous les fichiers | N DELETEs |
| `live_note` | PUT `live/{filename}` | 1 PUT |
| `live_read` | LIST `live/*`, GET fichiers sélectionnés | 1 LIST + N GETs |
| `live_search` | LIST `live/*`, GET tous, filtre texte | 1 LIST + N GETs |
| `bank_read` | GET `bank/{filename}` | 1 GET |
| `bank_read_all` | LIST `bank/*`, GET tous | 1 LIST + N GETs |
| `bank_list` | LIST `bank/*` | 1 LIST |
| `bank_consolidate` | GET rules + GET live/* + GET bank/* + PUT bank/* + DELETE live/* + PUT _synthesis | Beaucoup |
| `graph_connect` | GET+PUT `_meta.json` (ajout config graph_memory) | 1 GET + 1 PUT |
| `graph_push` | LIST `bank/*`, GET `bank/*`, GET+PUT `_meta.json` | N GETs + 1 PUT |
| `graph_status` | GET `_meta.json` | 1 GET |
| `graph_disconnect` | GET+PUT `_meta.json` (retrait config graph_memory) | 1 GET + 1 PUT |
| `backup_create` | LIST + GET tout → PUT dans `_backups/` | N GETs + N PUTs |
| `backup_restore` | GET depuis `_backups/` → PUT dans `{space_id}/` | N GETs + N PUTs |
| `admin_gc_notes` | LIST `*/live/*`, GET notes anciennes, DELETE/consolidate | Variable |

---

## 6. Considérations S3

### 6.1 Dell ECS — Configuration hybride

SigV2 pour PUT/GET/DELETE, SigV4 pour HEAD/LIST. Voir `CLOUD_TEMPLE_SERVICES.md`.

### 6.2 Limites

| Paramètre | Valeur | Impact |
|---|---|---|
| Taille max objet | 5 GB | Pas de souci (les notes font quelques KB) |
| Nombre max objets | Illimité | OK |
| Latence GET | ~20-50ms | OK pour des lectures individuelles |
| Latence LIST | ~50-100ms | Peut être lent si >1000 notes live |
| Coût LIST | 1 requête par 1000 objets | Penser à la pagination |

### 6.3 Pagination

Pour les espaces avec beaucoup de notes (>1000), le `StorageService` gère la pagination automatiquement via `list_objects_v2` avec `ContinuationToken`.

### 6.4 Cohérence

S3 offre une **cohérence forte** (strong consistency) pour les PUT et DELETE suivis de GET. Pas besoin de délai d'attente après écriture.

---

*Document mis à jour le 3 mars 2026 — Live Memory v0.4.0*
