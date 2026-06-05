from __future__ import annotations

import os
import socket
import tempfile
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path
from urllib.parse import ParseResult, unquote, urlparse


@dataclass(frozen=True)
class SourceProbe:
    source: str
    kind: str
    adapter: str
    is_url: bool
    canonical: str
    requires_cookies: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["notes"] = list(self.notes)
        return data


class UnsafeSourceUrlError(ValueError):
    """Raised when a URL is unsafe to classify for server-side processing."""


_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mov",
        ".webm",
        ".mkv",
        ".avi",
        ".flv",
        ".mpg",
        ".mpeg",
        ".mp3",
        ".m3u8",
        ".ogg",
        ".ogv",
        ".wav",
        ".aac",
        ".m4a",
        ".3gp",
    }
)

_KNOWN_HOSTS_REQUIRING_COOKIES: frozenset[str] = frozenset(
    {
        "instagram.com",
        "www.instagram.com",
        "m.instagram.com",
        "linkedin.com",
        "www.linkedin.com",
        "www.tiktok.com",
        "tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
        "x.com",
        "www.x.com",
        "twitter.com",
        "www.twitter.com",
        "twitch.tv",
        "www.twitch.tv",
    }
)

_KNOWN_HOSTS: set[str] = {
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "vt.tiktok.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "vimeo.com",
    "www.vimeo.com",
    "player.vimeo.com",
    "linkedin.com",
    "www.linkedin.com",
    "reddit.com",
    "www.reddit.com",
    "old.reddit.com",
    "v.redd.it",
    "preview.redd.it",
    "twitch.tv",
    "www.twitch.tv",
    "drive.google.com",
    "docs.google.com",
    "www.googleusercontent.com",
    "dropbox.com",
    "www.dropbox.com",
    "loom.com",
    "www.loom.com",
    "www.loom.host",
}

_LINKEDIN_HOSTS = frozenset({"linkedin.com", "www.linkedin.com"})
_REDDIT_HOSTS = frozenset(
    {
        "reddit.com",
        "www.reddit.com",
        "old.reddit.com",
        "v.redd.it",
        "preview.redd.it",
    }
)
_TWITCH_HOSTS = frozenset({"twitch.tv", "www.twitch.tv", "m.twitch.tv"})
_GOOGLE_DRIVE_HOSTS = frozenset({"drive.google.com", "docs.google.com"})
_DROPBOX_HOSTS = frozenset({"dropbox.com", "www.dropbox.com"})
_LOCAL_SOURCE_ROOTS_ENV = "VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS"
_LOCAL_SOURCE_AUTHZ_NOTE = (
    "detect_source apenas classifica a fonte; valide autorizacao e permissoes "
    "antes de ler qualquer arquivo local."
)


def _normalize_host(host: str | None) -> str:
    if not host:
        return ""
    return host.lower().strip().rstrip(".")


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _allowed_local_source_roots() -> tuple[Path, ...]:
    roots = [Path.cwd(), Path(tempfile.gettempdir())]
    configured_roots = os.environ.get(_LOCAL_SOURCE_ROOTS_ENV, "")
    roots.extend(Path(raw) for raw in configured_roots.split(os.pathsep) if raw.strip())

    resolved_roots: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        resolved = _resolve_path(root)
        key = str(resolved)
        if key not in seen:
            resolved_roots.append(resolved)
            seen.add(key)
    return tuple(resolved_roots)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_allowed_local_source_path(resolved_path: Path) -> bool:
    return any(
        resolved_path == root or _is_relative_to(resolved_path, root)
        for root in _allowed_local_source_roots()
    )


def _probe_local_path(source: str, file_path: Path, *, via_file_url: bool) -> SourceProbe:
    expanded_path = file_path.expanduser()
    resolved_path = _resolve_path(expanded_path)
    canonical = str(resolved_path)
    source_label = " via file://" if via_file_url else ""

    if not _is_allowed_local_source_path(resolved_path):
        return SourceProbe(
            source=source,
            kind="unknown",
            adapter="unknown",
            is_url=False,
            canonical=str(expanded_path),
            notes=[
                f"Caminho local{source_label} fora das raizes permitidas para probe.",
                f"Configure {_LOCAL_SOURCE_ROOTS_ENV} para liberar raizes adicionais.",
                _LOCAL_SOURCE_AUTHZ_NOTE,
            ],
        )

    if not expanded_path.exists() or not expanded_path.is_file():
        return SourceProbe(
            source=source,
            kind="unknown",
            adapter="unknown",
            is_url=False,
            canonical=str(expanded_path),
            notes=[f"Caminho local informado{source_label} nao foi encontrado."],
        )

    if expanded_path.suffix.lower() not in _VIDEO_EXTENSIONS:
        return SourceProbe(
            source=source,
            kind="unknown",
            adapter="unknown",
            is_url=False,
            canonical=canonical,
            notes=[
                f"Arquivo local{source_label} encontrado, mas a extensao nao parece "
                "midia suportada.",
                "Use um arquivo de video/audio ou uma URL suportada.",
                _LOCAL_SOURCE_AUTHZ_NOTE,
            ],
        )

    return SourceProbe(
        source=source,
        kind="local_file",
        adapter="local_file",
        is_url=False,
        canonical=canonical,
        notes=[f"Arquivo local{source_label} encontrado.", _LOCAL_SOURCE_AUTHZ_NOTE],
    )


def _probe_local_source(source: str) -> SourceProbe:
    return _probe_local_path(source, Path(source), via_file_url=False)


def _is_http_url(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"}


def _direct_media_extension(parsed: ParseResult) -> str | None:
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in _VIDEO_EXTENSIONS):
        for ext in _VIDEO_EXTENSIONS:
            if path.endswith(ext):
                return ext
    # Alguns cdn servem por subpath com querystring:
    # .../download?id=...&ext=mp4
    query = parsed.query.lower()
    if "ext=mp4" in query:
        return ".mp4"
    if "ext=m3u8" in query:
        return ".m3u8"
    return None


def _is_direct_media_url(parsed: ParseResult) -> bool:
    return _direct_media_extension(parsed) is not None


def _is_google_drive_public(parsed: ParseResult) -> bool:
    host = _normalize_host(parsed.hostname)
    path = (parsed.path or "").lower()
    query = parsed.query.lower()
    if host != "drive.google.com":
        return False
    if "/file/d/" in path:
        return True
    return "id=" in query or "export=download" in query


def _requires_twitch_cookies(path: str) -> bool:
    return "/videos/" in path or "/clips/" in path


def _parse_ip_address(value: str) -> IPv4Address | IPv6Address | None:
    normalized = value.strip().strip("[]").split("%", 1)[0]
    try:
        return ip_address(normalized)
    except ValueError:
        return None


def _is_forbidden_probe_ip(address: IPv4Address | IPv6Address) -> bool:
    return (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _raise_if_forbidden_host(host: str) -> None:
    normalized = _normalize_host(host).strip("[]")
    if not normalized:
        raise UnsafeSourceUrlError("URL sem host.")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise UnsafeSourceUrlError("URL aponta para host local.")

    address = _parse_ip_address(normalized)
    if address is not None and _is_forbidden_probe_ip(address):
        raise UnsafeSourceUrlError("URL aponta para IP local/privado/reservado.")


def _validate_public_probe_url(source: str, parsed: ParseResult) -> None:
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise UnsafeSourceUrlError("URL de fonte deve usar http(s).")
    if parsed.username or parsed.password:
        raise UnsafeSourceUrlError("URL de fonte nao pode incluir credenciais.")

    try:
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise UnsafeSourceUrlError("URL de fonte tem host ou porta invalida.") from exc

    _raise_if_forbidden_host(host)

    try:
        infos = socket.getaddrinfo(host, port or None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeSourceUrlError(f"Nao foi possivel resolver DNS para '{host}'.") from exc

    if not infos:
        raise UnsafeSourceUrlError(f"Nao foi possivel resolver DNS para '{host}'.")

    for *_, sockaddr in infos:
        resolved_host = str(sockaddr[0])
        address = _parse_ip_address(resolved_host)
        if address is None or _is_forbidden_probe_ip(address):
            raise UnsafeSourceUrlError("URL resolve para IP local/privado/reservado.")


def _probe_url(source: str, parsed: ParseResult) -> SourceProbe:
    _validate_public_probe_url(source, parsed)

    host = _normalize_host(parsed.hostname)
    path = (parsed.path or "").lower()

    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
        return SourceProbe(
            source=source,
            kind="youtube",
            adapter="youtube",
            is_url=True,
            canonical=source,
        )

    if host in _LINKEDIN_HOSTS:
        return SourceProbe(
            source=source,
            kind="linkedin",
            adapter="linkedin",
            is_url=True,
            canonical=source,
            requires_cookies=True,
            notes=[
                "LinkedIn pode exigir autenticacao e cookies dependendo da visibilidade "
                "do conteudo."
            ],
        )

    if host in _REDDIT_HOSTS:
        return SourceProbe(
            source=source,
            kind="reddit",
            adapter="reddit",
            is_url=True,
            canonical=source,
            notes=[
                "Reddit: se o yt-dlp retornar pagina de player, tente extrair o .m3u8 ou "
                "usar fallback de URL direta."
            ],
        )

    if host in _TWITCH_HOSTS:
        requires_twitch_cookies = _requires_twitch_cookies(path)
        notes = []
        if requires_twitch_cookies:
            notes.append("Twitch pode exigir cookies para clips/VOD protegidos.")

        return SourceProbe(
            source=source,
            kind="twitch",
            adapter="twitch",
            is_url=True,
            canonical=source,
            requires_cookies=requires_twitch_cookies,
            notes=notes,
        )

    if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
        if "/reel" in path or "/reels" in path:
            return SourceProbe(
                source=source,
                kind="instagram_reel",
                adapter="instagram_reel",
                is_url=True,
                canonical=source,
                requires_cookies=True,
                notes=["Reels costuma exigir cookies para alguns conteudos."],
            )
        return SourceProbe(
            source=source,
            kind="instagram",
            adapter="instagram",
            is_url=True,
            canonical=source,
            requires_cookies=True,
            notes=["Instagram pode solicitar login; cookies ajudam se houver bloqueio."],
        )

    if host in {"tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}:
        return SourceProbe(
            source=source,
            kind="tiktok",
            adapter="tiktok",
            is_url=True,
            canonical=source,
            requires_cookies=True,
            notes=["TikTok costuma bloquear sem autenticacao."],
        )

    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        return SourceProbe(
            source=source,
            kind="x_twitter",
            adapter="x_twitter",
            is_url=True,
            canonical=source,
            requires_cookies=True,
            notes=["Pode exigir cookies se o conteudo for protegido ou com bloqueio."],
        )

    if host in {"vimeo.com", "www.vimeo.com", "player.vimeo.com"}:
        return SourceProbe(
            source=source,
            kind="vimeo",
            adapter="vimeo",
            is_url=True,
            canonical=source,
        )

    if host.endswith("loom.com") or host in {"www.loom.host", "loom.com"}:
        return SourceProbe(
            source=source,
            kind="loom",
            adapter="loom",
            is_url=True,
            canonical=source,
        )

    if host in _GOOGLE_DRIVE_HOSTS and _is_google_drive_public(parsed):
        return SourceProbe(
            source=source,
            kind="google_drive",
            adapter="google_drive",
            is_url=True,
            canonical=source,
            notes=[
                "Google Drive publico detectado. Se o fluxo falhar, converta para "
                "uc?export=download&id=... "
                "e valide o novo URL."
            ],
        )

    if host in _DROPBOX_HOSTS:
        return SourceProbe(
            source=source,
            kind="dropbox",
            adapter="dropbox",
            is_url=True,
            canonical=source,
            notes=[
                "Dropbox publico detectado. Links com ?raw=1 ou ?dl=1 normalmente "
                "evitam pagina HTML."
            ],
        )

    direct_media_ext = _direct_media_extension(parsed)
    if direct_media_ext == ".m3u8":
        return SourceProbe(
            source=source,
            kind="direct_m3u8",
            adapter="yt_dlp_direct_media",
            is_url=True,
            canonical=source,
            notes=[
                "URL de stream HLS (.m3u8) detectada; tratar como fonte direta quando possivel."
            ],
        )

    if direct_media_ext is not None:
        return SourceProbe(
            source=source,
            kind="direct_media_url",
            adapter="yt_dlp_direct_media",
            is_url=True,
            canonical=source,
            notes=["URL com extensao de arquivo de mídia."],
        )

    if host in _KNOWN_HOSTS:
        return SourceProbe(
            source=source,
            kind="generic_yt_dlp_url",
            adapter="yt_dlp_generic",
            is_url=True,
            canonical=source,
            requires_cookies=host in _KNOWN_HOSTS_REQUIRING_COOKIES,
            notes=[
                "Sem adapter dedicado para este host; usando yt-dlp com parser generico.",
                "Se falhar, tente --cookies-browser <chrome|firefox> ou --cookies cookies.txt.",
            ],
        )

    return SourceProbe(
        source=source,
        kind="generic_yt_dlp_url",
        adapter="yt_dlp_generic",
        is_url=True,
        canonical=source,
        notes=["Detector dedicado nao aplicou; fallback para yt-dlp generico."],
    )


def detect_source(source: str) -> SourceProbe:
    """Classify a source.

    This is a best-effort classifier, not authorization to read local files or fetch
    remote URLs. Callers must enforce their own access policy before consuming a source.
    """
    source = source.strip()
    if not source:
        raise ValueError("source vazio")

    # URLs file:// também entram no fluxo local
    parsed = urlparse(source)
    if parsed.scheme == "file":
        if parsed.netloc and _normalize_host(parsed.netloc) != "localhost":
            return SourceProbe(
                source=source,
                kind="unknown",
                adapter="unknown",
                is_url=False,
                canonical=source,
                notes=["URL file:// com host remoto nao e suportada."],
            )
        return _probe_local_path(source, Path(unquote(parsed.path)), via_file_url=True)

    if _is_http_url(source):
        return _probe_url(source, parsed)

    return _probe_local_source(source)


def needs_cookie_message(probe: SourceProbe) -> str | None:
    if not probe.requires_cookies:
        return None
    if probe.notes:
        return " ".join(n for n in probe.notes if n)
    return "Essa fonte pode exigir autenticacao/cookies para download."


def is_direct_media_ext(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXTENSIONS


def iter_supported_kinds() -> Iterable[str]:
    return (
        "local_file",
        "youtube",
        "instagram",
        "instagram_reel",
        "tiktok",
        "x_twitter",
        "linkedin",
        "reddit",
        "twitch",
        "google_drive",
        "dropbox",
        "direct_m3u8",
        "vimeo",
        "loom",
        "direct_media_url",
        "generic_yt_dlp_url",
        "unknown",
    )
