#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests unitaires pour le moteur d'édition Markdown chirurgical.

Teste toutes les opérations du moteur :
- _parse_sections : parsing d'un fichier Markdown en sections
- _find_section_index : recherche flexible de sections
- _reconstruct_from_sections : reconstruction du Markdown
- _apply_operation : routage des opérations
- _op_replace_section : remplacement de section
- _op_append_to_section : ajout en fin de section
- _op_prepend_to_section : ajout en début de section
- _op_add_section : création de nouvelle section
- _op_delete_section : suppression de section
- _convert_legacy_format : rétrocompatibilité ancien format

Usage:
    python scripts/test_markdown_engine.py
"""

import sys
import os

# Ajouter le répertoire src au path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from live_mem.core.consolidator import (
    _parse_sections,
    _find_section_index,
    _reconstruct_from_sections,
    _apply_operation,
    _op_replace_section,
    _op_append_to_section,
    _op_prepend_to_section,
    _op_add_section,
    _op_delete_section,
    _convert_legacy_format,
    _extract_json,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

SAMPLE_MD = """# activeContext.md

## Focus Actuel
Mise en place de la Memory Bank pour le projet Live Memory (v0.5.3).

## Travail Récent
- Analyse des 9 notes live initiales.
- Création des 6 fichiers obligatoires.
- Documentation de l'architecture.

## Prochaines Étapes
1. Webhooks consolidation automatique.
2. Métriques Prometheus.
3. Rules par défaut embarquées.

## Décisions Actives
- Triple validation des permissions (v0.5.3).
- Token ≠ Agent.

## Insights Récents
- L'absence de validation côté serveur avait causé un bug critique.
- L'extraction JSON manuelle est robuste.

## Questions en Cours
- Quelle est la stratégie d'authentification pour les webhooks ?
- Comment standardiser les rules de mémoire par défaut ?"""

SIMPLE_MD = """# Titre

## Section A
Contenu A ligne 1
Contenu A ligne 2

## Section B
Contenu B

## Section C
Contenu C"""

PROGRESS_MD = """# progress.md

## Historique des Versions
- **v0.1.0** (20/02/2026) : 25 outils MCP.
- **v0.2.0** (21/02) : GC, multi-agents.
- **v0.3.0** (21/02) : Graph Bridge.

## Ce Qui Fonctionne
- 32 outils MCP.
- Interface web SPA.

## Problèmes Connus
- Aucun problème critique.

