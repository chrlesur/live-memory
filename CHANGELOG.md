# Changelog — Live Memory

Toutes les modifications notables sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

---

## [0.3.0] — 2026-02-21

### Ajouté
- **🌉 Graph Bridge** — Pont entre Live Memory (mémoire de travail) et Graph Memory (mémoire long terme)
  - `graph_connect` — Connecte un space à une instance Graph Memory (teste la connexion, crée la mémoire si besoin)
  - `graph_push` — Synchronise la bank dans le graphe (delete + re-ingest intelligent, nettoyage orphelins)
  - `graph_status` — Statut complet : stats graphe (documents, entités, relations), liste des documents ingérés, top entités
  - `graph_disconnect` — Déconnecte un space (les données restent dans le graphe)
- **`GraphMemoryConfig`** dans `SpaceMeta` — Configuration de connexion stockée dans `_meta.json` (url, token, memory_id, ontology, métriques push)
- **`GraphMemoryClient`** — Client MCP SSE minimaliste pour communiquer avec graph-memory (handshake complet, call_tool)
- **`GraphBridgeService`** — Service orchestrateur (connect, push, status, disconnect)
- **Test E2E `test_graph_bridge.py`** — Pipeline complet : notes → consolidation → push graph → stats → ré-ingestion → déconnexion
  - Mode `--step` (pas-à-pas interactif)
  - Affichage Rich (encadrés, stats graphe, top entités)
  - Arguments `--graph-url`, `--graph-token`, `--ontology`, `--graph-memory-id`
- **30 outils MCP** (était 26) — 7 catégories (+ graph)
- Ontologie paramétrable pour graph-memory (défaut: `general`, options: legal, cloud, managed-services, presales)
- **CLI Click `graph`** — 4 commandes scriptables : `graph connect`, `graph push`, `graph status`, `graph disconnect`
- **Shell interactif `graph`** — 4 commandes avec help contextuel (`help graph`)
- **Affichage Rich** — `show_graph_connected`, `show_graph_status` (stats + docs + top entités), `show_graph_push_result`, `show_graph_disconnected`
- Code mutualisé `display.py` partagé entre CLI Click et Shell (DRY)

### Changé
- Module `tools/__init__.py` — Enregistrement du nouveau module `tools/graph.py`
- Total outils MCP : **30** (26 + 4 graph)

---

## [0.2.0] — 2026-02-21

### Ajouté
- **Garbage Collector** (`admin_gc_notes`) — Nettoyage des notes orphelines
  - Mode dry-run (scan), consolidation forcée (LLM), suppression simple
  - Note "⚠️ GC — Consolidation forcée" ajoutée à la bank pour traçabilité
- **Découplage Token / Agent** — Le token est pour l'auth, le nom d'agent est explicite
  - `bank_consolidate` accepte un paramètre `agent=` (vide = consolide tout)
  - `live_note` avec `agent=` explicite, indépendant du token
  - Un token peut être partagé entre plusieurs agents
- **Scripts de test/recette**
  - `test_recette.py` — Recette E2E (1 agent, 12 notes, consolidation, bank)
  - `test_multi_agents.py` — 3 agents collaborent (infra + dev + qa)
  - `test_gc.py` — Test du Garbage Collector
  - Mode `--step` (pas-à-pas) pour démo interactive
  - Mode `--no-cleanup` pour inspection post-test
- **Client MCP** — Handshake `initialize` + `notifications/initialized` (protocole MCP complet)
- **26ème outil** : `admin_gc_notes` (GC des notes orphelines)

### Corrigé
- **Dockerfile** — CMD corrigé (`python -m live_mem` + `PYTHONPATH=/app/src`)
- **Caddyfile** — Nom du service `mon-mcp` → `live-mem-service`
- **Healthcheck Docker** — TCP socket au lieu de HTTP `/health` (FastMCP SSE)
- **Image Docker** — Nom propre `live-memory:latest` (au lieu de `live-mem-live-mem-service`)
- **Bannière de démarrage** — Cadre dynamique, gestion des emoji via `unicodedata`
- **Auth backup_list / backup_download** — `check_access(space_id)` ajouté
- **Rate limits WAF** — Augmentés pour tests multi-agents (60 SSE, 300 msg/min)
- **CLI URL par défaut** — `http://localhost:8080` (WAF) au lieu de `:8002` (direct)
- **CLI token fallback** — MCP_TOKEN → ADMIN_BOOTSTRAP_KEY → .env (4 niveaux)
- **About display** — Descriptions propres (1 ligne), groupées par catégorie
- **Shell help contextuel** — `help space`, `space help`, `help bank`, etc.

### Changé
- `bank_consolidate` — Paramètre `agent` explicite (plus de couplage avec le token name)
- `bank_consolidate` — Permission admin requise pour consolider les notes d'un autre agent
- Admin tools — 5 outils au lieu de 4 (`admin_gc_notes` ajouté)
- Logging structuré — `logging` Python au lieu de `print(stderr)` (auth, storage, consolidator, gc)
- Total outils MCP : **26** (25 + 1 GC)

---

## [0.1.0] — 2026-02-20

### Ajouté
- **25 outils MCP** en 6 catégories (system, space, live, bank, backup, admin)
- **Architecture modulaire** tools/ avec register pattern
- **S3 Dell ECS** — Dual client SigV2/SigV4, suppressions individuelles
- **LLMaaS Cloud Temple** — qwen3-2507:235b, extraction JSON manuelle
- **Consolidation par agent** — Chaque agent consolide ses propres notes
- **Auth middleware** — Bootstrap key + TokenService S3 (SHA-256)
- **CLI Click** — Sous-groupes (space, live, bank, token, backup)
- **Shell interactif** — prompt_toolkit avec autocomplétion
- **WAF Caddy + Coraza** — OWASP CRS, rate limiting, TLS auto
- **Docker Compose** — Service MCP + WAF
- **Test E2E** — Pipeline complet validé sur infrastructure Cloud Temple
- **9 documents de design** — Architecture, S3, LLM, Auth, Concurrence, Déploiement...
