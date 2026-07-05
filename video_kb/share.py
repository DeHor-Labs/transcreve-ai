from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .index import RunIndex, resolve_index_path
from .utils import ensure_dir, iso_now, slugify, write_json

DEFAULT_SHARE_DIR = Path.home() / ".transcreveai" / "shared-knowledge"
HANDOFF_MESSAGE = "O dossie que voce criou foi salvo para voce como conhecimento."
_URL_RE = re.compile(r"https?://[^\s'\"<>`]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?im)\b(api[_-]?key|token|secret|password|authorization|cookie)"
    r"(\s*[:=]\s*)(?:\"[^\r\n\"]*\"|'[^\r\n']*'|[^\r\n]*)"
)
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "code",
    "cookie",
    "key",
    "password",
    "secret",
    "signature",
    "sig",
    "token",
    "x-amz-credential",
    "x-amz-security-token",
    "x-amz-signature",
}


class ShareRunError(RuntimeError):
    """Raised when a run cannot be packaged for shared agent reuse."""


def share_run(
    *,
    run_id: str = "",
    run_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    index_db: str | None = None,
) -> dict[str, Any]:
    source_mode = "run_dir" if run_dir else "index"
    run = _resolve_run(run_id=run_id, run_dir=run_dir, index_db=index_db)
    analysis_path = _local_file(str(run.get("analysis_path") or ""), "analysis.json")
    markdown_path = _local_file(str(run.get("markdown_path") or ""), "knowledge.md")
    analysis = _read_analysis(analysis_path)

    resolved_run_id = str(run.get("id") or analysis.get("run_id") or "").strip()
    if not resolved_run_id:
        raise ShareRunError("run_id ausente no indice e no analysis.json.")

    share_root = (Path(out_dir).expanduser() if out_dir else DEFAULT_SHARE_DIR).resolve()
    share_dir = ensure_dir(share_root / slugify(resolved_run_id, fallback="run"))
    if share_dir == markdown_path.parent:
        raise ShareRunError("Diretorio de destino nao pode ser a propria pasta do run.")

    copied = {
        "knowledge_md": str(_copy_sanitized_text(markdown_path, share_dir / "knowledge.md")),
        "analysis_json": str(_write_sanitized_json(analysis, share_dir / "analysis.json")),
    }
    copied.update(_copy_templates(markdown_path.parent, share_dir))

    manifest = _manifest(
        run=run,
        analysis=analysis,
        copied=copied,
        share_dir=share_dir,
        index_db=index_db,
        source_mode=source_mode,
    )
    handoff_path = share_dir / "handoff.md"
    manifest_path = share_dir / "manifest.json"
    manifest["handoff_md"] = str(handoff_path)
    manifest["manifest_json"] = str(manifest_path)
    handoff_path.write_text(_handoff_markdown(manifest, analysis), encoding="utf-8")
    write_json(manifest_path, manifest)
    manifest.update(_update_catalog(share_root, manifest))
    write_json(manifest_path, manifest)
    return manifest


def _resolve_run(
    *,
    run_id: str,
    run_dir: str | Path | None,
    index_db: str | None,
) -> dict[str, Any]:
    if run_dir:
        return _run_from_dir(Path(run_dir).expanduser())
    clean_run_id = run_id.strip()
    if not clean_run_id:
        raise ShareRunError("Informe run_id ou --run-dir.")
    with RunIndex(resolve_index_path(index_db)) as idx:
        run = idx.get_run(clean_run_id)
    if run is None:
        raise ShareRunError(f"Run '{clean_run_id}' nao encontrado no indice.")
    return run


def _run_from_dir(run_dir: Path) -> dict[str, Any]:
    resolved = run_dir.resolve()
    analysis_path = resolved / "analysis.json"
    markdown_path = resolved / "knowledge.md"
    analysis = _read_analysis(analysis_path)
    metadata = _dict_field(analysis.get("metadata"))
    return {
        "id": str(analysis.get("run_id") or resolved.name),
        "source": str(analysis.get("source") or metadata.get("source") or ""),
        "title": str(metadata.get("title") or ""),
        "created_at": str(analysis.get("created_at") or ""),
        "output_dir": str(resolved),
        "analysis_path": str(analysis_path),
        "markdown_path": str(markdown_path),
        "provider": str(metadata.get("extractor") or ""),
    }


