#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de recette — Simulation complète via Docker Compose + WAF.

Pipeline testé :
    1. Health check
    2. Création d'un token agent (via bootstrap key)
    3. Création d'espace avec rules Memory Bank standard
    4. Écriture de 12 notes live (agent Ubuntu 24.04)
    5. Lecture des notes
    6. Consolidation LLM (notes → bank structurée)
    7. Lecture de la bank consolidée
    8. Nettoyage

Usage :
    docker compose up -d
    python scripts/test_recette.py
    python scripts/test_recette.py --no-cleanup
"""

import os, sys, json, time, asyncio, argparse, textwrap

sys.path.insert(0, os.path.dirname(__file__))
from cli.client import MCPClient

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

SPACE_ID = "recette-ubuntu-update"
TOKEN_NAME = "agent-sysadmin"

# Rules Memory Bank standard
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

# 12 notes simulant un agent sysadmin Ubuntu 24.04
NOTES = [
    ("observation", "Audit serveur",
     "Audit initial du serveur cible.\n"
     "- OS : Ubuntu 22.04.4 LTS (Jammy Jellyfish)\n"
     "- Noyau : 5.15.0-91-generic\n"
     "- RAM : 16 Go, CPU : 4 vCPU\n"
     "- Services : nginx 1.18, postgresql 14, php-fpm 8.1\n"
     "- Uptime : 247 jours, disque : 45% (18 Go libre)"),
    ("decision", "Stratégie",
     "Stratégie retenue : do-release-upgrade.\n"
     "- Méthode officielle Canonical\n"
     "- Fenêtre maintenance : samedi 02h00-06h00\n"
     "- Rollback : snapshot VM avant lancement"),
    ("todo", "Checklist pré-migration",
     "- [x] Backup /etc (tar.gz)\n"
     "- [x] Dump PostgreSQL (pg_dumpall)\n"
     "- [x] Snapshot VM\n"
     "- [ ] Notifier utilisateurs\n"
     "- [ ] Désactiver monitoring Zabbix\n"
     "- [ ] Lancer do-release-upgrade"),
    ("progress", "Backups OK",
     "Backup pré-migration terminé.\n"
     "- /etc : 12 Mo, PostgreSQL dump : 340 Mo\n"
     "- Snapshot VM : snap-ubuntu22-pre-upgrade\n"
     "- Durée : 8 minutes"),
    ("observation", "APT upgrade",
     "$ apt update && apt full-upgrade -y\n"
     "- 47 paquets mis à jour, 0 erreurs"),
    ("progress", "Upgrade lancé",
     "do-release-upgrade lancé à 02:15.\n"
     "- Téléchargement 24.04 : 1.2 Go\n"
     "- 3 fichiers config : garder version locale"),
    ("issue", "PHP incompatible",
     "php8.1-fpm supprimé pendant l'upgrade !\n"
     "Impact : WordPress + API hors service.\n"
     "Solution : installer php8.3-fpm."),
    ("decision", "Migration PHP 8.3",
     "Migration PHP 8.1 → 8.3 validée.\n"
     "- WordPress 6.x compatible\n"
     "- Extensions dispo (mbstring, xml, curl, pgsql)"),
    ("progress", "Reboot OK",
     "Système sur Ubuntu 24.04.1 LTS.\n"
     "- Noyau : 6.8.0-45-generic\n"
     "- Boot propre, upgrade : 45 min\n"
     "- PHP 8.3-fpm installé"),
    ("observation", "Services validés",
     "- nginx OK (80/443)\n"
     "- postgresql 16 OK (migration auto)\n"
     "- php8.3-fpm OK, WordPress OK\n"
     "- SSH OK, Let's Encrypt OK\n"
     "- Cron backup : chemin PHP à corriger"),
    ("issue", "Cron cassé",
     "/etc/cron.d/backup → /usr/bin/php8.1 obsolète.\n"
     "Impact : backups nocturnes KO.\n"
     "Fix : remplacer par /usr/bin/php8.3."),
    ("progress", "TERMINÉ",
     "Migration Ubuntu 24.04 TERMINÉE.\n"
     "- Durée : 1h45 (02:00 → 03:45)\n"
     "- 2 issues (PHP + cron), résolues\n"
     "- Tous services opérationnels\n"
     "- Retour en production à 03:50."),
]

# ═══════════════════════════════════════════════════════════════
# Affichage
# ═══════════════════════════════════════════════════════════════

G="\033[92m"; R="\033[91m"; Y="\033[93m"; C="\033[96m"
M="\033[95m"; B="\033[1m"; D="\033[2m"; Z="\033[0m"

STEP_MODE = False

def pause(msg="Appuyez sur Entrée pour continuer..."):
    """Pause step-by-step."""
    if STEP_MODE:
        print(f"\n  {D}⏸  {msg}{Z}", end="", flush=True)
        input()

CAT_EMOJI = {"observation":"🔍","decision":"🎯","todo":"📋",
             "progress":"📈","issue":"⚠️","insight":"💡"}

def header(t):
    w = 70
    print(f"\n{B}{C}{'═'*w}{Z}")
    print(f"{B}{C}  {t}{Z}")
    print(f"{B}{C}{'═'*w}{Z}")

def step(n, total, t):
    print(f"\n{B}[{n}/{total}]{Z} {t}")

def ok(t):   print(f"  {G}✅ {t}{Z}")
def warn(t): print(f"  {Y}⚠️  {t}{Z}")
def fail(t): print(f"  {R}❌ {t}{Z}")
def info(t): print(f"  {C}ℹ️  {t}{Z}")

def box(title, content, color=C):
    """Affiche un encadré avec titre et contenu complet."""
    lines = content.split('\n')
    # Calculer la largeur : max(titre, ligne la plus longue) + marge
    max_len = max(len(title), max((len(l) for l in lines), default=0))
    w = min(max(max_len + 4, 50), 100)  # Entre 50 et 100 colonnes
    print(f"  {color}┌{'─'*w}┐{Z}")
    print(f"  {color}│{Z} {B}{title}{Z}{' '*(w-len(title)-1)}{color}│{Z}")
    print(f"  {color}├{'─'*w}┤{Z}")
    for line in lines:
        pad = w - len(line) - 1
        if pad < 0:
            # Ligne trop longue → couper en morceaux
            while len(line) > w - 2:
                chunk = line[:w-2]
                line = line[w-2:]
                print(f"  {color}│{Z} {chunk} {color}│{Z}")
            pad = w - len(line) - 1
        print(f"  {color}│{Z} {line}{' '*pad}{color}│{Z}")
    print(f"  {color}└{'─'*w}┘{Z}")

def show_note_sent(i, total, cat, title, content):
    """Affiche une note envoyée — contenu COMPLET."""
    emoji = CAT_EMOJI.get(cat, "📝")
    box(f"{emoji} Note {i}/{total} [{cat}] — {title}", content, color=C)

def show_bank_file(filename, content):
    """Affiche un fichier bank consolidé — contenu COMPLET."""
    box(f"📄 {filename}", content.strip(), color=M)

def show_result(result):
    s = result.get("status", "?")
    color = G if s in ("ok","created","deleted") else R
    print(f"  → status: {color}{s}{Z}")
    for k in ("space_id","name","notes_processed","bank_files_created",
              "bank_files_updated","llm_tokens_used","duration_seconds",
              "file_count","total_size","total","message"):
        if k in result:
            print(f"    {k}: {result[k]}")

# ═══════════════════════════════════════════════════════════════
# Script principal
# ═══════════════════════════════════════════════════════════════

async def run_recette(url, bootstrap_key, cleanup=True):
    TOTAL = 9
    admin = MCPClient(base_url=url, token=bootstrap_key, timeout=600)
    t0 = time.monotonic()
    errors = 0
    agent_token = None

    header("🧪 RECETTE — Agent sysadmin : Ubuntu 22.04 → 24.04")
    info(f"Serveur : {url}")
    info(f"Espace  : {SPACE_ID}")
    info(f"Token   : {TOKEN_NAME}")
    info(f"L'agent ne passe PAS de paramètre agent= : le serveur")
    info(f"utilise automatiquement le client_name du token.")

    # ── 1. Health Check ──────────────────────────────
    step(1, TOTAL, "Health check du serveur MCP")
    try:
        r = await admin.call_tool("system_health", {})
        show_result(r)
        if r.get("status") in ("ok", "degraded"):
            ok("Serveur accessible via WAF")
        else:
            fail(f"Health check KO"); errors += 1
    except Exception as e:
        fail(f"Health check: {e}"); errors += 1

    # ── 2. Créer un token agent ──────────────────────
    step(2, TOTAL, f"Création token '{TOKEN_NAME}' (read+write)")
    try:
        r = await admin.call_tool("admin_create_token", {
            "name": TOKEN_NAME,
            "permissions": "read,write",
            "space_ids": SPACE_ID,
            "expires_in_days": 1,
        })
        if r.get("status") == "created":
            agent_token = r["token"]
            ok(f"Token : {agent_token[:25]}...")
            info(f"Permissions : read,write | Espace : {SPACE_ID}")
        else:
            fail(f"Token : {r.get('message','?')}"); errors += 1
    except Exception as e:
        fail(f"Token : {e}"); errors += 1

    if not agent_token:
        fail("Stop : pas de token"); return errors + 1

    agent = MCPClient(base_url=url, token=agent_token, timeout=600)

    # ── 3. Créer l'espace + rules ────────────────────
    step(3, TOTAL, f"Création espace '{SPACE_ID}'")
    try:
        r = await agent.call_tool("space_create", {
            "space_id": SPACE_ID,
            "description": "Recette : mise à jour Ubuntu 22.04 → 24.04",
            "rules": RULES,
        })
        if r.get("status") == "created":
            ok("Espace créé")
            box("Rules envoyées", RULES.strip()[:500], color=C)
        elif "already" in str(r.get("message","")).lower() or r.get("status") == "already_exists":
            warn("Espace existe déjà (reprise)")
        else:
            fail(f"Espace : {r.get('message','?')}"); errors += 1
    except Exception as e:
        fail(f"Espace : {e}"); errors += 1

    # ── 4. Lire les rules de l'espace ────────────────
    step(4, TOTAL, "Lecture des rules de l'espace (space_rules)")
    try:
        r = await agent.call_tool("space_rules", {"space_id": SPACE_ID})
        if r.get("status") == "ok":
            rules_content = r.get("content", r.get("rules", "(vide)"))
            ok("Rules lues depuis le serveur")
            header("📜 RULES STOCKÉES SUR LE SERVEUR")
            box(f"Rules de '{SPACE_ID}'", rules_content.strip(), color=Y)
        else:
            warn(f"Rules : {r.get('message','?')}")
    except Exception as e:
        fail(f"Rules : {e}"); errors += 1

    pause("Rules vérifiées. Étape 5 : écriture des notes →")

    # ── 5. Écrire 12 notes (SANS agent=) ─────────────
    step(5, TOTAL, f"Écriture de {len(NOTES)} notes (agent auto-détecté)")
    header("📝 CE QUE L'AGENT ENVOIE")
    notes_ok = 0
    for i, (cat, title, content) in enumerate(NOTES):
        show_note_sent(i+1, len(NOTES), cat, title, content)
        try:
            # PAS de paramètre agent= → le serveur utilise le token name
            r = await agent.call_tool("live_note", {
                "space_id": SPACE_ID,
                "category": cat,
                "content": content,
            })
            if r.get("status") in ("ok", "created"):
                notes_ok += 1
            else:
                fail(f"  Note {i+1}: {r.get('message','?')}"); errors += 1
        except Exception as e:
            fail(f"  Note {i+1}: {e}"); errors += 1

    print()
    if notes_ok == len(NOTES):
        ok(f"{notes_ok}/{len(NOTES)} notes écrites")
    else:
        warn(f"{notes_ok}/{len(NOTES)} notes"); errors += 1

    pause("Notes écrites. Étape 6 : vérification →")

    # ── 6. Lire les notes ────────────────────────────
    step(6, TOTAL, "Vérification : lecture des notes live")
    try:
        r = await agent.call_tool("live_read", {
            "space_id": SPACE_ID,
            "limit": 50,
        })
        show_result(r)
        nc = r.get("total", r.get("notes_count", 0))
        notes_list = r.get("notes", [])
        if nc >= len(NOTES) or len(notes_list) >= len(NOTES):
            ok(f"{max(nc, len(notes_list))} notes trouvées")
        else:
            warn(f"{max(nc, len(notes_list))} notes (attendu {len(NOTES)})")
    except Exception as e:
        fail(f"Lecture : {e}"); errors += 1

    pause("Notes vérifiées. Étape 7 : consolidation LLM →")

    # ── 7. Consolidation LLM ─────────────────────────
    step(7, TOTAL, "Consolidation LLM (notes → bank)")
    info("Appel LLMaaS qwen3-2507:235b...")
    tc = time.monotonic()
    try:
        r = await agent.call_tool("bank_consolidate", {"space_id": SPACE_ID})
        dur = round(time.monotonic() - tc, 1)
        show_result(r)
        if r.get("status") == "ok" and r.get("notes_processed", 0) > 0:
            ok(f"Consolidation : {r.get('notes_processed',0)} notes → "
               f"{r.get('bank_files_created',0)+r.get('bank_files_updated',0)} "
               f"fichiers en {dur}s")
        elif r.get("notes_processed", 0) == 0:
            warn("0 notes traitées (problème de filtre agent ?)")
        else:
            fail(f"Consolidation : {r.get('message','?')}"); errors += 1
    except Exception as e:
        fail(f"Consolidation : {e}"); errors += 1

    pause("Consolidation terminée. Étape 8 : lecture de la bank →")

    # ── 8. Lire la bank consolidée ───────────────────
    step(8, TOTAL, "Lecture de la Memory Bank")
    try:
        r = await agent.call_tool("bank_read_all", {"space_id": SPACE_ID})
        files = r.get("files", [])
        if files:
            ok(f"{len(files)} fichiers bank ({r.get('total_size',0)} octets)")
            header("📘 CE QUE LE LLM A PRODUIT DANS LA BANK")
            for f in files:
                show_bank_file(f.get("filename","?"), f.get("content",""))
        else:
            warn("Aucun fichier bank")
    except Exception as e:
        fail(f"Bank : {e}"); errors += 1

    # ── 9. Nettoyage ─────────────────────────────────
    if cleanup:
        step(9, TOTAL, "Nettoyage")
        try:
            r = await admin.call_tool("space_delete", {
                "space_id": SPACE_ID, "confirm": True})
            if r.get("status") in ("ok","deleted"):
                ok("Espace supprimé")
        except: pass
        try:
            r = await admin.call_tool("admin_list_tokens", {})
            for t in r.get("tokens", []):
                if t.get("name") == TOKEN_NAME and not t.get("revoked"):
                    await admin.call_tool("admin_revoke_token",
                                          {"token_hash": t["hash"]})
                    ok(f"Token '{TOKEN_NAME}' révoqué")
                    break
        except: pass
    else:
        step(9, TOTAL, "Nettoyage DÉSACTIVÉ (--no-cleanup)")

    # ── Résumé ───────────────────────────────────────
    dur = round(time.monotonic() - t0, 1)
    header("📊 RÉSUMÉ")
    info(f"Durée    : {dur}s")
    info(f"Notes    : {notes_ok}/{len(NOTES)}")
    info(f"Erreurs  : {errors}")
    if errors == 0:
        print(f"\n  {G}{B}🎉 RECETTE RÉUSSIE !{Z}")
    else:
        print(f"\n  {R}{B}💥 RECETTE ÉCHOUÉE — {errors} erreur(s){Z}")
    return errors


# ═══════════════════════════════════════════════════════════════
# Entrée
# ═══════════════════════════════════════════════════════════════

def _read_key():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p):
        for l in open(p):
            if l.strip().startswith("ADMIN_BOOTSTRAP_KEY="):
                return l.strip().split("=",1)[1].strip()
    return ""

def main():
    ap = argparse.ArgumentParser(description="Recette Live Memory")
    ap.add_argument("--url", default=os.environ.get("MCP_URL","http://localhost:8080"))
    ap.add_argument("--token", default=os.environ.get("ADMIN_BOOTSTRAP_KEY",""))
    ap.add_argument("--no-cleanup", action="store_true")
    ap.add_argument("--step", action="store_true",
                    help="Mode pas-à-pas : pause entre chaque étape")
    a = ap.parse_args()
    global STEP_MODE
    STEP_MODE = a.step
    if not a.token: a.token = _read_key()
    if not a.token:
        print(f"{R}❌ ADMIN_BOOTSTRAP_KEY requis{Z}"); sys.exit(1)
    sys.exit(1 if asyncio.run(run_recette(a.url, a.token, not a.no_cleanup)) else 0)

if __name__ == "__main__":
    main()
