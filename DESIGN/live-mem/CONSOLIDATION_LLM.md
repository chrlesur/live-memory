# Pipeline de Consolidation LLM — Live Memory

> **Version** : 0.6.0 | **Date** : 2026-03-10 | **Auteur** : Cloud Temple

---

## 1. Vue d'ensemble

La consolidation est le **cœur intelligent** de live-mem. C'est le processus par lequel le MCP utilise un LLM pour intégrer les notes live dans les fichiers bank structurés, puis nettoie le live.

**Changement majeur v0.6.0** : passage d'un mode **réécriture complète** à un mode **édition chirurgicale**. Le LLM produit désormais des **opérations d'édition par section Markdown** au lieu de réécrire les fichiers entiers. Ce qui n'est pas touché explicitement reste intact byte-for-byte.

### Pourquoi ce changement ?

L'ancien mode demandait au LLM de reproduire intégralement chaque fichier modifié. Or, un LLM ne "copie" jamais fidèlement — il synthétise, résume, reformule. À chaque consolidation, on perdait de la matière (détails supprimés, historique raccourci). C'est le syndrome de la "photocopie de photocopie".

Le nouveau mode résout ce problème : le LLM ne touche que ce qui doit changer. Le reste est préservé mécaniquement.

```
ANCIEN MODE (v0.1-v0.5)              NOUVEAU MODE (v0.6+)
─────────────────────                 ─────────────────────
LLM lit le fichier                    LLM lit le fichier
LLM réécrit TOUT le fichier           LLM décide des ÉDITIONS
→ Perte progressive de matière        → Zéro perte de matière
→ Tokens de sortie élevés             → Tokens de sortie réduits
→ Pas d'auditabilité                  → Opérations traçables
```

```
AVANT                                    APRÈS
─────                                    ─────
live/                                    live/
├── note_001.md (agent-A, observation)   ├── note_010.md (agent-B, todo)
├── note_002.md (agent-A, decision)      └── note_011.md (agent-B, insight)
├── note_003.md (agent-A, todo)              ↑ Notes d'agent-B non touchées
├── ... (42 notes agent-A)
├── note_010.md (agent-B, todo)          bank/
└── note_011.md (agent-B, insight)       ├── projectbrief.md    (inchangé ✓)
                                         ├── activeContext.md   (2 sections éditées)
bank/                                    ├── progress.md        (1 section appendée)
├── projectbrief.md (existant)           ├── systemPatterns.md  (inchangé ✓)
├── activeContext.md (existant)          ├── techContext.md      (inchangé ✓)
├── progress.md (existant)               └── productContext.md  (inchangé ✓)
├── systemPatterns.md (existant)
├── techContext.md (existant)            _synthesis.md          (écrasé)
└── productContext.md (existant)

_synthesis.md (précédent)
```

**Principes fondamentaux** :
- Les agents n'écrivent JAMAIS dans la bank. Seul le LLM le fait, guidé par les rules
- Chaque agent consolide **ses propres notes** (paramètre `agent`)
- Les notes des autres agents restent intactes dans le live
- Le LLM produit des **opérations d'édition**, pas des fichiers complets
- Ce qui n'est pas touché reste **intact byte-for-byte**

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

### Étape 2 — Construire le prompt LLM (édition chirurgicale)

Le prompt demande des **opérations d'édition par section Markdown**, pas des réécritures.

**Budget tokens estimé** :

