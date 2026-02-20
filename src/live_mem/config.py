# -*- coding: utf-8 -*-
"""
Configuration du service MCP Live Memory via pydantic-settings.

Toutes les variables sont chargées depuis :
1. Variables d'environnement (priorité haute)
2. Fichier .env (priorité basse)

Usage :
    from .config import get_settings
    settings = get_settings()
    print(settings.s3_bucket_name)
"""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration chargée depuis les variables d'env / .env."""

    # ─── Serveur MCP ───────────────────────────────────────────
    mcp_server_name: str = "Live Memory"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8002
    mcp_server_debug: bool = False

    # ─── Auth ──────────────────────────────────────────────────
    # Clé bootstrap pour le premier accès admin.
    # ⚠️ Changer impérativement en production !
    admin_bootstrap_key: str = "change_me_in_production"

    # ─── S3 Cloud Temple (Dell ECS) ────────────────────────────
    # Configuration HYBRIDE obligatoire : SigV2 pour PUT/GET/DELETE,
    # SigV4 pour HEAD/LIST. Voir CLOUD_TEMPLE_SERVICES.md.
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_bucket_name: str = "live-mem"
    s3_region_name: str = "fr1"

    # ─── LLMaaS Cloud Temple ──────────────────────────────────
    # API OpenAI-compatible. L'URL INCLUT déjà /v1 — ne pas l'ajouter.
    llmaas_api_url: str = ""
    llmaas_api_key: str = ""
    llmaas_model: str = "qwen3-2507:235b"
    llmaas_max_tokens: int = 100000
    llmaas_temperature: float = 0.3

    # ─── Consolidation ────────────────────────────────────────
    consolidation_timeout: int = 600        # Timeout par appel LLM (secondes)
    consolidation_max_notes: int = 500      # Max notes traitées par consolidation

    # extra="ignore" permet d'avoir des variables dans .env (SITE_ADDRESS, WAF_PORT)
    # qui ne sont pas déclarées dans Settings (utilisées par Docker/Caddy uniquement)
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    """Singleton Settings (cached)."""
    return Settings()
