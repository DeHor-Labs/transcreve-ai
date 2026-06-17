"""
Testes do nucleo RAG: chunking, indexacao, recuperacao e erros.

Todos os testes sao unitarios. Nenhum acesso a rede ou modelo de ML.
O provider.embed() e sempre mockado com vetores deterministicos.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_analysis(
    summary: str = "Resumo do video.",
    chapters: list | None = None,
    entities: list | None = None,
    transcript: str = "",
    evidence_items: list | None = None,
    title: str = "Video Teste",
    source_url: str = "https://example.com/video",
) -> dict:
    return {
        "metadata": {"title": title, "source": source_url},
        "synthesis": {
            "summary": summary,
            "chapters": chapters or [],
            "entities": entities or [],
        },
        "evidence_items": evidence_items or [],
        "transcript_text": transcript,
    }


def _make_mock_provider(dim: int = 4) -> MagicMock:
    """Provider mockado cujo embed() devolve vetores deterministicos (hash do texto)."""
    provider = MagicMock()
    provider.capabilities.return_value = {"embed", "transcribe", "synthesize"}

    def _fake_embed(texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            h = abs(hash(text)) % 1000
            vec = [float(h % (dim * (i + 1)) + 1) for i in range(dim)]
            norm = sum(x * x for x in vec) ** 0.5
            vec = [x / norm for x in vec]
            result.append(vec)
        return result

    provider.embed.side_effect = _fake_embed
    return provider


def _tmp_db() -> Path:
    """Retorna path de um arquivo SQLite temporario unico."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return Path(f.name)


# ---------------------------------------------------------------------------
# 1. Chunking
# ---------------------------------------------------------------------------


