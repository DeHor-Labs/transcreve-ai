from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestMediaFrames(unittest.TestCase):
    def test_extract_frames_static_image_uses_single_frame_without_seek(self) -> None:
        from video_kb.media import extract_frames

        commands: list[list[str]] = []

        def fake_run_command(command: list[str]) -> object:
            commands.append(command)
            Path(command[-1]).write_bytes(b"frame")
            return object()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            image = tmp_path / "source.jpg"
            image.write_bytes(b"jpg")
            frames_dir = tmp_path / "frames"

            with patch("video_kb.media.run_command", side_effect=fake_run_command):
                frames = extract_frames(image, frames_dir, duration=0.0)

        self.assertEqual(len(frames), 1)
        self.assertNotIn("-ss", commands[0])
        self.assertIn("-update", commands[0])

    def test_extract_frames_static_image_can_continue_frame_sequence(self) -> None:
        from video_kb.media import extract_frames

        def fake_run_command(command: list[str]) -> object:
            Path(command[-1]).write_bytes(b"frame")
            return object()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            image = tmp_path / "slide.jpg"
            image.write_bytes(b"jpg")
            frames_dir = tmp_path / "frames"

            with patch("video_kb.media.run_command", side_effect=fake_run_command):
                frames = extract_frames(
                    image,
                    frames_dir,
                    duration=0.0,
                    start_index=2,
                    timestamp_offset=1.0,
                )

        self.assertEqual([frame.name for frame in frames], ["frame_0002_00001s00.jpg"])


if __name__ == "__main__":
    unittest.main()
