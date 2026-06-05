from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .ai import (
    openai_available,
    select_visual_frames,
    transcript_near,
)
from .downloader import fetch_media
from .index import DuplicateRunError, RunIndex, resolve_index_path
from .media import extract_audio, extract_frames, probe_duration
from .models import AnalysisResult, FrameObservation, KnowledgeSynthesis
from .ocr import choose_language, ocr_image
from .providers import (
    CapabilityNotSupported,
    SynthesisContext,
    load_provider,
    resolve_provider_name,
)
from .report import write_markdown
from .storage import ArtifactPaths, load_storage, resolve_storage_name
from .utils import (
    ensure_dir,
    iso_now,
    now_id,
    sha256_file,
    sha256_url,
    slugify,
    write_json,
)


@dataclass
class PipelineOptions:
    out_dir: Path
    frame_interval: float = 5.0
    max_frames: int = 80
    visual_limit: int = 30
    ai_mode: str = "auto"
    vision_model: str = ""
    transcribe_model: str = ""
    language: str | None = None
    tesseract_lang: str = "por+eng"
    cookies_browser: str | None = None
    cookies: str | None = None
    video_format: str = "bv*+ba/b"
    provider_name: str = ""
    run_id: str = ""
    # --- novas flags de persistencia ---
    force: bool = False
    storage_backend: str = "filesystem"
    index_db: str | None = None
    # --- callback opcional de progresso (web UI) ---
    # Assinatura: on_progress(step: str, detail: str) -> None
    # Default None: comportamento identico ao anterior (so prints)
    on_progress: Callable[[str, str], None] | None = field(default=None, repr=False)


_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _resolve_run_id(source: str, requested_run_id: str = "") -> str:
    if not requested_run_id:
        return f"{now_id()}-{slugify(source)}"

    run_id = requested_run_id.strip()
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "run_id invalido: use apenas letras, numeros, hifen ou underscore, "
            "sem caminhos ou separadores."
        )
    return run_id


def _resolve_run_dir(out_dir: Path, run_id: str) -> Path:
    out_root = ensure_dir(out_dir).resolve()
    run_dir = ensure_dir(out_root / run_id).resolve()
    if not run_dir.is_relative_to(out_root):
        raise ValueError("run_id invalido: diretorio de execucao fora de out_dir.")
    return run_dir


