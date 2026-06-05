"""
Registry lazy de backends de armazenamento.

Segue o mesmo padrao do registry de providers (video_kb/providers/registry.py).
"""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import StorageBackend


# ---------------------------------------------------------------------------
# Mapa nome -> "modulo:Classe"
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, str] = {
    "filesystem": "video_kb.storage.filesystem:FilesystemBackend",
    "obsidian": "video_kb.storage.obsidian:ObsidianBackend",
    "notion": "video_kb.storage.notion:NotionBackend",
    "supabase": "video_kb.storage.supabase:SupabaseBackend",
    "s3": "video_kb.storage.s3:S3Backend",
}

_ENV_KEY = "VIDEO_KB_STORAGE"
_DEFAULT_STORAGE = "filesystem"


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------


def register_storage(name: str, module_path: str) -> None:
    """
    Registra um backend externo sem editar este arquivo.

    Uso em pyproject.toml (entry points):
        [project.entry-points."transcreve_ai.storage"]
        meu_backend = "meu_pacote.storage.meu:MinhaClasse"

    Ou em codigo:
        from video_kb.storage.registry import register_storage
        register_storage("meu_backend", "meu_pacote.storage.meu:MinhaClasse")
    """
    _REGISTRY[name] = module_path


def load_storage(name: str, **opts: object) -> StorageBackend:
    """
    Importa e instancia o backend pelo nome (lazy import).

    Levanta KeyError se o nome nao estiver registrado.
    Levanta ImportError com dica de instalacao se a dependencia estiver ausente.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(f"Backend de storage '{name}' nao encontrado. Disponiveis: {available}")

    ref = _REGISTRY[name]
    module_path, class_name = ref.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        hint = _extra_hint(name)
        raise ImportError(
            f"Nao foi possivel importar o backend '{name}' ({ref}). {hint}Erro original: {exc}"
        ) from exc

    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ImportError(
            f"Backend '{name}' aponta para classe inexistente '{class_name}' em '{module_path}'."
        ) from exc

    return cls(**opts)  # type: ignore[return-value]


def resolve_storage_name(cli_flag: str | None = None) -> str:
    """
    Determina o nome do backend seguindo a precedencia:
    1. Argumento cli_flag (flag --storage do CLI)
    2. Variavel de ambiente VIDEO_KB_STORAGE
    3. Default "filesystem"
    """
    return cli_flag or os.environ.get(_ENV_KEY) or _DEFAULT_STORAGE


# ---------------------------------------------------------------------------
# Hints de instalacao
# ---------------------------------------------------------------------------


def _extra_hint(name: str) -> str:
    hints: dict[str, str] = {
        "obsidian": "Instale com: pip install transcreve-ai[obsidian]  ",
        "notion": "Instale com: pip install transcreve-ai[notion]  ",
        "supabase": "Instale com: pip install transcreve-ai[supabase]  ",
        "s3": "Instale com: pip install transcreve-ai[s3]  ",
    }
    return hints.get(name, "")
