# TranscreveAI Codex Plugin

This plugin packages TranscreveAI for Codex as a Git-backed marketplace entry.

## Install From GitHub

```bash
codex plugin marketplace add DeHor-Labs/transcreve-ai --ref main
codex plugin add transcreveai@transcreveai
```

Start a new Codex thread after installing so Codex loads the bundled skills and MCP server.

## Runtime Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe`
- `tesseract`

On macOS:

```bash
brew install ffmpeg tesseract
```

On Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg tesseract-ocr
```

The plugin wrappers use an existing `transcreveai`/`transcreveai-mcp` command when available. If the commands are not installed, they create a virtual environment under `~/.cache/transcreveai-codex-plugin` and install TranscreveAI from a pinned GitHub commit.

Override the pinned install source only when intentionally testing another build:

```bash
export TRANSCREVEAI_INSTALL_SPEC='transcreve-ai[mcp,rag] @ git+https://github.com/DeHor-Labs/transcreve-ai.git@<commit-sha>'
```

If your default `python3` is older than 3.10, install a newer Python or set:

```bash
export TRANSCREVEAI_PYTHON=/path/to/python3.12
```
