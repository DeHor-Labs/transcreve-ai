"""
Backend de armazenamento filesystem (comportamento padrao).

Nao move nenhum arquivo: apenas retorna os paths locais ja existentes
gravados pelo pipeline na etapa 6. Compativel com o comportamento
anterior ao modulo de storage.
"""

from __future__ import annotations

from typing import Any

from ..models import AnalysisResult
from .base import ArtifactPaths, StorageBackend, StorageRef


class FilesystemBackend(StorageBackend):
    """
    Backend filesystem: zero side-effects alem dos que o pipeline ja faz.

    Os artefatos (analysis.json, knowledge.md) ja foram gravados pelo
    pipeline antes de save() ser chamado. Este backend apenas consolida
    as referencias em um StorageRef para registro no indice.
    """

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        return StorageRef(
            backend="filesystem",
            output_dir=str(artifacts.run_dir),
            analysis_path=str(artifacts.analysis_json),
            markdown_path=str(artifacts.markdown),
            extra={},
        )
