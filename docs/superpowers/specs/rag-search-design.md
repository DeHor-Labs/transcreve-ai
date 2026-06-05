# RAG / Busca Semantica - Design e Implementacao

## Visao geral

O modulo RAG do TranscreveAI permite pesquisar o conteudo dos videos indexados usando similaridade semantica de embeddings e, opcionalmente, gerar uma resposta sintetizada por LLM com base nos trechos recuperados.

O pipeline e composto por tres etapas independentes:

1. **Chunking** - divide o dossie (`analysis.json`) em unidades textuais atomicas
2. **Indexacao** - gera embeddings para os chunks e persiste em SQLite
3. **Recuperacao / Sintese** - vetoriza a query, busca por cosseno, opcionalmente chama LLM

---

## Vector store

O banco de embeddings fica na mesma instancia SQLite do indice de runs (`~/.transcreveai/index.db`), numa tabela separada `embeddings`.

### Schema da tabela

```sql
CREATE TABLE IF NOT EXISTS embeddings (
    id            TEXT    NOT NULL PRIMARY KEY,   -- "{run_id}:{chunk_index:04d}"
    run_id        TEXT    NOT NULL,
    chunk_index   INTEGER NOT NULL,
    chunk_type    TEXT    NOT NULL,               -- summary | chapter | entity | transcript
    chunk_text    TEXT    NOT NULL,
    embedding     BLOB    NOT NULL,               -- JSON array serializado em UTF-8
    model         TEXT    NOT NULL,
    dim           INTEGER NOT NULL,
    provider      TEXT    NOT NULL,               -- openai | local | gemini
    chapter_start REAL,                           -- segundos; NULL se nao for capitulo
    source_title  TEXT    NOT NULL DEFAULT '',
    source_url    TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_emb_run_id ON embeddings (run_id);
CREATE INDEX IF NOT EXISTS idx_emb_type   ON embeddings (chunk_type);
```

Os vetores sao armazenados como JSON (`json.dumps(vec).encode("utf-8")`) em `BLOB`. A busca por cosseno e feita em Python com NumPy (carregado lazy), sem extensoes SQLite.

### Classe EmbeddingStore

`video_kb/embeddings/store.py`

Gerenciador de contexto. API publica:

| Metodo | Descricao |
|---|---|
| `has_indexed(run_id)` | Retorna `True` se ja ha embeddings para o run |
| `delete_run(run_id)` | Remove todos os chunks de um run |
| `upsert_chunks(run_id, chunks, vectors, provider, model, force)` | Insere ou re-insere chunks; se `force=False` e ja indexado, retorna 0 |
| `search(query_vec, limit, run_ids)` | Busca top-k por cosseno; `run_ids` filtra o escopo |

`upsert_chunks` levanta `DimMismatchError` se a dimensao do vetor novo diferir da dimensao ja armazenada para o mesmo `run_id` e `force=False`.

---

## Chunking

`video_kb/embeddings/chunker.py`

`chunk_dossier(analysis, run_id, chunk_size=1000, overlap=150) -> list[EmbeddingChunk]`

Recebe o dict carregado de `analysis.json` e produz chunks em ordem:

| Tipo | Fonte | Quantidade |
|---|---|---|
| `summary` | `synthesis.summary` | 1 |
| `chapter` | `synthesis.chapters[*].title + notes` | 1 por capitulo |
| `entity` | `synthesis.entities` + `synthesis.tools_or_products` | 1 (todos concatenados) |
| `transcript` | `transcript_text` | N (janelas deslizantes) |

### Janelas deslizantes (transcript)

- Tamanho maximo: `chunk_size` caracteres (default 1000)
- Sobreposicao: `overlap` caracteres (default 150)
- O corte e feito na ultima fronteira de palavra dentro da janela
- Avanco: `(posicao_de_corte) - overlap`

### Dataclass EmbeddingChunk

```python
@dataclass
class EmbeddingChunk:
    chunk_id: str         # "{run_id}:{chunk_index:04d}"
    run_id: str
    chunk_index: int
    chunk_type: str       # summary | chapter | entity | transcript
    chunk_text: str
    excerpt: str          # primeiros 200 chars de chunk_text
    source_title: str
    source_url: str
    chapter_start: float | None
```

