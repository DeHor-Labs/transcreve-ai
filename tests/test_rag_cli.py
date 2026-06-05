"""
Testes dos subcomandos CLI 'index' e 'ask' do transcreve-ai.

Todos os testes sao unitarios. O nucleo RAG e completamente mockado -
nenhum acesso a rede, modelo ou filesystem real alem de SQLite em memoria.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis_json(
    summary: str = "Resumo de teste.",
    transcript: str = "Transcricao de teste.",
) -> dict:
    return {
        "metadata": {"title": "Video Teste", "source": "https://example.com/video"},
        "synthesis": {"summary": summary, "chapters": [], "entities": []},
        "transcript_text": transcript,
    }


def _make_mock_provider(dim: int = 4) -> MagicMock:
    """Provider mockado com embed deterministico."""
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


def _run_cmd(argv: list[str]) -> tuple[str, str, int]:
    """
    Roda o main() do CLI com argv dado.
    argv deve incluir a flag global --index-db ANTES do subcomando quando necessario.
    Retorna (stdout, stderr, exit_code).
    """
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


# ---------------------------------------------------------------------------
# 1. Subcomando 'index'
# ---------------------------------------------------------------------------


class TestCliIndex(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._tmp_path = Path(self._tmp)
        self._db = str(self._tmp_path / "test.db")

    def _populate_index(self, run_id: str = "run-001") -> Path:
        """Registra um run no RunIndex e cria analysis.json correspondente."""
        from video_kb.index import RunIndex

        run_dir = self._tmp_path / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = run_dir / "analysis.json"
        analysis_path.write_text(json.dumps(_make_analysis_json()), encoding="utf-8")

        with RunIndex(Path(self._db)) as idx:
            idx.register(
                run_id=run_id,
                source="https://example.com/video",
                output_dir=str(run_dir),
                analysis_path=str(analysis_path),
                markdown_path=str(run_dir / "knowledge.md"),
                source_hash="abc123",
            )
        return analysis_path

    def test_index_sem_run_id_e_sem_all_imprime_erro(self) -> None:
        # --index-db e flag global: vai ANTES do subcomando
        _out, err, code = _run_cmd(["--index-db", self._db, "index"])
        self.assertNotEqual(code, 0)
        combined = (err + _out).lower()
        self.assertTrue(
            "run_id" in combined or "informe" in combined or "error" in combined,
            f"Esperava mensagem de erro, obtido: {err!r} / {_out!r}",
        )

    def test_index_run_inexistente_imprime_aviso(self) -> None:
        provider = _make_mock_provider()
        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            out, _err, _code = _run_cmd(["--index-db", self._db, "index", "nao-existe-xyz"])
        self.assertIn("nao encontrado", out.lower() + _err.lower())

    def test_index_provider_sem_embed_imprime_erro(self) -> None:
        provider = MagicMock()
        provider.capabilities.return_value = {"transcribe"}

        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="anthropic"),
        ):
            _out, err, code = _run_cmd(["--index-db", self._db, "index", "--all"])
        self.assertNotEqual(code, 0)
        self.assertTrue(
            "embed" in err.lower() or "suporta" in err.lower() or "capability" in err.lower(),
            f"Esperava mensagem de erro sobre embed, mas stderr foi: {err!r}",
        )

    def test_index_all_sem_runs_imprime_mensagem_vazia(self) -> None:
        provider = _make_mock_provider()
        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            out, _err, code = _run_cmd(["--index-db", self._db, "index", "--all"])
        self.assertEqual(code, 0)
        self.assertIn("nenhum run", out.lower())

    def test_index_run_especifico_com_analysis_indexa(self) -> None:
        self._populate_index("run-001")
        provider = _make_mock_provider()

        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.cli._get_embed_model", return_value="mock-model"),
        ):
            out, _err, code = _run_cmd(["--index-db", self._db, "index", "run-001"])

        self.assertEqual(code, 0)
        self.assertIn("chunk", out.lower())

    def test_index_ja_indexado_sem_force_informa_skip(self) -> None:
        self._populate_index("run-dup")
        provider = _make_mock_provider()

        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.cli._get_embed_model", return_value="mock-model"),
        ):
            # Primeira indexacao
            _run_cmd(["--index-db", self._db, "index", "run-dup"])
            # Segunda sem --force
            out, _err, code = _run_cmd(["--index-db", self._db, "index", "run-dup"])

        self.assertEqual(code, 0)
        self.assertIn("ja indexado", out.lower())


# ---------------------------------------------------------------------------
# 2. Subcomando 'ask'
# ---------------------------------------------------------------------------


class TestCliAsk(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._db = str(Path(self._tmp) / "test.db")

    def test_ask_indice_vazio_imprime_mensagem_clara(self) -> None:
        provider = _make_mock_provider()
        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            out, _err, code = _run_cmd(["--index-db", self._db, "ask", "O que e Python?"])
        self.assertEqual(code, 0)
        self.assertIn("indexado", out.lower())

    def test_ask_provider_sem_embed_imprime_erro(self) -> None:
        provider = MagicMock()
        provider.capabilities.return_value = {"transcribe"}
        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="anthropic"),
        ):
            _out, err, code = _run_cmd(["--index-db", self._db, "ask", "Pergunta?"])
        self.assertNotEqual(code, 0)
        self.assertTrue(
            "embed" in err.lower() or "suporta" in err.lower(),
            f"stderr foi: {err!r}",
        )

    def test_ask_search_only_mostra_trechos_sem_resposta_llm(self) -> None:
        """--search-only nao deve chamar synth/complete no provider."""
        from video_kb.embeddings.chunker import EmbeddingChunk
        from video_kb.embeddings.store import EmbeddingStore

        provider = _make_mock_provider(dim=4)
        db_path = Path(self._db)

        # Insere manualmente 1 chunk no banco para search retornar algo
        chunk = EmbeddingChunk(
            chunk_id="run-s:0000",
            run_id="run-s",
            chunk_index=0,
            chunk_type="summary",
            chunk_text="Python e uma linguagem de programacao.",
            excerpt="Python e uma linguagem de programacao.",
            source_title="Video Python",
            source_url="https://example.com/python",
        )
        vec = provider.embed([chunk.chunk_text])[0]
        with EmbeddingStore(db_path) as store:
            store.upsert_chunks(
                run_id="run-s",
                chunks=[chunk],
                vectors=[vec],
                provider="mock",
                model="mock-model",
            )

        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
        ):
            out, _err, code = _run_cmd(["--index-db", self._db, "ask", "Python", "--search-only"])

        self.assertEqual(code, 0)
        # complete nao deve ter sido chamado
        provider.complete.assert_not_called()
        self.assertIn("python", out.lower())

    def test_ask_com_chunks_indexados_exibe_resposta(self) -> None:
        """ask com rag.ask mockado deve imprimir pergunta e resposta."""
        from video_kb.embeddings.chunker import EmbeddingChunk
        from video_kb.embeddings.rag import AskResult
        from video_kb.embeddings.store import EmbeddingStore, SearchHit

        provider = _make_mock_provider(dim=4)
        db_path = Path(self._db)

        # Insere chunk real para has_any=True no CLI
        chunk = EmbeddingChunk(
            chunk_id="run-r:0000",
            run_id="run-r",
            chunk_index=0,
            chunk_type="summary",
            chunk_text="Python e util para RAG.",
            excerpt="Python e util para RAG.",
            source_title="Video RAG",
            source_url="https://example.com/rag",
        )
        vec = provider.embed([chunk.chunk_text])[0]
        with EmbeddingStore(db_path) as store:
            store.upsert_chunks(
                run_id="run-r",
                chunks=[chunk],
                vectors=[vec],
                provider="mock",
                model="mock-model",
            )

        fake_hit = SearchHit(
            run_id="run-r",
            title="Video RAG",
            source_url="https://example.com/rag",
            chunk_type="summary",
            excerpt="Python e util para RAG.",
            score=0.95,
            chapter_start=None,
        )
        fake_result = AskResult(
            question="O que e RAG?",
            answer="RAG e Retrieval-Augmented Generation.",
            sources=[fake_hit],
        )

        with (
            patch("video_kb.providers.load_provider", return_value=provider),
            patch("video_kb.providers.resolve_provider_name", return_value="mock"),
            patch("video_kb.embeddings.rag.ask", return_value=fake_result),
        ):
            out, _err, code = _run_cmd(["--index-db", self._db, "ask", "O que e RAG?"])

        self.assertEqual(code, 0)
        self.assertIn("pergunta", out.lower())


class TestCliRuns(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp()
        self._db = str(Path(self._tmp) / "test.db")

    def _register_run(self, run_id: str, output_dir: str) -> None:
        from video_kb.index import RunIndex

        with RunIndex(Path(self._db)) as idx:
            idx.register(
                run_id=run_id,
                source="https://example.com/video",
                source_hash="abc",
                output_dir=output_dir,
            )

    def test_runs_rm_purge_fora_do_escopo_nao_deleta_arquivos(self) -> None:
        from video_kb.index import RunIndex

        escaped_dir = Path("/tmp/transcreveai-runs-rm-safeguard")
        escaped_dir.mkdir(parents=True, exist_ok=True)
        marker = escaped_dir / "marker.txt"
        marker.write_text("mantido", encoding="utf-8")

        self._register_run("run-safe", str(escaped_dir))

        out, err, code = _run_cmd(
            ["--index-db", self._db, "runs", "rm", "run-safe", "--purge", "--force"]
        )

        self.assertEqual(code, 0)
        self.assertIn("fora do escopo", (err + out).lower())
        self.assertTrue(escaped_dir.exists())
        self.assertTrue(marker.exists())

        with RunIndex(Path(self._db)) as idx:
            self.assertIsNone(idx.get_run("run-safe"))

    def test_runs_rm_purge_nao_aceita_cwd_como_output_dir(self) -> None:
        self._register_run("run-cwd", ".")

        with patch("shutil.rmtree") as rmtree:
            out, err, code = _run_cmd(
                ["--index-db", self._db, "runs", "rm", "run-cwd", "--purge", "--force"]
            )

        self.assertEqual(code, 0)
        self.assertIn("fora do escopo", (err + out).lower())
        rmtree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
