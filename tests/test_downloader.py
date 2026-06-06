from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_kb.downloader import (
    UnsafeDownloadUrlError,
    fetch_media,
    fetch_media_bundle,
    validate_public_download_url,
)


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self._read = False

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, *_args: object) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self.body


class TestDownloaderSafety(unittest.TestCase):
    def test_validate_public_download_url_blocks_private_targets(self) -> None:
        blocked = [
            "http://localhost/video.mp4",
            "http://127.0.0.1/video.mp4",
            "http://[::1]/video.mp4",
            "http://10.0.0.5/video.mp4",
            "http://172.16.0.5/video.mp4",
            "http://192.168.1.5/video.mp4",
            "http://169.254.169.254/latest/meta-data/",
        ]
        for source in blocked:
            with self.subTest(source=source):
                with self.assertRaises(UnsafeDownloadUrlError):
                    validate_public_download_url(source, resolve_dns=False)

    def test_validate_public_download_url_rejects_embedded_credentials(self) -> None:
        with self.assertRaises(UnsafeDownloadUrlError):
            validate_public_download_url(
                "https://user:secret@example.com/video.mp4",
                resolve_dns=False,
            )

    def test_fetch_media_accepts_file_url_as_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source = tmp_path / "video com espaco.mp4"
            source.write_bytes(b"dummy video")

            media_path, metadata = fetch_media(source.as_uri(), tmp_path / "out")

            self.assertEqual(media_path.name, "source.mp4")
            self.assertEqual(media_path.read_bytes(), b"dummy video")
            self.assertEqual(metadata.source, source.as_uri())
            self.assertEqual(metadata.title, "video com espaco")

    def test_fetch_media_falls_back_to_open_graph_image_when_no_video_formats(self) -> None:
        import yt_dlp

        class FakeYdl:
            def __init__(self, _opts: dict) -> None:
                pass

            def __enter__(self) -> FakeYdl:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def extract_info(self, _source: str, download: bool) -> dict:
                assert download is True
                raise yt_dlp.utils.DownloadError("ERROR: No video formats found!")

        html = (
            b'<meta property="og:title" content="Post de teste">'
            b'<meta property="og:description" content="Descricao">'
            b'<meta property="og:image" content="https://cdn.example.com/slide.jpg">'
        )
        image = b"fake-jpeg"

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            responses = [_FakeResponse(html), _FakeResponse(image)]
            with patch("yt_dlp.YoutubeDL", FakeYdl):
                with patch("video_kb.downloader.validate_public_download_url"):
                    with patch(
                        "video_kb.downloader.urlopen",
                        side_effect=lambda *_args, **_kwargs: responses.pop(0),
                    ):
                        media_path, metadata = fetch_media(
                            "https://example.com/post",
                            tmp_path / "out",
                        )

            self.assertEqual(media_path.name, "source.jpg")
            self.assertEqual(media_path.read_bytes(), image)
            self.assertEqual(metadata.title, "Post de teste")
            self.assertEqual(metadata.description, "Descricao")

    def test_fetch_media_bundle_reads_instagram_embed_carousel_images(self) -> None:
        import yt_dlp

        class FakeYdl:
            def __init__(self, _opts: dict) -> None:
                pass

            def __enter__(self) -> FakeYdl:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def extract_info(self, _source: str, download: bool) -> dict:
                assert download is True
                raise yt_dlp.utils.DownloadError("ERROR: No video formats found!")

        context = {
            "context": {
                "media": {
                    "__typename": "GraphSidecar",
                    "owner": {"username": "maestroprompts", "full_name": "Maestro"},
                    "edge_media_to_caption": {
                        "edges": [{"node": {"text": "Comenta PROMPT"}}]
                    },
                    "edge_sidecar_to_children": {
                        "edges": [
                            {
                                "node": {
                                    "__typename": "GraphImage",
                                    "display_url": "https://cdn.example.com/slide-1.heic",
                                }
                            },
                            {
                                "node": {
                                    "__typename": "GraphImage",
                                    "display_url": "https://cdn.example.com/slide-2.heic",
                                }
                            },
                        ]
                    },
                }
            }
        }
        html = (
            '<script>"contextJSON":'
            f"{json.dumps(json.dumps(context))}"
            "</script>"
        ).encode()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            responses = [
                _FakeResponse(html),
                _FakeResponse(b"slide-1"),
                _FakeResponse(b"slide-2"),
            ]
            with patch("yt_dlp.YoutubeDL", FakeYdl):
                with patch("video_kb.downloader.validate_public_download_url"):
                    with patch(
                        "video_kb.downloader.urlopen",
                        side_effect=lambda *_args, **_kwargs: responses.pop(0),
                    ):
                        media = fetch_media_bundle(
                            "https://www.instagram.com/p/example/",
                            tmp_path / "out",
                        )

            self.assertEqual(
                [path.name for path in media.media_paths],
                ["source_01.jpg", "source_02.jpg"],
            )
            self.assertEqual(media.media_paths[0].read_bytes(), b"slide-1")
            self.assertEqual(media.media_paths[1].read_bytes(), b"slide-2")
            self.assertEqual(media.metadata.extractor, "instagram_embed")
            self.assertEqual(media.metadata.channel, "maestroprompts")
            self.assertIn("Carrossel do Instagram detectado", media.warnings[0])

    def test_fetch_media_bundle_rejects_oversized_instagram_embed_item(self) -> None:
        import yt_dlp

        class FakeYdl:
            def __init__(self, _opts: dict) -> None:
                pass

            def __enter__(self) -> FakeYdl:
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def extract_info(self, _source: str, download: bool) -> dict:
                assert download is True
                raise yt_dlp.utils.DownloadError("ERROR: No video formats found!")

        context = {
            "context": {
                "media": {
                    "__typename": "GraphSidecar",
                    "owner": {"username": "maestroprompts", "full_name": "Maestro"},
                    "edge_media_to_caption": {
                        "edges": [{"node": {"text": "Comenta PROMPT"}}]
                    },
                    "edge_sidecar_to_children": {
                        "edges": [
                            {
                                "node": {
                                    "__typename": "GraphImage",
                                    "display_url": "https://cdn.example.com/slide-1.heic",
                                }
                            }
                        ]
                    },
                }
            }
        }
        html = (
            '<script>"contextJSON":'
            f"{json.dumps(json.dumps(context))}"
            "</script>"
        ).encode()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            out_dir = tmp_path / "out"
            responses = [
                _FakeResponse(html),
                _FakeResponse(b"0123456789"),
            ]
            with patch(
                "video_kb.downloader._INSTAGRAM_EMBED_ITEM_MAX_BYTES", 5
            ), patch("yt_dlp.YoutubeDL", FakeYdl):
                with patch("video_kb.downloader.validate_public_download_url"):
                    with patch(
                        "video_kb.downloader.urlopen",
                        side_effect=lambda *_args, **_kwargs: responses.pop(0),
                    ):
                        with self.assertRaises(RuntimeError):
                            fetch_media_bundle(
                                "https://www.instagram.com/p/example/",
                                out_dir,
                            )

            self.assertEqual(list(out_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
