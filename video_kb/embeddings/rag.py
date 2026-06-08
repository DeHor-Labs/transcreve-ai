"""
RAG - Recuperacao e geracao de respostas com base em chunks indexados.

Funcao principal: ask(question, ...) -> AskResult
  1. Gera embedding da pergunta via provider.embed()
  2. Recupera top-k chunks via EmbeddingStore.search()
  3. Monta prompt com os chunks como contexto
  4. Chama provider.complete() para gerar resposta
  5. Retorna AskResult com answer + sources
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import EmbeddingStore, SearchHit

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass
class AskResult:
    """Resultado de uma consulta RAG completa."""

    question: str
    answer: str
    sources: list[SearchHit] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt de sintese
# ---------------------------------------------------------------------------

_NOT_FOUND_ANSWER = "Nao encontrei informacao sobre isso nos videos indexados."

_PROMPT_TEMPLATE = """\
Responda a pergunta abaixo com base EXCLUSIVAMENTE nos trechos fornecidos.
Se a resposta nao estiver nos trechos, diga exatamente:
"_NOT_FOUND_ANSWER_PLACEHOLDER"
Cite os videos usados pelo titulo ao responder.
Se a pergunta pedir utilidade, aplicacao a projetos, riscos ou proximos passos,
separe fatos extraidos dos trechos de inferencias praticas. Nao diga que um
projeto especifico aparece no video se ele nao estiver nos trechos.
Nunca escreva que inferencias, riscos ou aplicacoes foram "extraidos do video";
rotule-os como inferencias derivadas dos fatos recuperados.
Quando um trecho mencionar confianca de evidencia, trate isso como forca da
deteccao/proveniencia, nao como risco tecnico da ferramenta.

Pergunta: {question}

