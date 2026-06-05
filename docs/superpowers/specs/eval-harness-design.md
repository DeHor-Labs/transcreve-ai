# Eval Harness - Design e Implementacao

## Visao geral

O eval harness do TranscreveAI compara dois ou mais providers de IA rodando o mesmo conjunto de videos de referencia (dataset). Para cada combinacao caso x provider, o pipeline completo e executado e metricas objetivas sao coletadas automaticamente. Um relatorio Markdown e um arquivo JSON estruturado sao gravados ao final.

O harness e desenhado para rodar localmente (custo do usuario) e nao exige infraestrutura adicional. Toda logica vive no subpacote `video_kb/eval/`.

---

## Estrutura do subpacote

```
video_kb/eval/
  __init__.py          # marca o subpacote
  runner.py            # EvalRunner, EvalCase, EvalDataset, CaseResult, load_dataset
  metrics.py           # extract_metrics, wer_simple
  judge.py             # run_judge, JudgeResult (judge opcional)
  cost_table.py        # PRICE_TABLE, estimate_cost
  report_writer.py     # write_report -> report.md + results.json
  stage_timer.py       # StageTimer (cronometragem por etapa)
  datasets/
    default.json       # dataset de smoke-test publico
    README.txt
```

---

## Dataset

### Formato

O dataset e um arquivo JSON com a seguinte estrutura:

```json
{
  "version": "1",
  "description": "Descricao do dataset",
  "cases": [
    {
      "id": "identificador_unico",
      "source": "URL ou caminho local",
      "notes": "Descricao opcional do caso",
      "ground_truth_transcript": "Transcricao de referencia (opcional, para calculo de WER)"
    }
  ]
}
```

Campos de cada caso:

| Campo | Tipo | Obrigatorio | Descricao |
|---|---|:---:|---|
| `id` | string | sim | Identificador unico do caso (usado no relatorio e nos diretorios de saida) |
| `source` | string | sim | URL ou caminho local do video |
| `notes` | string | nao | Descricao do conteudo, util para documentar o que o caso testa |
| `ground_truth_transcript` | string | nao | Texto de referencia para calculo do WER. Se vazio ou ausente, WER nao e calculado. |

### Dataset padrao

O arquivo `video_kb/eval/datasets/default.json` inclui tres casos publicos:

| ID | Fonte | Uso |
|---|---|---|
| `bbb_trailer_60s` | YouTube - Big Buck Bunny trailer ~60s | Testa OCR e visao em video sem fala |
| `wikimedia_commons_short` | Wikimedia Commons ~30s | Clip de dominio publico sem fala |
| `ted_ed_short` | YouTube - TED-Ed ~3min com narrador em ingles | Testa transcricao e calculo de WER |

### Datasets customizados

Crie um JSON seguindo o mesmo formato e passe com `--dataset PATH`. Cada caso pode misturar URLs e arquivos locais.

---

## Metricas coletadas

### Metricas estruturais (`extract_metrics`)

Extraidas do `AnalysisResult` sem chamadas adicionais de IA:

| Metrica | Descricao |
|---|---|
| `duration_seconds` | Duracao do video em segundos |
| `transcript_len_chars` | Comprimento da transcricao em caracteres |
| `transcript_len_words` | Contagem de palavras da transcricao |
| `transcript_segments_count` | Numero de segmentos temporais da transcricao |
| `frames_total` | Total de frames amostrados |
| `frames_with_visual_note` | Frames que receberam nota visual de IA |
| `frames_with_ocr` | Frames com texto OCR detectado |
| `visual_notes_len_chars` | Comprimento total das notas visuais (soma de todos os frames) |
| `summary_len_chars` | Comprimento do resumo gerado |
| `chapters_count` | Numero de capitulos na sintese |
| `entities_count` | Numero de entidades extraidas |
| `tools_count` | Numero de ferramentas/produtos identificados |
| `claims_count` | Numero de afirmacoes extraidas |
| `action_items_count` | Numero de itens de acao |
| `questions_count` | Numero de perguntas abertas |
| `synthesis_mode` | `"llm"` ou `"local"` (modo de sintese usado) |
| `warnings_count` | Numero de avisos emitidos pelo pipeline |

### Metricas de tempo (`StageTimer`)

O `StageTimer` intercepta o callback `on_progress` do pipeline e acumula tempo por etapa:

| Etapa | Descricao |
|---|---|
| `download` | Download/copia do video |
| `audio` | Extracao de audio com ffmpeg |
| `frames` | Amostragem de frames |
| `ocr` | OCR Tesseract em todos os frames |
| `ai` | Transcricao + sintese (chamadas de IA principais) |
| `ai_frame` | Notas visuais por frame (chamadas de IA adicionais) |
| `persist` | Persistencia dos artefatos em storage |

