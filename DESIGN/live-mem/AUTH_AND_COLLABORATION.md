# Authentification & Collaboration Multi-Agents — Live Memory

> **Version** : 0.4.0 | **Date** : 2026-03-03 | **Auteur** : Cloud Temple

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
│     (ou query string ?token=xxx)    │
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
| **Writer** | `read, write`        | Consultation + écriture | + `live_note`, `bank_consolidate`, `space_create`, `graph_push` |
| **Admin**  | `read, write, admin` | Tout                    | + `admin_*`, `space_delete`, `backup_restore`, `admin_gc_notes` |

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

Quand un outil reçoit un `space_id`, le helper `check_access()` vérifie :

```python
def check_access(resource_id: str) -> Optional[dict]:
    """Vérifie si le token courant peut accéder à cet espace."""
    token_info = current_token_info.get()
    
    if token_info is None:
        return {"status": "error", "message": "Authentification requise"}
    
    # Admin → accès total
    if "admin" in token_info.get("permissions", []):
        return None
    
    # Vérifier que l'espace est dans la liste autorisée
    allowed = token_info.get("allowed_resources", [])
    if allowed and resource_id not in allowed:
        return {"status": "error", "message": f"Accès refusé à l'espace '{resource_id}'"}
    
    return None  # OK
```

### 1.5 Découplage Token / Agent (v0.2.0+)

Le token est pour **l'authentification**, le nom d'agent est **explicite** :

- `live_note(agent="cline-dev")` : le paramètre `agent` identifie l'auteur de la note, indépendamment du token utilisé
- `bank_consolidate(agent="cline-dev")` : consolide uniquement les notes de cet agent
- Un même token peut être partagé entre plusieurs agents
- `get_current_agent_name()` retourne le `client_name` du token comme fallback

### 1.6 Stockage des tokens

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
4. En fin de session : `bank_consolidate("projet-alpha", agent="mon-nom")` pour synthétiser ses propres notes

#### Scénario B : Consolidation par agent (v0.2.0+)

