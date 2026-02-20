# Pipeline de Consolidation LLM — Live Memory

> **Version** : 0.1.0 | **Date** : 2026-02-20 | **Auteur** : Cloud Temple

---

## 1. Vue d'ensemble

La consolidation est le **cœur intelligent** de live-mem. C'est le processus par lequel le MCP utilise un LLM pour synthétiser les notes live en fichiers bank structurés, puis nettoie le live.

```
AVANT                                    APRÈS
─────                                    ─────
live/                                    live/
├── note_001.md (observation)            └── (vide — tout nettoyé)
├── note_002.md (decision)
├── note_003.md (todo)                   bank/
├── ... (42 notes)                       ├── projectbrief.md    (créé/MAJ)
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

**Principe fondamental** : Les agents n'écrivent JAMAIS dans la bank. Seul le LLM le fait, guidé par les rules.

---

## 2. Pipeline détaillé

### Étape 1 — Collecte des inputs

```python
# 1a. Lire les rules (immuables)
rules = await storage.get("{space_id}/_rules.md")

# 1b. Lire la synthèse précédente (contexte cumulatif)
synthesis = await storage.get("{space_id}/_synthesis.md")  # ou None

# 1c. Lire TOUTES les notes live
live_notes = await storage.list_and_get("{space_id}/live/*")
# Triées par timestamp (chronologique)
# Exclure .keep

# 1d. Lire TOUS les fichiers bank actuels
bank_files = await storage.list_and_get("{space_id}/bank/*")
# Exclure .keep
```

### Étape 2 — Préparer le prompt LLM

Le prompt est en **une seule requête** (pas de chunking) car on exploite la fenêtre de 100K tokens de qwen3-2507:235b.

**Calcul du budget tokens** :

| Composant | Tokens estimés |
|---|---|
| Prompt système | ~500 |
| Rules | ~500-2000 |
| Synthèse précédente | ~500-1500 |
| Notes live (42 notes × ~200 tokens) | ~8400 |
| Fichiers bank existants (6 × ~1000 tokens) | ~6000 |
| **Total input** | **~17K tokens** |
| Marge pour la réponse | ~80K tokens |
| **Total** | **~97K / 100K** |

Même avec un gros espace (200 notes, 10 fichiers bank), on reste dans les 100K tokens.

### Étape 3 — Appel LLM

Un **seul appel** LLM pour toute la consolidation.

```python
response = await llm_client.chat.completions.create(
    model="qwen3-2507:235b",
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": consolidation_prompt}
    ],
    max_tokens=100000,
    temperature=0.3,
    response_format={"type": "json_object"}
)
```

### Étape 4 — Écriture des résultats

```python
result = json.loads(response.choices[0].message.content)

# 4a. Écrire chaque fichier bank
for file_entry in result["bank_files"]:
    async with bank_locks[(space_id, file_entry["filename"])]:
        await storage.put(f"{space_id}/bank/{file_entry['filename']}", file_entry["content"])

# 4b. Écrire la synthèse résiduelle
await storage.put(f"{space_id}/_synthesis.md", result["synthesis"])

# 4c. Supprimer toutes les notes live
for note in live_notes:
    await storage.delete(note.key)

# 4d. Mettre à jour _meta.json
meta["last_consolidation"] = now
meta["consolidation_count"] += 1
meta["total_notes_processed"] += len(live_notes)
await storage.put(f"{space_id}/_meta.json", json.dumps(meta))
```

---

## 3. Prompts

### 3.1 Prompt système

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
- La synthèse doit être concise mais couvrir les points clés des notes traitées
- Si un fichier bank n'a pas besoin de modification, NE L'INCLUS PAS dans bank_files
```

### 3.2 Prompt utilisateur (consolidation)

```
=== RULES DE L'ESPACE "{space_id}" ===
{contenu de _rules.md}

=== SYNTHÈSE PRÉCÉDENTE (consolidation #{n-1}) ===
{contenu de _synthesis.md, ou "Aucune — première consolidation"}

=== NOTES LIVE À INTÉGRER ({count} notes) ===
{pour chaque note, chronologiquement :}

--- Note {i}/{count} ---
Timestamp: {timestamp}
Agent: {agent}
Catégorie: {category}
Tags: {tags}

{contenu de la note}

--- Fin note {i} ---

=== FICHIERS BANK ACTUELS ===
{pour chaque fichier bank existant :}

--- Fichier: {filename} ---
{contenu du fichier}

--- Fin fichier: {filename} ---

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
- La synthèse résiduelle doit résumer les notes traitées de façon concise
- Le contenu des fichiers bank doit être du Markdown pur, autosuffisant
```

### 3.3 Format de réponse attendu

```json
{
  "bank_files": [
    {
      "filename": "activeContext.md",
      "content": "# Active Context\n\n## Focus actuel\n\nRefactoring du module d'authentification...",
      "action": "updated"
    },
    {
      "filename": "progress.md",
      "content": "# Progress\n\n## Ce qui fonctionne\n- Module auth : terminé\n...",
      "action": "updated"
    },
    {
      "filename": "systemPatterns.md",
      "content": "# System Patterns\n\n## Architecture\n- Pattern S3-only...",
      "action": "created"
    }
  ],
  "synthesis": "## Synthèse de la consolidation #4\n\n### Faits principaux\n- L'auth fonctionne\n- Décision S3-only confirmée\n\n### Points d'attention\n- Timeout LLM à surveiller\n\n### Prochaines étapes\n- Backup system\n- Documentation"
}
```

