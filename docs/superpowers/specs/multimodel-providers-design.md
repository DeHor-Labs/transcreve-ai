# Design: Multi-modelo / Providers

**Versao:** 1.0 - 2026-06-02
**Autor:** Nikolas de Hor

---

## 1. Interface base (`video_kb/providers/base.py`)

```python
class AIProvider(ABC):
    def capabilities(self) -> set[Capability]: ...   # obrigatorio

    # Metodos publicos com guard _require()
    def transcribe(audio_path, chunks_dir, language) -> TranscribeResult
    def describe_frame(image_path, metadata, timestamp, ocr_text, transcript_context) -> str
    def synthesize(ctx: SynthesisContext) -> KnowledgeSynthesis
    def embed(texts: list[str]) -> list[list[float]]
```

`Capability = str` com valores canonicos: `"transcribe"`, `"vision"`, `"synthesize"`, `"embed"`.

Qualquer metodo publico chama `self._require(cap)` antes de delegar para o hook `_<metodo>()`.
Se a capacidade nao estiver em `capabilities()`, levanta `CapabilityNotSupported`.

DTOs relevantes:

| Classe | Campos |
|---|---|
| `TranscribeResult` | `text: str`, `segments: list[TranscriptSegment]` |
| `SynthesisContext` | `metadata`, `transcript_text`, `frames` |
| `CapabilityNotSupported` | `provider: str`, `capability: str` |

Constante compartilhada: `AUDIO_CHUNK_LIMIT_BYTES = 24 MB` - limite de chunk de audio para todos os providers.

---

## 2. Registry lazy (`video_kb/providers/registry.py`)

Mapa interno `_REGISTRY: dict[str, str]` com entradas no formato `"nome": "modulo:Classe"`.

```python
_REGISTRY = {
    "openai":    "video_kb.providers.openai_provider:OpenAIProvider",
    "local":     "video_kb.providers.local_provider:LocalProvider",
    "gemini":    "video_kb.providers.gemini_provider:GeminiProvider",
    "anthropic": "video_kb.providers.anthropic_provider:AnthropicProvider",
}
```

- **Import lazy:** `load_provider(name)` usa `importlib.import_module` apenas no momento da chamada. Listar o registry nunca importa dependencias opcionais.
- **Dica de instalacao:** `ImportError` gerado por `load_provider` inclui o comando `pip install transcreve-ai[<extra>]` correspondente.
- **Precedencia de resolucao** (`resolve_provider_name`): CLI `--provider` > env `VIDEO_KB_PROVIDER` > default `"openai"`. String vazia e `None` sao tratados como ausentes.
- **Extensibilidade por entry_points:** terceiros podem registrar providers sem editar o codigo:

```toml
[project.entry-points."transcreve_ai.providers"]
meu_provider = "meu_pacote.providers.meu:MinhaClasse"
```

Ou em codigo:

```python
from video_kb.providers.registry import register
register("meu_provider", "meu_pacote.providers.meu:MinhaClasse")
```

O `__init__.py` do pacote `providers` carrega entry_points automaticamente no import (falha silenciosa se ausentes).

---

## 3. Matriz de capacidades por provider

| Capacidade | openai | local | gemini | anthropic |
|---|:---:|:---:|:---:|:---:|
| `transcribe` | sim | sim | sim | condicional |
| `vision` | sim | nao | sim | sim |
| `synthesize` | sim | sim | sim | sim |
| `embed` | sim | sim | sim | nao |

**Notas:**

- **openai** - usa Whisper-1 para transcricao, gpt-4o-mini para visao/sintese e text-embedding-3-small para embeddings. Modelos configuráveis via `VIDEO_KB_VISION_MODEL` e `VIDEO_KB_TRANSCRIBE_MODEL`.
- **local** - sem chamadas de rede. Transcricao via `faster-whisper` (modelo configuravel por `VIDEO_KB_LOCAL_WHISPER_MODEL`, padrao `"base"`). Embeddings via `sentence-transformers/all-MiniLM-L6-v2`. Sintese estatistica local (sem IA generativa). Sem suporte a visao.
- **gemini** - usa `google-generativeai`. Transcricao via Files API + generate_content. Visao e sintese via `gemini-1.5-flash` (configuravel por `VIDEO_KB_GEMINI_MODEL`). Embeddings via `models/text-embedding-004`. Requer `GEMINI_API_KEY` (aceita tambem `GOOGLE_API_KEY` como fallback).
- **anthropic** - usa o SDK `anthropic`. Visao e sintese via `claude-3-5-sonnet-latest` (configuravel por `VIDEO_KB_ANTHROPIC_MODEL`). Transcricao e condicional: disponivel apenas se `faster-whisper` estiver instalado (delegada ao `LocalProvider`). Embed nao suportado.

---

## 4. Extras de instalacao

| Extra | Dependencias | Providers habilitados |
|---|---|---|
| `transcreve-ai[local]` | `faster-whisper>=1.0.0`, `sentence-transformers>=3.0.0` | `local`; tambem habilita `transcribe` no `anthropic` |
| `transcreve-ai[gemini]` | `google-generativeai>=0.7.0` | `gemini` |
| `transcreve-ai[anthropic]` | `anthropic>=0.30.0` | `anthropic` |

Instalacao de base inclui somente `yt-dlp` e `openai` (suficiente para o provider padrao).

---

## 5. Retrocompatibilidade

O modulo `video_kb.ai` continua reexportando os simbolos que o pipeline usava antes da refatoracao:

- `openai_available()` - verifica presenca de `OPENAI_API_KEY`
- `select_visual_frames(frames, limit)` - distribui frames uniformemente
- `transcript_near(segments, timestamp, window)` - filtra segmentos por janela
- `DEFAULT_VISION_MODEL` - valor padrao de modelo de visao
- `DEFAULT_TRANSCRIBE_MODEL` - valor padrao de modelo de transcricao

Codigo externo que importava esses simbolos diretamente de `video_kb.ai` nao precisa ser alterado.

---

## 6. API publica do pacote `providers`

```python
from video_kb.providers import (
    AIProvider,
    Capability,
    CapabilityNotSupported,
    TranscribeResult,
    SynthesisContext,
    AUDIO_CHUNK_LIMIT_BYTES,
    load_provider,
    register,
    resolve_provider_name,
)
```
