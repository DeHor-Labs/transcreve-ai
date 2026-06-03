# TranscreveAI - Interface Web: Especificacao Tecnica

Documento de contrato da interface web. Descreve a API REST/SSE, o modelo de jobs, a
arquitetura backend/frontend e a direcao de design. Fiel ao codigo implementado em
`video_kb/web/` e `frontend/src/`.

---

## 1. Visao geral

A interface web e um extra opcional do TranscreveAI. Ela expoe o pipeline de analise de
videos por meio de uma API HTTP e serve uma SPA React que permite submeter videos,
acompanhar o progresso em tempo real e visualizar o dossie gerado.

Para usar, instale o extra `web` e inicie o servidor:

```bash
pip install 'transcreve-ai[web]'
transcreveai serve
```

A SPA e servida automaticamente se o diretorio `frontend/dist/` existir. Para
desenvolvimento do frontend, o servidor backend roda em `localhost:8000` e o Vite em
`localhost:5173` (proxy configurado no `vite.config.ts`).

---

## 2. Arquitetura

### 2.1 Backend

```
video_kb/web/
  app.py          - factory FastAPI (create_app), lifespan, CORS, montagem da SPA
  jobs.py         - JobStore, ActiveJob, worker asyncio, build_progress_event
  schemas.py      - modelos Pydantic de request/response
  routes/
    api.py        - todos os endpoints /api/*
```

**Factory** (`create_app`):
- Aceita `out_dir: Path` e `index_db: str | None`.
- No lifespan: cria um `JobStore`, registra em `app.state`, dispara `worker_task` em background.
- Adiciona `CORSMiddleware` permitindo `localhost:5173` e `127.0.0.1:5173` (dev).
- Monta `frontend/dist/` como `StaticFiles(html=True)` em `/` se o diretorio existir.
- Docs Swagger em `/api/docs`, ReDoc desabilitado.

**Worker** (`worker_task`):
- Loop asyncio que consome `job_store._queue` (fila FIFO).
- Processa um job por vez (serializado).
- Executa `VideoKnowledgePipeline.run()` via `loop.run_in_executor(None, ...)` para nao
  bloquear o event loop.
- Envia eventos de progresso para o `_sse_queue` do job via `loop.call_soon_threadsafe`.
- Ao concluir: preenche `job.output_dir`, `job.analysis_path`, `job.markdown_path`,
  `job.title`, `job.duration_seconds`, `job.warnings_count`.
- Ao falhar: registra `job.error`, marca `status = "failed"`.
- Remove arquivos temporarios `/tmp/vkb_upload_*.mp4` apos processar uploads.

**Mapeamento step -> pct** (contrato compartilhado backend/frontend):

| Step | pct |
|---|---|
| `download` | 10 |
| `audio` | 20 |
| `frames` | 30 |
| `ocr` | 40 |
| `ai` | 50 |
| `ai_frame` | 51-69 (proporcional ao frame atual/total) |
| `persist` | 90 |
| `done` | 100 |
| `failed` | (mantém o pct do ultimo step) |

### 2.2 Frontend

```
frontend/src/
  api/
    client.ts     - fetch wrapper (get, post, postForm), ApiRequestError
    jobs.ts       - funcoes de API (submitUrl, submitFile, listJobs, getJob, getDossier, createEventSource)
    types.ts      - interfaces TypeScript espelhando os schemas Pydantic
  components/
    dossier/      - DossierView, ChapterList, ClaimsList, EntityCloud, MarkdownRenderer, SynthesisCard
    history/      - JobList, JobCard, StatusBadge
    progress/     - LiveStep, ProgressBar, StepTimeline
    submit/       - SubmitForm, FileDropzone, UrlInput
    ui/           - Badge, Button, EmptyState, ErrorState, Separator, Spinner
  hooks/
    useJobDetail  - polling do job individual
    useJobEvents  - SSE em tempo real com reconexao automatica
    useJobList    - lista de jobs com polling
    useSubmitJob  - submissao com tratamento de duplicate (409)
  pages/
    HomePage      - formulario de submit + historico
    JobDetailPage - progresso em tempo real + dossie
  styles/
    tokens.css    - design tokens CSS
    global.css    - estilos globais
  router.tsx      - rotas: "/" e "/jobs/:id"
```

**Stack**: React 19, Vite 8, TypeScript 6, Tailwind CSS 3, React Router 7, TanStack Query 5,
react-markdown + remark-gfm.

