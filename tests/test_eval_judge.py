"""
Testes unitarios: LLM-as-judge com provider mockado.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _make_synthesis(**kwargs):  # type: ignore[return]
    from video_kb.models import KnowledgeSynthesis

    return KnowledgeSynthesis(
        summary=kwargs.get("summary", "Resumo do video de teste."),
        chapters=kwargs.get("chapters", [{"title": "Introducao"}, {"title": "Conclusao"}]),
        entities=kwargs.get("entities", ["Python", "FastAPI"]),
        tools_or_products=kwargs.get("tools_or_products", ["pytest"]),
        claims=kwargs.get("claims", ["Testes sao importantes"]),
        action_items=kwargs.get("action_items", ["Escrever testes"]),
        questions=kwargs.get("questions", ["Por que testar?"]),
        raw=kwargs.get("raw", {"mode": "llm"}),
    )


class TestParseJudgeResponse(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.judge import _parse_judge_response

        self.parse = _parse_judge_response

    def test_valid_json(self) -> None:
        raw = '{"cobertura": 8, "coerencia": 7, "utilidade": 9, "justificativa": "Bom"}'
        result = self.parse(raw)
        assert result is not None
        self.assertEqual(result["cobertura"], 8)
        self.assertEqual(result["justificativa"], "Bom")

    def test_json_with_surrounding_text(self) -> None:
        raw = (
            "Aqui esta minha avaliacao:\n"
            '{"cobertura": 7, "coerencia": 8, "utilidade": 6, "justificativa": "ok"}'
            "\nObrigado."
        )
        result = self.parse(raw)
        assert result is not None
        self.assertEqual(result["cobertura"], 7)

    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(self.parse(""))

    def test_whitespace_only_returns_none(self) -> None:
        self.assertIsNone(self.parse("   \n  "))

    def test_invalid_json_returns_none(self) -> None:
        self.assertIsNone(self.parse("nao e json"))

    def test_broken_json_returns_none(self) -> None:
        self.assertIsNone(self.parse('{"cobertura": 8, "coerencia":'))


class TestToFloat(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.judge import _to_float

        self.to_float = _to_float

    def test_int_value(self) -> None:
        self.assertEqual(self.to_float(8), 8.0)

    def test_float_value(self) -> None:
        self.assertAlmostEqual(self.to_float(7.5), 7.5)

    def test_string_number(self) -> None:
        self.assertAlmostEqual(self.to_float("9"), 9.0)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(self.to_float(None))

    def test_invalid_string_returns_none(self) -> None:
        self.assertIsNone(self.to_float("invalido"))


class TestCalcMedia(unittest.TestCase):
    def setUp(self) -> None:
        from video_kb.eval.judge import _calc_media

        self.calc = _calc_media

    def test_three_values(self) -> None:
        result = self.calc(8.0, 7.0, 9.0)
        self.assertAlmostEqual(result, 8.0)

    def test_all_none_returns_none(self) -> None:
        self.assertIsNone(self.calc(None, None, None))

    def test_partial_none_ignores_none(self) -> None:
        # media de 6 e 8 = 7
        result = self.calc(6.0, None, 8.0)
        self.assertAlmostEqual(result, 7.0)

    def test_single_value(self) -> None:
        result = self.calc(5.0)
        self.assertAlmostEqual(result, 5.0)


class TestRunJudgeMocked(unittest.TestCase):
    """run_judge com provider mockado - nunca toca rede."""

    def _mock_provider(self, capabilities=("synthesize",), summary_response="{}"):
        """Cria mock de provider com capabilities e resposta configuravel."""
        mock_provider = MagicMock()
        mock_provider.capabilities.return_value = list(capabilities)
        mock_synthesis = MagicMock()
        mock_synthesis.summary = summary_response
        mock_provider.synthesize.return_value = mock_synthesis
        return mock_provider

    def test_returns_judge_result_on_success(self) -> None:
        from video_kb.eval.judge import run_judge

        json_response = (
            '{"cobertura": 8, "coerencia": 7, "utilidade": 9, "justificativa": "Cobertura boa."}'
        )
        mock_provider = self._mock_provider(summary_response=json_response)

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "openai")

        self.assertIsNone(result.error)
        self.assertIsNone(result.skipped)
        self.assertAlmostEqual(result.cobertura, 8.0)
        self.assertAlmostEqual(result.coerencia, 7.0)
        self.assertAlmostEqual(result.utilidade, 9.0)
        self.assertIsNotNone(result.nota_geral)
        self.assertEqual(result.justificativa, "Cobertura boa.")

    def test_nota_geral_e_media_correta(self) -> None:
        from video_kb.eval.judge import run_judge

        json_response = '{"cobertura": 6, "coerencia": 8, "utilidade": 7, "justificativa": "ok"}'
        mock_provider = self._mock_provider(summary_response=json_response)

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "openai")

        # media de 6, 8, 7 = 7.0
        self.assertAlmostEqual(result.nota_geral, 7.0)

    def test_provider_sem_synthesize_retorna_skipped(self) -> None:
        from video_kb.eval.judge import run_judge

        # provider sem capability "synthesize" (ex: local)
        mock_provider = self._mock_provider(capabilities=("transcribe",))

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "local")

        self.assertIsNotNone(result.skipped)
        self.assertIsNone(result.error)
        self.assertIsNone(result.cobertura)
        self.assertIsNone(result.nota_geral)

    def test_provider_load_error_retorna_error(self) -> None:
        from video_kb.eval.judge import run_judge

        with patch(
            "video_kb.providers.load_provider",
            side_effect=KeyError("provider_inexistente"),
        ):
            result = run_judge(_make_synthesis(), "provider_inexistente")

        self.assertIsNotNone(result.error)
        self.assertIsNone(result.skipped)
        self.assertIsNone(result.nota_geral)

    def test_parse_failure_retorna_error(self) -> None:
        from video_kb.eval.judge import run_judge

        # provider responde com texto invalido (nao e JSON)
        mock_provider = self._mock_provider(summary_response="Nao sei responder em JSON.")

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "openai")

        self.assertIsNotNone(result.error)
        self.assertIn("parse failed", result.error)
        self.assertIsNone(result.cobertura)

    def test_synthesize_exception_retorna_error(self) -> None:
        from video_kb.eval.judge import run_judge

        mock_provider = MagicMock()
        mock_provider.capabilities.return_value = ["synthesize"]
        mock_provider.synthesize.side_effect = RuntimeError("timeout de rede")

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "openai")

        self.assertIsNotNone(result.error)
        self.assertIn("chamada ao judge falhou", result.error)

    def test_judge_off_by_default_nao_chama_provider(self) -> None:
        """
        O judge e desligado por default no runner.
        Verifica que run_judge nao e chamado quando ai_mode='off' e sem --judge.
        Aqui testamos apenas que o modulo importa sem efeitos colaterais.
        """
        # Importar o modulo nao deve disparar chamadas de rede
        import video_kb.eval.judge as judge_mod

        self.assertTrue(hasattr(judge_mod, "run_judge"))
        self.assertTrue(hasattr(judge_mod, "JudgeResult"))

    def test_json_com_texto_extra_antes_e_depois(self) -> None:
        from video_kb.eval.judge import run_judge

        raw = (
            "Claro! Aqui esta minha avaliacao:\n"
            '{"cobertura": 9, "coerencia": 8, "utilidade": 8, "justificativa": "Excelente."}\n'
            "Espero que ajude."
        )
        mock_provider = self._mock_provider(summary_response=raw)

        with patch("video_kb.providers.load_provider", return_value=mock_provider):
            result = run_judge(_make_synthesis(), "openai")

        self.assertIsNone(result.error)
        self.assertAlmostEqual(result.cobertura, 9.0)
        self.assertEqual(result.justificativa, "Excelente.")


class TestJudgeResultDataclass(unittest.TestCase):
    def test_instancia_com_todos_campos(self) -> None:
        from video_kb.eval.judge import JudgeResult

        jr = JudgeResult(
            cobertura=8.0,
            coerencia=7.0,
            utilidade=9.0,
            nota_geral=8.0,
            justificativa="Boa sintese.",
        )
        self.assertEqual(jr.cobertura, 8.0)
        self.assertIsNone(jr.error)
        self.assertIsNone(jr.skipped)

    def test_instancia_com_error(self) -> None:
        from video_kb.eval.judge import JudgeResult

        jr = JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            error="provider indisponivel",
        )
        self.assertIsNotNone(jr.error)
        self.assertIsNone(jr.nota_geral)

    def test_instancia_com_skipped(self) -> None:
        from video_kb.eval.judge import JudgeResult

        jr = JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            skipped="sem synthesize",
        )
        self.assertIsNotNone(jr.skipped)
        self.assertIsNone(jr.error)


if __name__ == "__main__":
    unittest.main()
