"""
Gera report.md e results.json a partir dos dados brutos do eval.

Escrita atomica: escreve em .tmp e depois renomeia para evitar
arquivo parcialmente escrito em caso de interrupcao.

API publica:
    write_report(results, out_dir, dataset_path, judge_provider) -> (Path, Path)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_report(
    results: dict[str, Any],
    out_dir: Path,
    dataset_path: str = "",
    judge_provider: str | None = None,
) -> tuple[Path, Path]:
    """
    Gera report.md e results.json em out_dir.

    Escrita atomica via arquivo .tmp + rename.

    Retorna (path_report_md, path_results_json).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / "report.md"
    json_path = out_dir / "results.json"

    # Gera conteudo
    md_content = _build_markdown(results, dataset_path, judge_provider)
    json_content = json.dumps(results, ensure_ascii=False, indent=2)

    # Escrita atomica
    _atomic_write(md_path, md_content)
    _atomic_write(json_path, json_content)

    return md_path, json_path


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _build_markdown(
    results: dict[str, Any],
    dataset_path: str,
    judge_provider: str | None,
) -> str:
    providers: list[str] = results.get("providers", [])
    cases: list[dict[str, Any]] = results.get("cases", [])
    generated_at = results.get("generated_at", "")
    summary = results.get("summary", {})

    # Cabecalho
    date_label = generated_at[:16].replace("T", " ") if generated_at else ""
    lines: list[str] = [
        f"# Eval TranscreveAI - {date_label}",
        "",
        f"Dataset: {dataset_path}",
        f"Providers: {', '.join(providers)}",
        f"Judge: {judge_provider if judge_provider else 'desativado'}",
        "",
    ]

    # Tabela por caso
    for case in cases:
        case_id = case.get("id", "?")
        lines.append(f"## Caso: {case_id}")
        if case.get("notes"):
            lines.append(f"*{case['notes']}*")
        lines.append("")

        prov_data: dict[str, Any] = case.get("providers", {})

        # Coleta metricas de todos os providers para montar tabela
        metric_rows = _build_metrics_rows(prov_data, providers)
        lines.extend(metric_rows)
        lines.append("")

        # Secao de warnings por provider
        for pname in providers:
            pr = prov_data.get(pname, {})
            warns = pr.get("warnings") or []
            if warns:
                lines.append(f"**Avisos ({pname}):**")
                for w in warns:
                    lines.append(f"- {w}")
                lines.append("")

    # Secao de resumo
    lines.append("## Resumo")
    lines.append("")
    lines.extend(_build_summary_table(summary, providers))
    lines.append("")

    # Recomendacao simples (menor custo entre providers pagos)
    best = _best_provider(summary, providers)
    if best:
        lines.append(f"Melhor custo-beneficio: **{best}**")
        lines.append("")

    # Avisos de capabilities por provider
    cap_warnings = _collect_capability_warnings(cases, providers)
    if cap_warnings:
        lines.append("## Providers sem suporte detectado")
        lines.append("")
        for warn in cap_warnings:
            lines.append(f"- {warn}")
        lines.append("")

    # Secao do judge (somente se ativado)
    if judge_provider:
        judge_lines = _build_judge_section(cases, providers)
        if judge_lines:
            lines.append("## Avaliacao qualitativa (judge)")
            lines.append("")
            lines.extend(judge_lines)
            lines.append("")

    lines.append("---")
    lines.append(
        "*Custos sao estimativas heuristicas. Precos reais variam. Verificar em cost_table.py.*"
    )

    return "\n".join(lines) + "\n"


def _build_metrics_rows(
    prov_data: dict[str, Any],
    providers: list[str],
) -> list[str]:
    """Monta tabela markdown de metricas com providers nas colunas."""
    METRICS_TO_SHOW = [
        ("total_s", "total_s"),
        ("download_s", "download_s"),
        ("ai_s", "ai_s"),
        ("cost_total_usd", "cost_total_usd"),
        ("duration_seconds", "duration_seconds"),
        ("transcript_len_words", "transcript_len_words"),
        ("frames_total", "frames_total"),
        ("frames_with_visual_note", "frames_with_visual_note"),
        ("chapters_count", "chapters_count"),
        ("entities_count", "entities_count"),
        ("warnings_count", "warnings_count"),
        ("synthesis_mode", "synthesis_mode"),
        ("wer", "wer"),
    ]

    header = "| Metrica" + "".join(f" | {p}" for p in providers) + " |"
    sep = "|---" + "|---" * len(providers) + "|"
    rows = [header, sep]

    for label, key in METRICS_TO_SHOW:
        values = []
        for pname in providers:
            pr = prov_data.get(pname, {})
            if pr.get("status") == "error":
                values.append("ERRO")
                continue
            val = _get_metric_value(pr, key)
            values.append(val)
        row = f"| {label}" + "".join(f" | {v}" for v in values) + " |"
        rows.append(row)

    return rows


