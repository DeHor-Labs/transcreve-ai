"""
LLM-as-judge opcional para pontuar a qualidade da sintese.

Ativado apenas com --judge PROVIDER. Desligado por default.
Qualquer provider com suporte a 'synthesize' pode ser usado como judge.

API publica:
    JudgeResult  - dataclass com pontuacoes e justificativa
    run_judge(synthesis, provider_name) -> JudgeResult | None
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import KnowledgeSynthesis


@dataclass
class JudgeResult:
    cobertura: float | None  # 0-10: cobre os topicos principais?
    coerencia: float | None  # 0-10: logicamente consistente?
    utilidade: float | None  # 0-10: entidades/chapters/actions acionaveis?
    nota_geral: float | None  # media dos tres (calculada localmente)
    justificativa: str = ""
    error: str | None = None
    skipped: str | None = None


_JUDGE_PROMPT = """\
Avalie a sintese abaixo de um video em tres criterios de 0 a 10.
Responda APENAS com JSON: {{"cobertura": N, "coerencia": N, "utilidade": N, "justificativa": "..."}}

SINTESE:
{synthesis_json}
"""


def run_judge(
    synthesis: KnowledgeSynthesis,
    provider_name: str,
) -> JudgeResult:
    """
    Pontua uma KnowledgeSynthesis usando o provider como juiz LLM.

    Retorna JudgeResult com pontuacoes ou com campo error/skipped preenchido
    se o provider nao suportar synthesize ou se o parse falhar.
    """
    from ..models import SourceMetadata
    from ..providers import CapabilityNotSupported, SynthesisContext, load_provider

    try:
        provider = load_provider(provider_name)
    except Exception as exc:  # noqa: BLE001
        return JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            error=f"falha ao carregar provider '{provider_name}': {exc}",
        )

    if "synthesize" not in provider.capabilities():
        return JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            skipped=f"provider {provider_name} nao suporta judge LLM (sem synthesize)",
        )

    # Serializa a sintese como texto para o prompt do judge
    synth_dict: dict[str, Any] = {
        "summary": synthesis.summary,
        "chapters_count": len(synthesis.chapters),
        "entities": synthesis.entities[:10],
        "tools_or_products": synthesis.tools_or_products[:10],
        "claims": synthesis.claims[:5],
        "action_items": synthesis.action_items[:5],
        "questions": synthesis.questions[:5],
    }
    synthesis_json = json.dumps(synth_dict, ensure_ascii=False, indent=2)

    prompt = _JUDGE_PROMPT.format(synthesis_json=synthesis_json)

    # Cria contexto minimo para o judge - usa transcript_text como prompt
    dummy_metadata = SourceMetadata(source="judge-eval")
    ctx = SynthesisContext(
        metadata=dummy_metadata,
        transcript_text=prompt,
        frames=[],
    )

    try:
        result = provider.synthesize(ctx)
        # A resposta do judge esta no campo summary (texto bruto da resposta LLM)
        raw_response = result.summary or ""
    except CapabilityNotSupported as exc:
        return JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            skipped=f"provider {provider_name} nao suporta synthesize: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            error=f"chamada ao judge falhou: {exc}",
        )

    # Tenta parsear o JSON da resposta
    parsed = _parse_judge_response(raw_response)
    if parsed is None:
        return JudgeResult(
            cobertura=None,
            coerencia=None,
            utilidade=None,
            nota_geral=None,
            error="parse failed: resposta nao e JSON valido",
        )

    cobertura = _to_float(parsed.get("cobertura"))
    coerencia = _to_float(parsed.get("coerencia"))
    utilidade = _to_float(parsed.get("utilidade"))
    nota_geral = _calc_media(cobertura, coerencia, utilidade)

    return JudgeResult(
        cobertura=cobertura,
        coerencia=coerencia,
        utilidade=utilidade,
        nota_geral=nota_geral,
        justificativa=str(parsed.get("justificativa", "")),
    )


def _parse_judge_response(text: str) -> dict[str, Any] | None:
    """Tenta parsear JSON da resposta do judge, tolerante a texto extra."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_media(*values: float | None) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)
