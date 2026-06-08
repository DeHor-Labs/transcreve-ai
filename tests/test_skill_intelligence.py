from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_kb.models import AnalysisResult, FrameObservation, KnowledgeSynthesis, SourceMetadata
from video_kb.skill_intelligence import (
    build_skill_intelligence,
    render_skill_markdown,
    write_skill_artifacts,
)


def _sample_result() -> AnalysisResult:
    return AnalysisResult(
        run_id="run-skill-001",
        created_at="2026-06-05T00:00:00Z",
        source="https://example.com/reel",
        workdir="/tmp/run",
        media_path="source.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(source="https://example.com/reel", title="Claude Skills Demo"),
        transcript_text="Mostro como criar Claude Skills e salvar o resultado no Notion.",
        synthesis=KnowledgeSynthesis(
            summary="Video ensina a transformar referencias em Claude Skills.",
            tools_or_products=["Claude Code", "Notion"],
            claims=["Skills podem reutilizar referencias."],
            action_items=["Criar sua propria skill."],
        ),
    )


class SkillIntelligenceTests(unittest.TestCase):
    def test_build_skill_intelligence_extracts_contract(self) -> None:
        data = build_skill_intelligence(_sample_result())

        self.assertEqual(data["kind"], "skill_intelligence")
        self.assertIn("skill", data)
        self.assertTrue(data["skill"]["triggers"])
        self.assertTrue(data["skill"]["workflow"])
        self.assertTrue(data["skill"]["prompt_templates"])

    def test_render_skill_markdown_has_frontmatter_and_workflow(self) -> None:
        markdown = render_skill_markdown(_sample_result())

        self.assertIn("---", markdown)
        self.assertIn("## Quando Usar", markdown)
        self.assertIn("## Workflow", markdown)
        self.assertIn("## Prompts Base", markdown)

    def test_write_skill_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_skill_artifacts(_sample_result(), Path(tmpdir))
            skill_md = Path(paths["skill"])
            skill_json = Path(paths["skill_json"])
            self.assertTrue(skill_md.exists())
            self.assertTrue(skill_json.exists())
            payload = json.loads(skill_json.read_text(encoding="utf-8"))

        self.assertEqual(payload["run_id"], "run-skill-001")

    def test_visual_only_frames_preserve_tools_in_skill_draft(self) -> None:
        result = _sample_result()
        result.transcript_text = ""
        result.synthesis.tools_or_products = []
        result.frames = [
            FrameObservation(
                timestamp=2,
                image_path="frames/qa.jpg",
                ocr_text="Testes de Automacao - Playwright - Cypress - Selenium",
                visual_note="Tela lista ferramentas de automacao.",
            )
        ]

        data = build_skill_intelligence(result)

        self.assertIn("Playwright", data["evidence"]["tools_or_products"])
        self.assertIn("Cypress", data["evidence"]["tools_or_products"])
        tool_evidence = data["evidence"]["tool_evidence"]
        self.assertTrue(tool_evidence)
        self.assertGreater(len(tool_evidence), 0)
        self.assertEqual(tool_evidence[0]["confidence"], "high")
        self.assertTrue(any("Playwright" in trigger for trigger in data["skill"]["triggers"]))


if __name__ == "__main__":
    unittest.main()