## Backlog / Roadmap
- Webhooks consolidation automatique
- Métriques Prometheus"""


# ─────────────────────────────────────────────────────────────
# Compteurs de tests
# ─────────────────────────────────────────────────────────────

passed = 0
failed = 0
total = 0


def test(name: str, condition: bool, detail: str = ""):
    """Exécute un test et affiche le résultat."""
    global passed, failed, total
    total += 1
    if condition:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}")
        if detail:
            # Afficher les 3 premières lignes du détail
            lines = detail.split("\n")[:5]
            for line in lines:
                print(f"     {line}")


# ─────────────────────────────────────────────────────────────
# Tests : _parse_sections
# ─────────────────────────────────────────────────────────────

def test_parse_sections():
    """Tests du parsing Markdown en sections."""
    print("\n🔍 _parse_sections")

    sections = _parse_sections(SIMPLE_MD)

    # Nombre de sections (préambule vide + # Titre + ## A + ## B + ## C)
    test("Nombre de sections = 5 (preamble + 4 headings)",
         len(sections) == 5,
         f"Got {len(sections)} sections: {[s['heading'] for s in sections]}")

    # Le préambule est vide
    test("Préambule vide (level=0, heading='')",
         sections[0]["level"] == 0 and sections[0]["heading"] == "")

    # Section # Titre
    test("Section 1 = '# Titre' (level 1)",
         sections[1]["heading"] == "# Titre" and sections[1]["level"] == 1)

    # Section ## Section A
    test("Section 2 = '## Section A' avec contenu",
         sections[2]["heading"] == "## Section A"
         and "Contenu A ligne 1" in sections[2]["content"])

    # Contenu de Section A contient les 2 lignes
    test("Section A contient 2 lignes de contenu",
         "Contenu A ligne 1" in sections[2]["content"]
         and "Contenu A ligne 2" in sections[2]["content"])

    # Section B
    test("Section B = '## Section B' avec contenu",
         sections[3]["heading"] == "## Section B"
         and "Contenu B" in sections[3]["content"])

    # Test avec le fichier plus complexe
    sections2 = _parse_sections(SAMPLE_MD)
    headings = [s["heading"] for s in sections2 if s["heading"]]
    test("SAMPLE_MD a 7 headings",
         len(headings) == 7,
         f"Headings: {headings}")

    test("SAMPLE_MD contient '## Focus Actuel'",
         any(s["heading"] == "## Focus Actuel" for s in sections2))


# ─────────────────────────────────────────────────────────────
# Tests : _find_section_index
# ─────────────────────────────────────────────────────────────

def test_find_section_index():
    """Tests de la recherche flexible de sections."""
    print("\n🔍 _find_section_index")

    sections = _parse_sections(SAMPLE_MD)

    # Correspondance exacte
    idx = _find_section_index(sections, "## Focus Actuel")
    test("Correspondance exacte '## Focus Actuel'",
         idx != -1 and sections[idx]["heading"] == "## Focus Actuel",
         f"idx={idx}")

    # Correspondance exacte avec # Titre
    idx = _find_section_index(sections, "# activeContext.md")
    test("Correspondance exacte '# activeContext.md'",
         idx != -1 and sections[idx]["heading"] == "# activeContext.md")

    # Sans les # (le LLM omet parfois les ##)
    idx = _find_section_index(sections, "Focus Actuel")
    test("Sans # : 'Focus Actuel' → trouve '## Focus Actuel'",
         idx != -1 and sections[idx]["heading"] == "## Focus Actuel")

    # Case-insensitive
    idx = _find_section_index(sections, "focus actuel")
    test("Case-insensitive : 'focus actuel' → trouve '## Focus Actuel'",
         idx != -1 and sections[idx]["heading"] == "## Focus Actuel")

    # Section inexistante
    idx = _find_section_index(sections, "## Inexistante")
    test("Section inexistante retourne -1",
         idx == -1)


# ─────────────────────────────────────────────────────────────
# Tests : _reconstruct_from_sections
# ─────────────────────────────────────────────────────────────

def test_reconstruct():
    """Test de la reconstruction du Markdown depuis les sections."""
    print("\n🔍 _reconstruct_from_sections")

    sections = _parse_sections(SIMPLE_MD)
    reconstructed = _reconstruct_from_sections(sections)

    # Le contenu reconstruit doit contenir tous les éléments
    test("Reconstruction contient '# Titre'",
         "# Titre" in reconstructed)
    test("Reconstruction contient '## Section A'",
         "## Section A" in reconstructed)
    test("Reconstruction contient 'Contenu A ligne 1'",
         "Contenu A ligne 1" in reconstructed)
    test("Reconstruction contient 'Contenu B'",
         "Contenu B" in reconstructed)
    test("Reconstruction contient 'Contenu C'",
         "Contenu C" in reconstructed)

    # Le nombre de headings doit être préservé
    heading_count = sum(1 for line in reconstructed.split("\n")
                        if line.startswith("#"))
    test("Reconstruction préserve 4 headings",
         heading_count == 4,
         f"Got {heading_count}")


# ─────────────────────────────────────────────────────────────
# Tests : Idempotence (parse → reconstruct = identité)
# ─────────────────────────────────────────────────────────────

def test_idempotence():
    """Test que parse → reconstruct ne perd pas d'information."""
    print("\n🔍 Idempotence (parse → reconstruct)")

    for name, md in [("SIMPLE_MD", SIMPLE_MD), ("SAMPLE_MD", SAMPLE_MD), ("PROGRESS_MD", PROGRESS_MD)]:
        sections = _parse_sections(md)
        reconstructed = _reconstruct_from_sections(sections)

        # Vérifier que toutes les lignes non-vides sont préservées
        original_lines = set(line.strip() for line in md.split("\n") if line.strip())
        reconstructed_lines = set(line.strip() for line in reconstructed.split("\n") if line.strip())
        missing = original_lines - reconstructed_lines

        test(f"{name} : aucune ligne perdue",
             len(missing) == 0,
             f"Lignes manquantes: {missing}" if missing else "")


