import unittest

from video_kb.models import (
    AnalysisResult,
    FrameObservation,
    KnowledgeSynthesis,
    SourceMetadata,
    TranscriptSegment,
)
from video_kb.providers.base import normalize_items
from video_kb.report import render_markdown
from video_kb.utils import format_timestamp, slugify


class ReportTests(unittest.TestCase):
    def test_render_markdown_includes_multimodal_sections(self):
        result = AnalysisResult(
            run_id="run-1",
            created_at="2026-06-01T00:00:00Z",
            source="https://example.com/video",
            workdir="/tmp/run",
            media_path="source.mp4",
            audio_path="audio.mp3",
            metadata=SourceMetadata(
                source="https://example.com/video",
                title="Demo Video",
                duration=62,
            ),
            transcript_text="fala completa",
            transcript_segments=[TranscriptSegment(start=0, end=4, text="fala perto do frame")],
            frames=[
                FrameObservation(
                    timestamp=2,
                    image_path="frames/frame.jpg",
                    ocr_text="texto na tela",
                    visual_note="pessoa mostrando uma ferramenta",
                )
            ],
            synthesis=KnowledgeSynthesis(
                summary="Resumo executivo",
                entities=["Nikolas"],
                tools_or_products=["Ferramenta X"],
            ),
        )

        markdown = render_markdown(result)

        self.assertIn("# Demo Video", markdown)
        self.assertIn("## Linha do tempo multimodal", markdown)
        self.assertIn("texto na tela", markdown)
        self.assertIn("pessoa mostrando uma ferramenta", markdown)
        self.assertIn("## Transcricao", markdown)

    def test_format_timestamp(self):
        self.assertEqual(format_timestamp(62), "01:02")
        self.assertEqual(format_timestamp(3661), "1:01:01")

    def test_slugify_has_fallback(self):
        self.assertEqual(slugify("!!!", fallback="x"), "x")

    def test_render_markdown_lists_frames_without_notes(self):
        result = AnalysisResult(
            run_id="run-2",
            created_at="2026-06-01T00:00:00Z",
            source="local.mp4",
            workdir="/tmp/run",
            media_path="source.mp4",
            audio_path="audio.mp3",
            metadata=SourceMetadata(source="local.mp4", title="Frame Only"),
            frames=[FrameObservation(timestamp=1, image_path="frames/frame.jpg")],
        )

        markdown = render_markdown(result)

        self.assertIn("![frame](frames/frame.jpg)", markdown)
        self.assertIn("Frame capturado", markdown)

    def test_render_markdown_includes_evidence_profile(self):
        result = AnalysisResult(
            run_id="run-visual",
            created_at="2026-06-01T00:00:00Z",
            source="local.mp4",
            workdir="/tmp/run",
            media_path="source.mp4",
            audio_path="audio.mp3",
            metadata=SourceMetadata(source="local.mp4", title="Visual First"),
            frames=[
                FrameObservation(
                    timestamp=1,
                    image_path="frames/frame.jpg",
                    ocr_text="Playwright",
                    visual_note="Tela lista ferramentas de QA.",
                )
            ],
            evidence_profile={
                "primary_signal": "vision",
                "speech": {
                    "status": "discarded_low_value",
                    "chars": 0,
                    "segments": 0,
                    "reason": "caption_credit_only",
                },
                "visual": {"frames": 1, "ocr_frames": 1, "visual_note_frames": 1},
            },
        )

        markdown = render_markdown(result)

        self.assertIn("## Evidencias usadas", markdown)
        self.assertIn("Sinal principal: visao por IA", markdown)
        self.assertIn("Fala/transcricao: descartada por baixa utilidade", markdown)
        self.assertIn("Visual/OCR: 1 frames, 1 com OCR, 1 com analise visual", markdown)

    def test_render_markdown_includes_tool_provenance(self):
        result = AnalysisResult(
            run_id="run-tools",
            created_at="2026-06-01T00:00:00Z",
            source="local.mp4",
            workdir="/tmp/run",
            media_path="source.mp4",
            audio_path="",
            metadata=SourceMetadata(source="local.mp4", title="QA Tools"),
            frames=[
                FrameObservation(
                    timestamp=2,
                    image_path="frames/qa.jpg",
                    ocr_text="Playwright - Cypress - Selenium",
                    visual_note="Tela lista Playwright e Cypress como ferramentas.",
                )
            ],
            synthesis=KnowledgeSynthesis(summary="Video visual sobre QA."),
        )

        markdown = render_markdown(result)

        self.assertIn("## Ferramentas e produtos", markdown)
        self.assertIn("- Playwright", markdown)
        self.assertIn("## Ferramentas com proveniencia", markdown)
        self.assertIn("Playwright: confianca alta", markdown)
        self.assertIn("OCR em 00:02", markdown)

    def test_render_markdown_adapts_to_carousel(self):
        result = AnalysisResult(
            run_id="run-carousel",
            created_at="2026-06-01T00:00:00Z",
            source="https://www.instagram.com/p/example/",
            workdir="/tmp/run",
            media_path="source_01.jpg",
            media_paths=["source_01.jpg", "source_02.jpg"],
            audio_path="",
            metadata=SourceMetadata(
                source="https://www.tiktok.com/@creator/photo/example",
                title="Carousel Demo",
                extractor="tiktok",
                media_kind="carousel",
                channel="creator",
                upload_date="1779806341",
            ),
            frames=[
                FrameObservation(
                    timestamp=0,
                    image_path="frames/slide-1.jpg",
                    ocr_text="hook do slide",
                    visual_note="capa do carrossel",
                ),
                FrameObservation(
                    timestamp=1,
                    image_path="frames/slide-2.jpg",
                    ocr_text="passo dois",
                ),
            ],
            synthesis=KnowledgeSynthesis(
                summary="Resumo do carrossel",
                chapters=[{"start": 1, "title": "Capa", "notes": "Promessa principal"}],
            ),
        )

        markdown = render_markdown(result)

        self.assertIn("- Tipo: carrossel", markdown)
        self.assertIn("- Slides: 2", markdown)
        self.assertIn("## Slides / estrutura", markdown)
        self.assertIn("Slide 1 - Capa: Promessa principal", markdown)
        self.assertIn("## Slides do carrossel", markdown)
        self.assertIn("### Slide 1/2", markdown)
        self.assertIn("![slide 1](frames/slide-1.jpg)", markdown)
        self.assertIn("## Textos detectados nos slides", markdown)
        self.assertIn("[Slide 2] passo dois", markdown)
        self.assertIn("- Midias do carrossel: `source_01.jpg`, `source_02.jpg`", markdown)
        self.assertNotIn("## Linha do tempo multimodal", markdown)
        self.assertNotIn("- Video:", markdown)

    def test_normalize_items_formats_structured_ai_lists(self):
        items = normalize_items(
            [
                {"name": "Flow Labs", "type": "tool"},
                {"title": "Open question", "description": "Needs review"},
                "plain text",
            ]
        )

        self.assertEqual(
            items,
            ["Flow Labs (tool)", "Open question: Needs review", "plain text"],
        )


if __name__ == "__main__":
    unittest.main()
