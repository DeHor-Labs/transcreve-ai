# CLI Reference

## Comandos disponiveis

| Comando | Descricao |
|---|---|
| `transcreveai analyze SOURCE` | Analisa um link ou arquivo de video |
| `transcreveai index [RUN_ID\|--all]` | Indexa runs para busca semantica (RAG) |
| `transcreveai ask PERGUNTA` | Faz uma pergunta sobre os videos indexados |
| `transcreveai serve` | Inicia o servidor web com API e SPA |
| `transcreveai runs list` | Lista o historico de runs |
| `transcreveai runs show RUN_ID` | Exibe detalhes de um run |
| `transcreveai runs rm RUN_ID` | Remove um run do indice |

---

## Flag global

```bash
transcreveai [--index-db PATH] COMANDO
```

| Flag | Descricao | Default |
|---|---|---|
| `--index-db PATH` | Path do banco SQLite de indice. Sobreescreve `VIDEO_KB_INDEX_DB`. | `~/.transcreveai/index.db` |

---

## `transcreveai analyze`

Analisa um link ou arquivo de video e grava um dossie multimodal.

```bash
transcreveai analyze SOURCE [opcoes]
```

### Argumento

- `SOURCE`: URL ou caminho local do video.

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--out PATH` | Diretorio de saida | `outputs` |
| `--frame-interval N` | Intervalo entre frames em segundos | `5.0` |
| `--max-frames N` | Maximo de frames locais (`0` = sem limite) | `80` |
| `--visual-limit N` | Maximo de frames enviados para visao por IA | `30` |
| `--ai {auto,off,full}` | Modo de uso da IA. `auto` usa IA se a chave do provider estiver definida | `auto` |
| `--vision-model MODEL` | Modelo de visao/sintese | - |
| `--transcribe-model MODEL` | Modelo de transcricao | - |
| `--language LANG` | Idioma do audio, ex: `pt`, `en` | - |
| `--tesseract-lang LANG` | String de idioma OCR | `por+eng` |
| `--cookies-browser BROWSER` | Browser para cookies do yt-dlp, ex: `chrome` | - |
| `--cookies FILE` | Arquivo `cookies.txt` para yt-dlp | - |
| `--format SELECTOR` | Seletor de formato yt-dlp | `bv*+ba/b` |
| `--provider NOME` | Provider de IA: `openai`, `local`, `gemini`, `anthropic` ou externo via entry_points. Sobreescreve `VIDEO_KB_PROVIDER`. | `openai` |
| `--storage NOME` | Backend de armazenamento: `filesystem`, `obsidian`, `notion`, `supabase`, `s3`. Sobreescreve `VIDEO_KB_STORAGE`. | `filesystem` |
| `--force` | Ignora dedupe: reprocessa mesmo que o `source_hash` ja exista no indice | `false` |

### Comportamento de dedupe

Ao analisar uma fonte, o pipeline calcula um SHA-256 da URL ou do arquivo. Se um run com o mesmo hash ja existir no indice com `status != "failed"`, o pipeline exibe uma mensagem e encerra sem reprocessar. Use `--force` para sobrescrever.

### Exemplos

```bash
# Analise basica com IA automatica
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto --language pt

# Arquivo local sem IA
transcreveai analyze ./video.mp4 --ai off --frame-interval 3 --max-frames 60

# Com cookies de browser para plataformas que exigem login
transcreveai analyze "https://www.instagram.com/reel/..." --cookies-browser chrome --ai auto

# Provider Google Gemini
transcreveai analyze "https://youtu.be/..." --provider gemini --language pt

# Provider offline/gratuito (requer pip install transcreve-ai[local])
transcreveai analyze ./video.mp4 --provider local --ai auto

# Provider Anthropic (requer pip install transcreve-ai[anthropic])
transcreveai analyze "https://youtu.be/..." --provider anthropic --ai auto

# Definir provider via variavel de ambiente
VIDEO_KB_PROVIDER=gemini transcreveai analyze "https://youtu.be/..." --ai auto

