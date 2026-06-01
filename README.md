# TranscreveAI

Ferramenta para transformar um link de video em um dossie de base de conhecimento: metadados, audio, transcricao, frames, OCR, notas visuais, timeline e resumo estruturado.

O MVP funciona em duas camadas:

- **Local**: baixa o video com `yt-dlp`, extrai audio e frames com `ffmpeg`, roda OCR com `tesseract` e gera `analysis.json` + `knowledge.md`.
- **IA opcional**: com `OPENAI_API_KEY`, transcreve o audio, descreve frames-chave e sintetiza entidades, claims, passos, ferramentas citadas e notas para consulta futura.

## Requisitos

No macOS, estes binarios ja existem nesta maquina pelo menos no momento da criacao:

```bash
ffmpeg -version
yt-dlp --version
tesseract --version
```

Instale o pacote em modo editavel:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Para ativar a camada de IA:

```bash
export OPENAI_API_KEY="..."
```

Modelos podem ser ajustados por variavel ou flag:

```bash
export VIDEO_KB_VISION_MODEL="gpt-4o-mini"
export VIDEO_KB_TRANSCRIBE_MODEL="whisper-1"
```

## Uso

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto
```

Se a plataforma exigir login, tente novamente com cookies:

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --cookies-browser chrome --ai auto
```

Exemplo mais completo:

```bash
transcreveai analyze "https://youtu.be/..." \
  --out outputs \
  --frame-interval 4 \
  --max-frames 80 \
  --visual-limit 30 \
  --ai auto
```

Para arquivo local:

```bash
transcreveai analyze ./video.mp4 --ai auto
```

Resultados ficam em `outputs/<data>-<slug>/`:

- `source.*`: video baixado ou copiado.
- `audio.mp3`: audio extraido.
- `frames/`: imagens amostradas com timestamps.
- `analysis.json`: artefato estruturado para indexacao.
- `knowledge.md`: dossie legivel para leitura humana.

## Automacao por link

O CLI ja foi desenhado para virar automacao:

1. Um webhook recebe `{ "url": "..." }`.
2. O worker executa `transcreveai analyze "$url" --ai auto`.
3. O arquivo `analysis.json` e indexado na base de conhecimento.
4. O `knowledge.md` e salvo em Obsidian/Notion/Drive/Git, ou enviado de volta no canal.

Para videos privados ou redes sociais com login, use `--cookies-browser chrome` ou `--cookies cookies.txt`.

## Observacoes

- Instagram, TikTok e outras plataformas podem exigir cookies ou login.
- O modo local captura visual/OCR, mas a qualidade de "ver e anotar tudo" depende da camada de IA.
- Para videos longos, use `--frame-interval` maior ou `--max-frames` para controlar custo e tamanho do dossie.
