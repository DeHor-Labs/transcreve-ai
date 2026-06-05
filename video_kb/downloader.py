import shutil
import socket
from ipaddress import ip_address
from os import getenv
from pathlib import Path
from urllib.parse import unquote, urlparse

from .models import SourceMetadata
from .utils import ensure_dir


def _read_max_download_bytes() -> int:
    raw = getenv("VIDEO_KB_MAX_DOWNLOAD_BYTES", "").strip()
    if not raw:
        return 1073741824
    try:
        value = int(raw)
    except ValueError:
        return 1073741824
    return value if value > 0 else 1073741824


DEFAULT_MAX_DOWNLOAD_BYTES = _read_max_download_bytes()


class UnsafeDownloadUrlError(ValueError):
    """Raised when a remote URL is unsafe for server-side fetching."""


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _is_public_ip(host: str) -> bool:
    try:
        return ip_address(host).is_global
    except ValueError:
        return False


def _reject_if_private_host(host: str) -> None:
    normalized = host.lower().strip("[]")
    if normalized in {"localhost"} or normalized.endswith(".localhost"):
        raise UnsafeDownloadUrlError("URL aponta para host local/privado.")
    try:
        ip = ip_address(normalized)
    except ValueError:
        return
    if not ip.is_global:
        raise UnsafeDownloadUrlError("URL aponta para IP local/privado/reservado.")


def validate_public_download_url(source: str, *, resolve_dns: bool = True) -> None:
    """Validate remote URLs before server-side downloads to reduce SSRF risk."""
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UnsafeDownloadUrlError("URL de download deve usar http(s).")
    if parsed.username or parsed.password:
        raise UnsafeDownloadUrlError("URL de download nao pode incluir credenciais.")

    host = parsed.hostname or ""
    _reject_if_private_host(host)

    if not resolve_dns:
        return

    try:
        infos = socket.getaddrinfo(host, parsed.port or None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeDownloadUrlError(f"Nao foi possivel resolver DNS para '{host}'.") from exc

    if not infos:
        raise UnsafeDownloadUrlError(f"Nao foi possivel resolver DNS para '{host}'.")

    for *_, sockaddr in infos:
        resolved_host = str(sockaddr[0])
        if not _is_public_ip(resolved_host):
            raise UnsafeDownloadUrlError("URL resolve para IP local/privado/reservado.")


def _local_path_from_source(source: str) -> Path:
    parsed = urlparse(source)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path)).expanduser().resolve()
    return Path(source).expanduser().resolve()


def _metadata_from_info(source: str, info: dict) -> SourceMetadata:
    return SourceMetadata(
        source=source,
        title=info.get("title") or "",
        webpage_url=info.get("webpage_url") or info.get("original_url") or source,
        extractor=info.get("extractor") or "",
        uploader=info.get("uploader") or "",
        channel=info.get("channel") or "",
        duration=float(info.get("duration") or 0),
        upload_date=info.get("upload_date") or "",
        description=info.get("description") or "",
        tags=list(info.get("tags") or []),
        categories=list(info.get("categories") or []),
    )


def _find_downloaded_file(out_dir: Path) -> Path | None:
    candidates = [
        path
        for path in out_dir.glob("source.*")
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def fetch_media(
    source: str,
    out_dir: Path,
    cookies_browser: str | None = None,
    cookies: str | None = None,
    video_format: str = "bv*+ba/b",
) -> tuple[Path, SourceMetadata]:
    ensure_dir(out_dir)
    if not is_url(source):
        source_path = _local_path_from_source(source)
        if not source_path.exists():
            raise FileNotFoundError(str(source_path))
        target = out_dir / ("source" + source_path.suffix)
        if source_path != target:
            shutil.copy2(str(source_path), str(target))
        return target, SourceMetadata(source=source, title=source_path.stem)

    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError("yt-dlp Python package is required for URL downloads") from exc

    validate_public_download_url(source)

    opts = {
        "format": video_format,
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": DEFAULT_MAX_DOWNLOAD_BYTES,
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies:
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(source, download=True)

    media_path = None
    for download in info.get("requested_downloads") or []:
        filepath = download.get("filepath")
        if filepath and Path(filepath).exists():
            media_path = Path(filepath)
            break
    if media_path is None:
        media_path = _find_downloaded_file(out_dir)
    if media_path is None or not media_path.exists():
        raise RuntimeError("Could not locate downloaded media file")

    return media_path, _metadata_from_info(source, info)
