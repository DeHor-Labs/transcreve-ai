import json
import re
import shutil
import socket
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from ipaddress import ip_address
from os import getenv
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

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
_INSTAGRAM_EMBED_ITEM_MAX_BYTES = min(DEFAULT_MAX_DOWNLOAD_BYTES, 25 * 1024 * 1024)
_INSTAGRAM_EMBED_CAROUSEL_MAX_BYTES = min(
    DEFAULT_MAX_DOWNLOAD_BYTES,
    10 * _INSTAGRAM_EMBED_ITEM_MAX_BYTES,
)
_INSTAGRAM_EMBED_CHUNK_SIZE = 64 * 1024


class UnsafeDownloadUrlError(ValueError):
    """Raised when a remote URL is unsafe for server-side fetching."""


class ImageFallbackUsedWarning(RuntimeWarning):
    """Marker used internally when a URL resolves to an image instead of video."""


@dataclass
class DownloadedMedia:
    primary_path: Path
    media_paths: list[Path]
    metadata: SourceMetadata
    warnings: list[str] = field(default_factory=list)


class _YtDlpLogger:
    def debug(self, message: str) -> None:
        return None

    def warning(self, message: str) -> None:
        return None

    def error(self, message: str) -> None:
        return None


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
        media_kind="video",
    )


def _metadata_from_page(source: str, page: "_OpenGraphPage") -> SourceMetadata:
    return SourceMetadata(
        source=source,
        title=page.title,
        webpage_url=source,
        extractor="open_graph",
        description=page.description,
        media_kind="image",
    )