# Exportar para vault do Obsidian (requer pip install transcreve-ai[obsidian])
VIDEO_KB_OBSIDIAN_VAULT=~/ObsidianVault transcreveai analyze "https://youtu.be/..." --storage obsidian

# Exportar para Notion (requer pip install transcreve-ai[notion])
transcreveai analyze "https://youtu.be/..." --storage notion

# Upload para S3 (requer pip install transcreve-ai[s3])
transcreveai analyze "https://youtu.be/..." --storage s3

# Forcando reprocessamento de source ja indexada
transcreveai analyze "https://youtu.be/..." --force

# Banco de indice customizado
transcreveai --index-db ~/projetos/meu.db analyze "https://youtu.be/..."
```

---

## `transcreveai index`

Indexa um ou todos os runs para busca semantica. Requer o extra `[rag]`:

```bash
pip install 'transcreve-ai[rag]'
```

```bash
transcreveai index [RUN_ID | --all] [opcoes]
```

### Argumentos

- `RUN_ID`: ID do run a indexar (posicional, omitir quando `--all` for passado).

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--all` | Indexa todos os runs ainda nao indexados | `false` |
| `--provider NOME` | Provider de embedding: `openai`, `local` ou `gemini`. Sobreescreve `VIDEO_KB_PROVIDER`. | `openai` |
| `--force` | Reindexar mesmo que o run ja tenha embeddings | `false` |

O `--index-db` global tambem e respeitado.

### Comportamento

- Pula runs cujo `analysis_path` nao existe no disco.
- Pula runs ja indexados a menos que `--force` seja passado.
- Com `--force`, apaga os embeddings anteriores e regenera todos os chunks.
- Levanta erro se o provider atual gerar vetores com dimensao diferente da ja armazenada para o mesmo run (use `--force` para resolver).

### Modelos de embedding por provider

| Provider | Modelo | Offline |
|---|---|:---:|
| `openai` | `text-embedding-3-small` | Nao |
| `local` | `all-MiniLM-L6-v2` | Sim |
| `gemini` | `text-embedding-004` | Nao |

### Exemplos

```bash
# Indexar um run especifico
transcreveai index 20260601T060803Z-youtu-be-abc123

# Indexar todos os runs nao indexados (provider padrao)
transcreveai index --all

# Indexar tudo com provider offline
transcreveai index --all --provider local

# Forcar reindexacao com provider diferente
transcreveai index 20260601T060803Z-youtu-be-abc123 --provider gemini --force

# Com banco de indice customizado
transcreveai --index-db ~/projetos/meu.db index --all

# Definir provider via variavel de ambiente
VIDEO_KB_PROVIDER=local transcreveai index --all
```

---

## `transcreveai ask`

Faz uma pergunta sobre os videos indexados usando RAG. Requer o extra `[rag]`:

```bash
pip install 'transcreve-ai[rag]'
```

```bash
transcreveai ask PERGUNTA [opcoes]
```

### Argumento

- `PERGUNTA`: Texto da pergunta em linguagem natural (posicional).

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--provider NOME` | Provider de embedding e sintese: `openai`, `local` ou `gemini`. Sobreescreve `VIDEO_KB_PROVIDER`. | `openai` |
| `--top-k N` | Numero de trechos de contexto a recuperar | `5` |
| `--run-ids ID [ID...]` | Limita a busca a runs especificos | todos |
| `--search-only` | Exibe apenas os trechos recuperados, sem chamar LLM para sintese | `false` |

O `--index-db` global tambem e respeitado.

### Comportamento

- Vetoriza a pergunta com o provider escolhido.
- Busca os `top-k` chunks mais similares por cosseno no SQLite.
- Se `--search-only`: imprime os trechos com score, tipo e capitulo (quando disponivel) e encerra.
- Caso contrario: monta prompt com os trechos como contexto e chama o LLM do provider para gerar resposta.
- A resposta e instruida a citar os videos usados e a dizer explicitamente quando a informacao nao esta nos videos indexados.

### Saida padrao (RAG completo)

```
Pergunta: o que foi dito sobre autenticacao?

Resposta:
No video "Como usar TranscreveAI" foi mencionado que...

