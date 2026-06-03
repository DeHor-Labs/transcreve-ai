import hashlib
import json
import os
import re
import subprocess
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class CommandError(RuntimeError):
    def __init__(self, command: list[str], returncode: int, stderr: str):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__("Command failed ({}): {}".format(returncode, " ".join(command)))


def run_command(command: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if proc.returncode != 0:
        raise CommandError(command, proc.returncode, proc.stderr.strip())
    return proc


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str, fallback: str = "video") -> str:
    normalized = value.lower().strip()
    normalized = re.sub(r"https?://", "", normalized)
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return (normalized or fallback)[:80]


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_timestamp(seconds: float) -> str:
    seconds = max(0, float(seconds or 0))
    whole = int(seconds)
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def compact_text(text: str, limit: int = 12000) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    half = max(1000, limit // 2)
    return text[:half].rstrip() + "\n\n...[truncated]...\n\n" + text[-half:].lstrip()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sha256_url(url: str) -> str:
    """
    Retorna o sha256 de uma URL remota normalizada.

    Extrai o ID canonico quando possivel (YouTube, Vimeo) e descarta
    parametros de rastreamento para garantir que URLs equivalentes
    produzam o mesmo hash.
    """
    _TRACKING_PARAMS = frozenset(
        {
            "t",
            "si",
            "pp",
            "feature",
            "ref",
            "index",
            "list",
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
        }
    )

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")
    path_lower = parsed.path.rstrip("/").lower()
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)

    # YouTube: youtube.com ou youtu.be
    if host in ("youtube.com", "youtu.be", "m.youtube.com"):
        if host == "youtu.be":
            vid = path_lower.lstrip("/")
        else:
            vid = (qs.get("v") or [""])[0]
            if not vid:
                # /shorts/<id> ou /embed/<id>
                parts = path_lower.strip("/").split("/")
                vid = parts[-1] if len(parts) >= 2 else ""
        if vid:
            canonical = f"youtube:{vid}"
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Vimeo: vimeo.com
    if host == "vimeo.com":
        parts = path_lower.strip("/").split("/")
        vid = parts[0] if parts else ""
        if vid and vid.isdigit():
            canonical = f"vimeo:{vid}"
            return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Fallback generico: host + path sem parametros de rastreamento
    clean_qs = {k: v for k, v in qs.items() if k not in _TRACKING_PARAMS}
    clean_query = urllib.parse.urlencode(clean_qs, doseq=True)
    canonical = f"{host}{path_lower}"
    if clean_query:
        canonical = f"{canonical}?{clean_query}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def which(name: str) -> Optional[str]:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / name
        if candidate.exists() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value
