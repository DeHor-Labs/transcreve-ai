"""Rotas /api/* do TranscreveAI Web."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from ..jobs import ActiveJob, JobStore
from ..schemas import (
    DossierResponse,
    HealthResponse,
    JobDetail,
    JobListResponse,
    JobSummary,
    ProgressEvent,
)

router = APIRouter()

_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


# ---------------------------------------------------------------------------
# Helpers de conversao
# ---------------------------------------------------------------------------


def _progress_to_schema(p: Any) -> ProgressEvent | None:
    if p is None:
        return None
    return ProgressEvent(
        step=p.step,
        detail=p.detail,
        pct=p.pct,
        status=p.status,
        ts=p.ts,
    )


def _active_job_to_summary(job: ActiveJob) -> JobSummary:
    return JobSummary(
        job_id=job.job_id,
        title=job.title,
        source=job.source,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        duration_seconds=job.duration_seconds,
        provider=job.provider,
        ai_mode=job.ai_mode,
        warnings_count=job.warnings_count,
        storage_backend=job.storage_backend,
        progress=_progress_to_schema(job.progress),
    )


def _active_job_to_detail(job: ActiveJob) -> JobDetail:
    return JobDetail(
        job_id=job.job_id,
        title=job.title,
        source=job.source,
        status=job.status,
        created_at=job.created_at,
        finished_at=job.finished_at,
        duration_seconds=job.duration_seconds,
        provider=job.provider,
        ai_mode=job.ai_mode,
        warnings_count=job.warnings_count,
        storage_backend=job.storage_backend,
        progress=_progress_to_schema(job.progress),
        output_dir=job.output_dir,
        analysis_path=job.analysis_path,
        markdown_path=job.markdown_path,
        source_hash=job.source_hash,
        progress_history=[_progress_to_schema(p) for p in job.progress_history],  # type: ignore[misc]
    )


def _index_run_to_summary(run: dict[str, Any]) -> JobSummary:
    fin = run.get("finished_at") or None
    dur = run.get("duration_seconds")
    return JobSummary(
        job_id=run["id"],
        title=run.get("title") or "",
        source=run.get("source") or "",
        status=run.get("status") or "completed",
        created_at=run.get("created_at") or "",
        finished_at=fin if fin else None,
        duration_seconds=float(dur) if dur else None,
        provider=run.get("provider") or "",
        ai_mode=run.get("ai_mode") or "",
        warnings_count=run.get("warnings_count") or 0,
        storage_backend=run.get("storage_backend") or "filesystem",
        progress=None,
    )


def _index_run_to_detail(run: dict[str, Any]) -> JobDetail:
    fin = run.get("finished_at") or None
    dur = run.get("duration_seconds")
    done_evt = (
        ProgressEvent(
            step="done",
            detail="Analise concluida.",
            pct=100,
            status="completed",
            ts=fin or run.get("created_at") or "",
        )
        if run.get("status") == "completed"
        else None
    )

    return JobDetail(
        job_id=run["id"],
        title=run.get("title") or "",
        source=run.get("source") or "",
        status=run.get("status") or "completed",
        created_at=run.get("created_at") or "",
        finished_at=fin if fin else None,
        duration_seconds=float(dur) if dur else None,
        provider=run.get("provider") or "",
        ai_mode=run.get("ai_mode") or "",
        warnings_count=run.get("warnings_count") or 0,
        storage_backend=run.get("storage_backend") or "filesystem",
        progress=done_evt,
        output_dir=run.get("output_dir") or None,
        analysis_path=run.get("analysis_path") or None,
        markdown_path=run.get("markdown_path") or None,
        source_hash=run.get("source_hash") or None,
        progress_history=[done_evt] if done_evt else [],
    )


def _get_index(request: Request):  # type: ignore[no-untyped-def]
    from ...index import RunIndex, resolve_index_path

    db_path = resolve_index_path(request.app.state.index_db)
    return RunIndex(db_path)


# ---------------------------------------------------------------------------
# POST /api/jobs
# ---------------------------------------------------------------------------


@router.post("/jobs", status_code=202)
async def submit_job(
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> JSONResponse:
    from ...utils import now_id, slugify

    content_type = request.headers.get("content-type", "")

    # --- parse da requisicao ---
    if "multipart/form-data" in content_type:
        form = await request.form()
        file_field = form.get("file")
        if file_field is None or not isinstance(file_field, UploadFile):
            return JSONResponse(
                status_code=422,
                content={"error": "validation", "message": "Campo 'file' obrigatorio no upload."},
            )
        tmp_path = Path(tempfile.gettempdir()) / f"vkb_upload_{uuid.uuid4().hex}.mp4"
        content = await file_field.read()
        tmp_path.write_bytes(content)
        source = str(tmp_path)
        language = form.get("language") or None
        ai_mode = str(form.get("ai_mode") or "auto")
        provider = str(form.get("provider") or "openai")
    else:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=422,
                content={"error": "validation", "message": "Body JSON invalido."},
            )
        source = body.get("source", "").strip()
        if not source:
            return JSONResponse(
                status_code=422,
                content={
                    "error": "validation",
                    "message": "Campo 'source' obrigatorio quando nao ha arquivo anexado.",
                },
            )
        language = body.get("language") or None
        ai_mode = body.get("ai_mode") or "auto"
        provider = body.get("provider") or "openai"

    # --- dedupe por source_hash para URLs ---
    if source.startswith("http://") or source.startswith("https://"):
        try:
            from ...index import RunIndex, resolve_index_path
            from ...utils import sha256_url

            source_hash = sha256_url(source)
            db_path = resolve_index_path(request.app.state.index_db)
            with RunIndex(db_path) as idx:
                existing = idx.find_by_hash(source_hash)
            if existing and existing.get("status") != "failed":
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": "duplicate",
                        "message": "Esse video ja foi analisado.",
                        "existing_run_id": existing["id"],
                    },
                )
        except Exception:  # noqa: BLE001
            pass  # dedupe gracil: nao bloqueia o envio

    job_id = f"{now_id()}-{slugify(source)}"

    job_store.submit(
        job_id=job_id,
        source=source,
        provider=provider,
        ai_mode=ai_mode,
        language=language,
    )

    job = job_store.get(job_id)
    queued_at = job.created_at if job else ""

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued", "queued_at": queued_at},
    )


# ---------------------------------------------------------------------------
# GET /api/jobs
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    request: Request,
    limit: int = 50,
    status: str | None = None,
    job_store: JobStore = Depends(get_job_store),
) -> JobListResponse:
    active_ids = {j.job_id for j in job_store.list_active()}
    jobs: list[JobSummary] = []

    # Jobs ativos em memoria
    for job in job_store.list_active():
        if status is None or job.status == status:
            jobs.append(_active_job_to_summary(job))

    # Jobs historicos do RunIndex (excluindo os que ja estao na memoria)
    if status is None or status in ("completed", "failed"):
        try:
            from ...index import RunIndex, resolve_index_path

            db_path = resolve_index_path(request.app.state.index_db)
            with RunIndex(db_path) as idx:
                runs = idx.list_runs(limit=limit)
            for run in runs:
                if run["id"] not in active_ids:
                    if status is None or run.get("status") == status:
                        jobs.append(_index_run_to_summary(run))
        except Exception:  # noqa: BLE001
            pass

    # Ordena por created_at desc e aplica limite
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    jobs = jobs[:limit]

    return JobListResponse(jobs=jobs, total=len(jobs))


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobDetail)
def get_job(
    job_id: str,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> JobDetail:
    job = job_store.get(job_id)
    if job is not None:
        return _active_job_to_detail(job)

    # Tenta no RunIndex
    try:
        from ...index import RunIndex, resolve_index_path

        db_path = resolve_index_path(request.app.state.index_db)
        with RunIndex(db_path) as idx:
            run = idx.get_run(job_id)
        if run is not None:
            return _index_run_to_detail(run)
    except Exception:  # noqa: BLE001
        pass

    raise HTTPException(
        status_code=404, detail={"error": "not_found", "message": "Job nao encontrado."}
    )


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/events  (SSE)
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> Any:
    from sse_starlette.sse import EventSourceResponse

    job = job_store.get(job_id)

    # Job historico do RunIndex - envia evento final imediatamente
    if job is None:
        try:
            from ...index import RunIndex, resolve_index_path

            db_path = resolve_index_path(request.app.state.index_db)
            with RunIndex(db_path) as idx:
                run = idx.get_run(job_id)
            if run is not None:
                status = run.get("status", "completed")
                step = "done" if status == "completed" else "failed"
                detail = "Analise concluida." if step == "done" else (run.get("error") or "Falha.")
                pct = 100 if step == "done" else 0
                evt_status = "completed" if step == "done" else "failed"
                ts = run.get("finished_at") or run.get("created_at") or ""

                async def _history_gen():  # type: ignore[return]
                    payload = json.dumps(
                        {"step": step, "detail": detail, "pct": pct, "status": evt_status, "ts": ts}
                    )
                    yield {"data": payload}

                return EventSourceResponse(_history_gen())
        except Exception:  # noqa: BLE001
            pass

        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "Job nao encontrado."},
        )

    async def _sse_generator():  # type: ignore[return]
        # Drena historico (reconexao)
        for event in list(job.progress_history):
            yield {"data": event.model_dump_json()}

        if job.status in ("completed", "failed"):
            return

        # Escuta eventos novos
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await job._sse_queue.get()
            except Exception:  # noqa: BLE001
                break
            if event is None:
                break
            yield {"data": event.model_dump_json()}
            if event.step in ("done", "failed"):
                break

    return EventSourceResponse(_sse_generator())


# ---------------------------------------------------------------------------
# GET /api/jobs/{job_id}/dossier
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/dossier", response_model=DossierResponse)
def get_dossier(
    job_id: str,
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> DossierResponse:
    # Determina paths de saida
    output_dir: str | None = None
    status: str = "unknown"

    job = job_store.get(job_id)
    if job is not None:
        status = job.status
        output_dir = job.output_dir
    else:
        try:
            from ...index import RunIndex, resolve_index_path

            db_path = resolve_index_path(request.app.state.index_db)
            with RunIndex(db_path) as idx:
                run = idx.get_run(job_id)
            if run is not None:
                status = run.get("status") or "unknown"
                output_dir = run.get("output_dir") or None
            else:
                raise HTTPException(
                    status_code=404,
                    detail={"error": "not_found", "message": "Job nao encontrado."},
                )
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001
            raise HTTPException(
                status_code=404,
                detail={"error": "not_found", "message": "Job nao encontrado."},
            )

    if status != "completed":
        raise HTTPException(
            status_code=409,
            detail={"error": "not_ready", "message": f"Job ainda nao concluido. Status: {status}"},
        )

    if not output_dir:
        raise HTTPException(
            status_code=409,
            detail={"error": "not_ready", "message": "Output dir nao disponivel."},
        )

    md_path = Path(output_dir) / "knowledge.md"
    json_path = Path(output_dir) / "analysis.json"

    try:
        markdown_text = md_path.read_text(encoding="utf-8")
    except Exception:
        markdown_text = ""

    try:
        analysis_data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        analysis_data = {}

    # Adapta o payload ao contrato consumido pelo frontend: expoe frames_count
    # e remove as colecoes pesadas (frames com OCR, segmentos) que nao sao usadas
    # na renderizacao do dossie e inflariam a resposta.
    if isinstance(analysis_data, dict):
        frames = analysis_data.pop("frames", [])
        analysis_data.pop("transcript_segments", None)
        analysis_data["frames_count"] = len(frames) if isinstance(frames, list) else 0

    return DossierResponse(
        job_id=job_id,
        markdown=markdown_text,
        analysis=analysis_data,
    )


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health(
    request: Request,
    job_store: JobStore = Depends(get_job_store),
) -> HealthResponse:
    running = [j for j in job_store.list_active() if j.status == "running"]
    active_job = running[0].job_id if running else None
    queue_size = job_store._queue.qsize()

    return HealthResponse(
        status="ok",
        version=request.app.state.version,
        queue_size=queue_size,
        active_job=active_job,
    )
