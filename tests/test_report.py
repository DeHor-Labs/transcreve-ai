import unittest

from video_kb.models import (
    AnalysisResult,
    FrameObservation,
    KnowledgeSynthesis,
    SourceMetadata,
    TranscriptSegment,
)
from video_kb.report import render_markdown
from video_kb.utils import format_timestamp, slugify
from video_kb.ai import _normalize_items


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
            transcript_segments=[
                TranscriptSegment(start=0, end=4, text="fala perto do frame")
            ],
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

    def test_normalize_items_formats_structured_ai_lists(self):
        items = _normalize_items(
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
