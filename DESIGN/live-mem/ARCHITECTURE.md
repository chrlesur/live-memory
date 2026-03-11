# Architecture — Live Memory MCP Server

> **Version** : 0.6.0 | **Date** : 2026-03-11 | **Auteur** : Cloud Temple  
> **Projet** : live-mem | **Licence** : Apache 2.0

---

## 1. Vision

**Live Memory** est un serveur MCP (Model Context Protocol) qui fournit une **mémoire de travail partagée** (Memory Bank) pour des agents IA collaboratifs. Contrairement à graph-memory (mémoire long terme par Knowledge Graph), live-mem est une **mémoire live** : les agents y écrivent en temps réel, et un LLM intégré consolide automatiquement ces notes en une memory bank structurée.

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

6. **Pont vers la mémoire long terme** : Le Graph Bridge (`graph_push`) pousse la bank consolidée dans Graph Memory pour capitaliser les connaissances dans un graphe interrogeable.

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
| **Pont**            | —                              | **Graph Bridge** pousse la bank → graph-memory  |
| **Interface web**   | `/Graph` (visualisation graphe)| **`/live`** (Dashboard + Timeline + Bank)       |
| **Analogie**        | Une bibliothèque               | Un **tableau blanc partagé** + cahier structuré |

---

## 3. Architecture

### 3.1 Vue d'ensemble

```
          Agent Cline         Agent Claude        Agent X
              │                    │                 │
              └────────┬───────────┘                 │
                       │                             │
                       ▼ MCP Protocol (Streamable HTTP)     ▼
┌──────────────────────────────────────────────────────────┐
│                    Coraza WAF (Caddy)                     │
│  • OWASP CRS • Rate Limiting • TLS Let's Encrypt        │
│  • Routes MCP sans WAF (streaming)              │
└──────────────────────────┬───────────────────────────────┘
                           │ Réseau Docker interne
                           ▼
┌──────────────────────────────────────────────────────────┐
│              Live Memory MCP Server (:8002)               │
│                                                           │
│  ┌─────────────────┐  ┌──────────────────┐               │
│  │  30 Outils MCP  │  │  LLM Service     │               │
│  │  (7 catégories) │  │  (consolidator)  │               │
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
│                                                           │
│  ┌────────────────────────────────────────┐               │
│  │         Interface Web (/live)           │               │
│  │  • StaticFilesMiddleware (ASGI)         │               │
│  │  • Dashboard + Timeline + Bank Viewer   │               │
│  │  • 5 endpoints API REST (/api/*)        │               │
│  └────────────────────────────────────────┘               │
│                                                           │
│  ┌────────────────────────────────────────┐               │
│  │         Graph Bridge (optionnel)        │               │
│  │  • Client MCP Streamable HTTP vers Graph Memory     │               │
│  │  • Sync bank → graphe de connaissances  │               │
│  └────────────────────────────────────────┘               │
└──────────────────────────┬───────────────────────────────┘
                           │
              ┌────────────┼────────────────────┐
              ▼            ▼                    ▼
    ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
    │  S3 Object   │ │  LLMaaS API  │ │  Graph Memory      │
    │  Store       │ │  (Cloud      │ │  (optionnel)       │
    │  (Dell ECS)  │ │   Temple)    │ │  Neo4j + Qdrant    │
    │  Bucket:     │ │  qwen3-2507  │ │  via MCP Streamable HTTP       │
    │  live-mem    │ │  :235b       │ │                    │
    └──────────────┘ └──────────────┘ └────────────────────┘
```

### 3.2 Composants

| Composant                | Rôle                                        | Technologie                              |
| ------------------------ | ------------------------------------------- | ---------------------------------------- |
| **WAF**                  | Reverse proxy sécurisé                      | Caddy + Coraza OWASP CRS + Rate Limiting |
| **MCP Server**           | Serveur MCP Python (30 outils, 7 catégories)| FastMCP + Uvicorn (ASGI)                 |
| **Storage Service**      | Abstraction S3 (lecture/écriture/listing)   | boto3 hybride SigV2/V4                   |
| **Consolidator Service** | Synthèse LLM des notes → bank               | AsyncOpenAI (qwen3-2507:235b)            |
| **Graph Bridge**         | Pont vers Graph Memory (mémoire long terme) | SDK MCP (streamablehttp_client)               |
| **Auth Middleware**       | Authentification Bearer Token               | ASGI middleware custom                   |
| **Token Manager**        | Gestion des tokens (CRUD)                   | JSON sur S3 (`_system/tokens.json`)      |
| **Static Files**         | Interface web /live + API REST              | ASGI middleware (StaticFilesMiddleware)   |
| **GC Service**           | Nettoyage notes orphelines                  | Scan + consolidation/suppression          |

