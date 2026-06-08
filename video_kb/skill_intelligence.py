from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .evidence import (
    detect_tool_names,
    evidence_items_to_dicts,
    get_evidence_items,
    render_evidence_item,
    tool_names_from_evidence,
)
from .models import AnalysisResult
from .utils import compact_text, format_timestamp, slugify
from .utils import unique_strings as _unique


def build_skill_intelligence(result: AnalysisResult) -> dict[str, Any]:
    """Build a reusable agent-skill draft from a video dossier."""
    text = _joined_text(result)
    name = _skill_name(result)
    summary = _summary(result)
    evidence_items = get_evidence_items(result)
    tools = _unique(
        [
            *tool_names_from_evidence(evidence_items),
            *detect_tool_names(text),
        ]
    )
    triggers = _triggers(text, result)
    steps = _workflow_steps(text, result)
    prompts = _prompt_templates(text, result)

    return {
        "kind": "skill_intelligence",
        "version": 1,
        "source": result.source,
        "run_id": result.run_id,
        "name": name,
        "description": _clip(summary, 220),
        "evidence": {
            "summary": summary,
            "tools_or_products": tools,
            "tool_evidence": evidence_items_to_dicts(
                item for item in evidence_items if item.kind == "tool_or_product"
            ),
            "claims": list(result.synthesis.claims or []),
            "actions": list(result.synthesis.action_items or []),
            "questions": list(result.synthesis.questions or []),
            "transcript_chars": len(result.transcript_text or ""),
            "frames_count": len(result.frames or []),
        },
        "skill": {
            "triggers": triggers,
            "inputs": _inputs(text),
            "workflow": steps,
            "output_contract": _output_contract(text),
            "prompt_templates": prompts,
            "safety_notes": _safety_notes(text),
        },
        "caveats": [
            "Este e um rascunho de skill derivado de evidencias do video.",
            "Revise nomes, politicas, credenciais e permissoes antes de instalar como skill real.",
        ],
    }


