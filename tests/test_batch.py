from __future__ import annotations

import json
import tempfile
import unittest
from json import JSONDecodeError
from pathlib import Path
from unittest.mock import patch

from video_kb.agent_workflow import AgentWorkflowOptions, AgentWorkflowResult
from video_kb.batch import load_sources_file, run_agent_batch
from video_kb.sources import SourceProbe


class BatchTests(unittest.TestCase):
    def test_load_sources_file_supports_text_csv_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            txt = root / "sources.txt"
            txt.write_text("# ignore\nhttps://a.example/v\nhttps://a.example/v\n", encoding="utf-8")
            csv_path = root / "sources.csv"
            csv_path.write_text("url,title\nhttps://b.example/v,B\n", encoding="utf-8")
            json_path = root / "sources.json"
            json_path.write_text(json.dumps({"sources": [{"url": "https://c.example/v"}]}))

            self.assertEqual(load_sources_file(txt), ["https://a.example/v"])
            self.assertEqual(load_sources_file(csv_path), ["https://b.example/v"])
            self.assertEqual(load_sources_file(json_path), ["https://c.example/v"])

    def test_load_sources_file_csv_without_header_uses_first_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "sources.csv"
            csv_path.write_text(
                "https://a.example/v,A\nhttps://b.example/v,B\n",
                encoding="utf-8",
            )

            self.assertEqual(
                load_sources_file(csv_path),
                ["https://a.example/v", "https://b.example/v"],
            )

    def test_load_sources_file_json_ignores_malformed_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sources.json"
            json_path.write_text(
                json.dumps(["https://a.example/v", {"title": "sem url"}, 42, {"link": ""}]),
                encoding="utf-8",
            )

            self.assertEqual(load_sources_file(json_path), ["https://a.example/v"])

    def test_load_sources_file_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = Path(tmpdir) / "sources.json"
            json_path.write_text("{invalid", encoding="utf-8")

            with self.assertRaises(JSONDecodeError):
                load_sources_file(json_path)

    def test_run_agent_batch_writes_summary_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_file = root / "sources.txt"
            source_file.write_text("https://example.com/video\n", encoding="utf-8")
            out_dir = root / "out"
            options = AgentWorkflowOptions(
                out_dir=out_dir,
                provider_name="local",
                templates=("content", "skill"),
            )
            result = AgentWorkflowResult(
                source="https://example.com/video",
                probe=SourceProbe(
                    source="https://example.com/video",
                    kind="direct_media_url",
                    adapter="yt_dlp_direct_media",
                    is_url=True,
                    canonical="https://example.com/video",
                ),
                provider="local",
                run_id="run-001",
                workdir=str(out_dir / "run-001"),
                analysis_path=str(out_dir / "run-001" / "analysis.json"),
                markdown_path=str(out_dir / "run-001" / "knowledge.md"),
                template_paths={"content": str(out_dir / "run-001" / "content.md")},
            )

            with patch("video_kb.batch.run_agent_workflow", return_value=result):
                summary = run_agent_batch(source_file, options)

            self.assertEqual(summary["ok"], 1)
            self.assertTrue(summary["success"])
            self.assertEqual(summary["ok_count"], 1)
            self.assertEqual(summary["failed_count"], 0)
            self.assertTrue((out_dir / "batch.json").exists())
            self.assertTrue((out_dir / "batch.md").exists())

    def test_run_agent_batch_fail_fast_stops_after_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_file = root / "sources.txt"
            source_file.write_text(
                "https://a.example/video\nhttps://b.example/video\nhttps://c.example/video\n",
                encoding="utf-8",
            )
            out_dir = root / "out"
            options = AgentWorkflowOptions(out_dir=out_dir, provider_name="local")

            with patch(
                "video_kb.batch.run_agent_workflow",
                side_effect=RuntimeError("download falhou"),
            ) as run_mock:
                summary = run_agent_batch(source_file, options, fail_fast=True)

            self.assertEqual(run_mock.call_count, 1)
            self.assertEqual(summary["total"], 1)
            self.assertEqual(summary["ok"], 0)
            self.assertEqual(summary["failed"], 1)
            self.assertFalse(summary["success"])
            self.assertEqual(summary["ok_count"], 0)
            self.assertEqual(summary["failed_count"], 1)
            self.assertEqual(summary["items"][0]["position"], 1)
            self.assertIn("download falhou", summary["items"][0]["error"])


if __name__ == "__main__":
    unittest.main()
