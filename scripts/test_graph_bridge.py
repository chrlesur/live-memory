#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du Graph Bridge — Pont Live Memory → Graph Memory.

Pipeline testé :
    1. Health check Live Memory
    2. Création token + espace + notes + consolidation (prérequis)
    3. Connexion du space à Graph Memory (graph_connect)
    4. Push de la bank dans Graph Memory (graph_push)
    5. Vérification du statut (graph_status)
    6. Déconnexion (graph_disconnect)
    7. Nettoyage

Usage :
    # Démarrer live-memory
    docker compose up -d

    # Lancer le test (graph-memory en paramètres)
    python scripts/test_graph_bridge.py \\
        --graph-url https://graph-mem.mcp.cloud-temple.app \\
        --graph-token c83c26946f39...

    # Ou via variables d'environnement
    export GRAPH_MEM_URL=https://graph-mem.mcp.cloud-temple.app
    export GRAPH_MEM_TOKEN=c83c26946f39...
    python scripts/test_graph_bridge.py

    # Mode pas-à-pas
    python scripts/test_graph_bridge.py --step --no-cleanup
"""

import os
import sys
import time
import asyncio
import argparse

sys.path.insert(0, os.path.dirname(__file__))
from cli.client import MCPClient

# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

SPACE_ID = "test-graph-bridge"
TOKEN_NAME = "agent-graph-test"
GRAPH_MEMORY_ID = "LIVE-MEM-TEST"
GRAPH_ONTOLOGY = "general"

RULES = """# Rules — Memory Bank pour test Graph Bridge

La bank doit contenir 3 fichiers Markdown :

### projectbrief.md
Objectifs du projet, périmètre, critères de succès.

### activeContext.md
Focus actuel, changements récents, prochaines étapes.

### progress.md
Ce qui fonctionne, ce qui reste, problèmes connus.
"""

NOTES = [
    ("observation", "Architecture micro-services",
     "Le système est composé de 3 services :\n"
     "- **API Gateway** (Kong) sur port 8000\n"
     "- **Auth Service** (Keycloak) sur port 8080\n"
     "- **Data Service** (PostgreSQL 16 + PostgREST)\n"
     "Déploiement Docker Compose, réseau bridge."),
    ("decision", "Choix du load balancer",
     "HAProxy retenu comme load balancer L4/L7.\n"
     "- Performances supérieures à Nginx pour le TCP\n"
     "- Health checks actifs sur les 3 backends\n"
     "- Stats dashboard sur port 9000"),
    ("progress", "Phase 1 terminée",
     "API Gateway + Auth opérationnels.\n"
     "- 12 endpoints REST validés\n"
     "- JWT token flow OK (access + refresh)\n"
     "- Rate limiting : 100 req/min/client"),
    ("issue", "Latence PostgREST",
     "Latence p99 = 450ms sur les requêtes complexes.\n"
     "Cause : jointures N+1 sur la table relations.\n"
     "Solution envisagée : vue matérialisée + index GIN."),
    ("todo", "Phase 2",
     "- [ ] Implémenter la vue matérialisée\n"
     "- [ ] Configurer le monitoring Prometheus\n"
     "- [ ] Rédiger la doc API (OpenAPI 3.1)\n"
     "- [x] Déployer HAProxy\n"
     "- [x] Configurer les health checks"),
    ("progress", "Optimisation terminée",
     "Latence p99 réduite à 85ms !\n"
     "- Vue matérialisée sur 3 tables\n"
     "- Index GIN sur le JSONB\n"
     "- Connection pooling PgBouncer (50 conn)"),
]


# ═══════════════════════════════════════════════════════════════
# Affichage
# ═══════════════════════════════════════════════════════════════

G = "\033[92m"   # Vert
R = "\033[91m"   # Rouge
Y = "\033[93m"   # Jaune
C = "\033[96m"   # Cyan
M = "\033[95m"   # Magenta
B = "\033[1m"    # Gras
D = "\033[2m"    # Dim
Z = "\033[0m"    # Reset

STEP_MODE = False


def pause(msg="Appuyez sur Entrée pour continuer..."):
    """Pause interactive entre les étapes."""
    if STEP_MODE:
        print(f"\n  {D}⏸  {msg}{Z}", end="", flush=True)
        input()


def header(t):
    """Affiche un titre de section."""
    w = 70
    print(f"\n{B}{C}{'═' * w}{Z}")
    print(f"{B}{C}  {t}{Z}")
    print(f"{B}{C}{'═' * w}{Z}")


def step(n, total, t):
    """Affiche un numéro d'étape."""
    print(f"\n{B}[{n}/{total}]{Z} {t}")


