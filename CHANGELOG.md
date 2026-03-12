# Changelog — Live Memory

Toutes les modifications notables sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

---

## [0.7.1] — 2026-03-12

### Sécurité — Alignement des droits avec Graph Memory
- **Auto-ajout du space au token à la création** — Quand un client restreint (`space_ids: ["A"]`) crée un space "B", le space B est automatiquement ajouté à ses `space_ids` dans `tokens.json`. Élimine le deadlock UX où le client ne pouvait pas accéder au space qu'il venait de créer. Nouvelle méthode `TokenService.add_space_to_token()`.
- **Filtrage `backup_list` par space_ids du token** — Un client ne voit plus que les backups des spaces auxquels il a accès. Corrige une fuite d'information où un client pouvait lister tous les backups de tous les espaces.
- **Confirmation `backup_download` sécurisé** — Vérifié que `check_access(space_id)` est déjà en place (extrait le space_id du backup_id). Aucune modification nécessaire.
- **Script de recette unifié** — `scripts/test_recette.py` refait avec 4 suites sélectionnables par CLI (`--suite recette,isolation,qualite,graph`). Suite `isolation` : ~20 tests vérifiant l'isolation multi-tenant (accès inter-espaces refusé, filtrage backup_list, écriture read-only refusée, auto-ajout space au token).
- **Champ `email` dans les tokens** — Alignement Graph Memory : `admin_create_token(email=)` optionnel pour la traçabilité. Affiché dans `token list` (colonnes : Nom, Email, Hash, Permissions, Espaces, Créé le, Expire). CLI : `--email/-e`, Shell : `--email`.
- **CLI complète (32/32 outils)** — Ajouté : `space summary`, `space export`, `backup download`, `gc` en Click et Shell interactif.
- **WAF rate limits ×3** — MCP 200→600 req/min, API 60→120, Global 500→1500 (résout les TaskGroup errors).
- **Nettoyage scripts/** — 5 scripts supprimés (test_qualite, test_multi_agents, test_gc, test_graph_bridge, test_markdown_engine), tout intégré dans `test_recette.py`.

---

## [0.6.0] — 2026-03-11

### Changé — Consolidation chirurgicale (édition par section Markdown)
- **Refonte majeure du consolidateur LLM** — Passage du mode "réécriture complète" au mode "édition chirurgicale". Le LLM produit désormais des **opérations d'édition par section Markdown** (`replace_section`, `append_to_section`, `prepend_to_section`, `add_section`, `delete_section`) au lieu de réécrire les fichiers entiers.
- **Zéro perte de matière** — Ce qui n'est pas touché explicitement reste intact byte-for-byte. Test A/B validé : l'ancien mode perdait 28 lignes, le nouveau mode n'en perd aucune (hors `replace_section` attendu sur le focus).
- **Moteur d'édition Markdown** — Nouveau moteur dans `consolidator.py` : `_parse_sections()`, `_find_section_index()` (matching flexible 3 niveaux : exact → sans # → case-insensitive), `_reconstruct_from_sections()`, `_apply_operation()`.
- **Prompts LLM mis à jour** — Le prompt système et utilisateur demandent des opérations d'édition au format JSON structuré, avec 3 actions par fichier : `edit` (opérations chirurgicales), `create` (nouveau fichier), `rewrite` (fallback justifié).
- **Rétrocompatibilité** — Si le LLM retourne l'ancien format `bank_files`, conversion automatique via `_convert_legacy_format()`.

### Ajouté
- **Métriques de consolidation enrichies** — `operations_applied` et `operations_failed` dans le retour de `bank_consolidate` et dans le front-matter de `_synthesis.md`.
- **77 tests unitaires** — `scripts/test_markdown_engine.py` couvre le moteur d'édition : parsing, reconstruction, idempotence, toutes les opérations, cas limites, scénarios réalistes.
- **Test E2E consolidation chirurgicale** — `test_surgical_consolidation.py` : 7 phases (création, consolidation create, snapshot, notes supplémentaires, consolidation chirurgicale, comparaison avant/après, nettoyage).
- **Test A/B** — `run_ab_test.py` : compare production (ancien mode) vs local (nouveau mode) sur les mêmes données.

### Gains mesurés (test A/B)
| Métrique | Ancien mode (réécriture) | Nouveau mode (chirurgical) |
|---|---|---|
| Lignes perdues (progress.md) | 10 | **0** |
| Lignes perdues (total) | 28 | **1** (replace_section attendu) |
| Tokens completion LLM | 4850 | **3993** (-18%) |
| Durée consolidation | 29s | **14.4s** (-50%) |

### Fichiers modifiés
| Fichier | Changements |
|---------|------------|
| `src/live_mem/core/consolidator.py` | Moteur d'édition Markdown + prompts chirurgicaux + rétrocompat |
| `DESIGN/live-mem/CONSOLIDATION_LLM.md` | Design doc v0.6.0 complet |
| `scripts/test_markdown_engine.py` | 77 tests unitaires (nouveau) |

---

## [0.5.3] — 2026-03-09

### Corrigé — Validation des permissions tokens
- **Bug "permissions all"** — Le système acceptait n'importe quel texte comme permission (ex: `"all"`), mais `check_write_permission()` et `check_admin_permission()` ne reconnaissaient que `"read"`, `"write"` et `"admin"` individuellement. Un token créé avec `permissions="all"` était donc inutilisable pour les opérations write/admin.
- **Validation côté serveur** — `VALID_PERMISSIONS = {"read", "write", "admin"}` défini dans `core/tokens.py`. Les méthodes `create_token()` et `update_token()` rejettent désormais les permissions invalides avec un message explicite.
- **Validation côté CLI** — `token create` utilise `click.Choice(["read", "read,write", "read,write,admin"])` : plus de texte libre, Click rejette immédiatement les valeurs invalides.
- **Validation côté shell** — Le shell interactif valide aussi les permissions avant l'appel MCP.

### Ajouté — Commande `token update`
- **CLI Click** : `token update <hash> --permissions read,write --space-ids "p1,p2"` — permissions contraintes par `click.Choice`
- **Shell interactif** : `token update sha256:a8c5 --permissions read,write` avec parsing des flags `-p`/`-s`
- **Autocomplétion** enrichie dans le shell : `--permissions`, `--space-ids`, `read`, `read,write`, `read,write,admin`

### Fichiers modifiés
| Fichier | Changements |
|---------|------------|
| `scripts/cli/commands.py` | `VALID_PERMISSIONS` (click.Choice), `token_create_cmd` contraint, `token_update_cmd` ajouté |
| `scripts/cli/shell.py` | `_VALID_PERMS`, `_validate_permissions()`, handler `token update`, autocomplétion étendue |
| `src/live_mem/core/tokens.py` | `VALID_PERMISSIONS`, validation dans `create_token()` et `update_token()` |

---

## [0.5.2] — 2026-03-09

### Ajouté — Suppression physique des tokens
- **`admin_delete_token`** 👑 — Supprime physiquement un token du registre `tokens.json` sur S3
- **`admin_purge_tokens`** 👑 — Purge en masse : tokens révoqués seuls (`revoked_only=True`) ou tous (`revoked_only=False`)
- **32 outils MCP** (était 30) — 7 catégories (admin passe de 5 à 7 outils)
- **Script `scripts/delete_tokens.py`** — Utilitaire CLI pour lister, révoquer et purger les tokens à distance
  - `list` : liste les tokens
  - `revoke_all` : révoque tous les tokens actifs
  - `purge` : supprime physiquement les tokens révoqués
  - `purge_all` : supprime physiquement TOUS les tokens

### Notes
- Le **bootstrap key** (variable d'environnement `ADMIN_BOOTSTRAP_KEY`) n'est jamais stocké dans `tokens.json` et ne peut pas être supprimé
- Les 2 nouveaux outils utilisent le pattern `Annotated[type, Field(description="...")]` pour les descriptions Cline
- Méthodes `delete_token()` et `purge_tokens()` ajoutées dans `TokenService` (`core/tokens.py`)

---

## [0.5.1] — 2026-03-08

### Ajouté — Descriptions de paramètres MCP pour Cline
- **57 paramètres documentés** dans les 30 outils MCP avec le pattern `Annotated[type, Field(description="...")]`
- Chaque paramètre utilisateur affiche désormais sa description dans l'interface Cline (au lieu de "No description")
- Les descriptions incluent : valeurs possibles, exemples, contraintes, formats attendus
- Imports `from typing import Annotated` et `from pydantic import Field` ajoutés dans 6 fichiers tools
- **Script de vérification** `scripts/check_annotated_params.py` pour valider la couverture
- Pattern appliqué conforme au guide `MCP Tool Parameter Descriptions`

### Amélioré — CLI Shell : messages `--confirm`
- Les commandes `space delete`, `backup restore`, `backup delete` affichent un message d'aide clair quand `--confirm` est oublié
- Avant : erreur cryptique du serveur ("confirm=True requis")
- Après : `⚠️ Suppression de 'xxx' — ajoutez --confirm pour confirmer : space delete xxx --confirm`

### Détail par fichier
| Fichier     | Tools  | Params documentés |
| ----------- | ------ | ----------------- |
| `space.py`  | 7      | 10                |
| `live.py`   | 3      | 13                |
| `bank.py`   | 4      | 6                 |
| `graph.py`  | 4      | 8                 |
| `admin.py`  | 5      | 12                |
| `backup.py` | 5      | 8                 |
| `system.py` | 2      | 0 (aucun param)   |
| **Total**   | **30** | **57**            |

### Impact
- Les LLMs connectés via Cline disposent désormais de descriptions complètes pour chaque paramètre
- Réduction des erreurs de saisie et des retries grâce au guidage contextuel
- Aucun changement fonctionnel — uniquement des métadonnées de schéma JSON

---

## [0.5.0] — 2026-03-04

### Changé — Migration SSE → Streamable HTTP (issue #1)
- **Transport MCP** : `sse_app()` → `streamable_http_app()` — endpoint unique `/mcp` (remplace `/sse` + `/messages`)
- **SDK MCP** : `mcp>=1.2.0` → `mcp>=1.8.0` (v1.26.0)
- **Client CLI** (`scripts/cli/client.py`) : réécrit avec le SDK MCP officiel (`streamablehttp_client`), suppression du handshake SSE manuel (~150 lignes en moins)
- **Graph Bridge** (`core/graph_bridge.py`) : `GraphMemoryClient` réécrit avec sessions MCP auto-contenues (corrige l'erreur "cancel scope in different task" avec anyio). Ajout de `call_tools_batch()` pour les opérations multi-appels (push).
- **WAF Caddyfile** : routes `/sse*` + `/messages/*` fusionnées en `/mcp*`, rate limiting recalibré (200 req/min — chaque appel MCP = ~3 HTTP requests)
- **`HostNormalizerMiddleware`** supprimé (plus nécessaire avec Streamable HTTP)
- Pile middlewares : `Auth → Logging → StaticFiles → MCP Streamable HTTP`

### Ajouté
- **Endpoint `/health`** — Réponse JSON directe (`{"status": "healthy", "transport": "streamable-http"}`) pour les healthchecks Docker/WAF. Nécessaire car `streamable_http_app()` ne sert que `/mcp`.
- **`HEALTHCHECK` Docker** — `python urllib.request` sur `/health` (remplace le TCP socket)
- **`test_qualite.py`** — Test de qualité officiel (28 tests couvrant les 7 catégories d'outils : system, admin, space, live, bank, backup, gc, graph). Résultat attendu : 28 PASS, 0 FAIL.

### Supprimé
- `HostNormalizerMiddleware` (classe supprimée de `middleware.py`)
- Dépendance implicite à `httpx-sse` côté client (le SDK MCP gère le transport)
- Endpoints `/sse` et `/messages/*` (remplacés par `/mcp`)

---

## [0.4.0] — 2026-03-03

### Ajouté
- **🖥️ Interface Web `/live`** — Dashboard + Live Timeline + Bank Viewer
  - Page SPA accessible sur `/live` (même pattern que `/Graph` de graph-memory)
  - Login overlay avec Bearer Token (stocké en localStorage)
  - Layout 3 zones : Dashboard (gauche) | Live Timeline (haut-droite) | Bank (bas-droite)
  - Séparateur redimensionnable par drag entre Live et Bank
  - **Auto-refresh intelligent** configurable (3s/5s/10s/30s/manuel) — ne re-rend le DOM que si les données ont changé (anti-flicker via hash comparaison)
  - Pastille verte pulsante avec timestamp du dernier refresh
  - **Dashboard** : infos espace, consolidation (date + compteurs), stats live/bank, agents colorés, catégories avec %, rules Markdown, Graph Memory
  - **Live Timeline** : notes groupées par date (Aujourd'hui/Hier/date), cards avec agent coloré + catégorie + rendu Markdown
  - **Bank Viewer** : onglets de fichiers, rendu Markdown avec marked.js
  - Sélection espace → chargement immédiat (pas de bouton)
- **`StaticFilesMiddleware`** — Middleware ASGI pour servir `/live`, `/static/*` et 5 endpoints API REST
  - `GET /api/spaces` — Liste des espaces
  - `GET /api/space/{id}` — Info complète (meta + rules + stats)
  - `GET /api/live/{id}` — Notes live (filtres optionnels)
  - `GET /api/bank/{id}` — Liste fichiers bank
  - `GET /api/bank/{id}/{filename}` — Contenu d'un fichier bank
- **10 fichiers statiques** : HTML, CSS, 7 modules JS, logo SVG Cloud Temple
- **Parsing JSON robuste** dans le client API (gère réponses vides/tronquées)

### Changé
- **Dockerfile rootless** — User `mcp` UID 10001, `COPY --chown=mcp:mcp`, aucune opération root après `USER mcp`
- **`AuthMiddleware`** — Routes publiques étendues (`/live`, `/static/`)
- **`server.py`** — `StaticFilesMiddleware` ajouté dans la pile ASGI, URL `/live` dans la bannière
- Pile middlewares : `Auth → Logging → StaticFiles → HostNormalizer → MCP SSE`
- **Venv** : `.venv/` ajouté au `.gitignore`

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
