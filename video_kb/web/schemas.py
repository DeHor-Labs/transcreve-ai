from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SubmitUrlRequest(BaseModel):
    source: str
    language: str | None = None
    ai_mode: str = "auto"
    provider: str = "openai"


class ProgressEvent(BaseModel):
    step: str
    detail: str
    pct: int
    status: str  # "running" | "completed" | "failed"
    ts: str


class JobSummary(BaseModel):
    job_id: str
    title: str
    source: str
    status: str  # "queued" | "running" | "completed" | "failed"
    created_at: str
    finished_at: str | None
    duration_seconds: float | None
    provider: str
    ai_mode: str
    warnings_count: int
    storage_backend: str
    progress: ProgressEvent | None


class JobDetail(JobSummary):
    output_dir: str | None
    analysis_path: str | None
    markdown_path: str | None
    source_hash: str | None
    progress_history: list[ProgressEvent]


class JobListResponse(BaseModel):
    jobs: list[JobSummary]
    total: int


class DossierResponse(BaseModel):
    job_id: str
    markdown: str
    analysis: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    version: str
    queue_size: int
    active_job: str | None


class SubmitResponse(BaseModel):
    job_id: str
    status: str
    queued_at: str


class ErrorResponse(BaseModel):
    error: str
    message: str


# ---------------------------------------------------------------------------
# Schemas de busca semantica (RAG)
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    run_ids: list[str] | None = None


class SearchResult(BaseModel):
    run_id: str
    title: str
    source_url: str
    chunk_type: str
    excerpt: str
    score: float
    chapter_start: float | None


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchResult]


class AskRequest(BaseModel):
    question: str
    top_k: int = 5
    run_ids: list[str] | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[SearchResult]
