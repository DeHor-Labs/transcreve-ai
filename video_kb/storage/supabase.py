"""
Backend de armazenamento Supabase.

Upload de artefatos para bucket e upsert na tabela runs.
Requer: pip install transcreve-ai[supabase]  (supabase>=2.0.0)

Configuracao via env:
    SUPABASE_URL     URL do projeto Supabase (obrigatorio)
    SUPABASE_KEY     Chave anon/service do Supabase (obrigatorio)
    SUPABASE_BUCKET  Nome do bucket (default: "transcreve-ai")
"""

from __future__ import annotations

from typing import Any

from ..models import AnalysisResult
from .base import ArtifactPaths, StorageBackend, StorageRef


class SupabaseBackend(StorageBackend):
    """Backend Supabase - implementacao completa em fase futura."""

    def __init__(self, **opts: Any) -> None:
        import os

        self._url = opts.get("url") or os.environ.get("SUPABASE_URL") or ""
        self._key = opts.get("key") or os.environ.get("SUPABASE_KEY") or ""
        self._bucket = opts.get("bucket") or os.environ.get("SUPABASE_BUCKET") or "transcreve-ai"

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        raise NotImplementedError(
            "backend supabase ainda nao implementado; "
            "use filesystem/obsidian/notion/s3 por enquanto."
        )
