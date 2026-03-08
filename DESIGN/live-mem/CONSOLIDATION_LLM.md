# Pipeline de Consolidation LLM — Live Memory

> **Version** : 0.5.0 | **Date** : 2026-03-08 | **Auteur** : Cloud Temple

---

## 1. Vue d'ensemble

La consolidation est le **cœur intelligent** de live-mem. C'est le processus par lequel le MCP utilise un LLM pour synthétiser les notes live en fichiers bank structurés, puis nettoie le live.

```
AVANT                                    APRÈS
─────                                    ─────
live/                                    live/
├── note_001.md (agent-A, observation)   ├── note_010.md (agent-B, todo)
├── note_002.md (agent-A, decision)      └── note_011.md (agent-B, insight)
├── note_003.md (agent-A, todo)              ↑ Notes d'agent-B non touchées
├── ... (42 notes agent-A)
├── note_010.md (agent-B, todo)          bank/
└── note_011.md (agent-B, insight)       ├── projectbrief.md    (créé/MAJ)
                                         ├── activeContext.md   (MAJ)
bank/                                    ├── progress.md        (MAJ)
├── projectbrief.md (existant)           ├── systemPatterns.md  (MAJ)
├── activeContext.md (existant)          ├── techContext.md      (inchangé)
├── progress.md (existant)               └── productContext.md  (inchangé)
├── systemPatterns.md (existant)
├── techContext.md (existant)            _synthesis.md          (écrasé)
└── productContext.md (existant)

_synthesis.md (précédent)
```

**Principes fondamentaux** :
- Les agents n'écrivent JAMAIS dans la bank. Seul le LLM le fait, guidé par les rules
- Chaque agent consolide **ses propres notes** (paramètre `agent`)
- Les notes des autres agents restent intactes dans le live

---

## 2. Paramètre `agent` (v0.2.0+)

Le paramètre `agent` de `bank_consolidate` contrôle le filtrage des notes :

| Valeur | Comportement | Permission |
|--------|-------------|------------|
| `agent=""` (vide) | Consolide **TOUTES** les notes | Admin requis |
| `agent="cline-dev"` (= caller) | Consolide uniquement les notes de cet agent | Write suffit |
| `agent="autre"` (≠ caller) | Consolide les notes d'un autre agent | Admin requis |

Le filtrage se fait sur le nom de fichier : `{ts}_{agent}_{cat}_{uuid}.md` — on cherche `_{agent}_` dans le filename.

---

## 3. Pipeline détaillé

### Étape 1 — Collecte des inputs

```python
async def _collect_inputs(self, space_id: str, agent: str = "") -> dict:
    # 1a. Lire les rules (immuables)
    rules = await storage.get("{space_id}/_rules.md")

    # 1b. Lire la synthèse précédente (contexte cumulatif)
    synthesis = await storage.get("{space_id}/_synthesis.md")

    # 1c. Lire les notes live
    notes_raw = await storage.list_and_get("{space_id}/live/")
    notes_raw.sort(key=lambda n: n["key"])  # Tri chronologique

    # 1d. Filtrer par agent si spécifié
    if agent:
        notes_raw = [n for n in notes_raw if f"_{agent}_" in n["key"].split("/")[-1]]

    # 1e. Limiter au max_notes (les plus anciennes d'abord)
    if len(notes_raw) > self._max_notes:
        notes_raw = notes_raw[:self._max_notes]

    # 1f. Garder les clés pour suppression ultérieure
    notes_keys = [n["key"] for n in notes_raw]

    # 1g. Lire TOUS les fichiers bank actuels
    bank_files = await storage.list_and_get("{space_id}/bank/")
```

### Étape 2 — Construire le prompt LLM

Le prompt est en **une seule requête** car on exploite la fenêtre de 100K tokens de qwen3-2507:235b.

**Budget tokens estimé** :

| Composant | Tokens estimés |
|---|---|
| Prompt système | ~500 |
| Rules | ~500-2000 |
| Synthèse précédente | ~500-1500 |
| Notes live (42 notes × ~200 tokens) | ~8400 |
| Fichiers bank existants (6 × ~1000 tokens) | ~6000 |
| **Total input** | **~17K tokens** |
| Marge pour la réponse | ~80K tokens |

### Étape 3 — Appel LLM

Un **seul appel** LLM pour toute la consolidation.