**Comunicacao**:
- Todas as chamadas REST usam o prefixo `/api` (injetado em `client.ts`).
- Em dev, o Vite proxy redireciona `/api/*` para `localhost:8000`.
- Em producao, a SPA e servida pelo mesmo processo FastAPI - sem proxy necessario.

---

## 3. Contrato da API

### 3.1 Base URL

```
/api
```

Documentacao interativa disponivel em `/api/docs` (Swagger UI).

---

### 3.2 `POST /api/jobs` - Submeter job

Aceita dois formatos de corpo:

**JSON (URL)**:
```json
{
  "source": "https://youtu.be/...",
  "language": "pt",
  "ai_mode": "auto",
  "provider": "openai"
}
```

**multipart/form-data (upload de arquivo)**:
- Campo `file`: arquivo de video (obrigatorio)
- Campos opcionais: `language`, `ai_mode`, `provider`

**Resposta 202 (sucesso)**:
```json
{
  "job_id": "20260603T001500Z-youtu-be-abc123",
  "status": "queued",
  "queued_at": "2026-06-03T00:15:00.000Z"
}
```

**Resposta 409 (duplicata)**:
```json
{
  "error": "duplicate",
  "message": "Esse video ja foi analisado.",
  "existing_run_id": "20260601T060803Z-youtu-be-abc123"
}
```

**Resposta 422 (validacao)**:
```json
{
  "error": "validation",
  "message": "Campo 'source' obrigatorio quando nao ha arquivo anexado."
}
```

**Campos**:

| Campo | Tipo | Default | Descricao |
|---|---|---|---|
| `source` | string | - | URL ou caminho local do video (obrigatorio no modo JSON) |
| `language` | string \| null | null | Idioma do audio (ex: `pt`, `en`) |
| `ai_mode` | string | `"auto"` | `"auto"`, `"off"` ou `"full"` |
| `provider` | string | `"openai"` | `"openai"`, `"gemini"`, `"anthropic"` ou `"local"` |

**Dedupe**: para URLs, calcula SHA-256 antes de enfileirar. Se ja existe run com mesmo hash
e `status != "failed"`, retorna 409 com o `existing_run_id`. O frontend trata o 409
redirecionando para o job existente.

---

### 3.3 `GET /api/jobs` - Listar jobs

**Query params**:

| Param | Tipo | Default | Descricao |
|---|---|---|---|
| `limit` | int | 50 | Numero maximo de jobs retornados |
| `status` | string | null | Filtrar por status: `queued`, `running`, `completed`, `failed` |

**Resposta 200**:
```json
{
  "jobs": [ /* JobSummary[] */ ],
  "total": 12
}
```

**Fonte dos dados**: uniao de jobs ativos em memoria (`JobStore`) e runs historicos do
`RunIndex` SQLite, excluindo duplicatas. Ordenados por `created_at` decrescente.

---

### 3.4 `GET /api/jobs/{job_id}` - Detalhe do job

**Resposta 200** (`JobDetail`):
```json
{
  "job_id": "20260603T001500Z-youtu-be-abc123",
  "title": "Como usar TranscreveAI",
  "source": "https://youtu.be/...",
  "status": "completed",
  "created_at": "2026-06-03T00:15:00.000Z",
  "finished_at": "2026-06-03T00:19:47.000Z",
  "duration_seconds": 312.0,
  "provider": "openai",
  "ai_mode": "auto",
  "warnings_count": 0,
  "storage_backend": "filesystem",
  "progress": { /* ProgressEvent */ },
  "output_dir": "outputs/20260603T001500Z-youtu-be-abc123",
  "analysis_path": "outputs/20260603T001500Z-youtu-be-abc123/analysis.json",
  "markdown_path": "outputs/20260603T001500Z-youtu-be-abc123/knowledge.md",
  "source_hash": "e3b0c44...",
  "progress_history": [ /* ProgressEvent[] */ ]
}
```

**Resposta 404**:
```json
{ "error": "not_found", "message": "Job nao encontrado." }
```

**Lookup**: primeiro verifica `JobStore` (memoria), depois consulta `RunIndex` (SQLite).

---

### 3.5 `GET /api/jobs/{job_id}/events` - SSE de progresso

Retorna um stream `text/event-stream` com eventos de progresso.

**Comportamento**:
- Se o job esta em memoria e ainda em execucao: drena `progress_history` (reconexao) e
  depois escuta `_sse_queue` em tempo real.
