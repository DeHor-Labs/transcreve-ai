from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import asdict
from typing import Any

from .models import AnalysisResult, EvidenceItem, EvidenceSupport
from .utils import compact_text, format_timestamp

_CONFIDENCE_RANK = {"low": 1, "medium": 2, "high": 3}
_GENERIC_SYNTHESIS_PATTERNS = (
    r"^ferramentas?\s+de\b",
    r"^praticas?\s+de\b",
    r"^acessorios?\b",
    r"^computadores?\b",
    r"^pessoas?\b",
    r"^homens?\b",
)

TOOL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Claude Code", r"\b(?:claude|cloud)\s+code\b"),
    ("Claude", r"\bclaude\b(?!\s+code\b)"),
    ("Notion", r"\bnotion\b"),
    ("Instagram", r"\binstagram\b"),
    ("TikTok", r"\btiktok\b"),
    ("YouTube", r"\byoutube\b"),
    ("Python", r"\bpython\b"),
    ("Swagger", r"\bswagger\b"),
    ("Postman", r"\bpostman\b"),
    ("PactumJS", r"\bpactum\s*js\b|\bpactumjs\b"),
    ("Insomnia", r"\binsomnia\b"),
    ("Newman", r"\bnewman\b"),
    ("Playwright", r"\bplaywright\b"),
    ("Cypress", r"\bcypress\b"),
    ("Selenium", r"\bselenium\b"),
    ("Appium", r"\bappium\b"),
    ("Robot", r"\brobot(?:\s+framework)?\b"),
    ("K6", r"\bk6\b"),
    ("Grafana", r"\bgrafana\b"),
    ("JMeter", r"\bjmeter\b"),
    ("Kibana", r"\bkibana\b"),
    ("Docker", r"\bdocker\b"),
    ("Jenkins", r"\bjenkins\b"),
    ("GitHub Actions", r"\bgithub\s+actions\b"),
    ("GitHub", r"\bgithub\b(?!\s+actions\b)"),
    ("GitLab", r"\bgitlab\b"),
    ("Azure DevOps", r"\bazure\s+devops\b"),
    ("Jira", r"\bjira\b"),
    ("Trello", r"\btrello\b"),
    ("Qase", r"\bqase\b"),
)


def get_evidence_items(result: AnalysisResult) -> list[EvidenceItem]:
    if result.evidence_items:
        return _coerce_evidence_items(result.evidence_items)
    return build_evidence_items(result)


def build_evidence_items(result: AnalysisResult) -> list[EvidenceItem]:
    items: dict[tuple[str, str], EvidenceItem] = {}

    def add(
        *,
        kind: str,
        value: str,
        signal: str,
        confidence: str,
        excerpt: str = "",
        timestamp: float | None = None,
        frame_path: str = "",
    ) -> None:
        clean_value = _clean_value(value)
        if not clean_value:
            return

        key = (kind, _norm(clean_value))
        item = items.get(key)
        support = EvidenceSupport(
            signal=signal,
            confidence=confidence,
            timestamp=timestamp,
            frame_path=frame_path,
            excerpt=compact_text(_clean_excerpt(excerpt), 240),
        )
        if item is None:
            item = EvidenceItem(
                kind=kind,
                value=clean_value,
                confidence=confidence,
                supports=[support],
            )
            items[key] = item
            return

        if _confidence_rank(confidence) > _confidence_rank(item.confidence):
            item.confidence = confidence
        if not _has_support(item.supports, support):
            item.supports.append(support)

    for frame in result.frames or []:
        for name, pattern in TOOL_PATTERNS:
            ocr_excerpt = _match_excerpt(frame.ocr_text, pattern)
            if ocr_excerpt:
                add(
                    kind="tool_or_product",
                    value=name,
                    signal="ocr",
                    confidence="high",
                    timestamp=frame.timestamp,
                    frame_path=frame.image_path,
                    excerpt=ocr_excerpt,
                )

            visual_excerpt = _match_excerpt(frame.visual_note, pattern)
            if visual_excerpt:
                add(
                    kind="tool_or_product",
                    value=name,
                    signal="vision",
                    confidence="medium",
                    timestamp=frame.timestamp,
                    frame_path=frame.image_path,
                    excerpt=visual_excerpt,
                )

    for name, pattern in TOOL_PATTERNS:
        transcript_excerpt = _match_excerpt(result.transcript_text, pattern)
        if transcript_excerpt:
            add(
                kind="tool_or_product",
                value=name,
                signal="transcript",
                confidence="high",
                excerpt=transcript_excerpt,
            )

    metadata_text = _metadata_text(result)
    for name, pattern in TOOL_PATTERNS:
        metadata_excerpt = _match_excerpt(metadata_text, pattern)
        if metadata_excerpt:
            add(
                kind="tool_or_product",
                value=name,
                signal="metadata",
                confidence="medium",
                excerpt=metadata_excerpt,
            )

    for raw_value in result.synthesis.tools_or_products or []:
        synthesis_summary = result.synthesis.summary or ""
        known_names = detect_tool_names(str(raw_value))
        if known_names:
            for name in known_names:
                add(
                    kind="tool_or_product",
                    value=name,
                    signal="synthesis",
                    confidence="low",
                    excerpt=synthesis_summary or "Item citado na sintese estruturada.",
                )
            continue
        if not _should_keep_synthesis_value(str(raw_value)):
            continue
        add(
            kind="tool_or_product",
            value=str(raw_value),
            signal="synthesis",
            confidence="low",
            excerpt=synthesis_summary or "Item citado na sintese estruturada.",
        )

    return sorted(
        items.values(),
        key=lambda item: (
            item.kind,
            -_confidence_rank(item.confidence),
            item.value.lower(),
        ),
    )


