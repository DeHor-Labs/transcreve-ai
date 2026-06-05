"""
Testes unitarios: WER, StageTimer, estimate_cost, extract_metrics.
"""

from __future__ import annotations

import time
import unittest
from typing import Any


class TestWerSimple(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.metrics import wer_simple

        self.wer = wer_simple

    def test_identical_transcripts(self) -> None:
        self.assertAlmostEqual(self.wer("hello world", "hello world"), 0.0)

    def test_one_substitution(self) -> None:
        # ref=2 palavras, 1 substituicao -> 0.5
        result = self.wer("hello world", "hello there")
        self.assertAlmostEqual(result, 0.5)

    def test_empty_hypothesis(self) -> None:
        # 2 delecoes / 2 ref -> 1.0
        result = self.wer("hello world", "")
        self.assertAlmostEqual(result, 1.0)

    def test_empty_reference(self) -> None:
        # referencia vazia -> 0.0 (sem base para calcular)
        result = self.wer("", "hello world")
        self.assertAlmostEqual(result, 0.0)

    def test_both_empty(self) -> None:
        result = self.wer("", "")
        self.assertAlmostEqual(result, 0.0)

    def test_extra_words_in_hypothesis(self) -> None:
        # ref=2, hyp=4 -> 2 insercoes / 2 ref = 1.0
        result = self.wer("hello world", "hello beautiful world today")
        self.assertAlmostEqual(result, 1.0)

    def test_case_insensitive(self) -> None:
        result = self.wer("Hello World", "hello world")
        self.assertAlmostEqual(result, 0.0)

    def test_punctuation_stripped(self) -> None:
        result = self.wer("hello, world!", "hello world")
        self.assertAlmostEqual(result, 0.0)

    def test_wer_above_one_possible(self) -> None:
        # Hipotese completamente diferente e mais longa -> WER > 1 e possivel
        result = self.wer("cat", "dog fish bird whale elephant")
        self.assertGreater(result, 1.0)


class TestStageTimer(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.stage_timer import StageTimer

        self.StageTimer = StageTimer

    def test_records_single_stage(self) -> None:
        timer = self.StageTimer()
        timer.callback("download", "Baixando...")
        time.sleep(0.01)
        timer.close()
        result = timer.finalize()
        self.assertIn("download", result)
        self.assertGreater(result["download"], 0.0)

    def test_records_multiple_stages(self) -> None:
        timer = self.StageTimer()
        timer.callback("download", "x")
        time.sleep(0.005)
        timer.callback("audio", "y")
        time.sleep(0.005)
        timer.callback("frames", "z")
        time.sleep(0.005)
        timer.close()
        result = timer.finalize()
        self.assertIn("download", result)
        self.assertIn("audio", result)
        self.assertIn("frames", result)

    def test_finalize_idempotent(self) -> None:
        timer = self.StageTimer()
        timer.callback("download", "x")
        time.sleep(0.005)
        timer.close()
        r1 = timer.finalize()
        r2 = timer.finalize()
        self.assertEqual(r1, r2)

    def test_no_callbacks_returns_empty(self) -> None:
        timer = self.StageTimer()
        result = timer.finalize()
        self.assertEqual(result, {})

    def test_get_default(self) -> None:
        timer = self.StageTimer()
        self.assertEqual(timer.get("nonexistent", 99.0), 99.0)


class TestEstimateCost(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.cost_table import estimate_cost

        self.estimate = estimate_cost

    def test_local_is_zero(self) -> None:
        cost = self.estimate(
            provider_name="local",
            duration_seconds=120.0,
            frames_with_visual_note=10,
            transcript_len_chars=5000,
        )
        self.assertEqual(cost["total_usd"], 0.0)
        self.assertEqual(cost["whisper_usd"], 0.0)
        self.assertEqual(cost["vision_usd"], 0.0)
        self.assertEqual(cost["synthesis_usd"], 0.0)

    def test_openai_nonzero(self) -> None:
        cost = self.estimate(
            provider_name="openai",
            duration_seconds=60.0,
            frames_with_visual_note=5,
            transcript_len_chars=1000,
        )
        self.assertGreater(cost["total_usd"], 0.0)
        self.assertGreater(cost["whisper_usd"], 0.0)

    def test_zero_duration_zero_whisper(self) -> None:
        cost = self.estimate(
            provider_name="openai",
            duration_seconds=0.0,
            frames_with_visual_note=0,
            transcript_len_chars=0,
        )
        self.assertEqual(cost["whisper_usd"], 0.0)

    def test_custom_price_table(self) -> None:
        custom = {
            "test_provider": {
                "whisper_per_min": 1.0,
                "vision_in_per_1k": 0.0,
                "synth_in_per_1k": 0.0,
                "synth_out_per_1k": 0.0,
            }
        }
        cost = self.estimate(
            provider_name="test_provider",
            duration_seconds=60.0,
            frames_with_visual_note=0,
            transcript_len_chars=0,
            price_table=custom,
        )
        self.assertAlmostEqual(cost["whisper_usd"], 1.0, places=5)

    def test_returns_all_keys(self) -> None:
        cost = self.estimate("openai", 30.0, 2, 500)
        self.assertIn("whisper_usd", cost)
        self.assertIn("vision_usd", cost)
        self.assertIn("synthesis_usd", cost)
        self.assertIn("total_usd", cost)

    def test_estimate_cost_permite_assumptions_customizadas(self) -> None:
        custom = {
            "test_provider": {
                "whisper_per_min": 0.0,
                "vision_in_per_1k": 1.0,
                "synth_in_per_1k": 1.0,
                "synth_out_per_1k": 1.0,
            }
        }

        cost = self.estimate(
            provider_name="test_provider",
            duration_seconds=0.0,
            frames_with_visual_note=1,
            transcript_len_chars=0,
            price_table=custom,
            vision_tokens_per_frame=1000,
            synth_overhead_tokens=1000,
            synth_output_tokens=1000,
        )

        self.assertEqual(cost["vision_usd"], 1.0)
        self.assertEqual(cost["synthesis_usd"], 2.0)


class TestExtractMetrics(unittest.TestCase):
    def _make_result(self, **kwargs: Any) -> Any:
        """Cria um AnalysisResult mock com valores defaults."""
        from video_kb.models import (
            AnalysisResult,
            FrameObservation,
            KnowledgeSynthesis,
            SourceMetadata,
            TranscriptSegment,
        )

        metadata = SourceMetadata(
            source="https://example.com/video",
            title="Test Video",
            duration=kwargs.get("duration", 120.0),
        )
        frames = kwargs.get(
            "frames",
            [
                FrameObservation(
                    timestamp=1.0, image_path="f1.jpg", ocr_text="text", visual_note="note"
                ),
                FrameObservation(timestamp=2.0, image_path="f2.jpg", ocr_text="", visual_note=""),
            ],
        )
        synthesis = kwargs.get(
            "synthesis",
            KnowledgeSynthesis(
                summary="Test summary",
                chapters=[{"title": "ch1"}],
                entities=["e1", "e2"],
                tools_or_products=["tool1"],
                claims=["claim1"],
                action_items=["action1"],
                questions=["q1"],
                raw={"mode": "local"},
            ),
        )
        return AnalysisResult(
            run_id="test-run",
            created_at="2026-06-03T00:00:00Z",
            source="https://example.com/video",
            workdir="/tmp/test",
            media_path="video.mp4",
            audio_path="audio.mp3",
            metadata=metadata,
            transcript_text=kwargs.get("transcript_text", "hello world test"),
            transcript_segments=[TranscriptSegment(start=0.0, end=1.0, text="hello world test")],
            frames=frames,
            synthesis=synthesis,
            warnings=kwargs.get("warnings", ["w1"]),
        )

    def test_basic_metrics(self) -> None:
        from video_kb.eval.metrics import extract_metrics

        result = self._make_result()
        m = extract_metrics(result)

        self.assertEqual(m["duration_seconds"], 120.0)
        self.assertEqual(m["transcript_len_chars"], len("hello world test"))
        self.assertEqual(m["transcript_len_words"], 3)
        self.assertEqual(m["transcript_segments_count"], 1)
        self.assertEqual(m["frames_total"], 2)
        self.assertEqual(m["frames_with_visual_note"], 1)
        self.assertEqual(m["frames_with_ocr"], 1)
        self.assertEqual(m["chapters_count"], 1)
        self.assertEqual(m["entities_count"], 2)
        self.assertEqual(m["tools_count"], 1)
        self.assertEqual(m["claims_count"], 1)
        self.assertEqual(m["action_items_count"], 1)
        self.assertEqual(m["questions_count"], 1)
        self.assertEqual(m["warnings_count"], 1)
        self.assertEqual(m["synthesis_mode"], "local")

    def test_llm_synthesis_mode(self) -> None:
        from video_kb.eval.metrics import extract_metrics
        from video_kb.models import KnowledgeSynthesis

        synth = KnowledgeSynthesis(summary="s", raw={"mode": "llm"})
        result = self._make_result(synthesis=synth)
        m = extract_metrics(result)
        self.assertEqual(m["synthesis_mode"], "llm")

    def test_raw_nao_dict_nao_quebra_synthesis_mode(self) -> None:
        from video_kb.eval.metrics import extract_metrics
        from video_kb.models import KnowledgeSynthesis

        synth = KnowledgeSynthesis(summary="s", raw="modo local textual")  # type: ignore[arg-type]
        result = self._make_result(synthesis=synth)
        m = extract_metrics(result)
        self.assertEqual(m["synthesis_mode"], "llm")

    def test_empty_transcript(self) -> None:
        from video_kb.eval.metrics import extract_metrics

        result = self._make_result(transcript_text="")
        m = extract_metrics(result)
        self.assertEqual(m["transcript_len_chars"], 0)
        self.assertEqual(m["transcript_len_words"], 0)


if __name__ == "__main__":
    unittest.main()
