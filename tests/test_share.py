from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_kb.index import RunIndex
from video_kb.share import ShareRunError, share_run, shared_catalog


class TestShareRun(unittest.TestCase):
    def test_share_run_from_index_writes_handoff_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "outputs" / "run-001"
            run_dir.mkdir(parents=True)
            analysis_path = run_dir / "analysis.json"
            markdown_path = run_dir / "knowledge.md"
            analysis_path.write_text(
                json.dumps(
                    {
                        "run_id": "run-001",
                        "created_at": "2026-07-05T12:00:00Z",
                        "source": "https://example.com/video.mp4",
                        "metadata": {"title": "Demo Video"},
                        "synthesis": {
                            "summary": "Resumo reutilizavel.",
                            "tools_or_products": ["TranscreveAI"],
                            "action_items": ["Salvar o pacote."],
                        },
                    }
                ),
                encoding="utf-8",
            )
            markdown_path.write_text("# Demo\n\nConteudo.", encoding="utf-8")
            (run_dir / "content.md").write_text(
                "# Content\napi_key=secret\nAuthorization: Bearer secret-token\nCookie: a=b; c=d\n",
                encoding="utf-8",
            )
            db_path = tmp / "index.db"
            with RunIndex(db_path) as idx:
                idx.register(
                    "run-001",
                    "https://example.com/video.mp4",
                    "hash",
                    title="Demo Video",
                    output_dir=str(run_dir),
                    analysis_path=str(analysis_path),
                    markdown_path=str(markdown_path),
                )

            payload = share_run(
                run_id="run-001",
                out_dir=tmp / "shared",
                index_db=str(db_path),
            )

            share_dir = Path(payload["share_dir"])
            self.assertTrue((share_dir / "handoff.md").exists())
            self.assertTrue((share_dir / "manifest.json").exists())
            self.assertTrue((share_dir / "knowledge.md").exists())
            self.assertTrue((share_dir / "analysis.json").exists())
            self.assertTrue((share_dir / "content.md").exists())
            shared_content = (share_dir / "content.md").read_text(encoding="utf-8")
            self.assertIn("api_key=[redacted]", shared_content)
            self.assertIn("Authorization: [redacted]", shared_content)
            self.assertIn("Cookie: [redacted]", shared_content)
            self.assertNotIn("secret-token", shared_content)
            self.assertNotIn("a=b", shared_content)
            self.assertEqual(payload["run_id"], "run-001")
            self.assertEqual(payload["title"], "Demo Video")
            self.assertEqual(payload["source_mode"], "index")
            self.assertEqual(payload["index_db"], str(db_path.resolve()))
            self.assertEqual(payload["index_db_scope"], "isolated")
            self.assertTrue(Path(payload["catalog_json"]).exists())
            self.assertTrue(Path(payload["catalog_md"]).exists())
            catalog = json.loads(Path(payload["catalog_json"]).read_text(encoding="utf-8"))
            self.assertEqual(catalog["entries"][0]["run_id"], "run-001")
            shared = shared_catalog(out_dir=tmp / "shared")
            self.assertEqual(shared["entries"][0]["run_id"], "run-001")
            self.assertIn("O dossie", (share_dir / "handoff.md").read_text(encoding="utf-8"))

    def test_share_run_from_dir_does_not_claim_default_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            run_dir = tmp / "outputs" / "run-001"
            run_dir.mkdir(parents=True)
            (run_dir / "analysis.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-001",
                        "source": "https://example.com/video.mp4?token=secret-token&keep=1",
                        "metadata": {"title": "Demo"},
                        "synthesis": {
                            "summary": (
                                "Resumo em https://u:p@example.com/path. "
                                "Authorization: Bearer secret-token"
                            )
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "knowledge.md").write_text(
                "# Demo\n\napi_key=secret https://example.com/video.mp4?token=secret-token\n"
                'token="quoted secret"',
                encoding="utf-8",
            )

            payload = share_run(run_dir=run_dir, out_dir=tmp / "shared")
            share_dir = Path(payload["share_dir"])
            handoff = Path(payload["handoff_md"]).read_text(encoding="utf-8")
            shared_analysis = (share_dir / "analysis.json").read_text(encoding="utf-8")
            shared_knowledge = (share_dir / "knowledge.md").read_text(encoding="utf-8")
            catalog = Path(payload["catalog_json"]).read_text(encoding="utf-8")
            serialized = json.dumps(payload, ensure_ascii=False)

            self.assertEqual(payload["source_mode"], "run_dir")
            self.assertEqual(payload["index_db"], "")
            self.assertEqual(payload["index_db_scope"], "not_used")
            self.assertIn("Index DB: not used (not_used)", handoff)
            self.assertNotIn("secret-token", serialized)
            self.assertNotIn("secret-token", handoff)
            self.assertNotIn("secret-token", shared_analysis)
            self.assertNotIn("secret-token", shared_knowledge)
            self.assertNotIn("secret-token", catalog)
            self.assertNotIn("quoted secret", shared_knowledge)
            self.assertIn("token=%5Bredacted%5D", shared_analysis)
            self.assertIn("api_key=[redacted]", shared_knowledge)

    def test_share_run_requires_local_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "index.db"
            with RunIndex(db_path) as idx:
                idx.register(
                    "remote-run",
                    "https://example.com/video.mp4",
                    "hash",
                    analysis_path="https://example.com/run/analysis.json?token=secret-token",
                    markdown_path="s3://bucket/run/knowledge.md",
                )

            with self.assertRaises(ShareRunError) as ctx:
                share_run(
                    run_id="remote-run",
                    out_dir=Path(tmpdir) / "shared",
                    index_db=str(db_path),
                )
            self.assertNotIn("secret-token", str(ctx.exception))

    def test_share_run_rejects_same_directory_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run-001"
            run_dir.mkdir()
            (run_dir / "analysis.json").write_text('{"run_id":"run-001"}', encoding="utf-8")
            (run_dir / "knowledge.md").write_text("# Demo\n", encoding="utf-8")

            with self.assertRaises(ShareRunError):
                share_run(run_dir=run_dir, out_dir=Path(tmpdir))


if __name__ == "__main__":
    unittest.main()
