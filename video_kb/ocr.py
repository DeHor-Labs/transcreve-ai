import re
import subprocess
from pathlib import Path

from .utils import which


def available_tesseract_languages() -> list[str]:
    if not which("tesseract"):
        return []
    proc = subprocess.run(
        ["tesseract", "--list-langs"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return sorted(
        line.strip()
        for line in output.splitlines()
        if line.strip() and not line.lower().startswith("list of")
    )


def choose_language(preferred: str) -> tuple[str, str]:
    available = set(available_tesseract_languages())
    if not available:
        return "", "tesseract is not available; OCR skipped"

    requested = [part for part in re.split(r"[+,]", preferred or "") if part]
    supported = [part for part in requested if part in available]
    if supported:
        return "+".join(supported), ""
    if "eng" in available:
        return "eng", f"Requested OCR language '{preferred}' is unavailable; using eng"
    return sorted(available)[0], f"Requested OCR language '{preferred}' is unavailable"


def ocr_image(image_path: Path, language: str) -> str:
    if not language:
        return ""
    proc = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", language, "--psm", "6"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if proc.returncode != 0:
        return ""
    return "\n".join(line.strip() for line in proc.stdout.splitlines() if line.strip())
