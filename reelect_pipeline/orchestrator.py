from __future__ import annotations

from pathlib import Path

from reelect_pipeline.manifest_store import list_manifests


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
