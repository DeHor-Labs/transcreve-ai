from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# ProgressEvent (Pydantic para serializar via SSE)
# ---------------------------------------------------------------------------


class JobProgress(BaseModel):
    step: str
    detail: str
    pct: int
    status: str  # "running" | "completed" | "failed"
    ts: str


# ---------------------------------------------------------------------------
# Mapeamento step -> pct fixo (contrato compartilhado)
# ---------------------------------------------------------------------------

_STEP_PCT: dict[str, int] = {
    "download": 10,
    "audio": 20,
    "frames": 30,
    "ocr": 40,
    "ai": 50,
    "persist": 90,
    "done": 100,
}

_AI_FRAME_RE = re.compile(r"Frame\s+(\d+)/(\d+)", re.IGNORECASE)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_progress_event(step: str, detail: str) -> JobProgress:
    if step == "ai_frame":
        m = _AI_FRAME_RE.search(detail)
        if m:
            position = int(m.group(1))
            total = int(m.group(2))
            pct = 51 + int((position / total) * 18)
        else:
            pct = 55
    else:
        pct = _STEP_PCT.get(step, 0)

    if step == "done":
        status = "completed"
    elif step == "failed":
        status = "failed"
    else:
        status = "running"

    return JobProgress(step=step, detail=detail, pct=pct, status=status, ts=_iso_now())


# ---------------------------------------------------------------------------
# ActiveJob
# ---------------------------------------------------------------------------


@dataclass
class ActiveJob:
    job_id: str
    source: str
    status: str  # "queued" | "running" | "completed" | "failed"
    created_at: str
    provider: str
    ai_mode: str
    progress: JobProgress | None = None
    progress_history: list[JobProgress] = field(default_factory=list)
    error: str | None = None
    finished_at: str | None = None
    title: str = ""
    duration_seconds: float | None = None
    warnings_count: int = 0
    storage_backend: str = "filesystem"
    output_dir: str | None = None
    analysis_path: str | None = None
    markdown_path: str | None = None
    source_hash: str | None = None
    language: str | None = None
    _sse_queue: asyncio.Queue = field(default_factory=asyncio.Queue)  # type: ignore[type-arg]


# ---------------------------------------------------------------------------
# JobStore
# ---------------------------------------------------------------------------


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ActiveJob] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    def submit(self, job_id: str, source: str, **kwargs: Any) -> ActiveJob:
        job = ActiveJob(
            job_id=job_id,
            source=source,
            status="queued",
            created_at=_iso_now(),
            **kwargs,
        )
        self._jobs[job_id] = job
        self._queue.put_nowait(job_id)
        return job

    def get(self, job_id: str) -> ActiveJob | None:
        return self._jobs.get(job_id)

    def list_active(self) -> list[ActiveJob]:
        return list(self._jobs.values())


# ---------------------------------------------------------------------------
# Worker asyncio
# ---------------------------------------------------------------------------


async def worker_task(
    job_store: JobStore,
    out_dir: Path,
    index_db: str | None,
) -> None:
    from ..pipeline import PipelineOptions, VideoKnowledgePipeline

    loop = asyncio.get_running_loop()

    while True:
        job_id = await job_store._queue.get()
        job = job_store._jobs.get(job_id)
        if job is None:
            job_store._queue.task_done()
            continue

        job.status = "running"

        def make_progress_callback(j: ActiveJob) -> Callable[[str, str], None]:
            def progress_callback(step: str, detail: str) -> None:
                event = build_progress_event(step, detail)
                j.progress = event
                j.progress_history.append(event)
                loop.call_soon_threadsafe(j._sse_queue.put_nowait, event)

            return progress_callback

        options = PipelineOptions(
            out_dir=out_dir,
            ai_mode=job.ai_mode,
            provider_name=job.provider,
            on_progress=make_progress_callback(job),  # type: ignore[call-arg]
            index_db=index_db,
            language=job.language,
        )
        pipeline = VideoKnowledgePipeline(options)

        try:
            result = await loop.run_in_executor(None, pipeline.run, job.source)

            done_event = build_progress_event("done", "Analise concluida.")
            job.status = "completed"
            job.finished_at = _iso_now()
            job.progress = done_event
            job.progress_history.append(done_event)

            # Preenche campos de resultado
            job.title = (result.metadata.title or "") if result.metadata else ""
            job.duration_seconds = (result.metadata.duration or None) if result.metadata else None
            job.warnings_count = len(result.warnings)
            job.output_dir = result.workdir
            job.analysis_path = str(Path(result.workdir) / "analysis.json")
            job.markdown_path = str(Path(result.workdir) / "knowledge.md")

            loop.call_soon_threadsafe(job._sse_queue.put_nowait, done_event)
            loop.call_soon_threadsafe(job._sse_queue.put_nowait, None)  # sentinel

        except Exception as exc:  # noqa: BLE001
            current_pct = job.progress.pct if job.progress else 0
            failed_event = JobProgress(
                step="failed",
                detail=str(exc),
                pct=current_pct,
                status="failed",
                ts=_iso_now(),
            )
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = _iso_now()
            job.progress = failed_event
            job.progress_history.append(failed_event)
            loop.call_soon_threadsafe(job._sse_queue.put_nowait, failed_event)
            loop.call_soon_threadsafe(job._sse_queue.put_nowait, None)  # sentinel

        finally:
            # Remove upload temporario se for arquivo /tmp
            if job.source.startswith("/tmp/vkb_upload_"):
                try:
                    Path(job.source).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            job_store._queue.task_done()
