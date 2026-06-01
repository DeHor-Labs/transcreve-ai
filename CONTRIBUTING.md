# Contributing

Thanks for considering a contribution to TranscreveAI.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests
```

## Good First Areas

- Better scene detection and frame selection.
- More export formats such as JSONL, CSV and RAG chunks.
- Webhook worker mode.
- Better OCR language handling.
- Local transcription fallback.
- Safer and cheaper model-routing presets.

## Pull Request Checklist

- Keep secrets out of commits.
- Do not add real downloaded videos or private outputs.
- Add or update tests for behavior changes.
- Update README or docs when CLI behavior changes.
- Run:

```bash
python -m unittest discover -s tests
python -m compileall video_kb tests
```
