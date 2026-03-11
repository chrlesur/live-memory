# -*- coding: utf-8 -*-
"""
Service Consolidator — Pipeline LLM pour la consolidation notes → bank.

C'est le cœur intelligent de Live Memory. Le pipeline :
1. Collecte : rules + synthèse précédente + notes live + bank actuelle
2. Prompt : construit le prompt LLM (system + user)
3. Appel LLM : une seule requête à qwen3-2507:235b, réponse JSON
4. Application : éditions chirurgicales sur les fichiers bank existants
5. Écriture : bank files + synthesis + suppression notes + update meta

Principes :
    - Les agents n'écrivent JAMAIS dans la bank — seul le LLM le fait
    - Les notes sont supprimées UNIQUEMENT après succès complet (atomicité)
    - Un seul consolidate à la fois par espace (asyncio.Lock)
    - Le LLM produit des OPÉRATIONS D'ÉDITION (pas des réécritures complètes)
    - Ce qui n'est pas touché reste intact byte-for-byte (zéro perte)

Voir CONSOLIDATION_LLM.md pour les détails du pipeline et des prompts.
"""

import sys
import re
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from ..config import get_settings
from .storage import get_storage

logger = logging.getLogger("live_mem.consolidator")


# ─────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans la maintenance de Memory Banks pour des projets.

Ta mission : intégrer des notes de travail dans des fichiers Markdown structurés via des ÉDITIONS CHIRURGICALES.

## Ce que tu reçois :
1. Les RULES qui définissent la structure de la memory bank
2. La SYNTHÈSE PRÉCÉDENTE (contexte des consolidations antérieures)
3. Les NOTES LIVE nouvelles à intégrer
4. Les FICHIERS BANK actuels (le contenu existant)

## Ce que tu dois retourner :
Un JSON avec des OPÉRATIONS D'ÉDITION par fichier — PAS le contenu complet des fichiers.

## Principe fondamental : ÉDITER, NE PAS RÉÉCRIRE

⚠️ Tu ne dois JAMAIS renvoyer le contenu complet d'un fichier sauf si :
- C'est un nouveau fichier à créer (action "create")
- Le fichier nécessite une restructuration majeure (action "rewrite" — exceptionnel, justification obligatoire)

Pour les fichiers existants, tu produis des opérations d'édition par SECTION Markdown.
Tout ce que tu ne touches pas explicitement reste INTACT — c'est le but.

## Types d'opérations disponibles :

1. **replace_section** — Remplace le contenu d'une section (identifiée par son heading)
   Le contenu SOUS le heading jusqu'au prochain heading de même niveau ou supérieur est remplacé.
   
2. **append_to_section** — Ajoute du contenu à la FIN d'une section existante
   Préserve tout le contenu existant, ajoute après.

3. **prepend_to_section** — Ajoute du contenu au DÉBUT d'une section (après le heading)
   Préserve tout le contenu existant, ajoute avant.

4. **add_section** — Crée une nouvelle section (heading + contenu) à la fin du fichier
   Ou après une section spécifique si "after" est fourni.

5. **delete_section** — Supprime une section entière (heading + contenu)

