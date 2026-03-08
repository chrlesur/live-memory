# Gestion de la Concurrence Multi-Agents — Live Memory

> **Version** : 0.5.0 | **Date** : 2026-03-08 | **Auteur** : Cloud Temple

---

## 1. Problématique

Plusieurs agents IA peuvent interagir simultanément avec le même espace mémoire. Il faut garantir la cohérence des données sans bloquer les opérations courantes.

---

## 2. Analyse par type d'opération

### 2.1 Notes live — ✅ SANS CONFLIT (par design)

Chaque note = **un fichier S3 distinct** avec un nom unique (timestamp + agent + UUID) :

```
20260220T170001_cline-dev_observation_a1b2c3d4.md
20260220T170001_claude-rev_observation_e5f6a7b8.md  ← même seconde, agents différents
```

Deux agents écrivant au même instant créent deux fichiers différents → **zéro conflit**.

Le suffixe UUID8 (`uuid.uuid4().hex[:8]`) garantit l'unicité même si deux agents du même nom écrivent dans la même catégorie à la même seconde.

**Conclusion** : `live_note` ne nécessite aucun mécanisme de lock.

---

### 2.2 Fichiers bank — ⚠️ CONFLIT POSSIBLE

Seul `bank_consolidate` écrit dans la bank (les agents n'y écrivent jamais directement). Mais deux agents pourraient déclencher `bank_consolidate` en même temps.

**Solution** : Un `asyncio.Lock` **par espace** pour la consolidation.

```python
async def bank_consolidate(space_id: str, agent: str = "") -> dict:
    lock = get_lock_manager().consolidation(space_id)
    
    if lock.locked():
        return {
            "status": "conflict",
            "message": f"Consolidation already in progress for space '{space_id}'"
        }
    
    async with lock:
        return await get_consolidator().consolidate(space_id, agent=agent)
```

**Comportement** :
- Si un agent demande une consolidation pendant qu'une autre est en cours → retour immédiat `"conflict"`
- L'agent peut réessayer plus tard
- Deux espaces différents peuvent être consolidés en parallèle (locks indépendants)

---

### 2.3 Fichier tokens.json — ⚠️ CONFLIT POSSIBLE

Deux admins créant/modifiant des tokens simultanément pourraient écraser les modifications l'un de l'autre.

**Solution** : Un `asyncio.Lock` unique pour le fichier tokens.

```python
async with get_lock_manager().tokens:
    tokens_data = await storage.get_json("_system/tokens.json")
    modified = modifier_fn(tokens_data)
    await storage.put_json("_system/tokens.json", modified)
```

---

### 2.4 Fichier _meta.json — ⚠️ CONFLIT POSSIBLE

Mis à jour lors de la consolidation et du `graph_push`. Protégé par le lock de consolidation pour les consolidations. Les opérations graph utilisent une lecture-modification-écriture séquentielle.

---

## 3. Matrice récapitulative

| Opération | Risque | Solution | Impact performance |
|---|---|---|---|
| `live_note` (N agents simultanés) | Aucun | Fichiers uniques (timestamp+UUID) | **Zéro** |
| `live_read` / `live_search` (lecture //) | Aucun | Lectures S3 parallèles | **Zéro** |
| `bank_read` / `bank_read_all` (lecture //) | Aucun | Lectures S3 parallèles | **Zéro** |
| `bank_consolidate` (2 agents, même espace) | Écrasement | `asyncio.Lock` par espace | Le 2ème reçoit "conflict" |
| `bank_consolidate` (2 agents, espaces différents) | Aucun | Locks indépendants | **Zéro** |
| `admin_create_token` (2 admins) | Écrasement tokens.json | `asyncio.Lock` unique tokens | Sérialisation (~200ms) |
| `graph_connect` / `graph_push` | MAJ _meta.json | Séquentiel (opérations longues) | **Zéro** |
| `backup_create` (même espace) | Lecture seule de l'espace | Aucun lock nécessaire (snapshot) | **Zéro** |

---

## 4. Pattern de lock utilisé

### 4.1 Locks en mémoire (asyncio.Lock)

Le serveur MCP est un **processus unique** (une seule instance Python). Toutes les requêtes passent par le même event loop asyncio. Les `asyncio.Lock` sont donc suffisants.

```python
class LockManager:
    """Gestionnaire centralisé des locks asyncio."""
    
    def __init__(self):
        self._consolidation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tokens_lock = asyncio.Lock()
    
    def consolidation(self, space_id: str) -> asyncio.Lock:
        """Lock par espace pour la consolidation."""
        return self._consolidation_locks[space_id]
    
    @property
    def tokens(self) -> asyncio.Lock:
        """Lock unique pour tokens.json."""
        return self._tokens_lock
```

### 4.2 Pourquoi pas de locks S3 ?

S3 n'a pas de mécanisme de lock natif. Les alternatives ajoutent de la complexité pour un gain marginal :

- **Lock files S3** : Fragiles (si le serveur crash, le lock reste → deadlock)
- **ETags conditionnels** : Dell ECS ne supporte pas bien `If-Match` sur PUT
- **DynamoDB locks** : Hors périmètre

Le `asyncio.Lock` en mémoire est **suffisant** car :
1. Le serveur MCP est un processus unique
2. Pas de multi-instance (un seul container `mcp-service`)
3. Les opérations critiques sont courtes (< 1 minute sauf consolidation)

### 4.3 Cas multi-instance (futur)

Si live-mem devait tourner en multi-instance (load balancing), il faudrait :
- Redis pour les locks distribués (`redlock`)
- Ou un système de lease sur S3 (lock file avec TTL)
- Ou un routage par espace (chaque instance gère un sous-ensemble d'espaces)

Ce n'est **pas prévu** pour la v0.5.0.

---

## 5. Scénarios concrets

### Scénario 1 : 3 agents écrivent simultanément (nominal)

```
T+0s: Agent A → live_note("observation", "Build OK")      → PUT S3 : note_A.md ✅
T+0s: Agent B → live_note("decision", "On utilise FastAPI") → PUT S3 : note_B.md ✅
T+0s: Agent C → live_note("todo", "Écrire les tests")      → PUT S3 : note_C.md ✅
```

3 fichiers distincts, aucun conflit, aucun lock.

### Scénario 2 : 2 agents consolident en même temps

```
T+0s:  Agent A → bank_consolidate("projet-alpha", agent="agent-A")
       → Lock acquis ✅, consolidation démarre (prend 30s)

T+5s:  Agent B → bank_consolidate("projet-alpha", agent="agent-B")
       → Lock déjà pris → retour immédiat {"status": "conflict"} ⚡

T+30s: Agent A → consolidation terminée, lock relâché ✅
T+31s: Agent B → bank_consolidate("projet-alpha", agent="agent-B")
       → Lock acquis ✅, consolidation démarre
```

### Scénario 3 : Agent écrit pendant une consolidation

```
T+0s:  Agent A → bank_consolidate("projet-alpha", agent="agent-A")
       → Lock acquis, lit les notes live de agent-A

T+5s:  Agent B → live_note("observation", "Nouveau fait")
       → PUT S3 : note_new.md ✅ (pas de lock nécessaire)
       → Cette note ne sera PAS incluse dans la consolidation en cours
       → Elle sera traitée à la PROCHAINE consolidation

T+30s: Agent A → consolidation terminée
       → Seules les notes de agent-A collectées au T+0 sont supprimées
       → note_new.md (agent-B) reste dans live/
```

### Scénario 4 : Graph push pendant une consolidation

```
T+0s:  Agent A → bank_consolidate("projet-alpha")
       → Lock consolidation acquis

T+5s:  Agent B → graph_push("projet-alpha")
       → Pas de lock nécessaire (lecture seule de la bank + appel MCP Streamable HTTP)
       → Pousse la bank dans son état actuel (pas celle en cours de mise à jour)
```

---

## 6. Performances

| Opération | Latence typique | Lock ? | Impact |
|---|---|---|---|
| `live_note` | 50-100ms (1 PUT S3) | Non | Aucun |
| `live_read` (50 notes) | 200-500ms (1 LIST + N GETs) | Non | Aucun |
| `bank_read_all` (6 fichiers) | 100-300ms (1 LIST + 6 GETs) | Non | Aucun |
| `bank_consolidate` | 20-60s (LLM + I/O S3) | Oui (par espace) | Bloque les autres conso du même espace |
| `graph_push` (6 fichiers) | 60-180s (MCP Streamable HTTP) | Non | Aucun |
| `admin_create_token` | 100-200ms (1 GET + 1 PUT S3) | Oui (tokens) | Sérialisation courte |

---

*Document mis à jour le 8 mars 2026 — Live Memory v0.5.0*