Fontes:
  [1] Como usar TranscreveAI (20260601T060803Z-youtu-be-abc123) - score: 87.3%
  [2] Aula de Python (20260531T120000Z-video-mp4) - score: 74.1%
```

### Saida com `--search-only`

```
Top 3 trechos para: "autenticacao"

[1] Como usar TranscreveAI (summary) - score: 87.3%
    O video demonstra o fluxo de autenticacao via OAuth2...
    Capitulo em: 3:42

[2] Aula de Python (transcript) - score: 74.1%
    ...implementacao do middleware de autenticacao JWT...
```

### Exemplos

```bash
# Pergunta simples (RAG completo, provider padrao)
transcreveai ask "o que foi dito sobre autenticacao?"

# Busca sem sintese (inspecionar chunks indexados)
transcreveai ask "autenticacao" --search-only

# Limitar a dois runs
transcreveai ask "quais ferramentas foram mostradas?" \
  --run-ids 20260601T060803Z-youtu-be-abc123 20260531T120000Z-video-mp4

# Usar provider offline
transcreveai ask "resumo dos capitulos" --provider local

# Mais contexto (10 trechos)
transcreveai ask "fluxo de deploy" --top-k 10

# Com banco de indice customizado
transcreveai --index-db ~/projetos/meu.db ask "qual e a arquitetura?"

# Definir provider via variavel de ambiente
VIDEO_KB_PROVIDER=gemini transcreveai ask "o que foi discutido?"
```

---

## `transcreveai runs list`

Lista runs registrados no indice, ordenados do mais recente para o mais antigo.

```bash
transcreveai runs list [opcoes]
```

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--limit N` | Numero maximo de entradas retornadas | `20` |
| `--json` | Saida em JSON array (integravel com `jq`, scripts, etc.) | `false` |
| `--out PATH` | Filtrar apenas runs com `output_dir` igual ao valor informado | - |

### Saida padrao (tabela)

```
ID                                       STATUS     TITULO                               CRIADO EM
----------------------------------------------------------------------------------------------------
20260601T060803Z-youtu-be-abc123         completed  Como usar TranscreveAI               2026-06-01T06:08:03+00:00
20260531T120000Z-video-mp4               completed  Aula de Python                        2026-05-31T12:00:00+00:00
```

### Saida JSON (`--json`)

```json
[
  {
    "id": "20260601T060803Z-youtu-be-abc123",
    "source": "https://youtu.be/abc123",
    "source_hash": "e3b0c44...",
    "title": "Como usar TranscreveAI",
    "provider": "openai",
    "ai_mode": "auto",
    "status": "completed",
    "created_at": "2026-06-01T06:08:03+00:00",
    "finished_at": "2026-06-01T06:12:47+00:00",
    "output_dir": "outputs/20260601T060803Z-youtu-be-abc123",
    "analysis_path": "outputs/20260601T060803Z-youtu-be-abc123/analysis.json",
    "markdown_path": "outputs/20260601T060803Z-youtu-be-abc123/knowledge.md",
    "duration_seconds": 312.0,
    "warnings_count": 0,
    "storage_backend": "filesystem"
  }
]
```

### Exemplos

```bash
transcreveai runs list
transcreveai runs list --limit 50
transcreveai runs list --json
transcreveai runs list --json | jq '.[].title'
transcreveai runs list --out outputs/20260601T060803Z-youtu-be-abc123
```

---

## `transcreveai runs show`

Exibe todos os campos de um run especifico.

```bash
transcreveai runs show RUN_ID [opcoes]
```

### Argumento

- `RUN_ID`: ID exato do run (coluna `id` no indice).

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--json` | Saida em JSON bruto | `false` |

### Exemplos

```bash
transcreveai runs show 20260601T060803Z-youtu-be-abc123
transcreveai runs show 20260601T060803Z-youtu-be-abc123 --json
```

---

## `transcreveai runs rm`

Remove um run do indice SQLite. Opcionalmente apaga tambem o diretorio de saida do disco.

```bash
transcreveai runs rm RUN_ID [opcoes]
```

### Argumento

- `RUN_ID`: ID exato do run a remover.

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--purge` | Tambem deleta o `output_dir` do filesystem (`rm -rf`) | `false` |
| `--force` | Nao pede confirmacao interativa | `false` |