# ─────────────────────────────────────────────────────────────
# Tests : _op_replace_section
# ─────────────────────────────────────────────────────────────

def test_replace_section():
    """Tests du remplacement de section."""
    print("\n🔍 _op_replace_section")

    # Remplacement basique
    result = _op_replace_section(SIMPLE_MD, "## Section B", "Nouveau contenu B")
    test("Remplacement de Section B",
         "Nouveau contenu B" in result and "Contenu B" not in result)

    # Le heading est préservé
    test("Le heading '## Section B' est préservé",
         "## Section B" in result)

    # Les autres sections sont intactes
    test("Section A intacte après remplacement de B",
         "Contenu A ligne 1" in result and "Contenu A ligne 2" in result)
    test("Section C intacte après remplacement de B",
         "Contenu C" in result)

    # Remplacement avec correspondance flexible
    result2 = _op_replace_section(SIMPLE_MD, "Section B", "Flex contenu")
    test("Remplacement avec heading flexible (sans ##)",
         "Flex contenu" in result2)

    # Section inexistante → ValueError
    try:
        _op_replace_section(SIMPLE_MD, "## Inexistante", "foo")
        test("Section inexistante lève ValueError", False)
    except ValueError:
        test("Section inexistante lève ValueError", True)


# ─────────────────────────────────────────────────────────────
# Tests : _op_append_to_section
# ─────────────────────────────────────────────────────────────

def test_append_to_section():
    """Tests de l'ajout en fin de section."""
    print("\n🔍 _op_append_to_section")

    # Append basique
    result = _op_append_to_section(SIMPLE_MD, "## Section A", "- Nouvel élément")
    test("Append ajoute le nouveau contenu",
         "- Nouvel élément" in result)
    test("Append préserve le contenu existant",
         "Contenu A ligne 1" in result and "Contenu A ligne 2" in result)

    # L'ordre est correct : existant PUIS nouveau
    lines = result.split("\n")
    idx_existing = None
    idx_new = None
    for i, line in enumerate(lines):
        if "Contenu A ligne 2" in line:
            idx_existing = i
        if "Nouvel élément" in line:
            idx_new = i
    test("L'ordre est correct (existant avant nouveau)",
         idx_existing is not None and idx_new is not None and idx_existing < idx_new,
         f"existing={idx_existing}, new={idx_new}")

    # Append sur progress.md (cas réel)
    result_prog = _op_append_to_section(
        PROGRESS_MD,
        "## Historique des Versions",
        "- **v0.5.4** (10/03) : Consolidation chirurgicale."
    )
    test("Append sur Historique préserve les anciennes versions",
         "v0.1.0" in result_prog and "v0.2.0" in result_prog and "v0.3.0" in result_prog)
    test("Append sur Historique ajoute la nouvelle version",
         "v0.5.4" in result_prog)

    # Les autres sections sont intactes
    test("Sections Ce Qui Fonctionne et Problèmes Connus intactes",
         "32 outils MCP" in result_prog and "Aucun problème critique" in result_prog)


# ─────────────────────────────────────────────────────────────
# Tests : _op_prepend_to_section
# ─────────────────────────────────────────────────────────────

def test_prepend_to_section():
    """Tests de l'ajout en début de section."""
    print("\n🔍 _op_prepend_to_section")

    result = _op_prepend_to_section(SIMPLE_MD, "## Section B", "Ajout au début")
    test("Prepend ajoute le contenu",
         "Ajout au début" in result)
    test("Prepend préserve le contenu existant",
         "Contenu B" in result)

    # L'ordre est correct : nouveau PUIS existant
    lines = result.split("\n")
    idx_new = None
    idx_existing = None
    for i, line in enumerate(lines):
        if "Ajout au début" in line:
            idx_new = i
        if "Contenu B" in line and "Ajout" not in line:
            idx_existing = i
    test("L'ordre est correct (nouveau avant existant)",
         idx_new is not None and idx_existing is not None and idx_new < idx_existing,
         f"new={idx_new}, existing={idx_existing}")


