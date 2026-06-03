from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .index import DuplicateRunError, RunIndex, resolve_index_path
from .pipeline import PipelineOptions, VideoKnowledgePipeline
from .utils import load_dotenv

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcreveai",
        description="TranscreveAI extrai dossies multimodais de videos para base de conhecimento.",
    )

    # Flags globais
    parser.add_argument(
        "--index-db",
        default=None,
        metavar="PATH",
        help=(
            "Path do banco SQLite de indice. "
            "Sobreescreve VIDEO_KB_INDEX_DB. "
            "Default: ~/.transcreveai/index.db"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # analyze
    # ------------------------------------------------------------------
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
    analyze.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Ignora dedupe: reprocessa mesmo que o source_hash ja exista no indice.",
    )
    analyze.add_argument(
        "--storage",
        default="",
        metavar="NOME",
        help=(
            "Backend de armazenamento: filesystem (padrao), obsidian, notion, supabase, s3. "
            "Sobreescreve VIDEO_KB_STORAGE."
        ),
    )

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------
    runs_parser = subparsers.add_parser("runs", help="Gerencia o historico de runs")
    runs_sub = runs_parser.add_subparsers(dest="runs_command", required=True)

    # runs list
    runs_list = runs_sub.add_parser("list", help="Lista runs do indice")
    runs_list.add_argument(
        "--limit", type=int, default=20, help="Numero maximo de entradas (default: 20)"
    )
    runs_list.add_argument(
        "--json", dest="as_json", action="store_true", help="Saida em JSON array"
    )
    runs_list.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Filtrar por diretorio de saida",
    )

    # runs show
    runs_show = runs_sub.add_parser("show", help="Exibe detalhes de um run")
    runs_show.add_argument("run_id", help="ID do run")
    runs_show.add_argument(
        "--json", dest="as_json", action="store_true", help="Saida em JSON bruto"
    )

    # runs rm
    runs_rm = runs_sub.add_parser("rm", help="Remove um run do indice")
    runs_rm.add_argument("run_id", help="ID do run")
    runs_rm.add_argument(
        "--purge",
        action="store_true",
        default=False,
        help="Tambem deleta o output_dir do filesystem (rm -rf)",
    )
    runs_rm.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Nao pede confirmacao interativa",
    )

    # ------------------------------------------------------------------
    # serve
    # ------------------------------------------------------------------
    serve_parser = subparsers.add_parser("serve", help="Inicia o servidor web TranscreveAI")
    serve_parser.add_argument(
        "--host", default="127.0.0.1", help="Host do servidor (default: 127.0.0.1)"
    )
    serve_parser.add_argument(
        "--port", type=int, default=8000, help="Porta do servidor (default: 8000)"
    )
    serve_parser.add_argument(
        "--out", default="outputs", help="Diretorio de saida dos jobs (default: outputs)"
    )
    serve_parser.add_argument(
        "--reload", action="store_true", default=False, help="Hot-reload (apenas desenvolvimento)"
    )

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    load_dotenv(Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        _cmd_analyze(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "runs":
        if args.runs_command == "list":
            _cmd_runs_list(args)
        elif args.runs_command == "show":
            _cmd_runs_show(args)
        elif args.runs_command == "rm":
            _cmd_runs_rm(args)


# ---------------------------------------------------------------------------
# Implementacoes dos comandos
# ---------------------------------------------------------------------------


def _cmd_serve(args: argparse.Namespace) -> None:
    try:
        import uvicorn

        from .web.app import create_app
    except ImportError as exc:
        print(f"Dependencias web ausentes: {exc}", file=sys.stderr)
        print("Instale com: pip install 'transcreve-ai[web]'", file=sys.stderr)
        sys.exit(1)

    app = create_app(
        out_dir=Path(args.out),
        index_db=getattr(args, "index_db", None),
    )
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)


def _cmd_analyze(args: argparse.Namespace) -> None:
    from .storage.registry import resolve_storage_name

    storage_name = resolve_storage_name(args.storage or None)

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
        force=args.force,
        storage_backend=storage_name,
        index_db=getattr(args, "index_db", None),
    )

    try:
        result = VideoKnowledgePipeline(options).run(args.source)
    except DuplicateRunError as exc:
        run_id = exc.existing.get("id", "?")
        output_dir = exc.existing.get("output_dir", "?")
        print(f"Pulando: run '{run_id}' ja existe em '{output_dir}'.")
        print("Use --force para reprocessar mesmo assim.")
        sys.exit(0)

    print("")
    print(f"OK: {result.workdir}")
    print("Markdown: %s" % (Path(result.workdir) / "knowledge.md"))
    print("JSON: %s" % (Path(result.workdir) / "analysis.json"))


