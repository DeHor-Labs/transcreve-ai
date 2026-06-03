# Design da Camada de Persistencia

**Modulo:** `video_kb/index.py` + `video_kb/storage/`
**Status:** implementado (alpha)
**Autor:** Nikolas de Hor

---

## Visao geral

A camada de persistencia do TranscreveAI e composta por dois subsistemas independentes que colaboram ao final de cada run do pipeline:

1. **Indice SQLite** (`video_kb/index.py`) - metadados de todos os runs; dedupe por hash de fonte; historico consultavel via CLI.
2. **Storage backends** (`video_kb/storage/`) - destino final dos artefatos produzidos (filesystem, Obsidian, Notion, S3, Supabase); selecionavel por flag ou env var; arquitetura de plugin.

O pipeline (`VideoKnowledgePipeline.run`) orquestra ambos na etapa 6 (pos-analise). Falhas em qualquer um dos subsistemas sao gracis: o pipeline nao aborta, adiciona um warning ao resultado e retorna os artefatos locais.

---

## 1. Indice SQLite

### 1.1 Localizacao e resolucao de caminho

```
resolve_index_path(cli_flag=None) -> Path

Precedencia:
  1. cli_flag (--index-db do CLI)
  2. variavel de ambiente VIDEO_KB_INDEX_DB
  3. ~/.transcreveai/index.db  (default)
```

O diretorio pai e criado automaticamente com `mkdir(parents=True, exist_ok=True)` na primeira conexao.

### 1.2 Schema

Tabela unica: `runs`

| Coluna | Tipo | Descricao |
|---|---|---|
| `id` | TEXT PK | run_id gerado pelo pipeline (`<timestamp>-<slug-fonte>`) |
| `source` | TEXT | URL ou caminho local original |
| `source_hash` | TEXT | SHA-256 da fonte (URL ou arquivo) |
| `title` | TEXT | Titulo extraido dos metadados do video |
| `provider` | TEXT | Provider de IA usado (`openai`, `gemini`, etc.) |
| `ai_mode` | TEXT | Modo de IA (`auto`, `off`, `full`) |
| `status` | TEXT | `partial` durante execucao, `completed` ou `failed` |
| `created_at` | TEXT | ISO 8601 UTC do inicio do run |
| `finished_at` | TEXT | ISO 8601 UTC do fim do run |
| `output_dir` | TEXT | Path ou URI do diretorio/prefixo de saida final |
| `analysis_path` | TEXT | Path ou URI de `analysis.json` |
| `markdown_path` | TEXT | Path ou URI de `knowledge.md` |
| `duration_seconds` | REAL | Duracao do video em segundos |
| `warnings_count` | INTEGER | Numero de warnings gerados |
| `storage_backend` | TEXT | Nome do backend usado (`filesystem`, `s3`, etc.) |

Indices criados automaticamente:
- `idx_runs_source_hash` em `(source_hash)` - lookup de dedupe O(log n)
- `idx_runs_created_at` em `(created_at DESC)` - listagem cronologica
- `idx_runs_status` em `(status)` - filtro por status

Configuracoes SQLite ativadas na abertura:
- `PRAGMA journal_mode=WAL` - leituras concorrentes sem bloqueio de escrita
- `PRAGMA foreign_keys=ON`
- `timeout=10` segundos para aquisicao de lock

### 1.3 Classe RunIndex

Gerenciador de contexto recomendado:

```python
with RunIndex() as idx:
    idx.register(run_id, source, source_hash, ...)
    idx.update_run(run_id, status="completed", ...)
```

Tambem pode ser instanciado sem `with` para uso direto; a conexao e aberta no primeiro metodo chamado (lazy).

**Metodos publicos:**

| Metodo | Descricao |
|---|---|
| `register(run_id, source, source_hash, **kwargs)` | INSERT OR REPLACE - idempotente por run_id |
| `update_run(run_id, **fields)` | Atualiza campos especificos de um run existente |
| `find_by_hash(source_hash)` | Retorna o run mais recente com aquele hash, ou None |
| `list_runs(limit, output_dir_filter)` | Lista runs ordenados por created_at DESC |
| `get_run(run_id)` | Retorna run pelo ID exato, ou None |
| `delete_run(run_id)` | Remove run do indice; retorna bool |
| `close()` | Fecha a conexao SQLite |