| Composant | Tokens estimés |
|---|---|
| Prompt système | ~800 |
| Rules | ~500-2000 |
| Synthèse précédente | ~500-1500 |
| Notes live (42 notes × ~200 tokens) | ~8400 |
| Fichiers bank existants (6 × ~1000 tokens) | ~6000 |
| **Total input** | **~18K tokens** |
| Réponse (opérations d'édition, pas fichiers complets) | **~5-15K tokens** (au lieu de ~30-50K) |

### Étape 3 — Appel LLM

Un **seul appel** LLM pour toute la consolidation.

```python
response = await self._client.chat.completions.create(
    model=self._model,           # qwen3-2507:235b
    messages=messages,
    max_tokens=self._max_tokens, # 100000
    temperature=self._temperature, # 0.3
)
```

### Étape 4 — Extraction JSON robuste

Identique à la v0.5 : gère `<think>`, blocs ` ```json `, JSON brut.

### Étape 5 — Application des opérations d'édition

**C'est la nouveauté v0.6.** Au lieu d'écraser les fichiers, on applique les opérations chirurgicalement.

```python
for file_edit in llm_output["file_edits"]:
    if file_edit["action"] == "edit":
        # Lire le fichier existant
        existing_content = bank_index[file_edit["filename"]]
        updated_content = existing_content

        # Appliquer chaque opération séquentiellement
        for op in file_edit["operations"]:
            updated_content = _apply_operation(updated_content, op)

        # Écrire seulement si le contenu a changé
        if updated_content != existing_content:
            await storage.put(f"{space_id}/bank/{filename}", updated_content)

    elif file_edit["action"] == "create":
        # Nouveau fichier → écriture complète
        await storage.put(f"{space_id}/bank/{filename}", file_edit["content"])

    elif file_edit["action"] == "rewrite":
        # Réécriture complète (justifiée) → écriture complète
        await storage.put(f"{space_id}/bank/{filename}", file_edit["content"])
```

### Étape 6 — Écriture des résultats

```python
# 6a. Fichiers bank déjà écrits à l'étape 5

# 6b. Écrire la synthèse résiduelle (avec front-matter enrichi)
synthesis_md = f"""---
consolidated_at: "{now}"
notes_processed: {notes_count}
mode: surgical_edit
operations_applied: {operations_applied}
operations_failed: {operations_failed}
---

{synthesis_content}"""
await storage.put(f"{space_id}/_synthesis.md", synthesis_md)

# 6c. Mettre à jour _meta.json (compteurs)
meta["last_consolidation"] = now
meta["consolidation_count"] += 1
meta["total_notes_processed"] += notes_count

# 6d. Supprimer les notes live traitées (EN DERNIER — atomicité)
await storage.delete_many(notes_keys)
```

---

## 4. Types d'opérations d'édition

### 4.1 `replace_section`

Remplace le contenu d'une section identifiée par son heading Markdown. Le heading lui-même est conservé.

```json
{
  "type": "replace_section",
  "heading": "## Focus Actuel",
  "content": "Nouveau contenu de la section..."
}
```

**Comportement** : Tout ce qui est entre le heading `## Focus Actuel` et le prochain heading de même niveau ou supérieur est remplacé par `content`.

**Cas d'usage** : Mettre à jour le focus actuel dans `activeContext.md`, remplacer le statut d'un problème.

### 4.2 `append_to_section`

Ajoute du contenu **à la fin** d'une section existante. Le contenu existant est intégralement préservé.

```json
{
  "type": "append_to_section",
  "heading": "## Historique des Versions",
  "content": "- **v0.6.0** (10/03) : Consolidation chirurgicale."
}
```

**Comportement** : Le nouveau contenu est ajouté après le contenu existant de la section, avant le prochain heading.

**Cas d'usage** : Ajouter une entrée à l'historique, enrichir une section avec de nouvelles informations.

### 4.3 `prepend_to_section`

Ajoute du contenu **au début** d'une section (après le heading). Le contenu existant est intégralement préservé.

```json
{
  "type": "prepend_to_section",
  "heading": "## Travail Récent",
  "content": "- Nouveau développement important"
}
```

### 4.4 `add_section`

Crée une nouvelle section dans le fichier. Par défaut à la fin, ou après une section spécifique.

```json
{
  "type": "add_section",
  "heading": "## Nouvelle Section",
  "content": "Contenu de la nouvelle section",
  "after": "## Section Existante"
}
```

**Note** : Si le heading n'a pas de `#`, il est automatiquement complété en `## heading`.

### 4.5 `delete_section`

Supprime une section entière (heading + contenu).

```json
{
  "type": "delete_section",
  "heading": "## Section Obsolète"
}
```

---

## 5. Moteur d'édition Markdown

### 5.1 Parsing en sections

Le moteur `_parse_sections()` découpe un fichier Markdown en sections :

```python
[
    {"heading": "",                    "level": 0, "content": "préambule..."},
    {"heading": "# Titre",            "level": 1, "content": "\n..."},
    {"heading": "## Focus Actuel",    "level": 2, "content": "\nContenu..."},
    {"heading": "## Travail Récent",  "level": 2, "content": "\n- Item 1\n..."},
]
```

Chaque section contient :
- `heading` : la ligne complète du heading (`## Titre`)
- `heading_text` : le texte sans les `#` (`Titre`)
- `level` : le niveau (nombre de `#`, 0 pour le préambule)
- `content` : tout le texte entre ce heading et le suivant

### 5.2 Recherche flexible

`_find_section_index()` cherche une section avec 3 niveaux de flexibilité :

1. **Correspondance exacte** : `"## Focus Actuel"` → match direct
2. **Sans les `#`** : `"Focus Actuel"` → trouve `"## Focus Actuel"`
3. **Case-insensitive** : `"focus actuel"` → trouve `"## Focus Actuel"`

Cette flexibilité est cruciale car le LLM peut varier la façon dont il référence les headings.

### 5.3 Reconstruction

`_reconstruct_from_sections()` recompose le fichier depuis les sections modifiées. Garantie d'idempotence : `reconstruct(parse(content))` préserve toutes les lignes non-vides.

### 5.4 Tests

77 tests unitaires couvrent le moteur :
- Parsing, recherche, reconstruction
- Idempotence (parse → reconstruct = identité)
- Toutes les opérations (replace, append, prepend, add, delete)
- Opérations chaînées
- Cas limites (fichier vide, sans heading, sous-niveaux, caractères spéciaux)
- Scénario réaliste complet
- Rétrocompatibilité format legacy

```bash
python scripts/test_markdown_engine.py
# ✅ TOUS LES TESTS PASSENT : 77/77
```

---

## 6. Prompts

### 6.1 Prompt système

```
Tu es un assistant spécialisé dans la maintenance de Memory Banks pour des projets.

Ta mission : intégrer des notes de travail dans des fichiers Markdown structurés 
via des ÉDITIONS CHIRURGICALES.

## Principe fondamental : ÉDITER, NE PAS RÉÉCRIRE

⚠️ Tu ne dois JAMAIS renvoyer le contenu complet d'un fichier sauf si :
- C'est un nouveau fichier à créer (action "create")
- Le fichier nécessite une restructuration majeure (action "rewrite")

Pour les fichiers existants, tu produis des opérations d'édition par SECTION Markdown.
Tout ce que tu ne touches pas explicitement reste INTACT — c'est le but.

## Types d'opérations disponibles :
1. replace_section — Remplace le contenu d'une section
2. append_to_section — Ajoute du contenu à la FIN d'une section
3. prepend_to_section — Ajoute du contenu au DÉBUT d'une section
4. add_section — Crée une nouvelle section
5. delete_section — Supprime une section

## Règles :
- Préfère append_to_section et replace_section
- Pour progress.md : TOUJOURS append, JAMAIS supprimer l'historique
- Les headings doivent correspondre EXACTEMENT à ceux du fichier
- Si un fichier n'a pas besoin de modification, NE L'INCLUS PAS
```

### 6.2 Format de réponse attendu

```json
{
  "file_edits": [
    {
      "filename": "activeContext.md",
      "action": "edit",
      "operations": [
        {
          "type": "replace_section",
          "heading": "## Focus Actuel",
          "content": "Nouveau contenu de la section..."
        },
        {
          "type": "append_to_section",
          "heading": "## Travail Récent",
          "content": "- Nouvel élément ajouté"
        }
      ]
    },
    {
      "filename": "nouveau_fichier.md",
      "action": "create",
      "content": "# Titre\n\nContenu complet du nouveau fichier..."
    },
    {
      "filename": "fichier_restructure.md",
      "action": "rewrite",
      "content": "# Titre\n\nContenu complet réécrit...",
      "reason": "Restructuration majeure nécessaire car..."
    }
  ],
  "synthesis": "Résumé concis des notes traitées..."
}
```

### 6.3 Actions par fichier

| Action | Usage | Contenu renvoyé | Quand ? |
|--------|-------|-----------------|---------|
| `edit` | Fichier existant | Opérations d'édition | 95% des cas |
| `create` | Nouveau fichier | Contenu complet | Première consolidation |
| `rewrite` | Restructuration | Contenu complet + raison | Exceptionnel |

---

## 7. Rétrocompatibilité

Si le LLM retourne l'ancien format (`bank_files` au lieu de `file_edits`), une fonction `_convert_legacy_format()` convertit automatiquement :

- `"action": "updated"` → `"action": "rewrite"` (fallback)
- `"action": "created"` → `"action": "create"`

Ce filet de sécurité garantit que la transition est transparente.

---

## 8. Gestion des erreurs

### 8.1 Réponse LLM non-JSON

Identique à la v0.5 : retry avec rappel explicite.

### 8.2 Section introuvable

Si une opération référence un heading qui n'existe pas dans le fichier :
- L'opération échoue avec un `ValueError`
- L'erreur est loggée mais n'arrête pas la consolidation
- Les autres opérations sont appliquées normalement
- Le compteur `operations_failed` est incrémenté

### 8.3 Timeout LLM / Écriture partielle

Identique à la v0.5 : atomicité logique, notes supprimées en dernier.

---

## 9. Configuration LLMaaS

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

## 10. Métriques

Chaque consolidation retourne des métriques enrichies :

```json
{
  "status": "ok",
  "space_id": "projet-alpha",
  "notes_processed": 42,
  "bank_files_updated": 2,
  "bank_files_created": 0,
  "bank_files_unchanged": 4,
  "operations_applied": 5,
  "operations_failed": 0,
  "synthesis_size": 850,
  "llm_tokens_used": 25000,
  "llm_prompt_tokens": 17000,
  "llm_completion_tokens": 8000,
  "duration_seconds": 20.2
}
```

**Gains attendus** :
- `llm_completion_tokens` : réduit de ~50-70% (opérations vs fichiers complets)
- Zéro perte de matière dans les fichiers non touchés
- `operations_applied/failed` : auditabilité des modifications

---

## 11. Scénarios

### Scénario 1 : Première consolidation (espace neuf)

```
Input: 15 notes agent-A, 0 fichiers bank, pas de synthèse
→ LLM utilise action "create" pour les 6 fichiers bank
→ 15 notes agent-A supprimées
→ Durée : ~20s
```

### Scénario 2 : Consolidation typique (édition chirurgicale)

```
Input: 5 notes agent-A, 6 fichiers bank existants
→ LLM produit 3 file_edits avec action "edit" :
   - activeContext.md : replace_section "## Focus" + append "## Travail Récent"
   - progress.md : append "## Historique"
   - systemPatterns.md : append "## Décisions"
→ 3 fichiers mis à jour, 3 inchangés (projectbrief, productContext, techContext)
→ 5 notes agent-A supprimées
→ Durée : ~15s (moins de tokens en sortie)
```

### Scénario 3 : Consolidation avec erreur d'opération

```
Input: 3 notes, 6 fichiers bank
→ LLM produit 2 edits, dont 1 avec section introuvable
→ L'opération échouée est loggée, les autres appliquées
→ Métriques : operations_applied=3, operations_failed=1
```

---

*Document mis à jour le 10 mars 2026 — Live Memory v0.6.0 (consolidation chirurgicale)*
