# Architecture

TranscreveAI is intentionally small: a CLI orchestrates a media pipeline and produces stable artifacts.

## Pipeline

1. **Input**
   - URL supported by `yt-dlp`, or a local video file.
2. **Media acquisition**
   - URL sources are downloaded into the run directory.
   - Local files are copied into the run directory.
3. **Metadata**
   - `yt-dlp` metadata is used when available.
   - `ffprobe` fills duration when needed.
4. **Audio**
   - `ffmpeg` extracts `audio.mp3`.
5. **Frames**
   - `ffmpeg` samples frames across the duration.
   - `--max-frames` caps local frame volume.
6. **OCR**
   - `tesseract` extracts visible text from each sampled frame.
7. **AI layer**
   - Audio transcription creates timestamped segments.
   - Selected frames receive visual notes.
   - Transcript, OCR and frame notes are synthesized into knowledge fields.
8. **Artifacts**
   - `analysis.json` is the structured source of truth.
   - `knowledge.md` is the readable dossier.

## Data Flow

```text
source -> media_path -> audio_path + frames
frames -> OCR -> frame observations
audio -> transcript segments
metadata + transcript + frames -> synthesis
synthesis + raw observations -> JSON + Markdown
```

## Design Choices

- Keep downloaded media and outputs out of Git.
- Keep the CLI useful without AI keys.
- Make AI calls optional and bounded by `--visual-limit`.
- Store enough raw evidence for future re-indexing.
- Prefer plain files over a database in the MVP.

## Future Backend Shape

A production worker can wrap the CLI with:

- queue: Redis, Postgres, Supabase or durable queue;
- storage: local disk, S3, R2, Drive or Supabase Storage;
- status API: queued/running/done/failed;
- knowledge indexing: vector database or Postgres full-text search;
- UI: upload/link form plus run history.