class VideoKnowledgePipeline:
    def __init__(self, options: PipelineOptions):
        self.options = options

    def run(self, source: str) -> AnalysisResult:
        run_id = _resolve_run_id(source, self.options.run_id)
        run_dir = _resolve_run_dir(self.options.out_dir, run_id)

        def _emit(step: str, detail: str) -> None:
            print(detail)
            if self.options.on_progress:
                self.options.on_progress(step, detail)

        # ------------------------------------------------------------------
        # Indice e dedupe - erros sao gracis: nunca derrubam a analise
        # ------------------------------------------------------------------
        index_path = resolve_index_path(self.options.index_db)
        _index_ok = True
        try:
            _index_ctx = RunIndex(index_path)
            _index_ctx._connect()
        except Exception as _exc:  # noqa: BLE001
            _index_ok = False
            _index_ctx = None  # type: ignore[assignment]

        source_is_url = source.lower().startswith(("http://", "https://"))

        # Calcula hash para URLs antes do download (early-exit de dedupe)
        source_hash: str | None = None
        if source_is_url:
            try:
                source_hash = sha256_url(source)
            except Exception:  # noqa: BLE001
                source_hash = None

        # Checagem de dedupe para URLs (antes de baixar)
        if source_hash and _index_ok and not self.options.force:
            try:
                existing = _index_ctx.find_by_hash(source_hash)  # type: ignore[union-attr]
                if existing and existing.get("status") != "failed":
                    if _index_ctx is not None:
                        _index_ctx.close()
                    raise DuplicateRunError(existing)
            except DuplicateRunError:
                raise
            except Exception:  # noqa: BLE001
                pass  # falha no indice nao derruba o pipeline

        # Registro inicial no indice (status="partial") - gracil
        _run_registered = False
        if _index_ok and source_hash:
            try:
                _provider_name_for_index = resolve_provider_name(self.options.provider_name or None)
                _index_ctx.register(  # type: ignore[union-attr]
                    run_id=run_id,
                    source=source,
                    source_hash=source_hash,
                    provider=_provider_name_for_index,
                    ai_mode=self.options.ai_mode,
                    status="partial",
                    created_at=iso_now(),
                    storage_backend=self.options.storage_backend,
                )
                _run_registered = True
            except Exception:  # noqa: BLE001
                pass

        _emit("download", "Baixando ou copiando video...")
        media_path, metadata = fetch_media(
            source,
            run_dir,
            cookies_browser=self.options.cookies_browser,
            cookies=self.options.cookies,
            video_format=self.options.video_format,
        )

        # Para arquivos locais, calcula hash apos download
        if not source_is_url:
            try:
                source_hash = sha256_file(media_path)
            except Exception:  # noqa: BLE001
                source_hash = None

            # Checagem de dedupe para arquivos locais
            if source_hash and _index_ok and not self.options.force:
                try:
                    existing = _index_ctx.find_by_hash(source_hash)  # type: ignore[union-attr]
                    if existing and existing.get("status") != "failed":
                        if _index_ctx is not None:
                            _index_ctx.close()
                        raise DuplicateRunError(existing)
                except DuplicateRunError:
                    raise
                except Exception:  # noqa: BLE001
                    pass

            # Registro inicial para arquivos locais (apos calcular hash)
            if _index_ok and source_hash and not _run_registered:
                try:
                    _provider_name_for_index = resolve_provider_name(
                        self.options.provider_name or None
                    )
                    _index_ctx.register(  # type: ignore[union-attr]
                        run_id=run_id,
                        source=source,
                        source_hash=source_hash,
                        provider=_provider_name_for_index,
                        ai_mode=self.options.ai_mode,
                        status="partial",
                        created_at=iso_now(),
                        storage_backend=self.options.storage_backend,
                    )
                    _run_registered = True
                except Exception:  # noqa: BLE001
                    pass

        warnings = []
        try:
            metadata.duration = metadata.duration or probe_duration(media_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Nao foi possivel ler duracao com ffprobe: {exc}")

        _emit("audio", "Extraindo audio...")
        audio_path = run_dir / "audio.mp3"
        try:
            extract_audio(media_path, audio_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Nao foi possivel extrair audio: {exc}")
            audio_path = None  # type: ignore[assignment]

        _emit("frames", "Extraindo frames...")
        frames_dir = ensure_dir(run_dir / "frames")
        frame_paths = extract_frames(
            media_path,
            frames_dir,
            duration=metadata.duration,
            interval=self.options.frame_interval,
            max_frames=self.options.max_frames,
        )

        _emit("ocr", f"Rodando OCR em {len(frame_paths)} frames...")
        ocr_lang, ocr_warning = choose_language(self.options.tesseract_lang)
        if ocr_warning:
            warnings.append(ocr_warning)
        frames = []
        for frame_path in frame_paths:
            timestamp = _timestamp_from_frame_name(frame_path.name)
            frames.append(
                FrameObservation(
                    timestamp=timestamp,
                    image_path=str(frame_path.relative_to(run_dir)),
                    ocr_text=ocr_image(frame_path, ocr_lang),
                )
            )

        result = AnalysisResult(
            run_id=run_id,
            created_at=iso_now(),
            source=source,
            workdir=str(run_dir),
            media_path=str(media_path.relative_to(run_dir)),
            audio_path=str(audio_path.relative_to(run_dir)) if audio_path else "",
            metadata=metadata,
            frames=frames,
            warnings=warnings,
        )

        provider_name = resolve_provider_name(self.options.provider_name or None)
        use_ai = self._should_use_ai(provider_name)

        if use_ai and audio_path:
            _emit("ai", f"Transcrevendo e descrevendo com IA ({provider_name})...")
            try:
                provider = load_provider(
                    provider_name,
                    vision_model=self.options.vision_model,
                    transcribe_model=self.options.transcribe_model,
                    language=self.options.language,
                )

                # --- transcricao ---
                transcribe_result = provider.transcribe(
                    audio_path,
                    run_dir / "audio_chunks",
                    language=self.options.language,
                )
                result.transcript_text = transcribe_result.text
                result.transcript_segments = transcribe_result.segments

                # --- visao por frame ---
                visual_indexes = select_visual_frames(result.frames, self.options.visual_limit)
                for position, index in enumerate(visual_indexes, start=1):
                    frame = result.frames[index]
                    _emit("ai_frame", f"Frame {position}/{len(visual_indexes)}")
                    frame_path = run_dir / frame.image_path
                    context = transcript_near(result.transcript_segments, frame.timestamp)
                    try:
                        frame.visual_note = provider.describe_frame(
                            frame_path,
                            result.metadata,
                            frame.timestamp,
                            frame.ocr_text,
                            context,
                        )
                    except CapabilityNotSupported as exc:
                        result.warnings.append(
                            f"Visao nao suportada pelo provider '{provider_name}': {exc}"
                        )
                        break  # nao tentar os demais frames

                # --- sintese ---
                ctx = SynthesisContext(
                    metadata=result.metadata,
                    transcript_text=result.transcript_text,
                    frames=result.frames,
                )
                try:
                    result.synthesis = provider.synthesize(ctx)
                except CapabilityNotSupported:
                    if self.options.ai_mode == "full":
                        raise
                    result.warnings.append(
                        f"Sintese nao suportada pelo provider '{provider_name}';"
                        " usando sintese local."
                    )
                    result.synthesis = _local_synthesis(result)

            except Exception as exc:  # noqa: BLE001
                if self.options.ai_mode == "full":
                    raise
                result.warnings.append(
                    f"Camada de IA falhou; artefatos locais foram mantidos: {exc}"
                )
                result.synthesis = _local_synthesis(result)
        else:
            if self.options.ai_mode != "off":
                result.warnings.append(
                    f"Provider '{provider_name}' indisponivel;"
                    " gerando dossie local sem transcricao/visao por IA"
                )
            print("5/6 Gerando sintese local...")  # sem step SSE para este branch
            result.synthesis = _local_synthesis(result)

        _emit("persist", "Salvando analysis.json e knowledge.md...")
        write_json(run_dir / "analysis.json", result.to_dict())
        write_markdown(result, run_dir / "knowledge.md")

        # ------------------------------------------------------------------
        # Storage backend - gracil: falha adiciona warning mas nao aborta
        # ------------------------------------------------------------------
        artifacts = ArtifactPaths(
            analysis_json=run_dir / "analysis.json",
            markdown=run_dir / "knowledge.md",
            frames_dir=frames_dir,
            run_dir=run_dir,
        )
        storage_ref = None
        try:
            # Passa o backend ja resolvido explicitamente (default "filesystem"),
            # em vez de None, para nao deixar VIDEO_KB_STORAGE sobrescrever a
            # escolha que o pipeline ja fez.
            storage_name = resolve_storage_name(self.options.storage_backend or "filesystem")
            backend = load_storage(storage_name)
            storage_ref = backend.save(result, artifacts)
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"Storage backend falhou (artefatos locais mantidos): {exc}")

        # ------------------------------------------------------------------
        # Atualiza registro no indice com status final e paths
        # ------------------------------------------------------------------
        if _index_ok and _run_registered and source_hash:
            try:
                finished_at = datetime.now(timezone.utc).isoformat()
                _index_ctx.update_run(  # type: ignore[union-attr]
                    run_id,
                    status="completed",
                    finished_at=finished_at,
                    title=result.metadata.title or "",
                    duration_seconds=result.metadata.duration or 0.0,
                    warnings_count=len(result.warnings),
                    output_dir=(storage_ref.output_dir if storage_ref else str(run_dir)),
                    analysis_path=(
                        storage_ref.analysis_path if storage_ref else str(run_dir / "analysis.json")
                    ),
                    markdown_path=(
                        storage_ref.markdown_path if storage_ref else str(run_dir / "knowledge.md")
                    ),
                    storage_backend=(storage_ref.backend if storage_ref else "filesystem"),
                )
            except Exception:  # noqa: BLE001
                pass

        if _index_ctx is not None:
            try:
                _index_ctx.close()
            except Exception:  # noqa: BLE001
                pass

        return result

    def _should_use_ai(self, provider_name: str) -> bool:
        if self.options.ai_mode == "off":
            return False
        if self.options.ai_mode == "full":
            return True
        # modo "auto": verifica disponibilidade conforme o provider
        return _provider_available(provider_name)


def _provider_available(provider_name: str) -> bool:
    """Verifica se o provider esta disponivel (chave de API presente ou sem requisito)."""
    if provider_name == "openai":
        return openai_available()
    if provider_name == "local":
        return True  # local nao precisa de API key
    if provider_name == "gemini":
        import os

        return bool(os.environ.get("GOOGLE_API_KEY"))
    if provider_name == "anthropic":
        import os

        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    # provider externo desconhecido - tenta carregar e deixa falhar depois se necessario
    return True


def _timestamp_from_frame_name(name: str) -> float:
    # frame_0001_00010s00.jpg -> 10.00
    marker = name.rsplit("_", 1)[-1].split(".", 1)[0]
    try:
        return float(marker.replace("s", "."))
    except ValueError:
        return 0.0


def _local_synthesis(result: AnalysisResult) -> KnowledgeSynthesis:
    ocr_hits = [frame.ocr_text for frame in result.frames if frame.ocr_text]
    summary_parts = []
    if result.metadata.title:
        summary_parts.append(f"Video: {result.metadata.title}.")
    if result.metadata.description:
        summary_parts.append(result.metadata.description[:500])
    if ocr_hits:
        summary_parts.append(f"OCR encontrou textos em {len(ocr_hits)} frames.")
    if not summary_parts:
        summary_parts.append(
            "Analise local concluida; ative OPENAI_API_KEY"
            " para transcricao e notas visuais completas."
        )

    return KnowledgeSynthesis(
        summary=" ".join(summary_parts),
        chapters=[],
        entities=[],
        tools_or_products=[],
        claims=[],
        action_items=[],
        questions=[],
        raw={"mode": "local"},
    )
