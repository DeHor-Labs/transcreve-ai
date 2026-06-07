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

DEFAULT_GEMINI_MODEL = os.environ.get("VIDEO_KB_GEMINI_MODEL", "gemini-1.5-flash")
DEFAULT_EMBED_MODEL = "models/text-embedding-004"


def _resolve_api_key() -> str:
    """Retorna a chave de API do Gemini, priorizando GEMINI_API_KEY sobre GOOGLE_API_KEY."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        raise OSError(
            "Chave de API do Gemini nao encontrada. "
            "Defina a variavel de ambiente GEMINI_API_KEY (ou GOOGLE_API_KEY) "
            "com sua chave obtida em https://aistudio.google.com/app/apikey"
        )
    return key


class GeminiProvider(AIProvider):
    """Provider Google Gemini: transcricao, visao, sintese e embeddings."""

    def __init__(
        self,
        model: str = DEFAULT_GEMINI_MODEL,
        language: str | None = None,
    ) -> None:
        self.model = model
        self.language = language
        self._genai: Any = None

    def _get_genai(self) -> Any:
        """Importa e configura o SDK google-generativeai de forma lazy."""
        if self._genai is None:
            try:
                import google.generativeai as genai  # lazy import
            except ImportError as exc:
                raise ImportError(
                    "SDK google-generativeai nao instalado. "
                    "Instale com: pip install transcreve-ai[gemini]  "
                    f"Erro original: {exc}"
                ) from exc
            genai.configure(api_key=_resolve_api_key())
            self._genai = genai
        return self._genai

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
        from ..media import split_audio  # lazy - evita import circular no topo

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
                offset += 600.0

        text = "\n".join(part for part in texts if part).strip()
        return TranscribeResult(text=text, segments=segments)

    def _transcribe_chunk(
        self,
        audio_path: Path,
        offset: float,
        language: str | None,
    ) -> tuple[str, list[TranscriptSegment]]:
        genai = self._get_genai()

        # Faz upload do audio via Files API do Gemini
        audio_file = genai.upload_file(
            path=str(audio_path),
            mime_type=_mime_type_for_audio(audio_path),
        )

        lang_hint = ""
        if language:
            lang_hint = f" O audio esta em '{language}'."

        prompt = (
            "Transcreva o audio completo a seguir de forma fiel. "
            f"Retorne somente o texto transcrito, sem comentarios adicionais.{lang_hint}"
        )

        model = genai.GenerativeModel(self.model)
        try:
            response = model.generate_content([prompt, audio_file])
        finally:
            # Remove o arquivo temporario da Files API apos uso, mesmo em falha.
            try:
                genai.delete_file(audio_file.name)
            except Exception:  # noqa: BLE001
                pass

        text = (response.text or "").strip()
        segments: list[TranscriptSegment] = []
        if text:
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
        genai = self._get_genai()

        is_carousel = metadata.media_kind == "carousel"
        unit = "slide de carrossel" if is_carousel else "frame de video"
        position = (
            _slide_label(timestamp) if is_carousel else f"Timestamp: {format_timestamp(timestamp)}"
        )
        speech_label = (
            "Trecho de fala associado ao slide" if is_carousel else "Trecho de fala perto do frame"
        )
        prompt = (
            f"Voce esta analisando um {unit} para uma base de conhecimento. "
            "Responda em portugues, de forma compacta, em ate 8 bullets curtos. "
            "Inclua apenas detalhes uteis para busca futura: pessoas, tela, codigo, "
            "produto, interfaces, gestos, textos visiveis, contexto e acoes demonstradas. "
            "Nao use cabecalhos longos.\n\n"
            f"Titulo: {metadata.title or metadata.source}\n"
            f"{position}\n"
            f"OCR local: {compact_text(ocr_text, 1200)}\n"
            f"{speech_label}: {compact_text(transcript_context, 1600)}"
        )

        image_data = _image_inline_data(image_path, genai)
        model = genai.GenerativeModel(self.model)
        response = model.generate_content([prompt, image_data])
        return (response.text or "").strip()

    # ------------------------------------------------------------------
    # synthesize
    # ------------------------------------------------------------------
    def _synthesize(self, ctx: SynthesisContext) -> KnowledgeSynthesis:
        genai = self._get_genai()

        is_carousel = ctx.is_carousel
        frame_notes = "\n".join(
            f"[{_slide_label_at(index, frame.timestamp, is_carousel)}] "
            f"OCR: {compact_text(frame.ocr_text, 600)}\n"
            f"Visual: {compact_text(frame.visual_note, 900)}"
            for index, frame in enumerate(ctx.frames, start=1)
            if frame.ocr_text or frame.visual_note
        )
        structure_instruction = (
            "A origem e um carrossel de imagens. Em chapters, represente a ordem dos slides; "
            "use start como numero do slide (1, 2, 3...) e nao como timestamp. "
            "No summary, descreva o carrossel como sequencia/argumento visual, nao como video.\n\n"
            if is_carousel
            else "chapters deve ser uma lista de objetos com start, title e notes.\n\n"
        )
        prompt = (
            "Transforme a analise multimodal abaixo em JSON para base de conhecimento. "
            "Responda apenas JSON valido com as chaves: summary, chapters, entities, "
            "tools_or_products, claims, action_items, questions. "
            "Se a transcricao estiver vazia, descartada ou marcada como baixa utilidade, "
            "priorize Frames/OCR/visual e deixe claro que a evidencia principal veio da tela. "
            "Nao invente fala ausente.\n\n"
            + structure_instruction
            + "Metadados:\n"
            + json.dumps(metadata_dict(ctx.metadata), ensure_ascii=False, indent=2)
            + "\n\nPerfil de evidencias:\n"
            + json.dumps(ctx.evidence_profile, ensure_ascii=False, indent=2)
            + "\n\nTranscricao:\n"
            + (compact_text(ctx.transcript_text, 20000) or "[sem transcricao util]")
            + ("\n\nSlides/OCR/visual:\n" if is_carousel else "\n\nFrames/OCR/visual:\n")
            + compact_text(frame_notes, 20000)
        )

        model = genai.GenerativeModel(
            self.model,
            generation_config={"response_mime_type": "application/json"},
        )
        response = model.generate_content(prompt)
        text = (response.text or "").strip()
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

    def _complete(self, prompt: str) -> str:
        genai = self._get_genai()
        model = genai.GenerativeModel(self.model)
        response = model.generate_content(prompt)
        return (response.text or "").strip()

    # ------------------------------------------------------------------
    # embed
    # ------------------------------------------------------------------
    def _embed(self, texts: list[str]) -> list[list[float]]:
        genai = self._get_genai()

        results: list[list[float]] = []
        for text in texts:
            response = genai.embed_content(
                model=DEFAULT_EMBED_MODEL,
                content=text,
                task_type="retrieval_document",
            )
            results.append(response["embedding"])
        return results


# ------------------------------------------------------------------
# Funcoes auxiliares de modulo (sem estado)
# ------------------------------------------------------------------


def _mime_type_for_audio(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".m4a": "audio/mp4",
        ".wav": "audio/wav",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".aac": "audio/aac",
    }
    return mapping.get(suffix, "audio/mpeg")


def _image_inline_data(path: Path, genai: Any) -> Any:
    """Retorna objeto PIL Image ou dict inline_data compativel com o SDK."""
    try:
        from PIL import Image  # lazy - PIL pode nao estar instalado

        return Image.open(path)
    except ImportError:
        pass

    # Fallback: dict inline_data aceito pelo SDK
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"mime_type": "image/jpeg", "data": encoded}


def _slide_label(timestamp: float) -> str:
    return f"Slide: {max(1, int(timestamp) + 1)}"


def _slide_label_at(index: int, timestamp: float, is_carousel: bool) -> str:
    if is_carousel:
        return f"Slide {index}"
    return format_timestamp(timestamp)
