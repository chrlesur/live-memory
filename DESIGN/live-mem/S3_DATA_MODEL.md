# Modèle de Données S3 — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

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
│   ├── tokens.json                       # Registre des tokens d'authentification
│   └── config.json                       # Métadonnées globales (optionnel)
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

**Champs** :

| Champ | Type | Description |
|---|---|---|
| `hash` | string | SHA-256 du token (préfixe `sha256:`) |
| `name` | string | Nom descriptif |
| `permissions` | string[] | `["read"]`, `["read", "write"]`, ou `["read", "write", "admin"]` |
| `space_ids` | string[] | Espaces autorisés (`[]` = tous) |
| `created_at` | ISO 8601 | Date de création |
| `expires_at` | ISO 8601 / null | Date d'expiration (`null` = jamais) |
| `last_used_at` | ISO 8601 / null | Dernière utilisation |
| `revoked` | bool | `true` si révoqué |

**Concurrence** : Protégé par un `asyncio.Lock` dédié dans le serveur.

---

## 4. Fichiers d'un espace

### 4.1 `{space_id}/_meta.json`

Métadonnées de l'espace. Créé par `space_create`, jamais modifié ensuite (sauf consolidation).

```json
{
  "space_id": "projet-alpha",
  "description": "Projet de refonte API v3",
  "owner": "cline-dev",
  "created_at": "2026-02-20T14:00:00Z",
  "last_consolidation": "2026-02-20T16:00:00Z",
  "consolidation_count": 3,
  "total_notes_processed": 127,
  "version": 1
}
```

---

### 4.2 `{space_id}/_rules.md`

Les rules définissent la **structure souhaitée** de la memory bank. Elles sont **immuables** après création de l'espace.

**Exemple : rules standard "Cline Memory Bank"** :

```markdown
# Memory Bank Rules

## Structure de la Memory Bank

La memory bank doit contenir les fichiers suivants, organisés hiérarchiquement :

### 1. projectbrief.md
- Document fondateur qui cadre tous les autres
- Définit les exigences et objectifs principaux
- Source de vérité pour le périmètre du projet

### 2. productContext.md
- Pourquoi ce projet existe
- Problèmes qu'il résout
- Comment il devrait fonctionner
- Objectifs d'expérience utilisateur

### 3. systemPatterns.md
- Architecture système
- Décisions techniques clés
- Design patterns utilisés
- Relations entre composants

### 4. techContext.md
- Technologies utilisées
- Setup de développement
- Contraintes techniques
- Dépendances

### 5. activeContext.md
- Focus de travail actuel
- Changements récents
- Prochaines étapes
- Décisions actives

### 6. progress.md
- Ce qui fonctionne
- Ce qui reste à construire
- Statut actuel
- Problèmes connus

## Règles de consolidation

- Intégrer les nouvelles notes en conservant les informations existantes pertinentes
- Supprimer les informations rendues obsolètes par les nouvelles notes
- Maintenir un style factuel et concis
- Toujours utiliser le format Markdown
- Les fichiers doivent être autosuffisants (pas de références croisées implicites)
```

**Exemple : rules minimalistes "Journal de bord"** :

```markdown
# Rules — Journal de bord

## Structure

Un seul fichier : journal.md

### journal.md
- Entrées chronologiques (plus récent en haut)
- Format : ## YYYY-MM-DD suivi des événements du jour
- Résumé synthétique de chaque journée
- Conserver les 30 derniers jours, archiver le reste

## Règles de consolidation
- Grouper les notes par jour
- Résumer les notes redondantes
- Marquer les décisions importantes en **gras**
```

> **Point clé** : Le MCP ne sait pas quels fichiers bank existent ni n'existeront. C'est le LLM qui lit les rules et crée/maintient les fichiers correspondants. Si les rules définissent 6 fichiers, le LLM créera 6 fichiers. Si les rules n'en définissent qu'un, il n'en créera qu'un.

---

### 4.3 `{space_id}/_synthesis.md`

Synthèse résiduelle produite par la dernière consolidation. Sert de **pont de contexte** entre deux consolidations.

