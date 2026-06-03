from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

from ..models import KnowledgeSynthesis, SourceMetadata
from ..utils import compact_text, format_timestamp
from .base import (
    AIProvider,
    CapabilityNotSupported,
    SynthesisContext,
    TranscribeResult,
    extract_json,
    metadata_dict,
    normalize_items,
)

DEFAULT_MODEL = os.environ.get("VIDEO_KB_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

_FASTER_WHISPER_AVAILABLE: bool | None = None


def _check_faster_whisper() -> bool:
    global _FASTER_WHISPER_AVAILABLE
    if _FASTER_WHISPER_AVAILABLE is None:
        try:
            import importlib

            importlib.import_module("faster_whisper")
            _FASTER_WHISPER_AVAILABLE = True
        except ImportError:
            _FASTER_WHISPER_AVAILABLE = False
    return _FASTER_WHISPER_AVAILABLE


class AnthropicProvider(AIProvider):
    """Provider via API Anthropic: visao e sintese. Transcricao delegada ao LocalProvider."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        language: str | None = None,
    ) -> None:
        self.model = model
        self.language = language
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import anthropic  # lazy import
            except ImportError as exc:
                raise ImportError(
                    "Pacote 'anthropic' nao encontrado. "
                    "Instale com: pip install transcreve-ai[anthropic]  "
                    f"Erro original: {exc}"
                ) from exc

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise OSError(
                    "Variavel de ambiente ANTHROPIC_API_KEY nao definida. "
                    "Defina a chave antes de usar o provider 'anthropic'."
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def capabilities(self) -> set[str]:
        caps = {"vision", "synthesize"}
        if _check_faster_whisper():
            caps.add("transcribe")
        return caps

    # ------------------------------------------------------------------
    # transcribe - delegado ao LocalProvider (faster-whisper)
    # ------------------------------------------------------------------
    def _transcribe(
        self,
        audio_path: Path,
        chunks_dir: Path,
        language: str | None,
    ) -> TranscribeResult:
        if not _check_faster_whisper():
            raise CapabilityNotSupported(
                "AnthropicProvider",
                "transcribe",
            )
        try:
            from .local_provider import LocalProvider  # lazy import
        except ImportError as exc:
            raise CapabilityNotSupported(
                "AnthropicProvider",
                "transcribe",
            ) from exc

        local = LocalProvider()
        return local.transcribe(audio_path, chunks_dir, language=language or self.language)

    # ------------------------------------------------------------------
    # vision / describe_frame
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
        data = base64.standard_b64encode(image_path.read_bytes()).decode("ascii")
        response = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": data,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
        block = response.content[0] if response.content else None
        if block is None:
            return ""
        return getattr(block, "text", "") or ""

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
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        block = response.content[0] if response.content else None
        if block is None:
            return "{}"
        return getattr(block, "text", "") or "{}"

    # ------------------------------------------------------------------
    # embed - nao suportado
    # ------------------------------------------------------------------
    def _embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupported("AnthropicProvider", "embed")
