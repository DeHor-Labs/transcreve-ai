from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import video_kb


def test_version_constant_is_present() -> None:
    assert isinstance(video_kb.__version__, str)
    assert video_kb.__version__ != ""


def test_cli_build_parser_smoke() -> None:
    from video_kb.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["runs", "list", "--limit", "1"])

    assert args.command == "runs"
    assert args.runs_command == "list"


def test_cli_help_invocation_smoke() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "video_kb", "--help"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "TranscreveAI" in result.stdout
