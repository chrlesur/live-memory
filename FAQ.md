# ❓ FAQ — Live Memory

---

## Concepts généraux

### Quelle est la différence entre Live Memory et graph-memory ?

|                  | **Live Memory**                  | **graph-memory**                   |
| ---------------- | -------------------------------- | ---------------------------------- |
| **Type**         | Mémoire de travail               | Mémoire long terme                 |
| **Données**      | Notes live + bank Markdown       | Knowledge Graph + embeddings       |
| **Stockage**     | S3 (fichiers)                    | Neo4j + Qdrant                     |
| **Intelligence** | LLM consolide les notes en bank  | RAG vectoriel pour la recherche    |
| **Analogie**     | Tableau blanc → Cahier de projet | Bibliothèque → Moteur de recherche |

Les deux sont complémentaires. Live Memory est pour le travail quotidien, graph-memory pour la connaissance persistante.

### C'est quoi un "espace" (space) ?

Un espace mémoire isolé = un projet. Il contient :
- **Rules** : template Markdown qui définit la structure de la bank
- **Notes live** : observations, décisions, todos... des agents (append-only)
- **Bank** : fichiers Markdown consolidés par le LLM selon les rules

### C'est quoi les "rules" ?

Les rules définissent la structure de la Memory Bank. Elles sont écrites en Markdown à la création de l'espace et sont **immuables**. Le LLM les utilise pour créer et maintenir les fichiers bank.

Exemple de rules (standard Memory Bank) :
```markdown
### projectbrief.md
Objectifs, périmètre, critères de succès.

### activeContext.md
Focus actuel, changements récents, prochaines étapes.

### progress.md
Ce qui fonctionne, ce qui reste, problèmes connus.
```

---

## Agents et tokens

### Quelle différence entre un token et un agent ?

|                        | **Token**                         | **Agent**                          |
| ---------------------- | --------------------------------- | ---------------------------------- |
| **Rôle**               | Authentification (qui a le droit) | Identité (qui écrit)               |
| **Exemple**            | `lm_abc123...`                    | `"agent-cline"`                    |
| **Partageable ?**      | Oui, entre plusieurs agents       | Non, chaque agent a son nom        |
| **Où est-il fourni ?** | Header `Authorization: Bearer`    | Paramètre `agent=` dans les appels |

Un token `team-devops` peut être utilisé par `agent-alice` et `agent-bob`. Chaque agent fournit son nom dans `live_note(agent="alice")` et `bank_consolidate(agent="alice")`.

### Que se passe-t-il si je ne mets pas de paramètre agent= ?

Le serveur utilise le `client_name` du token comme fallback. Mais il est **recommandé** de toujours fournir `agent=` explicitement pour la traçabilité.

### Un agent peut-il lire les notes d'un autre agent ?

Oui ! `live_read(space_id="mon-projet")` retourne les notes de TOUS les agents. C'est le principe de la collaboration : chaque agent voit le travail des autres.

---

## Consolidation

### Comment fonctionne la consolidation ?

1. Le LLM (qwen3-2507:235b) lit les **rules**, la **bank actuelle**, la **synthèse précédente**, et les **notes live**
2. Il produit des fichiers bank mis à jour (Markdown pur)
3. Les notes consolidées sont **supprimées** de `live/`
4. Une synthèse résiduelle est sauvegardée

### Que se passe-t-il si 2 agents consolident en même temps ?

Un `asyncio.Lock` par espace empêche les consolidations simultanées :
- Le premier agent acquiert le lock → consolidation LLM (15-30s)
- Le second reçoit `{"status": "conflict"}` → doit réessayer

C'est voulu : les deux agents écrivent dans les mêmes fichiers bank. La consolidation séquentielle permet à chaque agent de voir le travail du précédent.

### Puis-je consolider les notes de TOUS les agents d'un coup ?

Oui ! `bank_consolidate(space_id="mon-projet")` sans paramètre `agent=` consolide toutes les notes de tous les agents en une seule fois.

⚠️ **Permissions** : consolider les notes d'un autre agent ou de tous les agents nécessite un token **admin**. Un token write ne peut consolider que ses propres notes (`agent="mon-nom"`).

### Que deviennent les notes après consolidation ?

Elles sont **supprimées** de `live/`. Leur contenu est intégré dans les fichiers bank. C'est irréversible (d'où l'intérêt des backups).

---

## Garbage Collector

### Pourquoi un Garbage Collector ?

Si un agent écrit des notes mais ne consolide jamais (crash, suppression, oubli), les notes s'accumulent sans fin dans `live/`. Le GC identifie et traite ces notes orphelines.

### Comment fonctionne le GC ?

3 modes via `admin_gc_notes` :

| Mode              | Paramètres                       | Action                                                                 |
| ----------------- | -------------------------------- | ---------------------------------------------------------------------- |
| **Dry-run**       | `confirm=False` (défaut)         | Scanne et rapporte                                                     |
| **Consolidation** | `confirm=True`                   | Consolide les notes dans la bank via LLM + ajoute une notice "⚠️ GC" |
| **Suppression**   | `confirm=True, delete_only=True` | Supprime sans consolider (perte de données)                            |

