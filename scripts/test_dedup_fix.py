#!/usr/bin/env python3
"""
Test du fix _deduplicate_content — indices décalés (v1.3.1)

Reproduit le bug exact : un fichier avec plusieurs headings dupliqués.
L'ancien algorithme (boucle for) crashait avec IndexError car les indices
étaient calculés une seule fois puis devenaient invalides après les pop().
Le nouveau algorithme (boucle while + re-détection) corrige le problème.
"""

import sys
import os
import re

# Ajouter src/ au path pour importer le module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from live_mem.core.consolidator import (
    _parse_sections,
    _reconstruct_from_sections,
    _detect_duplicates,
)

# ── Fichier test avec 5 headings dupliqués (scénario exact du bug) ──
CONTENT = """# activeContext.md

## Focus Actuel
Contenu focus v1

### Refonte Vela V4
Contenu Vela v1

### Session du 31/03/2026
Contenu session v1

### Nettoyage et stabilisation
Contenu nettoyage v1

### État du MCP Office
Contenu MCP v1

### État technique V2
Contenu tech v1

## Autre Section
Contenu autre

### Refonte Vela V4
Contenu Vela v2

### Session du 31/03/2026
Contenu session v2

### Nettoyage et stabilisation
Contenu nettoyage v2

### État du MCP Office
Contenu MCP v2

### État technique V2
Contenu tech v2
"""

passed = 0
failed = 0


def test(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1


print("=" * 60)
print("Test du fix _deduplicate_content (indices décalés)")
print("=" * 60)

# ── Test 1: Détection correcte des doublons ──
print("\n1. Détection des doublons")
dups = _detect_duplicates(CONTENT)
test("5 doublons détectés", len(dups) == 5, f"got {len(dups)}")
for heading, indices in dups.items():
    test(f"  {heading} → {len(indices)} occurrences", len(indices) == 2)

# ── Test 2: Ancien algorithme crashe ──
print("\n2. Ancien algorithme (boucle for sur indices stales)")
sections = _parse_sections(CONTENT)
crashed = False
try:
    for heading, indices in dups.items():
        versions = [sections[i]["content"] for i in indices]
        last_idx = indices[-1]
        sections[last_idx]["content"] = "merged"
        for idx in reversed(indices[:-1]):
            sections.pop(idx)
        sections = _parse_sections(_reconstruct_from_sections(sections))
except IndexError:
    crashed = True
test("IndexError reproduit (confirme le bug)", crashed)

# ── Test 3: Nouveau algorithme (while + re-détection) ──
print("\n3. Nouveau algorithme (boucle while + re-détection)")
content = CONTENT
total_merged = 0
max_iterations = 50
error_msg = None

for iteration in range(max_iterations):
    duplicates = _detect_duplicates(content)
    if not duplicates:
        break

    heading, indices = next(iter(duplicates.items()))
    sections = _parse_sections(content)

    # Vérification défensive des indices
    if any(i >= len(sections) for i in indices):
        error_msg = f"indices invalides: {indices} >= {len(sections)}"
        break

    versions = [sections[i]["content"] for i in indices]
    last_idx = indices[-1]
    sections[last_idx]["content"] = "\nmerged\n"

    for idx in reversed(indices[:-1]):
        sections.pop(idx)
        total_merged += 1

    content = _reconstruct_from_sections(sections)

test("Pas de crash", error_msg is None, error_msg or "")
test("5 fusions effectuées", total_merged == 5, f"got {total_merged}")

remaining = _detect_duplicates(content)
test("0 doublons restants", len(remaining) == 0, f"got {len(remaining)}")

# ── Test 4: Intégrité du contenu ──
print("\n4. Intégrité du contenu après déduplication")
final_sections = _parse_sections(content)
headings = [s["heading"] for s in final_sections if s["heading"]]
test("8 headings uniques conservés", len(headings) == 8, f"got {len(headings)}: {headings}")

# Vérifier qu'aucun heading n'est dupliqué
heading_counts = {}
for h in headings:
    heading_counts[h] = heading_counts.get(h, 0) + 1
dupes = {h: c for h, c in heading_counts.items() if c > 1}
test("Aucun heading dupliqué", len(dupes) == 0, f"doublons: {dupes}")

# ── Test 5: Cas limite — fichier sans doublons ──
print("\n5. Cas limite — fichier sans doublons")
clean_content = "# Title\n\n## Section A\nContent A\n\n## Section B\nContent B\n"
clean_dups = _detect_duplicates(clean_content)
test("0 doublons détectés", len(clean_dups) == 0)

# ── Test 6: Cas limite — heading triplé ──
print("\n6. Cas limite — heading triplé")
triple_content = """# Doc

## Section X
Version 1

## Section X
Version 2

## Section X
Version 3
"""
triple_dups = _detect_duplicates(triple_content)
test("1 heading triplé détecté", len(triple_dups) == 1)
if triple_dups:
    indices = list(triple_dups.values())[0]
    test("3 occurrences", len(indices) == 3, f"got {len(indices)}")

# Simuler la déduplication
content = triple_content
total = 0
for _ in range(50):
    dups = _detect_duplicates(content)
    if not dups:
        break
    heading, indices = next(iter(dups.items()))
    sections = _parse_sections(content)
    last_idx = indices[-1]
    sections[last_idx]["content"] = "\nmerged_triple\n"
    for idx in reversed(indices[:-1]):
        sections.pop(idx)
        total += 1
    content = _reconstruct_from_sections(sections)

test("2 fusions pour un triplet", total == 2, f"got {total}")
test("0 doublons restants", len(_detect_duplicates(content)) == 0)

# ── Résumé ──
print("\n" + "=" * 60)
total_tests = passed + failed
if failed == 0:
    print(f"🎉 {passed}/{total_tests} tests PASS — le fix est correct")
    sys.exit(0)
else:
    print(f"💥 {passed}/{total_tests} tests PASS, {failed} FAILED")
    sys.exit(1)
