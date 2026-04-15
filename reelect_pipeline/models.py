from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseState:
    status: str = "pending"
    transcript_path: str | None = None
    frames_dir: str | None = None
    frame_interval_sec: float | None = None
    frame_count: int | None = None
    has_audio: bool | None = None
    parsed_at: str | None = None


@dataclass
class AnalysisState:
    status: str = "pending"
    meta_output_path: str | None = None
    analyzed_at: str | None = None
    model: str | None = None


@dataclass
class ReelManifest:
    id: str
    source_type: str
    source_url: str
    video_path: Path
    shortcode: str | None = None
    downloaded_at: str | None = None
    download: dict[str, object] = field(
        default_factory=lambda: {"status": "completed", "gallery_dl_metadata": {}}
    )
    parse: ParseState = field(default_factory=ParseState)
    analysis: AnalysisState = field(default_factory=AnalysisState)

