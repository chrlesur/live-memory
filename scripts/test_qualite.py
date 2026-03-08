#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de qualité officiel — Live Memory MCP Server.

Ce script valide TOUTES les fonctionnalités de Live Memory via le
transport MCP Streamable HTTP (endpoint /mcp). Il couvre les 7
catégories d'outils (30 outils) :

    1. System   (2 outils) : health, about
    2. Admin    (4 outils) : create_token, list_tokens, revoke_token, gc_notes
    3. Space    (7 outils) : create, list, info, rules, update_rules, update_description, delete
    4. Live     (3 outils) : note, read, search
    5. Bank     (4 outils) : consolidate, list, read, read_all
    6. Backup   (4 outils) : create, list, download, delete
    7. Graph    (4 outils) : connect, status, push, disconnect (SKIP si pas de graph-memory)

Total : 28 tests (+ 4 graph optionnels)

Résultat attendu : 28 PASS, 0 FAIL, ~120s (dont ~10s consolidation LLM, ~90s graph push)

Usage :
    # Prérequis : le serveur tourne (Docker Compose)
    docker compose up -d

    # Lancer tous les tests
    python scripts/test_qualite.py

    # Verbose + pas-à-pas
    python scripts/test_qualite.py --step -v

    # Sans nettoyage (pour inspecter les données)
    python scripts/test_qualite.py --no-cleanup

    # Avec Graph Memory local (4 tests supplémentaires)
    python scripts/test_qualite.py --graph-url http://host.docker.internal:8080 --graph-token TOKEN

    # Contre un serveur spécifique
    python scripts/test_qualite.py --url http://localhost:8081
"""

import os
import sys
import json
import time
import asyncio
import argparse
import traceback

sys.path.insert(0, os.path.dirname(__file__))
from cli.client import MCPClient

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

SPACE_ID = "test-streamable-http"
TOKEN_NAME = "test-agent-streamable"
VERBOSE = False

RULES = """# Rules — Test Streamable HTTP

La bank doit contenir 3 fichiers :

### summary.md
Résumé général du contexte.

### decisions.md
Décisions prises et leur justification.

