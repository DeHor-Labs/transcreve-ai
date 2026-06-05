from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _run_cmd(argv: list[str]) -> tuple[str, str, int]:
    from video_kb.cli import main

    buf_out = io.StringIO()
    buf_err = io.StringIO()
    code = 0
    with patch("sys.argv", ["transcreveai"] + argv):
        with patch("sys.stdout", buf_out):
            with patch("sys.stderr", buf_err):
                try:
                    main()
                except SystemExit as exc:
                    code = int(exc.code) if exc.code is not None else 0
    return buf_out.getvalue(), buf_err.getvalue(), code


class TestCliSources(unittest.TestCase):
    def test_probe_json_returns_payload(self) -> None:
        out, err, code = _run_cmd(
            ["sources", "probe", "https://youtu.be/abc123", "--json"]
        )
        self.assertEqual(code, 0, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload.get("kind"), "youtube")
        self.assertEqual(payload.get("adapter"), "youtube")
        self.assertTrue(payload.get("is_url"))
        self.assertIn("notes", payload)

    def test_probe_json_missing_file_url_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "missing.mp4"
            out, err, code = _run_cmd(
                ["sources", "probe", missing_path.as_uri(), "--json"]
            )

        self.assertEqual(code, 0, msg=err)
        payload = json.loads(out.strip() or "{}")
        self.assertEqual(payload.get("kind"), "unknown")
        self.assertEqual(payload.get("adapter"), "unknown")
        self.assertFalse(payload.get("is_url"))
        self.assertEqual(payload.get("canonical"), str(missing_path))
        notes = " ".join(str(note) for note in payload.get("notes", []))
        self.assertIn("nao foi encontrado", notes.lower())

    def test_probe_prints_human_message(self) -> None:
        out, err, code = _run_cmd(["sources", "probe", "https://www.instagram.com/reel/abc123/"])
        self.assertEqual(code, 0, msg=err)
        output = (out + err).lower()
        self.assertIn("tipo:", output)
        self.assertIn("instagram_reel", output)
        self.assertIn("cookies", output)

    def test_probe_generic_informs_fallback(self) -> None:
        out, err, code = _run_cmd(["sources", "probe", "https://example.com/video"])
        self.assertEqual(code, 0, msg=err)
        output = (out + err).lower()
        self.assertIn("fallback", output)
        self.assertIn("yt_dlp", output)