- Se o job ja esta concluido/falhou em memoria: drena `progress_history` e encerra.
- Se o job esta apenas no `RunIndex` (historico): emite um unico evento final e encerra.
- Se o job nao existe: retorna 404.

**Formato de cada evento**:
```
data: {"step":"audio","detail":"Extraindo audio...","pct":20,"status":"running","ts":"2026-06-03T00:15:05.000Z"}
```

**Schema do evento** (`ProgressEvent`):

| Campo | Tipo | Descricao |
|---|---|---|
| `step` | string | `download`, `audio`, `frames`, `ocr`, `ai`, `ai_frame`, `persist`, `done`, `failed` |
| `detail` | string | Mensagem legivel para exibicao |
| `pct` | int | Percentual de conclusao (0-100) |
| `status` | string | `running`, `completed`, `failed` |
| `ts` | string | Timestamp ISO 8601 UTC |

O evento `done` (step = `"done"`) sinaliza conclusao. O evento `failed` (step = `"failed"`)
sinaliza falha. Em ambos o stream e encerrado pelo servidor. O frontend fecha a `EventSource`
ao receber qualquer um dos dois.

---

### 3.6 `GET /api/jobs/{job_id}/dossier` - Dossie completo

Disponivel apenas quando `status == "completed"`.

**Resposta 200** (`DossierResponse`):
```json
{
  "job_id": "...",
  "markdown": "# Titulo do video\n\n## Resumo\n...",
  "analysis": {
    "run_id": "...",
    "source": "https://youtu.be/...",
    "metadata": {
      "title": "...",
      "uploader": "...",
      "channel": "...",
      "duration": 312,
      "upload_date": "...",
      "description": "...",
      "webpage_url": "..."
    },
    "synthesis": {
      "summary": "...",
      "chapters": [{ "title": "...", "start": 0, "end": 30 }],
      "entities": ["..."],
      "tools_or_products": ["..."],
      "claims": ["..."],
      "action_items": ["..."],
      "questions": ["..."]
    },
    "transcript_text": "...",
    "frames_count": 42,
    "warnings": []
  }
}
```

**Resposta 409** (nao pronto):
```json
{ "error": "not_ready", "message": "Job ainda nao concluido. Status: running" }
```

Lê `knowledge.md` e `analysis.json` do `output_dir` do job.

---

### 3.7 `GET /api/health` - Health check

**Resposta 200**:
```json
{
  "status": "ok",
  "version": "0.1.0",
  "queue_size": 0,
  "active_job": null
}
```

| Campo | Descricao |
|---|---|
| `status` | Sempre `"ok"` se o servidor esta de pe |
| `version` | Versao da aplicacao |
| `queue_size` | Numero de jobs aguardando na fila |
| `active_job` | `job_id` do job em execucao ou `null` |

---

## 4. Modelo de jobs

### 4.1 Ciclo de vida

```
submit → queued → running → completed
                          → failed
```

- `queued`: job registrado no `JobStore`, aguardando na fila asyncio.
- `running`: worker pegou o job e o pipeline esta em execucao.
- `completed`: pipeline concluiu com sucesso. Dossie disponivel.
- `failed`: pipeline lancou excecao. Campo `error` contem a mensagem.

### 4.2 Persistencia pos-conclusao

Jobs completados sao persistidos no `RunIndex` SQLite (`~/.transcreveai/index.db`) pelo
proprio pipeline. O `JobStore` mantem os jobs em memoria enquanto o servidor estiver ativo.
Apos reinicializacao, os jobs aparecem apenas via `RunIndex`.

### 4.3 Identificacao

O `job_id` e gerado no momento do submit:

```
{now_id()}-{slugify(source)}
```

Exemplo: `20260603T001500Z-youtu-be-abc123`

---

## 5. Modelo SSE detalhado

### 5.1 Reconexao do cliente

O `useJobEvents` (frontend) reconecta automaticamente apos 2 segundos se a conexao cair
enquanto o job ainda nao concluiu. O servidor drena `progress_history` em toda nova conexao,
garantindo que o cliente receba todos os eventos anteriores mesmo apos reconexao.

Deduplicacao no cliente: eventos com mesmo `(step, ts)` sao descartados.

### 5.2 Job historico via SSE

Se o cliente pede SSE de um job que ja esta apenas no `RunIndex` (historico), o servidor
emite um unico evento sintetico (step `"done"` ou `"failed"`) e fecha o stream
imediatamente. Isso permite que o frontend use sempre o mesmo codigo para jobs em andamento
e historicos.

