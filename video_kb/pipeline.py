from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .ai import (
    DEFAULT_TRANSCRIBE_MODEL,
    DEFAULT_VISION_MODEL,
    OpenAIAnalyzer,
    openai_available,
    select_visual_frames,
    transcript_near,
)
from .downloader import fetch_media
from .media import extract_audio, extract_frames, probe_duration
from .models import AnalysisResult, FrameObservation, KnowledgeSynthesis
from .ocr import choose_language, ocr_image
from .report import write_markdown
from .utils import ensure_dir, iso_now, now_id, slugify, write_json


@dataclass
class PipelineOptions:
    out_dir: Path
    frame_interval: float = 5.0
    max_frames: int = 80
    visual_limit: int = 30
    ai_mode: str = "auto"
    vision_model: str = ""
    transcribe_model: str = ""
    language: Optional[str] = None
    tesseract_lang: str = "por+eng"
    cookies_browser: Optional[str] = None
    cookies: Optional[str] = None
    video_format: str = "bv*+ba/b"


class VideoKnowledgePipeline:
    def __init__(self, options: PipelineOptions):
        self.options = options

    def run(self, source: str) -> AnalysisResult:
        run_id = "%s-%s" % (now_id(), slugify(source))
        run_dir = ensure_dir(self.options.out_dir / run_id).resolve()

        print("1/6 Baixando ou copiando video...")
        media_path, metadata = fetch_media(
            source,
            run_dir,
            cookies_browser=self.options.cookies_browser,
            cookies=self.options.cookies,
            video_format=self.options.video_format,
        )

        warnings = []
        try:
            metadata.duration = metadata.duration or probe_duration(media_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append("Nao foi possivel ler duracao com ffprobe: %s" % exc)

        print("2/6 Extraindo audio...")
        audio_path = run_dir / "audio.mp3"
        try:
            extract_audio(media_path, audio_path)
        except Exception as exc:  # noqa: BLE001
            warnings.append("Nao foi possivel extrair audio: %s" % exc)
            audio_path = None

        print("3/6 Extraindo frames...")
        frames_dir = ensure_dir(run_dir / "frames")
        frame_paths = extract_frames(
            media_path,
            frames_dir,
            duration=metadata.duration,
            interval=self.options.frame_interval,
            max_frames=self.options.max_frames,
        )

        print("4/6 Rodando OCR local...")
        ocr_lang, ocr_warning = choose_language(self.options.tesseract_lang)
        if ocr_warning:
            warnings.append(ocr_warning)
        frames = []
        for frame_path in frame_paths:
            timestamp = _timestamp_from_frame_name(frame_path.name)
            frames.append(
                FrameObservation(
                    timestamp=timestamp,
                    image_path=str(frame_path.relative_to(run_dir)),
                    ocr_text=ocr_image(frame_path, ocr_lang),
                )
            )

        result = AnalysisResult(
            run_id=run_id,
            created_at=iso_now(),
            source=source,
            workdir=str(run_dir),
            media_path=str(media_path.relative_to(run_dir)),
            audio_path=str(audio_path.relative_to(run_dir)) if audio_path else "",
            metadata=metadata,
            frames=frames,
            warnings=warnings,
        )

        use_ai = self._should_use_ai()
        if use_ai and audio_path:
            print("5/6 Transcrevendo e descrevendo visualmente com IA...")
            try:
                analyzer = OpenAIAnalyzer(
                    vision_model=self.options.vision_model or DEFAULT_VISION_MODEL,
                    transcribe_model=self.options.transcribe_model or DEFAULT_TRANSCRIBE_MODEL,
                    language=self.options.language,
                )
                text, segments = analyzer.transcribe_audio(audio_path, run_dir / "audio_chunks")
                result.transcript_text = text
                result.transcript_segments = segments

                visual_indexes = select_visual_frames(result.frames, self.options.visual_limit)
                for position, index in enumerate(visual_indexes, start=1):
                    frame = result.frames[index]
                    print(
                        "   IA visual %d/%d em %s..."
                        % (position, len(visual_indexes), frame.image_path)
                    )
                    frame_path = run_dir / frame.image_path
                    context = transcript_near(result.transcript_segments, frame.timestamp)
                    frame.visual_note = analyzer.describe_frame(
                        frame_path,
                        result.metadata,
                        frame.timestamp,
                        frame.ocr_text,
                        context,
                    )

                result.synthesis = analyzer.synthesize(
                    result.metadata,
                    result.transcript_text,
                    result.frames,
                )
            except Exception as exc:  # noqa: BLE001
                result.warnings.append("Camada de IA falhou; artefatos locais foram mantidos: %s" % exc)
                result.synthesis = _local_synthesis(result)
        else:
            if self.options.ai_mode != "off":
                result.warnings.append("OPENAI_API_KEY ausente; gerando dossie local sem transcricao/visao por IA")
            print("5/6 Gerando sintese local...")
            result.synthesis = _local_synthesis(result)

        print("6/6 Salvando analysis.json e knowledge.md...")
        write_json(run_dir / "analysis.json", result.to_dict())
        write_markdown(result, run_dir / "knowledge.md")
        return result

    def _should_use_ai(self) -> bool:
        if self.options.ai_mode == "off":
            return False
        if self.options.ai_mode == "full":
            return True
        return openai_available()


def _timestamp_from_frame_name(name: str) -> float:
    # frame_0001_00010s00.jpg -> 10.00
    marker = name.rsplit("_", 1)[-1].split(".", 1)[0]
    try:
        return float(marker.replace("s", "."))
    except ValueError:
        return 0.0


def _local_synthesis(result: AnalysisResult) -> KnowledgeSynthesis:
    ocr_hits = [frame.ocr_text for frame in result.frames if frame.ocr_text]
    summary_parts = []
    if result.metadata.title:
        summary_parts.append("Video: %s." % result.metadata.title)
    if result.metadata.description:
        summary_parts.append(result.metadata.description[:500])
    if ocr_hits:
        summary_parts.append("OCR encontrou textos em %d frames." % len(ocr_hits))
    if not summary_parts:
        summary_parts.append("Analise local concluida; ative OPENAI_API_KEY para transcricao e notas visuais completas.")

    return KnowledgeSynthesis(
        summary=" ".join(summary_parts),
        chapters=[],
        entities=[],
        tools_or_products=[],
        claims=[],
        action_items=[],
        questions=[],
        raw={"mode": "local"},
    )