```markdown
---
consolidated_at: "2026-02-20T16:00:00Z"
notes_processed: 42
consolidation_number: 3
---

## Synthèse de la consolidation #3

### Faits principaux
- Le module d'authentification a été implémenté et testé (Bearer tokens)
- Décision : utiliser S3 comme unique backend (pas de base de données)
- Le pipeline de consolidation LLM est fonctionnel

### Points d'attention
- Le timeout LLM de 60s est trop court pour les gros espaces
- Question ouverte : faut-il supporter les webhooks pour trigger la consolidation ?

### Prochaines priorités identifiées
- Implémenter le système de backup
- Ajouter le rate limiting sur le WAF
- Écrire la documentation utilisateur
```

Ce fichier est **écrasé** à chaque consolidation. Les notes live sont **supprimées** après consolidation.

---

### 4.4 Notes live : `{space_id}/live/{filename}.md`

Chaque note est un fichier Markdown avec front-matter YAML.

**Convention de nommage** :
```
{YYYYMMDD}T{HHMMSS}_{agent}_{category}_{uuid8}.md
```

Exemples :
```
20260220T140000_cline-dev_observation_a1b2c3d4.md
20260220T140130_claude-review_decision_e5f6a7b8.md
20260220T141500_cline-dev_todo_c9d0e1f2.md
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
Tous les tests passent :
- Création de token : OK
- Vérification SHA-256 : OK
- Permissions read/write/admin : OK
- Expiration : OK
```

**Champs front-matter** :

| Champ | Type | Obligatoire | Description |
|---|---|---|---|
| `timestamp` | ISO 8601 | ✅ | Horodatage de la note |
| `agent` | string | ✅ | Identifiant de l'agent auteur |
| `category` | string | ✅ | Catégorie (observation, decision, etc.) |
| `tags` | string[] | ❌ | Tags optionnels |
| `space_id` | string | ✅ | Espace d'appartenance |

---

### 4.5 Fichiers bank : `{space_id}/bank/{filename}.md`

Les fichiers bank sont des Markdown purs, **sans front-matter**. Leur contenu est intégralement géré par le LLM lors de la consolidation.

Exemples :
```
bank/projectbrief.md
bank/activeContext.md
bank/progress.md
bank/systemPatterns.md
bank/techContext.md
bank/productContext.md
bank/journal.md            ← Si les rules définissent un journal
bank/api-specs.md          ← Si les rules le demandent
```

Les noms de fichiers sont **décidés par le LLM** en se basant sur les rules. Le MCP ne connaît pas les noms à l'avance.

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
| `backup_create` | LIST + GET tout → PUT dans `_backups/` | N GETs + N PUTs |
| `backup_restore` | GET depuis `_backups/` → PUT dans `{space_id}/` | N GETs + N PUTs |

---

## 6. Considérations S3

### 6.1 Dell ECS — Configuration hybride

Identique à graph-memory : SigV2 pour PUT/GET/DELETE, SigV4 pour HEAD/LIST. Voir `CLOUD_TEMPLE_SERVICES.md`.

### 6.2 Limites

| Paramètre | Valeur | Impact |
|---|---|---|
| Taille max objet | 5 GB | Pas de souci (les notes font quelques KB) |
| Nombre max objets | Illimité | OK |
| Latence GET | ~20-50ms | OK pour des lectures individuelles |
| Latence LIST | ~50-100ms | Peut être lent si >1000 notes live |
| Coût LIST | 1 requête par 1000 objets | Penser à la pagination |

### 6.3 Pagination

Pour les espaces avec beaucoup de notes (>1000), `LIST_OBJECTS_V2` retourne max 1000 objets par appel. Le `StorageService` doit gérer la pagination automatiquement :

```python
async def list_all_objects(self, prefix: str) -> list:
    """Liste TOUS les objets sous un préfixe, avec pagination."""
    all_keys = []
    continuation_token = None
    
    while True:
        params = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": 1000}
        if continuation_token:
            params["ContinuationToken"] = continuation_token
        
        response = self._client_v4.list_objects_v2(**params)
        all_keys.extend(response.get("Contents", []))
        
        if not response.get("IsTruncated"):
            break
        continuation_token = response["NextContinuationToken"]
    
    return all_keys
```

### 6.4 Cohérence

S3 offre une **cohérence forte** (strong consistency) depuis 2020 pour les PUT et DELETE suivis de GET. Pas besoin de délai d'attente après écriture.

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
