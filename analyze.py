#!/usr/bin/env python3
"""
analyze.py <video_file>

Extracts transcript and visual description from a video,
then uses Claude to produce a summary, category, and tags.
Writes result to saved_videos/meta/<stem>.json
"""

import sys
import json
import base64
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import anthropic

CLAUDE_MODEL = "claude-opus-4-6"
META_DIR = Path("saved_videos/meta")
FRAME_INTERVAL_SEC = 5
MAX_FRAMES = 10


# ── Audio ──────────────────────────────────────────────────────────────────────

def extract_transcript(video_path: Path) -> str:
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", audio_path],
        check=True, capture_output=True,
    )

    segments, _ = model.transcribe(audio_path, beam_size=5)
    transcript = " ".join(s.text.strip() for s in segments)
    Path(audio_path).unlink(missing_ok=True)
    return transcript


# ── Frames ─────────────────────────────────────────────────────────────────────

def extract_frames_b64(video_path: Path) -> list[str]:
    duration_result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(duration_result.stdout.strip())
    interval = max(FRAME_INTERVAL_SEC, duration / MAX_FRAMES)

    with tempfile.TemporaryDirectory() as tmp_dir:
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vf", f"fps=1/{interval:.1f}",
             "-vframes", str(MAX_FRAMES), f"{tmp_dir}/frame_%03d.jpg"],
            check=True, capture_output=True,
        )
        frames = sorted(Path(tmp_dir).glob("frame_*.jpg"))
        return [base64.standard_b64encode(f.read_bytes()).decode() for f in frames]


# ── Claude ─────────────────────────────────────────────────────────────────────

def describe_frames(client: anthropic.Anthropic, frames_b64: list[str]) -> str:
    content = []
    for frame in frames_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": frame},
        })
    content.append({
        "type": "text",
        "text": "These are frames from a video. Briefly describe what is visually happening — subject, setting, actions, mood. Be concise.",
    })

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": content}],
    )
    return response.content[0].text.strip()


def generate_metadata(client: anthropic.Anthropic, transcript: str, visual: str) -> dict:
    prompt = f"""You are analyzing a short video (Instagram Reel) saved by the user.

TRANSCRIPT:
{transcript or "(no speech detected)"}

VISUAL DESCRIPTION:
{visual}

Return a JSON object with exactly these fields:
- "summary": string, 2-3 sentence description of the video content
- "category": string, one topic label (e.g. "cooking", "travel", "fitness", "tech", "comedy", "art", "news", "music", "education", "lifestyle")
- "tags": array of 3-6 specific string tags

Respond with raw JSON only, no markdown."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(response.content[0].text.strip())


# ── Main ───────────────────────────────────────────────────────────────────────

def analyze(video_path: Path) -> Path:
    meta_path = META_DIR / (video_path.stem + ".json")
    if meta_path.exists():
        print(f"[skip] already analyzed: {meta_path}")
        return meta_path

    print(f"[analyze] {video_path.name}")
    client = anthropic.Anthropic()

    print("  → transcribing audio...")
    transcript = extract_transcript(video_path)

    print("  → extracting frames...")
    frames_b64 = extract_frames_b64(video_path)

    print("  → describing frames...")
    visual = describe_frames(client, frames_b64)

    print("  → generating metadata...")
    meta = generate_metadata(client, transcript, visual)

    result = {
        "id": video_path.stem,
        "filename": str(video_path),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "transcript": transcript,
        "visual_description": visual,
        **meta,
    }

    META_DIR.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"  ✓ saved → {meta_path}")
    return meta_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: analyze.py <video_file>")
        sys.exit(1)

    video = Path(sys.argv[1])
    if not video.exists():
        print(f"File not found: {video}")
        sys.exit(1)

    analyze(video)
