from pathlib import Path
from unittest.mock import patch

from reelect_pipeline.downloader import ReelDownloader
from reelect_pipeline.settings import PipelineSettings


def test_download_single_reel_returns_manifest_from_downloaded_file(tmp_path: Path):
    settings = PipelineSettings(
        instagram_username="tester",
        max_workers=3,
        llm_base_url="http://example.test/v1",
        llm_model="test-model",
        llm_api_key="",
        llm_concurrency=1,
        llm_native_video=False,
        llm_thinking_budget=512,
        llm_max_tokens_visual=4096,
        llm_max_tokens_metadata=8192,
        cron_schedule="0 * * * *",
    )

    downloader = ReelDownloader(settings=settings, raw_root=tmp_path / "saved_videos" / "raw")

    with patch.object(downloader, "_run_gallery_dl"):
        with patch.object(
            downloader,
            "_discover_downloaded_files",
            return_value=[tmp_path / "saved_videos" / "raw" / "url_submissions" / "clip.mp4"],
        ):
            manifest = downloader.download_single_reel("https://www.instagram.com/reel/test/")

    assert manifest.source_type == "single"
    assert manifest.source_url == "https://www.instagram.com/reel/test/"
    assert manifest.video_path.name == "clip.mp4"