---

## Embeddings - providers suportados

O modulo RAG usa a interface `provider.embed(texts: list[str]) -> list[list[float]]` definida nos providers de IA do TranscreveAI.

| Provider | Modelo padrao | Offline | Extra necessario |
|---|---|---|---|
| `openai` | `text-embedding-3-small` | Nao | nenhum (requer `OPENAI_API_KEY`) |
| `local` | `all-MiniLM-L6-v2` | Sim | `transcreve-ai[local]` + `transcreve-ai[rag]` |
| `gemini` | `text-embedding-004` | Nao | nenhum (requer `GEMINI_API_KEY`) |

O provider `local` usa `sentence-transformers` com o modelo `all-MiniLM-L6-v2` carregado via `SentenceTransformer`. Dimensao do vetor: 384. Nao faz chamadas de rede para embeddings.

O extra `[rag]` instala apenas `numpy>=1.24.0`. O chunker e o store nao importam numpy em nivel de modulo; o import e lazy dentro de `EmbeddingStore.search()`.

---

## Indexacao - `index_run`

`video_kb/embeddings/rag.py` - funcao `index_run(...) -> int`

```python
index_run(
    run_id,
    analysis,          # dict de analysis.json
    provider,          # instancia com capability "embed"
    provider_name,     # str: "openai" | "local" | "gemini"
    model_name,        # str: nome do modelo de embedding
    db_path,           # Path | None
    force,             # bool: reindexar mesmo que ja exista
    chunk_size,        # int: default 1000
    overlap,           # int: default 150
) -> int               # numero de chunks gravados (0 se pulado)
```

Fluxo:
1. `chunk_dossier(analysis, run_id)` - gera lista de `EmbeddingChunk`
2. `provider.embed([c.chunk_text for c in chunks])` - vetor por chunk
3. `EmbeddingStore.upsert_chunks(...)` - persiste no SQLite

---

## Recuperacao - `search` e `ask`

### `search` (sem LLM)

`video_kb/embeddings/rag.py` - funcao `search(...) -> list[SearchHit]`

1. `provider.embed([query])` - vetoriza a query
2. `EmbeddingStore.search(query_vec, limit=top_k, run_ids=...)` - busca cosine
3. Retorna lista de `SearchHit` ordenada por score decrescente

`SearchHit` contem: `run_id`, `title`, `source_url`, `chunk_type`, `excerpt`, `score`, `chapter_start`.

### `ask` (com LLM)

`video_kb/embeddings/rag.py` - funcao `ask(...) -> AskResult`

1. Chama `search(...)` para recuperar top-k chunks
2. Se vazio, retorna mensagem padrao sem chamar LLM
3. Monta prompt com os chunks como contexto via `_build_prompt`
4. Chama `_call_complete(synth_provider, prompt)` que tenta em ordem:
   - `provider.complete(prompt)`
   - `provider._client.chat.completions.create(...)` (OpenAI SDK)
   - `provider._model.generate_content(prompt)` (Gemini)
   - `provider._anthropic.messages.create(...)` (Anthropic)
5. Retorna `AskResult(question, answer, sources)`

O `embed_provider` e o `synth_provider` podem ser instancias diferentes, mas na CLI e na API web sao o mesmo objeto.

### Prompt de sintese

```
Responda a pergunta abaixo com base EXCLUSIVAMENTE nos trechos fornecidos.
Se a resposta nao estiver nos trechos, diga exatamente:
"Nao encontrei informacao sobre isso nos videos indexados."
Cite os videos usados pelo titulo ao responder.

Pergunta: {question}

Trechos:
[1] "{excerpt}" - {titulo} (resumo|capitulo|entidades|transcricao)
[2] ...
```

---

## CLI

### `transcreveai index`

Indexa um ou todos os runs. Requer `transcreve-ai[rag]` instalado.

```
transcreveai index [RUN_ID | --all] [--provider NOME] [--force]
```

| Argumento/Flag | Descricao | Default |
|---|---|---|
| `RUN_ID` | ID do run a indexar (posicional, opcional) | - |
| `--all` | Indexa todos os runs nao indexados | `false` |
| `--provider NOME` | Provider de embed: `openai`, `local`, `gemini` | `VIDEO_KB_PROVIDER` ou `openai` |
| `--force` | Reindexar mesmo que ja tenha embeddings | `false` |

