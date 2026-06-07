"""
video_kb.providers.local_provider - Provider offline/gratuito para o transcreve-ai.

Capacidades:
    transcribe  - faster-whisper (modelo configuravel via VIDEO_KB_LOCAL_WHISPER_MODEL)
    embed       - sentence-transformers all-MiniLM-L6-v2
    synthesize  - extracao estatistica local (sem IA, sem rede)

Sem suporte a visao (describe_frame levanta CapabilityNotSupported).

Dependencias opcionais:
    pip install transcreve-ai[local]
    (instala faster-whisper e sentence-transformers)
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..models import FrameObservation, KnowledgeSynthesis, SourceMetadata, TranscriptSegment
from ..utils import compact_text, format_timestamp
from .base import (
    AUDIO_CHUNK_LIMIT_BYTES,
    AIProvider,
    CapabilityNotSupported,
    SynthesisContext,
    TranscribeResult,
)

_DEFAULT_WHISPER_MODEL = os.environ.get("VIDEO_KB_LOCAL_WHISPER_MODEL", "base")


class LocalProvider(AIProvider):
    """
    Provider local/offline: transcricao via faster-whisper, embeddings via
    sentence-transformers e sintese estatistica sem chamadas de rede.
    """

    def __init__(self, whisper_model: str = _DEFAULT_WHISPER_MODEL) -> None:
        self.whisper_model = whisper_model
        self._whisper: Any = None
        self._embedder: Any = None

    # ------------------------------------------------------------------
    # Capacidades
    # ------------------------------------------------------------------

    def capabilities(self) -> set[str]:
        return {"transcribe", "embed", "synthesize"}

    # ------------------------------------------------------------------
    # transcribe
    # ------------------------------------------------------------------

    def _transcribe(
        self,
        audio_path: Path,
        chunks_dir: Path,
        language: str | None,
    ) -> TranscribeResult:
        model = self._get_whisper()

        from ..media import probe_duration, split_audio  # lazy - evita import circular no topo

        if audio_path.stat().st_size > AUDIO_CHUNK_LIMIT_BYTES:
            chunks = split_audio(audio_path, chunks_dir)
        else:
            chunks = [audio_path]

        texts: list[str] = []
        segments: list[TranscriptSegment] = []
        offset = 0.0

        for chunk in chunks:
            chunk_text, chunk_segments = self._transcribe_chunk(model, chunk, offset, language)
            texts.append(chunk_text)
            segments.extend(chunk_segments)
            if len(chunks) > 1:
                offset += _safe_chunk_duration(chunk, fallback=600.0, probe=probe_duration)

        text = "\n".join(part for part in texts if part).strip()
        return TranscribeResult(text=text, segments=segments)

    def _transcribe_chunk(
        self,
        model: Any,
        audio_path: Path,
        offset: float,
        language: str | None,
    ) -> tuple:
        kwargs: dict[str, Any] = {
            "beam_size": 5,
            "word_timestamps": False,
        }
        if language:
            kwargs["language"] = language

        result_segments, _info = model.transcribe(str(audio_path), **kwargs)

        texts: list[str] = []
        segments: list[TranscriptSegment] = []
        for seg in result_segments:
            seg_text = (seg.text or "").strip()
            if seg_text:
                texts.append(seg_text)
                segments.append(
                    TranscriptSegment(
                        start=float(seg.start) + offset,
                        end=float(seg.end) + offset,
                        text=seg_text,
                    )
                )

        full_text = " ".join(texts).strip()
        if not segments and full_text:
            segments.append(TranscriptSegment(start=offset, end=offset, text=full_text))
        return full_text, segments

    def _get_whisper(self) -> Any:
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel  # lazy import
            except ImportError as exc:
                raise ImportError(
                    "faster-whisper nao esta instalado. Execute: pip install transcreve-ai[local]"
                ) from exc
            self._whisper = WhisperModel(self.whisper_model, device="cpu", compute_type="int8")
        return self._whisper

    # ------------------------------------------------------------------
    # describe_frame (nao suportado)
    # ------------------------------------------------------------------

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
    # synthesize (extracao estatistica local, sem IA)
    # ------------------------------------------------------------------

    def _synthesize(self, ctx: SynthesisContext) -> KnowledgeSynthesis:
        transcript = ctx.transcript_text or ""
        metadata = ctx.metadata
        frames = ctx.frames

        raw: dict[str, Any] = {
            "provider": "local",
            "whisper_model": self.whisper_model,
            "transcript_chars": len(transcript),
            "frames_count": len(frames),
            "evidence_profile": ctx.evidence_profile,
        }

        return KnowledgeSynthesis(
            summary=_extract_summary(transcript, metadata),
            chapters=_extract_chapters(transcript, metadata.duration),
            entities=_extract_entities(transcript, frames),
            tools_or_products=_extract_tools_products(transcript, frames),
            claims=_extract_claims(transcript),
            action_items=_extract_action_items(transcript),
            questions=_extract_questions(transcript),
            raw=raw,
        )

    def _complete(self, prompt: str) -> str:
        hits = _extract_rag_hits(prompt)
        if not hits:
            return (
                "Nao encontrei informacao suficiente nos trechos recuperados para "
                "responder com seguranca."
            )

        lines = ["Resposta local baseada nos trechos indexados:"]
        seen_sources: list[str] = []
        for excerpt, title, chunk_type in hits[:5]:
            clean_excerpt = compact_text(excerpt, 260)
            lines.append(f"- {clean_excerpt} ({title}, {chunk_type})")
            if title not in seen_sources:
                seen_sources.append(title)

        if seen_sources:
            lines.append("")
            lines.append("Fontes: " + ", ".join(seen_sources[:5]))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # embed
    # ------------------------------------------------------------------

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_embedder()
        embeddings = model.encode(texts, show_progress_bar=False)
        return [vec.tolist() for vec in embeddings]

    def _get_embedder(self) -> Any:
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer  # lazy import
            except ImportError as exc:
                raise ImportError(
                    "sentence-transformers nao esta instalado. "
                    "Execute: pip install transcreve-ai[local]"
                ) from exc
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._embedder


# ------------------------------------------------------------------
# Funcoes auxiliares de sintese estatistica (sem estado, sem IA)
# ------------------------------------------------------------------

_QUESTION_RE = re.compile(r"[^.!?]*\?")
_SENTENCE_RE = re.compile(r"[^.!?\n]{20,}")

_TOOLS_KEYWORDS = (
    "claude",
    "chatgpt",
    "gemini",
    "gpt",
    "openai",
    "anthropic",
    "midjourney",
    "dall-e",
    "stable diffusion",
    "whisper",
    "python",
    "javascript",
    "typescript",
    "node",
    "react",
    "fastapi",
    "docker",
    "kubernetes",
    "aws",
    "gcp",
    "azure",
    "tiktok",
    "instagram",
    "youtube",
    "twitch",
    "kalodata",
    "kling",
    "runway",
    "pika",
    "heygen",
    "shopify",
    "stripe",
    "vercel",
    "supabase",
)

_ACTION_WORDS = (
    "fazer",
    "criar",
    "instalar",
    "configurar",
    "executar",
    "rodar",
    "baixar",
    "upload",
    "publicar",
    "testar",
    "validar",
    "revisar",
    "implementar",
    "adicionar",
    "remover",
    "atualizar",
    "verificar",
    "acessar",
    "abrir",
    "fechar",
    "salvar",
    "exportar",
    "importar",
)


def _extract_summary(transcript: str, metadata: SourceMetadata) -> str:
    if not transcript.strip():
        title = metadata.title or metadata.source or "Video sem titulo"
        return f"Video: {title}. Transcricao nao disponivel."

    sentences = [s.strip() for s in re.split(r"[.!?]", transcript) if len(s.strip()) > 30]
    if not sentences:
        return compact_text(transcript, 400)

    # Primeiras e ultimas sentencas tendem a ser mais informativas
    selected = sentences[:3]
    if len(sentences) > 6:
        selected += sentences[-2:]

    title = metadata.title or metadata.source or ""
    prefix = (f"Video: {title}. ") if title else ""
    return prefix + " ".join(selected[:4])


def _extract_chapters(
    transcript: str,
    duration_seconds: float | None = None,
) -> list[dict[str, Any]]:
    if not transcript.strip():
        return []

    words = transcript.split()
    total = len(words)
    if total < 100:
        return [{"start": "00:00", "title": "Conteudo completo", "notes": ""}]

    # Divide em blocos de ~25% do texto como capitulos aproximados
    chunk_size = max(50, total // 4)
    chapters: list[dict] = []
    for index in range(0, total, chunk_size):
        if len(chapters) >= 8:
            break
        chunk = " ".join(words[index : index + chunk_size])
        # Pega as primeiras palavras significativas como titulo estimado
        preview = _first_meaningful_sentence(chunk, 80)
        duration = duration_seconds if duration_seconds and duration_seconds > 0 else 600.0
        start_secs = int((index / total) * duration)
        chapters.append(
            {
                "start": format_timestamp(float(start_secs)),
                "title": preview or (f"Parte {len(chapters) + 1}"),
                "notes": "",
            }
        )

    return chapters


def _first_meaningful_sentence(text: str, limit: int) -> str:
    text = text.strip()
    for sentence in re.split(r"[.!?,]", text):
        clean = sentence.strip()
        if len(clean) > 15:
            return clean[:limit].rstrip()
    return text[:limit].rstrip()


def _extract_entities(transcript: str, frames: list[FrameObservation]) -> list[str]:
    combined = transcript + " " + " ".join(f.ocr_text or "" for f in frames)
    # Nomes proprios: sequencias com inicial maiuscula (heuristico leve)
    candidates = re.findall(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})*\b", combined)
    seen: set = set()
    result = []
    for name in candidates:
        key = name.lower()
        if key not in seen and len(name) > 3:
            seen.add(key)
            result.append(name)
        if len(result) >= 20:
            break
    return result


def _extract_tools_products(transcript: str, frames: list[FrameObservation]) -> list[str]:
    combined = (transcript + " " + " ".join(f.ocr_text or "" for f in frames)).lower()
    found = []
    seen: set = set()
    for keyword in _TOOLS_KEYWORDS:
        if keyword in combined and keyword not in seen:
            seen.add(keyword)
            found.append(keyword)
    return found


def _extract_claims(transcript: str) -> list[str]:
    claims = []
    # Sentencas de afirmacao com verbos de fato
    for match in _SENTENCE_RE.finditer(transcript):
        sentence = match.group().strip()
        low = sentence.lower()
        if any(
            word in low
            for word in (
                "e que",
                "porque",
                "portanto",
                "logo",
                "assim",
                "entao",
                "resultado",
                "prova",
                "mostra",
            )
        ):
            trimmed = sentence[:180].rstrip()
            if len(trimmed) > 30:
                claims.append(trimmed)
        if len(claims) >= 10:
            break
    return claims


def _extract_action_items(transcript: str) -> list[str]:
    items = []
    sentences = re.split(r"[.!?\n]", transcript)
    for sentence in sentences:
        low = sentence.lower().strip()
        if any(low.startswith(verb) or (" " + verb + " ") in low for verb in _ACTION_WORDS):
            clean = sentence.strip()[:160].rstrip()
            if len(clean) > 20:
                items.append(clean)
        if len(items) >= 10:
            break
    return items


def _extract_questions(transcript: str) -> list[str]:
    questions = []
    for match in _QUESTION_RE.finditer(transcript):
        question = match.group().strip()
        if len(question) > 15:
            questions.append(question[:200].rstrip())
        if len(questions) >= 10:
            break
    return questions


def _extract_rag_hits(prompt: str) -> list[tuple[str, str, str]]:
    hits: list[tuple[str, str, str]] = []
    pattern = (
        r'^\[\d+\]\s+"(?P<excerpt>.*)"\s+-\s+'
        r"(?P<title>.*)\s+\((?P<kind>[^()]*)\)\s*$"
    )
    for line in prompt.splitlines():
        match = re.match(pattern, line)
        if not match:
            continue
        excerpt = match.group("excerpt").strip()
        title = match.group("title").strip() or "video"
        kind = match.group("kind").strip() or "trecho"
        if excerpt:
            hits.append((excerpt, title, kind))
    return hits


def _safe_chunk_duration(chunk: Path, *, fallback: float, probe: Any) -> float:
    try:
        duration = float(probe(chunk))
    except Exception:  # noqa: BLE001
        return fallback
    return duration if duration > 0 else fallback
