#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test multi-agents — 3 agents collaborent sur un même espace.

Scénario :
    Phase 1 : agent-infra + agent-dev écrivent en parallèle
    Phase 2 : Chacun consolide ses notes → bank se construit
    Phase 3 : agent-qa lit la bank, écrit ses notes QA
    Phase 4 : agent-qa consolide → bank finale

Usage :
    docker compose up -d
    python scripts/test_multi_agents.py
"""

import os, sys, json, time, asyncio, argparse

sys.path.insert(0, os.path.dirname(__file__))
from cli.client import MCPClient

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

SPACE_ID = "multi-agent-ubuntu"

RULES = """# Rules — Memory Bank Standard

La bank doit contenir 6 fichiers Markdown :

### projectbrief.md
Objectifs, périmètre, critères de succès.

### productContext.md
Pourquoi ce projet, problèmes résolus, fonctionnement attendu.

### activeContext.md
Focus actuel, changements récents, prochaines étapes, décisions.

### systemPatterns.md
Architecture, décisions techniques, design patterns, composants.

### techContext.md
Technologies, setup, contraintes, dépendances.

### progress.md
Ce qui fonctionne, ce qui reste, statut, problèmes connus.

## Hiérarchie
projectbrief → productContext, systemPatterns, techContext → activeContext → progress
"""

# Notes de l'agent-infra (infrastructure, réseau, OS)
NOTES_INFRA = [
    ("observation", "État initial infra",
     "Serveur prod-web-01 :\n"
     "- Ubuntu 22.04.4 LTS, noyau 5.15\n"
     "- 16 Go RAM, 4 vCPU, 40 Go disque\n"
     "- Réseau : 10.0.1.50/24, gateway 10.0.1.1\n"
     "- Firewall : ufw actif (22, 80, 443)"),
    ("decision", "Plan de migration OS",
     "do-release-upgrade samedi 02h00.\n"
     "- Snapshot VM avant\n"
     "- Fenêtre 4h max\n"
     "- Rollback si services KO après 1h"),
    ("progress", "Backup infra OK",
     "Backups complets :\n"
     "- /etc : 12 Mo\n"
     "- Snapshot VM créé\n"
     "- DNS TTL réduit à 60s (rollback rapide)"),
    ("progress", "OS upgradé",
     "Ubuntu 24.04.1 LTS installé.\n"
     "- Noyau 6.8.0-45\n"
     "- Boot propre, réseau OK\n"
     "- ufw règles conservées\n"
     "- Durée upgrade : 45 min"),
]

# Notes de l'agent-dev (applications, bases de données)
NOTES_DEV = [
    ("observation", "État initial apps",
     "Applications sur prod-web-01 :\n"
     "- WordPress 6.4 (PHP 8.1 + nginx)\n"
     "- API interne Flask (Python 3.10)\n"
     "- PostgreSQL 14, 3 bases, 2.1 Go\n"
     "- Redis 6.0 (cache sessions)"),
    ("issue", "PHP 8.1 supprimé",
     "Après upgrade OS, php8.1-fpm supprimé !\n"
     "WordPress et API PHP hors service.\n"
     "Python et Redis non impactés."),
    ("decision", "Migration PHP 8.3",
     "PHP 8.1 → 8.3 validé :\n"
     "- WordPress 6.4 compatible\n"
     "- Extensions : mbstring, xml, curl, pgsql OK\n"
     "- Pool FPM recréé avec mêmes paramètres"),
    ("progress", "Apps restaurées",
     "Toutes les applications fonctionnent :\n"
     "- WordPress OK sur PHP 8.3\n"
     "- API Flask OK (Python non impacté)\n"
     "- PostgreSQL 14 → 16 migration auto\n"
     "- Redis 6.0 → 7.0 migration auto"),
]

# Notes de l'agent-qa (validation, tests, signoff)
NOTES_QA = [
    ("observation", "Lecture bank pré-QA",
     "Bank lue avec bank_read_all.\n"
     "Les agents infra et dev ont documenté :\n"
     "- Migration OS réussie (infra)\n"
     "- Migration apps réussie (dev)\n"
     "- 2 issues résolues (PHP, PostgreSQL)"),
    ("observation", "Tests fonctionnels",
     "Tests manuels effectués :\n"
     "- WordPress : login admin OK, article créé OK\n"
     "- API Flask : endpoint /health 200, /users 200\n"
     "- PostgreSQL : SELECT count(*) OK sur 3 bases\n"
     "- Redis : PING → PONG, cache sessions actif"),
    ("observation", "Tests de performance",
     "Benchmarks post-migration :\n"
     "- WordPress TTFB : 180ms (avant : 210ms) ✅\n"
     "- API Flask : 45ms (avant : 48ms) ✅\n"
     "- PostgreSQL : queries 5% plus rapides\n"
     "- Pas de régression détectée"),
    ("issue", "Cron backup cassé",
     "Le cron /etc/cron.d/backup utilise /usr/bin/php8.1.\n"
     "Les backups nocturnes ne s'exécutent pas.\n"
     "Fix : remplacer par /usr/bin/php8.3."),
    ("progress", "Signoff QA",
     "VALIDATION COMPLÈTE ✅\n"
     "- Tous les tests passent\n"
     "- Performance améliorée\n"
     "- 1 issue mineure (cron) corrigée\n"
     "- Migration Ubuntu 24.04 VALIDÉE\n"
     "- Retour en production confirmé"),
]

# ═══════════════════════════════════════════════════════════════
# Affichage (même style que test_recette.py)
# ═══════════════════════════════════════════════════════════════

G="\033[92m"; R="\033[91m"; Y="\033[93m"; C="\033[96m"
M="\033[95m"; B="\033[1m"; D="\033[2m"; Z="\033[0m"

# Mode step-by-step global
STEP_MODE = False

def pause(msg="Appuyez sur Entrée pour continuer..."):
    """Pause step-by-step : attend une touche si le mode est activé."""
    if STEP_MODE:
        print(f"\n  {D}⏸  {msg}{Z}", end="", flush=True)
        input()
# Couleurs par agent
AGENT_COLOR = {"agent-infra": "\033[94m", "agent-dev": "\033[93m", "agent-qa": "\033[95m"}
CAT_EMOJI = {"observation":"🔍","decision":"🎯","todo":"📋",
             "progress":"📈","issue":"⚠️","insight":"💡"}

def header(t):
    print(f"\n{B}{C}{'═'*70}{Z}\n{B}{C}  {t}{Z}\n{B}{C}{'═'*70}{Z}")

def phase(n, t):
    print(f"\n{B}{M}{'─'*70}{Z}")
    print(f"{B}{M}  PHASE {n} : {t}{Z}")
    print(f"{B}{M}{'─'*70}{Z}")

def ok(t):   print(f"  {G}✅ {t}{Z}")
def warn(t): print(f"  {Y}⚠️  {t}{Z}")
def fail(t): print(f"  {R}❌ {t}{Z}")
def info(t): print(f"  {C}ℹ️  {t}{Z}")

def box(title, content, color=C):
    lines = content.split('\n')
    max_len = max(len(title), max((len(l) for l in lines), default=0))
    w = min(max(max_len + 4, 50), 100)
    print(f"  {color}┌{'─'*w}┐{Z}")
    print(f"  {color}│{Z} {B}{title}{Z}{' '*(w-len(title)-1)}{color}│{Z}")
    print(f"  {color}├{'─'*w}┤{Z}")
    for line in lines:
        pad = w - len(line) - 1
        if pad < 0:
            while len(line) > w - 2:
                chunk = line[:w-2]
                line = line[w-2:]
                print(f"  {color}│{Z} {chunk} {color}│{Z}")
            pad = w - len(line) - 1
        print(f"  {color}│{Z} {line}{' '*pad}{color}│{Z}")
    print(f"  {color}└{'─'*w}┘{Z}")

def show_note(agent, i, total, cat, title, content):
    emoji = CAT_EMOJI.get(cat, "📝")
    color = AGENT_COLOR.get(agent, C)
    box(f"{emoji} {agent} — Note {i}/{total} [{cat}] — {title}", content, color=color)

def show_bank(files):
    header("📘 ÉTAT DE LA MEMORY BANK")
    for f in files:
        box(f"📄 {f.get('filename','?')}", f.get("content","").strip(), color=M)

def show_result(result):
    s = result.get("status", "?")
    color = G if s in ("ok","created","deleted") else R
    print(f"  → status: {color}{s}{Z}")
    for k in ("notes_processed","bank_files_created","bank_files_updated",
              "llm_tokens_used","duration_seconds","total","file_count","total_size"):
        if k in result:
            print(f"    {k}: {result[k]}")


# ═══════════════════════════════════════════════════════════════
# Script principal
# ═══════════════════════════════════════════════════════════════

async def write_notes(client, agent_name, notes):
    """Écrit toutes les notes d'un agent (agent= explicite, indépendant du token)."""
    count = 0
    for i, (cat, title, content) in enumerate(notes):
        show_note(agent_name, i+1, len(notes), cat, title, content)
        try:
            r = await client.call_tool("live_note", {
                "space_id": SPACE_ID,
                "category": cat,
                "content": content,
                "agent": agent_name,  # Identité explicite, découplée du token
            })
            if r.get("status") in ("ok", "created"):
                count += 1
            else:
                fail(f"  {agent_name} note {i+1}: {r.get('message','?')}")
        except Exception as e:
            fail(f"  {agent_name} note {i+1}: {e}")
    return count


