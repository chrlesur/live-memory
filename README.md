# 🧠 Live Memory — MCP Knowledge Live memory Service

> **Mémoire de travail partagée pour agents IA collaboratifs**

[![Version](https://img.shields.io/badge/version-0.6.0-blue.svg)]()
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
- [README English](#-readme-english)
- [Interface Web](#-interface-web)
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
| **🔴 Live** | Notes temps réel (observations, décisions, todos...) append-only  | Tableau blanc partagé      |
| **📘 Bank** | Consolidation LLM en fichiers Markdown structurés selon des rules | Cahier de projet structuré |

### Pourquoi Live Memory ?

| Problème                                    | Solution Live Memory                                            |
| ------------------------------------------- | --------------------------------------------------------------- |
| Agents perdent leur contexte entre sessions | `bank_read_all` → contexte complet en 1 appel                   |
| Collaboration multi-agents impossible       | Notes append-only, pas de conflit, visibilité croisée           |
| Consolidation manuelle fastidieuse          | LLM transforme les notes brutes en documentation structurée     |
| Mémoire dispersée en fichiers locaux        | Point central S3, accessible de partout                         |
| Pas de lien avec la mémoire long terme      | 🌉 Graph Bridge pousse la bank dans un graphe de connaissances |

### 🧠 Collaboration multi-agents et architecture mémoire à deux niveaux

La recherche récente sur les systèmes multi-agents à base de LLM ([Tran et al., 2025 — *Multi-Agent Collaboration Mechanisms: A Survey of LLMs*](https://arxiv.org/abs/2501.06322)) identifie la **mémoire partagée** comme un composant fondamental. Dans leur cadre formel, un système multi-agents est défini par des **agents** (A), un **environnement partagé** (E) et des **canaux de collaboration** (C). Les auteurs soulignent que les LLM sont intrinsèquement des algorithmes isolés, non conçus pour collaborer — ils ont besoin d'une **infrastructure de mémoire partagée** pour coordonner leurs actions.

Live Memory + Graph Memory implémente directement cette architecture :

```
┌─────────────────────────────────────────────────────────────┐
│                  Environnement partagé E                    │
│                                                             │
│  ┌──────────────────┐   LLM    ┌─────────────────────┐      │
│  │   Live           │ ──────►  │   Bank              │      │
│  │  Notes temps réel│ consolide│  Mémoire de travail │      │
│  │  (append-only)   │          │  structurée         │      │
│  └──────────────────┘          └──────────┬──────────┘      │
│                                          │                  │
│                                     graph_push              │
│                                     (MCP Streamable HTTP)   │
│                                          │                  │
│                               ┌──────────▼───────────┐      │
│                               │     Graph Memory     │      │
│                               │  Knowledge Graph     │      │
│                               │  (entités, relations,│      │
│                               │   embeddings, RAG)   │      │
│                               └──────────────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

| Niveau                 | Service      | Durée            | Contenu                                     | Usage                                                  |
| ---------------------- | ------------ | ---------------- | ------------------------------------------- | ------------------------------------------------------ |
| **Mémoire de travail** | Live Memory  | Session / projet | Notes brutes + bank consolidée Markdown     | Contexte opérationnel, coordination quotidienne        |
| **Mémoire long terme** | Graph Memory | Permanent        | Entités + relations + embeddings vectoriels | Base de connaissances interrogeable en langage naturel |

**Le Graph Bridge** (`graph_push`) est le canal de collaboration entre ces deux niveaux. Conformément au pattern **late-stage collaboration** décrit dans la littérature (partage des outputs consolidés comme inputs d'un autre système), il transforme la documentation de travail (Markdown) en connaissances structurées (graphe d'entités/relations).

**Pourquoi deux niveaux ?** Un seul niveau ne suffit pas :
- La mémoire de travail seule est **éphémère** — elle disparaît quand le projet se termine
- Le graphe de connaissances seul est **too lourd** pour des notes quotidiennes rapides
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
                   ▼  MCP Protocol (Streamable HTTP)  ▼
          ┌────────────────────────────────────────┐
          │   Caddy WAF (Coraza CRS)               │
          │   Rate Limiting • TLS • OWASP CRS      │
          └────────────┬───────────────────────────┘
                       │
          ┌────────────┴───────────────────┐
          │   Live Memory MCP (:8002)      │
          │   32 outils • Auth Bearer      │
          │   Consolidation LLM            │
          └──────┬──────────┬──────┬───────┘
                 │          │      │
          ┌──────┴──┐  ┌────┴───┐  │
          │   S3    │  │ LLMaaS │  │  MCP Streamable HTTP
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
curl -s http://localhost:8080/health
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
pip install click rich prompt-toolkit mcp[cli]>=1.8.0
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

32 outils exposés via le protocole MCP (Streamable HTTP), répartis en 7 catégories.

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

### Admin (7 outils)

| Outil                 | Paramètres                                               | Description                                                                  |
| --------------------- | -------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `admin_create_token`  | `name`, `permissions`, `space_ids?`, `expires_in_days?`  | Crée un token (⚠️ affiché une seule fois). Permissions: read, write, admin |
| `admin_list_tokens`   | —                                                        | Liste les tokens actifs                                                      |
| `admin_revoke_token`  | `token_hash`                                             | Révoque un token (le rend inutilisable)                                      |
| `admin_delete_token`  | `token_hash`                                             | Supprime physiquement un token du registre (⚠️ irréversible)               |
| `admin_purge_tokens`  | `revoked_only?`                                          | Purge en masse : révoqués seuls (défaut) ou tous les tokens                  |
| `admin_update_token`  | `token_hash`, `space_ids`, `action`                      | Modifie les espaces d'un token (add/remove/set)                              |
| `admin_gc_notes`      | `space_id?`, `max_age_days?`, `confirm?`, `delete_only?` | Garbage Collector : nettoie les notes orphelines                             |

---

## 🌉 Graph Bridge — Pont vers Graph Memory

Live Memory peut pousser sa Memory Bank dans une instance [Graph Memory](https://github.com/chrlesur/graph-memory) pour la mémoire long terme. Le graphe de connaissances extrait les entités, relations et embeddings des fichiers bank.

---

## 🇬🇧 README English

Une version anglaise de cette documentation est disponible ici : [README.en.md](README.en.md)

---

## 🖥️ Interface Web

Live Memory expose une **interface web** sur `/live` pour visualiser les espaces mémoire en temps réel.

### Accès

```
http://localhost:8080/live
```

### Fonctionnalités

| Zone                                | Contenu                                                                                                                          |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **📊 Dashboard** (gauche)          | Infos espace, consolidation (date + compteurs), stats live/bank, agents colorés, catégories avec %, rules Markdown, Graph Memory |
| **🔴 Live Timeline** (haut-droite) | Notes live groupées par date (Aujourd'hui/Hier/date), cards avec agent + catégorie + Markdown                                    |
| **📘 Bank Viewer** (bas-droite)    | Onglets de fichiers consolidés, rendu Markdown avec marked.js                                                                    |

### Layout

```
┌──────────────┬────────────────────────────┐
│  📊 Dashboard│  🔴 Live Timeline          │
│  (infos,     │  (auto-refresh, groupé/date)│
│   agents,    ├────────────────────────────┤
│   rules...)  │  📘 Bank (onglets Markdown) │
└──────────────┴────────────────────────────┘
```

### Auto-refresh intelligent

- Configurable : 3s / 5s / 10s / 30s / manuel
- **Anti-flicker** : ne re-rend le DOM que si les données ont changé
- Pastille verte pulsante avec timestamp du dernier refresh
- Sélection d'espace → chargement immédiat (pas de bouton)

### API REST (5 endpoints)

| Endpoint                        | Description                                              |
| ------------------------------- | -------------------------------------------------------- |
| `GET /api/spaces`               | Liste des espaces                                        |
| `GET /api/space/{id}`           | Info complète (meta + rules + stats + graph-memory)      |
| `GET /api/live/{id}`            | Notes live (filtres: `?agent=`, `?category=`, `?limit=`) |
| `GET /api/bank/{id}`            | Liste des fichiers bank                                  |
| `GET /api/bank/{id}/{filename}` | Contenu d'un fichier bank                                |

Les endpoints `/api/*` nécessitent un Bearer Token. La page `/live` et les fichiers `/static/*` sont publics.

---

## 🔌 Intégration MCP

> 📖 **Guide complet** : Voir [GUIDE_INTEGRATION_CLINE.md](GUIDE_INTEGRATION_CLINE.md) pour le guide pas-à-pas détaillé (configuration Cline, custom instructions, workflow, multi-agents, dépannage).

### Avec Cline (VS Code / VSCodium)

Dans les settings MCP de Cline (`cline_mcp_settings.json`) :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_VOTRE_TOKEN"
      }
    }
  }
}
```

Puis ajoutez un fichier **`.clinerules/standard.memory.bank.md`** dans votre projet (ou dans les Custom Instructions globales) :

```markdown
# Cline's Memory Bank — Live Memory MCP

Ma mémoire se réinitialise complètement entre les sessions. Je dépends ENTIÈREMENT
de la Memory Bank pour comprendre le projet et continuer efficacement.

## 🔌 Connexion

Ma mémoire persistante est gérée par le serveur MCP **Live Memory** (`live-memory`).

- **Space** : `mon-projet`
- **Agent** : `cline-dev`

## 📖 Au démarrage de CHAQUE tâche (OBLIGATOIRE)

1. Appeler `space_rules("mon-projet")` pour lire les rules (structure de la bank)
2. Appeler `bank_read_all("mon-projet")` pour charger TOUT le contexte
3. Lire attentivement le contenu avant de commencer
4. Identifier le focus actuel dans `activeContext.md`

> ⚠️ Ne JAMAIS commencer à travailler sans avoir lu la bank.

## 📝 Pendant le travail

Écrire des notes fréquentes et atomiques avec `live_note` :

live_note(space_id="mon-projet", category="observation", content="...", agent="cline-dev")
live_note(space_id="mon-projet", category="decision", content="...", agent="cline-dev")
live_note(space_id="mon-projet", category="progress", content="...", agent="cline-dev")
live_note(space_id="mon-projet", category="issue", content="...", agent="cline-dev")
live_note(space_id="mon-projet", category="todo", content="...", agent="cline-dev")
live_note(space_id="mon-projet", category="insight", content="...", agent="cline-dev")

**Catégories** :
- `observation` — Constats factuels, résultats de commandes
- `decision` — Choix techniques et leur justification
- `progress` — Avancement, ce qui est terminé
- `issue` — Problèmes rencontrés, bugs
- `todo` — Tâches identifiées à faire
- `insight` — Apprentissages, patterns découverts
- `question` — Points à clarifier, décisions en suspens

## 🧠 En fin de session

bank_consolidate(space_id="mon-projet", agent="cline-dev")

Le LLM consolidera les notes en mettant à jour les fichiers de la bank selon les rules.

## ⚠️ Règles impératives

1. **Ne JAMAIS écrire directement dans la bank** — seule la consolidation LLM le fait
2. **Toujours passer `agent="cline-dev"`** dans `live_note` et `bank_consolidate`
3. **Toujours passer `space_id="mon-projet"`** dans tous les appels
4. **Écrire des notes atomiques** — 1 note = 1 fait, 1 décision, ou 1 tâche
5. **Consolider en fin de session** — ne jamais quitter sans consolider
6. **Lire la bank au démarrage** — ne jamais travailler sans contexte

## 🔄 Quand demander une mise à jour

Si l'utilisateur demande **"update memory bank"** ou **"met à jour la memory bank"** :
1. Écrire des notes `live_note` résumant l'état actuel du travail
2. Appeler `bank_consolidate("mon-projet", agent="cline-dev")`
3. Vérifier le résultat avec `bank_read_all("mon-projet")`

## 📊 Commandes utiles

| Action                          | Commande                                                                           |
| ------------------------------- | ---------------------------------------------------------------------------------- |
| Lire tout le contexte           | `bank_read_all("mon-projet")`                                                      |
| Lire les rules                  | `space_rules("mon-projet")`                                                        |
| Écrire une note                 | `live_note(space_id="mon-projet", category="...", content="...", agent="cline-dev")`|
| Consolider                      | `bank_consolidate(space_id="mon-projet", agent="cline-dev")`                       |
| Voir les notes récentes         | `live_read(space_id="mon-projet")`                                                 |
| Voir les notes d'un autre agent | `live_read(space_id="mon-projet", agent="claude-review")`                          |
| Info sur l'espace               | `space_info("mon-projet")`                                                         |
```

> 💡 Remplacez `mon-projet` par votre space_id et `cline-dev` par le nom de votre agent.

### Avec Claude Desktop

Dans `claude_desktop_config.json` :

```json
{
  "mcpServers": {
    "live-memory": {
      "url": "http://localhost:8080/mcp",
      "headers": {
        "Authorization": "Bearer lm_VOTRE_TOKEN"
      }
    }
  }
}
```

### Via Python (client MCP)

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def exemple():
    headers = {"Authorization": "Bearer votre_token"}
    async with streamablehttp_client("http://localhost:8080/mcp", headers=headers) as (r, w, _):
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
pip install click rich prompt-toolkit mcp[cli]>=1.8.0
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
python scripts/mcp_cli.py graph connect mon-projet URL TOKEN MEM-ID -o general
python scripts/mcp_cli.py graph push mon-projet
python scripts/mcp_cli.py graph status mon-projet
python scripts/mcp_cli.py graph disconnect mon-projet
```

### Shell interactif

```bash
python scripts/mcp_cli.py shell
```

Autocomplétion, historique, affichage Rich. Voir [scripts/README.md](scripts/README.md) pour la référence complète.

---

## 🧪 Tests

5 scripts de test E2E, tous avec `--step` (pas-à-pas) et `--no-cleanup`.

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

# 5. Qualité : 28 tests couvrant les 7 catégories d'outils
python scripts/test_qualite.py

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
- **Rate Limiting** : 200 MCP/min (Streamable HTTP)
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
├── src/live_mem/              # Code source (32 outils MCP + interface web)
│   ├── server.py              # Serveur FastMCP + middlewares
│   ├── config.py              # Configuration pydantic-settings
│   ├── auth/                  # Authentification
│   │   ├── middleware.py      #   Auth + Logging + StaticFiles
│   │   └── context.py         #   check_access, check_write, check_admin
│   ├── static/                # Interface web /live
│   │   ├── live.html          #   SPA (Dashboard + Live + Bank)
│   │   ├── css/live.css       #   Styles (thème Cloud Temple)
│   │   ├── js/                #   7 modules JS (config, api, app, dashboard, timeline, bank, sidebar)
│   │   └── img/               #   Logo Cloud Temple SVG
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
│   └── tools/                 # Outils MCP (7 modules, 57 params documentés)
│       ├── system.py          #   2 outils (health, about)
│       ├── space.py           #   7 outils (CRUD espaces) — 10 params
│       ├── live.py            #   3 outils (notes) — 13 params
│       ├── bank.py            #   4 outils (bank + consolidation) — 6 params
│       ├── graph.py           #   4 outils (Graph Bridge) — 8 params
│       ├── backup.py          #   5 outils (snapshots) — 8 params
│       └── admin.py           #   7 outils (tokens + GC + purge) — 14 params
├── scripts/                   # CLI + Shell + Tests
│   ├── mcp_cli.py             #   Point d'entrée CLI Click
│   ├── delete_tokens.py       #   Utilitaire gestion tokens à distance
│   ├── check_annotated_params.py # Vérification des descriptions de paramètres
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
├── VERSION                    # 0.6.0
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

- Vérifiez que Graph Memory est accessible : `curl https://votre-graph-memory/mcp`
- Vérifiez le token Graph Memory (Bearer)
- L'URL peut être avec ou sans `/mcp` (normalisée automatiquement)

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

*Live Memory v0.6.0 — Mémoire de travail partagée pour agents IA collaboratifs*