def ok(t):
    print(f"  {G}✅ {t}{Z}")


def warn(t):
    print(f"  {Y}⚠️  {t}{Z}")


def fail(t):
    print(f"  {R}❌ {t}{Z}")


def info(t):
    print(f"  {C}ℹ️  {t}{Z}")


def box(title, content, color=C):
    """Affiche un encadré avec titre et contenu."""
    lines = content.split('\n')
    max_len = max(len(title), max((len(l) for l in lines), default=0))
    w = min(max(max_len + 4, 50), 100)
    print(f"  {color}┌{'─' * w}┐{Z}")
    print(f"  {color}│{Z} {B}{title}{Z}{' ' * (w - len(title) - 1)}{color}│{Z}")
    print(f"  {color}├{'─' * w}┤{Z}")
    for line in lines:
        pad = w - len(line) - 1
        if pad < 0:
            while len(line) > w - 2:
                chunk = line[:w - 2]
                line = line[w - 2:]
                print(f"  {color}│{Z} {chunk} {color}│{Z}")
            pad = w - len(line) - 1
        print(f"  {color}│{Z} {line}{' ' * pad}{color}│{Z}")
    print(f"  {color}└{'─' * w}┘{Z}")


def show_result(result):
    """Affiche le résultat d'un appel MCP."""
    s = result.get("status", "?")
    color = G if s in ("ok", "created", "deleted", "connected", "disconnected") else R
    print(f"  → status: {color}{s}{Z}")
    keys = [
        "space_id", "memory_id", "message",
        "notes_processed", "bank_files_created", "bank_files_updated",
        "pushed", "deleted_before_reingest", "cleaned_orphans",
        "errors", "duration_seconds", "file_count", "total_size",
        "connected", "reachable", "push_count", "files_pushed",
    ]
    for k in keys:
        if k in result:
            print(f"    {D}{k}:{Z} {result[k]}")


def show_graph_config(result):
    """Affiche joliment la config et les stats graph-memory."""
    config = result.get("config", result.get("graph_memory", {}))
    stats = result.get("graph_stats")
    docs = result.get("graph_documents", [])
    top = result.get("top_entities", [])

    lines = []
    lines.append(f"URL       : {config.get('url', '?')}")
    lines.append(f"Memory ID : {config.get('memory_id', '?')}")
    lines.append(f"Ontologie : {config.get('ontology', '?')}")
    if "memory_created" in config:
        lines.append(f"Créée     : {'oui ✨' if config['memory_created'] else 'existait déjà'}")
    if result.get("last_push"):
        lines.append(f"Dernier push  : {result['last_push']}")
        lines.append(f"Pushs totaux  : {result.get('push_count', 0)}")
        lines.append(f"Fichiers      : {result.get('files_pushed', 0)}")

    if stats:
        lines.append(f"")
        lines.append(f"─── 📊 Statistiques Graphe ───")
        lines.append(f"Documents : {stats.get('document_count', 0)}")
        lines.append(f"Entités   : {stats.get('entity_count', 0)}")
        lines.append(f"Relations : {stats.get('relation_count', 0)}")

    if docs:
        lines.append(f"")
        lines.append(f"─── 📄 Documents ingérés ───")
        for d in docs:
            fn = d.get("filename", "?")
            ec = d.get("entity_count", 0)
            sz = d.get("size", 0)
            lines.append(f"  {fn} — {ec} entités, {sz} octets")

    if top:
        lines.append(f"")
        lines.append(f"─── 🏷️  Top entités ───")
        for e in top[:10]:
            if isinstance(e, dict):
                name = e.get("name", "?")
                etype = e.get("type", "?")
                count = e.get("mention_count", e.get("count", ""))
                lines.append(f"  [{etype}] {name}" + (f" ({count} mentions)" if count else ""))
            else:
                lines.append(f"  {e}")

    box("🔗 Graph Memory", "\n".join(lines), color=M)


