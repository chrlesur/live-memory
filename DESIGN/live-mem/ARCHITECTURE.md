# Architecture — Live Memory MCP Server

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple  
> **Projet** : live-mem | **Licence** : Apache 2.0

---

## 1. Vision

**Live Memory** est un serveur MCP qui fournit une **mémoire de travail partagée** (Memory Bank) pour des agents IA collaboratifs. Contrairement à graph-memory (mémoire long terme par Knowledge Graph), live-mem est une **mémoire live** : les agents y écrivent en temps réel, et un LLM intégré consolide automatiquement ces notes en une memory bank structurée.

### Philosophie

```
graph-memory  = Mémoire LONG TERME (documents → Knowledge Graph → RAG)
live-mem      = Mémoire de TRAVAIL (notes live → LLM → Memory Bank)
```

### Principes Clés

1. **Deux modes complémentaires** :
   - **Mode Live** : Les agents écrivent des notes en continu (observations, décisions, todos, insights)
   - **Mode Bank** : Le MCP consolide les notes en fichiers structurés via LLM, puis nettoie le live

2. **Bank dynamique, pas hardcodée** : La structure de la memory bank est définie par les **rules** fournies à la création de l'espace. Le LLM crée et maintient les fichiers bank selon ces rules. Le MCP ne connaît aucun nom de fichier à l'avance.

3. **S3 comme seule source de vérité** : Pas de base de données (pas de Neo4j, pas de Qdrant). Tout est fichier Markdown/JSON sur S3. Simple, portable, auditable.

4. **Multi-agents natif** : Plusieurs agents peuvent écrire simultanément dans le même espace sans conflit (pattern append-only pour les notes live).

5. **LLM intégré** : Le MCP utilise un LLM (qwen3-2507:235b via LLMaaS Cloud Temple) pour la consolidation. Les agents ne peuvent pas écrire directement dans la bank — seul le LLM le fait.

---

## 2. Positionnement

| Aspect              | graph-memory                   | live-mem                                        |
| ------------------- | ------------------------------ | ----------------------------------------------- |
| **Type de mémoire** | Long terme (Knowledge Base)    | Mémoire de travail (Working Memory)             |
| **Input**           | Documents (PDF, DOCX, MD, CSV) | Notes textuelles des agents                     |
| **Stockage**        | Neo4j + Qdrant + S3            | **S3 uniquement**                               |
| **Intelligence**    | Extraction d'entités/relations | Consolidation & synthèse                        |
| **LLM utilisé**     | gpt-oss:120b (extraction)      | qwen3-2507:235b (consolidation)                 |
| **Recherche**       | Hybride Graph + RAG vectoriel  | Lecture directe fichiers + recherche texte      |
| **Agents**          | 1 agent par requête            | **Multi-agents collaboratifs**                  |
| **Analogie**        | Une bibliothèque               | Un **tableau blanc partagé** + cahier structuré |

---

## 3. Architecture

### 3.1 Vue d'ensemble

```
          Agent Cline         Agent Claude        Agent X
              │                    │                 │
              └────────┬───────────┘                 │
                       │                             │
                       ▼ MCP Protocol (HTTP/SSE)     ▼
┌──────────────────────────────────────────────────────────┐
│                    Coraza WAF (Caddy)                     │
│  • OWASP CRS • Rate Limiting • TLS Let's Encrypt        │
└──────────────────────────┬───────────────────────────────┘
                           │ Réseau Docker interne
                           ▼
┌──────────────────────────────────────────────────────────┐
│              Live Memory MCP Server (:8002)               │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │  24 Outils MCP  │  │  LLM Service     │               │
│  │  (server.py)    │  │  (consolidator)  │               │
│  └────────┬────────┘  └────────┬─────────┘               │
│           │                    │                          │
│  ┌────────┴────────────────────┴─────────┐               │
│  │         Storage Service (S3)           │               │
│  │  • Hybride SigV2/V4 (Dell ECS)        │               │
│  │  • Locks asyncio par fichier           │               │
│  └────────────────────┬──────────────────┘               │
│                       │                                   │
│  ┌────────────────────┴──────────────────┐               │
│  │         Auth Middleware (ASGI)          │               │
│  │  • Bearer Token • Permissions R/W/A    │               │
│  │  • Space access control                │               │
│  └────────────────────────────────────────┘               │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
    ┌──────────────────┐     ┌──────────────────┐
    │  S3 Object Store │     │  LLMaaS API      │
    │  (Dell ECS / CT) │     │  (Cloud Temple)  │
    │  Bucket: live-mem│     │  qwen3-2507:235b │
    └──────────────────┘     └──────────────────┘
```

### 3.2 Composants

