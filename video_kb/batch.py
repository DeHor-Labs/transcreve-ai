from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .agent_workflow import AgentWorkflowOptions, run_agent_workflow
from .utils import ensure_dir, iso_now


def load_sources_file(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _load_json_sources(path)
    if suffix == ".csv":
        return _load_csv_sources(path)
    return _load_text_sources(path)


def run_agent_batch(
    sources_file: Path,
    options: AgentWorkflowOptions,
    *,
    limit: int = 0,
    fail_fast: bool = False,
) -> dict[str, Any]:
    sources = load_sources_file(sources_file)
    if limit > 0:
        sources = sources[:limit]

    out_dir = ensure_dir(options.out_dir)
    items: list[dict[str, Any]] = []
    for position, source in enumerate(sources, start=1):
        try:
            result = run_agent_workflow(source, replace(options, out_dir=out_dir))
            payload = result.to_dict()
            payload["ok"] = bool(result.run_id and result.analysis_path)
        except Exception as exc:  # noqa: BLE001
            payload = {
                "source": source,
                "ok": False,
                "error": str(exc),
                "warnings": ["Falha inesperada no batch."],
            }
            if fail_fast:
                items.append({"position": position, **payload})
                break
        items.append({"position": position, **payload})

    ok_count = sum(1 for item in items if item.get("ok"))
    failed_count = sum(1 for item in items if not item.get("ok"))
    summary = {
        "source_file": str(sources_file),
        "created_at": iso_now(),
        "total": len(items),
        "success": failed_count == 0,
        "ok": ok_count,
        "failed": failed_count,
        "ok_count": ok_count,
        "failed_count": failed_count,
        "items": items,
    }
    _write_batch_artifacts(summary, out_dir)
    return summary


def _load_text_sources(path: Path) -> list[str]:
    sources: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            sources.append(clean)
    return _unique(sources)


def _load_json_sources(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    values: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, dict):
                source_value = item.get("source") or item.get("url") or item.get("link") or ""
                values.append(str(source_value))
    elif isinstance(data, dict):
        raw_items = data.get("sources") or data.get("urls") or []
        if isinstance(raw_items, list):
            for item in raw_items:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    source_value = item.get("source") or item.get("url") or item.get("link") or ""
                    values.append(str(source_value))
    return _unique([value.strip() for value in values if value.strip()])


def _load_csv_sources(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(text.splitlines()))
    if not rows:
        return []
    header = [cell.strip().lower() for cell in rows[0]]
    source_index = _source_column_index(header)
    start = 1 if source_index is not None else 0
    if source_index is None:
        source_index = 0
    values = [
        row[source_index].strip()
        for row in rows[start:]
        if len(row) > source_index and row[source_index].strip()
    ]
    return _unique(values)


def _source_column_index(header: list[str]) -> int | None:
    for name in ("source", "url", "link"):
        if name in header:
            return header.index(name)
    return None


def _write_batch_artifacts(summary: dict[str, Any], out_dir: Path) -> None:
    (out_dir / "batch.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# TranscreveAI Batch",
        "",
        f"- Fonte: `{summary['source_file']}`",
        f"- Total: {summary['total']}",
        f"- OK: {summary['ok']}",
        f"- Falhas: {summary['failed']}",
        "",
        "## Runs",
    ]
    for item in summary["items"]:
        status = "ok" if item.get("ok") else "falha"
        run_id = item.get("run_id") or "-"
        source = item.get("source") or "-"
        lines.append(f"- {item['position']}. {status}: `{run_id}` - {source}")
        template_paths = item.get("template_paths") or {}
        if template_paths:
            for name, path in template_paths.items():
                lines.append(f"  - {name}: `{path}`")
    lines.append("")
    (out_dir / "batch.md").write_text("\n".join(lines), encoding="utf-8")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result