```python
response = await self._client.chat.completions.create(
    model=self._model,           # qwen3-2507:235b
    messages=messages,
    max_tokens=self._max_tokens, # 100000
    temperature=self._temperature, # 0.3
    # Note: response_format non utilisé (pas supporté par tous les endpoints)
    # Le JSON est parsé manuellement depuis la réponse
)
```

### Étape 4 — Extraction JSON robuste

La réponse LLM peut contenir du JSON de plusieurs façons :

```python
def _extract_json(text: str) -> str:
    # 1. Retirer les blocs <think>...</think> (Qwen thinking mode)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # 2. Chercher un bloc ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match: return match.group(1).strip()

    # 3. Chercher un bloc ``` ... ``` commençant par {
    # 4. Chercher le premier { ... } (JSON brut)
    # 5. Fallback : retourner le texte tel quel
```

### Étape 5 — Écriture des résultats

```python
# 5a. Écrire chaque fichier bank mis à jour
for file_entry in llm_output["bank_files"]:
    await storage.put(f"{space_id}/bank/{filename}", content)

# 5b. Écrire la synthèse résiduelle (avec front-matter)
await storage.put(f"{space_id}/_synthesis.md", synthesis_md)

# 5c. Mettre à jour _meta.json (compteurs)
meta["last_consolidation"] = now
meta["consolidation_count"] += 1
meta["total_notes_processed"] += notes_count
await storage.put_json(f"{space_id}/_meta.json", meta)

# 5d. Supprimer les notes live traitées (EN DERNIER — atomicité)
await storage.delete_many(notes_keys)
```

**Point clé** : seules les notes collectées à l'étape 1 sont supprimées. Les notes arrivées pendant la consolidation restent dans live/ pour la prochaine consolidation.

---

## 4. Prompts

### 4.1 Prompt système

```
Tu es un assistant spécialisé dans la maintenance de Memory Banks pour des projets.

Ta mission : synthétiser des notes de travail en fichiers structurés selon des règles précises.

Tu reçois :
1. Les RULES qui définissent la structure de la memory bank
2. La SYNTHÈSE PRÉCÉDENTE (contexte des consolidations antérieures)
3. Les NOTES LIVE nouvelles à intégrer
4. Les FICHIERS BANK actuels à mettre à jour

Tu dois retourner un JSON avec :
- "bank_files" : liste des fichiers bank mis à jour ou créés
- "synthesis" : synthèse résiduelle des notes traitées

Règles :
- Respecte STRICTEMENT la structure définie dans les rules
- Intègre les nouvelles informations des notes live
- Conserve les informations existantes qui sont toujours pertinentes
- Supprime les informations rendues obsolètes par les nouvelles notes
- Chaque fichier bank doit être en Markdown pur (pas de front-matter)
- La synthèse doit être concise mais couvrir les points clés
- Si un fichier bank n'a pas besoin de modification, NE L'INCLUS PAS dans bank_files
```

### 4.2 Prompt utilisateur (consolidation)

```
=== RULES DE L'ESPACE "{space_id}" ===
{contenu de _rules.md}

=== SYNTHÈSE PRÉCÉDENTE ===
{contenu de _synthesis.md, ou "Aucune — première consolidation"}

=== NOTES LIVE À INTÉGRER ({count} notes) ===

--- Note 1/{count} ---
{contenu complet de la note (front-matter + corps)}

--- Note 2/{count} ---
...

=== FICHIERS BANK ACTUELS ===

--- Fichier: activeContext.md ---
{contenu}
--- Fin fichier: activeContext.md ---

...

{ou "Aucun fichier bank — première consolidation, créer les fichiers selon les rules."}

=== CONSIGNES ===
Retourne un JSON avec cette structure exacte :
{
  "bank_files": [
    {
      "filename": "nom_du_fichier.md",
      "content": "contenu complet du fichier en Markdown",
      "action": "created" ou "updated"
    }
  ],
  "synthesis": "Contenu Markdown de la synthèse résiduelle"
}

IMPORTANT :
- N'inclus QUE les fichiers qui ont été modifiés ou créés
- Les fichiers inchangés NE DOIVENT PAS apparaître dans bank_files
- La synthèse résiduelle doit résumer les notes traitées
- Le contenu des fichiers bank doit être du Markdown pur
```

### 4.3 Format de réponse attendu