Por padrao, o comando pede confirmacao antes de remover. Use `--force` para scripts e automacoes.

### Exemplos

```bash
# Remove do indice (pede confirmacao)
transcreveai runs rm 20260601T060803Z-youtu-be-abc123

# Remove do indice sem confirmacao
transcreveai runs rm 20260601T060803Z-youtu-be-abc123 --force

# Remove do indice e apaga o diretorio de saida do disco
transcreveai runs rm 20260601T060803Z-youtu-be-abc123 --purge

# Remove tudo sem confirmacao (uso em scripts)
transcreveai runs rm 20260601T060803Z-youtu-be-abc123 --purge --force
```

---

---

## `transcreveai serve`

Inicia o servidor web TranscreveAI. Requer o extra `web` instalado:

```bash
pip install 'transcreve-ai[web]'
```

```bash
transcreveai serve [opcoes]
```

### Opcoes

| Flag | Descricao | Default |
|---|---|---|
| `--host HOST` | Endereco de bind do servidor | `127.0.0.1` |
| `--port PORT` | Porta do servidor | `8000` |
| `--out DIR` | Diretorio de saida dos jobs processados | `outputs` |
| `--reload` | Hot-reload para desenvolvimento (nao usar em producao) | `false` |

O `--index-db` global tambem e respeitado:

```bash
transcreveai --index-db ~/meu.db serve --port 8080
```

### Comportamento

- Sobe uma aplicacao FastAPI com a API REST em `/api/*` e docs Swagger em `/api/docs`.
- Se `frontend/dist/` existir, serve a SPA em `/`. Caso contrario, apenas a API fica disponivel.
- Processa jobs de forma serial (um por vez) em background com asyncio.

### Exemplos

```bash
# Inicio basico
transcreveai serve

# Exposto na rede local, porta alternativa
transcreveai serve --host 0.0.0.0 --port 8080

# Com banco de indice customizado
transcreveai --index-db ~/projetos/meu.db serve

# Desenvolvimento com hot-reload (backend)
transcreveai serve --reload

# Construir e servir o frontend em producao
cd frontend && pnpm build
transcreveai serve
```

---

## Variaveis de ambiente

### Providers de IA

| Variavel | Descricao |
|---|---|
| `VIDEO_KB_PROVIDER` | Provider padrao quando `--provider` nao e passado |
| `OPENAI_API_KEY` | Chave para o provider `openai` |
| `GEMINI_API_KEY` | Chave para o provider `gemini` (aceita `GOOGLE_API_KEY` como fallback) |
| `ANTHROPIC_API_KEY` | Chave para o provider `anthropic` |
| `VIDEO_KB_LOCAL_WHISPER_MODEL` | Modelo faster-whisper para o provider `local` (default: `base`) |

### Storage e indice

| Variavel | Descricao | Default |
|---|---|---|
| `VIDEO_KB_INDEX_DB` | Path do banco SQLite de indice | `~/.transcreveai/index.db` |
| `VIDEO_KB_STORAGE` | Backend de storage padrao | `filesystem` |
| `VIDEO_KB_OBSIDIAN_VAULT` | Caminho absoluto da vault Obsidian | - |
| `VIDEO_KB_OBSIDIAN_SUBDIR` | Subpasta dentro da vault | `transcreve-ai` |
| `NOTION_API_KEY` | Token de integracao interna do Notion | - |
| `NOTION_DATABASE_ID` | UUID do banco de dados Notion destino | - |
| `VIDEO_KB_S3_BUCKET` | Nome do bucket S3 | - |
| `VIDEO_KB_S3_PREFIX` | Prefixo/pasta dentro do bucket (opcional) | - |
| `AWS_DEFAULT_REGION` | Regiao AWS | `us-east-1` |
| `AWS_ENDPOINT_URL` | Endpoint S3-compatible: Minio, LocalStack, etc. | - |
| `SUPABASE_URL` | URL do projeto Supabase (fase futura) | - |
| `SUPABASE_KEY` | Chave anon/service Supabase (fase futura) | - |
