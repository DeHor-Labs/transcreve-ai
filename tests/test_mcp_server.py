from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from video_kb import mcp_server
from video_kb.agent_workflow import AgentWorkflowOptions, AgentWorkflowResult
from video_kb.sources import SourceProbe


class TestMcpServer(unittest.TestCase):
    def test_sources_probe_returns_structured_unknown_for_unsafe_url(self) -> None:
        payload = mcp_server.mcp_sources_probe("http://127.0.0.1/video.mp4")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["probe"]["kind"], "unknown")
        self.assertIn("local", " ".join(payload["probe"]["notes"]))

    def test_agent_run_captures_stdout_and_returns_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir) / "run-001"
            workdir.mkdir()
            analysis_path = workdir / "analysis.json"
            markdown_path = workdir / "knowledge.md"
            analysis_path.write_text("{}", encoding="utf-8")
            markdown_path.write_text("# Dossie\n", encoding="utf-8")
            result = AgentWorkflowResult(
                source="https://example.com/video.mp4",
                probe=SourceProbe(
                    source="https://example.com/video.mp4",
                    kind="direct_media_url",
                    adapter="yt_dlp_direct_media",
                    is_url=True,
                    canonical="https://example.com/video.mp4",
                ),
                provider="local",
                run_id="run-001",
                workdir=str(workdir),
                analysis_path=str(analysis_path),
                markdown_path=str(markdown_path),
            )

            def fake_run(*_: object) -> AgentWorkflowResult:
                print("progresso do pipeline")
                return result

            with patch("video_kb.mcp_server.run_agent_workflow", side_effect=fake_run):
                payload = mcp_server.mcp_agent_run(
                    "https://example.com/video.mp4",
                    out=str(workdir.parent),
                    provider="local",
                )

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["provider"], "local")
        self.assertEqual(payload["run_id"], "run-001")
        self.assertIn("progresso do pipeline", payload["logs"]["stdout"])

    def test_analyze_captures_duplicate_run_as_reused_payload(self) -> None:
        from video_kb.index import DuplicateRunError

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis_path = Path(tmpdir) / "analysis.json"
            analysis_path.write_text("{}", encoding="utf-8")
            existing = {
                "id": "run-001",
                "analysis_path": str(analysis_path),
                "markdown_path": str(Path(tmpdir) / "knowledge.md"),
            }

            def fake_run(_: str) -> object:
                print("antes do dedupe")
                raise DuplicateRunError(existing)

            with patch.object(mcp_server.VideoKnowledgePipeline, "run", side_effect=fake_run):
                payload = mcp_server.mcp_analyze(
                    "https://example.com/video.mp4",
                    out=tmpdir,
                    provider="local",
                )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["reused_existing"])
        self.assertEqual(payload["run"]["id"], "run-001")
        self.assertIn("antes do dedupe", payload["logs"]["stdout"])

    def test_analyze_duplicate_remote_artifact_reference_is_ok(self) -> None:
        from video_kb.index import DuplicateRunError

        existing = {
            "id": "remote-run",
            "analysis_path": "s3://bucket/runs/remote-run/analysis.json",
            "markdown_path": "s3://bucket/runs/remote-run/knowledge.md",
        }

        def fake_run(_: str) -> object:
            raise DuplicateRunError(existing)

        with patch.object(mcp_server.VideoKnowledgePipeline, "run", side_effect=fake_run):
            payload = mcp_server.mcp_analyze(
                "https://example.com/video.mp4",
                provider="local",
            )

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["reused_existing"])
        self.assertEqual(payload["run"]["id"], "remote-run")

    def test_runs_list_uses_isolated_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "index.db")
            from video_kb.index import RunIndex

            with RunIndex(Path(db_path)) as idx:
                idx.register(
                    "run-001",
                    "https://example.com/video.mp4",
                    "hash-001",
                    title="Demo",
                    provider="local",
                )

            payload = mcp_server.mcp_runs_list(index_db=db_path)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["runs"][0]["id"], "run-001")

    def test_agent_batch_passes_analysis_options(self) -> None:
        captured: list[AgentWorkflowOptions] = []

        def fake_batch(_: Path, options: AgentWorkflowOptions, **__: object) -> dict[str, object]:
            captured.append(options)
            return {
                "total": 1,
                "success": True,
                "ok": 1,
                "failed": 0,
                "ok_count": 1,
                "failed_count": 0,
                "items": [],
            }

        with patch("video_kb.batch.run_agent_batch", side_effect=fake_batch):
            payload = mcp_server.mcp_agent_batch(
                "/tmp/sources.txt",
                frame_interval=2.5,
                max_frames=12,
                visual_limit=4,
                vision_model="vision-demo",
                transcribe_model="transcribe-demo",
                tesseract_lang="por",
                video_format="best",
                provider="local",
                storage="filesystem",
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["ok"], 1)
        self.assertEqual(len(captured), 1)
        options = captured[0]
        self.assertEqual(options.frame_interval, 2.5)
        self.assertEqual(options.max_frames, 12)
        self.assertEqual(options.visual_limit, 4)
        self.assertEqual(options.vision_model, "vision-demo")
        self.assertEqual(options.transcribe_model, "transcribe-demo")
        self.assertEqual(options.tesseract_lang, "por")
        self.assertEqual(options.video_format, "best")
        self.assertEqual(options.provider_name, "local")
        self.assertEqual(options.storage_backend, "filesystem")

    def test_agent_batch_failure_returns_structured_error_and_logs(self) -> None:
        def fake_batch(*_: object, **__: object) -> dict[str, object]:
            print("antes da falha")
            raise RuntimeError("arquivo invalido")

        with patch("video_kb.batch.run_agent_batch", side_effect=fake_batch):
            payload = mcp_server.mcp_agent_batch("/tmp/sources.json")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "agent_batch_failed")
        self.assertIn("antes da falha", payload["logs"]["stdout"])

    def test_create_server_registers_expected_tools_when_mcp_installed(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp optional dependency is not installed")

        server = mcp_server.create_server()
        tool_names = {tool.name for tool in asyncio.run(server.list_tools())}

        self.assertIn("sources_probe", tool_names)
        self.assertIn("agent_run", tool_names)
        self.assertIn("agent_batch", tool_names)
        self.assertIn("ask", tool_names)

    def test_registered_tool_returns_structured_payload_when_mcp_installed(self) -> None:
        try:
            import mcp  # noqa: F401
        except ImportError:
            self.skipTest("mcp optional dependency is not installed")

        async def call_probe() -> dict[str, Any]:
            server = mcp_server.create_server()
            _, structured = await server.call_tool(
                "sources_probe",
                {"source": "http://127.0.0.1/video.mp4"},
            )
            return structured

        payload = asyncio.run(call_probe())

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["probe"]["kind"], "unknown")

    def test_mcp_ask_search_only_serializes_hits(self) -> None:
        hit = SimpleNamespace(
            run_id="run-001",
            chunk_id="chunk-001",
            chunk_type="summary",
            title="Demo",
            score=0.98,
            excerpt="Trecho relevante",
            chapter_start=None,
            metadata={"k": "v"},
        )
        provider = SimpleNamespace(capabilities=lambda: ["embed"], embed=lambda _: [[0.1]])

        with patch("video_kb.providers.load_provider", return_value=provider):
            with patch("video_kb.embeddings.search", return_value=[hit]):
                payload = mcp_server.mcp_ask(
                    "o que aparece?",
                    provider="local",
                    search_only=True,
                    index_db="/tmp/transcreveai-test-mcp-ask.db",
                )

        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["answer"])
        self.assertEqual(payload["sources"][0]["chunk_id"], "chunk-001")


if __name__ == "__main__":
    unittest.main()
