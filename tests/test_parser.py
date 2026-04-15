from pathlib import Path

from reelect_pipeline.models import ReelManifest
from reelect_pipeline.parser import MediaParser


def test_parse_media_reuses_existing_transcript_and_frames(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")
    transcript_path = tmp_path / "clip.transcript.txt"
    transcript_path.write_text("hello", encoding="utf-8")
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
    manifest.parse.frame_count = 1

    parser = MediaParser()
    result = parser.parse_media(manifest)

    assert result.parse.transcript_path == str(transcript_path)
    assert result.parse.frames_dir == str(frames_dir)
    assert result.parse.frame_count == 1
