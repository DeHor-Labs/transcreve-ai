"""
Backend de armazenamento para vault do Obsidian.

Copia knowledge.md (e opcionalmente os frames) para uma subpasta dentro
da vault, adicionando frontmatter YAML ao markdown copiado.

Configuracao via variaveis de ambiente:
    VIDEO_KB_OBSIDIAN_VAULT   caminho absoluto da vault (obrigatorio se nao
                              passado como opt vault_path)
    VIDEO_KB_OBSIDIAN_SUBDIR  subpasta dentro da vault
                              (default: "transcreve-ai")

Dependencia opcional:
    python-frontmatter  --  instale com: pip install transcreve-ai[obsidian]
"""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from ..models import AnalysisResult
from .base import ArtifactPaths, StorageBackend, StorageRef

_ENV_VAULT = "VIDEO_KB_OBSIDIAN_VAULT"
_ENV_SUBDIR = "VIDEO_KB_OBSIDIAN_SUBDIR"
_DEFAULT_SUBDIR = "transcreve-ai"


class ObsidianBackend(StorageBackend):
    """
    Persiste o dossie de analise numa vault do Obsidian.

    Fluxo de save():
    1. Resolve o caminho da vault (opt > env > erro claro).
    2. Importa python-frontmatter (erro claro se ausente).
    3. Le knowledge.md ja gravado pelo pipeline.
    4. Injeta frontmatter YAML (titulo, fonte, provider, data, tags).
    5. Grava em <vault>/<subdir>/<run_id>/knowledge.md.
    6. Se houver frames e copy_frames=True, copia o diretorio inteiro.
    7. Retorna StorageRef com os paths finais.
    """

    def __init__(
        self,
        vault_path: str | None = None,
        subdir: str | None = None,
        copy_frames: bool = False,
        **_opts: Any,
    ) -> None:
        self._vault_path = vault_path or os.environ.get(_ENV_VAULT)
        self._subdir = subdir or os.environ.get(_ENV_SUBDIR) or _DEFAULT_SUBDIR
        self._copy_frames = copy_frames

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------

    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        """Copia o dossie para a vault e retorna a referencia final."""
        fm = self._require_frontmatter()
        vault = self._resolve_vault()

        dest_dir = vault / self._subdir / result.run_id
        dest_dir.mkdir(parents=True, exist_ok=True)

        # --- markdown com frontmatter injetado ---
        dest_md = dest_dir / "knowledge.md"
        raw_text = (
            artifacts.markdown.read_text(encoding="utf-8") if artifacts.markdown.exists() else ""
        )
        post = fm.loads(raw_text)
        post.metadata.update(self._build_frontmatter(result))
        dest_md.write_text(fm.dumps(post), encoding="utf-8")

        # --- frames (opcional) ---
        copy_frames = bool(opts.get("copy_frames", self._copy_frames))
        frames_dest: str | None = None
        if copy_frames and artifacts.frames_dir.exists():
            frames_dest_path = dest_dir / "frames"
            if frames_dest_path.exists():
                shutil.rmtree(frames_dest_path)
            shutil.copytree(artifacts.frames_dir, frames_dest_path)
            frames_dest = str(frames_dest_path)

        extra: dict[str, Any] = {"vault": str(vault)}
        if frames_dest:
            extra["frames_dir"] = frames_dest

        return StorageRef(
            backend="obsidian",
            output_dir=str(dest_dir),
            analysis_path=str(artifacts.analysis_json),
            markdown_path=str(dest_md),
            extra=extra,
        )

    def health_check(self) -> None:
        """Verifica vault acessivel e python-frontmatter instalado."""
        self._require_frontmatter()
        self._resolve_vault()

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _resolve_vault(self) -> Path:
        if not self._vault_path:
            raise RuntimeError(
                "Vault do Obsidian nao configurada. "
                f"Defina a variavel de ambiente {_ENV_VAULT} "
                "ou passe vault_path=... ao instanciar ObsidianBackend."
            )
        vault = Path(self._vault_path).expanduser().resolve()
        if not vault.exists():
            raise RuntimeError(
                f"Vault do Obsidian nao encontrada: {vault}. "
                "Verifique se o caminho esta correto e se a vault existe."
            )
        return vault

    @staticmethod
    def _require_frontmatter() -> Any:
        """Importa python-frontmatter ou levanta erro acionavel."""
        try:
            import frontmatter  # type: ignore[import-untyped]  # noqa: PLC0415

            return frontmatter
        except ImportError as exc:
            raise ImportError(
                "A dependencia 'python-frontmatter' e necessaria para o backend Obsidian. "
                "Instale com: pip install transcreve-ai[obsidian]"
            ) from exc

    @staticmethod
    def _build_frontmatter(result: AnalysisResult) -> dict[str, Any]:
        meta = result.metadata
        tags: list[str] = list(meta.tags or [])
        if meta.categories:
            tags.extend(meta.categories)

        title = meta.title or meta.source or result.run_id

        return {
            "title": title,
            "fonte": meta.webpage_url or meta.source or result.source,
            "provider": meta.extractor or "",
            "data": result.created_at[:10] if result.created_at else str(date.today()),
            "tags": tags,
            "run_id": result.run_id,
        }
