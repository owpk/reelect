from reelect_pipeline.models import ReelManifest
from reelect_pipeline.orchestrator import PipelineOrchestrator


def test_run_single_pipeline_calls_download_parse_and_analyze_in_order(tmp_path):
    manifest = ReelManifest(
        id="clip",
        source_type="single",
        source_url="https://example.test/reel/clip",
        video_path=tmp_path / "clip.mp4",
    )

    calls = []

    class Downloader:
        def download_single_reel(self, url):
            calls.append(("download", url))
            return manifest

    class Parser:
        def parse_media(self, item):
            calls.append(("parse", item.id))
            return item

    class Analyzer:
        def analyze_media(self, item):
            calls.append(("analyze", item.id))
            return item

    orchestrator = PipelineOrchestrator(
        downloader=Downloader(), parser=Parser(), analyzer=Analyzer()
    )
    orchestrator.run_single_pipeline("https://example.test/reel/clip")

    assert calls == [
        ("download", "https://example.test/reel/clip"),
        ("parse", "clip"),
        ("analyze", "clip"),
    ]
