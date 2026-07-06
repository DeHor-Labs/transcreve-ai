---
name: transcreveai-nested-usage
description: Use when an agent invokes TranscreveAI as a nested video-to-knowledge capability and must return a durable handoff to the caller.
---

# TranscreveAI Nested Usage

Use this skill when an AI agent, IDE assistant, or automated workflow invokes TranscreveAI to create or index a video dossier for another agent.

## Required Handoff

- Treat the execution as a nested workflow.
- Keep `run_id`, `out`, and `index-db` identifiable for the calling agent.
- Use temporary retention by default when the caller only needs extraction, summary, or an answer from YouTube, Reels, TikTok, local media, and similar sources.
- Preserve artifacts or index in the user's real knowledge base only when the caller/user asks to save, index, audit later, or reuse the dossier.
- When preservation is requested, run `transcreveai share RUN_ID --json` after analysis. If the run used an isolated index, pass the same `--index-db` or use `transcreveai share --run-dir "$RUN_DIR" --json`. The package contains `handoff.md`, `manifest.json`, `knowledge.md`, and `analysis.json`, and updates share-root `catalog.json`/`index.md`.
- If the dossier is preserved or indexed, explicitly tell the caller:
  `O dossie que voce criou foi salvo para voce como conhecimento.`
- Include the path to `knowledge.md`, the `run_id`, and whether the knowledge was saved in the user's real index or in an isolated agent index.
- If the run was temporary and cleaned up, do not claim it was saved; report the `run_id`, that the answer was based on generated artifacts, and that temporary files were removed.

## Operational Defaults

- For smoke tests, demos, and automated validation, prefer:
  - `--index-db /tmp/...`
  - `--out /tmp/...`
  - `--ai off`
  - `--provider local`
  - `--force`
- For temporary production-like agent runs, create a dedicated temp directory:
  `TMP=$(mktemp -d "${TMPDIR:-/tmp}/transcreveai-agent.XXXXXX")`,
  use `--index-db "$TMP/index.db"` and `--out "$TMP/runs"`, read the generated artifacts, then `rm -rf "$TMP"`.
- If a temporary run used the real index, remove it with `transcreveai runs rm RUN_ID --force` before deleting files.
- Base answers on generated artifacts: `knowledge.md`, `analysis.json`, and template files when present.
- Do not expose API keys, cookie contents, or complete sensitive URLs.

## CLI Fallback

If `transcreveai` is not on PATH, use the plugin wrapper:

```bash
./scripts/transcreveai --help
```

If the MCP server is needed outside an already-loaded Codex plugin context:

```bash
./scripts/transcreveai-mcp --transport stdio
```
