from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

from .models import AnalysisResult, FrameObservation
from .utils import compact_text, format_timestamp


def build_content_intelligence(result: AnalysisResult) -> dict[str, Any]:
    """Build a deterministic creator-remix layer from an AnalysisResult."""
    text = _joined_text(result)
    screen_text = _screen_text(result.frames)
    synthesis = result.synthesis
    is_carousel = _is_carousel(result)
    caption_items = _extract_caption_items(result.metadata.description)

    hooks = _extract_hooks(result.transcript_text, screen_text, synthesis.summary)
    ctas = _extract_ctas(result.transcript_text, synthesis.action_items)
    platforms = _detect_platforms(text)
    tools = _unique([*synthesis.tools_or_products, *_detect_tools(text)])
    thesis = _first_non_empty(
        synthesis.summary,
        _first_sentence(result.transcript_text),
        result.metadata.description,
    )

    export_fields = [
        "source_url",
        "source_timestamp",
        "platform",
        "hook",
        "angle",
        "voice",
        "cta",
        "status",
        "priority",
        "evidence",
    ]

    return {
        "kind": "content_intelligence",
        "version": 1,
        "source_kind": "carousel" if is_carousel else "video",
        "source": result.source,
        "run_id": result.run_id,
        "title": result.metadata.title or "Video analysis",
        "evidence": {
            "summary": thesis,
            "tools_or_products": tools,
            "claims": list(synthesis.claims or []),
            "actions": list(synthesis.action_items or []),
            "detected_platforms": platforms,
            "cta_signals": ctas,
            "caption_items": caption_items,
            "slide_count" if is_carousel else "frame_count": len(result.frames or []),
            "transcript_chars": len(result.transcript_text or ""),
        },
        "creator_remix": {
            "thesis": thesis,
            "audience_pain": _infer_audience_pain(text),
            "hook_candidates": hooks,
            "angles": _infer_angles(text, synthesis.claims, thesis),
            "script_outline": _script_outline(hooks, thesis, ctas),
            "platform_variants": _platform_variants(platforms, hooks, thesis, ctas),
            "export_fields": export_fields,
        },
        "automation_opportunities": _automation_opportunities(
            text,
            platforms,
            tools,
            is_carousel,
            caption_items,
        ),
        "caveats": _caveats(is_carousel),
    }


