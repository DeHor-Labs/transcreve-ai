from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .index import DuplicateRunError, RunIndex, resolve_index_path
from .pipeline import PipelineOptions, VideoKnowledgePipeline
from .sources import SourceProbe, detect_source
from .storage.registry import resolve_storage_name
from .utils import sha256_file, sha256_url


@dataclass
class AgentWorkflowOptions:
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
    storage_backend: str = ""
    force: bool = False
    index_db: str | None = None
    should_index: bool = False
    question: str | None = None
    top_k: int = 5
    index_force: bool = False


@dataclass
class AgentWorkflowResult:
    source: str
    probe: SourceProbe
    run_id: str = ""
    workdir: str = ""
    markdown_path: str = ""
    analysis_path: str = ""
    reused_existing: bool = False
    indexed: bool = False
    indexed_chunks: int = 0
    question: str | None = None
    answer: str | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["probe"] = self.probe.to_dict()
        return data


def run_agent_workflow(source: str, options: AgentWorkflowOptions) -> AgentWorkflowResult:
    probe = detect_source(source)
    if probe.kind == "unknown":
        return AgentWorkflowResult(
            source=source,
            probe=probe,
            warnings=["Fonte nao reconhecida como video/audio processavel."],
        )

    storage_name = resolve_storage_name(options.storage_backend or None)
    pipeline_options = PipelineOptions(
        out_dir=options.out_dir,
        frame_interval=options.frame_interval,
        max_frames=options.max_frames,
        visual_limit=options.visual_limit,
        ai_mode=options.ai_mode,
        vision_model=options.vision_model,
        transcribe_model=options.transcribe_model,
        language=options.language,
        tesseract_lang=options.tesseract_lang,
        cookies_browser=options.cookies_browser,
        cookies=options.cookies,
        video_format=options.video_format,
        provider_name=options.provider_name,
        force=options.force,
        storage_backend=storage_name,
        index_db=options.index_db,
    )

    warnings: list[str] = []
    if probe.requires_cookies and not (options.cookies_browser or options.cookies):
        warnings.append("Fonte pode exigir cookies. Se o download falhar, tente --cookies-browser.")

    try:
        analysis_result = VideoKnowledgePipeline(pipeline_options).run(source)
        result = _result_from_analysis(source, probe, analysis_result, warnings)
    except DuplicateRunError as exc:
        result = _result_from_existing(source, probe, exc.existing, warnings)
    except Exception as exc:  # noqa: BLE001
        failed_run_id = _mark_latest_partial_failed(source, probe, options.index_db)
        failure_warnings = [*warnings, f"Analise falhou: {exc}"]
        if failed_run_id:
            failure_warnings.append(
                f"Run parcial '{failed_run_id}' marcado como failed para nao bloquear retry."
            )
        return AgentWorkflowResult(
            source=source,
            probe=probe,
            warnings=failure_warnings,
        )

    if not result.run_id:
        return result

    if options.question and not options.should_index:
        options.should_index = True

    if options.should_index:
        _index_result(result, options)

    if options.question:
        _answer_question(result, options)
        if not result.answer:
            result.question = options.question
            result.warnings.append("Pergunta solicitada, mas nenhuma resposta foi gerada.")

    return result


def dumps_agent_result(result: AgentWorkflowResult) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)


def _result_from_analysis(
    source: str,
    probe: SourceProbe,
    analysis_result: Any,
    warnings: list[str],
) -> AgentWorkflowResult:
    workdir = Path(str(analysis_result.workdir))
    return AgentWorkflowResult(
        source=source,
        probe=probe,
        run_id=str(analysis_result.run_id),
        workdir=str(workdir),
        markdown_path=str(workdir / "knowledge.md"),
        analysis_path=str(workdir / "analysis.json"),
        warnings=[*warnings, *list(getattr(analysis_result, "warnings", []) or [])],
    )


def _result_from_existing(
    source: str,
    probe: SourceProbe,
    existing: dict[str, Any],
    warnings: list[str],
) -> AgentWorkflowResult:
    run_id = str(existing.get("id") or "")
    output_dir = str(existing.get("output_dir") or "")
    analysis_path = str(existing.get("analysis_path") or "")
    markdown_path = str(existing.get("markdown_path") or "")
    if output_dir:
        workdir = output_dir
        analysis_path = analysis_path or str(Path(output_dir) / "analysis.json")
        markdown_path = markdown_path or str(Path(output_dir) / "knowledge.md")
    else:
        workdir = ""

    existing_warnings = [*warnings, "Run existente reutilizado; use --force para reprocessar."]
    if not analysis_path or not Path(analysis_path).exists():
        existing_warnings.append(
            f"Run existente '{run_id}' nao tem analysis.json disponivel; use --force."
        )

    return AgentWorkflowResult(
        source=source,
        probe=probe,
        run_id=run_id,
        workdir=workdir,
        markdown_path=markdown_path,
        analysis_path=analysis_path,
        reused_existing=True,
        warnings=existing_warnings,
    )