### progress.md
Avancement, ce qui reste à faire.
"""

NOTES = [
    ("observation", "Le serveur utilise maintenant Streamable HTTP au lieu de SSE."),
    ("decision", "Migration SSE → Streamable HTTP validée. Pas de backward compat."),
    ("progress", "Transport migré : server.py, client.py, graph_bridge.py, Caddyfile."),
    ("todo", "Tester tous les outils MCP via le nouveau transport."),
    ("insight", "Le SDK MCP gère le handshake automatiquement — code client simplifié."),
    ("issue", "Rate limiting WAF à recalibrer : ×3 requêtes HTTP par appel d'outil."),
]

# ═══════════════════════════════════════════════════════════════
# Affichage
# ═══════════════════════════════════════════════════════════════

G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"
M = "\033[95m"; B = "\033[1m"; D = "\033[2m"; Z = "\033[0m"

STEP_MODE = False
passed = 0
failed = 0
skipped = 0
results = []


def pause(msg="Appuyez sur Entrée pour continuer..."):
    if STEP_MODE:
        print(f"\n  {D}⏸  {msg}{Z}", end="", flush=True)
        input()


def header(t):
    w = 70
    print(f"\n{B}{C}{'═' * w}{Z}")
    print(f"{B}{C}  {t}{Z}")
    print(f"{B}{C}{'═' * w}{Z}")


def section(t):
    print(f"\n{B}{M}── {t} ──{Z}")


def test_pass(name, detail=""):
    global passed
    passed += 1
    results.append(("PASS", name))
    d = f" — {detail}" if detail else ""
    print(f"  {G}✅ PASS{Z}  {name}{D}{d}{Z}")


def test_fail(name, detail=""):
    global failed
    failed += 1
    results.append(("FAIL", name))
    d = f" — {detail}" if detail else ""
    print(f"  {R}❌ FAIL{Z}  {name}{d}")


def test_skip(name, detail=""):
    global skipped
    skipped += 1
    results.append(("SKIP", name))
    d = f" — {detail}" if detail else ""
    print(f"  {Y}⏭  SKIP{Z}  {name}{D}{d}{Z}")


def vprint(msg):
    if VERBOSE:
        print(f"  {D}    → {msg}{Z}")


# ═══════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════

async def test_system(admin: MCPClient):
    """Teste les 2 outils system (pas d'auth requise)."""
    section("1. SYSTEM (2 outils)")

    # system_health
    try:
        r = await admin.call_tool("system_health", {})
        vprint(f"status={r.get('status')}, version={r.get('version')}")
        if r.get("status") in ("healthy", "degraded"):
            svc = r.get("services", {})
            s3 = svc.get("s3", {}).get("status", "?")
            llm = svc.get("llmaas", {}).get("status", "?")
            test_pass("system_health", f"S3={s3}, LLM={llm}, spaces={r.get('spaces_count', '?')}")
        else:
            test_fail("system_health", r.get("message", str(r)))
    except Exception as e:
        test_fail("system_health", str(e))

    # system_about
    try:
        r = await admin.call_tool("system_about", {})
        vprint(f"tools_count={r.get('tools_count')}")
        if r.get("status") == "ok" and r.get("tools_count", 0) >= 25:
            test_pass("system_about", f"{r.get('tools_count')} outils, v{r.get('version', '?')}")
        else:
            test_fail("system_about", f"tools={r.get('tools_count')}")
    except Exception as e:
        test_fail("system_about", str(e))


async def test_admin_tokens(admin: MCPClient) -> str:
    """Teste la gestion des tokens. Retourne le token agent créé."""
    section("2. ADMIN — Tokens (3 outils)")
    agent_token = ""

    # admin_create_token
    try:
        r = await admin.call_tool("admin_create_token", {
            "name": TOKEN_NAME,
            "permissions": "read,write",
            "space_ids": SPACE_ID,
            "expires_in_days": 1,
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") == "created" and r.get("token"):
            agent_token = r["token"]
            test_pass("admin_create_token", f"token={agent_token[:20]}...")
        else:
            test_fail("admin_create_token", r.get("message", str(r)))
    except Exception as e:
        test_fail("admin_create_token", str(e))

    # admin_list_tokens
    try:
        r = await admin.call_tool("admin_list_tokens", {})
        vprint(f"count={r.get('count')}")
        tokens = r.get("tokens", [])
        found = any(t.get("name") == TOKEN_NAME for t in tokens)
        if r.get("status") == "ok" and found:
            test_pass("admin_list_tokens", f"{r.get('count', len(tokens))} tokens, '{TOKEN_NAME}' trouvé")
        else:
            test_fail("admin_list_tokens", f"token '{TOKEN_NAME}' non trouvé")
    except Exception as e:
        test_fail("admin_list_tokens", str(e))

    # admin_revoke_token — on crée un token temporaire pour le révoquer
    try:
        r = await admin.call_tool("admin_create_token", {
            "name": "temp-to-revoke",
            "permissions": "read",
            "expires_in_days": 1,
        })
        if r.get("status") == "created":
            # Trouver le hash
            r2 = await admin.call_tool("admin_list_tokens", {})
            revoke_hash = ""
            for t in r2.get("tokens", []):
                if t.get("name") == "temp-to-revoke" and not t.get("revoked"):
                    revoke_hash = t["hash"]
                    break
            if revoke_hash:
                r3 = await admin.call_tool("admin_revoke_token", {"token_hash": revoke_hash})
                if r3.get("status") in ("ok", "revoked"):
                    test_pass("admin_revoke_token", "token temp révoqué")
                else:
                    test_fail("admin_revoke_token", r3.get("message", str(r3)))
            else:
                test_fail("admin_revoke_token", "hash non trouvé")
        else:
            test_fail("admin_revoke_token", "impossible de créer le token temp")
    except Exception as e:
        test_fail("admin_revoke_token", str(e))

    return agent_token


async def test_space(agent: MCPClient):
    """Teste les 7 outils space."""
    section("3. SPACE (7 outils)")

    # space_create
    try:
        r = await agent.call_tool("space_create", {
            "space_id": SPACE_ID,
            "description": "Test migration Streamable HTTP",
            "rules": RULES,
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") in ("created", "already_exists"):
            test_pass("space_create", SPACE_ID)
        else:
            test_fail("space_create", r.get("message", str(r)))
    except Exception as e:
        test_fail("space_create", str(e))

    # space_list
    try:
        r = await agent.call_tool("space_list", {})
        vprint(f"count={r.get('count')}")
        spaces = r.get("spaces", [])
        found = any(s.get("space_id") == SPACE_ID for s in spaces)
        if r.get("status") == "ok" and found:
            test_pass("space_list", f"{r.get('count', len(spaces))} espaces, '{SPACE_ID}' trouvé")
        else:
            test_fail("space_list", f"'{SPACE_ID}' non trouvé")
    except Exception as e:
        test_fail("space_list", str(e))

    # space_info
    try:
        r = await agent.call_tool("space_info", {"space_id": SPACE_ID})
        vprint(f"status={r.get('status')}, description={r.get('description', '')[:30]}")
        if r.get("status") == "ok" and r.get("space_id") == SPACE_ID:
            test_pass("space_info", f"created={r.get('created_at', '?')[:10]}")
        else:
            test_fail("space_info", r.get("message", str(r)))
    except Exception as e:
        test_fail("space_info", str(e))

    # space_rules
    try:
        r = await agent.call_tool("space_rules", {"space_id": SPACE_ID})
        vprint(f"rules_length={len(r.get('rules', r.get('content', '')))}")
        rules_text = r.get("rules", r.get("content", ""))
        if r.get("status") == "ok" and "summary.md" in rules_text:
            test_pass("space_rules", f"{len(rules_text)} chars")
        else:
            test_fail("space_rules", "rules manquantes ou incomplètes")
    except Exception as e:
        test_fail("space_rules", str(e))

    # space_update_rules
    try:
        new_rules = RULES + "\n### extra.md\nFichier bonus de test.\n"
        r = await agent.call_tool("space_update_rules", {
            "space_id": SPACE_ID,
            "rules": new_rules,
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") in ("ok", "updated"):
            test_pass("space_update_rules", "rules mises à jour")
        else:
            test_fail("space_update_rules", r.get("message", str(r)))
    except Exception as e:
        test_fail("space_update_rules", str(e))

    # space_update_description
    try:
        r = await agent.call_tool("space_update_description", {
            "space_id": SPACE_ID,
            "description": "Test Streamable HTTP — description mise à jour",
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") in ("ok", "updated"):
            test_pass("space_update_description", "description mise à jour")
        else:
            test_fail("space_update_description", r.get("message", str(r)))
    except Exception as e:
        test_fail("space_update_description", str(e))

    # space_delete — testé à la fin (cleanup)
    test_skip("space_delete", "testé dans cleanup")


async def test_live(agent: MCPClient):
    """Teste les 3 outils live."""
    section("4. LIVE (3 outils)")

    # live_note — 6 notes
    notes_ok = 0
    for i, (cat, content) in enumerate(NOTES):
        try:
            r = await agent.call_tool("live_note", {
                "space_id": SPACE_ID,
                "category": cat,
                "content": content,
            })
            if r.get("status") in ("ok", "created"):
                notes_ok += 1
            else:
                vprint(f"Note {i + 1} FAIL: {r.get('message', '')}")
        except Exception as e:
            vprint(f"Note {i + 1} ERROR: {e}")

    if notes_ok == len(NOTES):
        test_pass("live_note", f"{notes_ok}/{len(NOTES)} notes écrites")
    else:
        test_fail("live_note", f"{notes_ok}/{len(NOTES)} notes")

    # live_read
    try:
        r = await agent.call_tool("live_read", {
            "space_id": SPACE_ID,
            "limit": 50,
        })
        vprint(f"total={r.get('total')}")
        count = r.get("total", len(r.get("notes", [])))
        if r.get("status") == "ok" and count >= len(NOTES):
            test_pass("live_read", f"{count} notes lues")
        else:
            test_fail("live_read", f"{count} notes (attendu >= {len(NOTES)})")
    except Exception as e:
        test_fail("live_read", str(e))

    # live_search
    try:
        r = await agent.call_tool("live_search", {
            "space_id": SPACE_ID,
            "query": "Streamable HTTP",
        })
        vprint(f"matches={r.get('total', r.get('matches', '?'))}")
        matches = r.get("total", r.get("matches", len(r.get("notes", []))))
        if r.get("status") == "ok" and matches > 0:
            test_pass("live_search", f"{matches} résultat(s) pour 'Streamable HTTP'")
        else:
            test_fail("live_search", f"0 résultats")
    except Exception as e:
        test_fail("live_search", str(e))


async def test_bank(agent: MCPClient):
    """Teste les 4 outils bank."""
    section("5. BANK (4 outils)")

    # bank_consolidate
    try:
        t0 = time.monotonic()
        r = await agent.call_tool("bank_consolidate", {"space_id": SPACE_ID})
        dur = round(time.monotonic() - t0, 1)
        vprint(f"notes_processed={r.get('notes_processed')}, duration={dur}s")
        if r.get("status") == "ok" and r.get("notes_processed", 0) > 0:
            created = r.get("bank_files_created", 0)
            updated = r.get("bank_files_updated", 0)
            test_pass("bank_consolidate",
                       f"{r['notes_processed']} notes → {created + updated} fichiers ({dur}s)")
        elif r.get("notes_processed", 0) == 0:
            test_fail("bank_consolidate", "0 notes traitées (filtre agent ?)")
        else:
            test_fail("bank_consolidate", r.get("message", str(r)))
    except Exception as e:
        test_fail("bank_consolidate", str(e))

    # bank_list
    try:
        r = await agent.call_tool("bank_list", {"space_id": SPACE_ID})
        vprint(f"total={r.get('total')}")
        files = r.get("files", [])
        if r.get("status") == "ok" and len(files) > 0:
            names = [f.get("filename", "?") for f in files]
            test_pass("bank_list", f"{len(files)} fichiers : {', '.join(names[:5])}")
        else:
            test_fail("bank_list", "aucun fichier bank")
    except Exception as e:
        test_fail("bank_list", str(e))

    # bank_read (premier fichier)
    try:
        r = await agent.call_tool("bank_list", {"space_id": SPACE_ID})
        files = r.get("files", [])
        if files:
            fname = files[0].get("filename", "")
            r2 = await agent.call_tool("bank_read", {
                "space_id": SPACE_ID,
                "filename": fname,
            })
            vprint(f"filename={fname}, size={r2.get('size', '?')}")
            if r2.get("status") == "ok" and r2.get("content"):
                test_pass("bank_read", f"'{fname}' ({r2.get('size', '?')} octets)")
            else:
                test_fail("bank_read", r2.get("message", "contenu vide"))
        else:
            test_skip("bank_read", "pas de fichier bank")
    except Exception as e:
        test_fail("bank_read", str(e))

    # bank_read_all
    try:
        r = await agent.call_tool("bank_read_all", {"space_id": SPACE_ID})
        vprint(f"files={len(r.get('files', []))}, total_size={r.get('total_size')}")
        files = r.get("files", [])
        if r.get("status") == "ok" and len(files) > 0:
            test_pass("bank_read_all", f"{len(files)} fichiers, {r.get('total_size', '?')} octets")
        else:
            test_fail("bank_read_all", "aucun fichier")
    except Exception as e:
        test_fail("bank_read_all", str(e))


async def test_backup(admin: MCPClient):
    """Teste les 4 outils backup."""
    section("6. BACKUP (4 outils)")
    backup_id = ""

    # backup_create
    try:
        r = await admin.call_tool("backup_create", {
            "space_id": SPACE_ID,
            "description": "Test streamable HTTP backup",
        })
        vprint(f"status={r.get('status')}, backup_id={r.get('backup_id')}")
        if r.get("status") in ("ok", "created"):
            backup_id = r.get("backup_id", "")
            test_pass("backup_create", f"id={backup_id}")
        else:
            test_fail("backup_create", r.get("message", str(r)))
    except Exception as e:
        test_fail("backup_create", str(e))

    # backup_list
    try:
        r = await admin.call_tool("backup_list", {"space_id": SPACE_ID})
        vprint(f"count={r.get('count')}")
        backups = r.get("backups", [])
        if r.get("status") == "ok" and len(backups) > 0:
            test_pass("backup_list", f"{len(backups)} backup(s)")
        else:
            test_fail("backup_list", "aucun backup trouvé")
    except Exception as e:
        test_fail("backup_list", str(e))

    # backup_download
    if backup_id:
        try:
            r = await admin.call_tool("backup_download", {"backup_id": backup_id})
            vprint(f"status={r.get('status')}, files={r.get('file_count')}")
            if r.get("status") == "ok":
                test_pass("backup_download", f"{r.get('file_count', '?')} fichiers")
            else:
                test_fail("backup_download", r.get("message", str(r)))
        except Exception as e:
            test_fail("backup_download", str(e))
    else:
        test_skip("backup_download", "pas de backup_id")

    # backup_delete
    if backup_id:
        try:
            r = await admin.call_tool("backup_delete", {
                "backup_id": backup_id,
                "confirm": True,
            })
            vprint(f"status={r.get('status')}")
            if r.get("status") in ("ok", "deleted"):
                test_pass("backup_delete", f"backup {backup_id} supprimé")
            else:
                test_fail("backup_delete", r.get("message", str(r)))
        except Exception as e:
            test_fail("backup_delete", str(e))
    else:
        test_skip("backup_delete", "pas de backup_id")


async def test_gc(admin: MCPClient):
    """Teste le garbage collector (1 outil)."""
    section("7. ADMIN — GC (1 outil)")

    # admin_gc_notes (dry-run)
    try:
        r = await admin.call_tool("admin_gc_notes", {
            "space_id": SPACE_ID,
            "max_age_days": 30,
            "confirm": False,
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") in ("ok", "dry_run"):
            orphan = r.get("orphan_notes", r.get("notes_found", 0))
            test_pass("admin_gc_notes", f"dry-run OK, {orphan} notes orphelines")
        else:
            test_fail("admin_gc_notes", r.get("message", str(r)))
    except Exception as e:
        test_fail("admin_gc_notes", str(e))


async def test_graph(admin: MCPClient, graph_url: str, graph_token: str):
    """Teste les 4 outils graph (optionnel — nécessite Graph Memory)."""
    section("8. GRAPH (4 outils — optionnel)")

    if not graph_url or not graph_token:
        test_skip("graph_connect", "pas de GRAPH_MEM_URL / GRAPH_MEM_TOKEN")
        test_skip("graph_status", "pas de Graph Memory")
        test_skip("graph_push", "pas de Graph Memory")
        test_skip("graph_disconnect", "pas de Graph Memory")
        return

    memory_id = "STREAMABLE-HTTP-TEST"

    # graph_connect
    try:
        r = await admin.call_tool("graph_connect", {
            "space_id": SPACE_ID,
            "url": graph_url,
            "token": graph_token,
            "memory_id": memory_id,
        })
        vprint(f"status={r.get('status')}")
        if r.get("status") == "connected":
            test_pass("graph_connect", f"memory={memory_id}")
        else:
            test_fail("graph_connect", r.get("message", str(r)))
            return  # Pas la peine de continuer
    except Exception as e:
        test_fail("graph_connect", str(e))
        return

    # graph_status
    try:
        r = await admin.call_tool("graph_status", {"space_id": SPACE_ID})
        vprint(f"reachable={r.get('reachable')}")
        if r.get("status") == "ok" and r.get("reachable"):
            test_pass("graph_status", f"connecté, reachable")
        else:
            test_fail("graph_status", r.get("message", r.get("error", str(r))))
    except Exception as e:
        test_fail("graph_status", str(e))

    # graph_push
    try:
        r = await admin.call_tool("graph_push", {"space_id": SPACE_ID})
        vprint(f"pushed={r.get('pushed')}, errors={r.get('errors')}")
        if r.get("status") == "ok":
            test_pass("graph_push", f"{r.get('pushed', 0)} fichiers poussés")
        else:
            test_fail("graph_push", r.get("message", str(r)))
    except Exception as e:
        test_fail("graph_push", str(e))

    # graph_disconnect
    try:
        r = await admin.call_tool("graph_disconnect", {"space_id": SPACE_ID})
        vprint(f"status={r.get('status')}")
        if r.get("status") in ("ok", "disconnected"):
            test_pass("graph_disconnect", "déconnecté")
        else:
            test_fail("graph_disconnect", r.get("message", str(r)))
    except Exception as e:
        test_fail("graph_disconnect", str(e))


async def cleanup(admin: MCPClient):
    """Nettoyage final."""
    section("CLEANUP")

    # Supprimer l'espace
    try:
        r = await admin.call_tool("space_delete", {
            "space_id": SPACE_ID,
            "confirm": True,
        })
        if r.get("status") in ("ok", "deleted"):
            test_pass("space_delete", f"'{SPACE_ID}' supprimé")
        else:
            test_fail("space_delete", r.get("message", str(r)))
    except Exception as e:
        test_fail("space_delete", str(e))

    # Révoquer le token agent
    try:
        r = await admin.call_tool("admin_list_tokens", {})
        for t in r.get("tokens", []):
            if t.get("name") == TOKEN_NAME and not t.get("revoked"):
                r2 = await admin.call_tool("admin_revoke_token", {"token_hash": t["hash"]})
                if r2.get("status") in ("ok", "revoked"):
                    vprint(f"Token '{TOKEN_NAME}' révoqué")
                break
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Orchestrateur principal
# ═══════════════════════════════════════════════════════════════

async def run_all(url: str, bootstrap_key: str, do_cleanup: bool,
                  graph_url: str, graph_token: str):
    global passed, failed, skipped

    admin = MCPClient(base_url=url, token=bootstrap_key, timeout=600)
    t0 = time.monotonic()

    header("🧪 TEST DE QUALITÉ — Live Memory MCP Server")
    print(f"  {C}Serveur  :{Z} {url}")
    print(f"  {C}Endpoint :{Z} {url}/mcp")
    print(f"  {C}Espace   :{Z} {SPACE_ID}")
    print(f"  {C}Transport:{Z} Streamable HTTP (SDK MCP v1.8+)")

    # ── 1. System ────────────────────────────────────
    await test_system(admin)
    pause("System OK → Tokens")

    # ── 2. Admin tokens ──────────────────────────────
    agent_token = await test_admin_tokens(admin)
    if not agent_token:
        print(f"\n  {R}{B}💥 STOP — impossible de créer le token agent{Z}")
        return

    agent = MCPClient(base_url=url, token=agent_token, timeout=600)
    pause("Tokens OK → Spaces")

    # ── 3. Space ─────────────────────────────────────
    await test_space(agent)
    pause("Spaces OK → Live notes")

    # ── 4. Live ──────────────────────────────────────
    await test_live(agent)
    pause("Live OK → Bank consolidation")

    # ── 5. Bank ──────────────────────────────────────
    await test_bank(agent)
    pause("Bank OK → Backup")

    # ── 6. Backup ────────────────────────────────────
    await test_backup(admin)
    pause("Backup OK → GC")

    # ── 7. GC ────────────────────────────────────────
    await test_gc(admin)
    pause("GC OK → Graph (optionnel)")

    # ── 8. Graph (optionnel) ─────────────────────────
    await test_graph(admin, graph_url, graph_token)

    # ── Cleanup ──────────────────────────────────────
    if do_cleanup:
        pause("Tests terminés → Cleanup")
        await cleanup(admin)
    else:
        section("CLEANUP DÉSACTIVÉ (--no-cleanup)")
        test_skip("space_delete", "cleanup désactivé")

    # ── Résumé final ─────────────────────────────────
    duration = round(time.monotonic() - t0, 1)
    total = passed + failed

    header("📊 RÉSUMÉ — TEST DE QUALITÉ")
    print()
    for status, name in results:
        icon = {"PASS": f"{G}✅", "FAIL": f"{R}❌", "SKIP": f"{Y}⏭ "}[status]
        print(f"  {icon} {status:4s}{Z}  {name}")

    print(f"\n  {B}Total    :{Z} {total} tests")
    print(f"  {G}Passed   :{Z} {passed}")
    print(f"  {R}Failed   :{Z} {failed}")
    print(f"  {Y}Skipped  :{Z} {skipped}")
    print(f"  {C}Duration :{Z} {duration}s")

    if failed == 0:
        print(f"\n  {G}{B}🎉 QUALITÉ OK — {passed} PASS, 0 FAIL{Z}")
    else:
        print(f"\n  {R}{B}💥 QUALITÉ KO — {failed} test(s) en erreur{Z}")

    return failed


# ═══════════════════════════════════════════════════════════════
# Point d'entrée
# ═══════════════════════════════════════════════════════════════

def _read_key():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p):
        for l in open(p):
            if l.strip().startswith("ADMIN_BOOTSTRAP_KEY="):
                return l.strip().split("=", 1)[1].strip()
    return ""


def main():
    global VERBOSE, STEP_MODE

    ap = argparse.ArgumentParser(
        description="Test de qualité officiel — Live Memory MCP Server")
    ap.add_argument("--url", default=os.environ.get("MCP_URL", "http://localhost:8080"),
                    help="URL du serveur Live Memory")
    ap.add_argument("--token", default=os.environ.get("ADMIN_BOOTSTRAP_KEY", ""),
                    help="Bootstrap key admin")
    ap.add_argument("--no-cleanup", action="store_true",
                    help="Conserver les données de test")
    ap.add_argument("--step", action="store_true",
                    help="Mode pas-à-pas")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Affichage détaillé")
    ap.add_argument("--graph-url", default=os.environ.get("GRAPH_MEM_URL", ""),
                    help="URL de Graph Memory (optionnel)")
    ap.add_argument("--graph-token", default=os.environ.get("GRAPH_MEM_TOKEN", ""),
                    help="Token Graph Memory (optionnel)")
    a = ap.parse_args()

    VERBOSE = a.verbose
    STEP_MODE = a.step

    if not a.token:
        a.token = _read_key()
    if not a.token:
        print(f"{R}❌ ADMIN_BOOTSTRAP_KEY requis (--token ou .env){Z}")
        sys.exit(1)

    errors = asyncio.run(run_all(
        a.url, a.token, not a.no_cleanup,
        a.graph_url, a.graph_token,
    ))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
