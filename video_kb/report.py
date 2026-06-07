from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import AnalysisResult, FrameObservation, TranscriptSegment
from .utils import compact_text, format_timestamp

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def render_markdown(result: AnalysisResult) -> str:
    metadata = result.metadata
    is_carousel = _is_carousel(result)
    lines: list[str] = []
    lines.append("# %s" % (metadata.title or "Video analysis"))
    lines.append("")
    lines.append(f"- Fonte: `{result.source}`")
    if metadata.webpage_url:
        lines.append(f"- URL: {metadata.webpage_url}")
    if metadata.uploader or metadata.channel:
        lines.append("- Autor/canal: %s" % (metadata.uploader or metadata.channel))
    if is_carousel:
        lines.append("- Tipo: carrossel")
        lines.append(f"- Slides: {_media_count(result)}")
    elif metadata.duration:
        lines.append(f"- Duracao: {format_timestamp(metadata.duration)}")
    upload_date = _format_upload_date(metadata.upload_date)
    if upload_date:
        lines.append(f"- Data de publicacao: {upload_date}")
    lines.append(f"- Run: `{result.run_id}`")
    lines.append("")

    if result.warnings:
        lines.append("## Avisos")
        lines.extend(f"- {warning}" for warning in result.warnings)
        lines.append("")

    evidence_lines = _render_evidence_profile(result.evidence_profile)
    if evidence_lines:
        lines.append("## Evidencias usadas")
        lines.extend(evidence_lines)
        lines.append("")

    if result.synthesis.summary:
        lines.append("## Resumo")
        lines.append(result.synthesis.summary.strip())
        lines.append("")

    chapter_title = "Slides / estrutura" if is_carousel else "Capitulos"
    _append_list(lines, chapter_title, _render_chapters(result.synthesis.chapters, is_carousel))
    _append_list(lines, "Entidades", result.synthesis.entities)
    _append_list(lines, "Ferramentas e produtos", result.synthesis.tools_or_products)
    _append_list(lines, "Claims e ideias importantes", result.synthesis.claims)
    _append_list(lines, "Acoes sugeridas", result.synthesis.action_items)
    _append_list(lines, "Perguntas em aberto", result.synthesis.questions)

    if is_carousel:
        lines.append("## Slides do carrossel")
        slides = _render_carousel_slides(result.frames)
        if slides:
            lines.extend(slides)
        else:
            lines.append("_Nenhum slide extraido._")
    else:
        lines.append("## Linha do tempo multimodal")
        timeline = _render_timeline(result.frames, result.transcript_segments)
        if timeline:
            lines.extend(timeline)
        else:
            lines.append("_Nenhum frame extraido._")
    lines.append("")

    if result.transcript_text:
        lines.append("## Transcricao")
        lines.append(result.transcript_text.strip())
        lines.append("")

    ocr_blocks = _render_ocr_blocks(result.frames, is_carousel)
    ocr_title = "Textos detectados nos slides" if is_carousel else "Textos detectados na tela"
    _append_list(lines, ocr_title, ocr_blocks)

    lines.append("## Arquivos")
    lines.append("- JSON estruturado: `analysis.json`")
    if is_carousel:
        names = ", ".join(f"`{Path(path).name}`" for path in result.media_paths)
        lines.append(f"- Midias do carrossel: {names}")
    else:
        label = "Imagem" if Path(result.media_path).suffix.lower() in _IMAGE_SUFFIXES else "Video"
        lines.append(f"- {label}: `{Path(result.media_path).name}`")
    if result.audio_path:
        lines.append(f"- Audio: `{Path(result.audio_path).name}`")
    frames_label = "Frames dos slides" if is_carousel else "Frames"
    lines.append(f"- {frames_label}: `frames/`")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown(result: AnalysisResult, path: Path) -> None:
    path.write_text(render_markdown(result), encoding="utf-8")


def _append_list(lines: list[str], title: str, items: Iterable) -> None:
    clean_items = [str(item).strip() for item in items if str(item).strip()]
    if not clean_items:
        return
    lines.append(f"## {title}")
    lines.extend(f"- {item}" for item in clean_items)
    lines.append("")


def _is_carousel(result: AnalysisResult) -> bool:
    return result.metadata.media_kind == "carousel" or _media_count(result) > 1


def _media_count(result: AnalysisResult) -> int:
    if result.media_paths:
        return len(result.media_paths)
    return 1 if result.media_path else 0


def _format_upload_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.isdigit() and len(raw) == 8:
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    if raw.isdigit() and len(raw) >= 10:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return raw
    return raw


