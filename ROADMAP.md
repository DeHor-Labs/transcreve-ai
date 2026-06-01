# TranscreveAI Roadmap

## Agora

- CLI para receber link ou arquivo local.
- Download por `yt-dlp`.
- Extracao de audio e frames por `ffmpeg`.
- OCR local por `tesseract`.
- Transcricao, notas visuais e sintese por IA quando `OPENAI_API_KEY` estiver configurada.
- Saida em `analysis.json` e `knowledge.md`.

## Proximas evolucoes

- Webhook HTTP para receber `{ "url": "..." }` e processar em background.
- Fila de jobs com status: queued, running, done, failed.
- Persistencia dos dossies em Obsidian, Notion, Drive, Supabase ou bucket S3/R2.
- Indexacao vetorial para busca semantica por trecho, ferramenta citada, produto, pessoa ou timestamp.
- Deduplicacao por URL/hash para evitar reprocessar o mesmo video.
- Interface web simples para acompanhar jobs e revisar dossies.
- Exportadores para Markdown, JSONL, CSV e chunks prontos para RAG.
- Modo custo baixo: transcricao completa, menos frames visuais.
- Modo investigativo: mais frames, OCR agressivo, cena a cena e extracao de links/produtos.

## Cuidados

- Nunca commitar `.env`, `outputs/`, videos baixados ou chaves de API.
- Redes sociais podem exigir cookies ou login; preferir tentar sem cookies primeiro.
- Para producao, rodar em Python 3.10+ e usar secrets do ambiente/infra, nao arquivo local.
