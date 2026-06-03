"""
Testes das rotas /api/search e /api/ask via TestClient.

O nucleo RAG e completamente mockado - nenhum acesso a rede ou modelo.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_provider(dim: int = 4) -> MagicMock:
    provider = MagicMock()
    provider.capabilities.return_value = {"embed", "transcribe", "synthesize"}

    def _fake_embed(texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            h = abs(hash(text)) % 1000
            vec = [float(h % (dim * (i + 1)) + 1) for i in range(dim)]
            norm = sum(x * x for x in vec) ** 0.5
            result.append([x / norm for x in vec])
        return result

    provider.embed.side_effect = _fake_embed
    return provider


def _make_test_app(tmp_dir: str):  # type: ignore[no-untyped-def]
    from video_kb.web.app import create_app

    index_db = str(Path(tmp_dir) / "test.db")
    return create_app(out_dir=Path(tmp_dir), index_db=index_db)


def _make_search_hit(**kwargs) -> object:  # type: ignore[no-untyped-def]
    from video_kb.embeddings.store import SearchHit

    defaults = dict(
        run_id="run-001",
        title="Video Teste",
        source_url="https://example.com/video",
        chunk_type="summary",
        excerpt="Trecho de teste.",
        score=0.9,
        chapter_start=None,
    )
    defaults.update(kwargs)
    return SearchHit(**defaults)


class _RagWebTestCase(unittest.TestCase):
    """Base com TestClient + lifespan ativo e provider mockado."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        self._tmp = tempfile.mkdtemp()
        self._app = _make_test_app(self._tmp)
        self._provider = _make_mock_provider()
        self._tc = TestClient(self._app)
        self._tc.__enter__()
        self.client = self._tc

    def tearDown(self) -> None:
        import shutil

        try:
            self._tc.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. POST /api/search
# ---------------------------------------------------------------------------


class TestSearchEndpoint(_RagWebTestCase):
    def test_search_query_vazia_retorna_422(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            resp = self.client.post("/api/search", json={"query": ""})
        self.assertEqual(resp.status_code, 422)

    def test_search_query_vazia_retorna_json_com_erro(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            resp = self.client.post("/api/search", json={"query": ""})
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("message", data)

    def test_search_payload_invalido_retorna_422(self) -> None:
        resp = self.client.post(
            "/api/search",
            content=b"nao e json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_search_sem_campo_query_retorna_422(self) -> None:
        resp = self.client.post("/api/search", json={"top_k": 3})
        self.assertEqual(resp.status_code, 422)

    def test_search_com_rag_mockado_retorna_200(self) -> None:
        hits = [_make_search_hit()]
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=hits),
        ):
            resp = self.client.post("/api/search", json={"query": "Python"})
        self.assertEqual(resp.status_code, 200)

    def test_search_com_rag_mockado_retorna_resultados(self) -> None:
        hits = [_make_search_hit(run_id="run-abc", score=0.87)]
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=hits),
        ):
            resp = self.client.post("/api/search", json={"query": "Python"})
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["run_id"], "run-abc")
        self.assertAlmostEqual(data["results"][0]["score"], 0.87, places=2)

    def test_search_sem_resultados_retorna_lista_vazia(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=[]),
        ):
            resp = self.client.post("/api/search", json={"query": "nada"})
        data = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["results"], [])

    def test_search_preserva_query_na_resposta(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=[]),
        ):
            resp = self.client.post("/api/search", json={"query": "minha pergunta"})
        self.assertEqual(resp.json()["query"], "minha pergunta")

    def test_search_provider_sem_embed_retorna_503(self) -> None:
        provider_no_embed = MagicMock()
        provider_no_embed.capabilities.return_value = {"transcribe"}
        with (
            patch("video_kb.providers.load_provider", return_value=provider_no_embed),
            patch("video_kb.providers.resolve_provider_name", return_value="anthropic"),
        ):
            resp = self.client.post("/api/search", json={"query": "Python"})
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertIn("error", data)

    def test_search_provider_erro_retorna_503(self) -> None:
        with (
            patch(
                "video_kb.providers.load_provider",
                side_effect=RuntimeError("chave ausente"),
            ),
            patch("video_kb.providers.resolve_provider_name", return_value="openai"),
        ):
            resp = self.client.post("/api/search", json={"query": "Python"})
        self.assertEqual(resp.status_code, 503)

    def test_search_erro_interno_retorna_500(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", side_effect=RuntimeError("falha interna")),
        ):
            resp = self.client.post("/api/search", json={"query": "Python"})
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertIn("error", data)

    def test_search_resposta_tem_campos_obrigatorios(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=[]),
        ):
            resp = self.client.post("/api/search", json={"query": "x"})
        data = resp.json()
        for campo in ("query", "total", "results"):
            self.assertIn(campo, data)

    def test_search_result_tem_campos_obrigatorios(self) -> None:
        hits = [_make_search_hit()]
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.search", return_value=hits),
        ):
            resp = self.client.post("/api/search", json={"query": "x"})
        result = resp.json()["results"][0]
        for campo in ("run_id", "title", "source_url", "chunk_type", "excerpt", "score"):
            self.assertIn(campo, result)


