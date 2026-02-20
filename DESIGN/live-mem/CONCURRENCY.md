# Gestion de la Concurrence Multi-Agents — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

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
from collections import defaultdict
import asyncio

# Un lock par space_id pour la consolidation
_consolidation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

async def bank_consolidate(space_id: str) -> dict:
    lock = _consolidation_locks[space_id]
    
    if lock.locked():
        return {
            "status": "conflict",
            "message": f"Consolidation already in progress for space '{space_id}'"
        }
    
    async with lock:
        # ... pipeline de consolidation (peut durer 30-60s)
        result = await consolidator.consolidate(space_id)
        return result
```

**Comportement** :
- Si un agent demande une consolidation pendant qu'une autre est en cours → retour immédiat `"conflict"`
- L'agent peut réessayer plus tard
- Les deux espaces différents peuvent être consolidés en parallèle (locks indépendants)

---

### 2.3 Fichier tokens.json — ⚠️ CONFLIT POSSIBLE

Deux admins créant/modifiant des tokens simultanément pourraient écraser les modifications l'un de l'autre.

**Solution** : Un `asyncio.Lock` unique pour le fichier tokens.

```python
_tokens_lock = asyncio.Lock()

async def save_tokens(tokens_data: dict):
    async with _tokens_lock:
        content = json.dumps(tokens_data, indent=2)
        await storage.put("_system/tokens.json", content)

async def load_and_modify_tokens(modifier_fn):
    """Pattern read-modify-write atomique pour les tokens."""
    async with _tokens_lock:
        tokens_data = await storage.get_json("_system/tokens.json")
        modified = modifier_fn(tokens_data)
        await storage.put("_system/tokens.json", json.dumps(modified, indent=2))
        return modified
```

---

### 2.4 Fichier _meta.json — ⚠️ CONFLIT POSSIBLE

Mis à jour lors de la consolidation (compteurs). Protégé par le lock de consolidation (même section critique).

---

## 3. Matrice récapitulative

| Opération | Risque | Solution | Impact performance |
|---|---|---|---|
| `live_note` (N agents simultanés) | Aucun | Fichiers uniques (timestamp+UUID) | **Zéro** |
| `live_read` / `live_search` (lecture //) | Aucun | Lectures S3 parallèles | **Zéro** |
| `bank_read` / `bank_read_all` (lecture //) | Aucun | Lectures S3 parallèles | **Zéro** |
| `bank_consolidate` (2 agents, même espace) | Écrasement | `asyncio.Lock` par espace | Sérialisation (le 2ème reçoit "conflict") |
| `bank_consolidate` (2 agents, espaces différents) | Aucun | Locks indépendants | **Zéro** |
| `admin_create_token` (2 admins) | Écrasement tokens.json | `asyncio.Lock` unique tokens | Sérialisation (négligeable) |
| `backup_create` (même espace) | Lecture seule de l'espace | Aucun lock nécessaire (snapshot) | **Zéro** |

---

## 4. Pattern de lock utilisé

### 4.1 Locks en mémoire (asyncio.Lock)

Le serveur MCP est un **processus unique** (une seule instance Python). Toutes les requêtes passent par le même event loop asyncio. Les `asyncio.Lock` sont donc suffisants.

```python
import asyncio
from collections import defaultdict

class LockManager:
    """Gestionnaire centralisé des locks."""
    
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

# Singleton
_lock_manager = None

def get_lock_manager() -> LockManager:
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = LockManager()
    return _lock_manager
