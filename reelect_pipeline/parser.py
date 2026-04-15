from __future__ import annotations

import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from reelect_pipeline.manifest_store import save_manifest
from reelect_pipeline.models import ReelManifest

_whisper_model = None


def get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


class MediaParser:
    def __init__(self, frame_interval_sec: int = 1, max_frames: int = 350) -> None:
        self.frame_interval_sec = frame_interval_sec
        self.max_frames = max_frames

    def parse_media(self, manifest: ReelManifest) -> ReelManifest:
        transcript_path = manifest.video_path.with_suffix(".transcript.txt")
        frames_dir = manifest.video_path.with_suffix(".frames")

        if self._is_parse_cache_valid(manifest, transcript_path, frames_dir):
            manifest.parse.transcript_path = str(transcript_path)
            manifest.parse.frames_dir = str(frames_dir)
            manifest.parse.frame_count = len(sorted(frames_dir.glob("frame_*.jpg")))
            return manifest

        transcript = self._extract_transcript(manifest.video_path, transcript_path)
        frame_interval_sec, frame_count = self._extract_frames(manifest.video_path, frames_dir)

        manifest.parse.status = "completed"
        manifest.parse.parsed_at = datetime.now(timezone.utc).isoformat()
        manifest.parse.transcript_path = str(transcript_path)
        manifest.parse.frames_dir = str(frames_dir)
        manifest.parse.frame_interval_sec = frame_interval_sec
        manifest.parse.frame_count = frame_count
        manifest.parse.has_audio = self._has_audio(manifest.video_path)
        if not manifest.parse.has_audio and transcript_path.exists():
            transcript_path.write_text("", encoding="utf-8")
        save_manifest(manifest)
        return manifest

    def _is_parse_cache_valid(
        self, manifest: ReelManifest, transcript_path: Path, frames_dir: Path
    ) -> bool:
        if manifest.parse.status != "completed":
            return False
        if not transcript_path.exists():
            return False
        if not frames_dir.exists():
            return False
        return any(frames_dir.glob("frame_*.jpg"))

    def _has_audio(self, video_path: Path) -> bool:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(result.stdout.strip())

    def _extract_transcript(self, video_path: Path, transcript_path: Path) -> str:
        if transcript_path.exists():
            return transcript_path.read_text(encoding="utf-8")

        if not self._has_audio(video_path):
            transcript_path.write_text("", encoding="utf-8")
            return ""

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio_path = Path(tmp.name)

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(video_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(audio_path),
                ],
                check=True,
                capture_output=True,
            )
            segments, _ = get_whisper().transcribe(str(audio_path), beam_size=5)
            transcript = " ".join(segment.text.strip() for segment in segments)
            transcript_path.write_text(transcript, encoding="utf-8")
            return transcript
        finally:
            audio_path.unlink(missing_ok=True)

    def _extract_frames(self, video_path: Path, frames_dir: Path) -> tuple[float, int]:
        duration = self._get_duration(video_path)
        interval = max(self.frame_interval_sec, duration / self.max_frames if duration else 0)

        frames_dir.mkdir(parents=True, exist_ok=True)
        for frame_path in frames_dir.glob("frame_*.jpg"):
            frame_path.unlink()

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vf",
                f"fps=1/{interval:.3f}",
                "-vframes",
                str(self.max_frames),
                str(frames_dir / "frame_%03d.jpg"),
            ],
            check=True,
            capture_output=True,
        )

        frame_count = len(sorted(frames_dir.glob("frame_*.jpg")))
        return interval, frame_count

    def _get_duration(self, video_path: Path) -> float:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        raw_duration = result.stdout.strip()
        return float(raw_duration) if raw_duration else 0.0
