import json
import math
from pathlib import Path

from .utils import CommandError, ensure_dir, run_command

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def probe_duration(media_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(media_path),
    ]
    proc = run_command(command)
    payload = json.loads(proc.stdout or "{}")
    duration = payload.get("format", {}).get("duration")
    return float(duration or 0)


def extract_audio(media_path: Path, audio_path: Path) -> Path:
    ensure_dir(audio_path.parent)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(audio_path),
    ]
    run_command(command)
    return audio_path


def _sample_timestamps(duration: float, interval: float, max_frames: int) -> list[float]:
    duration = max(0.0, duration)
    interval = max(1.0, interval)
    if duration <= 0:
        return [0.0]

    timestamps = []
    current = 0.0
    while current <= duration:
        timestamps.append(round(current, 2))
        current += interval

    if max_frames > 0 and len(timestamps) > max_frames:
        if max_frames == 1:
            return [0.0]
        step = (len(timestamps) - 1) / float(max_frames - 1)
        selected = []
        seen = set()
        for index in range(max_frames):
            pos = int(round(index * step))
            value = timestamps[min(pos, len(timestamps) - 1)]
            if value not in seen:
                selected.append(value)
                seen.add(value)
        return selected
    return timestamps


def extract_frames(
    media_path: Path,
    frames_dir: Path,
    duration: float,
    interval: float = 5.0,
    max_frames: int = 80,
    width: int = 1280,
    start_index: int = 1,
    timestamp_offset: float = 0.0,
) -> list[Path]:
    ensure_dir(frames_dir)
    if media_path.suffix.lower() in _IMAGE_SUFFIXES:
        return _extract_static_image_frame(
            media_path,
            frames_dir,
            width=width,
            index=start_index,
            timestamp=timestamp_offset,
        )

    frame_paths = []
    timestamps = _sample_timestamps(duration, interval, max_frames)
    max_index = start_index + max(0, len(timestamps) - 1)
    digits = max(4, int(math.log10(max(1, max_index))) + 1)

    for index, timestamp in enumerate(timestamps, start=start_index):
        output = frames_dir / (
            f"frame_{index:0{digits}d}_{_safe_ts(timestamp + timestamp_offset)}.jpg"
        )
        command = [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            str(media_path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "3",
            str(output),
        ]
        try:
            run_command(command)
        except CommandError:
            continue
        if output.exists() and output.stat().st_size > 0:
            frame_paths.append(output)
    return frame_paths


def _extract_static_image_frame(
    media_path: Path,
    frames_dir: Path,
    width: int,
    index: int,
    timestamp: float,
) -> list[Path]:
    digits = max(4, int(math.log10(max(1, index))) + 1)
    output = frames_dir / f"frame_{index:0{digits}d}_{_safe_ts(timestamp)}.jpg"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(media_path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={width}:-2",
        "-q:v",
        "3",
        "-update",
        "1",
        str(output),
    ]
    try:
        run_command(command)
    except CommandError:
        return []
    if output.exists() and output.stat().st_size > 0:
        return [output]
    return []


def split_audio(audio_path: Path, chunks_dir: Path, segment_seconds: int = 600) -> list[Path]:
    ensure_dir(chunks_dir)
    pattern = chunks_dir / "chunk_%03d.mp3"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(audio_path),
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        "-c",
        "copy",
        str(pattern),
    ]
    run_command(command)
    return sorted(chunks_dir.glob("chunk_*.mp3"))


def _safe_ts(timestamp: float) -> str:
    return (f"{timestamp:08.2f}").replace(".", "s")