# ─────────────────────────────────────────────────────────────
# Tests : _op_add_section
# ─────────────────────────────────────────────────────────────

def test_add_section():
    """Tests de l'ajout de nouvelle section."""
    print("\n🔍 _op_add_section")

    # Ajout à la fin
    result = _op_add_section(SIMPLE_MD, "## Section D", "Contenu D")
    test("Ajout de Section D à la fin",
         "## Section D" in result and "Contenu D" in result)

    # Les sections existantes sont intactes
    test("Sections existantes intactes après ajout",
         "## Section A" in result and "## Section B" in result and "## Section C" in result)

    # Ajout après une section spécifique
    result2 = _op_add_section(SIMPLE_MD, "## Section D", "Contenu D", after="## Section A")
    lines = result2.split("\n")
    idx_a = None
    idx_d = None
    idx_b = None
    for i, line in enumerate(lines):
        if line == "## Section A":
            idx_a = i
        if line == "## Section D":
            idx_d = i
        if line == "## Section B":
            idx_b = i
    test("Section D insérée après Section A et avant Section B",
         idx_a is not None and idx_d is not None and idx_b is not None
         and idx_a < idx_d < idx_b,
         f"A={idx_a}, D={idx_d}, B={idx_b}")

    # Ajout avec heading sans # (auto-détection ## )
    result3 = _op_add_section(SIMPLE_MD, "Nouvelle Section", "Contenu nouveau")
    test("Heading sans # → auto-complété en '## Nouvelle Section'",
         "## Nouvelle Section" in result3)


# ─────────────────────────────────────────────────────────────
# Tests : _op_delete_section
# ─────────────────────────────────────────────────────────────

def test_delete_section():
    """Tests de la suppression de section."""
    print("\n🔍 _op_delete_section")

    result = _op_delete_section(SIMPLE_MD, "## Section B")
    test("Section B supprimée (heading absent)",
         "## Section B" not in result)
    test("Contenu de Section B supprimé",
         "Contenu B" not in result)
    test("Sections A et C intactes",
         "## Section A" in result and "Contenu A ligne 1" in result
         and "## Section C" in result and "Contenu C" in result)

    # Section inexistante → ValueError
    try:
        _op_delete_section(SIMPLE_MD, "## Inexistante")
        test("Suppression section inexistante lève ValueError", False)
    except ValueError:
        test("Suppression section inexistante lève ValueError", True)


# ─────────────────────────────────────────────────────────────
# Tests : _apply_operation (routage)
# ─────────────────────────────────────────────────────────────

def test_apply_operation():
    """Tests du routage des opérations."""
    print("\n🔍 _apply_operation (routage)")

    # replace_section
    result = _apply_operation(SIMPLE_MD, {
        "type": "replace_section",
        "heading": "## Section A",
        "content": "Nouveau A"
    })
    test("Routage replace_section fonctionne",
         "Nouveau A" in result)

    # append_to_section
    result = _apply_operation(SIMPLE_MD, {
        "type": "append_to_section",
        "heading": "## Section A",
        "content": "- Ajout"
    })
    test("Routage append_to_section fonctionne",
         "- Ajout" in result and "Contenu A ligne 1" in result)

    # Type inconnu → ValueError
    try:
        _apply_operation(SIMPLE_MD, {"type": "unknown_op", "heading": "## A"})
        test("Type inconnu lève ValueError", False)
    except ValueError:
        test("Type inconnu lève ValueError", True)


# ─────────────────────────────────────────────────────────────
# Tests : Opérations multiples chaînées
# ─────────────────────────────────────────────────────────────