async def run(url, bootstrap_key, cleanup=True):
    admin = MCPClient(base_url=url, token=bootstrap_key, timeout=600)
    t0 = time.monotonic()
    errors = 0

    header("🧪 TEST MULTI-AGENTS — 3 agents collaborent")
    info(f"Serveur : {url}")
    info(f"Espace  : {SPACE_ID}")
    info("Agents  : agent-infra, agent-dev, agent-qa")

    # ── Setup : espace + 3 tokens ────────────────────
    phase(0, "SETUP — Espace + 3 tokens")

    # Créer l'espace avec la bootstrap key
    r = await admin.call_tool("space_create", {
        "space_id": SPACE_ID,
        "description": "Test multi-agents : migration Ubuntu 24.04",
        "rules": RULES,
    })
    if r.get("status") == "created":
        ok("Espace créé")
    elif r.get("status") == "already_exists":
        warn("Espace existe déjà")
    else:
        fail(f"Espace : {r}"); return 1

    # Créer 3 tokens
    agents = {}
    for name in ["agent-infra", "agent-dev", "agent-qa"]:
        r = await admin.call_tool("admin_create_token", {
            "name": name,
            "permissions": "read,write",
            "space_ids": SPACE_ID,
            "expires_in_days": 1,
        })
        if r.get("status") == "created":
            agents[name] = MCPClient(base_url=url, token=r["token"], timeout=600)
            ok(f"Token '{name}' créé")
        else:
            fail(f"Token '{name}': {r.get('message','?')}"); errors += 1

    if len(agents) < 3:
        fail("Pas assez de tokens"); return errors + 1

    pause("Setup terminé. Phase 1 : écriture des notes →")

    # ── Phase 1 : agent-infra et agent-dev en parallèle ──
    phase(1, "AGENT-INFRA + AGENT-DEV travaillent en parallèle")
    info("Les deux agents écrivent leurs notes simultanément...")

    header("🔵 NOTES DE L'AGENT-INFRA (infrastructure)")
    n1 = await write_notes(agents["agent-infra"], "agent-infra", NOTES_INFRA)

    header("🟡 NOTES DE L'AGENT-DEV (applications)")
    n2 = await write_notes(agents["agent-dev"], "agent-dev", NOTES_DEV)

    ok(f"agent-infra : {n1}/{len(NOTES_INFRA)} notes")
    ok(f"agent-dev   : {n2}/{len(NOTES_DEV)} notes")

    pause("Notes écrites. Phase 2 : consolidation LLM →")

    # ── Phase 2 : Consolidation par chaque agent ─────
    phase(2, "CONSOLIDATION — Chaque agent consolide ses notes")

    info("agent-infra consolide ses notes (agent='agent-infra')...")
    tc = time.monotonic()
    r1 = await agents["agent-infra"].call_tool("bank_consolidate", {
        "space_id": SPACE_ID, "agent": "agent-infra"})
    d1 = round(time.monotonic() - tc, 1)
    show_result(r1)
    ok(f"agent-infra : {r1.get('notes_processed',0)} notes consolidées en {d1}s")

    info("agent-dev consolide ses notes (agent='agent-dev')...")
    tc = time.monotonic()
    r2 = await agents["agent-dev"].call_tool("bank_consolidate", {
        "space_id": SPACE_ID, "agent": "agent-dev"})
    d2 = round(time.monotonic() - tc, 1)
    show_result(r2)
    ok(f"agent-dev : {r2.get('notes_processed',0)} notes consolidées en {d2}s")

    # Afficher la bank après consolidation des 2 agents
    r = await agents["agent-infra"].call_tool("bank_read_all", {"space_id": SPACE_ID})
    files = r.get("files", [])
    if files:
        ok(f"Bank après Phase 2 : {len(files)} fichiers ({r.get('total_size',0)} octets)")
        show_bank(files)
    else:
        warn("Aucun fichier bank après Phase 2")

    pause("Bank construite par infra+dev. Phase 3 : agent-qa arrive →")

    # ── Phase 3 : agent-qa arrive et lit la bank ─────
    phase(3, "AGENT-QA arrive, lit la bank, écrit ses notes")

    info("agent-qa lit la bank pour comprendre le contexte...")
    r = await agents["agent-qa"].call_tool("bank_read_all", {"space_id": SPACE_ID})
    ok(f"agent-qa a lu {r.get('file_count',0)} fichiers bank")

    header("🟣 NOTES DE L'AGENT-QA (validation)")
    n3 = await write_notes(agents["agent-qa"], "agent-qa", NOTES_QA)
    ok(f"agent-qa : {n3}/{len(NOTES_QA)} notes")

    pause("Notes QA écrites. Phase 4 : consolidation finale →")

    # ── Phase 4 : Consolidation finale par agent-qa ──
    phase(4, "CONSOLIDATION FINALE — agent-qa consolide")

    info("agent-qa consolide ses notes (agent='agent-qa')...")
    tc = time.monotonic()
    r3 = await agents["agent-qa"].call_tool("bank_consolidate", {
        "space_id": SPACE_ID, "agent": "agent-qa"})
    d3 = round(time.monotonic() - tc, 1)
    show_result(r3)
    ok(f"agent-qa : {r3.get('notes_processed',0)} notes consolidées en {d3}s")

    # Afficher la bank finale
    r = await agents["agent-qa"].call_tool("bank_read_all", {"space_id": SPACE_ID})
    files = r.get("files", [])
    if files:
        ok(f"Bank FINALE : {len(files)} fichiers ({r.get('total_size',0)} octets)")
        show_bank(files)

    # ── Nettoyage ─────────────────────────────────────
    if cleanup:
        phase(5, "NETTOYAGE")
        await admin.call_tool("space_delete", {"space_id": SPACE_ID, "confirm": True})
        ok("Espace supprimé")
        r = await admin.call_tool("admin_list_tokens", {})
        for t in r.get("tokens", []):
            if t.get("name") in agents and not t.get("revoked"):
                await admin.call_tool("admin_revoke_token", {"token_hash": t["hash"]})
                ok(f"Token '{t['name']}' révoqué")

    # ── Résumé ────────────────────────────────────────
    dur = round(time.monotonic() - t0, 1)
    header("📊 RÉSUMÉ MULTI-AGENTS")
    info(f"Durée totale      : {dur}s")
    info(f"agent-infra notes : {n1}/{len(NOTES_INFRA)}")
    info(f"agent-dev notes   : {n2}/{len(NOTES_DEV)}")
    info(f"agent-qa notes    : {n3}/{len(NOTES_QA)}")
    info(f"Consolidations    : 3 (infra + dev + qa)")
    info(f"Erreurs           : {errors}")
    if errors == 0:
        print(f"\n  {G}{B}🎉 TEST MULTI-AGENTS RÉUSSI !{Z}")
    else:
        print(f"\n  {R}{B}💥 TEST ÉCHOUÉ — {errors} erreur(s){Z}")
    return errors


# ═══════════════════════════════════════════════════════════════

def _read_key():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p):
        for l in open(p):
            if l.strip().startswith("ADMIN_BOOTSTRAP_KEY="):
                return l.strip().split("=",1)[1].strip()
    return ""

def main():
    ap = argparse.ArgumentParser(description="Test multi-agents Live Memory")
    ap.add_argument("--url", default=os.environ.get("MCP_URL","http://localhost:8080"))
    ap.add_argument("--token", default=os.environ.get("ADMIN_BOOTSTRAP_KEY",""))
    ap.add_argument("--no-cleanup", action="store_true")
    ap.add_argument("--step", action="store_true",
                    help="Mode pas-à-pas : pause entre chaque phase")
    a = ap.parse_args()
    global STEP_MODE
    STEP_MODE = a.step
    if not a.token: a.token = _read_key()
    if not a.token:
        print(f"{R}❌ ADMIN_BOOTSTRAP_KEY requis{Z}"); sys.exit(1)
    sys.exit(1 if asyncio.run(run(a.url, a.token, not a.no_cleanup)) else 0)

if __name__ == "__main__":
    main()
