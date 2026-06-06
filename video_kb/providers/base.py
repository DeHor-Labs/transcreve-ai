from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import FrameObservation, KnowledgeSynthesis, SourceMetadata, TranscriptSegment

# Limite de tamanho de chunk de audio (24 MB) - compartilhado entre providers
AUDIO_CHUNK_LIMIT_BYTES: int = 24 * 1024 * 1024

# Capacidade declarada por cada provider
Capability = str  # "transcribe" | "vision" | "synthesize" | "embed"


class CapabilityNotSupported(NotImplementedError):
    """Levantada quando um provider nao suporta a operacao solicitada."""

    def __init__(self, provider: str, capability: Capability) -> None:
        self.provider = provider
        self.capability = capability
        super().__init__(
            f"Provider '{provider}' nao suporta '{capability}'. "
            "Providers disponiveis para esta capacidade: veja ProviderRegistry."
        )


class TranscribeResult:
    """Resultado bruto de transcricao."""

    def __init__(self, text: str, segments: list[TranscriptSegment]) -> None:
        self.text = text
        self.segments = segments


class SynthesisContext:
    """Contexto passado ao synthesize()."""

    def __init__(
        self,
        metadata: SourceMetadata,
        transcript_text: str,
        frames: list[FrameObservation],
        media_kind: str | None = None,
    ) -> None:
        self.metadata = metadata
        self.transcript_text = transcript_text
        self.frames = frames
        self.media_kind = media_kind or metadata.media_kind

    @property
    def is_carousel(self) -> bool:
        return self.media_kind == "carousel" and len(self.frames) > 1


class AIProvider(ABC):
    """
    Interface base para todos os providers de IA do transcreve-ai.

    Cada provider declara suas capacidades via capabilities().
    Metodos nao suportados levantam CapabilityNotSupported.
    """

    @abstractmethod
    def capabilities(self) -> set[Capability]:
        """Retorna o conjunto de capacidades suportadas por este provider."""
        ...

    def _require(self, cap: Capability) -> None:
        """Levanta CapabilityNotSupported se `cap` nao estiver em capabilities()."""
        if cap not in self.capabilities():
            raise CapabilityNotSupported(self.__class__.__name__, cap)

    # ------------------------------------------------------------------
    # transcribe
    # ------------------------------------------------------------------
    def transcribe(
        self,
        audio_path: Path,
        chunks_dir: Path,
        language: str | None = None,
    ) -> TranscribeResult:
        """
        Transcreve audio completo. Suporta split automatico para arquivos grandes.

        Levanta CapabilityNotSupported se "transcribe" nao estiver em capabilities().
        """
        self._require("transcribe")
        return self._transcribe(audio_path, chunks_dir, language)

    def _transcribe(
        self,
        audio_path: Path,
        chunks_dir: Path,
        language: str | None,
    ) -> TranscribeResult:
        raise CapabilityNotSupported(self.__class__.__name__, "transcribe")

    # ------------------------------------------------------------------
    # vision / describe_frame
    # ------------------------------------------------------------------
    def describe_frame(
        self,
        image_path: Path,
        metadata: SourceMetadata,
        timestamp: float,
        ocr_text: str,
        transcript_context: str,
    ) -> str:
        """
        Descreve visualmente um frame de video.

        Retorna string com bullets de observacoes (ate 8 items, pt-BR).
        Levanta CapabilityNotSupported se "vision" nao estiver em capabilities().
        """
        self._require("vision")
        return self._describe_frame(image_path, metadata, timestamp, ocr_text, transcript_context)

    def _describe_frame(
        self,
        image_path: Path,
        metadata: SourceMetadata,
        timestamp: float,
        ocr_text: str,
        transcript_context: str,
    ) -> str:
        raise CapabilityNotSupported(self.__class__.__name__, "vision")

    # ------------------------------------------------------------------
    # synthesize
    # ------------------------------------------------------------------
    def synthesize(self, ctx: SynthesisContext) -> KnowledgeSynthesis:
        """
        Consolida transcricao + notas visuais em KnowledgeSynthesis estruturado.

        Levanta CapabilityNotSupported se "synthesize" nao estiver em capabilities().
        """
        self._require("synthesize")
        return self._synthesize(ctx)

    def _synthesize(self, ctx: SynthesisContext) -> KnowledgeSynthesis:
        raise CapabilityNotSupported(self.__class__.__name__, "synthesize")

    def complete(self, prompt: str) -> str:
        """
        Gera texto livre para fluxos RAG/agent a partir de um prompt.

        Providers que suportam "synthesize" podem expor este metodo publico
        para evitar que consumidores dependam de clientes SDK privados.
        """
        self._require("synthesize")
        return self._complete(prompt)

    def _complete(self, prompt: str) -> str:
        raise CapabilityNotSupported(self.__class__.__name__, "synthesize")

    # ------------------------------------------------------------------
    # embed
    # ------------------------------------------------------------------
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Gera embeddings para uma lista de textos.

        Retorna lista de vetores float na mesma ordem dos textos de entrada.
        Levanta CapabilityNotSupported se "embed" nao estiver em capabilities().
        """
        self._require("embed")
        return self._embed(texts)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        raise CapabilityNotSupported(self.__class__.__name__, "embed")


# ------------------------------------------------------------------
# Funcoes auxiliares compartilhadas entre providers (sem estado)
# ------------------------------------------------------------------


def metadata_dict(metadata: SourceMetadata) -> dict[str, Any]:
    """Serializa SourceMetadata em dict para inclusao em prompts de sintese."""
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
        "media_kind": metadata.media_kind,
    }


def extract_json(text: str) -> dict[str, Any]:
    """Parseia JSON tolerante a texto extra, recortando o primeiro objeto valido."""
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


def normalize_items(value: Any) -> list[str]:
    """Normaliza listas heterogeneas (str ou dict) em lista de strings limpas."""
    if not value:
        return []
    items = value if isinstance(value, list) else [value]
    normalized = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("item")
            item_type = item.get("type") or item.get("kind")
            notes = item.get("notes") or item.get("description")
            if not name:
                normalized.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                continue
            text = str(name)
            if item_type:
                text += f" ({item_type})"
            if notes:
                text += f": {notes}"
            normalized.append(text)
        else:
            normalized.append(str(item))
    return [item.strip() for item in normalized if item.strip()]
