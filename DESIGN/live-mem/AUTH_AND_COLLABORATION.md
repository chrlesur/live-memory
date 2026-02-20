# Authentification & Collaboration Multi-Agents — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

---

## 1. Modèle d'authentification

### 1.1 Architecture

```
Agent (Cline, Claude, etc.)
    │
    │  Authorization: Bearer lm_a1b2c3d4e5f6...
    │
    ▼
┌────────────────────────────────────┐
│  Auth Middleware (ASGI)             │
│                                     │
│  1. Extrait le token du header      │
│  2. Hash SHA-256 du token           │
│  3. Cherche le hash dans tokens.json│
│  4. Vérifie : non-révoqué,          │
│     non-expiré, permissions OK,     │
│     space_id autorisé               │
│  5. Stocke l'identité dans          │
│     contextvars (pour les outils)   │
└────────────────────────────────────┘
```

### 1.2 Types de tokens

| Type       | Permissions          | Usage                   | Exemples d'outils                                 |
| ---------- | -------------------- | ----------------------- | ------------------------------------------------- |
| **Reader** | `read`               | Consultation seule      | `bank_read_all`, `live_read`, `space_list`        |
| **Writer** | `read, write`        | Consultation + écriture | + `live_note`, `bank_consolidate`, `space_create` |
| **Admin**  | `read, write, admin` | Tout                    | + `admin_*`, `space_delete`, `backup_restore`     |

### 1.3 Bootstrap Key

