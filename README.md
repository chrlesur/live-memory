# 🧠 Live Memory — MCP Server

> **Mémoire de travail partagée pour agents IA collaboratifs**

[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)]()
[![MCP](https://img.shields.io/badge/protocol-MCP-purple.svg)]()
[![Python](https://img.shields.io/badge/python-3.11+-yellow.svg)]()

---

## 🎯 Vision

**Live Memory** est un serveur MCP (Model Context Protocol) qui fournit une **Memory Bank as a Service** pour des agents IA. Plusieurs agents peuvent collaborer sur un même projet en partageant une mémoire de travail commune.

```
graph-memory  = Mémoire LONG TERME (documents → Knowledge Graph → RAG)
live-mem      = Mémoire de TRAVAIL (notes live → LLM → Memory Bank structurée)
```

### Deux modes complémentaires

| Mode         | Description                                                                     | Analogie                   |
| ------------ | ------------------------------------------------------------------------------- | -------------------------- |
| **🔴 Live** | Les agents écrivent des notes en temps réel (observations, décisions, todos...) | Tableau blanc partagé      |
| **📘 Bank** | Un LLM consolide les notes en fichiers Markdown structurés selon des rules      | Cahier de projet structuré |

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
          │   Rate Limiting • TLS                  │
          └────────────┬───────────────────────────┘
                       │
          ┌────────────┴───────────────────┐
          │   Live Memory MCP (:8002)      │
          │   26 outils • Auth Bearer      │
          │   Consolidation LLM            │
          └──────┬──────────┬──────────────┘
                 │          │
          ┌──────┴──┐  ┌────┴──────┐
          │   S3    │  │   LLMaaS  │
          │Dell ECS │  │  CT API   │
          └─────────┘  └───────────┘
```

**Stack minimale** : S3 + LLM. Pas de base de données (pas de Neo4j, pas de Qdrant).

---

## ✨ Fonctionnalités

### 26 outils MCP

| Catégorie       | Outils                                                                                                     | Description                 |
| --------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------- |
| **System** (2)  | `system_health`, `system_about`                                                                            | Santé & identité            |
| **Space** (7)   | `space_create`, `space_list`, `space_info`, `space_rules`, `space_summary`, `space_export`, `space_delete` | Gestion des espaces mémoire |
| **Live** (3)    | `live_note`, `live_read`, `live_search`                                                                    | Notes en temps réel         |
| **Bank** (4)    | `bank_read`, `bank_read_all`, `bank_list`, `bank_consolidate`                                              | Memory Bank consolidée      |
| **Backup** (5)  | `backup_create`, `backup_list`, `backup_restore`, `backup_download`, `backup_delete`                       | Sauvegarde & restauration   |
| **Admin** (5)   | `admin_create_token`, `admin_list_tokens`, `admin_revoke_token`, `admin_update_token`, `admin_gc_notes`    | Tokens + Garbage Collector  |

> **Statut** : ✅ 26/26 outils implémentés, pipeline E2E validé via Docker Compose + WAF sur infrastructure Cloud Temple (S3 + LLMaaS)

### Points forts

- 🤝 **Multi-agents natif** — Plusieurs agents écrivent simultanément sans conflit (append-only)
- 🧠 **Consolidation LLM** — Un LLM (qwen3-2507:235b) synthétise les notes en fichiers bank structurés
- 📐 **Rules dynamiques** — La structure de la bank est définie par des rules à la création de l'espace
- 🔒 **Sécurité complète** — WAF Coraza, Rate Limiting, TLS, Auth Bearer, Access Control par espace
- 💾 **S3-only** — Pas de base de données, tout est fichier Markdown/JSON sur S3
- 📦 **Backup/Restore** — Snapshots complets des espaces sur S3

---

## 🚀 Démarrage rapide

### Prérequis

- Docker >= 24.0 + Docker Compose v2
- Un bucket S3 (Cloud Temple Dell ECS ou compatible)
- Une clé API LLMaaS Cloud Temple

### Installation (Docker)

```bash
git clone https://github.com/chrlesur/live-memory.git
cd live-memory
cp .env.example .env
nano .env  # Remplir S3, LLMaaS, ADMIN_BOOTSTRAP_KEY

docker compose build
docker compose up -d
```

### Installation (Dev local)

```bash
git clone https://github.com/chrlesur/live-memory.git
cd live-memory
cp .env.example .env
nano .env  # Remplir les credentials

pip install -r requirements.txt
cd src && python -m live_mem.server
```

### Vérification rapide

```bash
# Recette complète via Docker Compose + WAF
docker compose build && docker compose up -d
python scripts/test_recette.py

# Test multi-agents (3 agents collaborent)
python scripts/test_multi_agents.py

# Test du Garbage Collector
python scripts/test_gc.py

# Mode pas-à-pas (démo interactive)
python scripts/test_multi_agents.py --step
```

---

## 📂 Structure du projet

```
live-mem/
├── DESIGN/
│   ├── live-mem/           # 📐 Architecture (9 documents)
│   │   ├── ARCHITECTURE.md
│   │   ├── MCP_TOOLS_SPEC.md
│   │   ├── S3_DATA_MODEL.md
│   │   ├── CONSOLIDATION_LLM.md
│   │   ├── AUTH_AND_COLLABORATION.md
│   │   ├── CONCURRENCY.md
│   │   ├── DEPLOIEMENT_PRODUCTION.md
│   │   ├── CLOUD_TEMPLE_SERVICES.md
│   │   └── ANALYSE_RISQUES_SECURITE.md
├── src/                    # 🐍 Code source (25 outils MCP)
│   └── live_mem/
│       ├── server.py       # Point d'entrée ASGI + middlewares
│       ├── config.py       # Configuration pydantic-settings
│       ├── auth/           # Auth Bearer (contextvars + middleware)
│       ├── core/           # Services métier
│       │   ├── storage.py  #   S3 dual SigV2/SigV4 (Dell ECS)
│       │   ├── space.py    #   CRUD espaces mémoire
│       │   ├── live.py     #   Notes live (append-only)
│       │   ├── consolidator.py # Pipeline LLM
│       │   ├── tokens.py   #   Gestion tokens SHA-256
│       │   ├── backup.py   #   Snapshots S3
│       │   └── gc.py       #   Garbage Collector
│       └── tools/          # Outils MCP par catégorie
│           ├── system.py   #   2 outils
│           ├── space.py    #   7 outils
│           ├── live.py     #   3 outils
│           ├── bank.py     #   4 outils
│           ├── backup.py   #   5 outils
│           └── admin.py    #   5 outils (tokens + GC)
├── scripts/                # 🖥️ CLI + Shell + Tests
├── waf/                    # 🛡️ WAF Caddy + Coraza
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── VERSION                 # 0.2.0
├── CHANGELOG.md            # 📋 Historique des versions
├── FAQ.md                  # ❓ Questions fréquentes
└── README.md               # ← Vous êtes ici
```

---

## 🔧 Configuration

### Variables d'environnement obligatoires

| Variable               | Description                           |
| ---------------------- | ------------------------------------- |
| `S3_ENDPOINT_URL`      | URL endpoint S3                       |
| `S3_ACCESS_KEY_ID`     | Access key S3                         |
| `S3_SECRET_ACCESS_KEY` | Secret key S3                         |
| `S3_BUCKET_NAME`       | Nom du bucket                         |
| `S3_REGION_NAME`       | Région (ex: `fr1`)                    |
| `LLMAAS_API_URL`       | URL API LLMaaS (avec `/v1`)           |
| `LLMAAS_API_KEY`       | Clé API LLMaaS                        |
| `ADMIN_BOOTSTRAP_KEY`  | Clé admin pour créer le premier token |

Voir `.env.example` pour la liste complète.

---

## 🤝 Collaboration multi-agents

Live Memory est conçu pour que plusieurs agents IA travaillent ensemble :

```
Agent Cline (Dev)     → live_note("observation", "Le build passe")
Agent Claude (Review) → live_note("insight", "Le pattern est pertinent")
Agent QA              → live_note("issue", "Test #42 échoue")
                             │
                             ▼
                    bank_consolidate()
                             │
                             ▼
                    Memory Bank mise à jour
                    (activeContext.md, progress.md, ...)
```

Chaque agent :
1. Charge le contexte : `bank_read_all("mon-projet")`
2. Écrit ses observations : `live_note("observation", "...")`
3. Lit les notes des autres : `live_read(agent="claude-review")`
4. Consolide périodiquement : `bank_consolidate("mon-projet")`

---

## 📖 Documentation

| Document                                                                   | Description                                    |
| -------------------------------------------------------------------------- | ---------------------------------------------- |
| [ARCHITECTURE.md](DESIGN/live-mem/ARCHITECTURE.md)                         | Vision, stack technique, flux de données       |
| [MCP_TOOLS_SPEC.md](DESIGN/live-mem/MCP_TOOLS_SPEC.md)                     | Spécification des 24 outils MCP                |
| [S3_DATA_MODEL.md](DESIGN/live-mem/S3_DATA_MODEL.md)                       | Modèle de données S3, format des fichiers      |
| [CONSOLIDATION_LLM.md](DESIGN/live-mem/CONSOLIDATION_LLM.md)               | Pipeline de consolidation LLM                  |
| [AUTH_AND_COLLABORATION.md](DESIGN/live-mem/AUTH_AND_COLLABORATION.md)     | Authentification et collaboration multi-agents |
| [CONCURRENCY.md](DESIGN/live-mem/CONCURRENCY.md)                           | Gestion de la concurrence                      |
| [DEPLOIEMENT_PRODUCTION.md](DESIGN/live-mem/DEPLOIEMENT_PRODUCTION.md)     | Guide de déploiement                           |
| [CLOUD_TEMPLE_SERVICES.md](DESIGN/live-mem/CLOUD_TEMPLE_SERVICES.md)       | Configuration services Cloud Temple            |
| [ANALYSE_RISQUES_SECURITE.md](DESIGN/live-mem/ANALYSE_RISQUES_SECURITE.md) | Analyse des risques et sécurité                |

---

## 🔗 Projets liés

| Projet           | Description                                        | Lien                                                                         |
| ---------------- | -------------------------------------------------- | ---------------------------------------------------------------------------- |
| **graph-memory** | Mémoire long terme (Knowledge Graph + RAG)         | [github.com/chrlesur/graph-memory](https://github.com/chrlesur/graph-memory) |

---

## 📄 Licence

Apache License 2.0 — Voir [LICENSE](LICENSE)

---

## 👤 Auteur

**Cloud Temple** — [cloud-temple.com](https://www.cloud-temple.com)

---

*Live Memory v0.2.0 — Mémoire de travail partagée pour agents IA collaboratifs*
