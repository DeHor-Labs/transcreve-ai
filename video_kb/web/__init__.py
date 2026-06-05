"""Modulo web do TranscreveAI - servidor FastAPI com fila de jobs.

Importar `create_app` diretamente nao e necessario para uso da CLI.
O import e feito de forma lazy em `video_kb/cli.py` (subcomando serve).
"""

__all__ = ["create_app"]


def __getattr__(name: str):  # type: ignore[no-untyped-def]
    if name == "create_app":
        from .app import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
