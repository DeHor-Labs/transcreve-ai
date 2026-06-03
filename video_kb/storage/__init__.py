"""
Modulo de armazenamento plugavel do TranscreveAI.

Re-exporta a ABC, tipos auxiliares e a factory publica.
"""

from __future__ import annotations

from .base import ArtifactPaths, StorageBackend, StorageRef
from .registry import load_storage, register_storage, resolve_storage_name

__all__ = [
    "ArtifactPaths",
    "StorageBackend",
    "StorageRef",
    "load_storage",
    "register_storage",
    "resolve_storage_name",
]