Aliases mantidos para uniformidade de API: `add_run = register`, `remove_run = delete_run`.

### 1.4 Deduplicacao por hash

O hash e calculado antes ou apos o download dependendo do tipo de fonte:

- **URL** (`http://` ou `https://`): `sha256_url(source)` calculado a partir da URL normalizada, antes do download. Permite early-exit de dedupe sem baixar o video.
- **Arquivo local**: `sha256_file(media_path)` calculado apos o download/copia, sobre o conteudo do arquivo.

Fluxo de dedupe no pipeline:

```
1. Calcula source_hash
2. find_by_hash(source_hash) no indice
3. Se existir e status != "failed" e --force nao passado:
       levanta DuplicateRunError(existing)
4. Caso contrario: prossegue e registra com status="partial"
5. Ao final: update_run(status="completed", ...)
```

`DuplicateRunError` carrega o atributo `.existing` (dict com todos os campos do run pre-existente) para o CLI exibir o run_id e output_dir ao usuario.

Com `--force`, a verificacao de dedupe e ignorada e o run e registrado normalmente (INSERT OR REPLACE substitui o registro anterior pelo mesmo run_id, se houver).

### 1.5 Graciosidade

Toda interacao com o indice e envolvida em `try/except Exception` no pipeline. Se o banco estiver corrompido, sem permissao ou indisponivel, o pipeline continua normalmente sem indice. O flag `_index_ok` controla se as operacoes subsequentes tentam usar o indice.

---

## 2. Interface de Storage (ABC)

### 2.1 Tipos de dados

**`ArtifactPaths`** (dataclass) - caminhos locais dos artefatos produzidos pelo pipeline antes de `save()`:

```
analysis_json: Path   # run_dir/analysis.json
markdown:      Path   # run_dir/knowledge.md
frames_dir:    Path   # run_dir/frames/
run_dir:       Path   # diretorio raiz do run
```

**`StorageRef`** (dataclass) - referencia retornada por `save()`; usada para preencher o indice:

```
backend:       str          # nome do backend ("filesystem", "s3", ...)
output_dir:    str          # path ou URI do diretorio/prefixo final
analysis_path: str          # path ou URI de analysis.json
markdown_path: str          # path ou URI de knowledge.md
extra:         dict[str, Any]  # metadados extras do backend (page_id, bucket, etc.)
```

### 2.2 StorageBackend (ABC)

```python
class StorageBackend(ABC):

    @abstractmethod
    def save(
        self,
        result: AnalysisResult,
        artifacts: ArtifactPaths,
        **opts: Any,
    ) -> StorageRef:
        """Persiste artefatos e retorna referencia final. Deve ser idempotente."""
        ...

    def health_check(self) -> None:
        """
        Verifica conectividade/credenciais.
        Levanta RuntimeError com mensagem clara se algo estiver errado.
        Default: noop (filesystem nao precisa checar nada).
        """
```

Contrato de `save()`:
- Recebe os artefatos ja gravados localmente pelo pipeline (etapa 6 pre-storage).
- Persiste no destino e retorna `StorageRef`.
- Deve ser idempotente: chamadas repetidas com o mesmo `run_id` nao devem duplicar dados no destino.
- Falhas propagam excecao; o pipeline captura e adiciona warning.

---

## 3. Registry lazy de backends

**Arquivo:** `video_kb/storage/registry.py`

### 3.1 Mapa interno

```python
_REGISTRY: dict[str, str] = {
    "filesystem": "video_kb.storage.filesystem:FilesystemBackend",
    "obsidian":   "video_kb.storage.obsidian:ObsidianBackend",
    "notion":     "video_kb.storage.notion:NotionBackend",
    "supabase":   "video_kb.storage.supabase:SupabaseBackend",
    "s3":         "video_kb.storage.s3:S3Backend",
}
```

### 3.2 API publica

```python
load_storage(name: str, **opts) -> StorageBackend
```
Faz lazy import do modulo e instancia a classe. Levanta `KeyError` se o nome nao estiver registrado. Levanta `ImportError` com dica de instalacao se a dependencia opcional estiver ausente.

