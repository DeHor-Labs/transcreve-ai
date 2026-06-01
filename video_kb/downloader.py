import shutil
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from .models import SourceMetadata
from .utils import ensure_dir


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


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


def _find_downloaded_file(out_dir: Path) -> Optional[Path]:
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
    cookies_browser: Optional[str] = None,
    cookies: Optional[str] = None,
    video_format: str = "bv*+ba/b",
) -> Tuple[Path, SourceMetadata]:
    ensure_dir(out_dir)
    if not is_url(source):
        source_path = Path(source).expanduser().resolve()
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

    opts = {
        "format": video_format,
        "outtmpl": str(out_dir / "source.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
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
