# 🖥️ Live Memory CLI, Shell & Tests

> CLI scriptable, shell interactif et scripts de test pour Live Memory MCP.

---

## Prérequis

```bash
pip install click rich prompt-toolkit httpx httpx-sse
```

Variables d'environnement :
```bash
export MCP_URL=http://localhost:8080    # URL du serveur (via WAF)
export MCP_TOKEN=votre_token_secret     # Token d'authentification
```

---

## CLI scriptable (Click)

### Commandes système

```bash
# État de santé (S3, LLMaaS, espaces)
python scripts/mcp_cli.py health
python scripts/mcp_cli.py health --json   # Sortie JSON brute

# Informations sur le service (version, outils)
python scripts/mcp_cli.py about
```

### Gestion des espaces

```bash
# Créer un espace avec des rules depuis un fichier
python scripts/mcp_cli.py space create mon-projet \
  --rules-file ./rules/standard.md \
  --description "Mon projet" \
  --owner "equipe-dev"

# Lister les espaces accessibles
python scripts/mcp_cli.py space list

# Infos détaillées d'un espace
python scripts/mcp_cli.py space info mon-projet

# Lire les rules d'un espace
python scripts/mcp_cli.py space rules mon-projet

# Supprimer un espace (⚠️ irréversible)
python scripts/mcp_cli.py space delete mon-projet --confirm
```

### Notes live

```bash
# Écrire une note
python scripts/mcp_cli.py live note mon-projet observation "Le build passe" \
  --agent cline-dev \
  --tags "build,ci"

# Lire les notes (filtres optionnels)
python scripts/mcp_cli.py live read mon-projet
python scripts/mcp_cli.py live read mon-projet --category observation --limit 10
python scripts/mcp_cli.py live read mon-projet --agent claude-review

# Rechercher dans les notes
python scripts/mcp_cli.py live search mon-projet "S3"
```

### Memory Bank

```bash
# Lister les fichiers bank
python scripts/mcp_cli.py bank list mon-projet

# Lire un fichier bank spécifique
python scripts/mcp_cli.py bank read mon-projet activeContext.md

# Lire toute la bank d'un coup
python scripts/mcp_cli.py bank read-all mon-projet

# 🧠 Consolider les notes via LLM
python scripts/mcp_cli.py bank consolidate mon-projet
```

### Tokens d'authentification

```bash
# Créer un token (⚠️ le token ne sera affiché qu'une fois !)
python scripts/mcp_cli.py token create agent-cline read,write \
  --space-ids "mon-projet" \
  --expires-in-days 90

# Lister les tokens
python scripts/mcp_cli.py token list

# Révoquer un token
python scripts/mcp_cli.py token revoke sha256:a1b2c3...
```

### Garbage Collector

```bash
# Dry-run : scanner les notes orphelines (> 7 jours)
python scripts/mcp_cli.py gc --space-id mon-projet

# Consolider les notes orphelines dans la bank (via LLM)
python scripts/mcp_cli.py gc --space-id mon-projet --confirm

# Supprimer sans consolider (perte de données !)
python scripts/mcp_cli.py gc --space-id mon-projet --confirm --delete-only

# Scanner tous les espaces
python scripts/mcp_cli.py gc --max-age-days 14
```

### Backup & Restore

```bash
# Créer un backup
python scripts/mcp_cli.py backup create mon-projet \
  --description "Avant refactoring"

# Lister les backups
python scripts/mcp_cli.py backup list
python scripts/mcp_cli.py backup list --space-id mon-projet

# Restaurer (l'espace ne doit pas exister)
python scripts/mcp_cli.py backup restore mon-projet/2026-02-20T18-00-00 --confirm

# Supprimer un backup
python scripts/mcp_cli.py backup delete mon-projet/2026-02-20T18-00-00 --confirm
```

---

## Shell interactif

```bash
python scripts/mcp_cli.py shell
```

Le shell offre :
- **Autocomplétion** (Tab) sur toutes les commandes
- **Historique** persistant (`~/.live_mem_shell_history`)
- **Affichage Rich** coloré (tables, panels, Markdown)

### Commandes shell

```
live-mem> help                        # Aide
live-mem> health                      # État de santé
live-mem> about                       # Infos service

live-mem> space list                  # Lister les espaces
live-mem> space info mon-projet       # Infos détaillées
live-mem> space create id desc rules  # Créer un espace

live-mem> live note projet obs "Build OK"  # Écrire une note
live-mem> live read projet            # Lire les notes
live-mem> live search projet "S3"     # Rechercher

live-mem> bank list projet            # Fichiers bank
live-mem> bank read projet file.md    # Lire un fichier
live-mem> bank consolidate projet     # 🧠 Consolider

live-mem> token list                  # Tokens
live-mem> backup list                 # Backups

live-mem> bank list projet --json     # Mode JSON
live-mem> quit                        # Quitter
```

---

---

## 🧪 Scripts de test

### Recette simple (1 agent)

```bash
# Test E2E complet via Docker Compose + WAF
docker compose up -d
python scripts/test_recette.py

# Garder l'espace pour inspection
python scripts/test_recette.py --no-cleanup

# Mode pas-à-pas (pause entre chaque étape)
python scripts/test_recette.py --step
```

Simule un agent sysadmin mettant à jour Ubuntu 22.04 → 24.04 :
token → espace → rules → 12 notes → consolidation LLM → 6 fichiers bank → cleanup

### Multi-agents (3 agents)

```bash
python scripts/test_multi_agents.py
python scripts/test_multi_agents.py --step --no-cleanup
```

3 agents collaborent : agent-infra (OS), agent-dev (apps), agent-qa (validation).
Chaque agent écrit ses notes et consolide indépendamment. La bank évolue progressivement.

### Garbage Collector

```bash
python scripts/test_gc.py
```

Crée des notes orphelines, teste le dry-run et la consolidation forcée GC.

---

## Architecture CLI

```
scripts/
├── mcp_cli.py              # Point d'entrée CLI Click
├── test_recette.py         # 🧪 Recette E2E (1 agent, 12 notes)
├── test_multi_agents.py    # 🧪 Multi-agents (3 agents collaborent)
├── test_gc.py              # 🧪 Test du Garbage Collector
├── README.md               # ← Vous êtes ici
└── cli/
    ├── __init__.py         # Config (BASE_URL, TOKEN)
    ├── client.py           # MCPClient HTTP/SSE + handshake MCP
    ├── commands.py         # Commandes Click (359 lignes)
    ├── display.py          # Affichage Rich (258 lignes)
    └── shell.py            # Shell interactif (307 lignes)
```

**Pattern** : Chaque commande appelle un outil MCP via `MCPClient.call_tool()` puis affiche le résultat via `display.py`. Les fonctions `show_xxx()` sont partagées entre CLI et Shell (DRY).

---

*Live Memory CLI v0.2.0*