```python
resolve_storage_name(cli_flag: str | None = None) -> str
```
Determina o backend seguindo a precedencia:
1. `cli_flag` (flag `--storage` do CLI)
2. Variavel de ambiente `VIDEO_KB_STORAGE`
3. Default `"filesystem"`

```python
register_storage(name: str, module_path: str) -> None
```
Registra backend externo sem editar o arquivo. Pode ser chamado programaticamente ou via entry_points do `pyproject.toml`:

```toml
[project.entry-points."transcreve_ai.storage"]
meu_backend = "meu_pacote.storage.meu:MinhaClasse"
```

### 3.3 Hints de instalacao

Quando `load_storage` falha por `ImportError`, a mensagem inclui o comando exato de instalacao:

| Backend | Hint |
|---|---|
| `obsidian` | `pip install transcreve-ai[obsidian]` |
| `notion` | `pip install transcreve-ai[notion]` |
| `supabase` | `pip install transcreve-ai[supabase]` |
| `s3` | `pip install transcreve-ai[s3]` |

---

## 4. Backends implementados

### 4.1 FilesystemBackend (padrao)

- **Zero side-effects alem dos que o pipeline ja faz.**
- Os artefatos ja existem no `run_dir`; o backend apenas retorna os paths locais encapsulados em `StorageRef`.
- Sem dependencias opcionais.
- Comportamento identico ao anterior a existencia do modulo de storage (retrocompativel).

### 4.2 ObsidianBackend

- **Dependencia opcional:** `python-frontmatter>=1.0.0` (`pip install transcreve-ai[obsidian]`)
- **Env vars:**
  - `VIDEO_KB_OBSIDIAN_VAULT` (obrigatorio se nao passado como `vault_path`)
  - `VIDEO_KB_OBSIDIAN_SUBDIR` (default: `"transcreve-ai"`)
- **Fluxo de `save()`:**
  1. Resolve o caminho da vault.
  2. Importa `python-frontmatter`.
  3. Le `knowledge.md` ja gravado.
  4. Injeta frontmatter YAML: `title`, `fonte`, `provider`, `data`, `tags`, `run_id`.
  5. Grava em `<vault>/<subdir>/<run_id>/knowledge.md`.
  6. Se `copy_frames=True`, copia o diretorio `frames/` inteiro.
  7. Retorna `StorageRef` com `extra={"vault": ..., "frames_dir": ...}`.
- O `analysis_path` no `StorageRef` aponta para o arquivo local (nao copiado para a vault por padrao).

### 4.3 NotionBackend

- **Dependencia opcional:** `notion-client>=2.2.0` (`pip install transcreve-ai[notion]`)
- **Env vars:**
  - `NOTION_API_KEY` (token de integracao interna - obrigatorio)
  - `NOTION_DATABASE_ID` (UUID do banco destino - obrigatorio)
- **Fluxo de `save()`:**
  1. Valida credenciais.
  2. Converte `AnalysisResult` em lista de blocos Notion (paragrafos, heading_2, bullet_list_item, divider).
  3. Cria pagina no banco com titulo = `metadata.title or source or run_id`.
  4. A API do Notion aceita maximo 100 blocos por request de criacao; blocos extras sao appendados em lotes de 100.
  5. Retorna `StorageRef` com `extra={"page_id": ..., "page_url": ..., "database_id": ...}`.
- **Nota de idempotencia:** a API do Notion nao oferece busca por campo arbitrario de forma gratuita; chamadas repetidas criam paginas duplicadas. Use o indice SQLite como guard de dedupe.

### 4.4 S3Backend

- **Dependencia opcional:** `boto3>=1.34.0` (`pip install transcreve-ai[s3]`)
- **Env vars:**
  - `VIDEO_KB_S3_BUCKET` (obrigatorio)
  - `VIDEO_KB_S3_PREFIX` (opcional - prefixo/pasta dentro do bucket)
  - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (ou cadeia de credenciais padrao AWS)
  - `AWS_DEFAULT_REGION` (default: `us-east-1`)
  - `AWS_ENDPOINT_URL` (opcional - Minio, LocalStack, etc.)