Par défaut, le GC **consolide** (ne supprime pas) pour ne pas perdre de données.

### Le GC laisse-t-il une trace dans la bank ?

Oui ! Le GC écrit une note spéciale avant chaque consolidation :
```
⚠️ GARBAGE COLLECTOR — Consolidation forcée
Le GC a détecté X notes orphelines de l'agent 'nom-agent' (> 7 jours).
Ces notes n'ont jamais été consolidées par l'agent.
```

Le LLM voit cette note et l'intègre dans la bank, assurant la traçabilité.

---

## Docker et déploiement

### Comment tester en local ?

```bash
# 1. Configurer l'environnement
cp .env.example .env
nano .env  # Remplir S3, LLMaaS, ADMIN_BOOTSTRAP_KEY

# 2. Lancer le stack
docker compose build
docker compose up -d

# 3. Tester
python scripts/test_recette.py           # Recette simple
python scripts/test_multi_agents.py      # Multi-agents
python scripts/test_gc.py                # Garbage Collector
```

### Comment fonctionne le WAF ?

Caddy + Coraza (OWASP CRS) protège contre les injections, XSS, etc. Les routes MCP (SSE + messages) passent **sans** WAF (authentifiées par token côté serveur). Les autres routes passent par le WAF.

### Pourquoi les routes SSE ne passent pas par le WAF ?

Coraza bufférise les réponses pour les inspecter, ce qui est **incompatible** avec le streaming SSE (connexions longues, flux continu). L'authentification est gérée côté serveur MCP.

### Comment déployer en production ?

1. Mettre `SITE_ADDRESS=mon-domaine.com` dans `.env`
2. Exposer les ports 80+443 dans docker-compose.yml
3. Caddy obtient automatiquement un certificat Let's Encrypt
4. Voir [DEPLOIEMENT_PRODUCTION.md](DESIGN/live-mem/DEPLOIEMENT_PRODUCTION.md) pour les détails

---

## S3 et stockage

### Pourquoi S3 et pas une base de données ?

- Simplicité : pas de schéma, pas de migrations, pas de serveur DB
- Portabilité : tout est fichier Markdown/JSON
- Scalabilité : S3 gère des milliards d'objets
- Coût : stockage S3 très bon marché

### Pourquoi deux clients S3 (SigV2 + SigV4) ?

Contrainte de Dell ECS (S3 Cloud Temple) :
- SigV2 pour les opérations de données (PUT, GET, DELETE)
- SigV4 pour les opérations de métadonnées (HEAD, LIST)

Si vous utilisez AWS S3 ou MinIO, un seul client SigV4 suffit.

### Puis-je utiliser AWS S3 ou MinIO ?

Oui ! Configurez `S3_ENDPOINT_URL` et les credentials. Le dual SigV2/V4 n'est nécessaire que pour Dell ECS. Pour les autres providers S3, modifiez `core/storage.py` pour utiliser un seul client.

---

## CLI et Shell

### Comment configurer la CLI ?

3 façons de passer l'URL et le token :

```bash
# 1. Variables d'environnement
export MCP_URL=http://localhost:8080
export MCP_TOKEN=lm_xxx
python scripts/mcp_cli.py health

# 2. Paramètres CLI
python scripts/mcp_cli.py --url http://mon-serveur:8080 --token lm_xxx health

# 3. Automatique (lit .env)
python scripts/mcp_cli.py health   # URL défaut 8080, token depuis .env
```

### Comment avoir l'aide sur une commande ?

```bash
# CLI Click (--help natif)
python scripts/mcp_cli.py space --help
python scripts/mcp_cli.py bank consolidate --help

# Shell interactif
live-mem> help           # aide globale
live-mem> help space     # sous-commandes de space
live-mem> space          # idem
live-mem> help bank      # sous-commandes de bank
```

### Puis-je utiliser la CLI en mode JSON pour le scripting ?

Oui ! Ajoutez `--json` (CLI) ou `--json` (shell) à n'importe quelle commande :

```bash
python scripts/mcp_cli.py space list --json | jq '.spaces[].space_id'
```

---

## Limites et performances

### Combien de notes peut-on écrire ?

Pas de limite théorique. Chaque note = 1 fichier S3 (~200-500 octets). La consolidation traite jusqu'à 500 notes à la fois (`CONSOLIDATION_MAX_NOTES`).

### Quelle est la latence ?

| Opération                     | Latence typique |
| ----------------------------- | --------------- |
| `live_note` (écriture)        | ~50ms           |
| `live_read` (lecture)         | ~100ms          |
| `bank_consolidate` (12 notes) | ~15-30s         |
| `bank_read_all` (6 fichiers)  | ~200ms          |
| `system_health`               | ~500ms          |

### Combien d'agents simultanés ?

Pas de limite sur le nombre d'agents écrivant en parallèle (append-only, zéro conflit). La consolidation est séquentielle par espace (1 à la fois).