---

## 4. Première consolidation

Lors de la première consolidation d'un espace (bank vide), le LLM doit **créer** tous les fichiers définis dans les rules :

```
Input:
- Rules : définit 6 fichiers (projectbrief, productContext, etc.)
- Synthèse précédente : "Aucune — première consolidation"
- Notes live : 15 notes initiales
- Fichiers bank : "Aucun fichier bank — première consolidation"

Output attendu:
- bank_files : 6 fichiers créés (action: "created" pour tous)
- synthesis : première synthèse
```

---

## 5. Gestion des erreurs

### 5.1 Réponse LLM non-JSON

```python
try:
    result = json.loads(response.choices[0].message.content)
except json.JSONDecodeError:
    # Retry 1 fois avec un prompt plus explicite
    # Si échec → retourner erreur, ne PAS supprimer les notes live
    return {"status": "error", "message": "LLM returned invalid JSON"}
```

### 5.2 Timeout LLM

Le timeout est configurable (`CONSOLIDATION_TIMEOUT`, défaut 600s). Si timeout :
- Ne PAS supprimer les notes live
- Retourner l'erreur
- Les notes seront traitées à la prochaine consolidation

### 5.3 Écriture partielle

Si l'écriture S3 échoue en cours de route (ex: certains fichiers bank écrits, d'autres non) :
- Les fichiers déjà écrits sont OK (cohérents)
- Les notes live NE SONT PAS supprimées (on ne supprime qu'après succès complet)
- La prochaine consolidation retraitera les notes → les fichiers bank non écrits seront créés

**Principe** : on ne supprime les notes live que quand TOUT est écrit avec succès (écriture atomique logique).

### 5.4 Notes trop nombreuses

Si `live_notes_count > CONSOLIDATION_MAX_NOTES` (défaut 500) :
- Prendre les 500 notes les plus anciennes
- Les consolider
- Les notes restantes attendront la prochaine consolidation
- Retourner `{"status": "ok", "notes_processed": 500, "notes_remaining": 150}`

---

## 6. Configuration LLMaaS

```env
# API
LLMAAS_API_URL=https://api.ai.cloud-temple.com/v1
LLMAAS_API_KEY=your_key

# Modèle
LLMAAS_MODEL=qwen3-2507:235b
LLMAAS_MAX_TOKENS=100000
LLMAAS_TEMPERATURE=0.3

# Timeouts
CONSOLIDATION_TIMEOUT=600          # Timeout par appel LLM (secondes)
CONSOLIDATION_MAX_NOTES=500        # Max notes par consolidation
```

### Client LLM

Même pattern que graph-memory : `AsyncOpenAI` compatible.

```python
from openai import AsyncOpenAI

class ConsolidatorService:
    def __init__(self):
        self._client = AsyncOpenAI(
            base_url=settings.llmaas_api_url,  # Inclut déjà /v1
            api_key=settings.llmaas_api_key,
            timeout=settings.consolidation_timeout
        )
    
    async def consolidate(self, space_id: str, ...) -> dict:
        response = await self._client.chat.completions.create(
            model=settings.llmaas_model,
            messages=[...],
            max_tokens=settings.llmaas_max_tokens,
            temperature=settings.llmaas_temperature,
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
```

---

## 7. Métriques

Chaque consolidation retourne des métriques :

```json
{
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

Ces métriques sont aussi loguées sur `stderr` pour le monitoring.

---

## 8. Scénarios

### Scénario 1 : Première consolidation (espace neuf)

```
Input: 15 notes, 0 fichiers bank, pas de synthèse
→ LLM crée 6 fichiers bank + synthèse
→ 15 notes supprimées
→ Durée : ~20s
```

### Scénario 2 : Consolidation incrémentale (cas typique)

```
Input: 30 notes, 6 fichiers bank existants, synthèse précédente
→ LLM met à jour 3 fichiers (activeContext, progress, techContext)
→ 3 fichiers inchangés (projectbrief, productContext, systemPatterns)
→ 30 notes supprimées, nouvelle synthèse
→ Durée : ~25s
```

### Scénario 3 : Gros batch (beaucoup de notes)

```
Input: 600 notes (> CONSOLIDATION_MAX_NOTES=500)
→ Les 500 plus anciennes sont traitées
→ 100 notes restent dans live/
→ Retour : {"notes_processed": 500, "notes_remaining": 100}
→ L'agent peut relancer bank_consolidate pour les 100 restantes
```

### Scénario 4 : Pas de notes (rien à faire)

```
Input: 0 notes
→ Retour immédiat : {"notes_processed": 0, "message": "No new notes to consolidate"}
→ Pas d'appel LLM (économie de tokens)
```

---

*Document généré le 20 février 2026 — Live Memory v0.1.0*
