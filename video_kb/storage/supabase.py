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

    def health_check(self) -> None:
        """Valida credenciais obrigatorias do Supabase."""
        self._require_credentials()

    def _require_credentials(self) -> None:
        erros: list[str] = []
        if not self._url:
            erros.append(
                "SUPABASE_URL nao definida. Configure a URL do projeto em SUPABASE_URL "
                "ou passe url=<endpoint> ao instanciar SupabaseBackend."
            )
        if not self._key:
            erros.append(
                "SUPABASE_KEY nao definida. Configure a chave anon/service em SUPABASE_KEY "
                "ou passe key=<chave> ao instanciar SupabaseBackend."
            )
        if erros:
            raise RuntimeError("\n".join(erros))

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        self._require_credentials()
        raise NotImplementedError(
            "backend supabase ainda nao implementado; "
            "use filesystem/obsidian/notion/s3 por enquanto."
        )
