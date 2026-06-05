"""
Extracao de metricas estruturais de AnalysisResult e calculo de WER.

API publica:
    extract_metrics(result) -> dict
    wer_simple(reference, hypothesis) -> float
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import AnalysisResult


def extract_metrics(result: AnalysisResult) -> dict[str, Any]:
    """
    Extrai metricas estruturais de um AnalysisResult sem fazer chamadas extras de IA.

    Retorna dict com todas as metricas documentadas no design do eval harness.
    """
    # Contagens de frames
    frames_total = len(result.frames)
    frames_with_visual_note = sum(1 for f in result.frames if f.visual_note)
    frames_with_ocr = sum(1 for f in result.frames if f.ocr_text)

    # Transcript
    transcript_text = result.transcript_text or ""
    transcript_words = transcript_text.split() if transcript_text.strip() else []

    # Notas visuais (para calculo de custo)
    visual_notes_chars = sum(len(f.visual_note) for f in result.frames if f.visual_note)

    # Sintese
    s = result.synthesis
    summary_len_chars = len(s.summary) if s.summary else 0
    chapters_count = len(s.chapters) if s.chapters else 0
    entities_count = len(s.entities) if s.entities else 0
    tools_count = len(s.tools_or_products) if s.tools_or_products else 0
    claims_count = len(s.claims) if s.claims else 0
    action_items_count = len(s.action_items) if s.action_items else 0
    questions_count = len(s.questions) if s.questions else 0

    # Modo de sintese
    synthesis_mode = "local" if (s.raw or {}).get("mode") == "local" else "llm"

    return {
        "duration_seconds": result.metadata.duration or 0.0,
        "transcript_len_chars": len(transcript_text),
        "transcript_len_words": len(transcript_words),
        "transcript_segments_count": len(result.transcript_segments),
        "frames_total": frames_total,
        "frames_with_visual_note": frames_with_visual_note,
        "frames_with_ocr": frames_with_ocr,
        "visual_notes_len_chars": visual_notes_chars,
        "summary_len_chars": summary_len_chars,
        "chapters_count": chapters_count,
        "entities_count": entities_count,
        "tools_count": tools_count,
        "claims_count": claims_count,
        "action_items_count": action_items_count,
        "questions_count": questions_count,
        "synthesis_mode": synthesis_mode,
        "warnings_count": len(result.warnings),
    }


def wer_simple(reference: str, hypothesis: str) -> float:
    """
    Calcula Word Error Rate simples entre referencia e hipotese.

    Formula: edit_distance_words(ref, hyp) / max(len(ref_words), 1)
    Implementacao DP classica, sem dependencias externas.

    Retorna float entre 0.0 e 1.0+ (pode ser > 1 se hipotese tiver muitas insercoes).
    Retorna 0.0 se referencia for vazia.
    """
    ref_words = _normalize_text(reference).split()
    hyp_words = _normalize_text(hypothesis).split()

    if not ref_words:
        return 0.0

    distance = _edit_distance(ref_words, hyp_words)
    return distance / len(ref_words)


def _normalize_text(text: str) -> str:
    """Normaliza texto para comparacao: minusculas, sem pontuacao basica."""
    text = text.lower()
    # Remove pontuacao simples sem regex para manter zero-dependencia
    for char in ".,!?;:\"'()-[]{}":
        text = text.replace(char, " ")
    # Colapsa espacos
    return " ".join(text.split())


def _edit_distance(ref: list[str], hyp: list[str]) -> int:
    """
    Distancia de edicao (Levenshtein) entre duas listas de palavras.
    DP classico O(m*n) - adequado para transcricoes de videos curtos.
    """
    m = len(ref)
    n = len(hyp)

    # Linha atual e linha anterior (economia de memoria vs matriz completa)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(
                    prev[j],  # delecao
                    curr[j - 1],  # insercao
                    prev[j - 1],  # substituicao
                )
        prev, curr = curr, [0] * (n + 1)

    return prev[n]