| Composant                | Rôle                                      | Technologie                              |
| ------------------------ | ----------------------------------------- | ---------------------------------------- |
| **WAF**                  | Reverse proxy sécurisé                    | Caddy + Coraza OWASP CRS + Rate Limiting |
| **MCP Server**           | Serveur MCP Python (24 outils)            | FastMCP + Uvicorn (ASGI)                 |
| **Storage Service**      | Abstraction S3 (lecture/écriture/listing) | boto3 hybride SigV2/V4                   |
| **Consolidator Service** | Synthèse LLM des notes → bank             | AsyncOpenAI (qwen3-2507:235b)            |
| **Auth Middleware**      | Authentification Bearer Token             | ASGI middleware custom                   |
| **Token Manager**        | Gestion des tokens (CRUD)                 | JSON sur S3 (`_system/tokens.json`)      |

### 3.3 Services externes

| Service    | Fournisseur                           | Usage                          | Obligatoire |
| ---------- | ------------------------------------- | ------------------------------ | ----------- |
| **S3**     | Cloud Temple (Dell ECS) ou compatible | Stockage de TOUTES les données | ✅          |
| **LLMaaS** | Cloud Temple (API OpenAI-compatible)  | Consolidation live → bank      | ✅          |

### 3.4 Stack technique

| Composant        | Technologie             | Rôle                               |
| ---------------- | ----------------------- | ---------------------------------- |
| Framework MCP    | `FastMCP` (Python SDK)  | Expose les outils via HTTP/SSE     |
| Serveur HTTP     | `Uvicorn` (ASGI)        | Sert l'application FastMCP         |
| Configuration    | `pydantic-settings`     | Variables d'environnement + `.env` |
| CLI scriptable   | `Click`                 | Commandes en ligne                 |
| Shell interactif | `prompt_toolkit`        | Autocomplétion, historique         |
| Affichage        | `Rich`                  | Tables, panels, couleurs, Markdown |
| Client HTTP/SSE  | `httpx` + `httpx-sse`   | CLI → serveur                      |
| Auth             | Bearer Token            | Authentification par token         |
| S3 client        | `boto3`                 | Stockage S3 (hybride SigV2/V4)     |
| LLM client       | `openai` (AsyncOpenAI)  | Appels LLMaaS                      |
| Conteneur        | Docker + Docker Compose | Déploiement                        |
| Reverse proxy    | Caddy + Coraza          | TLS, WAF, Rate Limiting            |

---

## 4. Flux de données

### 4.1 Écriture (Mode Live)

```
Agent → live_note("observation", "Le module auth fonctionne")
                │
                ▼
        MCP Server vérifie auth + accès espace
                │
                ▼
        Génère un nom unique :
        20260220T180512_cline-dev_observation_a3f8b2c1.md
                │
                ▼
        PUT S3 : {space_id}/live/{filename}
        (contenu = front-matter YAML + texte)
```

### 4.2 Lecture (Mode Bank)

```
Agent → bank_read_all("projet-alpha")
                │
                ▼
        MCP Server vérifie auth + accès espace
                │
                ▼
        LIST S3 : {space_id}/bank/*
                │
                ▼
        GET S3 : chaque fichier bank
                │
                ▼
        Retourne : {files: [{filename, content}, ...], total_size, file_count}
```

### 4.3 Consolidation (Mode Bank — via LLM)

```
Agent → bank_consolidate("projet-alpha")
                │
                ▼
        1. Lit _rules.md
        2. Lit les notes live non consolidées
        3. Lit la bank actuelle (tous les fichiers)
        4. Lit _synthesis.md (contexte précédent)
                │
                ▼
        Pour chaque fichier bank défini dans les rules :
        ┌─────────────────────────────────────────────┐
        │  Prompt LLM :                               │
        │  - Rules de l'espace                        │
        │  - Notes live pertinentes                   │
        │  - Contenu actuel du fichier bank           │
        │  - Synthèse précédente                      │
        │  →  LLM produit le fichier bank mis à jour  │
        └─────────────────────────────────────────────┘
                │
                ▼
        5. Écrit les fichiers bank mis à jour sur S3
        6. LLM produit une synthèse des notes
        7. Supprime les notes live
        8. Écrit _synthesis.md (résidu pour la prochaine consolidation)
```

---

## 5. Espaces Mémoire (Spaces)

Un **espace** est un namespace isolé. Chaque espace a :
- Un identifiant unique (`space_id` : alphanum + tirets, max 64 chars)
- Des **rules** immuables (définies à la création, ne changent plus)
- Un dossier `live/` pour les notes
- Un dossier `bank/` pour les fichiers consolidés
- Des métadonnées (`_meta.json`)

