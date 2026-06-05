"""
EvalRunner - orquestra casos x providers, coleta metricas e timings.

API publica:
    EvalCase      - dataclass de um caso do dataset
    EvalDataset   - dataclass do dataset carregado
    CaseResult    - resultado de um caso para um provider
    EvalRunner    - classe principal do eval
    load_dataset(path) -> EvalDataset
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .cost_table import estimate_cost
from .metrics import extract_metrics, wer_simple
from .stage_timer import StageTimer


@dataclass
class EvalCase:
    id: str
    source: str
    notes: str = ""
    ground_truth_transcript: str | None = None


@dataclass
class EvalDataset:
    version: str
    description: str
    cases: list[EvalCase]
    path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalDataset:
        cases = [
            EvalCase(
                id=c["id"],
                source=c["source"],
                notes=c.get("notes", ""),
                ground_truth_transcript=c.get("ground_truth_transcript") or None,
            )
            for c in data.get("cases", [])
        ]
        return cls(
            version=str(data.get("version", "1")),
            description=data.get("description", ""),
            cases=cases,
        )


@dataclass
class CaseResult:
    status: str  # "ok" | "error"
    provider: str
    case_id: str
    elapsed_total_s: float = 0.0
    stage_timings_s: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    cost_estimate: dict[str, float] = field(default_factory=dict)
    wer: float | None = None
    warnings: list[str] = field(default_factory=list)
    judge: dict[str, Any] | None = None
    error_message: str | None = None


def load_dataset(path: Path) -> EvalDataset:
    """Carrega dataset de avaliacao a partir de arquivo JSON."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    dataset = EvalDataset.from_dict(data)
    dataset.path = str(path)
    return dataset