def show_push_result(result):
    """Affiche joliment les résultats du push."""
    lines = []
    lines.append(f"Fichiers poussés        : {result.get('pushed', 0)}")
    lines.append(f"Supprimés (ré-ingest)   : {result.get('deleted_before_reingest', 0)}")
    lines.append(f"Orphelins nettoyés      : {result.get('cleaned_orphans', 0)}")
    lines.append(f"Erreurs                 : {result.get('errors', 0)}")
    lines.append(f"Durée                   : {result.get('duration_seconds', 0)}s")

    errs = result.get("error_details", [])
    if errs:
        lines.append(f"─── Détails erreurs ───")
        for e in errs:
            lines.append(f"  {e.get('filename', '?')} : {e.get('error', '?')}")

    color = G if result.get("errors", 0) == 0 else Y
    box("📤 Résultat du Push", "\n".join(lines), color=color)


# ═══════════════════════════════════════════════════════════════
# Script principal
# ═══════════════════════════════════════════════════════════════

async def run_test(live_url, bootstrap_key, graph_url, graph_token, cleanup=True):
    """Exécute le test complet du Graph Bridge."""
    TOTAL = 9
    admin = MCPClient(base_url=live_url, token=bootstrap_key, timeout=600)
    t0 = time.monotonic()
    errors = 0
    agent_token = None

    header("🌉 TEST GRAPH BRIDGE — Live Memory → Graph Memory")
    info(f"Live Memory  : {live_url}")
    info(f"Graph Memory : {graph_url}")
    info(f"Espace       : {SPACE_ID}")
    info(f"Memory Graph : {GRAPH_MEMORY_ID}")
    info(f"Ontologie    : {GRAPH_ONTOLOGY}")
    print()

    # ── 1. Health Check ──────────────────────────────
    step(1, TOTAL, "Health check Live Memory")
    try:
        r = await admin.call_tool("system_health", {})
        show_result(r)
        if r.get("status") in ("healthy", "degraded"):
            ok("Live Memory accessible")
        else:
            fail("Health check KO")
            errors += 1
    except Exception as e:
        fail(f"Health check: {e}")
        errors += 1
        return errors

    pause("Health OK. Étape 2 : préparation des données →")

    # ── 2. Prérequis : token + espace + notes + consolidation ──
    step(2, TOTAL, "Préparation : token + espace + notes + consolidation")

    # 2a. Créer un token
    info("Création du token agent...")
    try:
        r = await admin.call_tool("admin_create_token", {
            "name": TOKEN_NAME,
            "permissions": "read,write",
            "space_ids": SPACE_ID,
            "expires_in_days": 1,
        })
        if r.get("status") == "created":
            agent_token = r["token"]
            ok(f"Token créé : {agent_token[:25]}...")
        else:
            fail(f"Token : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"Token : {e}")
        errors += 1

    if not agent_token:
        fail("Stop : impossible de créer le token")
        return errors + 1

    agent = MCPClient(base_url=live_url, token=agent_token, timeout=600)

    # 2b. Créer l'espace
    info("Création de l'espace...")
    try:
        r = await agent.call_tool("space_create", {
            "space_id": SPACE_ID,
            "description": "Test du pont Graph Memory",
            "rules": RULES,
        })
        if r.get("status") == "created":
            ok("Espace créé")
        elif r.get("status") == "already_exists":
            warn("Espace existe déjà (reprise)")
        else:
            fail(f"Espace : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"Espace : {e}")
        errors += 1

    # 2c. Écrire les notes
    info(f"Écriture de {len(NOTES)} notes...")
    notes_ok = 0
    for i, (cat, title, content) in enumerate(NOTES):
        try:
            r = await agent.call_tool("live_note", {
                "space_id": SPACE_ID,
                "category": cat,
                "content": content,
            })
            if r.get("status") in ("ok", "created"):
                notes_ok += 1
        except Exception as e:
            fail(f"Note {i+1}: {e}")
            errors += 1
    if notes_ok == len(NOTES):
        ok(f"{notes_ok}/{len(NOTES)} notes écrites")
    else:
        warn(f"{notes_ok}/{len(NOTES)} notes")
        errors += 1

    # 2d. Consolidation LLM
    info("Consolidation LLM en cours... (peut prendre ~15s)")
    tc = time.monotonic()
    try:
        r = await agent.call_tool("bank_consolidate", {"space_id": SPACE_ID})
        dur = round(time.monotonic() - tc, 1)
        if r.get("status") == "ok" and r.get("notes_processed", 0) > 0:
            ok(f"Consolidation : {r.get('notes_processed', 0)} notes → "
               f"{r.get('bank_files_created', 0) + r.get('bank_files_updated', 0)} "
               f"fichiers bank en {dur}s")
        else:
            fail(f"Consolidation : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"Consolidation : {e}")
        errors += 1

    # 2e. Vérifier la bank
    info("Vérification de la bank...")
    bank_files = []
    try:
        r = await agent.call_tool("bank_read_all", {"space_id": SPACE_ID})
        bank_files = r.get("files", [])
        if bank_files:
            ok(f"{len(bank_files)} fichiers bank prêts")
            for f in bank_files:
                fn = f.get("filename", "?")
                sz = f.get("size", 0)
                info(f"  📄 {fn} ({sz} octets)")
        else:
            fail("Aucun fichier bank — le push ne poussera rien")
            errors += 1
    except Exception as e:
        fail(f"Bank : {e}")
        errors += 1

    pause("Données prêtes. Étape 3 : connexion à Graph Memory →")

    # ── 3. graph_connect ─────────────────────────────
    step(3, TOTAL, f"Connexion du space à Graph Memory")
    header("🔗 GRAPH_CONNECT")
    info(f"URL cible   : {graph_url}")
    info(f"Memory ID   : {GRAPH_MEMORY_ID}")
    info(f"Ontologie   : {GRAPH_ONTOLOGY}")
    print()

    tc = time.monotonic()
    try:
        r = await agent.call_tool("graph_connect", {
            "space_id": SPACE_ID,
            "url": graph_url,
            "token": graph_token,
            "memory_id": GRAPH_MEMORY_ID,
            "ontology": GRAPH_ONTOLOGY,
        })
        dur = round(time.monotonic() - tc, 1)
        show_result(r)
        if r.get("status") == "connected":
            ok(f"Connecté en {dur}s !")
            show_graph_config(r)
        else:
            fail(f"Connexion échouée : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"graph_connect : {e}")
        errors += 1
        fail("Impossible de continuer sans connexion Graph Memory")
        return errors

    pause("Connexion établie. Étape 4 : push de la bank →")

    # ── 4. graph_push ────────────────────────────────
    step(4, TOTAL, f"Push de la bank ({len(bank_files)} fichiers)")
    header("📤 GRAPH_PUSH")
    info("Synchronisation : delete + re-ingest pour chaque fichier")
    info("L'extraction LLM dans graph-memory prend ~10-30s par fichier...")
    print()

    tc = time.monotonic()
    try:
        r = await agent.call_tool("graph_push", {"space_id": SPACE_ID})
        dur = round(time.monotonic() - tc, 1)
        show_result(r)
        if r.get("status") == "ok":
            pushed = r.get("pushed", 0)
            errs = r.get("errors", 0)
            if errs == 0:
                ok(f"Push réussi : {pushed} fichiers en {dur}s")
            else:
                warn(f"Push partiel : {pushed} OK, {errs} erreurs")
                errors += errs
            show_push_result(r)
        else:
            fail(f"Push échoué : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"graph_push : {e}")
        errors += 1

    pause("Push terminé. Étape 5 : vérification du statut →")

    # ── 5. graph_status ──────────────────────────────
    step(5, TOTAL, "Vérification du statut Graph Memory")
    header("📊 GRAPH_STATUS")
    try:
        r = await agent.call_tool("graph_status", {"space_id": SPACE_ID})
        show_result(r)
        if r.get("connected"):
            reachable = r.get("reachable", False)
            if reachable:
                ok("Connexion active et Graph Memory joignable")
                show_graph_config(r)
            else:
                warn(f"Connecté mais injoignable : {r.get('error', '?')}")
        else:
            warn("Pas connecté")
    except Exception as e:
        fail(f"graph_status : {e}")
        errors += 1

    pause("Statut vérifié. Étape 6 : second push (ré-ingestion) →")

    # ── 6. Second push — Test de ré-ingestion ────────
    step(6, TOTAL, "Second push (test delete + re-ingest)")
    header("🔄 GRAPH_PUSH — Ré-ingestion")
    info("Les fichiers existants doivent être supprimés puis ré-ingérés")
    info("On vérifie que le graphe se recalcule correctement...")
    print()

    tc = time.monotonic()
    try:
        r = await agent.call_tool("graph_push", {"space_id": SPACE_ID})
        dur = round(time.monotonic() - tc, 1)
        if r.get("status") == "ok":
            reingest = r.get("deleted_before_reingest", 0)
            pushed = r.get("pushed", 0)
            if reingest > 0:
                ok(f"Ré-ingestion : {reingest} supprimés → {pushed} ré-ingérés en {dur}s")
            else:
                warn(f"Aucune ré-ingestion détectée (pushed={pushed})")
            show_push_result(r)
        else:
            fail(f"Second push : {r.get('message', '?')}")
            errors += 1
    except Exception as e:
        fail(f"Second push : {e}")
        errors += 1

    pause("Ré-ingestion testée. Étape 7 : déconnexion →")

    # ── 7. graph_disconnect ──────────────────────────
    step(7, TOTAL, "Déconnexion de Graph Memory")
    header("🔌 GRAPH_DISCONNECT")
    try:
        r = await agent.call_tool("graph_disconnect", {"space_id": SPACE_ID})
        show_result(r)
        if r.get("status") == "disconnected":
            ok("Space déconnecté de Graph Memory")
            was = r.get("was_connected_to", {})
            info(f"Était connecté à : {was.get('memory_id', '?')} "
                 f"({was.get('push_count', 0)} pushs)")
        else:
            warn(f"Déconnexion : {r.get('message', '?')}")
    except Exception as e:
        fail(f"graph_disconnect : {e}")
        errors += 1

    # ── 8. Vérif post-déconnexion ────────────────────
    step(8, TOTAL, "Vérification post-déconnexion")
    try:
        r = await agent.call_tool("graph_status", {"space_id": SPACE_ID})
        if not r.get("connected", True):
            ok("Statut confirme : non connecté")
        else:
            warn("Le space semble encore connecté ?")
    except Exception as e:
        fail(f"Vérif : {e}")

    pause("Test fonctionnel terminé. Étape 9 : nettoyage →")

    # ── 9. Nettoyage ─────────────────────────────────
    if cleanup:
        step(9, TOTAL, "Nettoyage")
        try:
            r = await admin.call_tool("space_delete", {
                "space_id": SPACE_ID, "confirm": True,
            })
            if r.get("status") in ("ok", "deleted"):
                ok(f"Espace '{SPACE_ID}' supprimé")
        except Exception as e:
            warn(f"Suppression espace : {e}")
        try:
            r = await admin.call_tool("admin_list_tokens", {})
            for t in r.get("tokens", []):
                if t.get("name") == TOKEN_NAME and not t.get("revoked"):
                    await admin.call_tool("admin_revoke_token",
                                          {"token_hash": t["hash"]})
                    ok(f"Token '{TOKEN_NAME}' révoqué")
                    break
        except Exception as e:
            warn(f"Révocation token : {e}")
        info(f"⚠️  La mémoire '{GRAPH_MEMORY_ID}' dans Graph Memory "
             f"n'est PAS supprimée (faites-le manuellement si souhaité)")
    else:
        step(9, TOTAL, "Nettoyage DÉSACTIVÉ (--no-cleanup)")
        info(f"Space '{SPACE_ID}' conservé")
        info(f"Mémoire '{GRAPH_MEMORY_ID}' dans Graph Memory conservée")

    # ── Résumé ───────────────────────────────────────
    dur = round(time.monotonic() - t0, 1)
    header("📊 RÉSUMÉ")
    info(f"Durée totale : {dur}s")
    info(f"Notes        : {notes_ok}/{len(NOTES)}")
    info(f"Bank files   : {len(bank_files)}")
    info(f"Erreurs      : {errors}")
    print()
    if errors == 0:
        print(f"  {G}{B}🎉 TEST GRAPH BRIDGE RÉUSSI !{Z}")
        print(f"  {G}La Memory Bank a été poussée dans le graphe{Z}")
        print(f"  {G}de connaissances avec succès.{Z}")
    else:
        print(f"  {R}{B}💥 TEST ÉCHOUÉ — {errors} erreur(s){Z}")
    print()
    return errors


# ═══════════════════════════════════════════════════════════════
# Entrée
# ═══════════════════════════════════════════════════════════════

def _read_bootstrap_key():
    """Lit ADMIN_BOOTSTRAP_KEY depuis le .env local."""
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(p):
        for line in open(p):
            if line.strip().startswith("ADMIN_BOOTSTRAP_KEY="):
                return line.strip().split("=", 1)[1].strip()
    return ""


def main():
    global STEP_MODE, GRAPH_MEMORY_ID, GRAPH_ONTOLOGY

    ap = argparse.ArgumentParser(
        description="Test du Graph Bridge — Live Memory → Graph Memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples :\n"
            "  # Via arguments\n"
            "  python scripts/test_graph_bridge.py \\\n"
            "    --graph-url https://graph-mem.mcp.cloud-temple.app \\\n"
            "    --graph-token c83c26946f39...\n"
            "\n"
            "  # Via variables d'environnement\n"
            "  export GRAPH_MEM_URL=https://graph-mem.mcp.cloud-temple.app\n"
            "  export GRAPH_MEM_TOKEN=c83c26946f39...\n"
            "  python scripts/test_graph_bridge.py --step\n"
        ),
    )
    ap.add_argument(
        "--url",
        default=os.environ.get("MCP_URL", "http://localhost:8080"),
        help="URL de Live Memory (défaut: MCP_URL ou localhost:8080)",
    )
    ap.add_argument(
        "--token",
        default=os.environ.get("ADMIN_BOOTSTRAP_KEY", ""),
        help="Bootstrap key de Live Memory (défaut: depuis .env)",
    )
    ap.add_argument(
        "--graph-url",
        default=os.environ.get("GRAPH_MEM_URL", ""),
        help="URL de Graph Memory (défaut: GRAPH_MEM_URL)",
    )
    ap.add_argument(
        "--graph-token",
        default=os.environ.get("GRAPH_MEM_TOKEN", ""),
        help="Token pour Graph Memory (défaut: GRAPH_MEM_TOKEN)",
    )
    ap.add_argument(
        "--graph-memory-id",
        default=GRAPH_MEMORY_ID,
        help=f"Memory ID dans Graph Memory (défaut: {GRAPH_MEMORY_ID})",
    )
    ap.add_argument(
        "--ontology",
        default=GRAPH_ONTOLOGY,
        help=f"Ontologie Graph Memory (défaut: {GRAPH_ONTOLOGY})",
    )
    ap.add_argument(
        "--no-cleanup", action="store_true",
        help="Ne pas supprimer l'espace après le test",
    )
    ap.add_argument(
        "--step", action="store_true",
        help="Mode pas-à-pas : appuyez sur Entrée entre chaque étape",
    )
    a = ap.parse_args()

    STEP_MODE = a.step
    STEP_MODE = a.step
    GRAPH_MEMORY_ID = a.graph_memory_id
    GRAPH_ONTOLOGY = a.ontology

    # Résoudre le token live-memory
    if not a.token:
        a.token = _read_bootstrap_key()
    if not a.token:
        print(f"{R}❌ ADMIN_BOOTSTRAP_KEY requis (--token ou .env){Z}")
        sys.exit(1)

    # Vérifier les credentials graph-memory
    if not a.graph_url:
        print(f"{R}❌ URL Graph Memory requise{Z}")
        print(f"  Utilisez --graph-url ou export GRAPH_MEM_URL=...")
        sys.exit(1)
    if not a.graph_token:
        print(f"{R}❌ Token Graph Memory requis{Z}")
        print(f"  Utilisez --graph-token ou export GRAPH_MEM_TOKEN=...")
        sys.exit(1)

    sys.exit(
        1 if asyncio.run(
            run_test(a.url, a.token, a.graph_url, a.graph_token, not a.no_cleanup)
        ) else 0
    )


if __name__ == "__main__":
    main()
