<p align="center">
  <img src="assets/banner.svg" alt="TranscreveAI: from video links to searchable knowledge dossiers" width="100%">
</p>

<h1 align="center">TranscreveAI</h1>

<p align="center">
  <strong>Turn any video link into a searchable, multimodal knowledge dossier.</strong>
</p>

<p align="center">
  <a href="https://github.com/nikolasdehor/transcreve-ai/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/nikolasdehor/transcreve-ai/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-f5c542.svg"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-3b82f6.svg">
  <img alt="CLI" src="https://img.shields.io/badge/interface-CLI-14b8a6.svg">
  <img alt="Status" src="https://img.shields.io/badge/status-alpha-64748b.svg">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a>
  ·
  <a href="#what-it-builds">What It Builds</a>
  ·
  <a href="#example-output">Example Output</a>
  ·
  <a href="#architecture">Architecture</a>
  ·
  <a href="docs/CLI_REFERENCE.md">CLI Reference</a>
</p>

---

TranscreveAI is a small but serious pipeline for video intelligence. It does not stop at speech-to-text. It downloads the source video, extracts audio, samples frames, reads visible text with OCR, optionally asks AI to inspect key frames, and exports a clean dossier for humans and machines.

Use it when a video contains the kind of knowledge that gets lost in a plain transcript: tools shown on screen, UI flows, product names, prompts, dashboards, code snippets, visual steps, claims, and decisions.

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto --language pt
```

## What It Builds

Every run produces a self-contained folder:

```text
outputs/20260601T060803Z-example/
  analysis.json      # structured data for indexing, RAG, search, dashboards
  knowledge.md       # readable dossier with summary, chapters and timeline
  source.mp4         # downloaded or copied source video
  audio.mp3          # extracted audio
  frames/            # timestamped frame evidence
```

The generated dossier includes:

| Layer | What TranscreveAI captures |
| --- | --- |
| Metadata | title, URL, channel/uploader, duration, upload date, description |
| Audio | extracted reviewable audio artifact |
| Transcript | timestamped speech segments when AI mode is enabled |
| Screen evidence | sampled frames across the video |
| OCR | visible text from slides, apps, comments, code, menus and dashboards |
| Visual notes | compact AI notes for selected frames |
| Knowledge synthesis | summary, chapters, entities, tools/products, claims, action items and open questions |

## Why It Exists

Most "video to text" workflows miss half the signal.

- The speaker says "click here", but the screen shows the actual tool and menu.
- A product, prompt, price or URL appears visually but is never spoken.
- A tutorial is valuable because of the sequence, not only the words.
- A knowledge base needs structured evidence, not a transcript blob.

TranscreveAI is built around the idea that video knowledge is multimodal by default.

## Quick Start

### 1. Install System Dependencies

Recommended:

- Python 3.10+ (`3.9` can run the current code, but some upstream tools already warn about deprecation)
- `ffmpeg`
- `yt-dlp`
- `tesseract`

On macOS:

```bash
brew install ffmpeg yt-dlp tesseract
```

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg tesseract-ocr
```

### 2. Install TranscreveAI

```bash
git clone https://github.com/nikolasdehor/transcreve-ai.git
cd transcreve-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Optional: Enable AI

Local mode works without an API key. AI mode adds transcription, visual frame notes and synthesis.

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
OPENAI_API_KEY=<your_openai_api_key>
VIDEO_KB_VISION_MODEL=gpt-4o-mini
VIDEO_KB_TRANSCRIBE_MODEL=whisper-1
```

### 4. Analyze A Video

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto --language pt
```

For local files:

```bash
transcreveai analyze ./video.mp4 --ai auto
```

For platforms that require login:

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --cookies-browser chrome --ai auto
```

## Example Output

`knowledge.md` is designed to be dropped into a knowledge base:

```md
# Video by creator

## Summary
The video demonstrates how to turn a reference clip and product image into a realistic short-form sales asset.

## Chapters
- 00:00 - Context and target video
- 00:30 - Collect source model and product references
- 00:58 - Upload inputs into the generation workflow
- 01:34 - Adjust and export the image
- 02:04 - Run motion transfer and prepare for publishing

## Timeline
### 01:14
- Speech: "Use image, 9x16, Nano Banana Pro..."
- OCR: "Nano Banana Pro", "generation will use credits"
- Visual: settings panel for image generation, aspect ratio selection, prompt workflow
```

`analysis.json` keeps the same information in structured form for indexing, search or RAG.

## CLI Examples

Balanced analysis:

```bash
transcreveai analyze "https://youtu.be/..." \
  --out outputs \
  --frame-interval 4 \
  --max-frames 80 \
  --visual-limit 30 \
  --ai auto \
  --language pt
```

Local-only, cheaper and private:

```bash
transcreveai analyze ./video.mp4 --ai off --frame-interval 3 --max-frames 60
```

More selective AI vision:

```bash
transcreveai analyze "https://youtu.be/..." --ai auto --max-frames 120 --visual-limit 16
```

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

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a deeper walkthrough.

## Automation Shape

The CLI is intentionally worker-friendly:

1. A webhook receives `{ "url": "..." }`.
2. A queue starts `transcreveai analyze "$url" --ai auto`.
3. `analysis.json` is indexed into a knowledge base.
4. `knowledge.md` is saved to Git, Obsidian, Notion, Drive or returned in chat.

Future versions can wrap the same core with a web UI, background jobs and storage adapters.

## Project Status

TranscreveAI is early but usable:

- CLI is functional.
- Local extraction works without AI.
- AI transcription, visual notes and synthesis work when configured.
- CI runs on Python 3.10, 3.11 and 3.12.
- Outputs are intentionally file-based for portability.

See [ROADMAP.md](ROADMAP.md) for what comes next.

## Privacy And Security

- `.env` is ignored by Git and should stay local.
- `outputs/` is ignored because it may contain videos, audio, screenshots and private context.
- Do not commit downloaded media or real user dossiers.
- Rotate API keys that appeared in chat, logs, screenshots or shell history.
- For production, use provider secrets instead of local `.env` files.

See [SECURITY.md](SECURITY.md).

## Development

```bash
python -m unittest discover -s tests
python -m compileall video_kb tests
```

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), [docs/CLI_REFERENCE.md](docs/CLI_REFERENCE.md) and [docs/OPEN_SOURCE_CHECKLIST.md](docs/OPEN_SOURCE_CHECKLIST.md).

## License

MIT. See [LICENSE](LICENSE).
