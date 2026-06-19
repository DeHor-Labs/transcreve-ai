# TranscreveAI Obsidian Plugin

Desktop-only Obsidian plugin that sends a local video/audio file to the
TranscreveAI CLI and writes a transcript note next to the original media file.

## What It Does

- Adds a command: `Transcribe current video or audio`.
- Adds a context-menu item for supported media files.
- Runs `transcreveai analyze <file> --json`.
- Creates or updates `video.transcricao.md` in the same folder as `video.mp4`.
- Stores temporary TranscreveAI artifacts outside the vault by default, so the
  vault folder only receives the sibling `.md` transcript note.
- Deletes the temporary run artifacts after the note is created by default.

## Requirements

Install TranscreveAI and its system dependencies first:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
brew install ffmpeg yt-dlp tesseract
```

The plugin calls `transcreveai` from Obsidian's desktop process. If Obsidian
does not inherit your shell `PATH`, set an absolute CLI path in the plugin
settings, for example:

```text
/Users/you/dev/transcreve-ai/.venv/bin/transcreveai
```

For local files, the plugin passes the vault root through
`VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS` when it invokes the CLI. This lets
TranscreveAI read the clicked media file without globally weakening local-file
access checks.

## Local Development

```bash
cd plugins/obsidian-transcreveai
npm install
npm run build
```

For a manual install, copy these files into your vault:

```text
<vault>/.obsidian/plugins/transcreveai/
  main.js
  manifest.json
```

Then enable the plugin in Obsidian settings.

## Settings

- `CLI path`: command or absolute path for the local TranscreveAI CLI.
- `Language`: language hint, default `pt`.
- `AI mode`: `auto`, `off` or `full`.
- `Provider`: optional provider override such as `openai`, `local`, `gemini`.
- `Output directory`: temporary artifact directory. Defaults outside the vault.
- `Index database`: optional `--index-db`; empty uses the user's default index.
- `Note suffix`: default `.transcricao`.
- `Supported extensions`: comma-separated media extensions.
- `Force reprocess`: passes `--force`.
- `Clean temporary artifacts`: removes the raw run files and index entry after
  the Obsidian note is created.
- `Overwrite existing transcript note`: update one sibling note per media file.
- `Include absolute artifact paths`: opt-in for writing external paths to notes.

## Output Note

The generated note includes frontmatter with the `run_id` and the
vault-relative source path. The body embeds the original media and appends the
generated `knowledge.md` dossier.
