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

    def test_short_videos_use_denser_default_sampling(self) -> None:
        from video_kb.media import _sample_timestamps

        self.assertEqual(
            _sample_timestamps(duration=11.84, interval=5.0, max_frames=80),
            [0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
        )
        self.assertEqual(
            _sample_timestamps(duration=45.0, interval=5.0, max_frames=80)[:4],
            [0.0, 3.0, 6.0, 9.0],
        )

    def test_explicit_frame_interval_is_preserved_for_short_videos(self) -> None:
        from video_kb.media import _sample_timestamps

        self.assertEqual(
            _sample_timestamps(duration=11.84, interval=10.0, max_frames=80),
            [0.0, 10.0],
        )
        self.assertEqual(
            _sample_timestamps(duration=11.84, interval=3.0, max_frames=80),
            [0.0, 3.0, 6.0, 9.0],
        )


if __name__ == "__main__":
    unittest.main()
