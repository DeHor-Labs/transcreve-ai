"""
Testes unitarios: EvalRunner com mocks do pipeline.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch


def _make_analysis_result(
    duration: float = 60.0,
    transcript: str = "hello world",
    frames_with_note: int = 2,
    warnings: list[str] | None = None,
) -> Any:
    from video_kb.models import (
        AnalysisResult,
        FrameObservation,
        KnowledgeSynthesis,
        SourceMetadata,
        TranscriptSegment,
    )

    frames = [
        FrameObservation(
            timestamp=float(i),
            image_path=f"f{i}.jpg",
            visual_note="note" if i < frames_with_note else "",
            ocr_text="ocr" if i % 2 == 0 else "",
        )
        for i in range(4)
    ]
    return AnalysisResult(
        run_id="run-001",
        created_at="2026-06-03T00:00:00Z",
        source="https://example.com/v",
        workdir="/tmp/test",
        media_path="video.mp4",
        audio_path="audio.mp3",
        metadata=SourceMetadata(source="https://example.com/v", duration=duration),
        transcript_text=transcript,
        transcript_segments=[TranscriptSegment(0.0, 1.0, transcript)],
        frames=frames,
        synthesis=KnowledgeSynthesis(
            summary="Summary text",
            chapters=[{"title": "ch1"}],
            entities=["e1"],
            raw={"mode": "llm"},
        ),
        warnings=warnings or [],
    )


class TestEvalRunnerMocked(unittest.TestCase):
    def _make_runner(
        self,
        tmp_path: Path,
        providers: list[str] | None = None,
        ground_truth: str | None = None,
        dataset_path: Path | str | None = None,
        dataset_metadata_path: str | None = None,
    ) -> Any:
        from video_kb.eval.runner import EvalCase, EvalDataset, EvalRunner

        case = EvalCase(
            id="test_case",
            source="https://example.com/video",
            notes="test",
            ground_truth_transcript=ground_truth,
        )
        dataset = EvalDataset(
            version="1",
            description="test",
            cases=[case],
            path=dataset_metadata_path,
        )
        return EvalRunner(
            dataset=dataset,
            providers=providers or ["local"],
            out_dir=tmp_path,
            ai_mode="off",
            dataset_path=dataset_path,
        )

    def test_run_ok_returns_structure(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = self._make_runner(tmp_path)
            mock_result = _make_analysis_result()

            mock_pipeline = MagicMock()
            mock_pipeline.return_value.run.return_value = mock_result

            MagicMock()

            with patch.object(runner, "_run_one") as mock_run_one:
                from video_kb.eval.runner import CaseResult

                mock_run_one.return_value = CaseResult(
                    status="ok",
                    provider="local",
                    case_id="test_case",
                    elapsed_total_s=5.0,
                    metrics={"duration_seconds": 60.0, "frames_total": 4},
                    cost_estimate={"total_usd": 0.0},
                )
                results = runner.run()

            self.assertIn("cases", results)
            self.assertIn("summary", results)
            self.assertIn("providers", results)
            self.assertEqual(len(results["cases"]), 1)
            self.assertEqual(results["cases"][0]["id"], "test_case")

    def test_run_uses_supplied_dataset_path_in_results_metadata(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset_path = Path("video_kb/eval/datasets/default.json")
            runner = self._make_runner(tmp_path, dataset_path=dataset_path)

            with patch.object(runner, "_run_one") as mock_run_one:
                from video_kb.eval.runner import CaseResult

                mock_run_one.return_value = CaseResult(
                    status="ok",
                    provider="local",
                    case_id="test_case",
                    elapsed_total_s=5.0,
                    metrics={"duration_seconds": 60.0, "frames_total": 4},
                    cost_estimate={"total_usd": 0.0},
                )
                results = runner.run()

            self.assertEqual(results["dataset"], str(dataset_path))

    def test_run_uses_loaded_dataset_path_metadata(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dataset_path = "datasets/custom.json"
            runner = self._make_runner(tmp_path, dataset_metadata_path=dataset_path)

            with patch.object(runner, "_run_one") as mock_run_one:
                from video_kb.eval.runner import CaseResult

                mock_run_one.return_value = CaseResult(
                    status="ok",
                    provider="local",
                    case_id="test_case",
                    elapsed_total_s=5.0,
                    metrics={"duration_seconds": 60.0, "frames_total": 4},
                    cost_estimate={"total_usd": 0.0},
                )
                results = runner.run()

            self.assertEqual(results["dataset"], dataset_path)

    def test_run_keeps_out_dir_dataset_metadata_when_path_not_supplied(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = self._make_runner(tmp_path)

            with patch.object(runner, "_run_one") as mock_run_one:
                from video_kb.eval.runner import CaseResult

                mock_run_one.return_value = CaseResult(
                    status="ok",
                    provider="local",
                    case_id="test_case",
                    elapsed_total_s=5.0,
                    metrics={"duration_seconds": 60.0, "frames_total": 4},
                    cost_estimate={"total_usd": 0.0},
                )
                results = runner.run()

            self.assertEqual(results["dataset"], str(tmp_path))

    def test_run_error_captured(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = self._make_runner(tmp_path)

            with patch.object(runner, "_run_one") as mock_run_one:
                from video_kb.eval.runner import CaseResult

                mock_run_one.return_value = CaseResult(
                    status="error",
                    provider="local",
                    case_id="test_case",
                    error_message="connection timeout",
                )
                results = runner.run()

            case_data = results["cases"][0]
            pr = case_data["providers"]["local"]
            self.assertEqual(pr["status"], "error")
            self.assertEqual(pr["error_message"], "connection timeout")

    def test_wer_computed_when_ground_truth_present(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = self._make_runner(
                tmp_path,
                ground_truth="hello world",
            )

            mock_result = _make_analysis_result(transcript="hello world")

            from video_kb.pipeline import PipelineOptions, VideoKnowledgePipeline

            with patch.object(VideoKnowledgePipeline, "run", return_value=mock_result):
                with patch.object(PipelineOptions, "__init__", return_value=None):
                    case = runner.dataset.cases[0]
                    cr = runner._run_one(
                        case=case,
                        provider_name="local",
                        pipeline_cls=VideoKnowledgePipeline,
                        options_cls=PipelineOptions,
                    )

            # WER identico -> 0.0
            self.assertIsNotNone(cr.wer)
            self.assertAlmostEqual(cr.wer, 0.0, places=3)  # type: ignore[arg-type]

    def test_wer_none_when_no_ground_truth(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = self._make_runner(tmp_path, ground_truth=None)
            mock_result = _make_analysis_result()

            from video_kb.pipeline import PipelineOptions, VideoKnowledgePipeline

            with patch.object(VideoKnowledgePipeline, "run", return_value=mock_result):
                with patch.object(PipelineOptions, "__init__", return_value=None):
                    case = runner.dataset.cases[0]
                    cr = runner._run_one(
                        case=case,
                        provider_name="local",
                        pipeline_cls=VideoKnowledgePipeline,
                        options_cls=PipelineOptions,
                    )

            self.assertIsNone(cr.wer)


class TestLoadDataset(unittest.TestCase):
    def test_load_default_dataset(self) -> None:
        from video_kb.eval.runner import load_dataset

        default_path = (
            Path(__file__).parent.parent / "video_kb" / "eval" / "datasets" / "default.json"
        )
        dataset = load_dataset(default_path)
        self.assertEqual(dataset.version, "1")
        self.assertGreater(len(dataset.cases), 0)
        # Verifica que os campos obrigatorios estao presentes
        for case in dataset.cases:
            self.assertTrue(case.id)
            self.assertTrue(case.source)

    def test_load_custom_dataset(self) -> None:
        import json
        import tempfile

        from video_kb.eval.runner import load_dataset

        data = {
            "version": "1",
            "description": "Test",
            "cases": [
                {
                    "id": "case_1",
                    "source": "https://example.com/v",
                    "notes": "test case",
                    "ground_truth_transcript": "hello world",
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)

        try:
            dataset = load_dataset(tmp_path)
            self.assertEqual(len(dataset.cases), 1)
            self.assertEqual(dataset.cases[0].id, "case_1")
            self.assertEqual(dataset.cases[0].ground_truth_transcript, "hello world")
            self.assertEqual(dataset.path, str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_ground_truth_empty_string_becomes_none(self) -> None:
        import json
        import tempfile

        from video_kb.eval.runner import load_dataset

        data = {
            "version": "1",
            "description": "Test",
            "cases": [
                {
                    "id": "case_1",
                    "source": "https://example.com/v",
                    "ground_truth_transcript": "",
                }
            ],
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)

        try:
            dataset = load_dataset(tmp_path)
            # String vazia deve ser None (nao gera WER)
            self.assertIsNone(dataset.cases[0].ground_truth_transcript)
        finally:
            tmp_path.unlink(missing_ok=True)


class TestBuildSummary(unittest.TestCase):
    def test_summary_ok_counts(self) -> None:
        from video_kb.eval.runner import _build_summary

        cases = [
            {
                "id": "c1",
                "providers": {
                    "openai": {
                        "status": "ok",
                        "elapsed_total_s": 40.0,
                        "cost_estimate": {"total_usd": 0.002},
                        "wer": 0.1,
                    },
                    "local": {
                        "status": "ok",
                        "elapsed_total_s": 10.0,
                        "cost_estimate": {"total_usd": 0.0},
                        "wer": None,
                    },
                },
            },
            {
                "id": "c2",
                "providers": {
                    "openai": {
                        "status": "error",
                    },
                    "local": {
                        "status": "ok",
                        "elapsed_total_s": 12.0,
                        "cost_estimate": {"total_usd": 0.0},
                        "wer": None,
                    },
                },
            },
        ]
        summary = _build_summary(cases, ["openai", "local"])
        self.assertEqual(summary["openai"]["cases_ok"], 1)
        self.assertEqual(summary["openai"]["cases_total"], 2)
        self.assertEqual(summary["local"]["cases_ok"], 2)
        self.assertAlmostEqual(summary["openai"]["avg_total_s"], 40.0)
        self.assertAlmostEqual(summary["local"]["avg_total_s"], 11.0)
        self.assertIsNone(summary["local"]["avg_wer"])


class TestPackageDataConfig(unittest.TestCase):
    def test_eval_datasets_are_included_as_package_data(self) -> None:
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        text = pyproject_path.read_text(encoding="utf-8")

        self.assertIn("[tool.setuptools.package-data]", text)
        self.assertIn('"video_kb.eval" = ["datasets/*.json", "datasets/*.txt"]', text)


if __name__ == "__main__":
    unittest.main()
