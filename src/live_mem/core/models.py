# -*- coding: utf-8 -*-
"""
Modèles Pydantic — Structures de données de Live Memory.

Ces modèles définissent les objets échangés entre les services (storage,
space, consolidator, tokens, backup) et sérialisés en JSON/Markdown sur S3.

Voir S3_DATA_MODEL.md pour l'arborescence S3 complète.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# Space — Métadonnées d'un espace mémoire
# =============================================================================

class GraphMemoryConfig(BaseModel):
    """
    Configuration de connexion vers une instance Graph Memory.

    Permet à un space de pousser ses fichiers bank dans un graphe
    de connaissances pour la mémoire long terme.

    Stocké dans _meta.json, champ "graph_memory".
    """
    url: str = ""                               # URL SSE de graph-memory (ex: "http://localhost:8080/sse")
    token: str = ""                             # Bearer token pour graph-memory
    memory_id: str = ""                         # Memory cible dans graph-memory
    ontology: str = "general"                   # Ontologie graph-memory à utiliser
    last_push: Optional[str] = None             # ISO 8601 du dernier push
    push_count: int = 0                         # Nombre total de pushs effectués
    files_pushed: int = 0                       # Nombre de fichiers poussés au dernier push


class SpaceMeta(BaseModel):
    """
    Métadonnées d'un espace (_meta.json sur S3).

    Créé par space_create, mis à jour par bank_consolidate.
    """
    space_id: str
    description: str = ""
    owner: str = ""
    created_at: str = ""                        # ISO 8601
    last_consolidation: Optional[str] = None    # ISO 8601 ou None
    consolidation_count: int = 0
    total_notes_processed: int = 0
    graph_memory: Optional[GraphMemoryConfig] = None  # Connexion graph-memory
    version: int = 1


# =============================================================================
# Live — Notes en temps réel
# =============================================================================

class LiveNote(BaseModel):
    """
    Une note live (front-matter YAML + contenu Markdown).

    Chaque note = 1 fichier S3 unique dans {space_id}/live/.
    Naming convention : {YYYYMMDD}T{HHMMSS}_{agent}_{category}_{uuid8}.md
    """
    filename: str = ""              # Nom du fichier S3 (sans le préfixe)
    timestamp: str = ""             # ISO 8601
    agent: str = ""                 # Identifiant de l'agent auteur
    category: str = ""              # observation, decision, todo, insight, question, progress, issue
    tags: list[str] = Field(default_factory=list)
    space_id: str = ""
    content: str = ""               # Corps de la note (sans le front-matter)
    size: int = 0                   # Taille en octets du fichier complet

    # Catégories autorisées
    VALID_CATEGORIES: list[str] = [
        "observation", "decision", "todo", "insight",
        "question", "progress", "issue"
    ]


# =============================================================================
# Bank — Fichiers consolidés
# =============================================================================

class BankFile(BaseModel):
    """
    Un fichier de la memory bank (Markdown pur, sans front-matter).

    Les fichiers bank sont créés et maintenus exclusivement par le LLM
    lors de la consolidation. Les noms sont décidés par le LLM selon les rules.
    """
    filename: str = ""              # Ex: "activeContext.md"
    content: str = ""               # Contenu Markdown complet
    size: int = 0                   # Taille en octets
    last_modified: Optional[str] = None  # ISO 8601
    action: str = ""                # "created", "updated", "unchanged" (post-consolidation)


# =============================================================================
# Tokens — Authentification
# =============================================================================

class TokenInfo(BaseModel):
    """
    Infos d'un token d'authentification (stocké dans _system/tokens.json).

    Le token en clair n'est JAMAIS stocké — seul le hash SHA-256 est conservé.
    """
    hash: str = ""                  # "sha256:{hex}" — identifiant unique
    name: str = ""                  # Nom descriptif (ex: "agent-cline")
    permissions: list[str] = Field(default_factory=list)  # ["read"], ["read", "write"], etc.
    space_ids: list[str] = Field(default_factory=list)    # [] = tous les espaces
    created_at: str = ""            # ISO 8601
    expires_at: Optional[str] = None  # ISO 8601 ou None (jamais)
    last_used_at: Optional[str] = None
    revoked: bool = False


class TokensStore(BaseModel):
    """
    Registre complet des tokens (_system/tokens.json).

    Protégé par un asyncio.Lock pour éviter les conflits
    lors de modifications concurrentes par plusieurs admins.
    """
    version: int = 1
    tokens: list[TokenInfo] = Field(default_factory=list)


# =============================================================================
# Backup — Sauvegarde & restauration
# =============================================================================

class BackupMeta(BaseModel):
    """
    Métadonnées d'un backup (snapshot d'un espace).

    Stocké dans _backups/{space_id}/{timestamp}/.
    """
    backup_id: str = ""             # "space_id/timestamp"
    space_id: str = ""
    timestamp: str = ""             # ISO 8601
    description: str = ""
    files_count: int = 0
    total_size: int = 0
    created_at: str = ""            # ISO 8601


# =============================================================================
# Consolidation — Résultat du pipeline LLM
# =============================================================================

class ConsolidationResult(BaseModel):
    """
    Résultat d'une consolidation LLM.

    Retourné par bank_consolidate avec les métriques d'exécution.
    """
    notes_processed: int = 0
    notes_remaining: int = 0        # Si > consolidation_max_notes
    bank_files_updated: int = 0
    bank_files_created: int = 0
    bank_files_unchanged: int = 0
    synthesis_size: int = 0
    llm_tokens_used: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    duration_seconds: float = 0.0
