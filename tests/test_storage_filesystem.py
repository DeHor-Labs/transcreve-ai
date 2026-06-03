"""
Testes do FilesystemBackend.

Cobre: save() retorna StorageRef correto, paths existentes,
backend nao move arquivos.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


def _make_result(run_dir: Path) -> object:
    """Cria um AnalysisResult minimo para uso nos testes."""
    from video_kb.models import AnalysisResult, KnowledgeSynthesis, SourceMetadata

    return AnalysisResult(
        run_id="test-fs-001",
        created_at="2026-06-02T00:00:00+00:00",
        source="video.mp4",
        workdir=str(run_dir),
        media_path="video.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(source="video.mp4", title="Teste"),
        synthesis=KnowledgeSynthesis(summary="ok"),
    )


def _make_artifacts(run_dir: Path) -> object:
    """Cria ArtifactPaths com arquivos vazios no run_dir."""
    from video_kb.storage.base import ArtifactPaths

    analysis = run_dir / "analysis.json"
    analysis.write_text("{}", encoding="utf-8")
    markdown = run_dir / "knowledge.md"
    markdown.write_text("# ok", encoding="utf-8")
    frames_dir = run_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    return ArtifactPaths(
        analysis_json=analysis,
        markdown=markdown,
        frames_dir=frames_dir,
        run_dir=run_dir,
    )


class FilesystemBackendSave(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._run_dir = Path(self._tmp) / "run-test"
        self._run_dir.mkdir()

    def test_save_retorna_storage_ref(self) -> None:
        from video_kb.storage.base import StorageRef
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        result = _make_result(self._run_dir)
        artifacts = _make_artifacts(self._run_dir)
        ref = backend.save(result, artifacts)  # type: ignore[arg-type]
        self.assertIsInstance(ref, StorageRef)

    def test_save_backend_e_filesystem(self) -> None:
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        ref = backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            _make_artifacts(self._run_dir),  # type: ignore[arg-type]
        )
        self.assertEqual(ref.backend, "filesystem")

    def test_save_output_dir_e_run_dir(self) -> None:
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        ref = backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            _make_artifacts(self._run_dir),  # type: ignore[arg-type]
        )
        self.assertEqual(ref.output_dir, str(self._run_dir))

    def test_save_analysis_path_correto(self) -> None:
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        ref = backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            _make_artifacts(self._run_dir),  # type: ignore[arg-type]
        )
        self.assertEqual(ref.analysis_path, str(self._run_dir / "analysis.json"))

    def test_save_markdown_path_correto(self) -> None:
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        ref = backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            _make_artifacts(self._run_dir),  # type: ignore[arg-type]
        )
        self.assertEqual(ref.markdown_path, str(self._run_dir / "knowledge.md"))

    def test_save_nao_move_arquivos(self) -> None:
        """FilesystemBackend nao deve criar nem mover arquivos."""
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        artifacts = _make_artifacts(self._run_dir)

        antes = set(self._run_dir.rglob("*"))
        backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            artifacts,  # type: ignore[arg-type]
        )
        depois = set(self._run_dir.rglob("*"))

        self.assertEqual(antes, depois)

    def test_save_extra_e_dict_vazio(self) -> None:
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        ref = backend.save(
            _make_result(self._run_dir),  # type: ignore[arg-type]
            _make_artifacts(self._run_dir),  # type: ignore[arg-type]
        )
        self.assertIsInstance(ref.extra, dict)
        self.assertEqual(len(ref.extra), 0)

    def test_save_idempotente(self) -> None:
        """Chamar save() duas vezes retorna refs equivalentes."""
        from video_kb.storage.filesystem import FilesystemBackend

        backend = FilesystemBackend()
        result = _make_result(self._run_dir)
        artifacts = _make_artifacts(self._run_dir)
        ref1 = backend.save(result, artifacts)  # type: ignore[arg-type]
        ref2 = backend.save(result, artifacts)  # type: ignore[arg-type]
        self.assertEqual(ref1.output_dir, ref2.output_dir)
        self.assertEqual(ref1.analysis_path, ref2.analysis_path)


if __name__ == "__main__":
    unittest.main()
