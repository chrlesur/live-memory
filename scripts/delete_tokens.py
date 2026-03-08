#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour gérer les tokens sur un serveur Live Memory distant.

Usage:
    export MCP_URL=https://live-mem.mcp.cloud-temple.app
    export MCP_TOKEN=...
    python scripts/delete_tokens.py list          # Lister les tokens
    python scripts/delete_tokens.py revoke_all    # Révoquer tous les tokens actifs
    python scripts/delete_tokens.py purge         # Supprimer physiquement les tokens révoqués
    python scripts/delete_tokens.py purge_all     # Supprimer physiquement TOUS les tokens
"""

import sys
import os
import asyncio
import json

# Ajouter le dossier scripts au path pour importer le client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "cli"))
from client import MCPClient


async def list_tokens(client: MCPClient):
    """Liste tous les tokens sur le serveur."""
    print("📋 Appel de admin_list_tokens...")
    result = await client.call_tool("admin_list_tokens", {})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


async def revoke_all_tokens(client: MCPClient):
    """Révoque tous les tokens (les rend inutilisables, sans les supprimer)."""
    print("📋 Récupération de la liste des tokens...")
    result = await client.call_tool("admin_list_tokens", {})

    if result.get("status") == "error":
        print(f"❌ Erreur : {result.get('message')}")
        return

    tokens = result.get("tokens", [])
    if not tokens:
        print("✅ Aucun token à révoquer.")
        return

    print(f"\n🔍 {len(tokens)} token(s) trouvé(s) :")
    for t in tokens:
        name = t.get("name", "?")
        hash_short = t.get("hash", t.get("token_hash", "?"))
        revoked = t.get("revoked", False)
        print(f"  - {name} | hash={hash_short} | revoked={revoked}")

    # Révoquer chaque token non révoqué
    revoked_count = 0
    for t in tokens:
        hash_short = t.get("hash", t.get("token_hash", ""))
        name = t.get("name", "?")
        revoked = t.get("revoked", False)

        if revoked:
            print(f"  ⏭️  {name} ({hash_short}) — déjà révoqué, on passe")
            continue

        print(f"\n🗑️  Révocation de '{name}' (hash={hash_short})...")
        rev_result = await client.call_tool("admin_revoke_token", {"token_hash": hash_short})
        print(f"   → {json.dumps(rev_result, ensure_ascii=False)}")
        revoked_count += 1

    print(f"\n✅ {revoked_count} token(s) révoqué(s).")


async def purge_tokens(client: MCPClient, revoked_only: bool = True):
    """
    Supprime physiquement les tokens du registre S3.

    Args:
        revoked_only: True = uniquement les révoqués, False = TOUS
    """
    mode = "révoqués uniquement" if revoked_only else "TOUS les tokens"
    print(f"🧹 Purge des tokens ({mode})...")
    print(f"   Appel de admin_purge_tokens(revoked_only={revoked_only})...")

    result = await client.call_tool("admin_purge_tokens", {"revoked_only": revoked_only})
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if result.get("status") == "ok":
        deleted = result.get("deleted", 0)
        remaining = result.get("remaining", 0)
        print(f"\n✅ {deleted} token(s) supprimé(s) physiquement. {remaining} restant(s).")
    else:
        print(f"\n❌ Erreur : {result.get('message', 'inconnue')}")


async def main():
    url = os.environ.get("MCP_URL", "")
    token = os.environ.get("MCP_TOKEN", "")

    if not url or not token:
        print("❌ Variables MCP_URL et MCP_TOKEN requises.")
        print("   export MCP_URL=https://live-mem.mcp.cloud-temple.app")
        print("   export MCP_TOKEN=...")
        sys.exit(1)

    client = MCPClient(base_url=url, token=token, timeout=30.0)

    action = sys.argv[1] if len(sys.argv) > 1 else "list"

    if action == "list":
        await list_tokens(client)
    elif action == "revoke_all":
        await revoke_all_tokens(client)
    elif action == "purge":
        await purge_tokens(client, revoked_only=True)
    elif action == "purge_all":
        await purge_tokens(client, revoked_only=False)
    else:
        print(f"❌ Action inconnue : {action}")
        print("   Usage : python scripts/delete_tokens.py [list|revoke_all|purge|purge_all]")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
