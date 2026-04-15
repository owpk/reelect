from __future__ import annotations

from pathlib import Path

from reelect_pipeline.analyzer import ReelAnalyzer
from reelect_pipeline.downloader import ReelDownloader
from reelect_pipeline.orchestrator import PipelineOrchestrator
from reelect_pipeline.parser import MediaParser
from reelect_pipeline.paths import build_paths
from reelect_pipeline.settings import load_pipeline_settings


def build_orchestrator(project_root: str | Path = ".") -> PipelineOrchestrator:
    paths = build_paths(project_root)
    settings = load_pipeline_settings(Path(project_root) / ".env")
    return PipelineOrchestrator(
        downloader=ReelDownloader(
            settings=settings,
            raw_root=paths.raw_root,
            archive_db=paths.archive_db,
            cookies_file=_resolve_cookies_file(Path(project_root)),
        ),
        parser=MediaParser(),
        analyzer=ReelAnalyzer(settings=settings, meta_root=paths.meta_root),
        raw_root=paths.raw_root,
        meta_root=paths.meta_root,
    )


def _resolve_cookies_file(project_root: Path) -> Path | None:
    cookie_candidates = [
        Path("/cookies/cookies.txt"),
        project_root / "cookies.txt",
    ]
    for candidate in cookie_candidates:
        if candidate.exists():
            return candidate
    return None
