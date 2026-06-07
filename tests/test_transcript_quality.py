from __future__ import annotations

from video_kb.models import TranscriptSegment
from video_kb.transcript_quality import sanitize_transcription


def test_discards_amara_caption_credit_hallucination() -> None:
    result = sanitize_transcription(
        "Transcrição e Legendas pela comunidade Amara.org",
        [
            TranscriptSegment(
                start=0.0, end=3.0, text="Transcrição e Legendas pela comunidade Amara.org"
            )
        ],
    )

    assert result.status == "discarded_low_value"
    assert result.reason == "caption_credit_only"
    assert result.text == ""
    assert result.segments == []
    assert "OCR/visao" in result.warning


def test_keeps_real_transcript_even_when_it_mentions_subtitles() -> None:
    result = sanitize_transcription(
        "Hoje eu explico como QA usa Playwright. As legendas foram revisadas depois.",
        [
            TranscriptSegment(
                start=0.0,
                end=6.0,
                text="Hoje eu explico como QA usa Playwright.",
            )
        ],
    )

    assert result.status == "available"
    assert "Playwright" in result.text
    assert len(result.segments) == 1
