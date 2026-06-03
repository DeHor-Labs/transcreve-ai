# CLI Reference

## `transcreveai analyze`

Analyze a URL or local video file.

```bash
transcreveai analyze SOURCE [options]
```

## Arguments

- `SOURCE`: URL or local video path.

## Options

- `--out`: output directory. Default: `outputs`.
- `--frame-interval`: seconds between candidate frames. Default: `5`.
- `--max-frames`: maximum local frames. `0` means no limit. Default: `80`.
- `--visual-limit`: maximum frames sent for AI visual analysis. Default: `30`.
- `--ai`: `auto`, `off` or `full`. Default: `auto`.
- `--vision-model`: model for visual notes and synthesis.
- `--transcribe-model`: model for transcription.
- `--language`: audio language hint, for example `pt` or `en`.
- `--tesseract-lang`: OCR language string. Default: `por+eng`.
- `--cookies-browser`: browser cookies for `yt-dlp`, for example `chrome`.
- `--cookies`: path to a `cookies.txt` file.
- `--format`: `yt-dlp` format selector.
- `--provider`: AI provider to use. Accepted values: `openai` (default), `local`, `gemini`, `anthropic`, or any provider registered via entry_points. Can also be set via the `VIDEO_KB_PROVIDER` environment variable. Precedence: `--provider` > `VIDEO_KB_PROVIDER` > `openai`.

## Examples

```bash
transcreveai analyze "https://www.instagram.com/reel/..." --ai auto --language pt
```

```bash
transcreveai analyze ./video.mp4 --ai off --frame-interval 3 --max-frames 60
```

```bash
transcreveai analyze "https://youtu.be/..." --cookies-browser chrome --visual-limit 12
```

```bash
# Provider Google Gemini
transcreveai analyze "https://youtu.be/..." --provider gemini --language pt

# Provider offline/gratuito (requer pip install transcreve-ai[local])
transcreveai analyze ./video.mp4 --provider local --ai auto

# Provider Anthropic (requer pip install transcreve-ai[anthropic])
transcreveai analyze "https://youtu.be/..." --provider anthropic --ai auto

# Definir provider via variavel de ambiente
VIDEO_KB_PROVIDER=gemini transcreveai analyze "https://youtu.be/..." --ai auto
```
