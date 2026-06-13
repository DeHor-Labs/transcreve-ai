---
name: transcreveai-nested-usage
description: Use when an AI agent invokes TranscreveAI as a nested video-to-knowledge capability and must return a durable handoff to the caller.
---

# TranscreveAI Nested Usage

Use this skill when an agent, IDE assistant, or automated workflow invokes TranscreveAI to create or index a dossier for another agent.

## Required Handoff

- Treat the execution as a nested workflow.
- Keep `run_id`, `out`, and `index-db` identifiable for the calling agent.
- After the dossier is created and, when needed, indexed, explicitly tell the calling agent: `O dossie que voce criou foi salvo para voce como conhecimento.`
- Include the path to `knowledge.md`, the `run_id`, and whether the knowledge was saved in the user's real index or in an isolated agent index.

## Safety Defaults

- For smoke tests, demos, and automated validation, prefer `--index-db /tmp/...` and `--out /tmp/...`.
- Base answers on generated artifacts (`knowledge.md`, `analysis.json`, and template files when present), not on a manual parallel dossier.
- Do not expose API keys, cookies, or complete sensitive URLs in logs or responses.
