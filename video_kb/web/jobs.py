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
    _sse_subscribers: set[asyncio.Queue[JobProgress | None]] = field(
        default_factory=set,
        repr=False,
    )

    def subscribe(self) -> asyncio.Queue[JobProgress | None]:
        queue: asyncio.Queue[JobProgress | None] = asyncio.Queue()
        self._sse_subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[JobProgress | None]) -> None:
        self._sse_subscribers.discard(queue)

    def publish(self, event: JobProgress | None) -> None:
        for queue in list(self._sse_subscribers):
            queue.put_nowait(event)


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

    def queue_size(self) -> int:
        return self._queue.qsize()


def _client_error_message(exc: Exception) -> str:
    raw = str(exc).strip()
    if not raw:
        return "Falha ao processar o video. Verifique a fonte e tente novamente."
    raw = re.sub(r"https?://\S+", "[url removida]", raw)
    raw = re.sub(r"/tmp/vkb_upload_[\w.-]+", "[upload temporario]", raw)
    return raw[:500]


def _persist_failed_job(job: ActiveJob, index_db: str | None) -> None:
    try:
        from ..index import RunIndex, resolve_index_path
        from ..utils import sha256_file, sha256_url

        source_hash = job.source_hash
        if not source_hash:
            if job.source.lower().startswith(("http://", "https://")):
                source_hash = sha256_url(job.source)
            else:
                source_path = Path(job.source)
                if source_path.is_file():
                    source_hash = sha256_file(source_path)

        if not source_hash:
            return

        with RunIndex(resolve_index_path(index_db)) as idx:
            if idx.get_run(job.job_id) is not None:
                idx.update_run(
                    job.job_id,
                    status="failed",
                    finished_at=job.finished_at or _iso_now(),
                    output_dir=job.output_dir or "",
                    storage_backend=job.storage_backend,
                )
            else:
                idx.register(
                    run_id=job.job_id,
                    source=job.source,
                    source_hash=source_hash,
                    provider=job.provider,
                    ai_mode=job.ai_mode,
                    status="failed",
                    created_at=job.created_at,
                    finished_at=job.finished_at or _iso_now(),
                    output_dir=job.output_dir or "",
                    storage_backend=job.storage_backend,
                )
    except Exception:  # noqa: BLE001
        pass


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
                loop.call_soon_threadsafe(j.publish, event)

            return progress_callback

        options = PipelineOptions(
            out_dir=out_dir,
            ai_mode=job.ai_mode,
            provider_name=job.provider,
            on_progress=make_progress_callback(job),  # type: ignore[call-arg]
            index_db=index_db,
            language=job.language,
            run_id=job.job_id,
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

            job.publish(done_event)
            job.publish(None)  # sentinel

        except Exception as exc:  # noqa: BLE001
            current_pct = job.progress.pct if job.progress else 0
            safe_detail = _client_error_message(exc)
            failed_event = JobProgress(
                step="failed",
                detail=safe_detail,
                pct=current_pct,
                status="failed",
                ts=_iso_now(),
            )
            job.status = "failed"
            job.error = safe_detail
            job.finished_at = _iso_now()
            job.progress = failed_event
            job.progress_history.append(failed_event)
            _persist_failed_job(job, index_db)
            job.publish(failed_event)
            job.publish(None)  # sentinel

        finally:
            # Remove upload temporario se for arquivo /tmp
            if job.source.startswith("/tmp/vkb_upload_"):
                try:
                    Path(job.source).unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
            job_store._queue.task_done()