class EvalRunner:
    """
    Orquestra a execucao do eval: para cada caso x provider,
    roda o VideoKnowledgePipeline com cronometragem por etapa.
    """

    def __init__(
        self,
        dataset: EvalDataset,
        providers: list[str],
        out_dir: Path,
        ai_mode: str = "full",
        judge_provider: str | None = None,
        dataset_path: Path | str | None = None,
        on_progress: Callable[[str], None] | None = None,
    ) -> None:
        self.dataset = dataset
        self.providers = providers
        self.out_dir = out_dir
        self.ai_mode = ai_mode
        self.judge_provider = judge_provider
        self.dataset_path = dataset_path if dataset_path is not None else dataset.path
        self.on_progress = on_progress  # callback(msg) para progresso no CLI

    def run(self) -> dict[str, Any]:
        """
        Executa o eval completo.

        Retorna estrutura de dados no formato de results.json.
        """
        from ..pipeline import PipelineOptions, VideoKnowledgePipeline

        cases_results: list[dict[str, Any]] = []

        for case in self.dataset.cases:
            self._log(f"\nCaso: {case.id}")
            providers_data: dict[str, Any] = {}

            for provider_name in self.providers:
                self._log(f"  Provider: {provider_name}")
                case_result = self._run_one(
                    case=case,
                    provider_name=provider_name,
                    pipeline_cls=VideoKnowledgePipeline,
                    options_cls=PipelineOptions,
                )
                providers_data[provider_name] = _case_result_to_dict(case_result)

            cases_results.append(
                {
                    "id": case.id,
                    "source": case.source,
                    "notes": case.notes,
                    "providers": providers_data,
                }
            )

        summary = _build_summary(cases_results, self.providers)

        return {
            "generated_at": _iso_now(),
            "dataset": str(self.dataset_path)
            if self.dataset_path is not None
            else str(self.out_dir),
            "providers": self.providers,
            "cases": cases_results,
            "summary": summary,
        }

    def _run_one(
        self,
        case: EvalCase,
        provider_name: str,
        pipeline_cls: Any,
        options_cls: Any,
    ) -> CaseResult:
        """Roda o pipeline para um caso/provider e coleta todas as metricas."""
        safe_case_id = _sanitize_case_id(case.id)

        # Diretorio de saida isolado por caso+provider
        run_out = self.out_dir / "runs" / safe_case_id / provider_name
        run_out.mkdir(parents=True, exist_ok=True)

        timer = StageTimer()

        options = options_cls(
            out_dir=run_out,
            ai_mode=self.ai_mode,
            provider_name=provider_name,
            force=True,  # evita deduplicacao entre providers
            on_progress=timer.callback,
        )
        pipeline = pipeline_cls(options)

        wall_start = time.perf_counter()
        analysis_result = None
        error_message = None

        try:
            analysis_result = pipeline.run(case.source)
        except Exception as exc:  # noqa: BLE001
            error_message = _sanitize_error_message(str(exc))
        finally:
            wall_elapsed = time.perf_counter() - wall_start
            timer.close()

        if error_message is not None:
            self._log(f"    ERRO: {error_message}")
            return CaseResult(
                status="error",
                provider=provider_name,
                case_id=case.id,
                elapsed_total_s=round(wall_elapsed, 3),
                stage_timings_s=timer.finalize(),
                error_message=error_message,
            )

        # Metricas estruturais
        metrics = extract_metrics(analysis_result)  # type: ignore[arg-type]
        stage_timings = timer.finalize()

        # Custo estimado
        visual_notes_chars = metrics.get("visual_notes_len_chars", 0)
        cost = estimate_cost(
            provider_name=provider_name,
            duration_seconds=metrics["duration_seconds"],
            frames_with_visual_note=metrics["frames_with_visual_note"],
            transcript_len_chars=metrics["transcript_len_chars"],
            visual_notes_len_chars=visual_notes_chars,
        )

        # WER (somente se ground_truth disponivel e nao-vazio)
        wer_value: float | None = None
        if case.ground_truth_transcript and case.ground_truth_transcript.strip():
            hyp = analysis_result.transcript_text or ""  # type: ignore[union-attr]
            wer_value = round(wer_simple(case.ground_truth_transcript, hyp), 4)

        # Judge (opcional)
        judge_data: dict[str, Any] | None = None
        if self.judge_provider:
            from .judge import run_judge

            try:
                judge_result = run_judge(
                    synthesis=analysis_result.synthesis,  # type: ignore[union-attr]
                    provider_name=self.judge_provider,
                )
            except Exception as exc:  # noqa: BLE001
                judge_data = {
                    "judge_error": _sanitize_error_message(
                        f"falha ao executar judge '{self.judge_provider}': {exc}"
                    )
                }
            else:
                judge_data = {
                    "cobertura": judge_result.cobertura,
                    "coerencia": judge_result.coerencia,
                    "utilidade": judge_result.utilidade,
                    "nota_geral": judge_result.nota_geral,
                    "justificativa": judge_result.justificativa,
                }
                if judge_result.error:
                    judge_data["judge_error"] = judge_result.error
                if judge_result.skipped:
                    judge_data["judge_skipped"] = judge_result.skipped

        self._log(f"    OK: total={wall_elapsed:.1f}s cost={cost['total_usd']:.4f} USD")

        return CaseResult(
            status="ok",
            provider=provider_name,
            case_id=case.id,
            elapsed_total_s=round(wall_elapsed, 3),
            stage_timings_s=stage_timings,
            metrics=metrics,
            cost_estimate=cost,
            wer=wer_value,
            warnings=list(analysis_result.warnings),  # type: ignore[union-attr]
            judge=judge_data,
        )

    def _log(self, msg: str) -> None:
        if self.on_progress:
            self.on_progress(msg)
        else:
            print(msg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _case_result_to_dict(r: CaseResult) -> dict[str, Any]:
    d: dict[str, Any] = {
        "status": r.status,
        "elapsed_total_s": r.elapsed_total_s,
        "stage_timings_s": r.stage_timings_s,
        "metrics": r.metrics,
        "cost_estimate": r.cost_estimate,
        "wer": r.wer,
        "warnings": r.warnings,
        "judge": r.judge,
    }
    if r.error_message:
        d["error_message"] = r.error_message
    return d


def _build_summary(
    cases_results: list[dict[str, Any]],
    providers: list[str],
) -> dict[str, Any]:
    """Calcula medias por provider para o bloco summary do results.json."""
    summary: dict[str, Any] = {}
    for provider in providers:
        total_s_list: list[float] = []
        cost_list: list[float] = []
        wer_list: list[float] = []
        ok_count = 0
        total_count = 0

        for case in cases_results:
            pr = case["providers"].get(provider, {})
            total_count += 1
            if pr.get("status") == "ok":
                ok_count += 1
                total_s_list.append(pr.get("elapsed_total_s", 0.0))
                cost = pr.get("cost_estimate") or {}
                cost_list.append(cost.get("total_usd", 0.0))
                if pr.get("wer") is not None:
                    wer_list.append(pr["wer"])

        summary[provider] = {
            "cases_ok": ok_count,
            "cases_total": total_count,
            "avg_total_s": round(sum(total_s_list) / len(total_s_list), 2)
            if total_s_list
            else None,
            "avg_cost_usd": round(sum(cost_list) / len(cost_list), 6) if cost_list else None,
            "avg_wer": round(sum(wer_list) / len(wer_list), 4) if wer_list else None,
        }
    return summary


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_case_id(value: str) -> str:
    """Sanitiza case.id para nome de pasta seguro no sistema de arquivos."""
    value = (value or "").strip()
    if not value:
        return "case"

    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", value)
    sanitized = sanitized.strip("-_.") or "case"
    if len(sanitized) > 80:
        sanitized = sanitized[:80]
    return sanitized


def _sanitize_error_message(message: str) -> str:
    """Limpa mensagem de erro para serializacao JSON e logs humanos."""
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]+", " ", message or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1000]
