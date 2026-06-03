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
        register(_ep.name, _ep.value)
except Exception:  # noqa: BLE001
    pass  # entry_points ausentes nao devem impedir o import do pacote

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