---

## 6. Layout das paginas

### 6.1 Home (`/`)

- Header fixo: logo "TranscreveAI" + link "Historico".
- Secao de submit (`max-w-680px`): titulo, descricao, card com `SubmitForm`.
  - `SubmitForm`: aba URL (`UrlInput`) e aba arquivo (`FileDropzone`).
  - Campos: source, language (opcional), ai_mode, provider.
  - Tratamento de 409: redireciona para `/jobs/{existing_run_id}`.
- Secao de historico (`max-w-860px`): separador + `JobList`.
  - `JobCard`: titulo, source, status badge, provider, duracao, data.
  - Clicar no card navega para `/jobs/{job_id}`.

### 6.2 Detalhe do job (`/jobs/:id`)

- Header fixo: botao voltar + titulo do job (truncado) + `StatusBadge` animado.
- Estado **em andamento** (queued/running):
  - Layout de duas colunas (sidebar + area principal).
  - Sidebar: `StepTimeline` com os steps `download -> audio -> frames -> ocr -> ai -> persist -> done`.
  - Area principal: `ProgressBar` + `LiveStep` (step atual com spinner) + log de eventos anteriores.
- Estado **falhou**: `ErrorState` com a mensagem de erro e botao de retry.
- Estado **concluido**: `DossierView` carregado via `GET /api/jobs/{id}/dossier`.

### 6.3 DossierView

Exibe o dossie completo apos conclusao:
- `SynthesisCard`: resumo da analise.
- `ChapterList`: capitulos com timestamps.
- `EntityCloud`: entidades, ferramentas e produtos identificados.
- `ClaimsList`: afirmacoes, action items e perguntas abertas.
- `MarkdownRenderer`: `knowledge.md` renderizado com react-markdown + remark-gfm.

---

## 7. Direcao de design

O frontend usa Tailwind CSS com design tokens declarados em `frontend/src/styles/tokens.css`.

**Tokens principais**:
- `--color-bg`: fundo global da aplicacao.
- `--color-surface1`: superficie de cards e paineis.
- `--color-accent`: cor de destaque (usada em badges ativos, spinner, marcadores de step).
- `--color-text-primary`, `--color-text-secondary`, `--color-text-muted`: hierarquia textual.
- `--color-border`: bordas de cards e separadores.
- `--font-heading`: fonte dos titulos e labels em uppercase.
- `--space-3xl`: espaco de secao da homepage.

**Principios**:
- Hierarquia clara por contraste de escala, nao por decoracao generica.
- Animacoes restritas a propriedades compositor-friendly (`transform`, `opacity`).
- `StatusBadge` com variante `animated` (pulse) para jobs em andamento.
- Layout responsivo: homepage em coluna unica, detalhe do job em duas colunas em `lg:`.
- Acessibilidade: `aria-label` nos elementos interativos, `aria-busy` em loaders,
  marcacao semantica com `header`, `main`, `nav`, `aside`, `section`.

---

## 8. Retrocompatibilidade e limites

### 8.1 Estado em memoria vs. disco

O `JobStore` nao persiste entre reinicializacoes. Jobs em andamento no momento de um
restart aparecem como perdidos para o frontend (404 no `GET /api/jobs/{id}`). A persistencia
de longo prazo e responsabilidade do `RunIndex`, que e preenchido pelo pipeline ao final
de cada execucao bem-sucedida.

### 8.2 Jobs falhos no RunIndex

Jobs com `status = "failed"` podem ser resubmetidos pelo usuario (nao ha dedupe de
falhas - a checagem de hash ignora runs com `status == "failed"`).

### 8.3 Fila serial

O worker processa um job por vez. Nao ha paralelismo de jobs no servidor atual. Jobs
adicionais ficam em `queued` ate o anterior concluir.

### 8.4 CORS

O servidor permite apenas `localhost:5173` e `127.0.0.1:5173` em modo CORS. Em producao
(SPA servida pelo mesmo processo), o CORS nao e necessario pois tudo e mesma origem.

### 8.5 Extra `web`

As dependencias do servidor (`fastapi`, `uvicorn`, `python-multipart`, `sse-starlette`) sao
opcionais. O CLI detecta a ausencia e exibe instrucao clara:

```
Dependencias web ausentes: ...
Instale com: pip install 'transcreve-ai[web]'
```
