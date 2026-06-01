import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .media import split_audio
from .models import FrameObservation, KnowledgeSynthesis, SourceMetadata, TranscriptSegment
from .utils import compact_text, format_timestamp


DEFAULT_VISION_MODEL = os.environ.get("VIDEO_KB_VISION_MODEL", "gpt-4o-mini")
DEFAULT_TRANSCRIBE_MODEL = os.environ.get("VIDEO_KB_TRANSCRIBE_MODEL", "whisper-1")


def openai_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


class OpenAIAnalyzer:
    def __init__(
        self,
        vision_model: str = DEFAULT_VISION_MODEL,
        transcribe_model: str = DEFAULT_TRANSCRIBE_MODEL,
        language: Optional[str] = None,
    ):
        from openai import OpenAI

        self.client = OpenAI()
        self.vision_model = vision_model
        self.transcribe_model = transcribe_model
        self.language = language

    def transcribe_audio(self, audio_path: Path, chunks_dir: Path) -> Tuple[str, List[TranscriptSegment]]:
        if audio_path.stat().st_size > 24 * 1024 * 1024:
            chunks = split_audio(audio_path, chunks_dir)
        else:
            chunks = [audio_path]

        texts: List[str] = []
        segments: List[TranscriptSegment] = []
        offset = 0.0
        for chunk in chunks:
            chunk_text, chunk_segments = self._transcribe_chunk(chunk, offset)
            texts.append(chunk_text)
            segments.extend(chunk_segments)
            if len(chunks) > 1:
                offset += 600.0
        return "\n".join(part for part in texts if part).strip(), segments

    def _transcribe_chunk(self, audio_path: Path, offset: float) -> Tuple[str, List[TranscriptSegment]]:
        kwargs: Dict[str, Any] = {
            "model": self.transcribe_model,
            "file": audio_path.open("rb"),
            "response_format": "verbose_json",
        }
        if self.language:
            kwargs["language"] = self.language
        try:
            kwargs["timestamp_granularities"] = ["segment"]
            response = self.client.audio.transcriptions.create(**kwargs)
        except TypeError:
            kwargs.pop("timestamp_granularities", None)
            response = self.client.audio.transcriptions.create(**kwargs)
        finally:
            kwargs["file"].close()

        payload = _model_to_dict(response)
        text = payload.get("text") or getattr(response, "text", "") or ""
        segments = []
        for item in payload.get("segments") or []:
            segments.append(
                TranscriptSegment(
                    start=float(item.get("start") or 0) + offset,
                    end=float(item.get("end") or 0) + offset,
                    text=item.get("text") or "",
                )
            )
        if not segments and text:
            segments.append(TranscriptSegment(start=offset, end=offset, text=text))
        return text, segments

    def describe_frame(
        self,
        image_path: Path,
        metadata: SourceMetadata,
        timestamp: float,
        ocr_text: str,
        transcript_context: str,
    ) -> str:
        prompt = (
            "Voce esta analisando um frame de video para uma base de conhecimento. "
            "Anote objetivamente tudo que for util: pessoas, tela, codigo, produto, "
            "interfaces, gestos, textos visiveis, contexto e qualquer detalhe que "
            "ajude alguem a recuperar essa informacao depois.\n\n"
            "Titulo: %s\nTimestamp: %s\nOCR local: %s\nTrecho de fala perto do frame: %s"
            % (
                metadata.title or metadata.source,
                format_timestamp(timestamp),
                compact_text(ocr_text, 1200),
                compact_text(transcript_context, 1600),
            )
        )
        return self._vision_text(prompt, image_path)

    def synthesize(
        self,
        metadata: SourceMetadata,
        transcript_text: str,
        frames: List[FrameObservation],
    ) -> KnowledgeSynthesis:
        frame_notes = "\n".join(
            "[%s] OCR: %s\nVisual: %s"
            % (
                format_timestamp(frame.timestamp),
                compact_text(frame.ocr_text, 600),
                compact_text(frame.visual_note, 900),
            )
            for frame in frames
            if frame.ocr_text or frame.visual_note
        )
        prompt = (
            "Transforme a analise multimodal abaixo em JSON para base de conhecimento. "
            "Responda apenas JSON valido com as chaves: summary, chapters, entities, "
            "tools_or_products, claims, action_items, questions. "
            "chapters deve ser uma lista de objetos com start, title e notes.\n\n"
            "Metadados:\n%s\n\nTranscricao:\n%s\n\nFrames/OCR/visual:\n%s"
            % (
                json.dumps(_metadata_dict(metadata), ensure_ascii=False, indent=2),
                compact_text(transcript_text, 20000),
                compact_text(frame_notes, 20000),
            )
        )
        text = self._text(prompt)
        parsed = _extract_json(text)
        return KnowledgeSynthesis(
            summary=str(parsed.get("summary") or text).strip(),
            chapters=list(parsed.get("chapters") or []),
            entities=[str(item) for item in parsed.get("entities") or []],
            tools_or_products=[str(item) for item in parsed.get("tools_or_products") or []],
            claims=[str(item) for item in parsed.get("claims") or []],
            action_items=[str(item) for item in parsed.get("action_items") or []],
            questions=[str(item) for item in parsed.get("questions") or []],
            raw=parsed if parsed else {"raw_text": text},
        )

    def _vision_text(self, prompt: str, image_path: Path) -> str:
        data_url = _image_data_url(image_path)
        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "low"},
                        },
                    ],
                }
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content or ""

    def _text(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"


def select_visual_frames(frames: List[FrameObservation], limit: int) -> List[int]:
    if limit <= 0 or len(frames) <= limit:
        return list(range(len(frames)))
    if limit == 1:
        return [0]
    step = (len(frames) - 1) / float(limit - 1)
    selected = []
    seen = set()
    for index in range(limit):
        pos = int(round(index * step))
        if pos not in seen:
            selected.append(pos)
            seen.add(pos)
    return selected


def transcript_near(segments: Iterable[TranscriptSegment], timestamp: float, window: float = 8.0) -> str:
    selected = [
        segment.text.strip()
        for segment in segments
        if segment.text and segment.start <= timestamp + window and segment.end >= timestamp - window
    ]
    return " ".join(selected)


def _image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return "data:image/jpeg;base64,%s" % encoded


def _metadata_dict(metadata: SourceMetadata) -> Dict[str, Any]:
    return {
        "source": metadata.source,
        "title": metadata.title,
        "webpage_url": metadata.webpage_url,
        "extractor": metadata.extractor,
        "uploader": metadata.uploader,
        "channel": metadata.channel,
        "duration": metadata.duration,
        "upload_date": metadata.upload_date,
        "description": metadata.description,
        "tags": metadata.tags,
        "categories": metadata.categories,
    }


def _model_to_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return json.loads(value.json()) if hasattr(value, "json") else {}


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}
