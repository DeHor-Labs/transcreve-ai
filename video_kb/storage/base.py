"""
Interface abstrata de armazenamento plugavel.

Cada backend recebe os artefatos ja gravados localmente pelo pipeline
e os persiste no destino (filesystem, Obsidian, Notion, Supabase, S3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import AnalysisResult


@dataclass
class ArtifactPaths:
    """Caminhos dos artefatos produzidos pelo pipeline antes de save()."""

    analysis_json: Path  # run_dir / "analysis.json"
    markdown: Path  # run_dir / "knowledge.md"
    frames_dir: Path  # run_dir / "frames/"
    run_dir: Path  # diretorio raiz do run


@dataclass
class StorageRef:
    """Referencia retornada por save(); usada para preencher o indice."""

    backend: str  # nome do backend ("filesystem", "s3", ...)
    output_dir: str  # path ou URI do diretorio/prefixo final
    analysis_path: str  # path ou URI de analysis.json
    markdown_path: str  # path ou URI de knowledge.md
    extra: dict[str, Any] = field(default_factory=dict)  # metadados extras do backend


class StorageBackend(ABC):
    """
    Interface de armazenamento plugavel.

    O metodo save() recebe o resultado da analise e os caminhos
    dos artefatos ja gravados localmente pelo pipeline (etapa 6).
    Deve persistir os artefatos no destino e retornar um StorageRef
    com as referencias finais para registro no indice.

    O adapter filesystem e o unico que nao move arquivos: apenas
    retorna os paths locais ja existentes (comportamento atual).
    """

    @abstractmethod
    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        """
        Persiste os artefatos no backend e retorna a referencia final.

        Deve ser idempotente: chamadas repetidas com o mesmo run_id
        nao devem duplicar dados no destino.
        """
        ...

    def health_check(self) -> None:
        """
        Verifica conectividade/credenciais do backend.
        Levanta RuntimeError com mensagem clara se algo estiver errado.
        Implementacao default: noop (filesystem nao precisa checar nada).
        """
