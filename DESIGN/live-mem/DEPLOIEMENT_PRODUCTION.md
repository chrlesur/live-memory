# Guide de Déploiement Production — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

---

## 1. Vue d'ensemble

Live Memory est déployé via Docker Compose avec 2 services :

| Service         | Rôle                                    | Image          | Port interne |
| --------------- | --------------------------------------- | -------------- | ------------ |
| **WAF**         | Reverse proxy sécurisé (Caddy + Coraza) | Custom (build) | 8080         |
| **MCP Service** | Serveur MCP Python (24 outils)          | Custom (build) | 8002         |

**Différence avec graph-memory** : Pas de Neo4j ni Qdrant → déploiement beaucoup plus léger.

---

## 2. Prérequis

| Ressource | Minimum   | Recommandé |
| --------- | --------- | ---------- |
| CPU       | 1 vCPU    | 2 vCPU     |
| RAM       | 1 GB      | 2 GB       |
| Disque    | 10 GB SSD | 20 GB SSD  |

```bash
docker --version        # >= 24.0
docker compose version  # v2
```

---

## 3. Déploiement

### 3.1 Mode développement (HTTP, port 8080)

```bash
git clone https://github.com/chrlesur/live-mem.git
cd live-mem
cp .env.example .env
nano .env   # Remplir S3, LLMaaS, ADMIN_BOOTSTRAP_KEY

docker compose build
docker compose up -d
docker compose logs -f mcp-service
```

### 3.2 Mode production (HTTPS, Let's Encrypt)

```bash
# 1. DNS : live-mem.votre-domaine.com → IP serveur
# 2. .env : SITE_ADDRESS=live-mem.votre-domaine.com
# 3. docker-compose.yml : décommenter ports 80/443, commenter 8080
docker compose build && docker compose up -d
```

### 3.3 Vérifications post-déploiement

```bash
# Health check
curl -s http://localhost:8080/api/health | python3 -m json.tool

# WAF bloque injection SQL
curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080/api?id=1%20OR%201=1"
# Attendu : 403

# Créer le premier token admin
export MCP_URL=http://localhost:8080
export MCP_TOKEN=<votre_ADMIN_BOOTSTRAP_KEY>
python3 scripts/mcp_cli.py token create admin-ops admin
```

---

## 4. Docker Compose (pattern)

```yaml
services:
  waf:
    build: ./waf
    ports:
      - "${WAF_PORT:-8080}:8080"
      # Production : décommenter ces lignes, commenter celle du dessus
      # - "80:80"
      # - "443:443"
    environment:
      - SITE_ADDRESS=${SITE_ADDRESS:-:8080}
      - MCP_BACKEND=mcp-service:8002
    depends_on:
      mcp-service:
        condition: service_started
    restart: unless-stopped
    networks:
      - live-mem-network

  mcp-service:
    build: .
    env_file: .env
    expose:
      - "8002"   # Interne uniquement, pas exposé publiquement
    restart: unless-stopped
    networks:
      - live-mem-network

networks:
  live-mem-network:
    driver: bridge
```

**Principe clé** : Seul le WAF est exposé. Le service MCP est isolé dans le réseau Docker.

---

## 5. Backup & restauration

```bash
# Créer un backup
python3 scripts/mcp_cli.py backup create projet-alpha -d "Backup hebdomadaire"

# Lister les backups
python3 scripts/mcp_cli.py backup list

# Restaurer (l'espace NE DOIT PAS exister)
python3 scripts/mcp_cli.py space delete projet-alpha --confirm
python3 scripts/mcp_cli.py backup restore "projet-alpha/2026-02-20T18-00-00"
```

Backups stockés sur S3 : `_backups/{space_id}/{timestamp}/`
Rétention : les **5 derniers** par espace (configurable via `BACKUP_RETENTION_COUNT`).

---

## 6. Monitoring

```bash
# Logs service MCP
docker compose logs -f mcp-service

# Logs WAF (requêtes bloquées)
docker compose logs -f waf

# Health check
python3 scripts/mcp_cli.py health

# Stats espace
python3 scripts/mcp_cli.py space info projet-alpha
```

---

## 7. Mise à jour

```bash
git pull origin main
docker compose build
docker compose up -d
docker compose logs -f mcp-service --tail=50
```

> **⚠️** Les données sont sur S3, pas dans les containers. Un `docker compose down` est sans risque.

---

## 8. CLI distante

```bash
# Depuis n'importe quel poste
export MCP_URL=https://live-mem.votre-domaine.com
export MCP_TOKEN=votre_token_admin
python3 scripts/mcp_cli.py health
python3 scripts/mcp_cli.py space list
```

---

## 9. Commandes essentielles

```bash
# Déploiement
cp .env.example .env && nano .env
docker compose build && docker compose up -d

# Premier token
python3 scripts/mcp_cli.py token create admin-ops admin

# Créer un espace
python3 scripts/mcp_cli.py space create mon-projet --rules-file ./rules/standard.md

# Vérifier
python3 scripts/mcp_cli.py health
python3 scripts/mcp_cli.py space list
```

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
