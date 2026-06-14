---
name: transcreveai-video-intelligence
description: Use to turn video URLs or media files into evidence-backed knowledge dossiers with TranscreveAI. Trigger on Reels, YouTube, TikTok, Loom, Vimeo, X/Twitter video links, local media files, video summaries, dossier requests, RAG over video runs, or requests to use TranscreveAI.
---

# TranscreveAI Video Intelligence

Use this skill when the user sends a video URL/file or asks Codex to extract, summarize, analyze, index, or ask questions about video content with TranscreveAI.

## Tooling Preference

- Prefer the TranscreveAI MCP tools when available:
  - `sources_probe` for source pre-checks.
  - `agent_run` for the full probe/analyze/index/ask workflow.
  - `agent_batch` for saved lists of sources.
  - `index`, `ask`, `runs_list`, and `runs_show` for retrieval.
- If the MCP tools are not available in the current Codex thread, use the CLI.
- CLI command preference:
  - First try `transcreveai`.
  - If it is not on PATH, use the plugin wrapper at `./scripts/transcreveai` from the installed plugin root.
- MCP server command for local registration:
  - `bash ./scripts/transcreveai-mcp --transport stdio` from the installed plugin root.
- The plugin wrappers add `/opt/homebrew/bin` and `/usr/local/bin` to PATH so Homebrew FFmpeg/Tesseract installs are visible to Codex-launched processes.
- If TranscreveAI is not installed globally, the wrappers create a venv under `~/.cache/transcreveai-codex-plugin` and install `transcreve-ai[mcp,rag]` from `https://github.com/DeHor-Labs/transcreve-ai.git`.

## Required Nested Handoff

Whenever TranscreveAI is used as a nested capability for another agent or workflow:

- Keep `run_id`, `out`, and `index-db` identifiable for the caller.
- After the dossier is created and, when needed, indexed, explicitly say:
  `O dossie que voce criou foi salvo para voce como conhecimento.`
- Include the path to `knowledge.md`, the `run_id`, and whether the knowledge was saved in the user's real index or in an isolated agent index.

## Safe Defaults

- For smoke tests, demos, and automated validation, isolate state:
  - `--index-db /tmp/transcreveai-agent.db`
  - `--out /tmp/transcreveai-agent`
  - `--ai off`
  - `--provider local`
  - `--force`
- Do not expose API keys, cookie contents, or complete sensitive URLs in logs or final answers.
- Use `--cookies-browser chrome` only for user-owned browser state and only when needed for sources such as Instagram.
- Base final answers on generated artifacts, especially `knowledge.md`, `analysis.json`, and template files. Do not create a parallel manual dossier and pretend it came from TranscreveAI.
- If analysis fails before artifacts are written, check whether `ffmpeg`, `ffprobe`, and `tesseract` are visible in PATH before treating it as a TranscreveAI bug.

## Recommended Agent Flow

1. Probe the source:

```bash
transcreveai sources probe "SOURCE" --json
```

Read `kind`, `adapter`, `requires_cookies`, and `notes`. If cookies are required, prefer `--cookies-browser chrome` for user-owned sources.

2. Run the agent workflow:

```bash
transcreveai agent run "SOURCE" --json
```

For an isolated no-cost smoke:

```bash
transcreveai --index-db /tmp/transcreveai-agent.db agent run "SOURCE" \
  --out /tmp/transcreveai-agent \
  --ai off \
  --provider local \
  --force \
  --json
```

3. Add templates when useful:

- Use `--template content` for creator, marketing, product, sales, distribution, or content workflow videos.
- Use `--template skill` for videos about agents, prompts, skills, Claude, Codex, automations, or reusable workflows.
- Read generated `content.md`/`content.json`/`content.csv` and `skill.md`/`skill.json` before answering about those artifacts.

4. Read the evidence:

- Always inspect `knowledge.md`.
- Inspect `analysis.json` for structured metadata, source, paths, transcript quality, and run details.
- If the user asks a question over the run, index and query:

```bash
transcreveai index RUN_ID
transcreveai ask "QUESTION" --run-id RUN_ID --top-k 8
```

5. Report compactly:

- Summarize what the video actually supports.
- Separate evidence from inference when making product, business, or technical recommendations.
- Cite artifact paths and the `run_id`.
- State limitations when transcript, OCR, visual context, or source access was weak.

## Batch Flow

For multiple URLs or files:

```bash
transcreveai agent batch ./sources.txt \
  --template content \
  --template skill \
  --strict \
  --json
```

Use `--strict` when any failed item should block the caller. Read `success`, `ok_count`, `failed_count`, `batch.md`, `batch.json`, and per-run `template_paths`.

## Expected Artifacts

- `knowledge.md`: human-readable dossier.
- `analysis.json`: structured run metadata and analysis.
- Optional `content.md`, `content.json`, `content.csv`.
- Optional `skill.md`, `skill.json`.
- Optional `batch.md`, `batch.json` for batch runs.

## Example Starter Commands

```bash
transcreveai sources probe "https://www.instagram.com/reel/..." --json
transcreveai agent run "https://www.instagram.com/reel/..." --template content --template skill --json
transcreveai agent batch ./sources.txt --template content --template skill --json
transcreveai ask "What decisions does this video support?" --run-id RUN_ID --top-k 8
```
