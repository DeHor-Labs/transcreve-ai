from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SourceMetadata:
    source: str
    title: str = ""
    webpage_url: str = ""
    extractor: str = ""
    uploader: str = ""
    channel: str = ""
    duration: float = 0.0
    upload_date: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class FrameObservation:
    timestamp: float
    image_path: str
    ocr_text: str = ""
    visual_note: str = ""


@dataclass
class KnowledgeSynthesis:
    summary: str = ""
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    tools_or_products: List[str] = field(default_factory=list)
    claims: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    run_id: str
    created_at: str
    source: str
    workdir: str
    media_path: str
    audio_path: str
    metadata: SourceMetadata
    transcript_text: str = ""
    transcript_segments: List[TranscriptSegment] = field(default_factory=list)
    frames: List[FrameObservation] = field(default_factory=list)
    synthesis: KnowledgeSynthesis = field(default_factory=KnowledgeSynthesis)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
