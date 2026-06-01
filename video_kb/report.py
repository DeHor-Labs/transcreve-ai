from pathlib import Path
from typing import Iterable, List

from .models import AnalysisResult, FrameObservation, TranscriptSegment
from .utils import compact_text, format_timestamp


def render_markdown(result: AnalysisResult) -> str:
    metadata = result.metadata
    lines: List[str] = []
    lines.append("# %s" % (metadata.title or "Video analysis"))
    lines.append("")
    lines.append("- Fonte: `%s`" % result.source)
    if metadata.webpage_url:
        lines.append("- URL: %s" % metadata.webpage_url)
    if metadata.uploader or metadata.channel:
        lines.append("- Autor/canal: %s" % (metadata.uploader or metadata.channel))
    if metadata.duration:
        lines.append("- Duracao: %s" % format_timestamp(metadata.duration))
    if metadata.upload_date:
        lines.append("- Data de upload: %s" % metadata.upload_date)
    lines.append("- Run: `%s`" % result.run_id)
    lines.append("")

    if result.warnings:
        lines.append("## Avisos")
        lines.extend("- %s" % warning for warning in result.warnings)
        lines.append("")

    if result.synthesis.summary:
        lines.append("## Resumo")
        lines.append(result.synthesis.summary.strip())
        lines.append("")

    _append_list(lines, "Capitulos", _render_chapters(result.synthesis.chapters))
    _append_list(lines, "Entidades", result.synthesis.entities)
    _append_list(lines, "Ferramentas e produtos", result.synthesis.tools_or_products)
    _append_list(lines, "Claims e ideias importantes", result.synthesis.claims)
    _append_list(lines, "Acoes sugeridas", result.synthesis.action_items)
    _append_list(lines, "Perguntas em aberto", result.synthesis.questions)

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

    ocr_blocks = [
        "[%s] %s" % (format_timestamp(frame.timestamp), frame.ocr_text)
        for frame in result.frames
        if frame.ocr_text
    ]
    _append_list(lines, "Textos detectados na tela", ocr_blocks)

    lines.append("## Arquivos")
    lines.append("- JSON estruturado: `analysis.json`")
    lines.append("- Video: `%s`" % Path(result.media_path).name)
    if result.audio_path:
        lines.append("- Audio: `%s`" % Path(result.audio_path).name)
    lines.append("- Frames: `frames/`")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown(result: AnalysisResult, path: Path) -> None:
    path.write_text(render_markdown(result), encoding="utf-8")


def _append_list(lines: List[str], title: str, items: Iterable) -> None:
    clean_items = [str(item).strip() for item in items if str(item).strip()]
    if not clean_items:
        return
    lines.append("## %s" % title)
    lines.extend("- %s" % item for item in clean_items)
    lines.append("")


def _render_chapters(chapters: List[dict]) -> List[str]:
    rendered = []
    for chapter in chapters:
        start = chapter.get("start", "")
        title = chapter.get("title", "")
        notes = chapter.get("notes", "")
        if isinstance(start, (int, float)):
            start = format_timestamp(float(start))
        text = "%s - %s" % (start, title) if start else str(title)
        if notes:
            text += ": %s" % notes
        rendered.append(text)
    return rendered


def _render_timeline(
    frames: List[FrameObservation],
    segments: List[TranscriptSegment],
) -> List[str]:
    lines: List[str] = []
    for frame in frames:
        parts = []
        speech = _speech_near(segments, frame.timestamp)
        if speech:
            parts.append("Fala: %s" % compact_text(speech, 500))
        if frame.ocr_text:
            parts.append("Tela/OCR: %s" % compact_text(frame.ocr_text, 500))
        if frame.visual_note:
            parts.append("Visual: %s" % compact_text(frame.visual_note, 700))
        rel_image = Path(frame.image_path)
        lines.append("### %s" % format_timestamp(frame.timestamp))
        lines.append("![frame](%s)" % rel_image.as_posix())
        if not parts:
            parts.append("Frame capturado; sem OCR, fala alinhada ou nota visual.")
        lines.extend("- %s" % part for part in parts)
        lines.append("")
    return lines


def _speech_near(segments: List[TranscriptSegment], timestamp: float, window: float = 6.0) -> str:
    selected = [
        segment.text.strip()
        for segment in segments
        if segment.text and segment.start <= timestamp + window and segment.end >= timestamp - window
    ]
    return " ".join(selected)