class TestChunkDossier(unittest.TestCase):
    def test_summary_gera_um_chunk(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(summary="Resumo curto.")
        chunks = chunk_dossier(analysis, "run-001")
        types = [c.chunk_type for c in chunks]
        self.assertIn("summary", types)
        self.assertEqual(types.count("summary"), 1)

    def test_capitulos_geram_chunks_individuais(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [
            {"title": "Intro", "notes": "Primeiro capitulo", "start": 0.0},
            {"title": "Desenvolvimento", "notes": "Segundo capitulo", "start": 60.0},
        ]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        chapter_chunks = [c for c in chunks if c.chunk_type == "chapter"]
        self.assertEqual(len(chapter_chunks), 2)

    def test_entidades_geram_chunk_unico(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(entities=["Python", "FastAPI", "SQLite"])
        chunks = chunk_dossier(analysis, "run-001")
        entity_chunks = [c for c in chunks if c.chunk_type == "entity"]
        self.assertEqual(len(entity_chunks), 1)
        self.assertIn("Python", entity_chunks[0].chunk_text)

    def test_transcript_curto_gera_um_chunk(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(transcript="Texto breve do video.")
        chunks = chunk_dossier(analysis, "run-001")
        transcript_chunks = [c for c in chunks if c.chunk_type == "transcript"]
        self.assertEqual(len(transcript_chunks), 1)

    def test_evidence_items_geram_chunks(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(
            transcript="Texto breve do video.",
            evidence_items=[
                {
                    "kind": "tool_or_product",
                    "value": "Playwright",
                    "confidence": "high",
                    "supports": [
                        {
                            "signal": "ocr",
                            "confidence": "high",
                            "timestamp": 12.34,
                            "frame_path": "frames/frame-012.png",
                            "excerpt": "Playwright aparece no canto inferior.",
                        }
                    ],
                }
            ],
        )
        chunks = chunk_dossier(analysis, "run-001")
        evidence_chunks = [c for c in chunks if c.chunk_type == "evidence"]
        self.assertEqual(len(evidence_chunks), 1)
        self.assertIn("valor: Playwright", evidence_chunks[0].chunk_text)
        self.assertIn("confianca_da_deteccao: high", evidence_chunks[0].chunk_text)
        self.assertIn("supports:", evidence_chunks[0].chunk_text)
        self.assertIn("signal=ocr", evidence_chunks[0].chunk_text)
        self.assertIn("support_confidence=high", evidence_chunks[0].chunk_text)
        self.assertIn("frame_path=frames/frame-012.png", evidence_chunks[0].chunk_text)

    def test_entity_chunk_prefere_evidence_items_a_tools_genericos(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(
            evidence_items=[
                {
                    "kind": "tool_or_product",
                    "value": "Playwright",
                    "confidence": "high",
                    "supports": [{"signal": "ocr", "confidence": "high"}],
                }
            ],
        )
        analysis["synthesis"]["tools_or_products"] = ["Ferramentas de automacao"]

        chunks = chunk_dossier(analysis, "run-001")
        entity_chunk = next((c for c in chunks if c.chunk_type == "entity"), None)
        self.assertIsNotNone(entity_chunk)

        assert entity_chunk is not None
        self.assertIn("Playwright", entity_chunk.chunk_text)
        self.assertNotIn("Ferramentas de automacao", entity_chunk.chunk_text)

    def test_transcript_curto_continua_gerando_um_chunk_com_evidence(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(
            transcript="Texto breve do video.",
            evidence_items=[
                {
                    "kind": "tool_or_product",
                    "value": "Playwright",
                    "confidence": "high",
                    "supports": [
                        {
                            "signal": "ocr",
                            "confidence": "high",
                            "timestamp": 12.34,
                        }
                    ],
                }
            ],
        )
        chunks = chunk_dossier(analysis, "run-001")
        transcript_chunks = [c for c in chunks if c.chunk_type == "transcript"]
        self.assertEqual(len(transcript_chunks), 1)

    def test_transcript_longo_gera_multiplos_chunks(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        longo = "palavra " * 500  # ~4000 chars
        analysis = _make_analysis(transcript=longo)
        chunks = chunk_dossier(analysis, "run-001", chunk_size=1000, overlap=100)
        transcript_chunks = [c for c in chunks if c.chunk_type == "transcript"]
        self.assertGreater(len(transcript_chunks), 1)

    def test_chunk_ids_sao_unicos(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap 1", "notes": "notas", "start": 0.0}]
        analysis = _make_analysis(
            summary="Resumo",
            chapters=chapters,
            entities=["Ent"],
            transcript="Transcricao de teste.",
        )
        chunks = chunk_dossier(analysis, "run-xyz")
        ids = [c.chunk_id for c in chunks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_chunk_id_contem_run_id(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(summary="Resumo")
        chunks = chunk_dossier(analysis, "run-abc-123")
        self.assertTrue(all("run-abc-123" in c.chunk_id for c in chunks))

    def test_excerpt_e_primeiros_200_chars(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        texto_longo = "x" * 500
        analysis = _make_analysis(summary=texto_longo)
        chunks = chunk_dossier(analysis, "run-001")
        summary_chunk = next(c for c in chunks if c.chunk_type == "summary")
        self.assertEqual(len(summary_chunk.excerpt), 200)

    def test_analysis_vazio_retorna_lista_vazia(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis: dict = {}
        chunks = chunk_dossier(analysis, "run-001")
        self.assertEqual(chunks, [])

    def test_chapter_start_propagado(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap", "notes": "notas", "start": 42.5}]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        cap = next(c for c in chunks if c.chunk_type == "chapter")
        chapter_start = cap.chapter_start
        self.assertIsNotNone(chapter_start)
        assert chapter_start is not None
        self.assertAlmostEqual(chapter_start, 42.5)

    def test_chapter_start_aceita_timestamp_mm_ss(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap", "notes": "notas", "start": "01:02,5"}]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        cap = next(c for c in chunks if c.chunk_type == "chapter")
        chapter_start = cap.chapter_start
        self.assertIsNotNone(chapter_start)
        assert chapter_start is not None
        self.assertAlmostEqual(chapter_start, 62.5)

    def test_chapter_start_aceita_timestamp_hh_mm_ss(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap", "notes": "notas", "start": "01:02:03.5"}]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        cap = next(c for c in chunks if c.chunk_type == "chapter")
        chapter_start = cap.chapter_start
        self.assertIsNotNone(chapter_start)
        assert chapter_start is not None
        self.assertAlmostEqual(chapter_start, 3723.5)

    def test_chapter_start_timestamp_invalido_nao_e_inserido(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap", "notes": "notas", "start": "01:02:03:04"}]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        cap = next(c for c in chunks if c.chunk_type == "chapter")
        self.assertIsNone(cap.chapter_start)

    def test_chapter_start_nao_finito_nao_e_inserido(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        chapters = [{"title": "Cap", "notes": "notas", "start": float("nan")}]
        analysis = _make_analysis(chapters=chapters)
        chunks = chunk_dossier(analysis, "run-001")
        cap = next(c for c in chunks if c.chunk_type == "chapter")
        self.assertIsNone(cap.chapter_start)

    def test_source_title_e_url_nos_chunks(self) -> None:
        from video_kb.embeddings.chunker import chunk_dossier

        analysis = _make_analysis(title="Meu Video", source_url="https://yt.com/abc")
        chunks = chunk_dossier(analysis, "run-001")
        for c in chunks:
            self.assertEqual(c.source_title, "Meu Video")
            self.assertEqual(c.source_url, "https://yt.com/abc")


# ---------------------------------------------------------------------------
# 2. Indexacao com provider mockado
# ---------------------------------------------------------------------------


class TestIndexRun(unittest.TestCase):
    def test_indexa_chunks_e_retorna_contagem(self) -> None:
        from video_kb.embeddings.rag import index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis = _make_analysis(
            summary="Resumo de teste.",
            entities=["Python"],
            transcript="Algum texto de transcricao.",
        )

        count = index_run(
            run_id="run-001",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        self.assertGreater(count, 0)
        provider.embed.assert_called()

    def test_segunda_indexacao_sem_force_retorna_zero(self) -> None:
        from video_kb.embeddings.rag import index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis = _make_analysis(summary="Resumo.")

        index_run(
            run_id="run-002",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        count2 = index_run(
            run_id="run-002",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        self.assertEqual(count2, 0)

    def test_force_reindexa(self) -> None:
        from video_kb.embeddings.rag import index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis = _make_analysis(summary="Resumo.")

        count1 = index_run(
            run_id="run-003",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        count2 = index_run(
            run_id="run-003",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
            force=True,
        )
        self.assertEqual(count1, count2)
        self.assertGreater(count2, 0)

    def test_analysis_sem_conteudo_retorna_zero(self) -> None:
        from video_kb.embeddings.rag import index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis: dict = {}

        count = index_run(
            run_id="run-004",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        self.assertEqual(count, 0)
        provider.embed.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Retrieval top-k cosine
# ---------------------------------------------------------------------------


class TestSearchRetrieval(unittest.TestCase):
    def _setup_db_with_chunks(self, run_id: str = "run-001") -> tuple[Path, MagicMock]:
        """Indexa chunks distintos e retorna (db_path, provider)."""
        from video_kb.embeddings.rag import index_run

        provider = _make_mock_provider(dim=8)
        db = _tmp_db()

        analysis = _make_analysis(
            summary="Python e uma linguagem de programacao.",
            entities=["Python", "FastAPI"],
            transcript="Este video fala sobre Python e desenvolvimento web.",
        )
        index_run(
            run_id=run_id,
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )
        return db, provider

    def test_search_retorna_lista(self) -> None:
        from video_kb.embeddings.rag import search

        db, provider = self._setup_db_with_chunks()
        hits = search("Python", provider, db_path=db, top_k=3)
        self.assertIsInstance(hits, list)

    def test_search_respeita_top_k(self) -> None:
        from video_kb.embeddings.rag import search

        db, provider = self._setup_db_with_chunks()
        hits = search("Python", provider, db_path=db, top_k=2)
        self.assertLessEqual(len(hits), 2)

    def test_search_em_db_vazio_retorna_lista_vazia(self) -> None:
        from video_kb.embeddings.rag import search

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        hits = search("qualquer coisa", provider, db_path=db, top_k=5)
        self.assertEqual(hits, [])

    def test_search_scores_em_ordem_decrescente(self) -> None:
        from video_kb.embeddings.rag import search

        db, provider = self._setup_db_with_chunks()
        hits = search("Python", provider, db_path=db, top_k=10)
        scores = [h.score for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_search_retorna_searchhit_com_campos_esperados(self) -> None:
        from video_kb.embeddings.rag import search
        from video_kb.embeddings.store import SearchHit

        db, provider = self._setup_db_with_chunks()
        hits = search("Python", provider, db_path=db, top_k=5)
        self.assertGreater(len(hits), 0)
        hit = hits[0]
        self.assertIsInstance(hit, SearchHit)
        self.assertIsInstance(hit.run_id, str)
        self.assertIsInstance(hit.excerpt, str)
        self.assertIsInstance(hit.score, float)
        self.assertIsInstance(hit.chunk_type, str)

    def test_search_filtra_por_run_ids(self) -> None:
        from video_kb.embeddings.rag import index_run, search

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()

        for rid in ("run-A", "run-B"):
            index_run(
                run_id=rid,
                analysis=_make_analysis(summary=f"Resumo de {rid}."),
                provider=provider,
                provider_name="mock",
                model_name="mock-model",
                db_path=db,
            )

        hits = search("Resumo", provider, db_path=db, top_k=10, run_ids=["run-A"])
        run_ids_nos_hits = {h.run_id for h in hits}
        self.assertNotIn("run-B", run_ids_nos_hits)
        self.assertIn("run-A", run_ids_nos_hits)

    def test_search_run_ids_vazio_retorna_lista_vazia(self) -> None:
        from video_kb.embeddings.rag import index_run, search

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()

        for rid in ("run-A", "run-B"):
            index_run(
                run_id=rid,
                analysis=_make_analysis(summary=f"Resumo de {rid}."),
                provider=provider,
                provider_name="mock",
                model_name="mock-model",
                db_path=db,
            )

        empty_filter_hits = search("Resumo", provider, db_path=db, top_k=10, run_ids=[])

        self.assertEqual(empty_filter_hits, [])

    def test_search_run_ids_vazio_nao_chama_embed(self) -> None:
        from video_kb.embeddings.rag import search

        provider = MagicMock()
        hits = search("Resumo", provider, db_path=_tmp_db(), top_k=10, run_ids=[])

        self.assertEqual(hits, [])
        provider.embed.assert_not_called()


class TestEmbeddingStoreSearch(unittest.TestCase):
    def test_search_run_ids_vazio_retorna_lista_vazia(self) -> None:
        from video_kb.embeddings.store import EmbeddingStore

        db = _tmp_db()
        with EmbeddingStore(db) as store:
            hits = store.search([0.1, 0.2, 0.3, 0.4], limit=5, run_ids=[])
            self.assertEqual(hits, [])


class TestSearchDimMismatchResiliencia(unittest.TestCase):
    """Busca em base com providers de dimensoes diferentes nao deve estourar."""

    def _index_run_com_dim(self, db: Path, run_id: str, dim: int) -> None:
        from video_kb.embeddings.rag import index_run

        index_run(
            run_id=run_id,
            analysis=_make_analysis(
                summary=f"Resumo do {run_id}.",
                entities=["WhatsApp", "Evolution API"],
                transcript=f"Transcricao do {run_id} sobre Coexistence.",
            ),
            provider=_make_mock_provider(dim=dim),
            provider_name="mock",
            model_name=f"mock-{dim}",
            db_path=db,
        )

    def test_busca_global_com_dims_mistas_nao_estoura(self) -> None:
        from video_kb.embeddings.rag import search

        db = _tmp_db()
        # Run antigo indexado com provider "local" (384-dim, simulado com dim=4)
        self._index_run_com_dim(db, "run-local-384", dim=4)
        # Run novo indexado com provider "openai" (1536-dim, simulado com dim=8)
        self._index_run_com_dim(db, "run-openai-1536", dim=8)

        provider_query = _make_mock_provider(dim=8)
        # Busca GLOBAL (sem run_ids) deve recuperar so os compativeis, sem ValueError.
        hits = search("Coexistence WhatsApp Evolution API", provider_query, db_path=db, top_k=10)

        self.assertIsInstance(hits, list)
        self.assertGreater(len(hits), 0)
        run_ids_nos_hits = {h.run_id for h in hits}
        self.assertIn("run-openai-1536", run_ids_nos_hits)
        self.assertNotIn("run-local-384", run_ids_nos_hits)

    def test_busca_emite_warning_ao_pular_chunks(self) -> None:
        from video_kb.embeddings.rag import search

        db = _tmp_db()
        self._index_run_com_dim(db, "run-local-384", dim=4)
        self._index_run_com_dim(db, "run-openai-1536", dim=8)

        provider_query = _make_mock_provider(dim=8)
        with self.assertLogs("video_kb.embeddings.store", level="WARNING") as cm:
            search("qualquer consulta", provider_query, db_path=db, top_k=10)

        log_text = "\n".join(cm.output)
        self.assertIn("dimensao incompativel", log_text)
        self.assertIn("dim=4", log_text)

    def test_run_id_compativel_continua_intacto(self) -> None:
        from video_kb.embeddings.rag import search

        db = _tmp_db()
        self._index_run_com_dim(db, "run-local-384", dim=4)
        self._index_run_com_dim(db, "run-openai-1536", dim=8)

        # Busca restrita ao run compativel (dim=8) deve funcionar normalmente.
        provider_query = _make_mock_provider(dim=8)
        hits = search(
            "Coexistence",
            provider_query,
            db_path=db,
            top_k=10,
            run_ids=["run-openai-1536"],
        )
        self.assertGreater(len(hits), 0)
        self.assertEqual({h.run_id for h in hits}, {"run-openai-1536"})


# ---------------------------------------------------------------------------
# 4. Provider sem embed levanta erro claro
# ---------------------------------------------------------------------------


class TestProviderSemEmbed(unittest.TestCase):
    def test_embed_em_provider_sem_capacidade_levanta_capability_not_supported(
        self,
    ) -> None:
        from video_kb.providers.base import CapabilityNotSupported

        provider = MagicMock()
        provider.capabilities.return_value = {"transcribe", "synthesize"}
        provider.embed.side_effect = CapabilityNotSupported("anthropic", "embed")

        with self.assertRaises(CapabilityNotSupported) as ctx:
            provider.embed(["texto"])

        self.assertIn("anthropic", str(ctx.exception))
        self.assertIn("embed", str(ctx.exception))

    def test_capability_not_supported_tem_atributos(self) -> None:
        from video_kb.providers.base import CapabilityNotSupported

        exc = CapabilityNotSupported("anthropic", "embed")
        self.assertEqual(exc.provider, "anthropic")
        self.assertEqual(exc.capability, "embed")

    def test_index_run_com_provider_sem_embed_propaga_excecao(self) -> None:
        from video_kb.embeddings.rag import index_run
        from video_kb.providers.base import CapabilityNotSupported

        provider = MagicMock()
        provider.capabilities.return_value = {"transcribe"}
        provider.embed.side_effect = CapabilityNotSupported("anthropic", "embed")

        db = _tmp_db()
        analysis = _make_analysis(summary="Resumo.")

        with self.assertRaises(CapabilityNotSupported):
            index_run(
                run_id="run-no-embed",
                analysis=analysis,
                provider=provider,
                provider_name="anthropic",
                model_name="n/a",
                db_path=db,
            )


# ---------------------------------------------------------------------------
# 5. Mistura de dimensoes
# ---------------------------------------------------------------------------


class TestDimMismatch(unittest.TestCase):
    def test_dim_mismatch_levanta_erro_ao_reindexar_com_dim_diferente(
        self,
    ) -> None:
        from video_kb.embeddings.rag import index_run
        from video_kb.embeddings.store import DimMismatchError

        provider_4 = _make_mock_provider(dim=4)
        provider_8 = _make_mock_provider(dim=8)
        db = _tmp_db()
        analysis = _make_analysis(summary="Resumo.")

        index_run(
            run_id="run-dim",
            analysis=analysis,
            provider=provider_4,
            provider_name="mock",
            model_name="mock-4",
            db_path=db,
        )

        # Tentar indexar com dim diferente e sem force deve levantar DimMismatchError
        with self.assertRaises(DimMismatchError) as ctx:
            # Precisamos que has_indexed retorne True mas force=False
            # Para isso passamos force=False (default)
            # O store vai ver que ja existe e vai checar dim
            from video_kb.embeddings.chunker import chunk_dossier
            from video_kb.embeddings.store import EmbeddingStore

            chunks = chunk_dossier(analysis, "run-dim")
            texts = [c.chunk_text for c in chunks]
            vectors = provider_8.embed(texts)  # dim=8 mas banco tem dim=4
            with EmbeddingStore(db) as store:
                store.upsert_chunks(
                    run_id="run-dim",
                    chunks=chunks,
                    vectors=vectors,
                    provider="mock",
                    model="mock-8",
                    force=False,
                )

        self.assertEqual(ctx.exception.run_id, "run-dim")
        self.assertEqual(ctx.exception.existing_dim, 4)
        self.assertEqual(ctx.exception.new_dim, 8)

    def test_dim_mismatch_mensagem_menciona_force(self) -> None:
        from video_kb.embeddings.store import DimMismatchError

        exc = DimMismatchError("run-x", 384, 1536)
        self.assertIn("force", str(exc).lower())
        self.assertIn("384", str(exc))
        self.assertIn("1536", str(exc))


# ---------------------------------------------------------------------------
# 6. ask() retorna AskResult
# ---------------------------------------------------------------------------


class TestAskFunction(unittest.TestCase):
    def test_ask_sem_chunks_retorna_resposta_padrao(self) -> None:
        from video_kb.embeddings.rag import ask

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()

        result = ask(
            question="O que e Python?",
            embed_provider=provider,
            synth_provider=provider,
            db_path=db,
        )
        self.assertIn("Nao encontrei", result.answer)
        self.assertEqual(result.sources, [])

    def test_ask_com_chunks_chama_synth_provider(self) -> None:
        from video_kb.embeddings.rag import ask, index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis = _make_analysis(summary="Python e excelente para RAG.")

        index_run(
            run_id="run-ask",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )

        synth = MagicMock()
        synth.complete.return_value = "Resposta mockada sobre Python."

        result = ask(
            question="Fale sobre Python",
            embed_provider=provider,
            synth_provider=synth,
            db_path=db,
        )
        self.assertIsInstance(result.answer, str)
        self.assertGreater(len(result.sources), 0)

    def test_ask_com_chunks_e_resposta_not_found_usa_fallback_evidencial(self) -> None:
        from video_kb.embeddings.rag import ask, index_run

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()
        analysis = _make_analysis(summary="Video mostra Playwright, Cypress e Selenium.")

        index_run(
            run_id="run-ask-fallback",
            analysis=analysis,
            provider=provider,
            provider_name="mock",
            model_name="mock-model",
            db_path=db,
        )

        synth = MagicMock()
        synth.complete.return_value = "Nao encontrei informacao sobre isso nos videos indexados."

        result = ask(
            question="Isso e util para meus projetos?",
            embed_provider=provider,
            synth_provider=synth,
            db_path=db,
        )

        self.assertIn("Fatos extraidos", result.answer)
        self.assertIn("Playwright", result.answer)
        self.assertGreater(len(result.sources), 0)

    def test_prompt_orienta_inferencias_como_derivadas(self) -> None:
        from video_kb.embeddings.rag import _build_prompt
        from video_kb.embeddings.store import SearchHit

        prompt = _build_prompt(
            "Isso e util para nossos projetos?",
            [
                SearchHit(
                    run_id="run-qa",
                    title="Video QA",
                    source_url="https://example.com/video",
                    chunk_type="summary",
                    excerpt="Video mostra Playwright e Cypress.",
                    score=0.9,
                    chapter_start=None,
                )
            ],
        )

        normalized_prompt = " ".join(prompt.split())
        self.assertIn("inferencias derivadas dos fatos recuperados", normalized_prompt)
        self.assertIn(
            "Nao diga que um projeto especifico aparece no video se ele nao estiver nos trechos",
            normalized_prompt,
        )
        self.assertIn("nao como risco tecnico da ferramenta", normalized_prompt)

    def test_prompt_remove_confianca_de_evidencia_do_contexto_llm(self) -> None:
        from video_kb.embeddings.rag import _build_prompt
        from video_kb.embeddings.store import SearchHit

        prompt = _build_prompt(
            "Quais riscos?",
            [
                SearchHit(
                    run_id="run-qa",
                    title="Video QA",
                    source_url="https://example.com/video",
                    chunk_type="evidence",
                    excerpt=(
                        "valor: Playwright | confianca_da_deteccao: medium | "
                        "supports: support_confidence=medium; signal=vision; timestamp=4.0"
                    ),
                    score=0.9,
                    chapter_start=None,
                )
            ],
        )

        self.assertIn("valor: Playwright", prompt)
        self.assertIn("signal=vision", prompt)
        self.assertIn("timestamp=4.0", prompt)
        self.assertNotIn("confianca_da_deteccao", prompt)
        self.assertNotIn("support_confidence", prompt)

        prompt = _build_prompt(
            "Quais riscos?",
            [
                SearchHit(
                    run_id="run-qa",
                    title="Video QA",
                    source_url="https://example.com/video",
                    chunk_type="evidence",
                    excerpt=(
                        "valor: Playwright | confianca_da_deteccao: medium | "
                        "supports: signal=vision; support_confidence=medium; timestamp=4.0"
                    ),
                    score=0.9,
                    chapter_start=None,
                )
            ],
        )

        self.assertIn("signal=vision; timestamp=4.0", prompt)
        self.assertNotIn("support_confidence", prompt)

    def test_ask_result_tem_question(self) -> None:
        from video_kb.embeddings.rag import ask

        provider = _make_mock_provider(dim=4)
        db = _tmp_db()

        result = ask(
            question="Pergunta de teste?",
            embed_provider=provider,
            synth_provider=provider,
            db_path=db,
        )
        self.assertEqual(result.question, "Pergunta de teste?")


class TestCallCompleteFallback(unittest.TestCase):
    def test_call_complete_usa_complete_publico(self) -> None:
        from video_kb.embeddings.rag import _call_complete

        provider = MagicMock()
        provider.complete.return_value = "resposta direta"

        out = _call_complete(provider, "pergunta")
        self.assertEqual(out, "resposta direta")

    def test_call_complete_fallback_para_chat_publico(self) -> None:
        from types import SimpleNamespace

        from video_kb.embeddings.rag import _call_complete

        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("provider down")
        provider.chat.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="resp da api",
                    )
                )
            ]
        )

        out = _call_complete(provider, "pergunta")
        self.assertEqual(out, "resp da api")

    def test_call_complete_fallback_para_generate_content_publico(self) -> None:
        from types import SimpleNamespace

        from video_kb.embeddings.rag import _call_complete

        provider = MagicMock()
        provider.complete.side_effect = RuntimeError("provider down")
        provider.chat.side_effect = RuntimeError("chat down")
        provider.generate_content.return_value = SimpleNamespace(text="resp gemini")

        out = _call_complete(provider, "pergunta")
        self.assertEqual(out, "resp gemini")

    def test_call_complete_sem_metodo_publico_retorna_fallback(self) -> None:
        from video_kb.embeddings.rag import _call_complete

        class ProviderSemComplete:
            pass

        out = _call_complete(ProviderSemComplete(), "pergunta")
        self.assertIn("Nao foi possivel", out)


if __name__ == "__main__":
    unittest.main()
