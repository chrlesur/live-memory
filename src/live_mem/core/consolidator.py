# -*- coding: utf-8 -*-
"""
Service Consolidator — Pipeline LLM pour la consolidation notes → bank.

C'est le cœur intelligent de Live Memory. Le pipeline :
1. Collecte : rules + synthèse précédente + notes live + bank actuelle
2. Prompt : construit le prompt LLM (system + user)
3. Appel LLM : une seule requête à qwen3-2507:235b, réponse JSON
4. Écriture : bank files + synthesis + suppression notes + update meta

Principes :
    - Les agents n'écrivent JAMAIS dans la bank — seul le LLM le fait
    - Les notes sont supprimées UNIQUEMENT après succès complet (atomicité)
    - Un seul consolidate à la fois par espace (asyncio.Lock)

Voir CONSOLIDATION_LLM.md pour les détails du pipeline et des prompts.
"""

import sys
import re
import json
import time
from datetime import datetime, timezone
from typing import Optional

from openai import AsyncOpenAI

from ..config import get_settings
from .storage import get_storage


# ─────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un assistant spécialisé dans la maintenance de Memory Banks pour des projets.

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
- Si un fichier bank n'a pas besoin de modification, NE L'INCLUS PAS dans bank_files"""


class ConsolidatorService:
    """
    Service de consolidation LLM : transforme les notes live en bank.

    Utilise AsyncOpenAI pour communiquer avec le LLMaaS Cloud Temple.
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
            2. Construire le prompt LLM
            3. Appeler le LLM
            4. Écrire les résultats (bank, synthesis, supprimer notes de l'agent)

        Args:
            space_id: Identifiant de l'espace à consolider
            agent: Nom de l'agent appelant (filtre les notes à consolider)

        Returns:
            Métriques de consolidation ou erreur
        """
        t0 = time.monotonic()
        storage = get_storage()

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

        # ── Étape 4 : Écrire les résultats ────────────────
        write_result = await self._write_results(
            space_id=space_id,
            llm_output=llm_result["data"],
            notes_keys=inputs["notes_keys"],
            notes_count=len(inputs["notes"]),
            usage=llm_result.get("usage", {}),
        )

        write_result["duration_seconds"] = round(time.monotonic() - t0, 1)
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

        Returns:
            Liste de messages [{"role": "system", ...}, {"role": "user", ...}]
        """
        # Construire la section notes
        notes_section = ""
        for i, note in enumerate(notes, 1):
            content = note["content"]
            notes_section += f"\n--- Note {i}/{len(notes)} ---\n{content}\n"

        # Construire la section bank
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
                "Aucun fichier bank — première consolidation, "
                "créer les fichiers selon les rules."
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

=== CONSIGNES ===
Retourne un JSON avec cette structure exacte :
{{
  "bank_files": [
    {{
      "filename": "nom_du_fichier.md",
      "content": "contenu complet du fichier en Markdown",
      "action": "created" ou "updated"
    }}
  ],
  "synthesis": "Contenu Markdown de la synthèse résiduelle"
}}

IMPORTANT :
- N'inclus QUE les fichiers qui ont été modifiés ou créés
- Les fichiers inchangés NE DOIVENT PAS apparaître dans bank_files
- La synthèse résiduelle doit résumer les notes traitées
- Le contenu des fichiers bank doit être du Markdown pur"""

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
                    # Note: response_format non supporté par tous les endpoints
                    # On parse manuellement le JSON depuis la réponse
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
                        print(
                            f"⚠️  LLM: JSON invalide (attempt {attempt+1}), retry...",
                            file=sys.stderr,
                        )
                        messages.append({"role": "assistant", "content": raw_content})
                        messages.append({
                            "role": "user",
                            "content": (
                                "Ta réponse n'est pas du JSON valide. "
                                "Retourne UNIQUEMENT un objet JSON valide."
                            ),
                        })
                        continue
                    return {
                        "status": "error",
                        "message": "LLM returned invalid JSON after retry",
                    }

                # Valider la structure minimale
                if "bank_files" not in data or "synthesis" not in data:
                    if attempt == 0:
                        continue
                    return {
                        "status": "error",
                        "message": "LLM response missing bank_files or synthesis",
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
        notes_keys: list[str],
        notes_count: int,
        usage: dict,
    ) -> dict:
        """
        Étape 4 : Écrire les résultats sur S3.

        Ordre : bank files → synthesis → meta → delete notes.
        Les notes sont supprimées EN DERNIER (atomicité logique).

        Returns:
            Métriques de consolidation
        """
        storage = get_storage()

        files_created = 0
        files_updated = 0

        # 4a. Écrire chaque fichier bank
        for file_entry in llm_output.get("bank_files", []):
            filename = file_entry.get("filename", "")
            content = file_entry.get("content", "")
            action = file_entry.get("action", "updated")

            if filename and content:
                await storage.put(f"{space_id}/bank/{filename}", content)
                if action == "created":
                    files_created += 1
                else:
                    files_updated += 1

        # 4b. Écrire la synthèse résiduelle
        synthesis_content = llm_output.get("synthesis", "")
        now = datetime.now(timezone.utc).isoformat()
        synthesis_md = (
            f"---\n"
            f"consolidated_at: \"{now}\"\n"
            f"notes_processed: {notes_count}\n"
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
            "synthesis_size": len(synthesis_content),
            "llm_tokens_used": usage.get("total_tokens", 0),
            "llm_prompt_tokens": usage.get("prompt_tokens", 0),
            "llm_completion_tokens": usage.get("completion_tokens", 0),
        }

    async def test_connection(self) -> dict:
        """Teste la connexion au LLMaaS avec un appel minimal."""
        try:
            t0 = time.monotonic()
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "Réponds OK"}],
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
    # On cherche la première accolade ouvrante et la dernière fermante
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace + 1]

    # 5. Retourner le texte tel quel (json.loads() échouera)
    return text.strip()


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
