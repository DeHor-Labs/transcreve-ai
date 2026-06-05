from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _run_cmd(argv: list[str]) -> tuple[str, str, int]:
    from video_kb.cli import main

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    code = 0
    with patch("sys.argv", ["transcreveai"] + argv):
        with patch("sys.stdout", buf_out):
            with patch("sys.stderr", buf_err):
                try:
                    main()
                except SystemExit as exc:
                    code = int(exc.code) if exc.code is not None else 0
    return buf_out.getvalue(), buf_err.getvalue(), code


class TestCliAgentRun(unittest.TestCase):
    def test_agent_run_unknown_source_json_exits_nonzero(self) -> None:
        out, err, code = _run_cmd(["agent", "run", "./README.md", "--json"])

        self.assertEqual(code, 1, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["probe"]["kind"], "unknown")
        self.assertFalse(payload["run_id"])
        self.assertGreater(len(payload["warnings"]), 0)

    def test_agent_run_unsafe_source_json_exits_nonzero(self) -> None:
        out, err, code = _run_cmd(["agent", "run", "http://127.0.0.1/video.mp4", "--json"])

        self.assertEqual(code, 1, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["probe"]["kind"], "unknown")
        self.assertFalse(payload["run_id"])
        warnings = " ".join(payload["warnings"])
        notes = " ".join(payload["probe"]["notes"])
        self.assertIn("validacao de seguranca", warnings)
        self.assertIn("local", notes)

    def test_agent_run_with_mocked_pipeline_outputs_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "video.mp4"
            source.write_bytes(b"fake")
            workdir = Path(tmpdir) / "outputs" / "run-001"
            workdir.mkdir(parents=True)
            (workdir / "knowledge.md").write_text("# Dossie\n", encoding="utf-8")
            (workdir / "analysis.json").write_text("{}", encoding="utf-8")

            fake_result = SimpleNamespace(
                run_id="run-001",
                workdir=str(workdir),
                warnings=[],
            )

            with patch(
                "video_kb.agent_workflow.VideoKnowledgePipeline.run",
                return_value=fake_result,
            ):
                out, err, code = _run_cmd(
                    ["agent", "run", str(source), "--out", str(workdir.parent), "--json"]
                )

        self.assertEqual(code, 0, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["probe"]["kind"], "local_file")
        self.assertEqual(payload["run_id"], "run-001")
        self.assertTrue(payload["markdown_path"].endswith("knowledge.md"))
        self.assertFalse(payload["reused_existing"])

    def test_agent_run_pipeline_error_returns_structured_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "video.mp4"
            source.write_bytes(b"fake")

            with patch(
                "video_kb.agent_workflow.VideoKnowledgePipeline.run",
                side_effect=RuntimeError("download falhou"),
            ):
                out, err, code = _run_cmd(["agent", "run", str(source), "--json"])

        self.assertEqual(code, 1, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["probe"]["kind"], "local_file")
        self.assertFalse(payload["run_id"])
        warnings = " ".join(payload["warnings"])
        self.assertNotIn("download falhou", warnings)
        self.assertIn("Consulte os logs", warnings)

    def test_agent_run_duplicate_without_artifacts_exits_nonzero(self) -> None:
        from video_kb.index import DuplicateRunError

        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "video.mp4"
            source.write_bytes(b"fake")
            existing = {"id": "partial-run", "output_dir": "", "status": "partial"}

            with patch(
                "video_kb.agent_workflow.VideoKnowledgePipeline.run",
                side_effect=DuplicateRunError(existing),
            ):
                out, err, code = _run_cmd(["agent", "run", str(source), "--json"])

        self.assertEqual(code, 1, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["run_id"], "partial-run")
        self.assertFalse(payload["analysis_path"])
        self.assertIn("analysis.json", " ".join(payload["warnings"]))

    def test_agent_run_question_without_answer_json_exits_nonzero(self) -> None:
        from video_kb.agent_workflow import AgentWorkflowResult
        from video_kb.sources import SourceProbe

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            analysis_path = tmp_path / "analysis.json"
            analysis_path.write_text("{}", encoding="utf-8")
            result = AgentWorkflowResult(
                source="https://example.com/video.mp4",
                probe=SourceProbe(
                    source="https://example.com/video.mp4",
                    kind="direct_media_url",
                    adapter="yt_dlp_direct_media",
                    is_url=True,
                    canonical="https://example.com/video.mp4",
                ),
                run_id="run-001",
                workdir=str(tmp_path),
                analysis_path=str(analysis_path),
                markdown_path=str(tmp_path / "knowledge.md"),
                question="resuma",
                warnings=["Erro ao responder pergunta: sem provider"],
            )

            with patch("video_kb.agent_workflow.run_agent_workflow", return_value=result):
                out, err, code = _run_cmd(
                    [
                        "agent",
                        "run",
                        "https://example.com/video.mp4",
                        "--question",
                        "resuma",
                        "--json",
                    ]
                )

        self.assertEqual(code, 1, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload["run_id"], "run-001")
        self.assertEqual(payload["question"], "resuma")
        self.assertIsNone(payload["answer"])

    def test_index_result_runtime_error_becomes_warning(self) -> None:
        from video_kb.agent_workflow import AgentWorkflowOptions, AgentWorkflowResult, _index_result
        from video_kb.sources import SourceProbe

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            analysis_path = tmp_path / "analysis.json"
            analysis_path.write_text("{}", encoding="utf-8")
            result = AgentWorkflowResult(
                source=str(tmp_path / "video.mp4"),
                probe=SourceProbe(
                    source=str(tmp_path / "video.mp4"),
                    kind="local_file",
                    adapter="local_file",
                    is_url=False,
                    canonical=str(tmp_path / "video.mp4"),
                ),
                run_id="run-001",
                analysis_path=str(analysis_path),
            )
            options = AgentWorkflowOptions(
                out_dir=tmp_path / "out",
                provider_name="local",
                index_db=str(tmp_path / "index.db"),
            )
            fake_provider = SimpleNamespace(capabilities=lambda: ["embed"])

            with patch("video_kb.providers.load_provider", return_value=fake_provider):
                with patch("video_kb.embeddings.index_run", side_effect=RuntimeError("embed caiu")):
                    _index_result(result, options)

        self.assertFalse(result.indexed)
        warnings = " ".join(result.warnings)
        self.assertNotIn("embed caiu", warnings)
        self.assertIn("Consulte os logs", warnings)

    def test_answer_question_runtime_error_becomes_warning(self) -> None:
        from video_kb.agent_workflow import (
            AgentWorkflowOptions,
            AgentWorkflowResult,
            _answer_question,
        )
        from video_kb.sources import SourceProbe

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            result = AgentWorkflowResult(
                source="https://example.com/video.mp4",
                probe=SourceProbe(
                    source="https://example.com/video.mp4",
                    kind="direct_media_url",
                    adapter="yt_dlp_direct_media",
                    is_url=True,
                    canonical="https://example.com/video.mp4",
                ),
                run_id="run-001",
            )
            options = AgentWorkflowOptions(
                out_dir=tmp_path / "out",
                provider_name="local",
                index_db=str(tmp_path / "index.db"),
                question="resuma",
            )
            fake_provider = SimpleNamespace(capabilities=lambda: ["embed"])

            with patch("video_kb.providers.load_provider", return_value=fake_provider):
                with patch("video_kb.embeddings.rag.ask", side_effect=RuntimeError("rag caiu")):
                    _answer_question(result, options)

        self.assertEqual(result.question, "resuma")
        self.assertIsNone(result.answer)
        warnings = " ".join(result.warnings)
        self.assertNotIn("rag caiu", warnings)
        self.assertIn("Consulte os logs", warnings)


if __name__ == "__main__":
    unittest.main()
