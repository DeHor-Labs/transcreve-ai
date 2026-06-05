"""
Tabela de precos para estimativa de custo do eval.

Substituivel sem tocar o harness: edite PRICE_TABLE ou passe uma
tabela customizada para estimate_cost().

Unidades:
  whisper_per_min: USD por minuto de audio transcrito
  vision_in_per_1k: USD por 1k tokens de entrada em chamadas de visao
  synth_in_per_1k:  USD por 1k tokens de entrada na sintese
  synth_out_per_1k: USD por 1k tokens de saida na sintese

Precos sao estimativas publicas documentadas; verificar nos sites
oficiais dos providers para valores atualizados.
"""

from __future__ import annotations

from typing import Any

# Estimativas baseadas em precos publicos (podem mudar)
PRICE_TABLE: dict[str, dict[str, float]] = {
    "openai": {
        "whisper_per_min": 0.006,
        "vision_in_per_1k": 0.000150,
        "synth_in_per_1k": 0.000150,
        "synth_out_per_1k": 0.000600,
    },
    "gemini": {
        "whisper_per_min": 0.0,
        "vision_in_per_1k": 0.000075,
        "synth_in_per_1k": 0.000075,
        "synth_out_per_1k": 0.000300,
    },
    "anthropic": {
        "whisper_per_min": 0.006,
        "vision_in_per_1k": 0.003000,
        "synth_in_per_1k": 0.003000,
        "synth_out_per_1k": 0.015000,
    },
    "local": {
        "whisper_per_min": 0.0,
        "vision_in_per_1k": 0.0,
        "synth_in_per_1k": 0.0,
        "synth_out_per_1k": 0.0,
    },
}

# Fallback para providers nao listados (desconhecidos)
_FALLBACK_PRICES: dict[str, float] = {
    "whisper_per_min": 0.006,
    "vision_in_per_1k": 0.000150,
    "synth_in_per_1k": 0.000150,
    "synth_out_per_1k": 0.000600,
}


def estimate_cost(
    provider_name: str,
    duration_seconds: float,
    frames_with_visual_note: int,
    transcript_len_chars: int,
    visual_notes_len_chars: int = 0,
    price_table: dict[str, Any] | None = None,
) -> dict[str, float]:
    """
    Estima custo em USD para um run.

    Parametros:
        provider_name: nome do provider (openai, gemini, anthropic, local)
        duration_seconds: duracao do video em segundos
        frames_with_visual_note: numero de frames com visual_note preenchida
        transcript_len_chars: comprimento do transcript em caracteres
        visual_notes_len_chars: comprimento total das notas visuais (opcional)
        price_table: tabela customizada (usa PRICE_TABLE se None)

    Retorna dict com: whisper_usd, vision_usd, synthesis_usd, total_usd
    """
    table = price_table if price_table is not None else PRICE_TABLE
    prices = table.get(provider_name, _FALLBACK_PRICES)

    # Custo de transcricao (Whisper)
    duration_min = duration_seconds / 60.0
    whisper_usd = duration_min * prices.get("whisper_per_min", 0.0)

    # Custo de visao: ~800 tokens de entrada por frame
    vision_tokens = frames_with_visual_note * 800
    vision_usd = (vision_tokens / 1000.0) * prices.get("vision_in_per_1k", 0.0)

    # Custo de sintese: input = transcript + notas visuais + overhead ~2000 tokens
    transcript_tokens = transcript_len_chars / 4.0
    notes_tokens = visual_notes_len_chars / 4.0
    synth_in_tokens = transcript_tokens + notes_tokens + 2000
    synth_out_tokens = 1500  # estimativa de saida da sintese
    synthesis_usd = (synth_in_tokens / 1000.0) * prices.get("synth_in_per_1k", 0.0) + (
        synth_out_tokens / 1000.0
    ) * prices.get("synth_out_per_1k", 0.0)

    total_usd = whisper_usd + vision_usd + synthesis_usd

    return {
        "whisper_usd": round(whisper_usd, 6),
        "vision_usd": round(vision_usd, 6),
        "synthesis_usd": round(synthesis_usd, 6),
        "total_usd": round(total_usd, 6),
    }
