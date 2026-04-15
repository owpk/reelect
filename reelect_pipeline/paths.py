from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelinePaths:
    project_root: Path
    raw_root: Path
    meta_root: Path
    archive_db: Path


def build_paths(project_root: str | Path = ".") -> PipelinePaths:
    root = Path(project_root)
    saved_root = root / "saved_videos"
    return PipelinePaths(
        project_root=root,
        raw_root=saved_root / "raw",
        meta_root=saved_root / "meta",
        archive_db=saved_root / "downloaded_archive.db",
    )