Comportamento:
- Se `--all`, busca todos os runs no indice e itera sobre eles
- Pula runs sem `analysis_path` valido
- Pula runs ja indexados a menos que `--force` seja passado
- Imprime `N chunks gerados` por run indexado
- Imprime `Concluido: X indexado(s), Y pulado(s).` ao final

### `transcreveai ask`

Faz uma pergunta sobre os videos indexados.

```
transcreveai ask PERGUNTA [--provider NOME] [--top-k N] [--run-ids ID...] [--search-only]
```

| Argumento/Flag | Descricao | Default |
|---|---|---|
| `PERGUNTA` | Texto da pergunta (posicional) | - |
| `--provider NOME` | Provider de embed e sintese | `VIDEO_KB_PROVIDER` ou `openai` |
| `--top-k N` | Numero de trechos de contexto | `5` |
| `--run-ids ID [ID...]` | Limita a busca a runs especificos | todos |
| `--search-only` | Exibe apenas os trechos, sem chamar LLM | `false` |

Com `--search-only`, imprime os trechos com score e trecho do excerpt (sem gerar resposta). Util para depurar o que foi indexado.

---

## Endpoints da API web

### `POST /api/search`

Busca semantica sem sintese. Nao chama LLM.

**Request:**
```json
{
  "query": "string",
  "top_k": 5,
  "run_ids": ["id1", "id2"] // opcional; null = todos
}
```

**Response 200:**
```json
{
  "query": "string",
  "total": 3,
  "results": [
    {
      "run_id": "string",
      "title": "string",
      "source_url": "string",
      "chunk_type": "summary | chapter | entity | transcript",
      "excerpt": "string",
      "score": 0.87,
      "chapter_start": 142.5   // null se nao for chunk de capitulo
    }
  ]
}
```

**Erros:**
- `422` - `query` vazio
- `503` - modulo RAG nao instalado (`rag_unavailable`) ou provider sem suporte a embed

### `POST /api/ask`

RAG completo: busca trechos + gera resposta com LLM.

**Request:**
```json
{
  "question": "string",
  "top_k": 5,
  "run_ids": null
}
```

**Response 200:**
```json
{
  "question": "string",
  "answer": "string",
  "sources": [ /* mesma estrutura de SearchResult */ ]
}
```

**Erros:**
- `422` - `question` vazio
- `503` - RAG nao disponivel ou provider sem suporte a embed
- `500` - erro interno de busca ou sintese

O provider e resolvido a partir da variavel `VIDEO_KB_PROVIDER` (ou `openai` como fallback). Nao e possivel escolher o provider por requisicao na API web.

---

## Interface web (SearchPage)

Rota: `/search`

A pagina tem:
- `textarea` para a query/pergunta
- checkbox "Gerar resposta com IA" que alterna entre `POST /api/search` e `POST /api/ask`
- Cards de resultado com: titulo linkando para `/jobs/{run_id}`, badge de tipo de chunk, score em %, excerpt truncado, tempo do capitulo (quando disponivel)
- Estado de erro com mensagem amigavel para 503 (provider sem embed)

---

## Retrocompatibilidade

- O modulo `video_kb.embeddings` e importado lazily nos comandos CLI e nos endpoints web. Se `[rag]` nao estiver instalado, as rotas `/api/search` e `/api/ask` retornam `503` com `error: "rag_unavailable"` em vez de travar o servidor.
- O comando `transcreveai index` e `transcreveai ask` saem com codigo 1 e imprimem instrucao de instalacao se o import falhar.
- A tabela `embeddings` e criada automaticamente no primeiro uso de `EmbeddingStore`. Instancias sem a tabela nao necessitam migracao manual.
- O campo `dim` na tabela protege contra mistura de vetores de dimensoes diferentes: `DimMismatchError` e levantada se o provider atual gerar vetores com dimensao diferente da ja armazenada para o mesmo `run_id`. A solucao e `transcreveai index RUN_ID --force`.
- A busca cosine e feita em Python puro com NumPy. Nao ha dependencia de extensoes SQLite (sqlite-vss, hnswlib, etc.), o que garante portabilidade maxima para instalacoes locais.