### 3.3 Services externes

| Service          | Fournisseur                           | Usage                          | Obligatoire |
| ---------------- | ------------------------------------- | ------------------------------ | ----------- |
| **S3**           | Cloud Temple (Dell ECS) ou compatible | Stockage de TOUTES les données | ✅          |
| **LLMaaS**       | Cloud Temple (API OpenAI-compatible)  | Consolidation live → bank      | ✅          |
| **Graph Memory** | Instance graph-memory (MCP Streamable HTTP)       | Mémoire long terme (graphe)    | ❌ Optionnel |

### 3.4 Stack technique

| Composant        | Technologie             | Rôle                               |
| ---------------- | ----------------------- | ---------------------------------- |
| Framework MCP    | `FastMCP` (Python SDK)  | Expose les outils via Streamable HTTP     |
| Serveur HTTP     | `Uvicorn` (ASGI)        | Sert l'application FastMCP         |
| Configuration    | `pydantic-settings`     | Variables d'environnement + `.env` |
| CLI scriptable   | `Click`                 | Commandes en ligne                 |
| Shell interactif | `prompt_toolkit`        | Autocomplétion, historique         |
| Affichage        | `Rich`                  | Tables, panels, couleurs, Markdown |
| Client MCP     | SDK MCP ≥1.8.0          | CLI + Graph Bridge → serveur                      |
| Auth             | Bearer Token            | Authentification par token         |
| S3 client        | `boto3`                 | Stockage S3 (hybride SigV2/V4)     |
| LLM client       | `openai` (AsyncOpenAI)  | Appels LLMaaS                      |
| Conteneur        | Docker + Docker Compose | Déploiement                        |
| Reverse proxy    | Caddy + Coraza          | TLS, WAF, Rate Limiting            |
| Interface web    | HTML/CSS/JS vanilla     | Dashboard, Timeline, Bank Viewer   |
| Rendu Markdown   | `marked.js` (CDN)       | Rendu bank files dans le navigateur|

### 3.5 Pile de middlewares ASGI

```
Requête HTTP entrante
    │
    ▼
AuthMiddleware          ← Extrait Bearer token, injecte dans contextvars
    │
    ▼
LoggingMiddleware       ← Trace méthode, path, status, durée (stderr)
    │
    ▼
StaticFilesMiddleware   ← Intercepte /live, /static/*, /api/*
    │
    ▼
mcp.streamable_http_app()           ← Handler MCP Streamable HTTP (outils via /mcp)
```

> **Note v0.5.0** : `HostNormalizerMiddleware` a été supprimé — la normalisation du header Host est désormais gérée nativement par le WAF Caddy.

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
Agent → bank_consolidate("projet-alpha", agent="cline-dev")
                │
                ▼
        1. Lit _rules.md
        2. Lit les notes live de l'agent (ou toutes si agent="")
        3. Lit la bank actuelle (tous les fichiers)
        4. Lit _synthesis.md (contexte précédent)
                │
                ▼
        Pour tous les fichiers bank en une seule requête LLM :
        ┌─────────────────────────────────────────────┐
        │  Prompt LLM :                               │
        │  - Rules de l'espace                        │
        │  - Notes live pertinentes                   │
        │  - Contenu actuel de tous les fichiers bank │
        │  - Synthèse précédente                      │
        │  →  LLM retourne un JSON avec des            │
        │     OPÉRATIONS D'ÉDITION par section          │
        │     (replace_section, append_to_section,      │
        │     add_section, delete_section) + synthesis   │
        └─────────────────────────────────────────────┘
                │
                ▼
        5. Applique les opérations chirurgicalement
           sur les fichiers bank existants (v0.6.0)
           → Ce qui n'est pas touché reste intact byte-for-byte
           → Zéro perte de matière (vs réécriture complète)
        6. Écrit _synthesis.md (résidu pour la prochaine consolidation)
        7. Supprime les notes live traitées (EN DERNIER)
        8. Met à jour _meta.json (compteurs)
