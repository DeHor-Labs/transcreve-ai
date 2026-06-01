# TranscreveAI

[![CI](https://github.com/nikolasdehor/transcreve-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/nikolasdehor/transcreve-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

TranscreveAI turns videos into knowledge-base dossiers. It is not only a transcription tool: it downloads the source video, extracts audio, samples frames, runs OCR, optionally uses AI to transcribe and inspect key frames, then exports structured JSON and human-readable Markdown.

It is useful when you want to send a video link and keep a durable, searchable record of what was said, shown, demonstrated, promised, or mentioned.

## What It Extracts

- Source metadata: title, URL, channel, duration, upload date and description.
- Audio artifact for later review.
- Timestamped frames sampled across the video.
- OCR from visible text on screen.
- Timestamped transcript segments when `OPENAI_API_KEY` is configured.
- Visual notes for selected frames when AI mode is enabled.
- Knowledge synthesis: summary, chapters, entities, tools/products, claims, action items and open questions.
- Two final artifacts: `analysis.json` for machines and `knowledge.md` for humans.

## Quick Start

Requirements:

- Python 3.10+ recommended.
- `ffmpeg`
- `yt-dlp`
- `tesseract`
- Optional: `OPENAI_API_KEY` for transcription, frame understanding and synthesis.

Install locally:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create local config:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
OPENAI_API_KEY=<your_openai_api_key>
VIDEO_KB_VISION_MODEL=gpt-4o-mini
VIDEO_KB_TRANSCRIBE_MODEL=whisper-1
```

Analyze a public video:

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto
```

If a platform requires login, retry with cookies:

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --cookies-browser chrome --ai auto
```

Analyze a local file:

```bash
transcreveai analyze ./video.mp4 --ai auto
```

## Output

Each run creates `outputs/<timestamp>-<slug>/`:

```text
outputs/20260601T060803Z-example/
  analysis.json
  knowledge.md
  source.mp4
  audio.mp3
  frames/
    frame_0001_00000s00.jpg
    frame_0002_00008s00.jpg
```

`knowledge.md` is optimized for reading and review. `analysis.json` is optimized for indexing, RAG pipelines, search, dashboards or future automations.

## Example Workflow

```bash
transcreveai analyze "https://youtu.be/..." \
  --out outputs \
  --frame-interval 4 \
  --max-frames 80 \
  --visual-limit 30 \
  --ai auto \
  --language pt
```

Useful defaults:

- `--ai auto`: uses AI only when `OPENAI_API_KEY` is present.
- `--ai off`: local-only mode with download, audio, frames and OCR.
- `--max-frames`: controls local frame volume.
- `--visual-limit`: controls how many frames are sent to the AI model.
- `--cookies-browser chrome`: helps with private/logged-in content, but public links should be tried without cookies first.

## Why This Exists

Most video pipelines stop at speech-to-text. Real knowledge extraction needs more:

- The screen may show tools, code, products, prices or URLs that are never spoken.
- The speaker may demonstrate a sequence visually.
- A future search should find both "what they said" and "what was on screen".
- A team needs structured data, not only a transcript blob.

TranscreveAI is the first step toward a "send a link, get a reusable knowledge artifact" workflow.

## Architecture

```text
URL or file
  -> yt-dlp download/copy
  -> ffprobe metadata
  -> ffmpeg audio extraction
  -> ffmpeg frame sampling
  -> tesseract OCR
  -> optional OpenAI transcription
  -> optional OpenAI visual frame notes
  -> optional OpenAI synthesis
  -> analysis.json + knowledge.md
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for more detail.

## Automation Shape

The CLI is designed to become a worker:

1. A webhook receives `{ "url": "..." }`.
2. A job runner executes `transcreveai analyze "$url" --ai auto`.
3. `analysis.json` is indexed in a knowledge base.
4. `knowledge.md` is saved to Git, Obsidian, Notion, Drive or returned in chat.

## Privacy And Security

- `.env` is ignored by Git and should stay local.
- `outputs/` is ignored by Git because it may contain copyrighted videos, personal data, audio, screenshots or private business context.
- Do not paste API keys into issues, commits, logs or examples.
- Rotate keys that were exposed in chat or terminal history.
- For production, use provider secrets instead of local `.env` files.

See [SECURITY.md](SECURITY.md).

## Open Source Status

This repository is prepared for open sourcing with an MIT license, CI, contribution notes and a security policy. Before making it public, run the checklist in [docs/OPEN_SOURCE_CHECKLIST.md](docs/OPEN_SOURCE_CHECKLIST.md).

My recommendation: open source it after rotating any API key that has appeared in chat/logs and after deciding whether example outputs should be synthetic only.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m unittest discover -s tests
python -m compileall video_kb tests
```

## Roadmap

See [ROADMAP.md](ROADMAP.md).

## License

MIT. See [LICENSE](LICENSE).