O relatorio exibe `total_s` (tempo de parede total), `download_s` e `ai_s` (soma de `ai` + `ai_frame`).

### WER (Word Error Rate)

Calculado apenas quando `ground_truth_transcript` esta preenchido e nao-vazio no dataset.

Formula:

```
WER = edit_distance_palavras(referencia, hipotese) / max(len(referencia_palavras), 1)
```

- Implementacao DP classica de distancia de edicao (Levenshtein) entre listas de palavras.
- Normalizacao: minusculas, remocao de pontuacao basica, colapso de espacos.
- Sem dependencias externas.
- Pode ser maior que 1.0 se a hipotese tiver muitas insercoes.
- Exibido no relatorio como percentual (ex: `12.3%`).

### Custo estimado (`estimate_cost`)

Estimativa heuristica em USD baseada em precos publicos dos providers. Os calculos sao:

| Componente | Calculo |
|---|---|
| `whisper_usd` | `(duration_seconds / 60) * whisper_per_min` |
| `vision_usd` | `(frames_with_visual_note * 800 tokens) * vision_in_per_1k / 1000` |
| `synthesis_usd` | `((transcript_chars/4 + visual_notes_chars/4 + 2000) * synth_in_per_1k + 1500 * synth_out_per_1k) / 1000` |
| `total_usd` | soma dos tres acima |

Tabela de precos padrao (em `cost_table.py`, valores aproximados, sujeitos a mudanca):

| Provider | whisper/min | vision in/1k | synth in/1k | synth out/1k |
|---|---|---|---|---|
| `openai` | $0.006 | $0.000150 | $0.000150 | $0.000600 |
| `gemini` | $0.000 | $0.000075 | $0.000075 | $0.000300 |
| `anthropic` | $0.006 | $0.003000 | $0.003000 | $0.015000 |
| `local` | $0.000 | $0.000000 | $0.000000 | $0.000000 |

A tabela e substituivel sem tocar o harness: edite `PRICE_TABLE` em `cost_table.py` ou passe `price_table=` para `estimate_cost()` diretamente.

---

## Judge opcional (LLM-as-judge)

O judge e desativado por padrao. Ativado com `--judge PROVIDER`.

Quando ativo, apos cada run bem-sucedido, o harness chama o provider especificado para pontuar a `KnowledgeSynthesis` em tres criterios:

| Criterio | Escala | Pergunta avaliada |
|---|---|---|
| `cobertura` | 0-10 | A sintese cobre os topicos principais do video? |
| `coerencia` | 0-10 | A sintese e logicamente consistente? |
| `utilidade` | 0-10 | Entidades, capitulos e itens de acao sao acionaveis? |
| `nota_geral` | 0-10 | Media dos tres criterios (calculada localmente) |

O prompt envia ao judge um JSON com: `summary`, contagem de capitulos, ate 10 entidades, ate 10 ferramentas, ate 5 afirmacoes, ate 5 itens de acao e ate 5 perguntas. A resposta esperada e JSON puro: `{"cobertura": N, "coerencia": N, "utilidade": N, "justificativa": "..."}`.

O parser e tolerante a texto extra ao redor do JSON. Se o parse falhar ou o provider nao suportar `synthesize`, o campo `judge` no resultado registra `judge_error` ou `judge_skipped` em vez de bloquear o eval.

Qualquer provider que implemente a capability `synthesize` pode ser usado como judge (incluindo o mesmo provider sendo avaliado).

**Custo adicional do judge:** aproximadamente 1 chamada de sintese por (caso x provider) avaliado. O CLI exibe um aviso antes de iniciar quando `--judge` aponta para um provider pago.

---

## Formato de saida

### Estrutura de diretorios

```
eval-report/<timestamp>/
  report.md           # relatorio legivel por humanos
  results.json        # dados brutos estruturados
  runs/
    <case_id>/
      <provider>/     # artefatos isolados de cada run
        analysis.json
        knowledge.md
        ...
```

O diretorio padrao e `eval-report/<timestamp>` (timestamp em formato `YYYYMMDD_HHMMSS`). Pode ser sobrescrito com `--out DIR`.

### `results.json`