def _index_result(result: AgentWorkflowResult, options: AgentWorkflowOptions) -> None:
    if not result.analysis_path or not Path(result.analysis_path).exists():
        result.warnings.append("Nao foi possivel indexar: analysis.json nao encontrado.")
        return

    try:
        from .embeddings import EmbedNotSupportedError, index_run
        from .embeddings.store import EmbeddingStore
        from .providers import CapabilityNotSupported, load_provider, resolve_provider_name
    except ImportError as exc:
        result.warnings.append(f"Dependencias de RAG ausentes: {exc}")
        return

    provider_name = resolve_provider_name(options.provider_name or None)
    try:
        provider = load_provider(provider_name)
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Erro ao carregar provider '{provider_name}' para index: {exc}")
        return

    if "embed" not in provider.capabilities():
        result.warnings.append(str(EmbedNotSupportedError(provider_name)))
        return

    db_path = resolve_index_path(options.index_db)
    with EmbeddingStore(db_path) as store:
        if store.has_indexed(result.run_id) and not options.index_force:
            result.indexed = True
            result.indexed_chunks = 0
            return

    try:
        analysis = json.loads(Path(result.analysis_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Nao foi possivel ler analysis.json para index: {exc}")
        return

    try:
        count = index_run(
            run_id=result.run_id,
            analysis=analysis,
            provider=provider,
            provider_name=provider_name,
            model_name=_get_embed_model(provider, provider_name),
            db_path=db_path,
            force=options.index_force,
        )
    except CapabilityNotSupported as exc:
        result.warnings.append(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Erro ao indexar run '{result.run_id}': {exc}")
        return

    result.indexed = True
    result.indexed_chunks = count


def _answer_question(result: AgentWorkflowResult, options: AgentWorkflowOptions) -> None:
    if not options.question:
        return
    try:
        from .embeddings.rag import ask
        from .providers import load_provider, resolve_provider_name
    except ImportError as exc:
        result.warnings.append(f"Dependencias de RAG ausentes: {exc}")
        return

    provider_name = resolve_provider_name(options.provider_name or None)
    try:
        provider = load_provider(provider_name)
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Erro ao carregar provider '{provider_name}' para ask: {exc}")
        return

    if "embed" not in provider.capabilities():
        result.warnings.append(f"Provider '{provider_name}' nao suporta embeddings para ask.")
        return

    try:
        rag_result = ask(
            question=options.question,
            embed_provider=provider,
            synth_provider=provider,
            db_path=resolve_index_path(options.index_db),
            top_k=options.top_k,
            run_ids=[result.run_id],
        )
    except Exception as exc:  # noqa: BLE001
        result.question = options.question
        result.warnings.append(f"Erro ao responder pergunta: {exc}")
        return
    result.question = rag_result.question
    result.answer = rag_result.answer
    result.sources = [
        {
            "run_id": hit.run_id,
            "chunk_type": hit.chunk_type,
            "title": hit.title,
            "score": hit.score,
            "excerpt": hit.excerpt,
            "chapter_start": hit.chapter_start,
        }
        for hit in rag_result.sources
    ]


def _get_embed_model(provider: object, provider_name: str) -> str:
    for attr in ("_embed_model", "_embedding_model", "embed_model"):
        val = getattr(provider, attr, None)
        if val and isinstance(val, str):
            return val
    defaults = {
        "openai": "text-embedding-3-small",
        "local": "all-MiniLM-L6-v2",
        "gemini": "text-embedding-004",
    }
    return defaults.get(provider_name, "unknown")


def _mark_latest_partial_failed(
    source: str,
    probe: SourceProbe,
    index_db: str | None,
) -> str:
    try:
        if probe.is_url:
            source_hash = sha256_url(source)
        else:
            source_hash = sha256_file(Path(probe.canonical))
    except Exception:  # noqa: BLE001
        return ""

    try:
        with RunIndex(resolve_index_path(index_db)) as idx:
            existing = idx.find_by_hash(source_hash)
            if not existing or existing.get("status") != "partial":
                return ""
            if existing.get("analysis_path"):
                return ""
            run_id = str(existing.get("id") or "")
            if not run_id:
                return ""
            idx.update_run(run_id, status="failed")
            return run_id
    except Exception:  # noqa: BLE001
        return ""
