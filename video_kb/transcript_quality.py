from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .models import TranscriptSegment


@dataclass(frozen=True)
class TranscriptQualityResult:
    text: str
    segments: list[TranscriptSegment]
    status: str
    reason: str = ""
    warning: str = ""
    original_text: str = ""


_CAPTION_CREDIT_PATTERNS = (
    "transcricao e legendas pela comunidade amara org",
    "transcricao e legenda pela comunidade amara org",
    "legendas pela comunidade amara org",
    "legenda pela comunidade amara org",
    "subtitles by the amara org community",
    "captions by the amara org community",
)


def sanitize_transcription(
    text: str,
    segments: list[TranscriptSegment],
) -> TranscriptQualityResult:
    """Drop known low-value speech hallucinations while keeping real transcript text."""
    clean_text = (text or "").strip()
    clean_segments = [
        TranscriptSegment(
            start=segment.start,
            end=segment.end,
            text=(segment.text or "").strip(),
        )
        for segment in segments
        if (segment.text or "").strip()
    ]

    if not clean_text and clean_segments:
        clean_text = " ".join(segment.text for segment in clean_segments).strip()

    if not clean_text:
        return TranscriptQualityResult(text="", segments=[], status="empty")

    if _is_caption_credit_only(clean_text):
        warning = (
            "Transcricao descartada por baixa utilidade: o audio retornou apenas "
            "credito generico de legenda, entao a analise deve priorizar OCR/visao."
        )
        return TranscriptQualityResult(
            text="",
            segments=[],
            status="discarded_low_value",
            reason="caption_credit_only",
            warning=warning,
            original_text=clean_text,
        )

    return TranscriptQualityResult(text=clean_text, segments=clean_segments, status="available")


def _is_caption_credit_only(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if normalized in _CAPTION_CREDIT_PATTERNS:
        return True
    if "amara org" not in normalized:
        return False
    words = normalized.split()
    return len(words) <= 12 and any(pattern in normalized for pattern in _CAPTION_CREDIT_PATTERNS)


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()
