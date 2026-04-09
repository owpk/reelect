#!/usr/bin/env python3
"""
analyze.py <video_file>

Extracts transcript and visual description from a video,
then uses a local LM Studio model to produce summary, category, and tags.
Writes result to saved_videos/meta/<stem>.json
"""

import os
import sys
import json
import base64
import logging
import subprocess
import tempfile
import threading
from pathlib import Path
from datetime import datetime, timezone

from openai import OpenAI

logger = logging.getLogger(__name__)

META_DIR = Path("saved_videos/meta")
FRAME_INTERVAL_SEC = 5
MAX_FRAMES = 10

_default_lm_url = "http://localhost:1234/v1"
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", _default_lm_url)
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-vl-7b-instruct")
LM_STUDIO_API_KEY = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")
LM_STUDIO_CONCURRENCY = int(os.environ.get("LM_STUDIO_CONCURRENCY", "1"))
LM_STUDIO_NATIVE_VIDEO = os.environ.get("LM_STUDIO_NATIVE_VIDEO", "false").lower() == "true"
# Thinking budget for reasoning models (e.g. Qwen3). -1 = unlimited, 0 = disabled
LM_STUDIO_THINKING_BUDGET = int(os.environ.get("LM_STUDIO_THINKING_BUDGET", "-1"))
LM_STUDIO_MAX_TOKENS_VISUAL = int(os.environ.get("LM_STUDIO_MAX_TOKENS_VISUAL", "1024"))
LM_STUDIO_MAX_TOKENS_METADATA = int(os.environ.get("LM_STUDIO_MAX_TOKENS_METADATA", "4096"))

_lm_semaphore = threading.Semaphore(LM_STUDIO_CONCURRENCY)

# Shared across threads — both are thread-safe
_client: OpenAI | None = None
_whisper_model = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=LM_STUDIO_URL, api_key=LM_STUDIO_API_KEY)
    return _client


def get_whisper() :
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _whisper_model


# ── Audio ──────────────────────────────────────────────────────────────────────

def has_audio(video_path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_type",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True,
    )
    return result.stdout.strip() != ""


def extract_transcript(video_path: Path) -> str:
    cache_path = video_path.with_suffix(".transcript.txt")
    if cache_path.exists():
        logger.info(f"  [{video_path.name}] transcript from cache")
        return cache_path.read_text(encoding="utf-8")

    if not has_audio(video_path):
        logger.info(f"  [{video_path.name}] no audio stream, skipping transcription")
        cache_path.write_text("", encoding="utf-8")
        return ""

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-ar", "16000", "-ac", "1", audio_path],
        check=True, capture_output=True,
    )

    segments, _ = get_whisper().transcribe(audio_path, beam_size=5)
    transcript = " ".join(s.text.strip() for s in segments)
    Path(audio_path).unlink(missing_ok=True)

    cache_path.write_text(transcript, encoding="utf-8")
    return transcript


# ── Frames ─────────────────────────────────────────────────────────────────────

def extract_frames_b64(video_path: Path) -> list[str]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(result.stdout.strip())
    interval = max(FRAME_INTERVAL_SEC, duration / MAX_FRAMES)

    with tempfile.TemporaryDirectory() as tmp_dir:
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vf", f"fps=1/{interval:.1f}",
             "-vframes", str(MAX_FRAMES), f"{tmp_dir}/frame_%03d.jpg"],
            check=True, capture_output=True,
        )
        frames = sorted(Path(tmp_dir).glob("frame_*.jpg"))
        return [base64.standard_b64encode(f.read_bytes()).decode() for f in frames]


# ── LM Studio ──────────────────────────────────────────────────────────────────

def _lm_chat(messages: list, max_tokens: int, label: str = "") -> str:
    """Streams a chat completion. Prints reasoning to console, returns final content."""
    extra: dict = {}
    if LM_STUDIO_THINKING_BUDGET >= 0:
        extra["thinking"] = {"type": "enabled", "budget_tokens": LM_STUDIO_THINKING_BUDGET}

    with _lm_semaphore:
        stream = get_client().chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            stream=True,
            extra_body=extra or None,
        )

        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        in_reasoning = False

        for chunk in stream:
            delta = chunk.choices[0].delta
            rc = getattr(delta, "reasoning_content", None)
            if rc:
                if not in_reasoning:
                    print(f"\n[{label}] 💭 ", end="", flush=True)
                    in_reasoning = True
                print(rc, end="", flush=True)
                reasoning_parts.append(rc)
            if delta.content:
                if in_reasoning:
                    print()  # newline after reasoning block
                    in_reasoning = False
                content_parts.append(delta.content)

        if in_reasoning:
            print()  # trailing newline if stream ended mid-reasoning

    return "".join(content_parts)


def describe_frames(video_path: Path, frames_b64: list[str]) -> str:
    cache_path = video_path.with_suffix(".visual.txt")
    if cache_path.exists():
        logger.info(f"  [{video_path.name}] visual description from cache")
        return cache_path.read_text(encoding="utf-8")

    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}}
        for f in frames_b64
    ]
    content.append({
        "type": "text",
        "text": "These are frames from a video. Briefly describe what is visually happening — subject, setting, actions, mood. Be concise.",
    })

    visual = _lm_chat(
        messages=[{"role": "user", "content": content}],
        max_tokens=LM_STUDIO_MAX_TOKENS_VISUAL,
        label=video_path.name,
    ).strip()
    if visual:
        cache_path.write_text(visual, encoding="utf-8")
    return visual


