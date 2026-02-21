# 🧠 Live Memory — MCP Knowledge Live memory Service

> **Mémoire de travail partagée pour agents IA collaboratifs**

[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)]()
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)]()

---

## 📋 Table des matières

- [Concept](#-concept)
- [Architecture](#-architecture)
- [Prérequis](#-prérequis)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Démarrage](#-démarrage)
- [Outils MCP](#-outils-mcp)
- [Graph Bridge](#-graph-bridge--pont-vers-graph-memory)
- [Intégration MCP](#-intégration-mcp)
- [CLI et Shell](#-cli-et-shell)
- [Tests](#-tests)
- [Sécurité](#-sécurité)
- [Structure du projet](#-structure-du-projet)
- [Dépannage](#-dépannage)

---

## 🎯 Concept

**Live Memory** est un serveur MCP (Model Context Protocol) qui fournit une **Memory Bank as a Service** pour agents IA. Plusieurs agents collaborent sur un même projet en partageant une mémoire de travail commune.

```
graph-memory  = Mémoire LONG TERME (documents → Knowledge Graph → RAG vectoriel)
live-memory   = Mémoire de TRAVAIL (notes live → LLM → Memory Bank structurée)
```

### Deux modes complémentaires

| Mode         | Description                                                       | Analogie                   |
| ------------ | ----------------------------------------------------------------- | -------------------------- |
| **🔴 Live** | Notes temps réel (observations, décisions, todos...) append-only   | Tableau blanc partagé      |
| **📘 Bank** | Consolidation LLM en fichiers Markdown structurés selon des rules  | Cahier de projet structuré |

### Pourquoi Live Memory ?

| Problème                                    | Solution Live Memory                                            |
| ------------------------------------------- | --------------------------------------------------------------- |
| Agents perdent leur contexte entre sessions | `bank_read_all` → contexte complet en 1 appel                   |
| Collaboration multi-agents impossible       | Notes append-only, pas de conflit, visibilité croisée           |
| Consolidation manuelle fastidieuse          | LLM transforme les notes brutes en documentation structurée     |
| Mémoire dispersée en fichiers locaux        | Point central S3, accessible de partout                         |
| Pas de lien avec la mémoire long terme      | 🌉 Graph Bridge pousse la bank dans un graphe de connaissancesv |

### 🧠 Collaboration multi-agents et architecture mémoire à deux niveaux

La recherche récente sur les systèmes multi-agents à base de LLM ([Tran et al., 2025 — *Multi-Agent Collaboration Mechanisms: A Survey of LLMs*](https://arxiv.org/abs/2501.06322)) identifie la **mémoire partagée** comme un composant fondamental. Dans leur cadre formel, un système multi-agents est défini par des **agents** (A), un **environnement partagé** (E) et des **canaux de collaboration** (C). Les auteurs soulignent que les LLM sont intrinsèquement des algorithmes isolés, non conçus pour collaborer — ils ont besoin d'une **infrastructure de mémoire partagée** pour coordonner leurs actions.

Live Memory + Graph Memory implémente directement cette architecture :

```
┌─────────────────────────────────────────────────────────────┐
│                  Environnement partagé E                    │
│                                                             │
│  ┌──────────────────┐   LLM    ┌─────────────────────┐      │
│  │  🔴 Live         │ ──────► │  📘 Bank             │      │
│  │  Notes temps réel│ consolide│  Mémoire de travail │      │
│  │  (append-only)   │         │  structurée          │      │
│  └──────────────────┘         └──────────┬───────────┘      │
│                                          │                  │
│                                     graph_push              │
│                                     (MCP SSE)               │
│                                          │                  │
│                               ┌──────────▼───────────┐      │
│                               │  🌐 Graph Memory     │      │
│                               │  Knowledge Graph     │      │
│                               │  (entités, relations,│      │
│                               │   embeddings, RAG)   │      │
│                               └──────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

| Niveau | Service | Durée | Contenu | Usage |
|--------|---------|-------|---------|-------|
| **Mémoire de travail** | Live Memory | Session / projet | Notes brutes + bank consolidée Markdown | Contexte opérationnel, coordination quotidienne |
| **Mémoire long terme** | Graph Memory | Permanent | Entités + relations + embeddings vectoriels | Base de connaissances interrogeable en langage naturel |

**Le Graph Bridge** (`graph_push`) est le canal de collaboration entre ces deux niveaux. Conformément au pattern **late-stage collaboration** décrit dans la littérature (partage des outputs consolidés comme inputs d'un autre système), il transforme la documentation de travail (Markdown) en connaissances structurées (graphe d'entités/relations).

**Pourquoi deux niveaux ?** Un seul niveau ne suffit pas :
- La mémoire de travail seule est **éphémère** — elle disparaît quand le projet se termine
- Le graphe de connaissances seul est **trop lourd** pour des notes quotidiennes rapides
- Le pont entre les deux permet aux agents de **travailler vite** (notes live) tout en **capitalisant** les connaissances (graphe)

Concrètement, les agents peuvent :
1. **Écrire rapidement** des notes sans friction (live-memory, append-only, ~50ms)
2. **Consolider automatiquement** via LLM en documentation structurée (bank, ~15s)
3. **Pérenniser les connaissances** dans un graphe interrogeable (graph-memory, ~2min)
4. **Interroger le graphe** en langage naturel pour retrouver des informations de projets passés

---

## 🏗️ Architecture

```
     Agent Cline        Agent Claude        Agent X
          │                   │                │
          └────────┬──────────┘                │
                   │                           │
                   ▼  MCP Protocol (HTTP/SSE)  ▼
          ┌────────────────────────────────────────┐
          │   Caddy WAF (Coraza CRS)               │
          │   Rate Limiting • TLS • OWASP CRS      │
          └────────────┬───────────────────────────┘
                       │
          ┌────────────┴───────────────────┐
          │   Live Memory MCP (:8002)      │
          │   30 outils • Auth Bearer      │
          │   Consolidation LLM            │
          └──────┬──────────┬──────┬───────┘
                 │          │      │
          ┌──────┴──┐  ┌────┴───┐  │
          │   S3    │  │ LLMaaS │  │  MCP SSE
          │Dell ECS │  │ CT API │  │  (optionnel)
          └─────────┘  └────────┘  │
                       ┌───────────┴────────────┐
                       │   Graph Memory         │
                       │   (mémoire long terme) │
                       │   Neo4j + Qdrant       │
                       └────────────────────────┘
```

**Stack minimale** : S3 + LLM. Pas de base de données locale.
**Optionnel** : connexion à Graph Memory pour la mémoire long terme (graphe de connaissances).

---

## 📦 Prérequis

- **Docker** >= 24.0 + **Docker Compose** v2
- **Python 3.11+** (pour la CLI, optionnel)
- Un **stockage S3** compatible (Cloud Temple Dell ECS, AWS, MinIO)
- Un **LLM** compatible OpenAI API (Cloud Temple LLMaaS, OpenAI, etc.)

---

## 🚀 Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/chrlesur/live-memory.git
cd live-memory
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
```

Éditez `.env` avec vos valeurs (voir section [Configuration](#-configuration)).

### 3a. Démarrage Docker (recommandé)

```bash
# Construire les images (WAF + serveur MCP)
docker compose build

# Démarrer les services
docker compose up -d

# Vérifier que tout tourne
docker compose ps

# Vérifier la santé
curl -s http://localhost:8080/sse | head -1
```

### 3b. Démarrage local (développement)

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le serveur
cd src && python -m live_mem
```

### 4. Installer la CLI (optionnel)

```bash
pip install click rich prompt-toolkit httpx httpx-sse
```

### 5. Vérifier l'installation

```bash
# Health check via la CLI
python scripts/mcp_cli.py health

# Ou test E2E complet (crée un espace, écrit des notes, consolide)
python scripts/test_recette.py
```

### Ports exposés

| Service    | Port   | Description                                |
| ---------- | ------ | ------------------------------------------ |
| **WAF**    | `8080` | Seul port exposé — Caddy WAF → Live Memory |
| MCP Server | `8002` | Réseau Docker interne uniquement           |

---

## ⚙️ Configuration

Éditez `.env`. Toutes les variables sont documentées dans `.env.example`.

### Variables obligatoires

| Variable               | Description              | Exemple                                      |
| ---------------------- | ------------------------ | -------------------------------------------- |
| `S3_ENDPOINT_URL`      | URL endpoint S3          | `https://takinc5acc.s3.fr1.cloud-temple.com` |
| `S3_ACCESS_KEY_ID`     | Access key S3            | `AKIA...`                                    |
| `S3_SECRET_ACCESS_KEY` | Secret key S3            | `wJal...`                                    |
| `S3_BUCKET_NAME`       | Nom du bucket            | `live-mem`                                   |
| `S3_REGION_NAME`       | Région S3                | `fr1`                                        |
| `LLMAAS_API_URL`       | URL API LLM (avec `/v1`) | `https://api.ai.cloud-temple.com/v1`         |
| `LLMAAS_API_KEY`       | Clé API LLM              | `sk-...`                                     |
| `ADMIN_BOOTSTRAP_KEY`  | Clé admin bootstrap      | `ma-cle-secrete-changez-moi`                 |

### Variables optionnelles

| Variable                  | Défaut            | Description                      |
| ------------------------- | ----------------- | -------------------------------- |
| `MCP_SERVER_PORT`         | `8002`            | Port d'écoute du serveur MCP     |
| `MCP_SERVER_DEBUG`        | `false`           | Logs détaillés                   |
| `LLMAAS_MODEL`            | `qwen3-2507:235b` | Modèle LLM pour la consolidation |
| `LLMAAS_MAX_TOKENS`       | `100000`          | Max tokens par appel LLM         |
| `LLMAAS_TEMPERATURE`      | `0.3`             | Température LLM                  |
| `CONSOLIDATION_TIMEOUT`   | `600`             | Timeout consolidation (secondes) |
| `CONSOLIDATION_MAX_NOTES` | `500`             | Max notes par consolidation      |

---

## ▶️ Démarrage

```bash
docker compose up -d
docker compose ps       # Vérifier le statut
docker compose logs -f live-mem-service --tail 50  # Logs
```

---

## 🔧 Outils MCP

30 outils exposés via le protocole MCP (HTTP/SSE), répartis en 7 catégories.

### System (2 outils)

| Outil           | Paramètres | Description                                      |
| --------------- | ---------- | ------------------------------------------------ |
| `system_health` | —          | État de santé (S3, LLMaaS, nombre d'espaces)     |
| `system_about`  | —          | Identité du service (version, outils, capacités) |

### Space (7 outils)

| Outil           | Paramètres                                   | Description                                                |
| --------------- | -------------------------------------------- | ---------------------------------------------------------- |
| `space_create`  | `space_id`, `description`, `rules`, `owner?` | Crée un espace avec ses rules (structure de la bank)       |
| `space_list`    | —                                            | Liste les espaces accessibles par le token courant         |
| `space_info`    | `space_id`                                   | Infos détaillées (notes, bank, consolidation)              |
| `space_rules`   | `space_id`                                   | Lit les rules immuables de l'espace                        |
| `space_summary` | `space_id`                                   | Synthèse complète : rules + bank + stats (démarrage agent) |
| `space_export`  | `space_id`                                   | Export tar.gz en base64                                    |
| `space_delete`  | `space_id`, `confirm`                        | Supprime l'espace (⚠️ irréversible, admin requis)        |

### Live (3 outils)

| Outil         | Paramètres                                           | Description                                                                                            |
| ------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `live_note`   | `space_id`, `category`, `content`, `agent?`, `tags?` | Écrit une note horodatée. Catégories : observation, decision, todo, insight, question, progress, issue |
| `live_read`   | `space_id`, `limit?`, `category?`, `agent?`          | Lit les notes live (filtres optionnels)                                                                |
| `live_search` | `space_id`, `query`, `limit?`                        | Recherche plein texte dans les notes                                                                   |

### Bank (4 outils)

| Outil              | Paramètres             | Description                                                                                                |
| ------------------ | ---------------------- | ---------------------------------------------------------------------------------------------------------- |
| `bank_read`        | `space_id`, `filename` | Lit un fichier bank spécifique (ex: `activeContext.md`)                                                    |
| `bank_read_all`    | `space_id`             | Lit toute la bank en une requête (🚀 démarrage agent)                                                     |
| `bank_list`        | `space_id`             | Liste les fichiers bank (sans contenu)                                                                     |
| `bank_consolidate` | `space_id`, `agent?`   | 🧠 Consolide les notes via LLM. `agent` vide = toutes les notes (admin). `agent=nom` = notes de cet agent |

### Graph (4 outils) — 🌉 Pont vers Graph Memory

| Outil              | Paramètres                                           | Description                                                                                                  |
| ------------------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `graph_connect`    | `space_id`, `url`, `token`, `memory_id`, `ontology?` | Connecte un space à Graph Memory. Teste la connexion, crée la mémoire si besoin. Ontologie défaut: `general` |
| `graph_push`       | `space_id`                                           | Synchronise la bank → graphe. Delete + re-ingest intelligent, nettoyage orphelins. ~30s/fichier              |
| `graph_status`     | `space_id`                                           | Statut connexion + stats graphe (documents, entités, relations, top entités, liste documents)                |
| `graph_disconnect` | `space_id`                                           | Déconnecte (les données restent dans le graphe)                                                              |

### Backup (5 outils)

| Outil             | Paramètres                 | Description                                       |
| ----------------- | -------------------------- | ------------------------------------------------- |
| `backup_create`   | `space_id`, `description?` | Crée un snapshot complet sur S3                   |
| `backup_list`     | `space_id?`                | Liste les backups disponibles                     |
| `backup_restore`  | `backup_id`                | Restaure un backup (l'espace ne doit pas exister) |
| `backup_download` | `backup_id`                | Télécharge en tar.gz base64                       |
| `backup_delete`   | `backup_id`                | Supprime un backup                                |

### Admin (5 outils)

| Outil                | Paramètres                                               | Description                                                                  |
| -------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `admin_create_token` | `name`, `permissions`, `space_ids?`, `expires_in_days?`  | Crée un token (⚠️ affiché une seule fois). Permissions: read, write, admin |
| `admin_list_tokens`  | —                                                        | Liste les tokens actifs                                                      |
| `admin_revoke_token` | `token_hash`                                             | Révoque un token                                                             |
| `admin_update_token` | `token_hash`, `space_ids`, `action`                      | Modifie les espaces d'un token (add/remove/set)                              |
| `admin_gc_notes`     | `space_id?`, `max_age_days?`, `confirm?`, `delete_only?` | Garbage Collector : nettoie les notes orphelines                             |

---

## 🌉 Graph Bridge — Pont vers Graph Memory

Live Memory peut pousser sa Memory Bank dans une instance [Graph Memory](https://github.com/chrlesur/graph-memory) pour la mémoire long terme. Le graphe de connaissances extrait les entités, relations et embeddings des fichiers bank.

### Flux

```
1. graph_connect(space_id, url, token, memory_id, ontology="general")
   └─ Teste la connexion, crée la mémoire Graph Memory si besoin

2. bank_consolidate(space_id)
   └─ Le LLM produit/met à jour les fichiers bank

3. graph_push(space_id)
   ├─ Liste les documents dans Graph Memory
   ├─ Pour chaque fichier bank modifié :
   │   ├─ document_delete (supprime entités orphelines)
   │   └─ memory_ingest (recalcul complet du graphe)
   ├─ Nettoie les documents supprimés de la bank
   └─ Met à jour les métriques (last_push, push_count)

4. graph_status(space_id)
   └─ Stats : 79 entités, 61 relations, top entités, documents...
```

### Push intelligent (delete + re-ingest)

Chaque push est un **refresh complet** du graphe. Les fichiers existants sont supprimés puis ré-ingérés pour que Graph Memory recalcule les entités, relations et embeddings avec le contenu à jour.

### Ontologies disponibles

| Ontologie          | Usage                                        |
| ------------------ | -------------------------------------------- |
| `general` (défaut) | Polyvalent : FAQ, specs, certifications, RSE |
| `legal`            | Documents juridiques, contrats               |
| `cloud`            | Infrastructure cloud, fiches produits        |
| `managed-services` | Services managés, infogérance                |
| `presales`         | Avant-vente, RFP/RFI, propositions           |

### Exemple complet

```python
# 1. Connecter le space à Graph Memory
graph_connect(
    space_id="mon-projet",
    url="https://graph-mem.mcp.cloud-temple.app/sse",
    token="votre_token_graph_memory",
    memory_id="MON-PROJET",
    ontology="general"
)

# 2. Consolider les notes en bank
bank_consolidate(space_id="mon-projet")

# 3. Pousser la bank dans le graphe
graph_push(space_id="mon-projet")
# → 3 fichiers poussés, 79 entités extraites, 61 relations

# 4. Vérifier les stats
graph_status(space_id="mon-projet")
# → Documents: 3, Entités: 79, Relations: 61
# → Top: [Product] HAProxy, [Product] API Gateway (Kong), ...
```

---

## 🔌 Intégration MCP

### Avec Cline (VS Code)

Dans les settings MCP de Cline :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/sse",
      "headers": {
        "Authorization": "Bearer VOTRE_TOKEN"
      }
    }
  }
}
```

### Avec Claude Desktop

Dans `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/sse",
      "headers": {
        "Authorization": "Bearer VOTRE_TOKEN"
      }
    }
  }
}
```

### Via Python (client MCP)

```python
from mcp.client.sse import sse_client
from mcp import ClientSession

async def exemple():
    headers = {"Authorization": "Bearer votre_token"}
    async with sse_client("http://localhost:8080/sse", headers=headers) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # Charger tout le contexte
            result = await session.call_tool("bank_read_all", {
                "space_id": "mon-projet"
            })

            # Écrire une note
            await session.call_tool("live_note", {
                "space_id": "mon-projet",
                "category": "observation",
                "content": "Le build passe en CI"
            })
```

---

## 💻 CLI et Shell

### Installation CLI

```bash
pip install click rich prompt-toolkit httpx httpx-sse
export MCP_URL=http://localhost:8080
export MCP_TOKEN=votre_token
```

### Commandes CLI (Click)

```bash
python scripts/mcp_cli.py health
python scripts/mcp_cli.py about
python scripts/mcp_cli.py space list
python scripts/mcp_cli.py space create mon-projet --rules-file rules.md
python scripts/mcp_cli.py live note mon-projet observation "Build OK"
python scripts/mcp_cli.py bank consolidate mon-projet
python scripts/mcp_cli.py bank read-all mon-projet
python scripts/mcp_cli.py token create agent-cline read,write
```

### Shell interactif

```bash
python scripts/mcp_cli.py shell
```

Autocomplétion, historique, affichage Rich. Voir [scripts/README.md](scripts/README.md) pour la référence complète.

---

## 🧪 Tests

4 scripts de test E2E, tous avec `--step` (pas-à-pas) et `--no-cleanup`.

```bash
docker compose up -d   # Prérequis

# 1. Recette : 1 agent, 12 notes, consolidation → 6 fichiers bank
python scripts/test_recette.py

# 2. Multi-agents : 3 agents collaborent
python scripts/test_multi_agents.py

# 3. Garbage Collector
python scripts/test_gc.py

# 4. Graph Bridge : pont vers Graph Memory
python scripts/test_graph_bridge.py \
  --graph-url https://graph-mem.mcp.cloud-temple.app \
  --graph-token votre_token

# Mode pas-à-pas (Entrée pour avancer)
python scripts/test_recette.py --step --no-cleanup
```

Voir [scripts/README.md](scripts/README.md) pour le détail de chaque test.

---

## 🔒 Sécurité

### Authentification

- **Bearer Token** obligatoire sur toutes les requêtes MCP
- **Bootstrap key** pour créer le premier token admin
- **Tokens SHA-256** stockés sur S3 (jamais en clair)
- **3 niveaux** : read, write, admin
- **Scope par espace** : un token peut être limité à certains espaces

### WAF (Caddy + Coraza)

- **OWASP CRS** : injection SQL/XSS, path traversal, SSRF
- **Rate Limiting** : 60 SSE/min, 300 messages/min
- **TLS automatique** : Let's Encrypt en production (`SITE_ADDRESS=domaine.com`)
- **Container non-root** : utilisateur `mcp`

### Bonnes pratiques

1. **Changez `ADMIN_BOOTSTRAP_KEY`** en production
2. Ne commitez jamais `.env`
3. Créez des tokens avec les permissions minimales
4. Activez HTTPS via `SITE_ADDRESS`

---

## 📂 Structure du projet

```
live-memory/
├── src/live_mem/              # Code source (30 outils MCP)
│   ├── server.py              # Serveur FastMCP + middlewares
│   ├── config.py              # Configuration pydantic-settings
│   ├── auth/                  # Authentification
│   │   ├── middleware.py      #   Middleware ASGI (Bearer + contextvars)
│   │   └── context.py         #   check_access, check_write, check_admin
│   ├── core/                  # Services métier
│   │   ├── storage.py         #   S3 dual SigV2/SigV4 (Dell ECS)
│   │   ├── space.py           #   CRUD espaces mémoire
│   │   ├── live.py            #   Notes live (append-only)
│   │   ├── consolidator.py    #   Pipeline LLM (4 étapes)
│   │   ├── graph_bridge.py    #   🌉 Pont vers Graph Memory
│   │   ├── tokens.py          #   Gestion tokens SHA-256
│   │   ├── backup.py          #   Snapshots S3
│   │   ├── gc.py              #   Garbage Collector
│   │   ├── locks.py           #   Locks asyncio par espace
│   │   └── models.py          #   Modèles Pydantic
│   └── tools/                 # Outils MCP (7 modules)
│       ├── system.py          #   2 outils (health, about)
│       ├── space.py           #   7 outils (CRUD espaces)
│       ├── live.py            #   3 outils (notes)
│       ├── bank.py            #   4 outils (bank + consolidation)
│       ├── graph.py           #   4 outils (Graph Bridge)
│       ├── backup.py          #   5 outils (snapshots)
│       └── admin.py           #   5 outils (tokens + GC)
├── scripts/                   # CLI + Shell + Tests
│   ├── mcp_cli.py             #   Point d'entrée CLI Click
│   ├── test_recette.py        #   Test E2E (1 agent)
│   ├── test_multi_agents.py   #   Test multi-agents (3 agents)
│   ├── test_gc.py             #   Test Garbage Collector
│   ├── test_graph_bridge.py   #   Test Graph Bridge
│   └── cli/                   #   Package CLI
├── waf/                       # WAF Caddy + Coraza
│   ├── Caddyfile              #   Config WAF + rate limiting
│   └── Dockerfile             #   Image Caddy + Coraza
├── DESIGN/live-mem/           # 9 documents d'architecture
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── VERSION                    # 0.3.0
├── CHANGELOG.md
└── FAQ.md                     # 20 questions/réponses
```

---

## 🔍 Dépannage

### Le service ne démarre pas

```bash
docker compose logs live-mem-service --tail 50
docker compose logs waf --tail 20
```

### Erreur 401 Unauthorized

- Vérifiez votre token : `Authorization: Bearer VOTRE_TOKEN`
- La bootstrap key n'est pas un token — créez d'abord un token via `admin_create_token`

### Consolidation échoue

- Vérifiez les credentials LLMaaS dans `.env`
- Le timeout par défaut est 600s — augmentez `CONSOLIDATION_TIMEOUT` si nécessaire
- Un seul `bank_consolidate` à la fois par espace (lock asyncio)

### Graph Bridge : connexion impossible

- Vérifiez que Graph Memory est accessible : `curl https://votre-graph-memory/sse`
- Vérifiez le token Graph Memory (Bearer)
- L'URL peut être avec ou sans `/sse` (normalisée automatiquement)

### Rebuild après modification du code

```bash
docker compose build live-mem-service && docker compose up -d live-mem-service
```

---

## 🔗 Projets liés

| Projet           | Description                                | Lien                                                                         |
| ---------------- | ------------------------------------------ | ---------------------------------------------------------------------------- |
| **graph-memory** | Mémoire long terme (Knowledge Graph + RAG) | [github.com/chrlesur/graph-memory](https://github.com/chrlesur/graph-memory) |

---

## 📄 Licence

Apache License 2.0

---

## 👤 Auteur

**Cloud Temple** — [cloud-temple.com](https://www.cloud-temple.com)

Développé par **Christophe Lesur**, Directeur Général.

---

*Live Memory v0.3.0 — Mémoire de travail partagée pour agents IA collaboratifs*