```

### 4.2 Pourquoi pas de locks S3 ?

S3 n'a pas de mécanisme de lock natif. Les alternatives (lock files, ETags conditionnels) ajoutent de la complexité pour un gain marginal dans notre cas :

- **Lock files S3** : Fragiles (si le serveur crash, le lock reste → deadlock)
- **ETags conditionnels** : Dell ECS ne supporte pas bien `If-Match` sur PUT (cf. problèmes SigV4)
- **DynamoDB locks** : Hors périmètre (pas de DynamoDB)

Le `asyncio.Lock` en mémoire est **suffisant** car :
1. Le serveur MCP est un processus unique
2. Pas de multi-instance (un seul container `mcp-service`)
3. Les opérations critiques sont courtes (< 1 minute sauf consolidation)

### 4.3 Cas multi-instance (futur)

Si live-mem devait tourner en multi-instance (load balancing), il faudrait :
- Redis pour les locks distribués (`redlock`)
- Ou un système de lease sur S3 (lock file avec TTL)
- Ou un routage par espace (chaque instance gère un sous-ensemble d'espaces)

Ce n'est **pas prévu** pour la v0.1.0.

---

## 5. Scénarios concrets

### Scénario 1 : 3 agents écrivent simultanément (nominal)

```
T+0s: Agent A → live_note("observation", "Build OK")      → PUT S3 : note_A.md ✅
T+0s: Agent B → live_note("decision", "On utilise FastAPI") → PUT S3 : note_B.md ✅
T+0s: Agent C → live_note("todo", "Écrire les tests")      → PUT S3 : note_C.md ✅
```

**Résultat** : 3 fichiers distincts, aucun conflit, aucun lock.

### Scénario 2 : 2 agents consolident en même temps

```
T+0s: Agent A → bank_consolidate("projet-alpha")
      → Lock acquis ✅, consolidation démarre (prend 30s)

T+5s: Agent B → bank_consolidate("projet-alpha")
      → Lock déjà pris → retour immédiat {"status": "conflict"} ⚡

T+30s: Agent A → consolidation terminée, lock relâché ✅
T+31s: Agent B → bank_consolidate("projet-alpha")
       → Lock acquis ✅, consolidation démarre
```

### Scénario 3 : Agent écrit pendant une consolidation

```
T+0s:  Agent A → bank_consolidate("projet-alpha")
       → Lock consolidation acquis, lit les notes live

T+5s:  Agent B → live_note("observation", "Nouveau fait")
       → PUT S3 : note_new.md ✅ (pas de lock nécessaire)
       → Cette note ne sera PAS incluse dans la consolidation en cours
       → Elle sera traitée à la PROCHAINE consolidation

T+30s: Agent A → consolidation terminée
       → Les notes existantes au T+0s sont supprimées
       → note_new.md reste dans live/ (elle est postérieure)
```

**⚠️ Point important** : La consolidation capture un snapshot des notes au moment où elle lit le live. Les notes arrivées après ne sont pas incluses et ne sont pas supprimées.

**Implémentation** :
```python
# Au début de la consolidation, noter les clés des notes lues
notes_keys = [note.key for note in live_notes]

# À la fin, ne supprimer que ces notes (pas les nouvelles)
for key in notes_keys:
    await storage.delete(key)
```

### Scénario 4 : 2 admins créent des tokens simultanément

```
T+0s: Admin A → admin_create_token("agent-1", "read,write")
      → _tokens_lock acquis, lecture tokens.json, ajout token, écriture

T+0s: Admin B → admin_create_token("agent-2", "read")
      → _tokens_lock bloqué, attente... (~50ms)

T+0.05s: Admin A → lock relâché
T+0.05s: Admin B → lock acquis, lecture tokens.json (contient agent-1), ajout agent-2, écriture
```

**Résultat** : Les deux tokens sont créés correctement, séquentiellement.

---

## 6. Performances

| Opération | Latence typique | Lock ? | Impact |
|---|---|---|---|
| `live_note` | 50-100ms (1 PUT S3) | Non | Aucun |
| `live_read` (50 notes) | 200-500ms (1 LIST + N GETs) | Non | Aucun |
| `bank_read_all` (6 fichiers) | 100-300ms (1 LIST + 6 GETs) | Non | Aucun |
| `bank_consolidate` | 20-60s (LLM + I/O S3) | Oui (par espace) | Bloque les autres consolidations du même espace |
| `admin_create_token` | 100-200ms (1 GET + 1 PUT S3) | Oui (tokens) | Sérialisation courte (~200ms) |

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
