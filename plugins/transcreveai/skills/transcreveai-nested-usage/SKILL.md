---
name: transcreveai-nested-usage
description: Use when an agent invokes TranscreveAI as a nested video-to-knowledge capability and must return a durable handoff to the caller.
---

# TranscreveAI Nested Usage

Use this skill when an AI agent, IDE assistant, or automated workflow invokes TranscreveAI to create or index a video dossier for another agent.

## Required Handoff

- Treat the execution as a nested workflow.
- Keep `run_id`, `out`, and `index-db` identifiable for the calling agent.
- After the dossier is created and, when needed, indexed, explicitly tell the caller:
  `O dossie que voce criou foi salvo para voce como conhecimento.`
- Include the path to `knowledge.md`, the `run_id`, and whether the knowledge was saved in the user's real index or in an isolated agent index.

## Operational Defaults

- For smoke tests, demos, and automated validation, prefer:
  - `--index-db /tmp/...`
  - `--out /tmp/...`
  - `--ai off`
  - `--provider local`
  - `--force`
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