Trechos:
{trechos}
"""


def _build_prompt(question: str, hits: list[SearchHit]) -> str:
    lines: list[str] = []
    for i, hit in enumerate(hits, start=1):
        tipo = _chunk_type_label(hit.chunk_type)
        titulo = hit.title or hit.run_id
        excerpt = _prompt_excerpt(hit)
        lines.append(f'[{i}] "{excerpt}" - {titulo} ({tipo})')
    trechos = "\n".join(lines)
    return _PROMPT_TEMPLATE.replace(
        "_NOT_FOUND_ANSWER_PLACEHOLDER",
        _NOT_FOUND_ANSWER,
    ).format(question=question, trechos=trechos)


def _chunk_type_label(chunk_type: str) -> str:
    labels = {
        "summary": "resumo",
        "chapter": "capitulo",
        "entity": "entidades",
        "evidence": "evidencia/proveniencia",
        "transcript": "transcricao",
    }
    return labels.get(chunk_type, chunk_type)


def _prompt_excerpt(hit: SearchHit) -> str:
    excerpt = hit.excerpt or ""
    if hit.chunk_type != "evidence":
        return excerpt
    excerpt = re.sub(r"\s*\|\s*confianca_da_deteccao:\s*[^|]+", "", excerpt)
    excerpt = re.sub(r";\s*support_confidence=[^;|]+", "", excerpt)
    return excerpt


# ---------------------------------------------------------------------------
# Funcao de indexacao de um run
# ---------------------------------------------------------------------------


def index_run(
    run_id: str,
    analysis: dict[str, Any],
    provider: Any,
    provider_name: str,
    model_name: str,
    db_path: Path | None = None,
    force: bool = False,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> int:
    """
    Indexa um run: chunkeia o dossie, gera embeddings e grava no banco.

    Args:
        run_id: ID do run.
        analysis: dict carregado do analysis.json.
        provider: instancia de AIProvider com capability "embed".
        provider_name: nome do provider (ex: "openai").
        model_name: nome do modelo de embedding (ex: "text-embedding-3-small").
        db_path: caminho do SQLite (default: resolve_index_path()).
        force: se True, reindexar mesmo que ja exista.
        chunk_size: tamanho maximo de chunks de transcript.
        overlap: sobreposicao entre chunks consecutivos.

    Returns:
        Numero de chunks gravados (0 se ja indexado e nao --force).
    """
    from .chunker import chunk_dossier

    chunks = chunk_dossier(analysis, run_id, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        return 0

    texts = [c.chunk_text for c in chunks]
    vectors = provider.embed(texts)

    with EmbeddingStore(db_path) as store:
        # Se ja indexado e nao --force, upsert_chunks retorna 0
        count = store.upsert_chunks(
            run_id=run_id,
            chunks=chunks,
            vectors=vectors,
            provider=provider_name,
            model=model_name,
            force=force,
        )

    return count


# ---------------------------------------------------------------------------
# Funcao de busca (search-only, sem LLM)
# ---------------------------------------------------------------------------


def search(
    query: str,
    provider: Any,
    db_path: Path | None = None,
    top_k: int = 5,
    run_ids: list[str] | None = None,
) -> list[SearchHit]:
    """
    Gera embedding da query e retorna top-k chunks mais similares.

    Nao chama LLM para sintese. Util para inspecionar o que foi indexado.

    Args:
        query: texto da consulta.
        provider: instancia de AIProvider com capability "embed".
        db_path: caminho do SQLite.
        top_k: numero maximo de resultados.
        run_ids: filtrar busca a runs especificos (None = todos).

    Returns:
        Lista de SearchHit ordenada por score decrescente.
    """
    if run_ids is not None and not run_ids:
        return []

    query_vecs = provider.embed([query])
    query_vec = query_vecs[0]

    with EmbeddingStore(db_path) as store:
        hits = store.search(query_vec, limit=top_k, run_ids=run_ids)

    return hits


# ---------------------------------------------------------------------------
# Funcao principal de RAG
# ---------------------------------------------------------------------------


def ask(
    question: str,
    embed_provider: Any,
    synth_provider: Any,
    db_path: Path | None = None,
    top_k: int = 5,
    run_ids: list[str] | None = None,
) -> AskResult:
    """
    RAG completo: recupera chunks relevantes e gera resposta com LLM.

    O provider de embeddings (embed_provider) pode ser diferente do
    provider de sintese (synth_provider). Caso mais comum: mesmo provider.

    Args:
        question: pergunta do usuario.
        embed_provider: provider com capability "embed" para vetorizar a query.
        synth_provider: provider com capability "synthesize" ou "complete"
                        para gerar a resposta. Na pratica usa synthesize()
                        com prompt RAG via _call_complete().
        db_path: caminho do SQLite.
        top_k: numero de chunks de contexto.
        run_ids: filtrar busca a runs especificos.

    Returns:
        AskResult com answer e sources usadas.
    """
    hits = search(
        query=question,
        provider=embed_provider,
        db_path=db_path,
        top_k=top_k,
        run_ids=run_ids,
    )

    if not hits:
        return AskResult(
            question=question,
            answer=_NOT_FOUND_ANSWER,
            sources=[],
        )

    prompt = _build_prompt(question, hits)
    answer = _call_complete(synth_provider, prompt)
    if _is_not_found_answer(answer):
        answer = _fallback_evidence_answer(hits)

    return AskResult(question=question, answer=answer, sources=hits)


def _is_not_found_answer(answer: str) -> bool:
    return (answer or "").strip().strip('"') == _NOT_FOUND_ANSWER


def _fallback_evidence_answer(hits: list[SearchHit]) -> str:
    lines = [
        "Encontrei trechos relacionados, mas eles nao respondem a pergunta inteira diretamente.",
        "",
        "Fatos extraidos dos videos indexados:",
    ]
    seen: set[str] = set()
    for hit in hits[:6]:
        excerpt = (hit.excerpt or "").strip()
        if not excerpt:
            continue
        key = excerpt.lower()
        if key in seen:
            continue
        seen.add(key)
        title = hit.title or hit.run_id
        lines.append(f"- {excerpt} ({title})")

    lines.extend(
        [
            "",
            "Limite: aplicacoes a projetos ou produtos citados na pergunta devem ser "
            "tratadas como inferencia do agente, nao como fala do video.",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Adaptador de sintese: chama o LLM do provider com o prompt RAG
# ---------------------------------------------------------------------------


def _call_complete(provider: Any, prompt: str) -> str:
    """
    Chama o LLM do provider para gerar texto a partir de um prompt.

    Tenta apenas metodos publicos para manter o contrato de providers
    plugavel por entry points:
      1. provider.complete(prompt)
      2. provider.chat(prompt)
      3. provider.generate_content(prompt)

    Retorna string com a resposta gerada.
    """
    for method_name in ("complete", "chat", "generate_content"):
        method = getattr(provider, method_name, None)
        if not callable(method):
            continue
        try:
            response = method(prompt)
        except Exception:  # noqa: BLE001
            _LOGGER.debug("provider.%s falhou", method_name, exc_info=True)
            continue
        text = _response_to_text(response)
        if text:
            return text

    _LOGGER.info("falha em todos os metodos publicos de sintese no _call_complete")
    return "Nao foi possivel gerar resposta: provider de sintese nao disponivel."


def _response_to_text(response: Any) -> str:
    """Extrai texto de respostas publicas comuns de SDKs/adapter sem acoplar ao provider."""
    if isinstance(response, str):
        return response.strip()
    if type(response).__module__.startswith("unittest.mock"):
        return ""

    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()

    content_blocks = getattr(response, "content", None)
    if content_blocks:
        first = content_blocks[0]
        content_text = getattr(first, "text", None)
        if isinstance(content_text, str) and content_text.strip():
            return content_text.strip()

    return ""