# ---------------------------------------------------------------------------
# 2. POST /api/ask
# ---------------------------------------------------------------------------


class TestAskEndpoint(_RagWebTestCase):
    def test_ask_question_vazia_retorna_422(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            resp = self.client.post("/api/ask", json={"question": ""})
        self.assertEqual(resp.status_code, 422)

    def test_ask_question_vazia_retorna_json_com_erro(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            resp = self.client.post("/api/ask", json={"question": ""})
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("message", data)

    def test_ask_payload_invalido_retorna_422(self) -> None:
        resp = self.client.post(
            "/api/ask",
            content=b"nao e json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_ask_sem_campo_question_retorna_422(self) -> None:
        resp = self.client.post("/api/ask", json={"top_k": 3})
        self.assertEqual(resp.status_code, 422)

    def test_ask_com_rag_mockado_retorna_200(self) -> None:
        from video_kb.embeddings.rag import AskResult

        fake_result = AskResult(
            question="O que e Python?",
            answer="Python e uma linguagem de programacao.",
            sources=[],
        )
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            resp = self.client.post("/api/ask", json={"question": "O que e Python?"})
        self.assertEqual(resp.status_code, 200)

    def test_ask_retorna_question_e_answer(self) -> None:
        from video_kb.embeddings.rag import AskResult

        fake_result = AskResult(
            question="O que e RAG?",
            answer="RAG usa recuperacao para augmentar geracao.",
            sources=[],
        )
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            resp = self.client.post("/api/ask", json={"question": "O que e RAG?"})
        data = resp.json()
        self.assertEqual(data["question"], "O que e RAG?")
        self.assertIn("RAG", data["answer"])

    def test_ask_retorna_sources(self) -> None:
        from video_kb.embeddings.rag import AskResult

        hit = _make_search_hit(run_id="run-src", score=0.92)
        fake_result = AskResult(
            question="Pergunta?",
            answer="Resposta.",
            sources=[hit],  # type: ignore[list-item]
        )
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            resp = self.client.post("/api/ask", json={"question": "Pergunta?"})
        data = resp.json()
        self.assertIsInstance(data["sources"], list)
        self.assertEqual(len(data["sources"]), 1)
        self.assertEqual(data["sources"][0]["run_id"], "run-src")

    def test_ask_provider_sem_embed_retorna_503(self) -> None:
        provider_no_embed = MagicMock()
        provider_no_embed.capabilities.return_value = {"transcribe"}
        with (
            patch("video_kb.providers.load_provider", return_value=provider_no_embed),
            patch("video_kb.providers.resolve_provider_name", return_value="anthropic"),
        ):
            resp = self.client.post("/api/ask", json={"question": "Pergunta?"})
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertIn("error", data)

    def test_ask_provider_erro_retorna_503(self) -> None:
        with (
            patch(
                "video_kb.providers.load_provider",
                side_effect=RuntimeError("chave ausente"),
            ),
            patch("video_kb.providers.resolve_provider_name", return_value="openai"),
        ):
            resp = self.client.post("/api/ask", json={"question": "Pergunta?"})
        self.assertEqual(resp.status_code, 503)

    def test_ask_erro_interno_retorna_500(self) -> None:
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", side_effect=RuntimeError("falha")),
        ):
            resp = self.client.post("/api/ask", json={"question": "Pergunta?"})
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertIn("error", data)

    def test_ask_resposta_tem_campos_obrigatorios(self) -> None:
        from video_kb.embeddings.rag import AskResult

        fake_result = AskResult(question="Q?", answer="A.", sources=[])
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            resp = self.client.post("/api/ask", json={"question": "Q?"})
        data = resp.json()
        for campo in ("question", "answer", "sources"):
            self.assertIn(campo, data)

    def test_ask_sources_tem_campos_obrigatorios(self) -> None:
        from video_kb.embeddings.rag import AskResult

        hit = _make_search_hit()
        fake_result = AskResult(question="Q?", answer="A.", sources=[hit])  # type: ignore[list-item]
        with (
            patch("video_kb.providers.load_provider", return_value=self._provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            resp = self.client.post("/api/ask", json={"question": "Q?"})
        src = resp.json()["sources"][0]
        for campo in ("run_id", "title", "source_url", "chunk_type", "excerpt", "score"):
            self.assertIn(campo, src)


if __name__ == "__main__":
    unittest.main()