def test_chained_operations():
    """Tests d'opérations multiples appliquées en séquence."""
    print("\n🔍 Opérations chaînées")

    content = SAMPLE_MD

    # 1. Remplacer le focus
    content = _apply_operation(content, {
        "type": "replace_section",
        "heading": "## Focus Actuel",
        "content": "Nouveau focus : consolidation chirurgicale"
    })

    # 2. Ajouter une entrée au travail récent
    content = _apply_operation(content, {
        "type": "append_to_section",
        "heading": "## Travail Récent",
        "content": "- Implémentation du moteur d'édition Markdown."
    })

    # 3. Supprimer une section
    content = _apply_operation(content, {
        "type": "delete_section",
        "heading": "## Questions en Cours"
    })

    # Vérifications
    test("Focus remplacé",
         "consolidation chirurgicale" in content
         and "Memory Bank pour le projet" not in content)

    test("Travail Récent enrichi (existant préservé + nouveau)",
         "Analyse des 9 notes live initiales" in content
         and "moteur d'édition Markdown" in content)

    test("Questions en Cours supprimées",
         "## Questions en Cours" not in content
         and "stratégie d'authentification" not in content)

    test("Décisions Actives intactes (non touchées)",
         "## Décisions Actives" in content
         and "Triple validation" in content)

    test("Insights Récents intacts (non touchés)",
         "## Insights Récents" in content
         and "extraction JSON manuelle" in content)


# ─────────────────────────────────────────────────────────────
# Tests : _convert_legacy_format
# ─────────────────────────────────────────────────────────────

def test_legacy_format():
    """Tests de la conversion de l'ancien format."""
    print("\n🔍 _convert_legacy_format")

    old_data = {
        "bank_files": [
            {"filename": "activeContext.md", "content": "# Active\n\nContent", "action": "updated"},
            {"filename": "new_file.md", "content": "# New\n\nContent", "action": "created"},
        ],
        "synthesis": "Synthèse test"
    }

    new_data = _convert_legacy_format(old_data)

    test("Conversion produit file_edits",
         "file_edits" in new_data)
    test("2 file_edits",
         len(new_data["file_edits"]) == 2)

    # updated → rewrite
    test("'updated' converti en action 'rewrite'",
         new_data["file_edits"][0]["action"] == "rewrite")

    # created → create
    test("'created' converti en action 'create'",
         new_data["file_edits"][1]["action"] == "create")

    test("Synthesis préservée",
         new_data["synthesis"] == "Synthèse test")


# ─────────────────────────────────────────────────────────────
# Tests : _extract_json (existant, vérifie non-régression)
# ─────────────────────────────────────────────────────────────

def test_extract_json():
    """Tests de l'extraction JSON (non-régression)."""
    print("\n🔍 _extract_json")

    # JSON dans un bloc ```json
    result = _extract_json('Some text\n```json\n{"key": "value"}\n```\nMore text')
    test("Extraction depuis ```json bloc",
         '"key"' in result and '"value"' in result)

    # JSON avec <think>
    result = _extract_json('<think>internal reasoning</think>{"key": "value"}')
    test("Extraction avec <think> block",
         '"key"' in result)

    # JSON brut
    result = _extract_json('{"file_edits": [], "synthesis": "test"}')
    test("Extraction JSON brut",
         '"file_edits"' in result)


# ─────────────────────────────────────────────────────────────
# Tests : Cas limites
# ─────────────────────────────────────────────────────────────

