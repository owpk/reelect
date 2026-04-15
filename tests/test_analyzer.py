import json
from pathlib import Path
from unittest.mock import patch

from reelect_pipeline.analyzer import ReelAnalyzer
from reelect_pipeline.models import ReelManifest
from reelect_pipeline.settings import PipelineSettings


def test_analyze_media_writes_viewer_meta_json(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    transcript_path = tmp_path / "clip.transcript.txt"
    transcript_path.write_text("test transcript", encoding="utf-8")
    frames_dir = tmp_path / "clip.frames"
    frames_dir.mkdir()
    (frames_dir / "frame_001.jpg").write_bytes(b"frame")

    manifest = ReelManifest(
        id="clip",
        source_type="single",
        source_url="https://example.test/reel/clip",
        video_path=video_path,
    )
    manifest.parse.status = "completed"
    manifest.parse.transcript_path = str(transcript_path)
    manifest.parse.frames_dir = str(frames_dir)

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

    analyzer = ReelAnalyzer(settings=settings, meta_root=tmp_path / "saved_videos" / "meta")

    with patch.object(
        analyzer,
        "_call_model",
        return_value={"summary": "s", "category": "tech", "tags": ["one"], "actionable": None},
    ):
        result = analyzer.analyze_media(manifest)

    meta_file = tmp_path / "saved_videos" / "meta" / "clip.json"
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert result.analysis.meta_output_path == str(meta_file)
    assert data["summary"] == "s"
    assert data["transcript"] == "test transcript"