def render_content_markdown(result: AnalysisResult) -> str:
    data = build_content_intelligence(result)
    evidence = data["evidence"]
    remix = data["creator_remix"]

    lines: list[str] = []
    lines.append(f"# Content Intelligence: {data['title']}")
    lines.append("")
    lines.append(f"- Fonte: `{data['source']}`")
    lines.append(f"- Run: `{data['run_id']}`")
    if data.get("source_kind") == "carousel":
        lines.append("- Tipo: carrossel")
        lines.append(f"- Slides: {len(result.frames or [])}")
    if result.metadata.uploader or result.metadata.channel:
        lines.append(f"- Autor/canal: {result.metadata.uploader or result.metadata.channel}")
    if data.get("source_kind") != "carousel" and result.metadata.duration:
        lines.append(f"- Duracao: {format_timestamp(result.metadata.duration)}")
    lines.append("")

    evidence_title = (
        "## Evidencia do carrossel"
        if data.get("source_kind") == "carousel"
        else "## Evidencia do video"
    )
    lines.append(evidence_title)
    lines.append(_paragraph(evidence["summary"]))
    lines.append("")
    _append_list(lines, "Ferramentas/produtos detectados", evidence["tools_or_products"])
    _append_list(lines, "Claims extraidos", evidence["claims"])
    _append_list(lines, "CTAs e acoes detectadas", evidence["cta_signals"] or evidence["actions"])
    _append_list(lines, "Plataformas citadas", evidence["detected_platforms"])
    _append_caption_items(lines, "Itens extraidos da legenda", evidence["caption_items"])

    lines.append("## Creator Remix")
    lines.append(f"- Tese: {_inline(remix['thesis'])}")
    lines.append(f"- Dor do publico: {_inline(remix['audience_pain'])}")
    lines.append("")
    _append_list(lines, "Hooks reaproveitaveis", remix["hook_candidates"])
    _append_list(lines, "Angulos", remix["angles"])

    lines.append("## Roteiro curto")
    for item in remix["script_outline"]:
        lines.append(f"- {item['slot']}: {item['text']}")
    lines.append("")

    lines.append("## Variacoes por plataforma")
    for item in remix["platform_variants"]:
        lines.append(f"### {item['platform']}")
        lines.append(f"- Formato: {item['format']}")
        lines.append(f"- Hook: {item['hook']}")
        lines.append(f"- Corpo: {item['body']}")
        lines.append(f"- CTA: {item['cta']}")
        lines.append("")

    lines.append("## Campos para Notion/CSV")
    lines.extend(f"- `{field}`" for field in remix["export_fields"])
    lines.append("")

    lines.append("## Oportunidades de produto")
    for item in data["automation_opportunities"]:
        lines.append(f"### {item['feature']}")
        lines.append(f"- Por que: {item['why']}")
        lines.append(f"- Prioridade: {item['priority']}")
        lines.append(f"- Esforco: {item['effort']}")
        lines.append(f"- Risco: {item['risk']}")
        lines.append(f"- Evidencia: {item['evidence']}")
        lines.append("")

    lines.append("## Limites")
    lines.extend(f"- {item}" for item in data["caveats"])
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_content_artifacts(result: AnalysisResult, run_dir: Path) -> dict[str, str]:
    markdown_path = run_dir / "content.md"
    json_path = run_dir / "content.json"
    csv_path = run_dir / "content.csv"
    data = build_content_intelligence(result)
    markdown_path.write_text(render_content_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path.write_text(render_content_csv(data), encoding="utf-8")
    return {
        "content": str(markdown_path),
        "content_json": str(json_path),
        "content_csv": str(csv_path),
    }


def render_content_csv(data: dict[str, Any]) -> str:
    fields = list(data["creator_remix"]["export_fields"])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    evidence = data["evidence"]["summary"]
    variants = data["creator_remix"]["platform_variants"] or []
    for variant in variants:
        writer.writerow(
            {
                "source_url": data["source"],
                "source_timestamp": "",
                "platform": variant.get("platform", ""),
                "hook": variant.get("hook", ""),
                "angle": _first_or_empty(data["creator_remix"]["angles"]),
                "voice": "",
                "cta": variant.get("cta", ""),
                "status": "Not started",
                "priority": "High",
                "evidence": evidence,
            }
        )
    return buffer.getvalue()


def _joined_text(result: AnalysisResult) -> str:
    parts = [
        result.metadata.title,
        result.metadata.description,
        result.transcript_text,
        result.synthesis.summary,
        " ".join(result.synthesis.claims or []),
        " ".join(result.synthesis.action_items or []),
        _screen_text(result.frames),
    ]
    return "\n".join(part for part in parts if part)


def _screen_text(frames: list[FrameObservation]) -> str:
    return "\n".join(frame.ocr_text for frame in frames if frame.ocr_text)


def _extract_hooks(transcript: str, screen_text: str, summary: str) -> list[str]:
    candidates: list[str] = []
    for match in re.finditer(r"(?i)\bhook\s*:\s*[\"“”']?([^\"\n]{8,160})", screen_text):
        candidates.append(_clean_sentence(match.group(1)))
    first = _first_sentence(transcript)
    if first:
        candidates.append(first)
    if summary:
        candidates.append(f"Como transformar isso em resultado: {_clip_text(summary, 180)}")
    return _unique([item for item in candidates if item])[:5]


def _extract_ctas(transcript: str, action_items: list[str]) -> list[str]:
    ctas: list[str] = list(action_items or [])
    for sentence in _sentences(transcript):
        lower = sentence.lower()
        if any(marker in lower for marker in ("comenta", "compartilhe", "segue", "clique")):
            ctas.append(sentence)
    return _unique(ctas)[:5]


def _detect_platforms(text: str) -> list[str]:
    platforms = {
        "Instagram": r"\binstagram\b|reels?\b",
        "TikTok": r"\btiktok\b",
        "YouTube": r"\byoutube\b",
        "LinkedIn": r"\blinkedin\b",
        "Notion": r"\bnotion\b",
    }
    return [name for name, pattern in platforms.items() if re.search(pattern, text, re.I)]


def _detect_tools(text: str) -> list[str]:
    tools = {
        "Claude": r"\bclaude\b|cloud code",
        "Notion": r"\bnotion\b",
        "Instagram": r"\binstagram\b",
        "TikTok": r"\btiktok\b",
        "YouTube": r"\byoutube\b",
        "Python": r"\bpython\b",
        "Playwright": r"\bplaywright\b",
        "Cypress": r"\bcypress\b",
        "Selenium": r"\bselenium\b",
        "Appium": r"\bappium\b",
        "Robot": r"\brobot\b",
        "Azure DevOps": r"\bazure\s+devops\b",
        "Jira": r"\bjira\b",
        "Trello": r"\btrello\b",
        "Qase": r"\bqase\b",
    }
    return [name for name, pattern in tools.items() if re.search(pattern, text, re.I)]


def _extract_caption_items(description: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current_section = ""
    for raw_line in (description or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s*(.+)$", line)
        if bullet:
            text = _clean_sentence(bullet.group(1))
            if text:
                items.append({"section": current_section, "text": text})
            continue
        if _looks_like_caption_heading(line):
            current_section = _clean_caption_heading(line)
    return items


def _looks_like_caption_heading(line: str) -> bool:
    lower = line.lower()
    return (
        "trilha" in lower
        or "projetos" in lower
        or line.endswith(":")
        or bool(re.match(r"^[^\w\s]+", line))
    )


def _clean_caption_heading(line: str) -> str:
    clean = re.sub(r"^[^\w]+", "", line).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean.rstrip(":")


def _is_carousel(result: AnalysisResult) -> bool:
    return result.metadata.media_kind == "carousel" or len(result.media_paths or []) > 1


def _caveats(is_carousel: bool) -> list[str]:
    evidence_source = (
        "As evidencias vêm dos slides, OCR e notas visuais do carrossel."
        if is_carousel
        else "As evidencias vêm do audio, OCR e notas visuais do video."
    )
    return [
        evidence_source,
        (
            "Backlog, prioridade e oportunidade sao inferencias de produto "
            "baseadas nessas evidencias."
        ),
    ]


def _infer_audience_pain(text: str) -> str:
    lower = text.lower()
    if "salv" in lower and ("conteudo" in lower or "conteúdo" in lower):
        return (
            "Tem muitos conteúdos salvos, mas pouco processo para transformar "
            "referencia em publicacao."
        )
    if "notion" in lower or "database" in lower:
        return "Precisa organizar referencias e transformar base de conhecimento em execucao."
    if "hook" in lower or "cta" in lower:
        return "Sabe o tema, mas precisa converter a ideia em hook, roteiro e chamada para acao."
    return (
        "Quer transformar um video/referencia em um ativo reutilizavel sem "
        "depender de transcricao bruta."
    )


def _infer_angles(text: str, claims: list[str], thesis: str) -> list[str]:
    lower = text.lower()
    angles: list[str] = []
    if "tom de voz" in lower or "ângulo" in lower or "angulo" in lower:
        angles.append("Adaptar referencias para o proprio angulo e tom de voz.")
    if "salv" in lower:
        angles.append("Transformar conteudo salvo em fila de ideias publicaveis.")
    if "notion" in lower or "database" in lower:
        angles.append("Organizar referencias em database com status, prioridade e plataforma.")
    if "skill" in lower or "claude" in lower:
        angles.append("Converter referencias em skill/prompt reutilizavel para agentes.")
    angles.extend(_clip_text(claim, 160) for claim in claims[:3])
    if thesis and not angles:
        angles.append(_clip_text(thesis, 180))
    return _unique(angles)[:6]


def _script_outline(hooks: list[str], thesis: str, ctas: list[str]) -> list[dict[str, str]]:
    hook = hooks[0] if hooks else _clip_text(thesis, 140)
    cta = ctas[0] if ctas else "Salve esta ideia e transforme em um proximo experimento."
    return [
        {"slot": "0-5s", "text": hook},
        {"slot": "5-20s", "text": "Mostre a referencia original e a transformacao gerada."},
        {"slot": "20-40s", "text": _clip_text(thesis, 180)},
        {"slot": "40-55s", "text": "Mostre o output pronto: hook, angulo, roteiro e CTA."},
        {"slot": "CTA", "text": cta},
    ]


def _platform_variants(
    platforms: list[str],
    hooks: list[str],
    thesis: str,
    ctas: list[str],
) -> list[dict[str, str]]:
    selected = [p for p in platforms if p in {"Instagram", "TikTok", "YouTube", "LinkedIn"}]
    if not selected:
        selected = ["Instagram", "TikTok", "YouTube"]

    defaults = {
        "Instagram": "Reel 30-60s",
        "TikTok": "Video 30-60s",
        "YouTube": "Short ou video 8-12min",
        "LinkedIn": "Post carrossel ou video curto",
    }
    cta = ctas[0] if ctas else "Comente uma palavra-chave para receber o guia."
    hook = hooks[0] if hooks else _clip_text(thesis, 140)
    variants = []
    for platform in selected:
        variants.append(
            {
                "platform": platform,
                "format": defaults.get(platform, "Conteudo curto"),
                "hook": hook,
                "body": "Explique o antes/depois e mostre o output final com evidencia visual.",
                "cta": cta,
            }
        )
    return variants


def _automation_opportunities(
    text: str,
    platforms: list[str],
    tools: list[str],
    is_carousel: bool = False,
    caption_items: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    lower = text.lower()
    source_label = "carrossel" if is_carousel else "video"
    items = [
        {
            "feature": "--template content",
            "why": (
                "Gerar hook, angulo, roteiro, CTA, variacoes por plataforma e campos de exportacao."
            ),
            "priority": "Alta",
            "effort": "Baixo/medio",
            "risk": "Baixo",
            "evidence": (
                f"O {source_label} mostra transformacao de referencia em ideias prontas "
                "para publicacao."
            ),
        },
        {
            "feature": "Export content.json para Notion/CSV",
            "why": "Permite jogar o pacote gerado em databases de producao de conteudo.",
            "priority": "Alta" if "notion" in lower else "Media",
            "effort": "Medio",
            "risk": "Medio",
            "evidence": "Plataformas detectadas: " + (", ".join(platforms) or "nao detectadas"),
        },
        {
            "feature": "Entrada em lote de URLs salvas",
            "why": "Transforma varias fontes/referencias em backlog de ideias.",
            "priority": "Media",
            "effort": "Medio/alto",
            "risk": "Alto se depender de scraping autenticado; menor com CSV/lista de URLs.",
            "evidence": "Ferramentas detectadas: " + (", ".join(tools) or "nao detectadas"),
        },
    ]
    if "skill" in lower or "claude" in lower:
        items.append(
            {
                "feature": "--template skill",
                "why": "Converter videos sobre prompts/agentes em esqueleto de skill reutilizavel.",
                "priority": "Media",
                "effort": "Medio",
                "risk": "Medio",
                "evidence": "O video menciona Claude/Skills como formato reutilizavel.",
            }
        )
    if caption_items:
        items.append(
            {
                "feature": "Caption/List Intelligence",
                "why": "Promover bullets e listas da legenda para o pacote final.",
                "priority": "Alta",
                "effort": "Baixo",
                "risk": "Baixo",
                "evidence": (
                    f"{len(caption_items)} itens estruturados foram encontrados na legenda."
                ),
            }
        )
    return items


def _first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return compact_text(value.strip(), 500)
    return "Analise concluida; use os trechos e frames para definir a tese."


def _first_or_empty(values: list[str]) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""


def _first_sentence(text: str) -> str:
    for sentence in _sentences(text):
        return sentence
    return ""


def _sentences(text: str) -> list[str]:
    raw = re.split(r"(?<=[.!?])\s+", text or "")
    return [_clean_sentence(item) for item in raw if _clean_sentence(item)]


def _clean_sentence(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" -:;\"'“”")


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = _clean_sentence(item)
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _append_list(lines: list[str], title: str, items: list[str]) -> None:
    clean_items = [str(item).strip() for item in items if str(item).strip()]
    if not clean_items:
        return
    lines.append(f"## {title}")
    lines.extend(f"- {item}" for item in clean_items)
    lines.append("")


def _append_caption_items(lines: list[str], title: str, items: list[dict[str, str]]) -> None:
    clean_items = [
        (str(item.get("section") or "Legenda").strip(), str(item.get("text") or "").strip())
        for item in items
        if str(item.get("text") or "").strip()
    ]
    if not clean_items:
        return
    lines.append(f"## {title}")
    for section, text in clean_items:
        lines.append(f"- **{section}:** {text}")
    lines.append("")


def _paragraph(text: str) -> str:
    return compact_text(text or "", 800) or "_Sem resumo extraido._"


def _inline(text: str) -> str:
    return _clip_text(text or "", 240)


def _clip_text(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text or "").strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 3)].rstrip() + "..."
