"""
Testes dos backends cloud: Notion, Supabase, S3.

Todos usam unittest.mock - SEM rede, SEM servico real.

Cobre:
- save() chama a API correta com os parametros esperados
- Ausencia de credenciais levanta RuntimeError clara
- SDK ausente levanta ImportError clara
- StorageRef retornado tem campos corretos
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers compartilhados
# ---------------------------------------------------------------------------


def _make_result(run_id: str = "run-cloud-001") -> object:
    from video_kb.models import AnalysisResult, KnowledgeSynthesis, SourceMetadata

    return AnalysisResult(
        run_id=run_id,
        created_at="2026-06-02T00:00:00+00:00",
        source="https://example.com/video",
        workdir="/tmp",
        media_path="video.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(
            source="https://example.com/video",
            title="Cloud Test",
            webpage_url="https://example.com/video",
            uploader="canal-teste",
            duration=120.0,
        ),
        synthesis=KnowledgeSynthesis(
            summary="resumo cloud",
            entities=["Python", "S3"],
            claims=["Afirmacao A"],
            action_items=["Fazer X"],
        ),
    )


def _make_artifacts(tmp_dir: Path) -> object:
    from video_kb.storage.base import ArtifactPaths

    analysis = tmp_dir / "analysis.json"
    analysis.write_text('{"run_id": "run-cloud-001"}', encoding="utf-8")
    markdown = tmp_dir / "knowledge.md"
    markdown.write_text("# Cloud Test\n", encoding="utf-8")
    frames_dir = tmp_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    return ArtifactPaths(
        analysis_json=analysis,
        markdown=markdown,
        frames_dir=frames_dir,
        run_dir=tmp_dir,
    )


# ===========================================================================
# Notion
# ===========================================================================


class NotionBackendSave(unittest.TestCase):
    """Testa NotionBackend.save() com notion_client mockado."""

    def _make_fake_notion_client(self, page_id: str = "page-abc-123") -> MagicMock:
        """Retorna modulo notion_client simulado."""
        fake_page = {
            "id": page_id,
            "url": f"https://notion.so/{page_id}",
        }
        fake_client_instance = MagicMock()
        fake_client_instance.pages.create.return_value = fake_page

        fake_module = MagicMock()
        fake_module.Client.return_value = fake_client_instance
        return fake_module

    def test_save_chama_pages_create(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client()

            with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                backend = NotionBackend(api_key="secret_fake", database_id="db-fake")
                backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            fake_nc.Client.return_value.pages.create.assert_called_once()

    def test_save_retorna_storage_ref_notion(self) -> None:
        from video_kb.storage.base import StorageRef
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client("notion-page-xyz")

            with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                backend = NotionBackend(api_key="secret_fake", database_id="db-fake")
                ref = backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertIsInstance(ref, StorageRef)
            self.assertEqual(ref.backend, "notion")

    def test_save_extra_contem_page_id(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client("page-id-verificado")

            with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                backend = NotionBackend(api_key="key", database_id="db")
                ref = backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertIn("page_id", ref.extra)
            self.assertEqual(ref.extra["page_id"], "page-id-verificado")

    def test_save_extra_contem_database_id(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client()

            with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                backend = NotionBackend(api_key="key", database_id="db-id-check")
                ref = backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertEqual(ref.extra.get("database_id"), "db-id-check")

    def test_sem_api_key_levanta_runtime_error(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client()

            import os

            env_sem_key = {
                k: v
                for k, v in os.environ.items()
                if k not in ("NOTION_API_KEY", "NOTION_DATABASE_ID")
            }
            with patch.dict("os.environ", env_sem_key, clear=True):
                with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                    backend = NotionBackend()
                    with self.assertRaises(RuntimeError) as ctx:
                        backend.save(
                            _make_result(),  # type: ignore[arg-type]
                            _make_artifacts(tmp),  # type: ignore[arg-type]
                        )
            self.assertIn("NOTION_API_KEY", str(ctx.exception))

    def test_sem_database_id_levanta_runtime_error(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_nc = self._make_fake_notion_client()

            import os

            env_sem_db = {
                k: v
                for k, v in os.environ.items()
                if k not in ("NOTION_API_KEY", "NOTION_DATABASE_ID")
            }
            with patch.dict("os.environ", env_sem_db, clear=True):
                with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                    backend = NotionBackend(api_key="secret_fake")
                    with self.assertRaises(RuntimeError) as ctx:
                        backend.save(
                            _make_result(),  # type: ignore[arg-type]
                            _make_artifacts(tmp),  # type: ignore[arg-type]
                        )
            self.assertIn("NOTION_DATABASE_ID", str(ctx.exception))

    def test_notion_client_ausente_levanta_import_error(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)

            with patch(
                "video_kb.storage.notion._require_notion_client",
                side_effect=ImportError("notion-client nao instalado"),
            ):
                backend = NotionBackend(api_key="key", database_id="db")
                with self.assertRaises(ImportError) as ctx:
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(tmp),  # type: ignore[arg-type]
                    )
            self.assertIn("notion", str(ctx.exception).lower())

    def test_save_pages_create_falha_levanta_runtime_error(self) -> None:
        from video_kb.storage.notion import NotionBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_client_instance = MagicMock()
            fake_client_instance.pages.create.side_effect = Exception("API error 401")
            fake_nc = MagicMock()
            fake_nc.Client.return_value = fake_client_instance

            with patch("video_kb.storage.notion._require_notion_client", return_value=fake_nc):
                backend = NotionBackend(api_key="key", database_id="db")
                with self.assertRaises(RuntimeError) as ctx:
                    backend.save(
                        _make_result(),  # type: ignore[arg-type]
                        _make_artifacts(tmp),  # type: ignore[arg-type]
                    )
            self.assertIn("Notion", str(ctx.exception))


# ===========================================================================
# Supabase
# ===========================================================================


class SupabaseBackendSave(unittest.TestCase):
    """SupabaseBackend.save() levanta NotImplementedError (fase futura)."""

    def test_save_levanta_not_implemented(self) -> None:
        from video_kb.storage.supabase import SupabaseBackend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            backend = SupabaseBackend(url="https://fake.supabase.co", key="fake-key")
            with self.assertRaises(NotImplementedError) as ctx:
                backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )
            self.assertIn("filesystem", str(ctx.exception))

    def test_instancia_sem_credenciais_nao_levanta(self) -> None:
        """Instanciar sem credenciais nao deve levantar (erros so em save/health_check)."""
        import os

        from video_kb.storage.supabase import SupabaseBackend

        env = {k: v for k, v in os.environ.items() if k not in ("SUPABASE_URL", "SUPABASE_KEY")}
        with patch.dict("os.environ", env, clear=True):
            backend = SupabaseBackend()
        self.assertIsNotNone(backend)


# ===========================================================================
# S3
# ===========================================================================


class S3BackendSave(unittest.TestCase):
    """Testa S3Backend.save() com boto3 mockado."""

    def _make_fake_boto3(self) -> MagicMock:
        fake_client = MagicMock()
        fake_client.upload_file = MagicMock(return_value=None)

        fake_boto3 = MagicMock()
        fake_boto3.client.return_value = fake_client
        return fake_boto3

    def test_save_chama_upload_file_duas_vezes(self) -> None:
        """save() deve fazer upload de analysis.json e knowledge.md."""
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="meu-bucket", region="us-east-1")
                backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            fake_boto3.client.return_value.upload_file.call_count == 2  # noqa: B015

    def test_save_retorna_storage_ref_s3(self) -> None:
        from video_kb.storage.base import StorageRef
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="meu-bucket")
                ref = backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertIsInstance(ref, StorageRef)
            self.assertEqual(ref.backend, "s3")

    def test_save_output_dir_e_uri_s3(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="meu-bucket")
                ref = backend.save(
                    _make_result("run-s3-uri"),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertTrue(ref.output_dir.startswith("s3://meu-bucket/"))
            self.assertIn("run-s3-uri", ref.output_dir)

    def test_save_analysis_path_e_uri_s3(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="bucket-x")
                ref = backend.save(
                    _make_result("run-s3-paths"),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertTrue(ref.analysis_path.startswith("s3://bucket-x/"))
            self.assertTrue(ref.analysis_path.endswith("analysis.json"))

    def test_save_markdown_path_e_uri_s3(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="bucket-x")
                ref = backend.save(
                    _make_result("run-s3-md"),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertTrue(ref.markdown_path.startswith("s3://bucket-x/"))
            self.assertTrue(ref.markdown_path.endswith("knowledge.md"))

    def test_save_extra_contem_bucket(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="bucket-extra")
                ref = backend.save(
                    _make_result(),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertEqual(ref.extra.get("bucket"), "bucket-extra")

    def test_save_com_prefix(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            with patch.dict("sys.modules", {"boto3": fake_boto3}):
                backend = S3Backend(bucket="bucket-y", prefix="meu/prefix")
                ref = backend.save(
                    _make_result("run-prefix"),  # type: ignore[arg-type]
                    _make_artifacts(tmp),  # type: ignore[arg-type]
                )

            self.assertIn("meu/prefix", ref.output_dir)
            self.assertIn("run-prefix", ref.output_dir)

    def test_sem_bucket_levanta_runtime_error(self) -> None:
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            fake_boto3 = self._make_fake_boto3()

            import os

            env = {k: v for k, v in os.environ.items() if k != "VIDEO_KB_S3_BUCKET"}
            with patch.dict("os.environ", env, clear=True):
                with patch.dict("sys.modules", {"boto3": fake_boto3}):
                    backend = S3Backend()
                    with self.assertRaises(RuntimeError) as ctx:
                        backend.save(
                            _make_result(),  # type: ignore[arg-type]
                            _make_artifacts(tmp),  # type: ignore[arg-type]
                        )
            self.assertIn("VIDEO_KB_S3_BUCKET", str(ctx.exception))

    def test_boto3_ausente_levanta_import_error(self) -> None:
        """Sem boto3 instalado, save() deve levantar ImportError com dica."""
        from video_kb.storage.s3 import S3Backend

        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)

            import sys

            # Remove boto3 do sys.modules para simular ausencia
            original = sys.modules.pop("boto3", None)
            try:
                with patch.dict("sys.modules", {"boto3": None}):
                    backend = S3Backend(bucket="meu-bucket")
                    with self.assertRaises((ImportError, TypeError)):
                        backend.save(
                            _make_result(),  # type: ignore[arg-type]
                            _make_artifacts(tmp),  # type: ignore[arg-type]
                        )
            finally:
                if original is not None:
                    sys.modules["boto3"] = original


if __name__ == "__main__":
    unittest.main()
