from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_kb.sources import detect_source, iter_supported_kinds, needs_cookie_message


class TestDetectSource(unittest.TestCase):
    _DNS_RECORDS = {
        "private.example": ("10.1.2.3",),
        "dual.example": ("93.184.216.34", "192.168.1.10"),
        "ipv6-link-local.example": ("fe80::1",),
    }

    def setUp(self) -> None:
        dns_patch = patch(
            "video_kb.sources.socket.getaddrinfo",
            side_effect=self._fake_getaddrinfo,
        )
        dns_patch.start()
        self.addCleanup(dns_patch.stop)

    @classmethod
    def _fake_getaddrinfo(
        cls,
        host: str,
        port: int | None,
        *args: object,
        **kwargs: object,
    ) -> list[tuple[int, int, int, str, tuple[object, ...]]]:
        normalized = str(host).lower().strip("[]").rstrip(".")
        if normalized == "dns-failure.example":
            raise OSError("mocked DNS failure")
        addresses = cls._DNS_RECORDS.get(normalized, ("93.184.216.34",))
        resolved: list[tuple[int, int, int, str, tuple[object, ...]]] = []
        for address in addresses:
            family = socket.AF_INET6 if ":" in address else socket.AF_INET
            sockaddr: tuple[object, ...]
            if family == socket.AF_INET6:
                sockaddr = (address, port or 443, 0, 0)
            else:
                sockaddr = (address, port or 443)
            resolved.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
        return resolved

    def test_local_file_is_detected(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as handle:
            handle.write(b"dummy")
            handle.flush()
            probe = detect_source(handle.name)

        self.assertEqual(probe.kind, "local_file")
        self.assertEqual(probe.adapter, "local_file")
        self.assertFalse(probe.is_url)
        self.assertTrue(Path(probe.canonical).exists())

    def test_youtube_is_detected(self) -> None:
        probe = detect_source("https://youtu.be/abc123")
        self.assertEqual(probe.kind, "youtube")
        self.assertEqual(probe.adapter, "youtube")
        self.assertTrue(probe.is_url)

    def test_instagram_reel_is_detected(self) -> None:
        probe = detect_source("https://www.instagram.com/reel/abc123/")
        self.assertEqual(probe.kind, "instagram_reel")
        self.assertEqual(probe.adapter, "instagram_reel")
        self.assertTrue(probe.requires_cookies)
        self.assertIn("cookies", (needs_cookie_message(probe) or "").lower())

    def test_tiktok_is_detected(self) -> None:
        probe = detect_source("https://www.tiktok.com/@user/video/9876543210")
        self.assertEqual(probe.kind, "tiktok")
        self.assertEqual(probe.adapter, "tiktok")

    def test_x_twitter_is_detected(self) -> None:
        probe = detect_source("https://x.com/someuser/status/123")
        self.assertEqual(probe.kind, "x_twitter")
        self.assertEqual(probe.adapter, "x_twitter")

    def test_linkedin_is_detected(self) -> None:
        probe = detect_source("https://www.linkedin.com/posts/example-organization/hello-world")
        self.assertEqual(probe.kind, "linkedin")
        self.assertEqual(probe.adapter, "linkedin")
        self.assertTrue(probe.requires_cookies)
        self.assertIn("cookies", (needs_cookie_message(probe) or "").lower())

    def test_vimeo_is_detected(self) -> None:
        probe = detect_source("https://vimeo.com/123456789")
        self.assertEqual(probe.kind, "vimeo")
        self.assertEqual(probe.adapter, "vimeo")

    def test_reddit_is_detected(self) -> None:
        probe = detect_source("https://www.reddit.com/r/test/comments/abc123/test")
        self.assertEqual(probe.kind, "reddit")
        self.assertEqual(probe.adapter, "reddit")
        self.assertFalse(probe.requires_cookies)

    def test_twitch_is_detected(self) -> None:
        probe = detect_source("https://www.twitch.tv/videos/123456789")
        self.assertEqual(probe.kind, "twitch")
        self.assertEqual(probe.adapter, "twitch")
        self.assertTrue(probe.requires_cookies)

    def test_google_drive_is_detected(self) -> None:
        probe = detect_source(
            "https://drive.google.com/file/d/1AbCdeFgHiJkLmNoPqRstUvWxYz/view?usp=sharing"
        )
        self.assertEqual(probe.kind, "google_drive")
        self.assertEqual(probe.adapter, "google_drive")
        self.assertFalse(probe.requires_cookies)

    def test_dropbox_is_detected(self) -> None:
        probe = detect_source("https://www.dropbox.com/s/abcd1234/video.mp4?raw=1")
        self.assertEqual(probe.kind, "dropbox")
        self.assertEqual(probe.adapter, "dropbox")
        self.assertFalse(probe.requires_cookies)

    def test_loom_is_detected(self) -> None:
        probe = detect_source("https://www.loom.com/share/test")
        self.assertEqual(probe.kind, "loom")
        self.assertEqual(probe.adapter, "loom")

    def test_direct_m3u8_is_detected(self) -> None:
        probe = detect_source("https://cdn.example.com/live/index.m3u8")
        self.assertEqual(probe.kind, "direct_m3u8")
        self.assertEqual(probe.adapter, "yt_dlp_direct_media")

    def test_direct_media_url_is_detected(self) -> None:
        probe = detect_source("https://cdn.example.com/videos/aula.mov")
        self.assertEqual(probe.kind, "direct_media_url")
        self.assertEqual(probe.adapter, "yt_dlp_direct_media")

    def test_generic_is_detected(self) -> None:
        probe = detect_source("https://example.com/video")
        self.assertEqual(probe.kind, "generic_yt_dlp_url")
        self.assertEqual(probe.adapter, "yt_dlp_generic")
        self.assertFalse(probe.requires_cookies)
        self.assertTrue(any("fallback" in note.lower() for note in probe.notes))

    def test_url_ssrf_guard_blocks_private_and_special_ip_literals(self) -> None:
        blocked_sources = [
            "http://localhost/video.mp4",
            "http://service.localhost/video.mp4",
            "http://127.0.0.1/video.mp4",
            "http://10.0.0.1/video.mp4",
            "http://172.16.0.1/video.mp4",
            "http://192.168.0.1/video.mp4",
            "http://169.254.169.254/latest/meta-data/",
            "http://0.0.0.0/video.mp4",
            "http://224.0.0.1/video.mp4",
            "http://[::1]/video.mp4",
            "http://[::]/video.mp4",
            "http://[fe80::1]/video.mp4",
            "http://[ff02::1]/video.mp4",
            "http://[::ffff:127.0.0.1]/video.mp4",
        ]

        for source in blocked_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    detect_source(source)

    def test_url_ssrf_guard_blocks_private_dns_resolution(self) -> None:
        blocked_sources = [
            "https://private.example/video.mp4",
            "https://dual.example/video.mp4",
            "https://ipv6-link-local.example/video.mp4",
        ]

        for source in blocked_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    detect_source(source)

    def test_url_ssrf_guard_blocks_dns_failure_and_credentials(self) -> None:
        blocked_sources = [
            "https://dns-failure.example/video.mp4",
            "https://user:pass@example.com/video.mp4",
        ]

        for source in blocked_sources:
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    detect_source(source)

    def test_file_url_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "file.mp4"
            file_path.write_bytes(b"dummy")
            probe = detect_source(f"file://{file_path}")

        self.assertEqual(probe.kind, "local_file")
        self.assertFalse(probe.requires_cookies)

    def test_missing_file_url_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "missing.mp4"
            probe = detect_source(file_path.as_uri())

        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")
        self.assertFalse(probe.is_url)
        self.assertEqual(probe.canonical, str(file_path))
        self.assertTrue(any("nao foi encontrado" in note.lower() for note in probe.notes))

    def test_local_file_outside_allowed_roots_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_root = Path(tmpdir) / "allowed"
            blocked_root = Path(tmpdir) / "blocked"
            allowed_root.mkdir()
            blocked_root.mkdir()
            file_path = blocked_root / "file.mp4"
            file_path.write_bytes(b"dummy")

            with patch(
                "video_kb.sources._allowed_local_source_roots",
                return_value=(allowed_root.resolve(),),
            ):
                probe = detect_source(str(file_path))

        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")
        self.assertTrue(any("raizes permitidas" in note.lower() for note in probe.notes))

    def test_file_url_reuses_local_path_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            allowed_root = Path(tmpdir) / "allowed"
            blocked_root = Path(tmpdir) / "blocked"
            allowed_root.mkdir()
            blocked_root.mkdir()
            file_path = blocked_root / "file.mp4"
            file_path.write_bytes(b"dummy")

            with patch(
                "video_kb.sources._allowed_local_source_roots",
                return_value=(allowed_root.resolve(),),
            ):
                probe = detect_source(file_path.as_uri())

        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")
        self.assertTrue(any("raizes permitidas" in note.lower() for note in probe.notes))

    def test_remote_file_url_is_unknown(self) -> None:
        probe = detect_source("file://example.com/tmp/file.mp4")

        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")
        self.assertTrue(any("host remoto" in note.lower() for note in probe.notes))

    def test_existing_non_media_file_is_unknown(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
            handle.write(b"not a video")
            handle.flush()
            probe = detect_source(handle.name)

        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")
        self.assertTrue(any("midia" in note.lower() for note in probe.notes))

    def test_unknown_path_without_file_is_marked_unknown(self) -> None:
        probe = detect_source("/tmp/nao_existe_12345_video_file")
        self.assertEqual(probe.kind, "unknown")
        self.assertEqual(probe.adapter, "unknown")

    def test_iter_supported_kinds_contains_new_sources(self) -> None:
        kinds = set(iter_supported_kinds())
        expected = {
            "linkedin",
            "reddit",
            "twitch",
            "google_drive",
            "dropbox",
            "direct_m3u8",
        }
        self.assertTrue(expected.issubset(kinds))