Au premier démarrage, seule la `ADMIN_BOOTSTRAP_KEY` (variable d'environnement) permet de s'authentifier. Elle sert à créer le premier token admin, après quoi elle ne devrait plus être utilisée.

```
Démarrage → ADMIN_BOOTSTRAP_KEY → admin_create_token → Token admin
                                                         │
                                                         ▼
                                              admin_create_token → Tokens agents
```

### 1.4 Space Access Control

Chaque token a une liste `space_ids` :
- `[]` (vide) = accès à **tous** les espaces
- `["projet-alpha", "projet-beta"]` = accès restreint à ces espaces

Quand un outil reçoit un `space_id`, le middleware vérifie :

```python
def check_access(space_id: str) -> Optional[dict]:
    """Vérifie si le token courant peut accéder à cet espace."""
    token_info = get_current_token()
    
    # Bootstrap key ou token admin sans restriction
    if not token_info.get("space_ids"):
        return None  # OK, pas de restriction
    
    # Token restreint : vérifier que space_id est autorisé
    if space_id not in token_info["space_ids"]:
        return {"status": "forbidden", "message": f"Access denied to space '{space_id}'"}
    
    return None  # OK
```

### 1.5 Stockage des tokens

Les tokens sont stockés dans `_system/tokens.json` sur S3 (voir `S3_DATA_MODEL.md`).

**Format du token** : `lm_` + 43 caractères base64url = **46 caractères** totaux.

```python
import secrets
token = "lm_" + secrets.token_urlsafe(32)
# Ex: lm_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2
```

**Hashage** : SHA-256 du token complet.

```python
import hashlib
token_hash = "sha256:" + hashlib.sha256(token.encode()).hexdigest()
# Ex: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

---

## 2. Collaboration Multi-Agents

### 2.1 Scénarios de collaboration

#### Scénario A : Équipe de développement (2-3 agents)

```
┌──────────────┐     ┌───────────────┐     ┌──────────────┐
│ Cline (Dev)  │     │Claude (Review)│     │ Agent QA     │
│ Token: write │     │ Token: write  │     │ Token: write │
└──────┬───────┘     └──────┬────────┘     └──────┬───────┘
       │                    │                     │
       ▼                    ▼                     ▼
    live_note            live_note             live_note
    (observation,        (insight,             (issue,
     decision,           question)              progress)
     todo)
       │                    │                     │
       └────────────────────┼─────────────────────┘
                            │
                            ▼
                    ┌─────────────────┐
                    │ Espace partagé  │
                    │ "projet-alpha"  │
                    │                 │
                    │ live/ (toutes   │
                    │  les notes)     │
                    │                 │
                    │ bank/ (consolidé│
                    │  par le LLM)    │
                    └─────────────────┘
```

Chaque agent :
1. Au démarrage : `bank_read_all("projet-alpha")` pour charger le contexte
2. Pendant le travail : `live_note(...)` pour écrire ses observations
3. Périodiquement : `live_read(agent="claude-review")` pour voir ce que font les autres
4. En fin de session : `bank_consolidate("projet-alpha")` pour synthétiser

#### Scénario B : Un agent, plusieurs projets

```
Agent Cline (Token: write, space_ids: ["front", "back", "infra"])
    │
    ├── live_note("front", "observation", "Le composant React est OK")
    ├── live_note("back", "decision", "On utilise FastAPI")
    └── live_note("infra", "todo", "Configurer le CI/CD")
```

#### Scénario C : Agents spécialisés avec droits différents

```
┌────────────────────┐     ┌────────────────────┐
│ Agent Dev          │     │ Agent Monitoring   │
│ Token: read,write  │     │ Token: read        │
│ Spaces: ["prod"]   │     │ Spaces: ["prod"]   │
│                    │     │                    │
│ ✅ live_note       │     │ ❌ live_note       │
│ ✅ bank_consolidate│     │ ❌ bank_consolidate│
│ ✅ bank_read_all   │     │ ✅ bank_read_all   │
└────────────────────┘     └────────────────────┘
```

### 2.2 Patterns de communication inter-agents

Les agents ne communiquent pas directement entre eux. Ils communiquent **via l'espace partagé** :

```
Agent A → live_note(category="question", "Faut-il supporter le CSV ?")
                                            │
                                            ▼
                                        S3 (note)
                                            │
Agent B → live_read(category="question") ←──┘
Agent B → live_note(category="decision", "Non, JSON uniquement")
```

### 2.3 Bonnes pratiques pour la collaboration

| Practice                     | Description                                                          |
| ---------------------------- | -------------------------------------------------------------------- |
| **Identifier l'agent**       | Toujours passer `agent="nom-agent"` dans `live_note`                 |
| **Catégoriser les notes**    | Utiliser les catégories standard (observation, decision, todo, etc.) |
| **Taguer**                   | Ajouter des tags pour le filtrage (`tags="auth,module"`)             |
| **Lire avant d'écrire**      | `bank_read_all` au démarrage, `live_read` régulièrement              |
| **Consolider régulièrement** | Ne pas attendre 500 notes — consolider toutes les 20-50 notes        |
| **Notes atomiques**          | Une note = un fait, une décision, un todo. Pas de notes méga-longues |

### 2.4 Configuration recommandée pour un projet multi-agents

```bash
# 1. Créer le token admin
export MCP_TOKEN=$ADMIN_BOOTSTRAP_KEY
python3 scripts/mcp_cli.py token create admin-ops admin

# 2. Créer l'espace avec les rules standard
export MCP_TOKEN=<admin_token>
python3 scripts/mcp_cli.py space create projet-alpha \
  --rules-file ./rules/standard-memory-bank.md \
  --description "Refonte API v3" \
  --owner "equipe-dev"

# 3. Créer les tokens agents
python3 scripts/mcp_cli.py token create agent-cline read,write projet-alpha
python3 scripts/mcp_cli.py token create agent-claude read,write projet-alpha
python3 scripts/mcp_cli.py token create monitoring read projet-alpha
```

---

## 3. Matrice des permissions détaillée

### Par catégorie d'outil

| Outil              | Perm min | Check access         | Check write | Notes                                 |
| ------------------ | -------- | -------------------- | ----------- | ------------------------------------- |
| **Space**          |          |                      |             |                                       |
| `space_create`     | write    | —                    | ✅          | Crée un nouvel espace                 |
| `space_list`       | read     | filtre par space_ids | —           | Ne montre que les espaces autorisés   |
| `space_info`       | read     | ✅                   | —           |                                       |
| `space_rules`      | read     | ✅                   | —           |                                       |
| `space_summary`    | read     | ✅                   | —           |                                       |
| `space_export`     | read     | ✅                   | —           | Peut exporter car lecture seule       |
| `space_delete`     | admin    | ✅                   | —           | Irréversible                          |
| **Live**           |          |                      |             |                                       |
| `live_note`        | write    | ✅                   | ✅          | Écriture                              |
| `live_read`        | read     | ✅                   | —           | Lecture                               |
| `live_search`      | read     | ✅                   | —           | Lecture                               |
| **Bank**           |          |                      |             |                                       |
| `bank_read`        | read     | ✅                   | —           | Lecture                               |
| `bank_read_all`    | read     | ✅                   | —           | Lecture                               |
| `bank_list`        | read     | ✅                   | —           | Lecture                               |
| `bank_consolidate` | write    | ✅                   | ✅          | Déclenche le LLM                      |
| **Backup**         |          |                      |             |                                       |
| `backup_create`    | write    | ✅                   | ✅          | Crée un snapshot                      |
| `backup_list`      | read     | filtre               | —           | Ne montre que les backups accessibles |
| `backup_restore`   | admin    | ✅                   | —           | Potentiellement destructif            |
| `backup_download`  | read     | ✅                   | —           | Lecture                               |
| `backup_delete`    | admin    | ✅                   | —           | Irréversible                          |
| **Admin**          |          |                      |             |                                       |
| `admin_*`          | admin    | —                    | —           | Gestion tokens (transversal)          |
| **System**         |          |                      |             |                                       |
| `system_*`         | public   | —                    | —           | Pas d'auth                            |

### Résumé : qui peut faire quoi

| Action                   | Reader | Writer | Admin |
| ------------------------ | :----: | :----: | :---: |
| Lire la bank             |   ✅   |   ✅   |  ✅   |
| Lire les notes live      |   ✅   |   ✅   |  ✅   |
| Écrire des notes         |   ❌   |   ✅   |  ✅   |
| Déclencher consolidation |   ❌   |   ✅   |  ✅   |
| Créer un espace          |   ❌   |   ✅   |  ✅   |
| Supprimer un espace      |   ❌   |   ❌   |  ✅   |
| Créer un backup          |   ❌   |   ✅   |  ✅   |
| Restaurer un backup      |   ❌   |   ❌   |  ✅   |
| Gérer les tokens         |   ❌   |   ❌   |  ✅   |

---

## 4. Sécurité

### 4.1 Vérification dans chaque outil

Pattern standard en tête de chaque outil :

```python
@mcp.tool()
async def live_note(space_id: str, category: str, content: str, ...) -> dict:
    try:
        # 1. Vérifier l'accès à l'espace
        access_err = check_access(space_id)
        if access_err:
            return access_err
        
        # 2. Vérifier la permission write
        write_err = check_write_permission()
        if write_err:
            return write_err
        
        # 3. Logique métier...
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

### 4.2 Logging d'audit

Chaque action authentifiée est loguée sur `stderr` :

```
🔑 [Auth] Token 'agent-cline' (sha256:a1b2...first8) → live_note on 'projet-alpha'
🔑 [Auth] Token 'monitoring' (sha256:f7e8...first8) → bank_read_all on 'projet-alpha'
⛔ [Auth] Token 'monitoring' (sha256:f7e8...first8) → DENIED live_note (write required)
```

### 4.3 Recommandations

| Recommandation                                                      | Priorité           |
| ------------------------------------------------------------------- | ------------------ |
| Changer `ADMIN_BOOTSTRAP_KEY` en production (≥ 32 chars aléatoires) | 🔴 Critique       |
| TLS en production (HTTPS via Let's Encrypt)                         | 🔴 Critique       |
| Tokens agents restreints par `space_ids`                            | 🟠 Élevée         |
| Tokens reader pour les agents en lecture seule                      | 🟡 Moyenne        |
| Rotation périodique des tokens                                      | 🟡 Moyenne        |
| Expiration automatique des tokens (`expires_in_days`)               | 🟢 Bonne pratique |

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