def test_edge_cases():
    """Tests des cas limites."""
    print("\n🔍 Cas limites")

    # Fichier vide
    sections = _parse_sections("")
    test("Fichier vide → 1 section (préambule vide)",
         len(sections) == 1 and sections[0]["heading"] == "")

    # Fichier sans heading
    sections = _parse_sections("Juste du texte\nSur plusieurs lignes")
    test("Fichier sans heading → 1 section préambule",
         len(sections) == 1 and "Juste du texte" in sections[0]["content"])

    # Heading seul sans contenu
    sections = _parse_sections("## Section Vide")
    test("Heading seul → section avec contenu vide",
         len(sections) == 2 and sections[1]["heading"] == "## Section Vide")

    # Sections avec sous-niveaux
    nested_md = """# Titre
## Section A
Contenu A
### Sous-section A1
Contenu A1
## Section B
Contenu B"""
    sections = _parse_sections(nested_md)
    headings = [s["heading"] for s in sections if s["heading"]]
    test("Parsing avec sous-niveaux : 4 headings",
         len(headings) == 4,
         f"Headings: {headings}")

    # Replace section ne touche pas les sous-sections
    result = _op_replace_section(nested_md, "## Section A", "Nouveau contenu A")
    test("Replace Section A remplace son contenu",
         "Nouveau contenu A" in result and "Contenu A\n" not in result)
    test("Section B intacte après replace de A",
         "## Section B" in result and "Contenu B" in result)

    # Heading avec caractères spéciaux
    special_md = """## Problèmes Connus & Solutions
Contenu spécial: accents éàü, symboles #@!
## Section Normale
Normal"""
    sections = _parse_sections(special_md)
    test("Heading avec caractères spéciaux parsé correctement",
         any("Problèmes Connus & Solutions" in s["heading"] for s in sections))


# ─────────────────────────────────────────────────────────────
# Tests : Scénario réaliste complet
# ─────────────────────────────────────────────────────────────

def test_realistic_scenario():
    """Simule un scénario complet de consolidation chirurgicale."""
    print("\n🔍 Scénario réaliste complet")

    # Point de départ : le progress.md actuel
    content = PROGRESS_MD

    # Le LLM produit ces opérations après consolidation de 5 notes
    operations = [
        {
            "type": "append_to_section",
            "heading": "## Historique des Versions",
            "content": "- **v0.5.4** (10/03) : Consolidation chirurgicale, moteur d'édition Markdown."
        },
        {
            "type": "append_to_section",
            "heading": "## Ce Qui Fonctionne",
            "content": "- Consolidation LLM chirurgicale (zéro perte de matière)."
        },
        {
            "type": "replace_section",
            "heading": "## Problèmes Connus",
            "content": "- Aucun problème critique.\n- À surveiller : robustesse du parsing Markdown sur cas limites."
        },
    ]

    # Appliquer toutes les opérations
    for op in operations:
        content = _apply_operation(content, op)

    # Vérifier que TOUT l'historique est préservé
    test("v0.1.0 préservée", "v0.1.0" in content)
    test("v0.2.0 préservée", "v0.2.0" in content)
    test("v0.3.0 préservée", "v0.3.0" in content)
    test("v0.5.4 ajoutée", "v0.5.4" in content)

    # Vérifier les enrichissements
    test("'32 outils MCP' préservé", "32 outils MCP" in content)
    test("'Consolidation LLM chirurgicale' ajoutée",
         "Consolidation LLM chirurgicale" in content)

    # Vérifier le remplacement
    test("'À surveiller' ajouté dans Problèmes Connus",
         "À surveiller" in content)

    # Vérifier que la roadmap est intacte
    test("Backlog/Roadmap intacte",
         "Webhooks consolidation automatique" in content
         and "Métriques Prometheus" in content)

    # Compter les lignes non-vides pour vérifier qu'on n'a rien perdu
    original_lines = set(line.strip() for line in PROGRESS_MD.split("\n")
                         if line.strip() and "Aucun problème critique." not in line)
    result_lines = set(line.strip() for line in content.split("\n") if line.strip())
    missing = original_lines - result_lines

    test("Aucune ligne originale perdue (sauf section remplacée)",
         len(missing) == 0,
         f"Lignes manquantes: {missing}" if missing else "")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 Tests du moteur d'édition Markdown chirurgical")
    print("=" * 60)

    test_parse_sections()
    test_find_section_index()
    test_reconstruct()
    test_idempotence()
    test_replace_section()
    test_append_to_section()
    test_prepend_to_section()
    test_add_section()
    test_delete_section()
    test_apply_operation()
    test_chained_operations()
    test_legacy_format()
    test_extract_json()
    test_edge_cases()
    test_realistic_scenario()

    print("\n" + "=" * 60)
    if failed == 0:
        print(f"✅ TOUS LES TESTS PASSENT : {passed}/{total}")
    else:
        print(f"❌ ÉCHECS : {failed}/{total} tests échoués")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