def _render_evidence_profile(profile: dict[str, Any]) -> list[str]:
    if not profile:
        return []

    primary = str(profile.get("primary_signal") or "").strip()
    speech_raw = profile.get("speech")
    visual_raw = profile.get("visual")
    speech: dict[str, Any] = speech_raw if isinstance(speech_raw, dict) else {}
    visual: dict[str, Any] = visual_raw if isinstance(visual_raw, dict) else {}

    lines: list[str] = []
    if primary:
        lines.append(f"- Sinal principal: {_human_signal(primary)}")

    speech_status = str(speech.get("status") or "").strip()
    if speech_status:
        speech_text = _human_speech_status(speech_status)
        chars = int(speech.get("chars") or 0)
        segments = int(speech.get("segments") or 0)
        if chars or segments:
            speech_text += f" ({segments} segmentos, {chars} caracteres)"
        reason = str(speech.get("reason") or "").strip()
        if reason:
            speech_text += f"; motivo: {reason}"
        lines.append(f"- Fala/transcricao: {speech_text}")

    frames = int(visual.get("frames") or 0)
    ocr_frames = int(visual.get("ocr_frames") or 0)
    visual_note_frames = int(visual.get("visual_note_frames") or 0)
    if frames or ocr_frames or visual_note_frames:
        lines.append(
            "- Visual/OCR: "
            f"{frames} frames, {ocr_frames} com OCR, "
            f"{visual_note_frames} com analise visual"
        )

    return lines


def _human_signal(value: str) -> str:
    labels = {
        "speech+visual": "fala + visual/OCR",
        "speech": "fala",
        "vision": "visao por IA",
        "ocr": "OCR/texto na tela",
        "frames": "frames extraidos",
        "metadata": "metadados",
    }
    return labels.get(value, value)


def _human_speech_status(value: str) -> str:
    labels = {
        "available": "disponivel",
        "empty": "sem fala util detectada",
        "discarded_low_value": "descartada por baixa utilidade",
        "unsupported": "nao suportada pelo provider",
        "not_applicable": "nao aplicavel",
        "not_run": "nao executada",
    }
    return labels.get(value, value)


def _render_chapters(chapters: list[dict], is_carousel: bool = False) -> list[str]:
    rendered = []
    for chapter in chapters:
        start = chapter.get("start", "")
        title = chapter.get("title") or chapter.get("heading") or ""
        notes = chapter.get("notes") or chapter.get("content") or chapter.get("summary") or ""
        if is_carousel and isinstance(start, (int, float)):
            start = _slide_label_from_number(float(start))
        elif isinstance(start, (int, float)):
            start = format_timestamp(float(start))
        text = f"{start} - {title}" if start and title else str(start or title)
        if notes:
            text += f": {notes}" if title else f" - {notes}"
        rendered.append(text)
    return rendered


def _slide_label_from_number(value: float) -> str:
    index = int(value)
    if index < 1:
        index += 1
    return f"Slide {index}"


def _render_carousel_slides(frames: list[FrameObservation]) -> list[str]:
    lines: list[str] = []
    total = len(frames)
    for index, frame in enumerate(frames, start=1):
        parts = []
        if frame.ocr_text:
            parts.append(f"Texto/OCR: {compact_text(frame.ocr_text, 700)}")
        if frame.visual_note:
            parts.append(f"Analise visual: {compact_text(frame.visual_note, 800)}")
        rel_image = Path(frame.image_path)
        lines.append(f"### Slide {index}/{total}")
        lines.append(f"![slide {index}]({rel_image.as_posix()})")
        if not parts:
            parts.append("Slide capturado; sem OCR ou nota visual.")
        lines.extend(f"- {part}" for part in parts)
        lines.append("")
    return lines


def _render_timeline(
    frames: list[FrameObservation],
    segments: list[TranscriptSegment],
) -> list[str]:
    lines: list[str] = []
    for frame in frames:
        parts = []
        speech = _speech_near(segments, frame.timestamp)
        if speech:
            parts.append(f"Fala: {compact_text(speech, 500)}")
        if frame.ocr_text:
            parts.append(f"Tela/OCR: {compact_text(frame.ocr_text, 500)}")
        if frame.visual_note:
            parts.append(f"Visual: {compact_text(frame.visual_note, 700)}")
        rel_image = Path(frame.image_path)
        lines.append(f"### {format_timestamp(frame.timestamp)}")
        lines.append(f"![frame]({rel_image.as_posix()})")
        if not parts:
            parts.append("Frame capturado; sem OCR, fala alinhada ou nota visual.")
        lines.extend(f"- {part}" for part in parts)
        lines.append("")
    return lines


def _render_ocr_blocks(frames: list[FrameObservation], is_carousel: bool) -> list[str]:
    if is_carousel:
        return [
            f"[Slide {index}] {frame.ocr_text}"
            for index, frame in enumerate(frames, start=1)
            if frame.ocr_text
        ]
    return [
        f"[{format_timestamp(frame.timestamp)}] {frame.ocr_text}"
        for frame in frames
        if frame.ocr_text
    ]


def _speech_near(segments: list[TranscriptSegment], timestamp: float, window: float = 6.0) -> str:
    selected = [
        segment.text.strip()
        for segment in segments
        if segment.text
        and segment.start <= timestamp + window
        and segment.end >= timestamp - window
    ]
    return " ".join(selected)
