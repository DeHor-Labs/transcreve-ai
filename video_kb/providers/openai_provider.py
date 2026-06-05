from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from ..models import KnowledgeSynthesis, SourceMetadata, TranscriptSegment
from ..utils import compact_text, format_timestamp
from .base import (
    AUDIO_CHUNK_LIMIT_BYTES,
    AIProvider,
    SynthesisContext,
    TranscribeResult,
    extract_json,
    metadata_dict,
    normalize_items,
)

DEFAULT_VISION_MODEL = os.environ.get("VIDEO_KB_VISION_MODEL", "gpt-4o-mini")
DEFAULT_TRANSCRIBE_MODEL = os.environ.get("VIDEO_KB_TRANSCRIBE_MODEL", "whisper-1")
DEFAULT_EMBED_MODEL = "text-embedding-3-small"


class OpenAIProvider(AIProvider):
    """Provider OpenAI: transcricao (Whisper), visao, sintese e embeddings."""

    def __init__(
        self,
        vision_model: str = DEFAULT_VISION_MODEL,
        transcribe_model: str = DEFAULT_TRANSCRIBE_MODEL,
        language: str | None = None,
    ) -> None:
        self.vision_model = vision_model
        self.transcribe_model = transcribe_model
        self.language = language
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # lazy import

            self._client = OpenAI()
        return self._client

    def capabilities(self) -> set[str]:
        return {"transcribe", "vision", "synthesize", "embed"}

    # ------------------------------------------------------------------
    # transcribe
    # ------------------------------------------------------------------
    def _transcribe(
        self,
        audio_path: Path,
        chunks_dir: Path,
        language: str | None,
    ) -> TranscribeResult:
        from ..media import probe_duration, split_audio  # lazy - evita import circular no topo

        lang = language or self.language
        if audio_path.stat().st_size > AUDIO_CHUNK_LIMIT_BYTES:
            chunks = split_audio(audio_path, chunks_dir)
        else:
            chunks = [audio_path]

        texts: list[str] = []
        segments: list[TranscriptSegment] = []
        offset = 0.0
        for chunk in chunks:
            chunk_text, chunk_segments = self._transcribe_chunk(chunk, offset, lang)
            texts.append(chunk_text)
            segments.extend(chunk_segments)
            if len(chunks) > 1:
                offset += _safe_chunk_duration(chunk, fallback=600.0, probe=probe_duration)

        text = "\n".join(part for part in texts if part).strip()
        return TranscribeResult(text=text, segments=segments)

    def _transcribe_chunk(
        self,
        audio_path: Path,
        offset: float,
        language: str | None,
    ) -> tuple[str, list[TranscriptSegment]]:
        client = self._get_client()
        kwargs: dict[str, Any] = {"model": self.transcribe_model, "response_format": "verbose_json"}
        if language:
            kwargs["language"] = language
        try:
            with audio_path.open("rb") as handle:
                response = client.audio.transcriptions.create(
                    **kwargs,
                    file=handle,
                    timestamp_granularities=["segment"],
                )
        except TypeError:
            with audio_path.open("rb") as handle:
                response = client.audio.transcriptions.create(**kwargs, file=handle)

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

    # ------------------------------------------------------------------
    # vision
    # ------------------------------------------------------------------
    def _describe_frame(
        self,
        image_path: Path,
        metadata: SourceMetadata,
        timestamp: float,
        ocr_text: str,
        transcript_context: str,
    ) -> str:
        prompt = (
            "Voce esta analisando um frame de video para uma base de conhecimento. "
            "Responda em portugues, de forma compacta, em ate 8 bullets curtos. "
            "Inclua apenas detalhes uteis para busca futura: pessoas, tela, codigo, "
            "produto, interfaces, gestos, textos visiveis, contexto e acoes demonstradas. "
            "Nao use cabecalhos longos.\n\n"
            f"Titulo: {metadata.title or metadata.source}\n"
            f"Timestamp: {format_timestamp(timestamp)}\n"
            f"OCR local: {compact_text(ocr_text, 1200)}\n"
            f"Trecho de fala perto do frame: {compact_text(transcript_context, 1600)}"
        )
        return self._vision_text(prompt, image_path)

    def _vision_text(self, prompt: str, image_path: Path) -> str:
        client = self._get_client()
        data_url = _image_data_url(image_path)
        response = client.chat.completions.create(
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

    # ------------------------------------------------------------------
    # synthesize
    # ------------------------------------------------------------------
    def _synthesize(self, ctx: SynthesisContext) -> KnowledgeSynthesis:
        frame_notes = "\n".join(
            f"[{format_timestamp(frame.timestamp)}] OCR: {compact_text(frame.ocr_text, 600)}\n"
            f"Visual: {compact_text(frame.visual_note, 900)}"
            for frame in ctx.frames
            if frame.ocr_text or frame.visual_note
        )
        prompt = (
            "Transforme a analise multimodal abaixo em JSON para base de conhecimento. "
            "Responda apenas JSON valido com as chaves: summary, chapters, entities, "
            "tools_or_products, claims, action_items, questions. "
            "chapters deve ser uma lista de objetos com start, title e notes.\n\n"
            "Metadados:\n"
            + json.dumps(metadata_dict(ctx.metadata), ensure_ascii=False, indent=2)
            + "\n\nTranscricao:\n"
            + compact_text(ctx.transcript_text, 20000)
            + "\n\nFrames/OCR/visual:\n"
            + compact_text(frame_notes, 20000)
        )
        text = self._text(prompt)
        parsed = extract_json(text)
        return KnowledgeSynthesis(
            summary=str(parsed.get("summary") or text).strip(),
            chapters=list(parsed.get("chapters") or []),
            entities=normalize_items(parsed.get("entities")),
            tools_or_products=normalize_items(parsed.get("tools_or_products")),
            claims=normalize_items(parsed.get("claims")),
            action_items=normalize_items(parsed.get("action_items")),
            questions=normalize_items(parsed.get("questions")),
            raw=parsed if parsed else {"raw_text": text},
        )

    def _text(self, prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.vision_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    def _complete(self, prompt: str) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.vision_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1024,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # embed
    # ------------------------------------------------------------------
    def _embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = client.embeddings.create(
            model=DEFAULT_EMBED_MODEL,
            input=texts,
        )
        # Retorna na ordem dos indices originais
        items = sorted(response.data, key=lambda item: item.index)
        return [item.embedding for item in items]


# ------------------------------------------------------------------
# Funcoes auxiliares de modulo (sem estado)
# ------------------------------------------------------------------


def _image_data_url(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return json.loads(value.json()) if hasattr(value, "json") else {}


def _safe_chunk_duration(chunk: Path, *, fallback: float, probe: Any) -> float:
    try:
        duration = float(probe(chunk))
    except Exception:  # noqa: BLE001
        return fallback
    return duration if duration > 0 else fallback