def describe_video_native(video_path: Path) -> str:
    cache_path = video_path.with_suffix(".visual.txt")
    if cache_path.exists():
        logger.info(f"  [{video_path.name}] visual description from cache")
        return cache_path.read_text(encoding="utf-8")

    video_b64 = base64.standard_b64encode(video_path.read_bytes()).decode()
    content = [
        {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
        {"type": "text", "text": "Describe what is happening in this video — subject, setting, actions, mood. Be concise."},
    ]

    visual = _lm_chat(
        messages=[{"role": "user", "content": content}],
        max_tokens=LM_STUDIO_MAX_TOKENS_VISUAL,
        label=video_path.name,
    ).strip()
    if visual:
        cache_path.write_text(visual, encoding="utf-8")
    return visual


def generate_metadata(transcript: str, visual: str) -> dict:
    visual_block = f"VISUAL DESCRIPTION:\n{visual}" if visual else "VISUAL DESCRIPTION: (not available)"
    transcript_block = f"TRANSCRIPT:\n{transcript}" if transcript else "TRANSCRIPT: (no speech)"

    prompt = f"""You are analyzing a short Instagram Reel saved by a user who wants to extract useful information from it.

{transcript_block}

{visual_block}

Return a JSON object with exactly these fields:

"summary": 1-2 sentence description of what the video is about. Use the same language as the transcript if present, otherwise English.

"category": exactly one lowercase label from: cooking, travel, fitness, tech, comedy, art, news, music, education, lifestyle, fashion, sports, animals, motivation, other

"tags": array of 3-6 specific lowercase tags

"actionable": extract ONLY if the video contains concrete, reusable information the user can act on. Otherwise set to null.
  Supported types:
  - "recipe"         — cooking recipe. Extract: title, ingredients list, step-by-step instructions. Only include what is explicitly mentioned.
  - "guide"          — how-to, tutorial, life hack, tip. Extract: title + numbered steps or key points.
  - "recommendation" — film, series, book, podcast, music. Extract: title, type (film/series/book/etc), brief reason why it was recommended.
  - "resource"       — website, app, tool, product, place. Extract: name, what it is, why useful.

  Format for actionable:
  {{"type": "recipe", "title": "...", "content": "..."}}

  Set to null for: entertainment, comedy, vlogs, opinion pieces, motivational content without specific steps.

Example output for a recipe video:
{{"summary": "Автор показывает как приготовить сан-себастьян без миксера за 40 минут.", "category": "cooking", "tags": ["cheesecake", "рецепт", "выпечка", "десерт"], "actionable": {{"type": "recipe", "title": "Сан-Себастьян чизкейк", "content": "Ингредиенты: 600г сливочного сыра, 5 яиц, 200г сахара, 300мл сливок, 2 ст.л. муки\\n\\nШаги:\\n1. Смешать все ингредиенты венчиком\\n2. Вылить в форму, застеленную бумагой\\n3. Выпекать 30-40 мин при 220°C"}}}}

Return only the JSON object. No markdown, no explanation, no code fences."""

    text = _lm_chat(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=LM_STUDIO_MAX_TOKENS_METADATA,
        label="metadata",
    ).strip()

    # strip markdown code fences if model adds them
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    logger.info(f"metadata response: {text[:200]}")

    if not text:
        logger.warning("LM Studio returned empty response for metadata, using defaults")
        raise Exception("Llm did not respond with text, check your llm provider")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning(f"Could not parse JSON from model response: {text[:200]!r}")
        return {"summary": text[:300], "category": "uncategorized", "tags": []}


# ── Main ───────────────────────────────────────────────────────────────────────

def analyze(video_path: Path) -> Path:
    meta_path = META_DIR / (video_path.stem + ".json")
    if meta_path.exists():
        logger.info(f"[skip] {video_path.name}")
        return meta_path

    logger.info(f"[analyze] {video_path.name}")

    logger.info(f"  [{video_path.name}] transcribing...")
    transcript = extract_transcript(video_path)

    if LM_STUDIO_NATIVE_VIDEO:
        logger.info(f"  [{video_path.name}] describing video (native)...")
        visual = describe_video_native(video_path)
    else:
        logger.info(f"  [{video_path.name}] extracting frames...")
        frames_b64 = extract_frames_b64(video_path)
        logger.info(f"  [{video_path.name}] describing frames...")
        visual = describe_frames(video_path, frames_b64)

    logger.info(f"  [{video_path.name}] generating metadata...")
    meta = generate_metadata(transcript, visual)

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
    logger.info(f"  [{video_path.name}] saved → {meta_path}")
    return meta_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    if len(sys.argv) != 2:
        print("Usage: analyze.py <video_file>")
        sys.exit(1)

    video = Path(sys.argv[1])
    if not video.exists():
        print(f"File not found: {video}")
        sys.exit(1)

    analyze(video)