```json
{
  "bank_files": [
    {
      "filename": "activeContext.md",
      "content": "# Active Context\n\n## Focus actuel\n...",
      "action": "updated"
    },
    {
      "filename": "progress.md",
      "content": "# Progress\n\n## Ce qui fonctionne\n...",
      "action": "updated"
    }
  ],
  "synthesis": "## Synthèse\n\n### Faits principaux\n- L'auth fonctionne\n..."
}
```

---

## 5. Gestion des erreurs

### 5.1 Réponse LLM non-JSON

```python
for attempt in range(2):  # 1 essai + 1 retry
    raw_content = response.choices[0].message.content
    json_str = _extract_json(raw_content)  # Gère <think>, ```json, etc.
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        if attempt == 0:
            # Retry avec rappel explicite
            messages.append({"role": "assistant", "content": raw_content})
            messages.append({"role": "user", "content": "Retourne UNIQUEMENT un JSON valide."})
            continue
        return {"status": "error", "message": "LLM returned invalid JSON after retry"}
```

### 5.2 Timeout LLM

Le timeout est configurable (`CONSOLIDATION_TIMEOUT`, défaut 600s). Si timeout :
- Ne PAS supprimer les notes live
- Retourner l'erreur
- Les notes seront traitées à la prochaine consolidation

### 5.3 Écriture partielle

Si l'écriture S3 échoue en cours de route :
- Les fichiers déjà écrits sont OK (cohérents)
- Les notes live NE SONT PAS supprimées (suppression en dernier)
- La prochaine consolidation retraitera les notes

**Principe** : on ne supprime les notes live que quand TOUT est écrit avec succès (atomicité logique).

### 5.4 Notes trop nombreuses

Si `live_notes_count > CONSOLIDATION_MAX_NOTES` (défaut 500) :
- Prendre les 500 notes les plus anciennes
- Les consolider
- Les notes restantes attendront la prochaine consolidation

---

## 6. Configuration LLMaaS

```env
LLMAAS_API_URL=https://api.ai.cloud-temple.com/v1
LLMAAS_API_KEY=your_key
LLMAAS_MODEL=qwen3-2507:235b
LLMAAS_MAX_TOKENS=100000
LLMAAS_TEMPERATURE=0.3
CONSOLIDATION_TIMEOUT=600
CONSOLIDATION_MAX_NOTES=500
```

---

## 7. Métriques

Chaque consolidation retourne des métriques :

```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "notes_processed": 42,
  "bank_files_updated": 3,
  "bank_files_created": 1,
  "bank_files_unchanged": 2,
  "synthesis_size": 850,
  "llm_tokens_used": 45000,
  "llm_prompt_tokens": 17000,
  "llm_completion_tokens": 28000,
  "duration_seconds": 35.2
}
```

Ces métriques sont aussi loguées sur `stderr` via le module `logging`.

---

## 8. Scénarios

### Scénario 1 : Première consolidation (espace neuf)

```
Input: 15 notes agent-A, 0 fichiers bank, pas de synthèse
→ LLM crée 6 fichiers bank + synthèse
→ 15 notes agent-A supprimées
→ Durée : ~20s
```

### Scénario 2 : Consolidation par agent (cas typique)

```
Input: 30 notes agent-A, 10 notes agent-B, 6 fichiers bank existants
→ bank_consolidate(agent="agent-A")
→ LLM met à jour 3 fichiers (activeContext, progress, techContext)
→ 30 notes agent-A supprimées
→ 10 notes agent-B restent dans live/
→ Durée : ~25s
```

### Scénario 3 : Gros batch (beaucoup de notes)

```
Input: 600 notes agent-A (> CONSOLIDATION_MAX_NOTES=500)
→ Les 500 plus anciennes sont traitées
→ 100 notes restent dans live/
→ L'agent peut relancer bank_consolidate pour les 100 restantes
```

### Scénario 4 : Pas de notes (rien à faire)

```
Input: 0 notes (ou 0 notes de l'agent spécifié)
→ Retour immédiat : {"notes_processed": 0, "message": "No new notes to consolidate"}
→ Pas d'appel LLM (économie de tokens)
```

### Scénario 5 : GC — Consolidation forcée

```
admin_gc_notes(space_id="projet-alpha", max_age_days=7, confirm=True)
→ Identifie les notes de plus de 7 jours
→ Les consolide via LLM (avec notice "⚠️ GC consolidation forcée")
→ Supprime les notes traitées
```

---

*Document mis à jour le 8 mars 2026 — Live Memory v0.5.0*
