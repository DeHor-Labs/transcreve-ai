"""
StageTimer - cronometra latencia por etapa via on_progress callback.

Uso:
    timer = StageTimer()
    options.on_progress = timer.callback
    pipeline.run(source)
    timings = timer.finalize()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class StageTimer:
    """Acumula tempo por step usando o callback on_progress do PipelineOptions."""

    _starts: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _totals: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _last_step: str | None = field(default=None, init=False, repr=False)

    def callback(self, step: str, detail: str) -> None:  # noqa: ARG002
        """Assinatura compativel com PipelineOptions.on_progress."""
        now = time.perf_counter()
        # Fecha etapa anterior (se houver)
        if self._last_step is not None:
            elapsed = now - self._starts.get(self._last_step, now)
            self._totals[self._last_step] = self._totals.get(self._last_step, 0.0) + elapsed
        # Abre nova etapa
        self._starts[step] = now
        self._last_step = step

    def close(self) -> None:
        """Fecha a ultima etapa aberta (chamar apos pipeline.run() retornar)."""
        if self._last_step is not None:
            now = time.perf_counter()
            elapsed = now - self._starts.get(self._last_step, now)
            self._totals[self._last_step] = self._totals.get(self._last_step, 0.0) + elapsed
            self._last_step = None

    def finalize(self) -> dict[str, float]:
        """
        Fecha a ultima etapa e retorna dict com tempos acumulados por step.
        Keys possiveis: download, audio, frames, ocr, ai, ai_frame, persist.
        """
        self.close()
        # Colapsa ai_frame dentro de ai para o relatorio de alto nivel
        result: dict[str, float] = {}
        for step, total in self._totals.items():
            result[step] = round(total, 3)
        return result

    def get(self, step: str, default: float = 0.0) -> float:
        """Retorna tempo acumulado para um step especifico."""
        return self._totals.get(step, default)
