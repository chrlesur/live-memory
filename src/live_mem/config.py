# -*- coding: utf-8 -*-
"""Configuration du service MCP via pydantic-settings."""

from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration chargée depuis les variables d'env / .env."""

    # --- Serveur MCP ---
    mcp_server_name: str = "mon-mcp-service"
    mcp_server_host: str = "0.0.0.0"
    mcp_server_port: int = 8002
    mcp_server_debug: bool = False

    # --- Auth ---
    admin_bootstrap_key: str = "change_me_in_production"

    # --- Vos services métier (exemples) ---
    # database_url: str = "postgresql://user:pass@db:5432/mydb"
    # redis_url: str = "redis://redis:6379/0"
    # external_api_key: str = ""
    # external_api_url: str = "https://api.example.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    """Singleton Settings (cached)."""
    return Settings()
