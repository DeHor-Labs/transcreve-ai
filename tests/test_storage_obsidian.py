"""
Testes do ObsidianBackend.

Cobre:
- save() cria arquivo com frontmatter YAML correto em tmp dir
- vault inexistente levanta RuntimeError clara
- vault nao configurada levanta RuntimeError clara
- python-frontmatter ausente levanta ImportError clara
- copy_frames copia diretorio de frames para a vault
- save() e idempotente (segunda chamada sobrescreve sem duplicar)
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(run_id: str = "run-obs-001") -> object:
    from video_kb.models import AnalysisResult, KnowledgeSynthesis, SourceMetadata

    return AnalysisResult(
        run_id=run_id,
        created_at="2026-06-02T00:00:00+00:00",
        source="video.mp4",
        workdir="/tmp",
        media_path="video.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(
            source="video.mp4",
            title="Titulo Obsidian",
            tags=["python", "dev"],
            categories=["tech"],
        ),
        synthesis=KnowledgeSynthesis(summary="resumo obsidian"),
    )


def _make_artifacts(run_dir: Path) -> object:
    from video_kb.storage.base import ArtifactPaths

    analysis = run_dir / "analysis.json"
    analysis.write_text("{}", encoding="utf-8")
    markdown = run_dir / "knowledge.md"
    markdown.write_text("# Titulo Obsidian\n\nConteudo.", encoding="utf-8")
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    (frames_dir / "frame_001.jpg").write_bytes(b"fake-jpeg")

    return ArtifactPaths(
        analysis_json=analysis,
        markdown=markdown,
        frames_dir=frames_dir,
        run_dir=run_dir,
    )


def _has_frontmatter() -> bool:
    try:
        import frontmatter  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Testes reais (exigem python-frontmatter)
# ---------------------------------------------------------------------------


@unittest.skipUnless(_has_frontmatter(), "python-frontmatter nao instalado")
class ObsidianBackendSave(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._vault = Path(self._tmp) / "vault"
        self._vault.mkdir()
        self._run_dir = Path(self._tmp) / "run"
        self._run_dir.mkdir()

    def test_save_cria_arquivo_na_vault(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        result = _make_result()
        artifacts = _make_artifacts(self._run_dir)
        ref = backend.save(result, artifacts)  # type: ignore[arg-type]

        dest = Path(ref.markdown_path)
        self.assertTrue(dest.exists(), f"Arquivo nao criado: {dest}")

    def test_save_retorna_backend_obsidian(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]
        self.assertEqual(ref.backend, "obsidian")

    def test_save_output_dir_dentro_da_vault(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result("run-obs-vault"), _make_artifacts(self._run_dir))  # type: ignore[arg-type]
        self.assertTrue(Path(ref.output_dir).is_relative_to(self._vault.resolve()))

    def test_save_frontmatter_contem_titulo(self) -> None:
        import frontmatter

        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]

        dest = Path(ref.markdown_path)
        post = frontmatter.load(str(dest))
        self.assertEqual(post.metadata.get("title"), "Titulo Obsidian")

    def test_save_frontmatter_contem_run_id(self) -> None:
        import frontmatter

        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result("run-obs-id-check"), _make_artifacts(self._run_dir))  # type: ignore[arg-type]

        dest = Path(ref.markdown_path)
        post = frontmatter.load(str(dest))
        self.assertEqual(post.metadata.get("run_id"), "run-obs-id-check")

    def test_save_frontmatter_contem_tags(self) -> None:
        import frontmatter

        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]

        dest = Path(ref.markdown_path)
        post = frontmatter.load(str(dest))
        tags = cast(list[str], post.metadata.get("tags", []))
        self.assertIn("python", tags)
        self.assertIn("dev", tags)

    def test_save_copy_frames_copia_diretorio(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault), copy_frames=True)
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]

        frames_dest = Path(ref.output_dir) / "frames"
        self.assertTrue(frames_dest.exists(), "Diretorio de frames nao copiado")
        self.assertTrue((frames_dest / "frame_001.jpg").exists())

    def test_save_sem_copy_frames_nao_copia(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault), copy_frames=False)
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]

        frames_dest = Path(ref.output_dir) / "frames"
        self.assertFalse(frames_dest.exists(), "Frames nao deveriam ter sido copiados")

    def test_save_idempotente(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        result = _make_result()
        artifacts = _make_artifacts(self._run_dir)
        ref1 = backend.save(result, artifacts)  # type: ignore[arg-type]
        ref2 = backend.save(result, artifacts)  # type: ignore[arg-type]
        self.assertEqual(ref1.output_dir, ref2.output_dir)
        self.assertEqual(ref1.markdown_path, ref2.markdown_path)

    def test_extra_contem_vault(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        backend = ObsidianBackend(vault_path=str(self._vault))
        ref = backend.save(_make_result(), _make_artifacts(self._run_dir))  # type: ignore[arg-type]
        self.assertIn("vault", ref.extra)


# ---------------------------------------------------------------------------
# Erros de configuracao (nao precisam de frontmatter instalado)
# ---------------------------------------------------------------------------


class ObsidianBackendErrosConfiguracao(unittest.TestCase):
    def test_vault_nao_configurada_levanta_runtime_error(self) -> None:
        """
        Sem vault configurada, save() deve levantar RuntimeError.
        Se frontmatter nao estiver instalado, levanta ImportError primeiro - ambos sao aceitaveis.
        """
        from video_kb.storage.obsidian import ObsidianBackend

        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "run"
            run_dir.mkdir()
            backend = ObsidianBackend(vault_path=None)
            import os

            env = {k: v for k, v in os.environ.items() if k != "VIDEO_KB_OBSIDIAN_VAULT"}
            with patch.dict("os.environ", env, clear=True):
                with self.assertRaises((RuntimeError, ImportError)):
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(run_dir),  # type: ignore[arg-type]
                    )

    def test_vault_inexistente_levanta_runtime_error(self) -> None:
        """
        Com vault apontando para caminho inexistente, deve levantar RuntimeError.
        Se frontmatter nao estiver instalado, levanta ImportError primeiro - ambos sao aceitaveis.
        """
        from video_kb.storage.obsidian import ObsidianBackend

        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "run"
            run_dir.mkdir()
            vault_inexistente = Path(d) / "nao_existe_vault"
            backend = ObsidianBackend(vault_path=str(vault_inexistente))
            with self.assertRaises((RuntimeError, ImportError)):
                backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(run_dir),  # type: ignore[arg-type]
                )

    def test_frontmatter_ausente_levanta_import_error(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        with tempfile.TemporaryDirectory() as d:
            vault = Path(d) / "vault"
            vault.mkdir()
            run_dir = Path(d) / "run"
            run_dir.mkdir()
            backend = ObsidianBackend(vault_path=str(vault))

            # Simula ausencia do frontmatter
            with patch.dict("sys.modules", {"frontmatter": None}):
                with self.assertRaises((ImportError, TypeError)):
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(run_dir),  # type: ignore[arg-type]
                    )

    def test_subdir_com_path_absolute_levanta_runtime_error(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "run"
            run_dir.mkdir()
            vault = Path(d) / "vault"
            vault.mkdir()

            fake_frontmatter = MagicMock()
            fake_frontmatter.loads.return_value = MagicMock(metadata={})
            fake_frontmatter.dumps.return_value = "# markdown\n"

            with patch.object(
                ObsidianBackend, "_require_frontmatter", return_value=fake_frontmatter
            ):
                backend = ObsidianBackend(vault_path=str(vault), subdir="/nao-permitido")
                with self.assertRaises(RuntimeError) as ctx:
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(run_dir),  # type: ignore[arg-type]
                    )
            self.assertIn("Subdir invalido", str(ctx.exception))

    def test_subdir_com_traversal_levanta_runtime_error(self) -> None:
        from video_kb.storage.obsidian import ObsidianBackend

        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "run"
            run_dir.mkdir()
            vault = Path(d) / "vault"
            vault.mkdir()

            fake_frontmatter = MagicMock()
            fake_frontmatter.loads.return_value = MagicMock(metadata={})
            fake_frontmatter.dumps.return_value = "# markdown\n"

            with patch.object(
                ObsidianBackend, "_require_frontmatter", return_value=fake_frontmatter
            ):
                backend = ObsidianBackend(vault_path=str(vault), subdir="../../hack")
                with self.assertRaises(RuntimeError) as ctx:
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(run_dir),  # type: ignore[arg-type]
                    )
            self.assertIn("Subdir invalido", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
