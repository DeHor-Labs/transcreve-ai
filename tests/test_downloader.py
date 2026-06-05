from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from video_kb.downloader import (
    UnsafeDownloadUrlError,
    fetch_media,
    validate_public_download_url,
)


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


if __name__ == "__main__":
    unittest.main()
