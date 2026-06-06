from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_kb.models import SourceMetadata
from video_kb.pipeline import PipelineOptions, VideoKnowledgePipeline


class PipelineTemplateTests(unittest.TestCase):
    def test_content_template_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "out"
            index_db = Path(tmpdir) / "index.db"

            def fake_fetch_media(_source: str, run_dir: Path, **_: object):
                return (
                    run_dir / "source.mp4",
                    SourceMetadata(
                        source="https://example.com/video",
                        title="Template Demo",
                        duration=30,
                    ),
                )

            options = PipelineOptions(
                out_dir=out_dir,
                ai_mode="off",
                provider_name="local",
                run_id="run-template-001",
                index_db=str(index_db),
                templates=("content", "skill"),
            )

            with patch("video_kb.pipeline.fetch_media", side_effect=fake_fetch_media):
                with patch("video_kb.pipeline.extract_audio"):
                    with patch("video_kb.pipeline.extract_frames", return_value=[]):
                        with patch("video_kb.pipeline.probe_duration", return_value=30.0):
                            with patch(
                                "video_kb.pipeline.sha256_url",
                                return_value="hash-template",
                            ):
                                result = VideoKnowledgePipeline(options).run(
                                    "https://example.com/video"
                                )

            run_dir = Path(result.workdir)
            content_md = run_dir / "content.md"
            content_json = run_dir / "content.json"
            content_csv = run_dir / "content.csv"
            skill_md = run_dir / "skill.md"
            skill_json = run_dir / "skill.json"

            self.assertTrue(content_md.exists())
            self.assertTrue(content_json.exists())
            self.assertTrue(content_csv.exists())
            self.assertTrue(skill_md.exists())
            self.assertTrue(skill_json.exists())
            payload = json.loads(content_json.read_text(encoding="utf-8"))

        self.assertEqual(payload["run_id"], "run-template-001")
        self.assertIn("automation_opportunities", payload)


if __name__ == "__main__":
    unittest.main()
