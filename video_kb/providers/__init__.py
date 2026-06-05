"""
video_kb.providers - Abstracao de providers de IA para o transcreve-ai.

API publica:
    AIProvider           - classe base ABC
    CapabilityNotSupported - excecao para capacidade nao suportada
    TranscribeResult     - DTO de resultado de transcricao
    SynthesisContext     - DTO de contexto para synthesize()
    load_provider(name)  - instancia provider pelo nome (lazy import)
    resolve_provider_name(cli) - resolve nome seguindo precedencia CLI > env > default
"""

from __future__ import annotations

import importlib.metadata
import warnings

from .base import (
    AUDIO_CHUNK_LIMIT_BYTES,
    AIProvider,
    Capability,
    CapabilityNotSupported,
    SynthesisContext,
    TranscribeResult,
)
from .registry import load_provider, register, resolve_provider_name

# Carrega providers externos registrados via entry_points
# (ex: [project.entry-points."transcreve_ai.providers"] no pyproject.toml de terceiros)
try:
    for _ep in importlib.metadata.entry_points(group="transcreve_ai.providers"):
        try:
            if not _ep.name or not _ep.value:
                raise ValueError(
                    "Entrada de entry point sem nome ou valor."
                )
            if ":" not in str(_ep.value):
                raise ValueError(
                    f"entry_point '{_ep.name}' sem referencia de classe (esperado 'modulo:Classe')."
                )
            register(_ep.name, _ep.value)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(
                f"Falha ao registrar provider externo via entry point '{_ep.name}': {exc}"
            )
except Exception as exc:  # noqa: BLE001
    warnings.warn(
        "Nao foi possivel carregar entry points do grupo transcreve_ai.providers. "
        f"Isso nao impede o uso dos providers internos. Erro: {exc}"
    )

__all__ = [
    "AUDIO_CHUNK_LIMIT_BYTES",
    "AIProvider",
    "Capability",
    "CapabilityNotSupported",
    "SynthesisContext",
    "TranscribeResult",
    "load_provider",
    "register",
    "resolve_provider_name",
]