```
Agent Cline écrit 20 notes → bank_consolidate(agent="cline-dev")
    → Seules les notes de cline-dev sont consolidées
    → Les notes de claude-review restent dans live/
    → Permission write suffit

Agent Claude écrit 15 notes → bank_consolidate(agent="claude-review")
    → Seules les notes de claude-review sont consolidées
    → Permission write suffit

Admin → bank_consolidate(agent="")
    → TOUTES les notes sont consolidées
    → Permission admin requise
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
| **Consolider ses notes**     | `bank_consolidate(agent="mon-nom")` — chaque agent consolide les siennes |
| **Notes atomiques**          | Une note = un fait, une décision, un todo. Pas de notes méga-longues |
| **GC périodique**            | `admin_gc_notes` pour nettoyer les notes d'agents disparus           |

---

## 3. Matrice des permissions détaillée

### Par catégorie d'outil

| Outil              | Perm min | Check access | Notes                                 |
| ------------------ | -------- | ------------ | ------------------------------------- |
| **Space**          |          |              |                                       |
| `space_create`     | write    | —            | Crée un nouvel espace                 |
| `space_list`       | read     | filtre       | Ne montre que les espaces autorisés   |
| `space_info`       | read     | ✅           |                                       |
| `space_rules`      | read     | ✅           |                                       |
| `space_summary`    | read     | ✅           |                                       |
| `space_export`     | read     | ✅           |                                       |
| `space_delete`     | admin    | ✅           | Irréversible                          |
| **Live**           |          |              |                                       |
| `live_note`        | write    | ✅           | Écriture                              |
| `live_read`        | read     | ✅           | Lecture                               |
| `live_search`      | read     | ✅           | Lecture                               |
| **Bank**           |          |              |                                       |
| `bank_read`        | read     | ✅           | Lecture                               |
| `bank_read_all`    | read     | ✅           | Lecture                               |
| `bank_list`        | read     | ✅           | Lecture                               |
| `bank_consolidate` | write*   | ✅           | *admin si agent="" ou agent≠caller    |
| **Graph**          |          |              |                                       |
| `graph_connect`    | write    | ✅           | Configure la connexion Graph Memory   |
| `graph_push`       | write    | ✅           | Pousse la bank dans le graphe         |
| `graph_status`     | read     | ✅           | Statut connexion + stats graphe       |
| `graph_disconnect` | write    | ✅           | Supprime la config de connexion       |
| **Backup**         |          |              |                                       |
| `backup_create`    | write    | ✅           | Crée un snapshot                      |
| `backup_list`      | read     | filtre       | Ne montre que les backups accessibles |
| `backup_restore`   | admin    | ✅           | Potentiellement destructif            |
| `backup_download`  | read     | ✅           | Lecture                               |
| `backup_delete`    | admin    | ✅           | Irréversible                          |
| **Admin**          |          |              |                                       |
| `admin_create_token` | admin  | —            | Gestion tokens                        |
| `admin_list_tokens`  | admin  | —            | Gestion tokens                        |
| `admin_revoke_token` | admin  | —            | Gestion tokens                        |
| `admin_update_token` | admin  | —            | Gestion tokens                        |
| `admin_gc_notes`     | admin  | —            | Maintenance (GC notes orphelines)     |
| **System**         |          |              |                                       |
| `system_health`    | public   | —            | Pas d'auth                            |
| `system_about`     | public   | —            | Pas d'auth                            |

### Résumé : qui peut faire quoi

| Action                         | Reader | Writer | Admin |
| ------------------------------ | :----: | :----: | :---: |
| Lire la bank                   |   ✅   |   ✅   |  ✅   |
| Lire les notes live            |   ✅   |   ✅   |  ✅   |
| Écrire des notes               |   ❌   |   ✅   |  ✅   |
| Consolider ses propres notes   |   ❌   |   ✅   |  ✅   |
| Consolider toutes les notes    |   ❌   |   ❌   |  ✅   |
| Créer un espace                |   ❌   |   ✅   |  ✅   |
| Supprimer un espace            |   ❌   |   ❌   |  ✅   |
| Connecter/pousser Graph Memory |   ❌   |   ✅   |  ✅   |
| Voir le statut Graph Memory    |   ✅   |   ✅   |  ✅   |
| Créer un backup                |   ❌   |   ✅   |  ✅   |
| Restaurer un backup            |   ❌   |   ❌   |  ✅   |
| Gérer les tokens               |   ❌   |   ❌   |  ✅   |
| GC notes orphelines            |   ❌   |   ❌   |  ✅   |

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

### 4.2 Helpers d'authentification (auth/context.py)

4 fonctions basées sur `contextvars` :
- `check_access(resource_id)` — vérifie l'accès à un espace
- `check_write_permission()` — vérifie la permission write
- `check_admin_permission()` — vérifie la permission admin
- `get_current_agent_name()` — retourne le nom de l'agent (client_name du token, ou "anonymous")

### 4.3 Logging d'audit

Chaque requête HTTP est loguée sur `stderr` via `LoggingMiddleware` :

```
19:05:12 INFO  [live_mem.auth] GET /mcp → 200 (45.2ms)
19:05:15 INFO  [live_mem.auth] POST /mcp → 200 (120.5ms)
```

### 4.4 Recommandations

| Recommandation                                                      | Priorité           |
| ------------------------------------------------------------------- | ------------------ |
| Changer `ADMIN_BOOTSTRAP_KEY` en production (≥ 32 chars aléatoires) | 🔴 Critique       |
| TLS en production (HTTPS via Let's Encrypt)                         | 🔴 Critique       |
| Tokens agents restreints par `space_ids`                            | 🟠 Élevée         |
| Tokens reader pour les agents en lecture seule                      | 🟡 Moyenne        |
| Rotation périodique des tokens                                      | 🟡 Moyenne        |
| Expiration automatique des tokens (`expires_in_days`)               | 🟢 Bonne pratique |
| GC notes régulier (`admin_gc_notes`)                                | 🟢 Bonne pratique |

---

*Document mis à jour le 3 mars 2026 — Live Memory v0.4.0*