```

### 4.4 Graph Push (Pont vers Graph Memory)

```
Agent → graph_push("projet-alpha")
                │
                ▼
        1. Lit la config graph_memory depuis _meta.json
        2. Liste les fichiers bank
                │
                ▼
        Pour chaque fichier bank :
        ┌─────────────────────────────────────────────┐
        │  Via MCP Streamable HTTP vers Graph Memory :            │
        │  1. Supprime l'ancien document (si existant)│
        │  2. Ingère le nouveau contenu               │
        │     (extraction LLM entités/relations)      │
        │  ~10-30s par fichier                        │
        └─────────────────────────────────────────────┘
                │
                ▼
        3. Nettoie les orphelins (fichiers supprimés de la bank)
        4. Met à jour les métriques dans _meta.json
```

---

## 5. Espaces Mémoire (Spaces)

Un **espace** est un namespace isolé. Chaque espace a :
- Un identifiant unique (`space_id` : alphanum + tirets, max 64 chars)
- Des **rules** immuables (définies à la création, ne changent plus)
- Un dossier `live/` pour les notes
- Un dossier `bank/` pour les fichiers consolidés
- Des métadonnées (`_meta.json`), incluant optionnellement la config Graph Memory
- Une synthèse résiduelle (`_synthesis.md`)

Les espaces sont isolés : un token ne peut accéder qu'aux espaces autorisés.

---

## 6. Interface Web

Live Memory expose une **interface web SPA** sur `/live` :

```
┌──────────────┬────────────────────────────┐
│  📊 Dashboard│  🔴 Live Timeline          │
│  (infos,     │  (auto-refresh, groupé/date)│
│   agents,    ├────────────────────────────┤
│   rules...)  │  📘 Bank (onglets Markdown) │
└──────────────┴────────────────────────────┘
```

- **Dashboard** : stats espace, consolidation, agents, catégories, rules, Graph Memory
- **Live Timeline** : notes groupées par date, rendu Markdown
- **Bank Viewer** : onglets, rendu Markdown via `marked.js`
- **Auto-refresh** : 3s/5s/10s/30s/manuel, anti-flicker par hash comparaison
- **5 endpoints API REST** (`/api/*`) pour alimenter l'interface

---

## 7. Comparaison des architectures

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
| Interface web de visualisation        | ✅ (/Graph)  | ✅ (/live)   |

### Ce que live-mem ne reprend PAS

| Élément                        | Raison                         |
| ------------------------------ | ------------------------------ |
| Neo4j                          | Pas de graphe de connaissances |
| Qdrant                         | Pas de recherche vectorielle   |
| Chunking (SemanticChunker)     | Pas d'ingestion de documents   |
| Extraction d'entités/relations | Pas pertinent pour des notes   |
| RAG                            | Pas de recherche sémantique    |

### Ce que live-mem ajoute de nouveau

| Élément                      | Description                                          |
| ---------------------------- | ---------------------------------------------------- |
| **Notes live multi-agents**  | Écriture concurrente sans conflit (append-only)      |
| **Consolidation LLM**        | Synthèse automatique notes → bank via LLM            |
| **Consolidation par agent**  | `bank_consolidate(agent="...")` filtre les notes      |
| **Rules dynamiques**         | Structure bank définie par rules, pas hardcodée      |
| **Bank read_all**            | Lecture complète de la bank en une requête            |
| **Synthèse résiduelle**      | `_synthesis.md` comme pont entre consolidations      |
| **Tokens sur S3**            | Plus besoin de Neo4j pour stocker les tokens         |
| **Graph Bridge**             | Pont MCP Streamable HTTP vers graph-memory (mémoire long terme)  |
| **Garbage Collector**        | Nettoyage/consolidation des notes orphelines         |
| **Interface web /live**      | Dashboard + Timeline + Bank Viewer avec auto-refresh |

---

## 8. Prérequis

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
| —        | Sortant   | Graph Memory (MCP Streamable HTTP, optionnel)  |

---

## 9. Configuration (.env)

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
```

---

*Document mis à jour le 11 mars 2026 — Live Memory v0.6.0*
