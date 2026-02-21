#!/usr/bin/env python3
"""Test rapide du Garbage Collector."""
import os, sys, asyncio, json
sys.path.insert(0, os.path.dirname(__file__))
from cli.client import MCPClient

G="\033[92m"; R="\033[91m"; C="\033[96m"; M="\033[95m"
B="\033[1m"; D="\033[2m"; Z="\033[0m"

def ok(t): print(f"  {G}✅ {t}{Z}")
def info(t): print(f"  {C}ℹ️  {t}{Z}")
def header(t): print(f"\n{B}{C}{'═'*60}{Z}\n{B}{C}  {t}{Z}\n{B}{C}{'═'*60}{Z}")

SPACE = "gc-test-space"

def read_key():
    p = os.path.join(os.path.dirname(__file__), "..", ".env")
    for l in open(p):
        if l.strip().startswith("ADMIN_BOOTSTRAP_KEY="):
            return l.strip().split("=",1)[1].strip()

async def main():
    url = os.environ.get("MCP_URL", "http://localhost:8080")
    key = read_key()
    admin = MCPClient(base_url=url, token=key, timeout=600)

    header("🗑️  TEST GARBAGE COLLECTOR")

    # 1. Créer l'espace
    info("Création espace de test...")
    r = await admin.call_tool("space_create", {
        "space_id": SPACE,
        "description": "Test GC",
        "rules": "### progress.md\nStatut du projet.",
    })
    ok(f"Espace : {r.get('status')}")

    # 2. Écrire 5 notes (simulant un agent disparu)
    info("Écriture de 5 notes (agent-disparu, SANS consolidation)...")
    token_r = await admin.call_tool("admin_create_token", {
        "name": "agent-disparu",
        "permissions": "read,write",
        "space_ids": SPACE,
    })
    agent = MCPClient(base_url=url, token=token_r["token"], timeout=600)

    for i in range(5):
        await agent.call_tool("live_note", {
            "space_id": SPACE,
            "category": "observation",
            "content": f"Note orpheline #{i+1} de l'agent disparu",
        })
    ok("5 notes écrites (non consolidées)")

    # 3. GC dry-run (max_age_days=0 pour attraper TOUTES les notes)
    header("📋 GC DRY-RUN (max_age_days=0)")
    r = await admin.call_tool("admin_gc_notes", {
        "space_id": SPACE,
        "max_age_days": 0,
        "confirm": False,
    })
    print(f"  {json.dumps(r, indent=2, ensure_ascii=False)}")

    # 4. GC consolidation forcée
    header("🔄 GC CONSOLIDATION FORCÉE (max_age_days=0)")
    info("Le GC va consolider les 5 notes dans la bank...")
    r = await admin.call_tool("admin_gc_notes", {
        "space_id": SPACE,
        "max_age_days": 0,
        "confirm": True,
    })
    print(f"  {json.dumps(r, indent=2, ensure_ascii=False)}")

    # 5. Vérifier la bank
    header("📘 BANK APRÈS GC")
    r = await admin.call_tool("bank_read_all", {"space_id": SPACE})
    for f in r.get("files", []):
        print(f"\n  {M}📄 {f['filename']}{Z}")
        for line in f.get("content","").strip().split("\n"):
            print(f"  {D}{line}{Z}")

    # 6. Vérifier qu'il ne reste plus de notes
    header("🔍 NOTES RESTANTES")
    r = await admin.call_tool("live_read", {"space_id": SPACE, "limit": 50})
    notes = r.get("notes", [])
    total = r.get("total", len(notes))
    ok(f"{total} notes restantes (attendu : 0)")

    # 7. Cleanup
    header("🧹 NETTOYAGE")
    await admin.call_tool("space_delete", {"space_id": SPACE, "confirm": True})
    ok("Espace supprimé")

    # Révoquer les tokens
    r = await admin.call_tool("admin_list_tokens", {})
    for t in r.get("tokens", []):
        if t.get("name") == "agent-disparu" and not t.get("revoked"):
            await admin.call_tool("admin_revoke_token", {"token_hash": t["hash"]})
            ok("Token agent-disparu révoqué")

    header("✅ TEST GC TERMINÉ")

asyncio.run(main())
