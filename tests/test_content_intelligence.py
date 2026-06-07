from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_kb.content_intelligence import (
    build_content_intelligence,
    render_content_csv,
    render_content_markdown,
    write_content_artifacts,
)
from video_kb.models import (
    AnalysisResult,
    FrameObservation,
    KnowledgeSynthesis,
    SourceMetadata,
    TranscriptSegment,
)


def _sample_result() -> AnalysisResult:
    return AnalysisResult(
        run_id="run-content-001",
        created_at="2026-06-05T00:00:00Z",
        source="https://www.instagram.com/reel/demo",
        workdir="/tmp/run",
        media_path="source.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(
            source="https://www.instagram.com/reel/demo",
            title="Creator System Demo",
            uploader="Creator",
            duration=52,
            description=(
                "Trilha de Desenvolvimento Web\n"
                "• Portfolio pessoal com IA\n"
                "• Quadro branco colaborativo em tempo real\n"
                "\n"
                "Trilha de IA / Machine Learning\n"
                "• Chatbot com RAG em base pessoal\n"
            ),
        ),
        transcript_text=(
            "Eu transformei meus posts salvos do Instagram em ideias de Reels. "
            "Comenta CONTENT que eu te mando o guia completo."
        ),
        transcript_segments=[
            TranscriptSegment(start=0, end=5, text="Eu transformei meus posts salvos.")
        ],
        frames=[
            FrameObservation(
                timestamp=10,
                image_path="frames/frame.jpg",
                ocr_text=(
                    'Hook: "Transformei 3.200 posts salvos em ideias de Reels" '
                    "Notion TikTok YouTube CTA"
                ),
                visual_note="Tela mostra database de conteudo.",
            )
        ],
        synthesis=KnowledgeSynthesis(
            summary="Sistema transforma referencias salvas em ideias prontas para publicar.",
            tools_or_products=["Notion", "Claude Code"],
            claims=["Conteudos salvos viram hooks e angulos."],
            action_items=["Comentar CONTENT para receber o guia."],
        ),
    )


class ContentIntelligenceTests(unittest.TestCase):
    def test_build_content_intelligence_extracts_creator_package(self) -> None:
        data = build_content_intelligence(_sample_result())

        self.assertEqual(data["kind"], "content_intelligence")
        self.assertIn("Notion", data["evidence"]["tools_or_products"])
        self.assertIn("Instagram", data["evidence"]["detected_platforms"])
        self.assertIn("TikTok", data["evidence"]["detected_platforms"])
        self.assertIn("hook", data["creator_remix"]["export_fields"])
        self.assertTrue(data["creator_remix"]["hook_candidates"])
        self.assertEqual(len(data["evidence"]["caption_items"]), 3)
        self.assertEqual(
            data["evidence"]["caption_items"][0]["section"],
            "Trilha de Desenvolvimento Web",
        )
        self.assertIn(
            "Caption/List Intelligence",
            [item["feature"] for item in data["automation_opportunities"]],
        )
        self.assertTrue(data["automation_opportunities"])

    def test_render_content_markdown_separates_evidence_and_inference(self) -> None:
        markdown = render_content_markdown(_sample_result())

        self.assertIn("## Evidencia do video", markdown)
        self.assertIn("## Creator Remix", markdown)
        self.assertIn("## Itens extraidos da legenda", markdown)
        self.assertIn("Portfolio pessoal com IA", markdown)
        self.assertIn("## Oportunidades de produto", markdown)
        self.assertIn("Backlog, prioridade e oportunidade sao inferencias", markdown)

    def test_render_content_markdown_adapts_to_carousel(self) -> None:
        result = _sample_result()
        result.media_path = "source_01.jpg"
        result.media_paths = ["source_01.jpg", "source_02.jpg"]
        result.audio_path = ""
        result.metadata.extractor = "tiktok"
        result.metadata.media_kind = "carousel"
        result.metadata.duration = 0
        result.frames.append(
            FrameObservation(
                timestamp=1,
                image_path="frames/slide-2.jpg",
                ocr_text="segundo slide",
            )
        )

        data = build_content_intelligence(result)
        markdown = render_content_markdown(result)

        self.assertEqual(data["source_kind"], "carousel")
        self.assertIn("slide_count", data["evidence"])
        self.assertIn("- Tipo: carrossel", markdown)
        self.assertIn("- Slides: 2", markdown)
        self.assertIn("## Evidencia do carrossel", markdown)
        self.assertNotIn("## Evidencia do video", markdown)

    def test_write_content_artifacts_writes_markdown_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = write_content_artifacts(_sample_result(), Path(tmpdir))

            content_md = Path(paths["content"])
            content_json = Path(paths["content_json"])
            content_csv = Path(paths["content_csv"])

            self.assertTrue(content_md.exists())
            self.assertTrue(content_json.exists())
            self.assertTrue(content_csv.exists())
            payload = json.loads(content_json.read_text(encoding="utf-8"))

        self.assertEqual(payload["run_id"], "run-content-001")
        self.assertIn("creator_remix", payload)

    def test_render_content_csv_is_notion_ready(self) -> None:
        data = build_content_intelligence(_sample_result())
        csv_text = render_content_csv(data)

        self.assertIn("source_url,source_timestamp,platform,hook", csv_text)
        self.assertIn("Instagram", csv_text)
        self.assertIn("Not started", csv_text)

    def test_visual_only_frames_preserve_qa_tools(self) -> None:
        result = _sample_result()
        result.transcript_text = ""
        result.transcript_segments = []
        result.synthesis.tools_or_products = []
        result.frames = [
            FrameObservation(
                timestamp=2,
                image_path="frames/qa.jpg",
                ocr_text="Testes de Automacao - Playwright - Cypress - Selenium - Appium - Robot",
                visual_note="Tela lista ferramentas de automacao de QA.",
            ),
            FrameObservation(
                timestamp=8,
                image_path="frames/gestao.jpg",
                ocr_text="Gestao - Azure DevOps - Jira - Trello - Qase - Notion",
            ),
        ]

        data = build_content_intelligence(result)

        self.assertIn("Playwright", data["evidence"]["tools_or_products"])
        self.assertIn("Cypress", data["evidence"]["tools_or_products"])
        self.assertIn("Azure DevOps", data["evidence"]["tools_or_products"])
        self.assertIn("Qase", data["evidence"]["tools_or_products"])


if __name__ == "__main__":
    unittest.main()
