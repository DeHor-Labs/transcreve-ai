"""Factory FastAPI do TranscreveAI Web."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .jobs import JobStore, worker_task

_VERSION = "0.1.0"


def _accepts_html(scope: dict[str, object]) -> bool:
    from starlette.datastructures import Headers

    return "text/html" in Headers(scope=scope).get("accept", "")


def create_app(
    out_dir: Path | None = None,
    index_db: str | None = None,
) -> FastAPI:
    _out_dir = out_dir or Path("outputs")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        import asyncio

        job_store = JobStore()
        app.state.job_store = job_store
        app.state.out_dir = _out_dir
        app.state.index_db = index_db
        app.state.version = _VERSION

        task = asyncio.create_task(worker_task(job_store, _out_dir, index_db))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(
        title="TranscreveAI",
        version=_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from .routes.api import router as api_router

    app.include_router(api_router, prefix="/api")

    # Serve frontend/dist se existir (SPA)
    _dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if _dist.is_dir():
        from starlette.exceptions import HTTPException as StarletteHTTPException
        from starlette.staticfiles import StaticFiles

        class SPAStaticFiles(StaticFiles):
            async def get_response(self, path: str, scope: dict[str, object]):  # type: ignore[override]
                try:
                    response = await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code != 404 or scope.get("method") not in {"GET", "HEAD"}:
                        raise
                    if not _accepts_html(scope):
                        raise
                    return await super().get_response("index.html", scope)

                if response.status_code == 404 and scope.get("method") in {"GET", "HEAD"}:
                    if _accepts_html(scope):
                        return await super().get_response("index.html", scope)
                return response

        app.mount("/", SPAStaticFiles(directory=str(_dist), html=True), name="spa")

    return app