def detect_tool_names(text: str) -> list[str]:
    names: list[str] = []
    for name, pattern in TOOL_PATTERNS:
        if re.search(pattern, text or "", re.I):
            names.append(name)
    return _unique_names(names)


def tool_names_from_evidence(items: Iterable[EvidenceItem]) -> list[str]:
    return _unique_names(item.value for item in items if item.kind == "tool_or_product")


def evidence_items_to_dicts(items: Iterable[EvidenceItem]) -> list[dict[str, Any]]:
    return [asdict(item) for item in _coerce_evidence_items(items)]


def render_evidence_item(item: EvidenceItem) -> str:
    supports = "; ".join(_render_support(support) for support in item.supports[:4])
    suffix = f" - {supports}" if supports else ""
    return f"{item.value}: confianca {_human_confidence(item.confidence)}{suffix}"


def _render_support(support: EvidenceSupport) -> str:
    parts = [_human_signal(support.signal)]
    if support.timestamp is not None:
        parts.append(f"em {format_timestamp(support.timestamp)}")
    if support.frame_path:
        parts.append(f"frame `{support.frame_path}`")
    text = " ".join(parts)
    if support.excerpt:
        text += f' ("{compact_text(support.excerpt, 120)}")'
    return text


def _match_excerpt(text: str, pattern: str) -> str:
    raw = text or ""
    match = re.search(pattern, raw, re.I)
    if not match:
        return ""
    start = max(0, match.start() - 80)
    end = min(len(raw), match.end() + 80)
    return raw[start:end]


def _metadata_text(result: AnalysisResult) -> str:
    metadata = result.metadata
    return "\n".join(
        part
        for part in [
            metadata.title,
            metadata.description,
            " ".join(metadata.tags or []),
            " ".join(metadata.categories or []),
        ]
        if part
    )


def _should_keep_synthesis_value(value: str) -> bool:
    clean = _clean_value(value)
    if not clean:
        return False
    lower = clean.lower()
    if any(re.search(pattern, lower, re.I) for pattern in _GENERIC_SYNTHESIS_PATTERNS):
        return False
    if len(clean.split()) > 5:
        return False
    if re.search(r"\b[A-Z0-9]{2,}\b", clean):
        return True
    if re.search(r"[a-z][A-Z]", clean):
        return True
    if re.search(r"\d", clean):
        return True
    tokens = [token for token in re.split(r"\s+", clean) if token.lower() not in {"de", "do", "da"}]
    return bool(tokens) and all(token[:1].isupper() for token in tokens)


def _has_support(supports: list[EvidenceSupport], candidate: EvidenceSupport) -> bool:
    return any(
        support.signal == candidate.signal
        and support.timestamp == candidate.timestamp
        and support.frame_path == candidate.frame_path
        and support.excerpt == candidate.excerpt
        for support in supports
    )


def _coerce_evidence_items(items: Iterable[Any]) -> list[EvidenceItem]:
    result: list[EvidenceItem] = []
    for raw_item in items:
        if isinstance(raw_item, EvidenceItem):
            result.append(
                EvidenceItem(
                    kind=raw_item.kind,
                    value=raw_item.value,
                    confidence=raw_item.confidence,
                    supports=_coerce_supports(raw_item.supports),
                )
            )
            continue
        if not isinstance(raw_item, dict):
            continue
        kind = str(raw_item.get("kind") or "").strip()
        value = str(raw_item.get("value") or "").strip()
        confidence = str(raw_item.get("confidence") or "").strip()
        if not kind or not value:
            continue
        result.append(
            EvidenceItem(
                kind=kind,
                value=value,
                confidence=confidence or "low",
                supports=_coerce_supports(raw_item.get("supports") or []),
            )
        )
    return result


def _coerce_supports(supports: Any) -> list[EvidenceSupport]:
    if isinstance(supports, dict):
        raw_supports: Iterable[Any] = [supports]
    elif isinstance(supports, Iterable) and not isinstance(supports, str):
        raw_supports = supports
    else:
        raw_supports = []

    result: list[EvidenceSupport] = []
    for raw_support in raw_supports:
        if isinstance(raw_support, EvidenceSupport):
            result.append(raw_support)
            continue
        if not isinstance(raw_support, dict):
            continue
        timestamp = raw_support.get("timestamp")
        result.append(
            EvidenceSupport(
                signal=str(raw_support.get("signal") or "").strip(),
                confidence=str(raw_support.get("confidence") or "").strip() or "low",
                timestamp=_coerce_optional_float(timestamp),
                frame_path=str(raw_support.get("frame_path") or "").strip(),
                excerpt=str(raw_support.get("excerpt") or "").strip(),
            )
        )
    return result


def _coerce_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_value(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clean_excerpt(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _confidence_rank(value: str) -> int:
    return _CONFIDENCE_RANK.get(value, 0)


def _human_confidence(value: str) -> str:
    labels = {"high": "alta", "medium": "media", "low": "baixa"}
    return labels.get(value, value)


def _human_signal(value: str) -> str:
    labels = {
        "ocr": "OCR",
        "vision": "visao",
        "transcript": "transcricao",
        "metadata": "metadados",
        "synthesis": "sintese",
    }
    return labels.get(value, value)


def _unique_names(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = _clean_value(item)
        key = _norm(clean)
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result
