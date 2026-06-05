from __future__ import annotations

import importlib
import inspect
import os
from typing import Any

from .base import AIProvider

# Mapa nome -> "modulo:NomeClasse" (imports sao lazy via importlib)
_REGISTRY: dict[str, str] = {
    "openai": "video_kb.providers.openai_provider:OpenAIProvider",
    "local": "video_kb.providers.local_provider:LocalProvider",
    "gemini": "video_kb.providers.gemini_provider:GeminiProvider",
    "anthropic": "video_kb.providers.anthropic_provider:AnthropicProvider",
}

_ENV_KEY = "VIDEO_KB_PROVIDER"
_DEFAULT_PROVIDER = "openai"


def register(name: str, module_path: str) -> None:
    """
    Registra um provider externo sem editar este arquivo.

    Uso em pyproject.toml (entry points):
        [project.entry-points."transcreve_ai.providers"]
        meu_provider = "meu_pacote.providers.meu:MinhaClasse"

    Ou em codigo:
        from video_kb.providers.registry import register
        register("meu_provider", "meu_pacote.providers.meu:MinhaClasse")
    """
    _REGISTRY[name] = module_path


def load_provider(
    name: str,
    *,
    vision_model: str = "",
    transcribe_model: str = "",
    language: str | None = None,
) -> AIProvider:
    """
    Importa e instancia o provider pelo nome (lazy import).

    Levanta KeyError se o nome nao estiver registrado.
    Levanta ImportError com dica de instalacao se a dependencia estiver ausente.
    """
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise KeyError(f"Provider '{name}' nao encontrado. Disponiveis: {available}")

    ref = _REGISTRY[name]
    if ":" not in ref:
        raise ImportError(
            f"Provider '{name}' tem referencia invalida '{ref}'. "
            "Use o formato 'modulo:Classe'."
        )
    module_path, class_name = ref.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        hint = _extra_hint(name)
        raise ImportError(
            f"Nao foi possivel importar o provider '{name}' ({ref}). {hint}Erro original: {exc}"
        ) from exc

    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ImportError(
            f"Provider '{name}' aponta para classe inexistente '{class_name}' em '{module_path}'."
        ) from exc

    opts = _constructor_options(
        name,
        vision_model=vision_model,
        transcribe_model=transcribe_model,
        language=language,
    )
    return cls(**_filter_constructor_options(cls, opts))


def resolve_provider_name(cli_provider: str | None = None) -> str:
    """
    Determina o nome do provider seguindo a precedencia:
    1. Argumento CLI --provider (se fornecido e nao vazio)
    2. Variavel de ambiente VIDEO_KB_PROVIDER
    3. Default "openai"
    """
    return cli_provider or os.environ.get(_ENV_KEY) or _DEFAULT_PROVIDER


def _extra_hint(name: str) -> str:
    hints: dict[str, str] = {
        "local": "Instale com: pip install transcreve-ai[local]  ",
        "gemini": "Instale com: pip install transcreve-ai[gemini]  ",
        "anthropic": "Instale com: pip install transcreve-ai[anthropic]  ",
    }
    return hints.get(name, "")


def _constructor_options(
    name: str,
    *,
    vision_model: str,
    transcribe_model: str,
    language: str | None,
) -> dict[str, Any]:
    opts: dict[str, Any] = {}
    _add_option(opts, "language", language)

    if name == "local":
        _add_option(opts, "whisper_model", transcribe_model)
    elif name in {"gemini", "anthropic"}:
        _add_option(opts, "model", vision_model or transcribe_model)
    else:
        _add_option(opts, "vision_model", vision_model)
        _add_option(opts, "transcribe_model", transcribe_model)

    return opts


def _add_option(opts: dict[str, Any], key: str, value: Any) -> None:
    if value:
        opts[key] = value


def _filter_constructor_options(cls: type[Any], opts: dict[str, Any]) -> dict[str, Any]:
    if not opts:
        return {}
    signature = inspect.signature(cls)
    params = signature.parameters
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values()):
        return opts
    return {key: value for key, value in opts.items() if key in params}