```json
{
  "generated_at": "2026-06-03T10:00:00Z",
  "dataset": "video_kb/eval/datasets/default.json",
  "providers": ["openai", "gemini"],
  "cases": [
    {
      "id": "ted_ed_short",
      "source": "https://...",
      "notes": "...",
      "providers": {
        "openai": {
          "status": "ok",
          "elapsed_total_s": 47.2,
          "stage_timings_s": {
            "download": 3.1,
            "audio": 1.2,
            "frames": 0.8,
            "ocr": 2.4,
            "ai": 38.5,
            "persist": 0.2
          },
          "metrics": { "duration_seconds": 180.0, "transcript_len_words": 420, "..." },
          "cost_estimate": {
            "whisper_usd": 0.018,
            "vision_usd": 0.0036,
            "synthesis_usd": 0.0009,
            "total_usd": 0.0225
          },
          "wer": 0.0823,
          "warnings": [],
          "judge": {
            "cobertura": 8.5,
            "coerencia": 9.0,
            "utilidade": 7.5,
            "nota_geral": 8.33,
            "justificativa": "..."
          }
        }
      }
    }
  ],
  "summary": {
    "openai": {
      "cases_ok": 3,
      "cases_total": 3,
      "avg_total_s": 45.1,
      "avg_cost_usd": 0.021,
      "avg_wer": 0.09
    }
  }
}
```

Em caso de erro em um run, o objeto do provider contem `"status": "error"` e `"error_message": "..."` em vez das metricas.

### `report.md`

Relatorio Markdown com:
- Cabecalho com data, dataset, providers e status do judge
- Tabela de metricas por caso (providers nas colunas)
- Secao de avisos de capabilities por provider
- Tabela-resumo com medias por provider (casos OK, latencia media, custo medio, WER medio)
- Recomendacao de melhor custo-beneficio entre providers pagos
- Secao do judge (somente se ativo), com notas por caso e provider

A escrita e atomica: gravado em `.tmp` e renomeado para evitar arquivo parcialmente escrito.

---

## CLI

### Uso basico

```bash
transcreveai eval
```

Roda o dataset padrao com o provider configurado no ambiente.

### Flags

| Flag | Descricao | Default |
|---|---|---|
| `--dataset PATH` | JSON de dataset customizado | `video_kb/eval/datasets/default.json` |
| `--providers LISTA` | Providers separados por virgula, ex: `openai,gemini,local` | Provider do ambiente ou `openai` |
| `--judge PROVIDER` | Ativa LLM-as-judge com o provider informado | desativado |
| `--ai-mode {auto,full,off}` | Modo de IA repassado ao pipeline | `full` |
| `--out DIR` | Diretorio de saida do relatorio | `eval-report/<timestamp>` |
| `--json` | Imprime `results.json` no stdout alem de salvar em disco | `false` |
| `--no-cost-warning` | Suprime confirmacao interativa de custo (util em CI/CD) | `false` |

### Exemplos

```bash
# Smoke-test local (sem custo de API)
transcreveai eval --providers local

# Comparar dois providers pagos
transcreveai eval --providers openai,gemini

# Com dataset customizado e judge ativado
transcreveai eval --dataset meus-videos.json --providers openai,gemini --judge openai

# Saida em diretorio fixo
transcreveai eval --providers openai --out resultados/sprint-42

# Sem confirmacao interativa (CI/CD)
transcreveai eval --providers openai --no-cost-warning

# Imprimir JSON no stdout e salvar em disco
transcreveai eval --providers local --json
```

---

## Retrocompatibilidade

- O formato de `results.json` usa campos estaveis (`status`, `elapsed_total_s`, `stage_timings_s`, `metrics`, `cost_estimate`, `wer`, `warnings`, `judge`, `summary`). Campos novos podem ser adicionados sem quebrar leitores existentes que ignoram campos desconhecidos.
- O campo `judge` e sempre `null` quando o judge nao e ativado, nunca ausente.
- O campo `wer` e sempre `null` quando `ground_truth_transcript` nao esta disponivel ou e vazio, nunca ausente.
- A `PRICE_TABLE` em `cost_table.py` e publica e substituivel: passe `price_table=` para `estimate_cost()` sem tocar o harness principal.
- Novos providers registrados via entry_points sao automaticamente aceitos pelo runner sem alteracoes no harness.
- O subpacote `video_kb.eval` e importado de forma lazy pelo CLI para nao impactar o tempo de startup dos outros comandos.

---

## Custo estimado de um eval tipico

Exemplo com o dataset padrao (3 casos, ~4 min de video total), provider `openai`, modo `full`:

| Componente | Estimativa |
|---|---|
| Transcricao Whisper | ~$0.024 (4 min x $0.006/min) |
| Notas visuais (~30 frames x 800 tokens) | ~$0.004 |
| Sintese (1 chamada, ~3k tokens entrada) | ~$0.001 |
| **Total por provider** | **~$0.03** |
| Com judge ativado (openai) | +~$0.01 por caso avaliado |

Para comparar dois providers pagos com o dataset padrao e judge: ~$0.12 total. Para o provider `local`, custo zero.

Esses valores sao estimativas heuristicas. Precos reais variam. Consulte o site do provider e o arquivo `cost_table.py`.
