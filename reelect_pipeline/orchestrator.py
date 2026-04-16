from __future__ import annotations

import shutil
from pathlib import Path

from reelect_pipeline.manifest_store import list_manifests, load_manifest, save_manifest


class PipelineOrchestrator:
    def __init__(
        self,
        downloader,
        parser,
        analyzer,
        raw_root: Path | None = None,
        meta_root: Path | None = None,
    ) -> None:
        self.downloader = downloader
        self.parser = parser
        self.analyzer = analyzer
        self.raw_root = raw_root
        self.meta_root = meta_root

    def run_single_pipeline(self, url: str):
        manifest = self.download_single_reel(url)
        manifest = self.parse_manifests([manifest])[0]
        return self.analyze_manifests([manifest])[0]

    def run_saved_pipeline(self) -> list:
        manifests = self.download_saved_reels()
        manifests = self.parse_manifests(manifests)
        return self.analyze_manifests(manifests)

    def delete_video(self, video_id: str) -> bool:
        if self.raw_root is None:
            return False
        manifests = list_manifests(self.raw_root, self.meta_root)
        manifest = next((m for m in manifests if m.id == video_id), None)
        if manifest is None:
            return False

        video_path = Path(manifest.video_path)
        transcript_path = video_path.with_suffix(".transcript.txt")
        frames_dir = video_path.with_suffix(".frames")
        manifest_path = self.raw_root / f"{video_id}.manifest.json"
        meta_path = self.meta_root / f"{video_id}.json" if self.meta_root else None

        if not video_path.exists():
            return False

        video_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        transcript_path.unlink(missing_ok=True)
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        if meta_path and meta_path.exists():
            meta_path.unlink()

        return True

    def regenerate_video(self, video_id: str):
        if self.raw_root is None:
            return None
        manifests = list_manifests(self.raw_root, self.meta_root)
        manifest = next((m for m in manifests if m.id == video_id), None)
        if manifest is None:
            return None

        video_path = Path(manifest.video_path)
        if not video_path.exists():
            return None

        transcript_path = video_path.with_suffix(".transcript.txt")
        frames_dir = video_path.with_suffix(".frames")

        transcript_path.unlink(missing_ok=True)
        if frames_dir.exists():
            shutil.rmtree(frames_dir)

        manifest.parse.status = "pending"
        manifest.parse.transcript_path = None
        manifest.parse.frames_dir = None
        manifest.parse.frame_count = None
        manifest.parse.has_audio = None
        manifest.parse.parsed_at = None
        manifest.analysis.status = "pending"
        manifest.analysis.meta_output_path = None
        manifest.analysis.analyzed_at = None
        manifest.analysis.model = None
        save_manifest(manifest)

        manifest = self.parser.parse_media(manifest)
        return self.analyzer.analyze_media(manifest)

    def download_saved_reels(self) -> list:
        return self.downloader.download_saved_reels()

    def download_single_reel(self, url: str):
        return self.downloader.download_single_reel(url)

    def parse_manifests(self, manifests: list) -> list:
        return [self.parser.parse_media(manifest) for manifest in manifests]

    def analyze_manifests(self, manifests: list) -> list:
        return [self.analyzer.analyze_media(manifest) for manifest in manifests]

    def run_parse_pending(self) -> list:
        return [self.parser.parse_media(manifest) for manifest in self._pending_parse_manifests()]

    def run_analysis_pending(self) -> list:
        return [
            self.analyzer.analyze_media(manifest)
            for manifest in self._pending_analysis_manifests()
        ]

    def _pending_parse_manifests(self) -> list:
        return [
            manifest
            for manifest in self._list_manifests()
            if manifest.parse.status != "completed"
        ]

    def _pending_analysis_manifests(self) -> list:
        return [
            manifest
            for manifest in self._list_manifests()
            if manifest.parse.status == "completed" and manifest.analysis.status != "completed"
        ]

    def _list_manifests(self) -> list:
        if self.raw_root is None:
            return []
        return list_manifests(self.raw_root, self.meta_root)
