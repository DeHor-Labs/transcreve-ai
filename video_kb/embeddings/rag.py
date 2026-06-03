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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import EmbeddingStore, SearchHit

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

_PROMPT_TEMPLATE = """\
Responda a pergunta abaixo com base EXCLUSIVAMENTE nos trechos fornecidos.
Se a resposta nao estiver nos trechos, diga exatamente:
"Nao encontrei informacao sobre isso nos videos indexados."
Cite os videos usados pelo titulo ao responder.

Pergunta: {question}

Trechos:
{trechos}
"""


def _build_prompt(question: str, hits: list[SearchHit]) -> str:
    lines: list[str] = []
    for i, hit in enumerate(hits, start=1):
        tipo = _chunk_type_label(hit.chunk_type)
        titulo = hit.title or hit.run_id
        lines.append(f'[{i}] "{hit.excerpt}" - {titulo} ({tipo})')
    trechos = "\n".join(lines)
    return _PROMPT_TEMPLATE.format(question=question, trechos=trechos)


def _chunk_type_label(chunk_type: str) -> str:
    labels = {
        "summary": "resumo",
        "chapter": "capitulo",
        "entity": "entidades",
        "transcript": "transcricao",
    }
    return labels.get(chunk_type, chunk_type)


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
            answer="Nao encontrei informacao sobre isso nos videos indexados.",
            sources=[],
        )

    prompt = _build_prompt(question, hits)
    answer = _call_complete(synth_provider, prompt)

    return AskResult(question=question, answer=answer, sources=hits)


# ---------------------------------------------------------------------------
# Adaptador de sintese: chama o LLM do provider com o prompt RAG
# ---------------------------------------------------------------------------


def _call_complete(provider: Any, prompt: str) -> str:
    """
    Chama o LLM do provider para gerar texto a partir de um prompt.

    Tenta diferentes interfaces em ordem de preferenca:
      1. provider.complete(prompt) - interface direta (providers que a implementarem)
      2. provider.synthesize() via wrapper minimo
      3. Fallback com o client OpenAI/Gemini/Anthropic diretamente

    Retorna string com a resposta gerada.
    """
    # Tenta interface direta `complete` se existir
    if hasattr(provider, "complete"):
        try:
            return str(provider.complete(prompt))
        except Exception:  # noqa: BLE001
            pass

    # Tenta via OpenAI client (OpenAIProvider expoe _client)
    if hasattr(provider, "_client"):
        try:
            client = provider._client
            # OpenAI SDK
            if hasattr(client, "chat"):
                resp = client.chat.completions.create(
                    model=_get_vision_model(provider),
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1024,
                )
                return resp.choices[0].message.content or ""
        except Exception:  # noqa: BLE001
            pass

    # Tenta via Gemini client
    if hasattr(provider, "_model"):
        try:
            model = provider._model
            if hasattr(model, "generate_content"):
                resp = model.generate_content(prompt)
                return resp.text or ""
        except Exception:  # noqa: BLE001
            pass

    # Tenta via Anthropic client
    if hasattr(provider, "_anthropic"):
        try:
            client = provider._anthropic
            resp = client.messages.create(
                model=_get_vision_model(provider),
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
        except Exception:  # noqa: BLE001
            pass

    return "Nao foi possivel gerar resposta: provider de sintese nao disponivel."


def _get_vision_model(provider: Any) -> str:
    """Tenta obter o modelo configurado no provider; usa fallback por tipo."""
    for attr in ("_vision_model", "_model_name", "model"):
        val = getattr(provider, attr, None)
        if val and isinstance(val, str):
            return val
    # Fallbacks seguros por tipo de provider
    cls = type(provider).__name__.lower()
    if "openai" in cls:
        return "gpt-4o-mini"
    if "gemini" in cls:
        return "gemini-1.5-flash"
    if "anthropic" in cls:
        return "claude-3-haiku-20240307"
    return "gpt-4o-mini"