- **Fluxo de `save()`:**
  1. Monta o prefixo: `<VIDEO_KB_S3_PREFIX>/<run_id>` ou `<run_id>` se sem prefixo.
  2. Faz upload de `analysis.json` para `<prefix>/analysis.json`.
  3. Faz upload de `knowledge.md` para `<prefix>/knowledge.md`.
  4. Retorna `StorageRef` com URIs `s3://<bucket>/<key>` e `extra={"bucket": ..., "prefix": ..., "region": ...}`.
- Idempotente: chaves ja existentes no bucket sao sobrescritas.
- `health_check()` executa `head_bucket` para verificar acesso antes de iniciar o pipeline.

### 4.5 SupabaseBackend

- **Status: nao implementado** (`save()` levanta `NotImplementedError`).
- **Dependencia opcional:** `supabase>=2.0.0` (`pip install transcreve-ai[supabase]`)
- **Env vars previstas:** `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_BUCKET` (default: `transcreve-ai`).
- Reservado para fase futura. Use `--storage filesystem` por enquanto.

---

## 5. Configuracao por variavel de ambiente

| Variavel | Modulo | Descricao | Default |
|---|---|---|---|
| `VIDEO_KB_INDEX_DB` | `index.py` | Path do banco SQLite | `~/.transcreveai/index.db` |
| `VIDEO_KB_STORAGE` | `storage/registry.py` | Backend de storage padrao | `filesystem` |
| `VIDEO_KB_OBSIDIAN_VAULT` | `storage/obsidian.py` | Path absoluto da vault Obsidian | - |
| `VIDEO_KB_OBSIDIAN_SUBDIR` | `storage/obsidian.py` | Subpasta dentro da vault | `transcreve-ai` |
| `NOTION_API_KEY` | `storage/notion.py` | Token de integracao Notion | - |
| `NOTION_DATABASE_ID` | `storage/notion.py` | ID do banco Notion destino | - |
| `VIDEO_KB_S3_BUCKET` | `storage/s3.py` | Nome do bucket S3 | - |
| `VIDEO_KB_S3_PREFIX` | `storage/s3.py` | Prefixo dentro do bucket | - |
| `AWS_ACCESS_KEY_ID` | `storage/s3.py` | Credencial AWS | cadeia padrao |
| `AWS_SECRET_ACCESS_KEY` | `storage/s3.py` | Credencial AWS | cadeia padrao |
| `AWS_DEFAULT_REGION` | `storage/s3.py` | Regiao AWS | `us-east-1` |
| `AWS_ENDPOINT_URL` | `storage/s3.py` | Endpoint S3-compatible (Minio, etc.) | - |
| `SUPABASE_URL` | `storage/supabase.py` | URL do projeto Supabase | - |
| `SUPABASE_KEY` | `storage/supabase.py` | Chave anon/service Supabase | - |
| `SUPABASE_BUCKET` | `storage/supabase.py` | Bucket Supabase | `transcreve-ai` |

---

## 6. Retrocompatibilidade

- Antes da introducao deste modulo, o pipeline gravava artefatos localmente e nao registrava nada em banco.
- O `FilesystemBackend` preserva exatamente esse comportamento: nenhum arquivo e movido ou copiado.
- O indice SQLite e criado silenciosamente na primeira execucao; se o diretorio `~/.transcreveai/` nao existir, e criado automaticamente.
- Instalacoes existentes sem nenhuma variavel de storage configurada continuam funcionando sem alteracao de comportamento.
- O flag `--force` permite reprocessar sources ja indexadas, substituindo o registro anterior no indice via `INSERT OR REPLACE`.

---

## 7. Fluxo completo no pipeline

```
VideoKnowledgePipeline.run(source)
  |
  +-- resolve_index_path()                    # determina path do SQLite
  +-- RunIndex._connect()                     # abre conexao (gracil)
  +-- sha256_url(source) ou sha256_file()     # calcula hash
  +-- find_by_hash() + DuplicateRunError?     # dedupe (early-exit)
  +-- register(..., status="partial")         # registro inicial
  |
  | [etapas 1-6: download, audio, frames, OCR, IA, gravacao local]
  |
  +-- load_storage(storage_name)              # instancia backend (lazy import)
  +-- backend.save(result, artifacts)         # persiste no destino
  +-- update_run(..., status="completed")     # atualiza indice com paths finais
  +-- RunIndex.close()
```
