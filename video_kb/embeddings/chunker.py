"""
Chunking de dossies para indexacao semantica.

Recebe um dict de analysis.json e produz lista de EmbeddingChunk
prontos para serem enviados ao provider de embed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EmbeddingChunk:
    """Unidade de texto a ser indexada com metadados de citacao."""

    chunk_id: str  # "{run_id}:{chunk_index:04d}"
    run_id: str
    chunk_index: int
    chunk_type: str  # "summary" | "chapter" | "entity" | "transcript"
    chunk_text: str
    excerpt: str  # primeiros 200 chars de chunk_text
    source_title: str
    source_url: str
    chapter_start: float | None = field(default=None)


def chunk_dossier(
    analysis: dict[str, Any],
    run_id: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[EmbeddingChunk]:
    """
    Divide um dossie (dict de analysis.json) em chunks para indexacao.

    Ordem de producao:
      1. summary (1 chunk)
      2. chapters (1 chunk por capitulo)
      3. entities (1 chunk com todas as entidades)
      4. transcript (N chunks deslizantes de chunk_size com overlap)

    Args:
        analysis: dict carregado do analysis.json de um run.
        run_id: ID do run ao qual os chunks pertencem.
        chunk_size: tamanho maximo de cada chunk de transcript em caracteres.
        overlap: sobreposicao em caracteres entre chunks consecutivos.

    Returns:
        Lista de EmbeddingChunk com chunk_index sequencial global.
    """
    chunks: list[EmbeddingChunk] = []
    idx = 0

    synthesis: dict[str, Any] = analysis.get("synthesis") or {}
    metadata: dict[str, Any] = analysis.get("metadata") or {}

    source_title = metadata.get("title") or ""
    # Prefere source como URL canonica; fallback para webpage_url
    source_url = metadata.get("source") or metadata.get("webpage_url") or ""

    def _make_chunk(
        text: str,
        ctype: str,
        chapter_start: float | None = None,
    ) -> EmbeddingChunk:
        nonlocal idx
        chunk = EmbeddingChunk(
            chunk_id=f"{run_id}:{idx:04d}",
            run_id=run_id,
            chunk_index=idx,
            chunk_type=ctype,
            chunk_text=text,
            excerpt=text[:200],
            source_title=source_title,
            source_url=source_url,
            chapter_start=chapter_start,
        )
        idx += 1
        return chunk

    # ------------------------------------------------------------------
    # 1. Summary
    # ------------------------------------------------------------------
    summary_text = (synthesis.get("summary") or "").strip()
    if summary_text:
        chunks.append(_make_chunk(summary_text, "summary"))

    # ------------------------------------------------------------------
    # 2. Chapters
    # ------------------------------------------------------------------
    for ch in synthesis.get("chapters") or []:
        title = (ch.get("title") or "").strip()
        notes = (ch.get("notes") or "").strip()
        text = f"{title}: {notes}".strip(": ")
        if not text:
            continue
        chapter_start = _coerce_finite_float(ch.get("start"))
        chunks.append(_make_chunk(text, "chapter", chapter_start))

    # ------------------------------------------------------------------
    # 3. Entities
    # ------------------------------------------------------------------
    entities: list[str] = []
    for key in ("entities", "tools_or_products"):
        raw = synthesis.get(key) or []
        for item in raw:
            if isinstance(item, str):
                entities.append(item.strip())
            elif isinstance(item, dict):
                name = item.get("name") or item.get("title") or ""
                if name:
                    entities.append(str(name).strip())

    entity_text = ", ".join(e for e in entities if e)
    if entity_text:
        chunks.append(_make_chunk(entity_text, "entity"))

    # ------------------------------------------------------------------
    # 4. Transcript (janelas deslizantes por fronteira de palavra)
    # ------------------------------------------------------------------
    transcript = (analysis.get("transcript_text") or "").strip()
    if transcript:
        start = 0
        while start < len(transcript):
            end = start + chunk_size
            if end >= len(transcript):
                segment = transcript[start:]
            else:
                # Recua ate a ultima fronteira de palavra
                cut = transcript.rfind(" ", start, end)
                if cut <= start:
                    cut = end  # sem espaco encontrado, corta exato
                segment = transcript[start:cut]

            segment = segment.strip()
            if segment:
                chunks.append(_make_chunk(segment, "transcript"))

            if end >= len(transcript):
                break

            # Avanca mantendo overlap
            next_start = (end if cut <= start else cut) - overlap
            if next_start <= start:
                next_start = start + max(1, chunk_size - overlap)
            start = next_start

    return chunks


def _coerce_finite_float(value: Any) -> float | None:
    """Converte para float e retorna apenas se o valor for finito."""
    if value is None:
        return None
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(candidate):
        return None
    return candidate