## Règles :
- Respecte STRICTEMENT la structure définie dans les rules
- Intègre les nouvelles informations des notes live
- Préfère append_to_section et replace_section — ce sont les opérations les plus courantes
- Pour activeContext.md : replace_section le focus, append les éléments récents
- Pour progress.md : append les nouvelles entrées, NE JAMAIS supprimer l'historique
- Les headings doivent correspondre EXACTEMENT à ceux du fichier (avec les ## )
- Si un fichier n'a pas besoin de modification, NE L'INCLUS PAS
- La synthèse doit être concise mais couvrir les points clés des notes traitées"""


class ConsolidatorService:
    """
    Service de consolidation LLM : transforme les notes live en bank.

    Utilise AsyncOpenAI pour communiquer avec le LLMaaS Cloud Temple.
    Mode "édition chirurgicale" : le LLM produit des opérations d'édition
    par section Markdown, pas des réécritures complètes.
    """

    def __init__(self):
        settings = get_settings()
        self._client = AsyncOpenAI(
            base_url=settings.llmaas_api_url,
            api_key=settings.llmaas_api_key,
            timeout=settings.consolidation_timeout,
        )
        self._model = settings.llmaas_model
        self._max_tokens = settings.llmaas_max_tokens
        self._temperature = settings.llmaas_temperature
        self._max_notes = settings.consolidation_max_notes

    async def consolidate(self, space_id: str, agent: str = "") -> dict:
        """
        Pipeline complet de consolidation pour un espace.

        IMPORTANT : Seules les notes de l'agent appelant sont consolidées.
        Les notes des autres agents restent dans live/ en attente.

        Étapes :
            1. Collecter les inputs (rules, synthesis, notes de l'agent, bank)
            2. Construire le prompt LLM (format édition chirurgicale)
            3. Appeler le LLM
            4. Appliquer les opérations d'édition sur les fichiers bank
            5. Écrire les résultats (bank, synthesis, supprimer notes)

        Args:
            space_id: Identifiant de l'espace à consolider
            agent: Nom de l'agent appelant (filtre les notes à consolider)

        Returns:
            Métriques de consolidation ou erreur
        """
        t0 = time.monotonic()
        storage = get_storage()
        agent_label = agent or "(all)"
        logger.info("Consolidation start — space=%s agent=%s", space_id, agent_label)

        # ── Étape 1 : Collecter les inputs ────────────────
        inputs = await self._collect_inputs(space_id, agent=agent)
        if inputs.get("status") == "error":
            return inputs

        # Pas de notes → rien à faire
        if not inputs["notes"]:
            return {
                "status": "ok",
                "notes_processed": 0,
                "message": "No new notes to consolidate",
            }

        # ── Étape 2 : Construire le prompt ────────────────
        messages = self._build_prompt(
            space_id=space_id,
            rules=inputs["rules"],
            synthesis=inputs["synthesis"],
            notes=inputs["notes"],
            bank_files=inputs["bank_files"],
        )

        # ── Étape 3 : Appeler le LLM ─────────────────────
        llm_result = await self._call_llm(messages)
        if llm_result.get("status") == "error":
            return llm_result

        # ── Étape 4 : Appliquer les éditions et écrire ───
        write_result = await self._write_results(
            space_id=space_id,
            llm_output=llm_result["data"],
            bank_files=inputs["bank_files"],
            notes_keys=inputs["notes_keys"],
            notes_count=len(inputs["notes"]),
            usage=llm_result.get("usage", {}),
        )

        write_result["duration_seconds"] = round(time.monotonic() - t0, 1)
        logger.info(
            "Consolidation done — space=%s agent=%s notes=%d files_created=%d "
            "files_updated=%d files_unchanged=%d tokens=%d duration=%.1fs",
            space_id, agent_label,
            write_result.get("notes_processed", 0),
            write_result.get("bank_files_created", 0),
            write_result.get("bank_files_updated", 0),
            write_result.get("bank_files_unchanged", 0),
            write_result.get("llm_tokens_used", 0),
            write_result["duration_seconds"],
        )
        return write_result

    async def _collect_inputs(self, space_id: str, agent: str = "") -> dict:
        """
        Étape 1 : Lire les rules, synthèse, notes de l'agent et bank depuis S3.

        Si agent est fourni, seules les notes de cet agent sont collectées.
        Les notes des autres agents restent dans live/.

        Returns:
            Dict avec rules, synthesis, notes, notes_keys, bank_files
        """
        storage = get_storage()

        # Vérifier l'existence de l'espace
        meta = await storage.get_json(f"{space_id}/_meta.json")
        if meta is None:
            return {"status": "error", "message": f"Espace '{space_id}' introuvable"}

        # Lire les rules (immuables)
        rules = await storage.get(f"{space_id}/_rules.md") or ""

        # Lire la synthèse précédente (peut ne pas exister)
        synthesis = await storage.get(f"{space_id}/_synthesis.md")

        # Lire les notes live
        notes_raw = await storage.list_and_get(f"{space_id}/live/")
        # Trier par clé (= par timestamp, chronologique)
        notes_raw.sort(key=lambda n: n["key"])

        # Filtrer par agent : chaque agent ne consolide que SES notes
        # Le nom de l'agent est dans le nom de fichier : {ts}_{agent}_{cat}_{uuid}.md
        if agent:
            notes_raw = [
                n for n in notes_raw
                if f"_{agent}_" in n["key"].split("/")[-1]
                or n["key"].split("/")[-1].startswith(f"{agent}_")
            ]

        # Limiter au max_notes (les plus anciennes d'abord)
        notes_remaining = 0
        if len(notes_raw) > self._max_notes:
            notes_remaining = len(notes_raw) - self._max_notes
            notes_raw = notes_raw[:self._max_notes]

        # Garder les clés pour la suppression ultérieure
        notes_keys = [n["key"] for n in notes_raw]

        # Lire les fichiers bank actuels
        bank_raw = await storage.list_and_get(f"{space_id}/bank/")

        return {
            "rules": rules,
            "synthesis": synthesis,
            "notes": notes_raw,
            "notes_keys": notes_keys,
            "notes_remaining": notes_remaining,
            "bank_files": bank_raw,
            "meta": meta,
        }

    def _build_prompt(
        self,
        space_id: str,
        rules: str,
        synthesis: Optional[str],
        notes: list[dict],
        bank_files: list[dict],
    ) -> list[dict]:
        """
        Étape 2 : Construire les messages pour l'appel LLM.

        Le prompt demande des OPÉRATIONS D'ÉDITION, pas des réécritures.

        Returns:
            Liste de messages [{"role": "system", ...}, {"role": "user", ...}]
        """
        # Construire la section notes
        notes_section = ""
        for i, note in enumerate(notes, 1):
            content = note["content"]
            notes_section += f"\n--- Note {i}/{len(notes)} ---\n{content}\n"

        # Construire la section bank (fichiers existants avec leur contenu)
        if bank_files:
            bank_section = ""
            for bf in bank_files:
                filename = bf["key"].split("/")[-1]
                bank_section += (
                    f"\n--- Fichier: {filename} ---\n"
                    f"{bf['content']}\n"
                    f"--- Fin fichier: {filename} ---\n"
                )
        else:
            bank_section = (
                "Aucun fichier bank — première consolidation. "
                "Utilise l'action 'create' pour créer les fichiers selon les rules."
            )

        # Construire le prompt utilisateur
        user_prompt = f"""=== RULES DE L'ESPACE "{space_id}" ===
{rules}

=== SYNTHÈSE PRÉCÉDENTE ===
{synthesis or "Aucune — première consolidation"}

=== NOTES LIVE À INTÉGRER ({len(notes)} notes) ===
{notes_section}

=== FICHIERS BANK ACTUELS ===
{bank_section}

=== FORMAT DE RÉPONSE ===
Retourne un JSON avec cette structure exacte :
{{
  "file_edits": [
    {{
      "filename": "activeContext.md",
      "action": "edit",
      "operations": [
        {{
          "type": "replace_section",
          "heading": "## Focus Actuel",
          "content": "Nouveau contenu de la section..."
        }},
        {{
          "type": "append_to_section",
          "heading": "## Travail Récent",
          "content": "- Nouvel élément ajouté\\n- Autre élément"
        }},
        {{
          "type": "add_section",
          "heading": "## Nouvelle Section",
          "content": "Contenu de la nouvelle section",
          "after": "## Section Existante"
        }},
        {{
          "type": "delete_section",
          "heading": "## Section Obsolète"
        }}
      ]
    }},
    {{
      "filename": "nouveau_fichier.md",
      "action": "create",
      "content": "# Titre\\n\\nContenu complet du nouveau fichier..."
    }},
    {{
      "filename": "fichier_restructure.md",
      "action": "rewrite",
      "content": "# Titre\\n\\nContenu complet réécrit...",
      "reason": "Restructuration majeure nécessaire car..."
    }}
  ],
  "synthesis": "Résumé concis des notes traitées..."
}}

=== CONSIGNES IMPORTANTES ===
1. Pour les fichiers EXISTANTS, utilise action "edit" avec des opérations chirurgicales
2. Pour les NOUVEAUX fichiers, utilise action "create" avec le contenu complet
3. Action "rewrite" = réécriture COMPLÈTE — UNIQUEMENT si restructuration majeure nécessaire
4. Les fichiers inchangés NE DOIVENT PAS apparaître dans file_edits
5. Les headings dans les opérations doivent correspondre EXACTEMENT à ceux du fichier (ex: "## Focus Actuel")
6. Préfère append_to_section pour AJOUTER de l'information sans rien perdre
7. Préfère replace_section pour METTRE À JOUR une section dont le contenu change
8. Pour progress.md : TOUJOURS append, JAMAIS supprimer l'historique
9. La synthèse résiduelle doit résumer les notes traitées"""

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    async def _call_llm(self, messages: list[dict]) -> dict:
        """
        Étape 3 : Appeler le LLM et parser la réponse JSON.

        Inclut un retry si la réponse n'est pas du JSON valide.

        Returns:
            {"status": "ok", "data": {...}, "usage": {...}} ou erreur
        """
        for attempt in range(2):  # 1 essai + 1 retry
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )

                raw_content = response.choices[0].message.content or ""

                # Extraire le JSON de la réponse (peut être enveloppé dans ```json)
                json_str = _extract_json(raw_content)

                # Parser le JSON
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    if attempt == 0:
                        # Retry avec un rappel plus explicite
                        logger.warning("LLM: JSON invalide (attempt %d), retry...", attempt + 1)
                        messages.append({"role": "assistant", "content": raw_content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "Ta réponse n'est pas du JSON valide. "
                                "Retourne UNIQUEMENT un objet JSON valide "
                                "avec file_edits et synthesis."
                            ),
                        })
                        continue
                    return {
                        "status": "error",
                        "message": "LLM returned invalid JSON after retry",
                    }

                # Valider la structure minimale
                if "file_edits" not in data or "synthesis" not in data:
                    # Rétrocompat : accepter aussi l'ancien format "bank_files"
                    if "bank_files" in data and "synthesis" in data:
                        data = _convert_legacy_format(data)
                    elif attempt == 0:
                        logger.warning("LLM: structure invalide (attempt %d), retry...", attempt + 1)
                        messages.append({"role": "assistant", "content": raw_content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "Ta réponse doit contenir 'file_edits' et 'synthesis'. "
                                "Retourne le JSON au format demandé."
                            ),
                        })
                        continue
                    else:
                        return {
                            "status": "error",
                            "message": "LLM response missing file_edits or synthesis",
                        }

                # Extraire les métriques d'usage
                usage = {}
                if response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    }

                return {"status": "ok", "data": data, "usage": usage}

            except Exception as e:
                return {"status": "error", "message": f"LLM call failed: {str(e)}"}

        return {"status": "error", "message": "LLM failed after retries"}

    async def _write_results(
        self,
        space_id: str,
        llm_output: dict,
        bank_files: list[dict],
        notes_keys: list[str],
        notes_count: int,
        usage: dict,
    ) -> dict:
        """
        Étape 4 : Appliquer les éditions et écrire les résultats sur S3.

        Pour chaque file_edit :
        - action "edit" : lire le fichier existant, appliquer les opérations, écrire
        - action "create" : écrire le contenu complet (nouveau fichier)
        - action "rewrite" : écrire le contenu complet (réécriture justifiée)

        Ordre : bank files → synthesis → meta → delete notes.
        Les notes sont supprimées EN DERNIER (atomicité logique).

        Returns:
            Métriques de consolidation
        """
        storage = get_storage()

        # Construire un index des fichiers bank existants par filename
        bank_index = {}
        for bf in bank_files:
            filename = bf["key"].split("/")[-1]
            bank_index[filename] = bf["content"]

        files_created = 0
        files_updated = 0
        operations_applied = 0
        operations_failed = 0

        # 4a. Appliquer chaque édition de fichier
        for file_edit in llm_output.get("file_edits", []):
            filename = file_edit.get("filename", "")
            action = file_edit.get("action", "edit")

            if not filename:
                logger.warning("file_edit sans filename, ignoré")
                continue

            if action == "create":
                # Nouveau fichier : écriture complète
                content = file_edit.get("content", "")
                if content:
                    await storage.put(f"{space_id}/bank/{filename}", content)
                    files_created += 1
                    logger.info("Created bank file: %s", filename)

            elif action == "rewrite":
                # Réécriture complète (fallback justifié)
                content = file_edit.get("content", "")
                reason = file_edit.get("reason", "non spécifiée")
                if content:
                    await storage.put(f"{space_id}/bank/{filename}", content)
                    files_updated += 1
                    logger.info(
                        "Rewrote bank file: %s (reason: %s)", filename, reason
                    )

            elif action == "edit":
                # Édition chirurgicale : appliquer les opérations
                operations = file_edit.get("operations", [])
                if not operations:
                    continue

                # Lire le contenu existant
                existing_content = bank_index.get(filename)
                if existing_content is None:
                    # Le fichier n'existe pas → le LLM aurait dû utiliser "create"
                    # On tente quand même en partant de rien
                    logger.warning(
                        "edit sur fichier inexistant '%s', traité comme create",
                        filename,
                    )
                    existing_content = ""

                # Appliquer les opérations une par une
                updated_content = existing_content
                for op in operations:
                    try:
                        updated_content = _apply_operation(updated_content, op)
                        operations_applied += 1
                    except Exception as e:
                        logger.error(
                            "Échec opération %s sur %s: %s",
                            op.get("type", "?"),
                            filename,
                            str(e),
                        )
                        operations_failed += 1

                # Écrire seulement si le contenu a changé
                if updated_content != existing_content:
                    await storage.put(f"{space_id}/bank/{filename}", updated_content)
                    files_updated += 1
                    logger.info(
                        "Updated bank file: %s (%d operations applied)",
                        filename,
                        len(operations),
                    )
            else:
                logger.warning("Action inconnue '%s' pour %s, ignorée", action, filename)

        # 4b. Écrire la synthèse résiduelle
        synthesis_content = llm_output.get("synthesis", "")
        now = datetime.now(timezone.utc).isoformat()
        synthesis_md = (
            f"---\n"
            f"consolidated_at: \"{now}\"\n"
            f"notes_processed: {notes_count}\n"
            f"mode: surgical_edit\n"
            f"operations_applied: {operations_applied}\n"
            f"operations_failed: {operations_failed}\n"
            f"---\n\n"
            f"{synthesis_content}"
        )
        await storage.put(f"{space_id}/_synthesis.md", synthesis_md)

        # 4c. Mettre à jour _meta.json
        meta = await storage.get_json(f"{space_id}/_meta.json") or {}
        meta["last_consolidation"] = now
        meta["consolidation_count"] = meta.get("consolidation_count", 0) + 1
        meta["total_notes_processed"] = (
            meta.get("total_notes_processed", 0) + notes_count
        )
        await storage.put_json(f"{space_id}/_meta.json", meta)

        # 4d. Supprimer les notes live traitées (EN DERNIER)
        await storage.delete_many(notes_keys)

        # Compter les fichiers bank inchangés
        bank_objects = await storage.list_objects(f"{space_id}/bank/")
        total_bank = len([o for o in bank_objects if not o["Key"].endswith(".keep")])
        files_unchanged = total_bank - files_created - files_updated

        return {
            "status": "ok",
            "space_id": space_id,
            "notes_processed": notes_count,
            "bank_files_updated": files_updated,
            "bank_files_created": files_created,
            "bank_files_unchanged": max(0, files_unchanged),
            "operations_applied": operations_applied,
            "operations_failed": operations_failed,
            "synthesis_size": len(synthesis_content),
            "llm_tokens_used": usage.get("total_tokens", 0),
            "llm_prompt_tokens": usage.get("prompt_tokens", 0),
            "llm_completion_tokens": usage.get("completion_tokens", 0),
        }

    async def test_connection(self) -> dict:
        """Teste la connexion au LLMaaS avec un appel minimal."""
        try:
            t0 = time.monotonic()
            test_messages: list[dict[str, str]] = [
                {"role": "user", "content": "Réponds OK"}
            ]
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=test_messages,  # type: ignore[arg-type]
                max_tokens=5,
            )
            latency = round((time.monotonic() - t0) * 1000, 1)
            return {
                "status": "ok",
                "model": self._model,
                "latency_ms": latency,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


# ─────────────────────────────────────────────────────────────
# Moteur d'édition Markdown
# ─────────────────────────────────────────────────────────────

def _parse_sections(content: str) -> list[dict]:
    """
    Parse un fichier Markdown en sections.

    Chaque section est définie par un heading (# ## ### etc.) et contient
    tout le texte jusqu'au prochain heading de même niveau ou supérieur.

    Returns:
        Liste de dicts :
        {
            "heading": "## Section Title" (ou "" pour le préambule),
            "heading_text": "Section Title" (sans les #),
            "level": 2 (nombre de #, 0 pour le préambule),
            "content": "lignes de contenu après le heading\\n...",
            "start_line": 0  (index de ligne du heading)
        }
    """
    lines = content.split("\n")
    sections = []
    current_heading = ""
    current_heading_text = ""
    current_level = 0
    current_content_lines = []
    current_start = 0

    for i, line in enumerate(lines):
        # Détecter un heading Markdown (# à ######)
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)

        if heading_match:
            # Sauvegarder la section précédente
            sections.append({
                "heading": current_heading,
                "heading_text": current_heading_text,
                "level": current_level,
                "content": "\n".join(current_content_lines),
                "start_line": current_start,
            })

            # Commencer une nouvelle section
            hashes = heading_match.group(1)
            current_heading = line
            current_heading_text = heading_match.group(2).strip()
            current_level = len(hashes)
            current_content_lines = []
            current_start = i
        else:
            current_content_lines.append(line)

    # Sauvegarder la dernière section
    sections.append({
        "heading": current_heading,
        "heading_text": current_heading_text,
        "level": current_level,
        "content": "\n".join(current_content_lines),
        "start_line": current_start,
    })

    return sections


def _find_section_index(sections: list[dict], heading: str) -> int:
    """
    Trouve l'index d'une section par son heading.

    Matching flexible :
    - Correspondance exacte : "## Focus Actuel"
    - Sans les # : "Focus Actuel"
    - Case-insensitive en dernier recours

    Returns:
        Index dans la liste sections, ou -1 si non trouvé
    """
    heading_stripped = heading.strip()

    # 1. Correspondance exacte
    for i, sec in enumerate(sections):
        if sec["heading"].strip() == heading_stripped:
            return i

    # 2. Sans les # (le LLM a peut-être omis les ##)
    heading_no_hash = re.sub(r"^#+\s*", "", heading_stripped)
    for i, sec in enumerate(sections):
        if sec["heading_text"] == heading_no_hash:
            return i

    # 3. Case-insensitive
    heading_lower = heading_no_hash.lower()
    for i, sec in enumerate(sections):
        if sec["heading_text"].lower() == heading_lower:
            return i

    return -1


def _reconstruct_from_sections(sections: list[dict]) -> str:
    """
    Reconstruit un fichier Markdown à partir de sections parsées.

    Returns:
        Contenu Markdown reconstruit
    """
    parts = []
    for sec in sections:
        if sec["heading"]:
            parts.append(sec["heading"])
        if sec["content"]:
            parts.append(sec["content"])
        elif sec["heading"]:
            # Section avec heading mais sans contenu : ajouter une ligne vide
            parts.append("")

    result = "\n".join(parts)

    # Nettoyer les lignes vides multiples (max 2 consécutives)
    result = re.sub(r"\n{4,}", "\n\n\n", result)

    return result


def _apply_operation(content: str, operation: dict) -> str:
    """
    Applique une seule opération d'édition sur un contenu Markdown.

    Args:
        content: Contenu Markdown du fichier
        operation: Dict avec "type", "heading", "content", etc.

    Returns:
        Contenu Markdown modifié

    Raises:
        ValueError: Si l'opération est invalide ou la section introuvable
    """
    op_type = operation.get("type", "")
    heading = operation.get("heading", "")
    new_content = operation.get("content", "")

    if op_type == "replace_section":
        return _op_replace_section(content, heading, new_content)
    elif op_type == "append_to_section":
        return _op_append_to_section(content, heading, new_content)
    elif op_type == "prepend_to_section":
        return _op_prepend_to_section(content, heading, new_content)
    elif op_type == "add_section":
        after = operation.get("after", "")
        return _op_add_section(content, heading, new_content, after)
    elif op_type == "delete_section":
        return _op_delete_section(content, heading)
    else:
        raise ValueError(f"Type d'opération inconnu: {op_type}")


def _op_replace_section(content: str, heading: str, new_content: str) -> str:
    """
    Remplace le contenu d'une section (entre le heading et le prochain
    heading de même niveau ou supérieur).

    Le heading lui-même est conservé.
    """
    sections = _parse_sections(content)
    idx = _find_section_index(sections, heading)

    if idx == -1:
        raise ValueError(f"Section non trouvée: {heading}")

    # Remplacer le contenu de la section
    # S'assurer que le nouveau contenu commence et finit proprement
    if new_content and not new_content.startswith("\n"):
        new_content = "\n" + new_content
    if new_content and not new_content.endswith("\n"):
        new_content = new_content + "\n"

    sections[idx]["content"] = new_content

    return _reconstruct_from_sections(sections)


def _op_append_to_section(content: str, heading: str, new_content: str) -> str:
    """
    Ajoute du contenu à la fin d'une section existante.
    Le contenu existant est intégralement préservé.
    """
    sections = _parse_sections(content)
    idx = _find_section_index(sections, heading)

    if idx == -1:
        raise ValueError(f"Section non trouvée: {heading}")

    existing = sections[idx]["content"]

    # Ajouter le nouveau contenu après l'existant
    if existing.rstrip():
        sections[idx]["content"] = existing.rstrip("\n") + "\n" + new_content + "\n"
    else:
        sections[idx]["content"] = "\n" + new_content + "\n"

    return _reconstruct_from_sections(sections)


def _op_prepend_to_section(content: str, heading: str, new_content: str) -> str:
    """
    Ajoute du contenu au début d'une section (après le heading).
    Le contenu existant est intégralement préservé.
    """
    sections = _parse_sections(content)
    idx = _find_section_index(sections, heading)

    if idx == -1:
        raise ValueError(f"Section non trouvée: {heading}")

    existing = sections[idx]["content"]

    # Ajouter le nouveau contenu avant l'existant
    if existing.lstrip():
        sections[idx]["content"] = "\n" + new_content + "\n" + existing.lstrip("\n")
    else:
        sections[idx]["content"] = "\n" + new_content + "\n"

    return _reconstruct_from_sections(sections)


def _op_add_section(
    content: str, heading: str, new_content: str, after: str = ""
) -> str:
    """
    Ajoute une nouvelle section au fichier.

    Si 'after' est spécifié, insère après cette section.
    Sinon, ajoute à la fin du fichier.
    """
    sections = _parse_sections(content)

    # Déterminer le niveau du heading
    heading_match = re.match(r"^(#{1,6})\s+(.+)$", heading.strip())
    if heading_match:
        level = len(heading_match.group(1))
        heading_text = heading_match.group(2).strip()
    else:
        # Pas de # → on assume ## (section de 2ème niveau)
        level = 2
        heading_text = heading.strip()
        heading = f"## {heading_text}"

    new_section = {
        "heading": heading,
        "heading_text": heading_text,
        "level": level,
        "content": "\n" + new_content + "\n",
        "start_line": -1,
    }

    if after:
        # Insérer après la section spécifiée
        idx = _find_section_index(sections, after)
        if idx != -1:
            sections.insert(idx + 1, new_section)
        else:
            # Section 'after' non trouvée → ajouter à la fin
            logger.warning(
                "Section 'after' non trouvée: %s — ajout en fin de fichier", after
            )
            sections.append(new_section)
    else:
        sections.append(new_section)

    return _reconstruct_from_sections(sections)


def _op_delete_section(content: str, heading: str) -> str:
    """
    Supprime une section entière (heading + contenu).
    """
    sections = _parse_sections(content)
    idx = _find_section_index(sections, heading)

    if idx == -1:
        raise ValueError(f"Section non trouvée pour suppression: {heading}")

    # Supprimer la section
    sections.pop(idx)

    return _reconstruct_from_sections(sections)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """
    Extrait le JSON d'une réponse LLM qui peut le contenir dans :
    - Un bloc ```json ... ```
    - Un bloc <think>...</think> suivi de JSON
    - Du texte brut avec un objet JSON {}

    Args:
        text: Réponse brute du LLM

    Returns:
        Chaîne JSON nettoyée prête pour json.loads()
    """
    # 1. Retirer les blocs <think>...</think> (Qwen thinking mode)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # 2. Chercher un bloc ```json ... ```
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 3. Chercher un bloc ``` ... ```
    match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        if candidate.startswith("{"):
            return candidate

    # 4. Chercher le premier { ... } (objet JSON brut)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]

    # 5. Retourner le texte tel quel (json.loads() échouera)
    return text.strip()


def _convert_legacy_format(data: dict) -> dict:
    """
    Convertit l'ancien format de réponse LLM (bank_files) vers le nouveau
    format (file_edits). Sert de filet de sécurité si le LLM retombe
    sur l'ancien format malgré le nouveau prompt.

    Ancien format:
        {"bank_files": [{"filename": "x.md", "content": "...", "action": "updated"}]}

    Nouveau format:
        {"file_edits": [{"filename": "x.md", "action": "rewrite", "content": "..."}]}
    """
    file_edits = []
    for bf in data.get("bank_files", []):
        old_action = bf.get("action", "updated")
        file_edits.append({
            "filename": bf.get("filename", ""),
            "action": "create" if old_action == "created" else "rewrite",
            "content": bf.get("content", ""),
            "reason": "Legacy format conversion (LLM used old bank_files format)",
        })

    return {
        "file_edits": file_edits,
        "synthesis": data.get("synthesis", ""),
    }


# ─────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────

_consolidator: ConsolidatorService | None = None


def get_consolidator() -> ConsolidatorService:
    """Retourne le singleton ConsolidatorService."""
    global _consolidator
    if _consolidator is None:
        _consolidator = ConsolidatorService()
    return _consolidator