def _cmd_runs_list(args: argparse.Namespace) -> None:
    db_path = resolve_index_path(getattr(args, "index_db", None))
    try:
        with RunIndex(db_path) as idx:
            runs = idx.list_runs(
                limit=args.limit,
                output_dir_filter=args.out,
            )
    except Exception as exc:
        print(f"Erro ao acessar indice: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(runs, ensure_ascii=False, indent=2))
        return

    if not runs:
        print("Nenhum run encontrado.")
        return

    # Tabela simples
    header = f"{'ID':<40} {'STATUS':<10} {'TITULO':<35} {'CRIADO EM':<25}"
    print(header)
    print("-" * len(header))
    for r in runs:
        run_id = r.get("id", "")[:40]
        status = r.get("status", "")[:10]
        title = (r.get("title") or r.get("source", ""))[:35]
        created = r.get("created_at", "")[:25]
        print(f"{run_id:<40} {status:<10} {title:<35} {created:<25}")


def _cmd_runs_show(args: argparse.Namespace) -> None:
    db_path = resolve_index_path(getattr(args, "index_db", None))
    try:
        with RunIndex(db_path) as idx:
            run = idx.get_run(args.run_id)
    except Exception as exc:
        print(f"Erro ao acessar indice: {exc}", file=sys.stderr)
        sys.exit(1)

    if run is None:
        print(f"Run '{args.run_id}' nao encontrado.", file=sys.stderr)
        sys.exit(1)

    if args.as_json:
        print(json.dumps(run, ensure_ascii=False, indent=2))
        return

    # Exibicao legivel
    for key, value in run.items():
        print(f"{key}: {value}")


def _cmd_runs_rm(args: argparse.Namespace) -> None:
    db_path = resolve_index_path(getattr(args, "index_db", None))

    # Carregar run antes de perguntar
    try:
        with RunIndex(db_path) as idx:
            run = idx.get_run(args.run_id)
    except Exception as exc:
        print(f"Erro ao acessar indice: {exc}", file=sys.stderr)
        sys.exit(1)

    if run is None:
        print(f"Run '{args.run_id}' nao encontrado.", file=sys.stderr)
        sys.exit(1)

    output_dir = run.get("output_dir", "")

    if not args.force:
        purge_msg = f" e deletar '{output_dir}'" if args.purge and output_dir else ""
        resposta = input(f"Remover '{args.run_id}'{purge_msg} do indice? [s/N] ").strip().lower()
        if resposta not in ("s", "sim", "y", "yes"):
            print("Cancelado.")
            return

    try:
        with RunIndex(db_path) as idx:
            removed = idx.delete_run(args.run_id)
    except Exception as exc:
        print(f"Erro ao remover do indice: {exc}", file=sys.stderr)
        sys.exit(1)

    if not removed:
        print(f"Run '{args.run_id}' nao encontrado.", file=sys.stderr)
        sys.exit(1)

    print(f"Run '{args.run_id}' removido do indice.")

    if args.purge and output_dir:
        dir_path = Path(output_dir)
        if dir_path.exists():
            shutil.rmtree(dir_path, ignore_errors=True)
            print(f"Diretorio '{output_dir}' deletado.")
        else:
            print(f"Aviso: diretorio '{output_dir}' nao encontrado no disco.")