def _metadata_from_instagram_embed(source: str, media: dict) -> SourceMetadata:
    caption = _instagram_caption(media)
    owner = media.get("owner") or {}
    username = str(owner.get("username") or "")
    full_name = str(owner.get("full_name") or "")
    title = f"Instagram carousel by {username}" if username else "Instagram carousel"
    return SourceMetadata(
        source=source,
        title=title,
        webpage_url=source,
        extractor="instagram_embed",
        uploader=full_name,
        channel=username,
        duration=float(media.get("video_duration") or 0),
        upload_date=str(media.get("taken_at_timestamp") or ""),
        description=caption,
        media_kind="carousel",
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


def _find_downloaded_files(out_dir: Path) -> list[Path]:
    candidates = [
        path
        for path in out_dir.glob("source*.*")
        if path.is_file() and path.suffix.lower() not in {".part", ".ytdl"}
    ]
    return sorted(candidates)


def fetch_media_bundle(
    source: str,
    out_dir: Path,
    cookies_browser: str | None = None,
    cookies: str | None = None,
    video_format: str = "bv*+ba/b",
) -> DownloadedMedia:
    media_path, metadata = _fetch_primary_or_collection(
        source,
        out_dir,
        cookies_browser=cookies_browser,
        cookies=cookies,
        video_format=video_format,
    )
    if isinstance(media_path, DownloadedMedia):
        return media_path
    return DownloadedMedia(primary_path=media_path, media_paths=[media_path], metadata=metadata)


def fetch_media(
    source: str,
    out_dir: Path,
    cookies_browser: str | None = None,
    cookies: str | None = None,
    video_format: str = "bv*+ba/b",
) -> tuple[Path, SourceMetadata]:
    media = fetch_media_bundle(
        source,
        out_dir,
        cookies_browser=cookies_browser,
        cookies=cookies,
        video_format=video_format,
    )
    return media.primary_path, media.metadata


def _fetch_primary_or_collection(
    source: str,
    out_dir: Path,
    cookies_browser: str | None = None,
    cookies: str | None = None,
    video_format: str = "bv*+ba/b",
) -> tuple[Path, SourceMetadata] | tuple[DownloadedMedia, SourceMetadata]:
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

    allow_playlist = _should_allow_playlist_download(source)
    outtmpl = "source_%(playlist_index)02d.%(ext)s" if allow_playlist else "source.%(ext)s"
    opts = {
        "format": video_format,
        "outtmpl": str(out_dir / outtmpl),
        "merge_output_format": "mp4",
        "noplaylist": not allow_playlist,
        "quiet": True,
        "no_warnings": False,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
        "max_filesize": DEFAULT_MAX_DOWNLOAD_BYTES,
        "ignore_no_formats_error": True,
        "logger": _YtDlpLogger(),
    }
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
    if cookies:
        opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            info = ydl.extract_info(source, download=True)
        except yt_dlp.utils.DownloadError as exc:
            if not _is_no_video_formats_error(exc):
                raise
            media = _fetch_instagram_embed_media(source, out_dir)
            if media:
                return media, media.metadata
            return _fetch_image_fallback(source, out_dir)

    media_paths = _downloaded_paths_from_info(info)
    if not media_paths:
        media_paths = _find_downloaded_files(out_dir)
    if media_paths:
        return (
            DownloadedMedia(
                primary_path=media_paths[0],
                media_paths=media_paths,
                metadata=_metadata_from_info(source, info),
            ),
            _metadata_from_info(source, info),
        )

    media_path = None
    for download in info.get("requested_downloads") or []:
        filepath = download.get("filepath")
        if filepath and Path(filepath).exists():
            media_path = Path(filepath)
            break
    if media_path is None:
        media_path = _find_downloaded_file(out_dir)
    if media_path is None or not media_path.exists():
        media = _fetch_instagram_embed_media(source, out_dir)
        if media:
            return media, media.metadata
        if _info_has_no_formats(info):
            return _fetch_image_fallback(source, out_dir)
        raise RuntimeError("Could not locate downloaded media file")

    return media_path, _metadata_from_info(source, info)


def _downloaded_paths_from_info(info: dict) -> list[Path]:
    paths: list[Path] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for download in value.get("requested_downloads") or []:
                filepath = download.get("filepath")
                if filepath and Path(filepath).exists():
                    paths.append(Path(filepath))
            for entry in value.get("entries") or []:
                visit(entry)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(info)
    unique: dict[str, Path] = {}
    for path in paths:
        unique[str(path)] = path
    return sorted(unique.values())


def _should_allow_playlist_download(source: str) -> bool:
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/")
    return host.endswith("instagram.com") and path.startswith("/p/")


def _is_no_video_formats_error(exc: Exception) -> bool:
    message = str(exc)
    return "No video formats found" in message or "Requested format is not available" in message


def _info_has_no_formats(info: dict) -> bool:
    formats = info.get("formats")
    requested_downloads = info.get("requested_downloads")
    entries = info.get("entries") or []
    entries_have_formats = any(entry.get("formats") for entry in entries if isinstance(entry, dict))
    return (
        isinstance(formats, list)
        and not formats
        and not requested_downloads
        and not entries_have_formats
    )


class _OpenGraphPage(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url = ""
        self.title = ""
        self.description = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        data = {key.lower(): value or "" for key, value in attrs}
        name = data.get("property") or data.get("name") or ""
        content = data.get("content") or ""
        if name in {"og:image", "twitter:image"} and content and not self.image_url:
            self.image_url = content
        elif name in {"og:title", "twitter:title"} and content and not self.title:
            self.title = content
        elif name in {"og:description", "description", "twitter:description"}:
            if content and not self.description:
                self.description = content


def _fetch_image_fallback(source: str, out_dir: Path) -> tuple[Path, SourceMetadata]:
    page = _read_open_graph_page(source)
    if not page.image_url:
        raise RuntimeError("URL nao possui formatos de video nem imagem de preview detectavel.")

    image_url = page.image_url.replace("&amp;", "&")
    validate_public_download_url(image_url)
    suffix = Path(urlparse(image_url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    target = out_dir / f"source{suffix}"

    request = Request(image_url, headers={"User-Agent": "Mozilla/5.0"})
    max_image_bytes = min(DEFAULT_MAX_DOWNLOAD_BYTES, 25 * 1024 * 1024)
    with urlopen(request, timeout=30) as response:
        target.write_bytes(response.read(max_image_bytes + 1))
    if target.stat().st_size > max_image_bytes:
        target.unlink(missing_ok=True)
        raise RuntimeError("Imagem de fallback excede VIDEO_KB_MAX_DOWNLOAD_BYTES.")

    return target, _metadata_from_page(source, page)


def _fetch_instagram_embed_media(source: str, out_dir: Path) -> DownloadedMedia | None:
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    route_path = parsed.path.rstrip("/")
    if not host.endswith("instagram.com") or not route_path.startswith("/p/"):
        return None

    shortcode = route_path.split("/")[2] if len(route_path.split("/")) > 2 else ""
    if not shortcode:
        return None

    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
    page = _read_instagram_embed_page(embed_url)
    media = _extract_instagram_embed_media(page)
    if not media:
        return None

    items = _instagram_media_items(media)
    if not items:
        return None

    media_paths: list[Path] = []
    remaining_carousel_bytes = _INSTAGRAM_EMBED_CAROUSEL_MAX_BYTES
    for index, item in enumerate(items, start=1):
        media_url = str(item.get("url") or "")
        media_type = str(item.get("type") or "image")
        if not media_url:
            continue
        if remaining_carousel_bytes <= 0:
            raise RuntimeError("Carrossel do Instagram excede limite agregado de tamanho.")
        media_path = _download_instagram_embed_item(
            media_url,
            out_dir,
            index,
            media_type,
            max_bytes=min(_INSTAGRAM_EMBED_ITEM_MAX_BYTES, remaining_carousel_bytes),
        )
        if media_path:
            media_paths.append(media_path)
            remaining_carousel_bytes -= media_path.stat().st_size

    if not media_paths:
        return None

    warnings: list[str] = []
    if len(media_paths) > 1:
        warnings.append(
            f"Carrossel do Instagram detectado; {len(media_paths)} itens baixados via embed."
        )

    return DownloadedMedia(
        primary_path=media_paths[0],
        media_paths=media_paths,
        metadata=_metadata_from_instagram_embed(source, media),
        warnings=warnings,
    )


def _read_instagram_embed_page(embed_url: str) -> str:
    validate_public_download_url(embed_url)
    request = Request(embed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        return response.read(2 * 1024 * 1024).decode("utf-8", errors="replace")


def _extract_instagram_embed_media(page: str) -> dict | None:
    match = re.search(r'"contextJSON":"((?:\\.|[^"\\])*)"', page)
    if not match:
        return None
    try:
        context_json = json.loads(f'"{match.group(1)}"')
        payload = json.loads(context_json)
    except json.JSONDecodeError:
        return None
    context = payload.get("context") or {}
    media = context.get("media") or {}
    if media:
        return media
    return (payload.get("gql_data") or {}).get("shortcode_media") or None


def _instagram_media_items(media: dict) -> list[dict[str, str]]:
    edges = (media.get("edge_sidecar_to_children") or {}).get("edges") or []
    nodes = [edge.get("node") or {} for edge in edges if isinstance(edge, dict)]
    if not nodes:
        nodes = [media]

    items: list[dict[str, str]] = []
    for node in nodes:
        typename = str(node.get("__typename") or "")
        if typename == "GraphVideo" and node.get("video_url"):
            items.append({"type": "video", "url": str(node["video_url"])})
        elif node.get("display_url"):
            items.append({"type": "image", "url": str(node["display_url"])})
    return items


def _download_instagram_embed_item(
    media_url: str,
    out_dir: Path,
    index: int,
    media_type: str,
    max_bytes: int = _INSTAGRAM_EMBED_ITEM_MAX_BYTES,
) -> Path | None:
    if max_bytes <= 0:
        raise RuntimeError("Item do carrossel excede VIDEO_KB_MAX_DOWNLOAD_BYTES.")
    validate_public_download_url(media_url)
    suffix = Path(urlparse(media_url).path).suffix.lower()
    if media_type == "image":
        suffix = ".jpg" if suffix not in {".jpg", ".jpeg", ".png", ".webp"} else suffix
    elif suffix not in {".mp4", ".mov", ".m4v", ".webm"}:
        suffix = ".mp4"
    target = out_dir / f"source_{index:02d}{suffix}"
    request = Request(
        media_url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.instagram.com/",
        },
    )
    with urlopen(request, timeout=30) as response:
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=out_dir, prefix=f"{target.name}.", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                downloaded = 0
                while True:
                    chunk = response.read(_INSTAGRAM_EMBED_CHUNK_SIZE)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError(
                            "Item do carrossel excede VIDEO_KB_MAX_DOWNLOAD_BYTES."
                        )
                    temp_file.write(chunk)
            temp_path.replace(target)
        except Exception:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            raise
    return target


def _instagram_caption(media: dict) -> str:
    edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
    for edge in edges:
        node = edge.get("node") if isinstance(edge, dict) else None
        text = node.get("text") if isinstance(node, dict) else ""
        if text:
            return str(text)
    return ""


def _read_open_graph_page(source: str) -> _OpenGraphPage:
    validate_public_download_url(source)
    request = Request(source, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=30) as response:
        body = response.read(2 * 1024 * 1024)
    parser = _OpenGraphPage()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser
