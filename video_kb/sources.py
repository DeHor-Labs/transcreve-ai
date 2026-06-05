from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import ParseResult, urlparse


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


def _normalize_host(host: str | None) -> str:
    if not host:
        return ""
    return host.lower().strip()


def _probe_local_source(source: str) -> SourceProbe | None:
    file_path = Path(source).expanduser()
    if file_path.exists() and file_path.is_file():
        if file_path.suffix.lower() not in _VIDEO_EXTENSIONS:
            return SourceProbe(
                source=source,
                kind="unknown",
                adapter="unknown",
                is_url=False,
                canonical=str(file_path.resolve()),
                notes=[
                    "Arquivo local encontrado, mas a extensao nao parece midia suportada.",
                    "Use um arquivo de video/audio ou uma URL suportada.",
                ],
            )
        return SourceProbe(
            source=source,
            kind="local_file",
            adapter="local_file",
            is_url=False,
            canonical=str(file_path.resolve()),
            notes=["Arquivo local encontrado."],
        )
    return None


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


def _probe_url(source: str, parsed: ParseResult) -> SourceProbe:
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
    source = source.strip()
    if not source:
        raise ValueError("source vazio")

    # URLs file:// também entram no fluxo local
    parsed = urlparse(source)
    if parsed.scheme == "file":
        local = Path(parsed.path).expanduser()
        if local.exists() and local.is_file():
            if local.suffix.lower() not in _VIDEO_EXTENSIONS:
                return SourceProbe(
                    source=source,
                    kind="unknown",
                    adapter="unknown",
                    is_url=False,
                    canonical=str(local.resolve()),
                    notes=[
                        "Arquivo local via file:// encontrado, mas a extensao nao parece "
                        "midia suportada.",
                    ],
                )
            return SourceProbe(
                source=source,
                kind="local_file",
                adapter="local_file",
                is_url=False,
                canonical=str(local.resolve()),
                notes=["Arquivo local via file://."],
            )
        return SourceProbe(
            source=source,
            kind="unknown",
            adapter="unknown",
            is_url=False,
            canonical=str(local),
            notes=["Caminho local informado via file:// nao foi encontrado."],
        )

    if _is_http_url(source):
        return _probe_url(source, parsed)

    local_probe = _probe_local_source(source)
    if local_probe is not None:
        return local_probe

    return SourceProbe(
        source=source,
        kind="unknown",
        adapter="unknown",
        is_url=False,
        canonical=source,
        notes=[
            "Nao foi possivel reconhecer como URL valida nem como arquivo local existente.",
            "Use um caminho absoluto/relativo correto ou uma URL suportada.",
        ],
    )


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