def _get_metric_value(pr: dict[str, Any], key: str) -> str:
    """Extrai valor de metrica do dict de resultado de um provider/caso."""
    if key == "total_s":
        v = pr.get("elapsed_total_s")
        return f"{v:.2f}" if isinstance(v, (int, float)) else "-"
    if key == "download_s":
        v = (pr.get("stage_timings_s") or {}).get("download")
        return f"{v:.2f}" if isinstance(v, (int, float)) else "-"
    if key == "ai_s":
        timings = pr.get("stage_timings_s") or {}
        ai = timings.get("ai", 0.0)
        ai_frame = timings.get("ai_frame", 0.0)
        total_ai = (ai or 0.0) + (ai_frame or 0.0)
        return f"{total_ai:.2f}" if total_ai else "-"
    if key == "cost_total_usd":
        v = (pr.get("cost_estimate") or {}).get("total_usd")
        return f"{v:.4f}" if isinstance(v, (int, float)) else "-"
    if key == "wer":
        v = pr.get("wer")
        if v is None:
            return "-"
        return f"{v * 100:.1f}%"
    # metricas estruturais
    v = (pr.get("metrics") or {}).get(key)
    if v is None:
        return "-"
    return str(v)


def _build_summary_table(
    summary: dict[str, Any],
    providers: list[str],
) -> list[str]:
    header = "| Provider | Casos OK | Media total_s | Media cost_usd | WER medio |"
    sep = "|---|---|---|---|---|"
    rows = [header, sep]
    for pname in providers:
        s = summary.get(pname, {})
        ok = s.get("cases_ok", 0)
        total = s.get("cases_total", 0)
        avg_s = s.get("avg_total_s")
        avg_cost = s.get("avg_cost_usd")
        avg_wer = s.get("avg_wer")
        ok_str = f"{ok}/{total}"
        s_str = f"{avg_s:.1f}" if isinstance(avg_s, (int, float)) else "-"
        cost_str = f"{avg_cost:.4f}" if isinstance(avg_cost, (int, float)) else "-"
        wer_str = f"{avg_wer * 100:.1f}%" if isinstance(avg_wer, (int, float)) else "-"
        rows.append(f"| {pname} | {ok_str} | {s_str} | {cost_str} | {wer_str} |")
    return rows


def _best_provider(summary: dict[str, Any], providers: list[str]) -> str | None:
    """Retorna o provider pago com menor custo medio (exclui 'local')."""
    paid = [p for p in providers if p != "local"]
    if not paid:
        return None
    best = None
    best_cost = float("inf")
    for pname in paid:
        cost = summary.get(pname, {}).get("avg_cost_usd")
        if cost is not None and cost < best_cost:
            best_cost = cost
            best = pname
    return best


def _collect_capability_warnings(
    cases: list[dict[str, Any]],
    providers: list[str],
) -> list[str]:
    """Coleta warnings de capabilities de todos os casos/providers."""
    seen: set = set()
    result = []
    for case in cases:
        for pname in providers:
            pr = (case.get("providers") or {}).get(pname, {})
            for w in pr.get("warnings") or []:
                w_lower = w.lower()
                if any(
                    kw in w_lower
                    for kw in ("suportad", "capacidade", "sem embed", "sem visao", "nao suport")
                ):
                    key = (pname, w[:60])
                    if key not in seen:
                        seen.add(key)
                        result.append(f"{pname}: {w}")
    return result


def _build_judge_section(
    cases: list[dict[str, Any]],
    providers: list[str],
) -> list[str]:
    """Monta tabela do judge para todos os casos/providers."""
    rows: list[str] = []
    for case in cases:
        case_id = case.get("id", "?")
        has_judge = any(
            (case.get("providers") or {}).get(p, {}).get("judge") is not None for p in providers
        )
        if not has_judge:
            continue
        rows.append(f"### Caso: {case_id}")
        rows.append("")
        header = "| Provider | Cobertura | Coerencia | Utilidade | Nota Geral |"
        sep = "|---|---|---|---|---|"
        rows.extend([header, sep])
        for pname in providers:
            judge = (case.get("providers") or {}).get(pname, {}).get("judge")
            if judge is None:
                rows.append(f"| {pname} | - | - | - | - |")
                continue
            if judge.get("judge_skipped"):
                rows.append(f"| {pname} | (sem suporte) | - | - | - |")
                continue
            if judge.get("judge_error"):
                rows.append(f"| {pname} | ERRO | - | - | - |")
                continue
            c = judge.get("cobertura")
            co = judge.get("coerencia")
            u = judge.get("utilidade")
            ng = judge.get("nota_geral")
            rows.append(
                f"| {pname}"
                f" | {_fmt_score(c)}"
                f" | {_fmt_score(co)}"
                f" | {_fmt_score(u)}"
                f" | {_fmt_score(ng)}"
                " |"
            )
        rows.append("")
    return rows


def _fmt_score(v: Any) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):.1f}"
    except (TypeError, ValueError):
        return str(v)