Les espaces sont isolés : un token ne peut accéder qu'aux espaces autorisés.

---

## 6. Comparaison des architectures

### Ce que live-mem reprend de graph-memory

| Pattern                               | graph-memory | live-mem     |
| ------------------------------------- | ------------ | ------------ |
| Pattern 3 couches (MCP + CLI + Shell) | ✅           | ✅           |
| S3 Dell ECS hybride SigV2/V4          | ✅           | ✅           |
| Auth Bearer Token + bootstrap key     | ✅           | ✅           |
| WAF Caddy + Coraza + Rate Limiting    | ✅           | ✅           |
| Docker Compose + réseau isolé         | ✅           | ✅           |
| Container non-root                    | ✅           | ✅           |
| LLMaaS Cloud Temple (API OpenAI)      | ✅           | ✅           |
| Backup/Restore sur S3                 | ✅           | ✅           |
| Token management (CRUD)               | ✅ (Neo4j)   | ✅ (S3 JSON) |
| Format retour standardisé             | ✅           | ✅           |
| Logs sur stderr                       | ✅           | ✅           |
| Lazy-loading des services             | ✅           | ✅           |

### Ce que live-mem ne reprend PAS

| Élément                        | Raison                         |
| ------------------------------ | ------------------------------ |
| Neo4j                          | Pas de graphe de connaissances |
| Qdrant                         | Pas de recherche vectorielle   |
| Chunking (SemanticChunker)     | Pas d'ingestion de documents   |
| Extraction d'entités/relations | Pas pertinent pour des notes   |
| RAG                            | Pas de recherche sémantique    |
| Interface web graphe           | Pas de graphe à visualiser     |

### Ce que live-mem ajoute de nouveau

| Élément                     | Description                                     |
| --------------------------- | ----------------------------------------------- |
| **Notes live multi-agents** | Écriture concurrente sans conflit (append-only) |
| **Consolidation LLM**       | Synthèse automatique notes → bank via LLM       |
| **Rules dynamiques**        | Structure bank définie par rules, pas hardcodée |
| **Bank read_all**           | Lecture complète de la bank en une requête      |
| **Synthèse résiduelle**     | `_synthesis.md` comme pont entre consolidations |
| **Tokens sur S3**           | Plus besoin de Neo4j pour stocker les tokens    |

---

## 7. Prérequis

### Matériel minimal

| Ressource | Minimum   | Recommandé |
| --------- | --------- | ---------- |
| CPU       | 1 vCPU    | 2 vCPU     |
| RAM       | 1 GB      | 2 GB       |
| Disque    | 10 GB SSD | 20 GB SSD  |

> **Note** : live-mem est bien plus léger que graph-memory (pas de Neo4j ni Qdrant). Le service MCP consomme ~100 MB au repos, ~500 MB pendant une consolidation LLM.

### Réseau

| Port     | Direction | Usage                              |
| -------- | --------- | ---------------------------------- |
| **80**   | Entrant   | HTTP → redirect HTTPS (prod)       |
| **443**  | Entrant   | HTTPS (TLS Let's Encrypt, prod)    |
| **8080** | Entrant   | HTTP (dev uniquement)              |
| —        | Sortant   | `api.ai.cloud-temple.com` (LLMaaS) |
| —        | Sortant   | `*.s3.fr1.cloud-temple.com` (S3)   |

---

## 8. Configuration (.env)

### Variables OBLIGATOIRES

```env
# ─── S3 ───
S3_ENDPOINT_URL=https://your-endpoint.s3.fr1.cloud-temple.com
S3_ACCESS_KEY_ID=AKIA_YOUR_KEY
S3_SECRET_ACCESS_KEY=your_secret
S3_BUCKET_NAME=live-mem
S3_REGION_NAME=fr1

# ─── LLMaaS ───
LLMAAS_API_URL=https://api.ai.cloud-temple.com/v1
LLMAAS_API_KEY=your_key
LLMAAS_MODEL=qwen3-2507:235b
LLMAAS_MAX_TOKENS=100000
LLMAAS_TEMPERATURE=0.3

# ─── Auth ───
ADMIN_BOOTSTRAP_KEY=change_me_to_a_strong_random_key_64chars
```

### Variables optionnelles

```env
# ─── Server ───
MCP_SERVER_PORT=8002
MCP_SERVER_DEBUG=false
WAF_PORT=8080
SITE_ADDRESS=:8080

# ─── Consolidation ───
CONSOLIDATION_TIMEOUT=600        # Timeout LLM en secondes
CONSOLIDATION_MAX_NOTES=500      # Max notes par consolidation

# ─── Backup ───
BACKUP_RETENTION_COUNT=5
```

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
