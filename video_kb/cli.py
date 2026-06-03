import argparse
from pathlib import Path

from .pipeline import PipelineOptions, VideoKnowledgePipeline
from .utils import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcreveai",
        description="TranscreveAI extrai dossies multimodais de videos para base de conhecimento.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analisa um link ou arquivo de video")
    analyze.add_argument("source", help="URL ou caminho local do video")
    analyze.add_argument("--out", default="outputs", help="Diretorio de saida")
    analyze.add_argument(
        "--frame-interval", type=float, default=5.0, help="Intervalo entre frames em segundos"
    )
    analyze.add_argument(
        "--max-frames", type=int, default=80, help="Maximo de frames locais (0 = sem limite)"
    )
    analyze.add_argument(
        "--visual-limit", type=int, default=30, help="Maximo de frames enviados para visao por IA"
    )
    analyze.add_argument(
        "--ai",
        choices=["auto", "off", "full"],
        default="auto",
        help="auto usa IA se a chave de API do provider estiver definida",
    )
    analyze.add_argument("--vision-model", default="", help="Modelo de visao/sintese")
    analyze.add_argument("--transcribe-model", default="", help="Modelo de transcricao")
    analyze.add_argument("--language", default=None, help="Idioma do audio, ex: pt, en")
    analyze.add_argument("--tesseract-lang", default="por+eng", help="Idioma OCR desejado")
    analyze.add_argument(
        "--cookies-browser", default=None, help="Browser para cookies do yt-dlp, ex: chrome"
    )
    analyze.add_argument("--cookies", default=None, help="Arquivo cookies.txt para yt-dlp")
    analyze.add_argument("--format", default="bv*+ba/b", help="Formato yt-dlp")
    analyze.add_argument(
        "--provider",
        default="",
        metavar="NOME",
        help=(
            "Provider de IA a usar: openai (padrao), local, gemini, anthropic ou qualquer "
            "provider registrado via entry_points. Pode ser definido tambem via "
            "VIDEO_KB_PROVIDER. Precedencia: --provider > VIDEO_KB_PROVIDER > openai."
        ),
    )
    return parser


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        options = PipelineOptions(
            out_dir=Path(args.out),
            frame_interval=args.frame_interval,
            max_frames=args.max_frames,
            visual_limit=args.visual_limit,
            ai_mode=args.ai,
            vision_model=args.vision_model,
            transcribe_model=args.transcribe_model,
            language=args.language,
            tesseract_lang=args.tesseract_lang,
            cookies_browser=args.cookies_browser,
            cookies=args.cookies,
            video_format=args.format,
            provider_name=args.provider,
        )
        result = VideoKnowledgePipeline(options).run(args.source)
        print("")
        print(f"OK: {result.workdir}")
        print("Markdown: %s" % (Path(result.workdir) / "knowledge.md"))
        print("JSON: %s" % (Path(result.workdir) / "analysis.json"))
