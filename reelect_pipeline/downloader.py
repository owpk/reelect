from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from reelect_pipeline.manifest_store import save_manifest
from reelect_pipeline.models import ReelManifest
from reelect_pipeline.settings import PipelineSettings


class ReelDownloader:
    def __init__(
        self,
        settings: PipelineSettings,
        raw_root: Path,
        archive_db: Path | None = None,
        cookies_file: Path | None = None,
    ) -> None:
        self.settings = settings
        self.raw_root = raw_root
        self.archive_db = archive_db
        self.cookies_file = cookies_file

    def download_saved_reels(self) -> list[ReelManifest]:
        target = self.raw_root / "instagram"
        before = set(self._discover_downloaded_files(target))
        self._run_gallery_dl(
            self._build_command(
                target=target,
                url=f"https://www.instagram.com/{self.settings.instagram_username}/saved/",
                use_archive=True,
            )
        )
        after = self._discover_downloaded_files(target)
        return [
            self._build_manifest(path, source_type="saved", source_url="")
            for path in after
            if path not in before
        ]

    def download_single_reel(self, url: str) -> ReelManifest:
        target = self.raw_root / "url_submissions"
        self._run_gallery_dl(self._build_command(target=target, url=url, use_archive=False))
        videos = self._discover_downloaded_files(target)
        latest = sorted(videos, key=lambda path: path.stat().st_mtime if path.exists() else 0)[-1]
        return self._build_manifest(latest, source_type="single", source_url=url)

    def _build_command(self, target: Path, url: str, use_archive: bool) -> list[str]:
        target.mkdir(parents=True, exist_ok=True)
        command = [
            "gallery-dl",
            "--filter",
            "extension == 'mp4'",
            "--retries",
            "3",
            "--sleep",
            "4-8",
            "-d",
            str(target),
        ]
        if self.cookies_file and self.cookies_file.exists():
            command.extend(["--cookies", str(self.cookies_file)])
        if use_archive and self.archive_db is not None:
            self.archive_db.parent.mkdir(parents=True, exist_ok=True)
            command.extend(["--download-archive", str(self.archive_db)])
        command.append(url)
        return command

    def _run_gallery_dl(self, command: list[str]) -> None:
        subprocess.run(command, check=True)

    def _discover_downloaded_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(root.rglob("*.mp4"))

    def _build_manifest(self, video_path: Path, source_type: str, source_url: str) -> ReelManifest:
        video_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = ReelManifest(
            id=video_path.stem,
            source_type=source_type,
            source_url=source_url,
            video_path=video_path,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )
        save_manifest(manifest)
        return manifest
