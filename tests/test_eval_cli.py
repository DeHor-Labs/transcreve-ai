from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


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


def _fake_results(providers: list[str] | None = None) -> dict[str, object]:
    providers = providers or ["local"]
    return {
        "generated_at": "2026-06-04T12:00:00Z",
        "dataset": "mock",
        "providers": providers,
        "cases": [],
        "summary": {},
    }


class TestEvalCli(unittest.TestCase):
    def test_eval_local_dispatches_runner_and_report_without_prompt(self) -> None:
        dataset = object()
        results = _fake_results(["local"])
        runner = MagicMock()
        runner.run.return_value = results

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            report_path = tmp_path / "report.md"
            json_path = tmp_path / "results.json"

            with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
                with patch(
                    "video_kb.eval.runner.load_dataset",
                    return_value=dataset,
                ) as load_dataset:
                    with patch(
                        "video_kb.eval.runner.EvalRunner",
                        return_value=runner,
                    ) as runner_cls:
                        with patch(
                            "video_kb.eval.report_writer.write_report",
                            return_value=(report_path, json_path),
                        ) as write_report:
                            out, err, code = _run_cmd(
                                ["eval", "--providers", "local", "--out", str(tmp_path)]
                            )

        self.assertEqual(code, 0, msg=err)
        self.assertIn("OK:", out)
        load_dataset.assert_called_once()
        runner_cls.assert_called_once()
        write_report.assert_called_once()
        _, runner_kwargs = runner_cls.call_args
        self.assertIs(runner_kwargs["dataset"], dataset)
        self.assertEqual(runner_kwargs["providers"], ["local"])
        self.assertEqual(runner_kwargs["out_dir"], tmp_path)
        self.assertEqual(runner_kwargs["ai_mode"], "full")
        self.assertIsNone(runner_kwargs["judge_provider"])
        self.assertIsNotNone(runner_kwargs["on_progress"])

    def test_eval_json_prints_results_to_stdout(self) -> None:
        dataset = object()
        results = _fake_results(["local"])
        runner = MagicMock()
        runner.run.return_value = results

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
                with patch("video_kb.eval.runner.load_dataset", return_value=dataset):
                    with patch("video_kb.eval.runner.EvalRunner", return_value=runner):
                        with patch(
                            "video_kb.eval.report_writer.write_report",
                            return_value=(tmp_path / "report.md", tmp_path / "results.json"),
                        ):
                            out, err, code = _run_cmd(
                                [
                                    "eval",
                                    "--providers",
                                    "local",
                                    "--out",
                                    str(tmp_path),
                                    "--json",
                                ]
                            )

        self.assertEqual(code, 0, msg=err)
        payload = json.loads(out)
        self.assertEqual(payload["providers"], ["local"])
        self.assertIn("Report:", err)

    def test_eval_paid_provider_prompts_and_cancel_stops_before_runner(self) -> None:
        with patch("builtins.input", return_value="n") as prompt:
            with patch("video_kb.eval.runner.EvalRunner") as runner_cls:
                out, err, code = _run_cmd(["eval", "--providers", "openai"])

        self.assertEqual(code, 0, msg=err)
        prompt.assert_called_once()
        runner_cls.assert_not_called()
        self.assertIn("possivel custo", err)
        self.assertIn("openai", err)
        self.assertIn("Cancelado.", out)

    def test_eval_no_cost_warning_skips_prompt_for_paid_provider(self) -> None:
        dataset = object()
        results = _fake_results(["openai"])
        runner = MagicMock()
        runner.run.return_value = results

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("builtins.input", side_effect=AssertionError("unexpected prompt")):
                with patch("video_kb.eval.runner.load_dataset", return_value=dataset):
                    with patch(
                        "video_kb.eval.runner.EvalRunner",
                        return_value=runner,
                    ) as runner_cls:
                        with patch(
                            "video_kb.eval.report_writer.write_report",
                            return_value=(tmp_path / "report.md", tmp_path / "results.json"),
                        ):
                            _, err, code = _run_cmd(
                                [
                                    "eval",
                                    "--providers",
                                    "openai",
                                    "--out",
                                    str(tmp_path),
                                    "--no-cost-warning",
                                ]
                            )

        self.assertEqual(code, 0, msg=err)
        runner_cls.assert_called_once()
        _, runner_kwargs = runner_cls.call_args
        self.assertEqual(runner_kwargs["providers"], ["openai"])

    def test_eval_paid_judge_prompts_even_with_local_provider(self) -> None:
        with patch("builtins.input", return_value="n") as prompt:
            with patch("video_kb.eval.runner.EvalRunner") as runner_cls:
                out, err, code = _run_cmd(["eval", "--providers", "local", "--judge", "gemini"])

        self.assertEqual(code, 0, msg=err)
        prompt.assert_called_once()
        runner_cls.assert_not_called()
        self.assertIn("judge:gemini", err)
        self.assertIn("Cancelado.", out)