def render_skill_markdown(result: AnalysisResult) -> str:
    data = build_skill_intelligence(result)
    skill = data["skill"]
    evidence = data["evidence"]

    lines: list[str] = []
    lines.append("---")
    lines.append(f"name: {data['name']}")
    lines.append(f'description: "{_escape_frontmatter(data["description"])}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {data['name']}")
    lines.append("")
    lines.append(f"- Fonte: `{data['source']}`")
    lines.append(f"- Run: `{data['run_id']}`")
    if result.metadata.duration:
        lines.append(f"- Duracao: {format_timestamp(result.metadata.duration)}")
    lines.append("")

    lines.append("## Evidencia Base")
    lines.append(evidence["summary"])
    lines.append("")
    _append_list(lines, "Ferramentas/produtos", evidence["tools_or_products"])
    _append_list(
        lines,
        "Ferramentas/produtos com proveniencia",
        [
            render_evidence_item(item)
            for item in get_evidence_items(result)
            if item.kind == "tool_or_product"
        ],
    )
    _append_list(lines, "Claims", evidence["claims"])
    _append_list(lines, "Acoes extraidas", evidence["actions"])

    _append_list(lines, "Quando Usar", skill["triggers"])
    _append_list(lines, "Entradas Esperadas", skill["inputs"])

    lines.append("## Workflow")
    for index, step in enumerate(skill["workflow"], start=1):
        lines.append(f"{index}. {step}")
    lines.append("")

    _append_list(lines, "Contrato De Saida", skill["output_contract"])

    lines.append("## Prompts Base")
    for item in skill["prompt_templates"]:
        lines.append(f"### {item['name']}")
        lines.append("```text")
        lines.append(item["prompt"])
        lines.append("```")
        lines.append("")

    _append_list(lines, "Notas De Segurança", skill["safety_notes"])
    lines.append("## Limites")
    lines.extend(f"- {item}" for item in data["caveats"])
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_skill_artifacts(result: AnalysisResult, run_dir: Path) -> dict[str, str]:
    markdown_path = run_dir / "skill.md"
    json_path = run_dir / "skill.json"
    data = build_skill_intelligence(result)
    markdown_path.write_text(render_skill_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"skill": str(markdown_path), "skill_json": str(json_path)}


def _skill_name(result: AnalysisResult) -> str:
    base = result.metadata.title or result.metadata.uploader or result.source or "video-skill"
    return slugify(base, fallback="video-derived-skill")[:48]


def _summary(result: AnalysisResult) -> str:
    for value in (
        result.synthesis.summary,
        _first_sentence(result.transcript_text),
        result.metadata.description,
    ):
        if value and value.strip():
            return compact_text(value.strip(), 800)
    return "Skill derivada de um video processado pelo TranscreveAI."


def _joined_text(result: AnalysisResult) -> str:
    parts = [
        result.metadata.title,
        result.metadata.description,
        result.transcript_text,
        result.synthesis.summary,
        " ".join(result.synthesis.tools_or_products or []),
        " ".join(result.synthesis.claims or []),
        " ".join(result.synthesis.action_items or []),
        " ".join(frame.ocr_text for frame in result.frames if frame.ocr_text),
        " ".join(frame.visual_note for frame in result.frames if frame.visual_note),
    ]
    return "\n".join(part for part in parts if part)


def _triggers(text: str, result: AnalysisResult) -> list[str]:
    lower = text.lower()
    triggers = ["O usuario enviar um video/link e pedir para transformar em workflow reutilizavel."]
    if "skill" in lower or "claude" in lower or "codex" in lower:
        triggers.append(
            "O conteudo mencionar skills, agentes, prompts, Claude, Codex ou automacao."
        )
    if "notion" in lower or "database" in lower:
        triggers.append("O video mostrar organizacao de conhecimento em database ou Notion.")
    if "hook" in lower or "cta" in lower or "reels" in lower:
        triggers.append("O objetivo for converter referencia em conteudo publicavel.")
    tools = _unique(
        [
            *tool_names_from_evidence(get_evidence_items(result)),
            *detect_tool_names(text),
        ]
    )
    if tools:
        tools_text = ", ".join(tools[:6])
        triggers.append("Ferramentas detectadas: " + tools_text)
    return _unique(triggers)


def _inputs(text: str) -> list[str]:
    inputs = ["URL ou arquivo de video ja autorizado pelo usuario."]
    if "notion" in text.lower():
        inputs.append("Opcional: database/schema de Notion para exportar campos.")
    if "instagram" in text.lower():
        inputs.append("Opcional: cookies do browser quando Instagram exigir sessao.")
    inputs.append("Pergunta ou objetivo do usuario para guiar a saida.")
    return inputs


def _workflow_steps(text: str, result: AnalysisResult) -> list[str]:
    steps = [
        "Rodar probe da origem e registrar adapter, riscos e necessidade de cookies.",
        "Executar analise multimodal e ler knowledge.md, analysis.json e templates gerados.",
        "Separar evidencias extraidas de inferencias de produto, conteudo ou automacao.",
        "Gerar saida acionavel com campos, proximos passos e limites de confianca.",
    ]
    lower = text.lower()
    if "hook" in lower or "cta" in lower:
        steps.append("Extrair hook, angulo, CTA e variações por plataforma.")
    if "skill" in lower or "claude" in lower:
        steps.append("Converter o workflow demonstrado em rascunho de skill/prompt reutilizavel.")
    if result.synthesis.questions:
        steps.append("Preservar perguntas em aberto como checklist de validacao antes de executar.")
    return steps


def _output_contract(text: str) -> list[str]:
    fields = [
        "Resumo evidencial curto",
        "Ferramentas/produtos citados",
        "Passos ou workflow",
        "Artefatos gerados e paths",
        "Proveniencia e confianca por ferramenta/produto",
        "Limites e riscos",
    ]
    lower = text.lower()
    if "hook" in lower or "reels" in lower or "tiktok" in lower:
        fields.extend(["Hooks", "Angulos", "CTA", "Variações por plataforma"])
    if "skill" in lower or "claude" in lower or "codex" in lower:
        fields.extend(["Triggers da skill", "Workflow da skill", "Prompts base"])
    return _unique(fields)


def _prompt_templates(text: str, result: AnalysisResult) -> list[dict[str, str]]:
    summary = _clip(_summary(result), 500)
    prompts = [
        {
            "name": "extract_workflow",
            "prompt": (
                "Com base apenas nas evidencias do video, extraia o workflow em passos, "
                "ferramentas, entradas, saidas e riscos. Evidencia: "
                f"{summary}"
            ),
        }
    ]
    lower = text.lower()
    if "hook" in lower or "reels" in lower:
        prompts.append(
            {
                "name": "creator_remix",
                "prompt": (
                    "Transforme a referencia em um pacote de conteudo com tese, publico, "
                    "hook, angulo, roteiro curto, CTA e variacoes por plataforma."
                ),
            }
        )
    if "skill" in lower or "claude" in lower or "codex" in lower:
        prompts.append(
            {
                "name": "skill_draft",
                "prompt": (
                    "Converta o workflow evidenciado em um SKILL.md com quando usar, "
                    "entradas, passos obrigatorios, saida esperada e limites."
                ),
            }
        )
    return prompts


def _safety_notes(text: str) -> list[str]:
    notes = [
        "Nao inventar passos ausentes do video sem marcar como inferencia.",
        "Nao expor chaves, cookies ou conteudo sensivel em logs ou resposta final.",
    ]
    lower = text.lower()
    if "instagram" in lower:
        notes.append("Evitar scraping autenticado amplo; preferir URLs fornecidas ou export CSV.")
    if "notion" in lower:
        notes.append("Confirmar schema/permissoes antes de escrever em workspace Notion real.")
    return notes


def _first_sentence(text: str) -> str:
    for item in re.split(r"(?<=[.!?])\s+", text or ""):
        clean = re.sub(r"\s+", " ", item).strip()
        if clean:
            return clean
    return ""


def _clip(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."


def _escape_frontmatter(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _append_list(lines: list[str], title: str, items: list[str]) -> None:
    clean_items = [str(item).strip() for item in items if str(item).strip()]
    if not clean_items:
        return
    lines.append(f"## {title}")
    lines.extend(f"- {item}" for item in clean_items)
    lines.append("")

