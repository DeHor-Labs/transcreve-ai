"""
Testes unitarios: geracao de markdown e JSON do relatorio.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any


def _make_results(providers: list[str] | None = None) -> dict[str, Any]:
    """Monta estrutura minima de results para os testes."""
    providers = providers or ["openai", "local"]
    return {
        "generated_at": "2026-06-03T01:46:00Z",
        "dataset": "video_kb/eval/datasets/default.json",
        "providers": providers,
        "cases": [
            {
                "id": "test_case",
                "source": "https://example.com/v",
                "notes": "Caso de teste",
                "providers": {
                    "openai": {
                        "status": "ok",
                        "elapsed_total_s": 45.2,
                        "stage_timings_s": {
                            "download": 3.1,
                            "audio": 1.2,
                            "ai": 38.2,
                            "persist": 0.3,
                        },
                        "metrics": {
                            "duration_seconds": 60.0,
                            "transcript_len_words": 120,
                            "frames_total": 12,
                            "frames_with_visual_note": 5,
                            "chapters_count": 3,
                            "entities_count": 8,
                            "warnings_count": 0,
                            "synthesis_mode": "llm",
                        },
                        "cost_estimate": {
                            "whisper_usd": 0.0006,
                            "vision_usd": 0.0006,
                            "synthesis_usd": 0.0009,
                            "total_usd": 0.0021,
                        },
                        "wer": 0.123,
                        "warnings": [],
                        "judge": None,
                    },
                    "local": {
                        "status": "ok",
                        "elapsed_total_s": 12.3,
                        "stage_timings_s": {
                            "download": 3.1,
                            "audio": 0.5,
                            "ai": 0.0,
                            "persist": 0.1,
                        },
                        "metrics": {
                            "duration_seconds": 60.0,
                            "transcript_len_words": 0,
                            "frames_total": 12,
                            "frames_with_visual_note": 0,
                            "chapters_count": 0,
                            "entities_count": 0,
                            "warnings_count": 1,
                            "synthesis_mode": "local",
                        },
                        "cost_estimate": {
                            "whisper_usd": 0.0,
                            "vision_usd": 0.0,
                            "synthesis_usd": 0.0,
                            "total_usd": 0.0,
                        },
                        "wer": None,
                        "warnings": ["Provider local sem visao por IA"],
                        "judge": None,
                    },
                },
            }
        ],
        "summary": {
            "openai": {
                "cases_ok": 1,
                "cases_total": 1,
                "avg_total_s": 45.2,
                "avg_cost_usd": 0.0021,
                "avg_wer": 0.123,
            },
            "local": {
                "cases_ok": 1,
                "cases_total": 1,
                "avg_total_s": 12.3,
                "avg_cost_usd": 0.0,
                "avg_wer": None,
            },
        },
    }


class TestWriteReport(unittest.TestCase):
    def test_creates_both_files(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "report"
            md_path, json_path = write_report(
                results=_make_results(),
                out_dir=out_dir,
                dataset_path="video_kb/eval/datasets/default.json",
            )
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.exists())

    def test_json_is_valid(self) -> None:
        from video_kb.eval.report_writer import write_report

        results = _make_results()
        with tempfile.TemporaryDirectory() as tmp:
            _, json_path = write_report(results=results, out_dir=Path(tmp))
            loaded = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["providers"], results["providers"])
            self.assertEqual(len(loaded["cases"]), 1)

    def test_markdown_contains_case_id(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(
                results=_make_results(),
                out_dir=Path(tmp),
                dataset_path="my_dataset.json",
            )
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("test_case", content)

    def test_markdown_contains_providers(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=_make_results(), out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("openai", content)
            self.assertIn("local", content)

    def test_markdown_contains_summary_section(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=_make_results(), out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("## Resumo", content)

    def test_markdown_wer_percentage(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=_make_results(), out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            # WER 0.123 deve aparecer como "12.3%"
            self.assertIn("12.3%", content)

    def test_markdown_wer_dash_when_none(self) -> None:
        from video_kb.eval.report_writer import write_report

        results = _make_results()
        # Seta WER como None para o provider local
        results["cases"][0]["providers"]["local"]["wer"] = None
        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=results, out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            # Nao deve aparecer percentual para o local (WER null)
            # A metrica wer na tabela deve ter "-" para local
            self.assertIn("-", content)

    def test_markdown_error_case(self) -> None:
        from video_kb.eval.report_writer import write_report

        results = _make_results(["openai"])
        results["cases"][0]["providers"]["openai"]["status"] = "error"
        results["cases"][0]["providers"]["openai"]["error_message"] = "timeout"
        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=results, out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("ERRO", content)

    def test_no_em_dashes_in_markdown(self) -> None:
        """Garante que o relatorio nao usa em-dashes."""
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=_make_results(), out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            self.assertNotIn("—", content)  # em dash
            self.assertNotIn("–", content)  # en dash

    def test_judge_section_shown_when_active(self) -> None:
        from video_kb.eval.report_writer import write_report

        results = _make_results(["openai"])
        results["cases"][0]["providers"]["openai"]["judge"] = {
            "cobertura": 8.0,
            "coerencia": 7.5,
            "utilidade": 9.0,
            "nota_geral": 8.2,
            "justificativa": "Boa cobertura geral.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(
                results=results,
                out_dir=Path(tmp),
                judge_provider="openai",
            )
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("Avaliacao qualitativa", content)
            self.assertIn("8.0", content)

    def test_judge_section_absent_when_not_active(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(
                results=_make_results(),
                out_dir=Path(tmp),
                judge_provider=None,
            )
            content = md_path.read_text(encoding="utf-8")
            self.assertNotIn("Avaliacao qualitativa", content)

    def test_atomic_write_no_tmp_left(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            write_report(results=_make_results(), out_dir=out_dir)
            tmp_files = list(out_dir.glob("*.tmp"))
            self.assertEqual(tmp_files, [])

    def test_footer_cost_disclaimer(self) -> None:
        from video_kb.eval.report_writer import write_report

        with tempfile.TemporaryDirectory() as tmp:
            md_path, _ = write_report(results=_make_results(), out_dir=Path(tmp))
            content = md_path.read_text(encoding="utf-8")
            self.assertIn("estimativas", content)
            self.assertIn("cost_table.py", content)


class TestGetMetricValue(unittest.TestCase):
    def test_total_s(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {"elapsed_total_s": 45.2, "status": "ok"}
        self.assertEqual(_get_metric_value(pr, "total_s"), "45.20")

    def test_cost_total(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {"cost_estimate": {"total_usd": 0.0021}, "status": "ok"}
        self.assertEqual(_get_metric_value(pr, "cost_total_usd"), "0.0021")

    def test_wer_percentage(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {"wer": 0.15, "status": "ok"}
        self.assertEqual(_get_metric_value(pr, "wer"), "15.0%")

    def test_wer_none_dash(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {"wer": None, "status": "ok"}
        self.assertEqual(_get_metric_value(pr, "wer"), "-")

    def test_download_s_from_timings(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {"stage_timings_s": {"download": 3.1}, "status": "ok"}
        self.assertEqual(_get_metric_value(pr, "download_s"), "3.10")

    def test_ai_s_collapses_ai_frame(self) -> None:
        from video_kb.eval.report_writer import _get_metric_value

        pr = {
            "stage_timings_s": {"ai": 10.0, "ai_frame": 5.0},
            "status": "ok",
        }
        self.assertEqual(_get_metric_value(pr, "ai_s"), "15.00")


if __name__ == "__main__":
    unittest.main()