def _read_analysis(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ShareRunError(f"analysis.json nao encontrado: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ShareRunError(f"analysis.json invalido: {path}") from exc
    if not isinstance(data, dict):
        raise ShareRunError(f"analysis.json invalido: {path}")
    return data


def _local_file(raw_path: str, label: str) -> Path:
    if not raw_path:
        raise ShareRunError(f"{label} ausente no run.")
    parsed = urlparse(raw_path)
    if parsed.scheme and parsed.scheme != "file":
        raise ShareRunError(
            f"{label} remoto nao pode ser copiado localmente: {_sanitize_text(raw_path)}"
        )
    path = Path(parsed.path if parsed.scheme == "file" else raw_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ShareRunError(f"{label} nao encontrado: {path}")
    return path


def _copy(src: Path, dest: Path) -> Path:
    ensure_dir(dest.parent)
    shutil.copy2(src, dest)
    return dest


def _copy_sanitized_text(src: Path, dest: Path) -> Path:
    ensure_dir(dest.parent)
    dest.write_text(_sanitize_text(src.read_text(encoding="utf-8")), encoding="utf-8")
    return dest


def _write_sanitized_json(data: Any, dest: Path) -> Path:
    write_json(dest, _sanitize_value(data))
    return dest


def _copy_templates(run_dir: Path, share_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    for filename in ("content.md", "content.json", "content.csv", "skill.md", "skill.json"):
        src = run_dir / filename
        if src.exists() and src.is_file():
            copied_path = _copy_template(src, share_dir / filename)
            key = Path(filename).stem if filename.endswith(".md") else filename
            copied[key] = str(copied_path)
    return copied


def _copy_template(src: Path, dest: Path) -> Path:
    if src.suffix == ".json":
        try:
            return _write_sanitized_json(json.loads(src.read_text(encoding="utf-8")), dest)
        except json.JSONDecodeError:
            return _copy_sanitized_text(src, dest)
    if src.suffix in {".md", ".csv"}:
        return _copy_sanitized_text(src, dest)
    return _copy(src, dest)


def _manifest(
    *,
    run: dict[str, Any],
    analysis: dict[str, Any],
    copied: dict[str, str],
    share_dir: Path,
    index_db: str | None,
    source_mode: str,
) -> dict[str, Any]:
    metadata = _dict_field(analysis.get("metadata"))
    synthesis = _dict_field(analysis.get("synthesis"))
    run_id = str(run.get("id") or analysis.get("run_id") or "")
    return {
        "ok": True,
        "handoff_message": HANDOFF_MESSAGE,
        "shared_at": iso_now(),
        "run_id": run_id,
        "title": _sanitize_text(str(run.get("title") or metadata.get("title") or run_id)),
        "source": _sanitize_text(
            str(run.get("source") or analysis.get("source") or metadata.get("source") or "")
        ),
        "created_at": str(run.get("created_at") or analysis.get("created_at") or ""),
        "share_dir": str(share_dir),
        "source_mode": source_mode,
        "index_db": str(resolve_index_path(index_db)) if source_mode == "index" else "",
        "index_db_scope": (
            _resolve_index_db_scope(index_db) if source_mode == "index" else "not_used"
        ),
        "original": {
            "output_dir": str(run.get("output_dir") or analysis.get("workdir") or ""),
            "knowledge_md": str(run.get("markdown_path") or ""),
            "analysis_json": str(run.get("analysis_path") or ""),
        },
        "artifacts": copied,
        "summary": _sanitize_text(str(synthesis.get("summary") or "")),
        "tools_or_products": _sanitize_list(synthesis.get("tools_or_products")),
        "action_items": _sanitize_list(synthesis.get("action_items")),
    }


def _handoff_markdown(manifest: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# TranscreveAI Shared Knowledge",
        "",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Title: {manifest['title']}",
        f"- Source: {manifest['source']}",
        f"- Shared at: {manifest['shared_at']}",
        f"- Source mode: {manifest['source_mode']}",
        f"- Index DB: {manifest['index_db'] or 'not used'} ({manifest['index_db_scope']})",
        f"- Knowledge: `{manifest['artifacts']['knowledge_md']}`",
        f"- Analysis: `{manifest['artifacts']['analysis_json']}`",
        "",
        manifest["handoff_message"],
        "",
    ]
    summary = str(manifest.get("summary") or "").strip()
    if summary:
        lines.extend(["## Summary", "", summary, ""])
    _extend_list(lines, "Tools Or Products", manifest.get("tools_or_products") or [])
    _extend_list(lines, "Action Items", manifest.get("action_items") or [])

    synthesis = _dict_field(analysis.get("synthesis"))
    claims = _list_field(synthesis.get("claims"))
    questions = _list_field(synthesis.get("questions"))
    _extend_list(lines, "Claims", claims)
    _extend_list(lines, "Open Questions", questions)

    extra = {
        key: value
        for key, value in manifest["artifacts"].items()
        if key not in {"knowledge_md", "analysis_json"}
    }
    if extra:
        lines.extend(["## Extra Artifacts", ""])
        for name, path in extra.items():
            lines.append(f"- {name}: `{path}`")
        lines.append("")
    lines.extend(
        [
            "## Agent Use",
            "",
            "- Read `knowledge.md` first for the human dossier.",
            "- Use `analysis.json` for structured fields and evidence-backed automation.",
            "- Treat this packet as generated evidence, not as proof of current external state.",
            "",
        ]
    )
    return "\n".join(lines)


def _update_catalog(share_root: Path, manifest: dict[str, Any]) -> dict[str, str]:
    ensure_dir(share_root)
    catalog_json = share_root / "catalog.json"
    catalog_md = share_root / "index.md"
    existing_entries = _read_catalog_entries(catalog_json)
    entry = _catalog_entry(manifest)
    entries = [
        item
        for item in existing_entries
        if not (
            item.get("run_id") == entry["run_id"]
            and item.get("share_dir") == entry["share_dir"]
        )
    ]
    entries.insert(0, entry)
    entries.sort(key=lambda item: str(item.get("shared_at") or ""), reverse=True)
    write_json(
        catalog_json,
        {
            "ok": True,
            "updated_at": iso_now(),
            "entries": entries,
        },
    )
    catalog_md.write_text(_catalog_markdown(entries), encoding="utf-8")
    return {"catalog_json": str(catalog_json), "catalog_md": str(catalog_md)}


def _read_catalog_entries(catalog_json: Path) -> list[dict[str, Any]]:
    if not catalog_json.exists():
        return []
    try:
        data = json.loads(catalog_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    return [item for item in entries if isinstance(item, dict)]


def _catalog_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": manifest.get("run_id", ""),
        "title": manifest.get("title", ""),
        "source": manifest.get("source", ""),
        "summary": manifest.get("summary", ""),
        "shared_at": manifest.get("shared_at", ""),
        "share_dir": manifest.get("share_dir", ""),
        "handoff_md": manifest.get("handoff_md", ""),
        "manifest_json": manifest.get("manifest_json", ""),
        "source_mode": manifest.get("source_mode", ""),
        "index_db_scope": manifest.get("index_db_scope", ""),
    }


def _catalog_markdown(entries: list[dict[str, Any]]) -> str:
    lines = [
        "# TranscreveAI Shared Knowledge Catalog",
        "",
        "Use this catalog to discover durable TranscreveAI packets generated for agents.",
        "",
    ]
    if not entries:
        lines.append("_No shared packets yet._")
        return "\n".join(lines)
    for entry in entries:
        title = str(entry.get("title") or entry.get("run_id") or "Untitled")
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Run ID: `{entry.get('run_id', '')}`",
                f"- Shared at: {entry.get('shared_at', '')}",
                f"- Source: {entry.get('source', '')}",
                f"- Handoff: `{entry.get('handoff_md', '')}`",
                f"- Manifest: `{entry.get('manifest_json', '')}`",
                f"- Index scope: {entry.get('index_db_scope', '')}",
                "",
            ]
        )
        summary = str(entry.get("summary") or "").strip()
        if summary:
            lines.extend([summary, ""])
    return "\n".join(lines)


def _extend_list(lines: list[str], title: str, items: list[Any]) -> None:
    clean = [_sanitize_text(str(item).strip()) for item in items if str(item).strip()]
    if not clean:
        return
    lines.extend([f"## {title}", ""])
    lines.extend(f"- {item}" for item in clean[:20])
    lines.append("")


def _dict_field(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_field(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _resolve_index_db_scope(index_db: str | None) -> str:
    raw = (index_db or "").strip()
    if raw == ":memory:":
        return "isolated"

    resolved = resolve_index_path(index_db)
    tmp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    if Path("/private/tmp").exists():
        tmp_roots.add(Path("/private/tmp").resolve())
    for tmp_root in tmp_roots:
        try:
            resolved.relative_to(tmp_root)
            return "isolated"
        except ValueError:
            continue
    return "real"


def _sanitize_list(value: Any) -> list[str]:
    return [_sanitize_text(str(item).strip()) for item in _list_field(value) if str(item).strip()]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _sanitize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    return value


def _sanitize_text(text: str) -> str:
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1\2[redacted]", text)
    return _URL_RE.sub(_redact_sensitive_url, text)


def _redact_sensitive_url(match: re.Match[str]) -> str:
    url = match.group(0)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return url

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    has_sensitive_query = any(key.lower() in _SENSITIVE_QUERY_KEYS for key, _ in query_pairs)
    if not has_sensitive_query and not (parsed.username or parsed.password):
        return url

    netloc = parsed.hostname or ""
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    safe_pairs = [
        (key, "[redacted]" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
        for key, value in query_pairs
    ]
    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            "",
            urlencode(safe_pairs, doseq=True),
            "",
        )
    )
