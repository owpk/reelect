# Reel Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current shell-based reel processing flow with a reusable Python pipeline that supports both saved reels and a single direct reel URL.

**Architecture:** Build a small `reelect_pipeline` package with explicit services for download, parse, analyze, and orchestration. Keep `saved_videos/meta/*.json` as the stable output contract while moving internal state and caches into per-reel manifests stored next to the downloaded video.

**Tech Stack:** Python 3.12, gallery-dl, ffmpeg/ffprobe, faster-whisper, FastAPI, httpx, file-based `.env` config, JSON manifests

---

### Task 0: Add the test runtime needed for the refactor

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Write the failing command expectation**

Run: `python3 -m pytest --version`
Expected: FAIL if `pytest` is not installed in the current environment

- [ ] **Step 2: Add pytest to project dependencies**

```text
openai
faster-whisper
gallery-dl
yt-dlp
fastapi
httpx
uvicorn[standard]
pytest
```

- [ ] **Step 3: Rebuild or reinstall dependencies**

Run: `pip install -r requirements.txt`
Expected: `pytest` installed successfully

- [ ] **Step 4: Verify the test runtime is available**

Run: `python3 -m pytest --version`
Expected: PASS and prints installed `pytest` version

- [ ] **Step 5: Commit**

```bash
git add requirements.txt
git commit -m "test: add pytest runtime"
```

### Task 1: Introduce the Python pipeline package and shared models

**Files:**
- Create: `reelect_pipeline/__init__.py`
- Create: `reelect_pipeline/settings.py`
- Create: `reelect_pipeline/paths.py`
- Create: `reelect_pipeline/models.py`
- Create: `reelect_pipeline/manifest_store.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_manifest_store.py`

- [ ] **Step 1: Write the failing settings test**

```python
from pathlib import Path

from reelect_pipeline.settings import PipelineSettings, load_pipeline_settings


def test_load_pipeline_settings_reads_values_from_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "INSTAGRAM_USERNAME=test_user\n"
        "MAX_WORKERS=5\n"
        "LLM_BASE_URL=http://example.test/v1\n"
        "LLM_MODEL=test-model\n",
        encoding="utf-8",
    )

    settings = load_pipeline_settings(env_file)

    assert isinstance(settings, PipelineSettings)
    assert settings.instagram_username == "test_user"
    assert settings.max_workers == 5
    assert settings.llm_base_url == "http://example.test/v1"
    assert settings.llm_model == "test-model"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing symbol errors for `reelect_pipeline.settings`

- [ ] **Step 3: Write the failing manifest store test**

```python
from pathlib import Path

from reelect_pipeline.manifest_store import load_manifest, save_manifest
from reelect_pipeline.models import ReelManifest


def test_save_manifest_writes_next_to_video(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    manifest = ReelManifest(
        id="clip",
        source_type="single",
        source_url="https://example.test/reel/clip",
        video_path=video_path,
    )

    manifest_path = save_manifest(manifest)
    loaded = load_manifest(manifest_path)

    assert manifest_path == tmp_path / "clip.manifest.json"
    assert loaded.id == "clip"
    assert loaded.video_path == video_path
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_manifest_store.py -v`
Expected: FAIL with missing module or missing function errors

- [ ] **Step 5: Implement shared package skeleton**

```python
# reelect_pipeline/models.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParseState:
    status: str = "pending"
    transcript_path: str | None = None
    frames_dir: str | None = None
    frame_interval_sec: float | None = None
    frame_count: int | None = None
    has_audio: bool | None = None
    parsed_at: str | None = None


@dataclass
class AnalysisState:
    status: str = "pending"
    meta_output_path: str | None = None
    analyzed_at: str | None = None
    model: str | None = None


@dataclass
class ReelManifest:
    id: str
    source_type: str
    source_url: str
    video_path: Path
    shortcode: str | None = None
    downloaded_at: str | None = None
    download: dict = field(default_factory=lambda: {"status": "completed"})
    parse: ParseState = field(default_factory=ParseState)
    analysis: AnalysisState = field(default_factory=AnalysisState)
```

- [ ] **Step 6: Implement `.env`-file-backed settings loader**

```python
# reelect_pipeline/settings.py
from dataclasses import dataclass
from pathlib import Path

from config import load_env


@dataclass(frozen=True)
class PipelineSettings:
    instagram_username: str
    max_workers: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_concurrency: int
    llm_native_video: bool
    llm_thinking_budget: int
    llm_max_tokens_visual: int
    llm_max_tokens_metadata: int
    cron_schedule: str


def load_pipeline_settings(env_path: str | Path = ".env") -> PipelineSettings:
    data = load_env(str(env_path))
    return PipelineSettings(
        instagram_username=data.get("INSTAGRAM_USERNAME", ""),
        max_workers=int(data.get("MAX_WORKERS", "3")),
        llm_base_url=data.get("LLM_BASE_URL", ""),
        llm_model=data.get("LLM_MODEL", ""),
        llm_api_key=data.get("LLM_API_KEY", ""),
        llm_concurrency=int(data.get("LLM_CONCURRENCY", "1")),
        llm_native_video=data.get("LLM_NATIVE_VIDEO", "false").lower() == "true",
        llm_thinking_budget=int(data.get("LLM_THINKING_BUDGET", "512")),
        llm_max_tokens_visual=int(data.get("LLM_MAX_TOKENS_VISUAL", "4096")),
        llm_max_tokens_metadata=int(data.get("LLM_MAX_TOKENS_METADATA", "8192")),
        cron_schedule=data.get("CRON_SCHEDULE", "0 * * * *"),
    )
```

- [ ] **Step 7: Implement manifest serialization**

```python
# reelect_pipeline/manifest_store.py
import json
from dataclasses import asdict
from pathlib import Path

from reelect_pipeline.models import AnalysisState, ParseState, ReelManifest


def manifest_path_for(video_path: Path) -> Path:
    return video_path.with_suffix(".manifest.json")


def save_manifest(manifest: ReelManifest) -> Path:
    path = manifest_path_for(manifest.video_path)
    payload = asdict(manifest)
    payload["video_path"] = str(manifest.video_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path) -> ReelManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReelManifest(
        id=payload["id"],
        source_type=payload["source_type"],
        source_url=payload["source_url"],
        video_path=Path(payload["video_path"]),
        shortcode=payload.get("shortcode"),
        downloaded_at=payload.get("downloaded_at"),
        download=payload.get("download", {"status": "completed"}),
        parse=ParseState(**payload.get("parse", {})),
        analysis=AnalysisState(**payload.get("analysis", {})),
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest tests/test_settings.py tests/test_manifest_store.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add reelect_pipeline tests
git commit -m "refactor: add pipeline package skeleton"
```

### Task 2: Implement reusable downloader service for saved and single-url modes

**Files:**
- Create: `reelect_pipeline/downloader.py`
- Test: `tests/test_downloader.py`
- Modify: `reelect_pipeline/models.py`
- Modify: `reelect_pipeline/manifest_store.py`

- [ ] **Step 1: Write the failing downloader test for single URL mode**

```python
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

    with patch.object(downloader, "_run_gallery_dl") as run_gallery_dl:
        with patch.object(downloader, "_discover_downloaded_files", return_value=[tmp_path / "saved_videos" / "raw" / "url_submissions" / "clip.mp4"]):
            manifest = downloader.download_single_reel("https://www.instagram.com/reel/test/")

    assert manifest.source_type == "single"
    assert manifest.source_url == "https://www.instagram.com/reel/test/"
    assert manifest.video_path.name == "clip.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_downloader.py -v`
Expected: FAIL because `ReelDownloader` does not exist

- [ ] **Step 3: Implement downloader service**

```python
# reelect_pipeline/downloader.py
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from reelect_pipeline.manifest_store import save_manifest
from reelect_pipeline.models import ReelManifest


class ReelDownloader:
    def __init__(self, settings, raw_root: Path, archive_db: Path | None = None):
        self.settings = settings
        self.raw_root = raw_root
        self.archive_db = archive_db

    def download_saved_reels(self) -> list[ReelManifest]:
        target = self.raw_root / "instagram"
        self._run_gallery_dl(
            [
                "gallery-dl",
                "--download-archive",
                str(self.archive_db),
                "--filter",
                "extension == 'mp4'",
                "-d",
                str(target),
                f"https://www.instagram.com/{self.settings.instagram_username}/saved/",
            ]
        )
        return [self._build_manifest(path, source_type="saved", source_url=None) for path in self._discover_downloaded_files(target)]

    def download_single_reel(self, url: str) -> ReelManifest:
        target = self.raw_root / "url_submissions"
        self._run_gallery_dl(
            [
                "gallery-dl",
                "--filter",
                "extension == 'mp4'",
                "-d",
                str(target),
                url,
            ]
        )
        videos = self._discover_downloaded_files(target)
        latest = sorted(videos, key=lambda path: path.stat().st_mtime)[-1]
        return self._build_manifest(latest, source_type="single", source_url=url)

    def _build_manifest(self, video_path: Path, source_type: str, source_url: str | None) -> ReelManifest:
        manifest = ReelManifest(
            id=video_path.stem,
            source_type=source_type,
            source_url=source_url or "",
            video_path=video_path,
            downloaded_at=datetime.now(timezone.utc).isoformat(),
        )
        save_manifest(manifest)
        return manifest
```

- [ ] **Step 4: Add downloader metadata fields if needed**

```python
# reelect_pipeline/models.py
@dataclass
class ReelManifest:
    id: str
    source_type: str
    source_url: str
    video_path: Path
    shortcode: str | None = None
    downloaded_at: str | None = None
    download: dict = field(default_factory=lambda: {"status": "completed", "gallery_dl_metadata": {}})
    parse: ParseState = field(default_factory=ParseState)
    analysis: AnalysisState = field(default_factory=AnalysisState)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_downloader.py tests/test_manifest_store.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add reelect_pipeline tests
git commit -m "feat: add reusable reel downloader"
```

### Task 3: Implement ffmpeg and Whisper parse stage with persistent caches

**Files:**
- Create: `reelect_pipeline/parser.py`
- Test: `tests/test_parser.py`
- Modify: `reelect_pipeline/manifest_store.py`
- Modify: `reelect_pipeline/models.py`

- [ ] **Step 1: Write the failing parser cache reuse test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL because `MediaParser` does not exist

- [ ] **Step 3: Implement parse stage**

```python
# reelect_pipeline/parser.py
from pathlib import Path

from reelect_pipeline.manifest_store import save_manifest


class MediaParser:
    def __init__(self, frame_interval_sec: int = 1, max_frames: int = 350):
        self.frame_interval_sec = frame_interval_sec
        self.max_frames = max_frames

    def parse_media(self, manifest):
        transcript_path = manifest.video_path.with_suffix(".transcript.txt")
        frames_dir = manifest.video_path.with_suffix(".frames")

        if self._is_parse_cache_valid(manifest, transcript_path, frames_dir):
            return manifest

        transcript = self._extract_transcript(manifest.video_path, transcript_path)
        frame_interval_sec, frame_count = self._extract_frames(manifest.video_path, frames_dir)

        manifest.parse.status = "completed"
        manifest.parse.transcript_path = str(transcript_path)
        manifest.parse.frames_dir = str(frames_dir)
        manifest.parse.frame_interval_sec = frame_interval_sec
        manifest.parse.frame_count = frame_count
        manifest.parse.has_audio = bool(transcript)
        save_manifest(manifest)
        return manifest
```

- [ ] **Step 4: Implement ffprobe, ffmpeg, and Whisper helpers behind small methods**

```python
def _is_parse_cache_valid(self, manifest, transcript_path: Path, frames_dir: Path) -> bool:
    if manifest.parse.status != "completed":
        return False
    if not transcript_path.exists():
        return False
    if not frames_dir.exists():
        return False
    return any(frames_dir.glob("frame_*.jpg"))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add reelect_pipeline tests
git commit -m "feat: add parse stage with persistent caches"
```

### Task 4: Implement single-pass multimodal LLM analysis

**Files:**
- Create: `reelect_pipeline/analyzer.py`
- Test: `tests/test_analyzer.py`
- Modify: `reelect_pipeline/models.py`
- Modify: `reelect_pipeline/manifest_store.py`

- [ ] **Step 1: Write the failing analyzer output test**

```python
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

    with patch.object(analyzer, "_call_model", return_value={"summary": "s", "category": "tech", "tags": ["one"], "actionable": None}):
        result = analyzer.analyze_media(manifest)

    meta_file = tmp_path / "saved_videos" / "meta" / "clip.json"
    data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert result.analysis.meta_output_path == str(meta_file)
    assert data["summary"] == "s"
    assert data["transcript"] == "test transcript"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analyzer.py -v`
Expected: FAIL because `ReelAnalyzer` does not exist

- [ ] **Step 3: Implement single-pass analyzer**

```python
# reelect_pipeline/analyzer.py
import json
from datetime import datetime, timezone
from pathlib import Path

from reelect_pipeline.manifest_store import save_manifest


class ReelAnalyzer:
    def __init__(self, settings, meta_root: Path):
        self.settings = settings
        self.meta_root = meta_root

    def analyze_media(self, manifest):
        transcript = Path(manifest.parse.transcript_path).read_text(encoding="utf-8")
        frames = sorted(Path(manifest.parse.frames_dir).glob("frame_*.jpg"))
        payload = self._call_model(transcript=transcript, frames=frames)

        result = {
            "id": manifest.id,
            "filename": str(manifest.video_path),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "transcript": transcript,
            **payload,
        }

        self.meta_root.mkdir(parents=True, exist_ok=True)
        meta_path = self.meta_root / f"{manifest.id}.json"
        meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest.analysis.status = "completed"
        manifest.analysis.meta_output_path = str(meta_path)
        manifest.analysis.analyzed_at = result["analyzed_at"]
        manifest.analysis.model = self.settings.llm_model
        save_manifest(manifest)
        return manifest
```

- [ ] **Step 4: Preserve fallback parsing behavior from the current implementation**

```python
def _normalize_model_payload(self, payload):
    if isinstance(payload, dict):
        return payload
    return {"summary": str(payload)[:300], "category": "other", "tags": [], "actionable": None}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_analyzer.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add reelect_pipeline tests
git commit -m "feat: add single-pass multimodal analyzer"
```

### Task 5: Implement orchestrator and Python CLI entrypoints

**Files:**
- Create: `reelect_pipeline/orchestrator.py`
- Create: `reelect_pipeline/cli.py`
- Create: `reelect_pipeline/bootstrap.py`
- Test: `tests/test_orchestrator.py`
- Modify: `entrypoint.sh`
- Modify: `Dockerfile`

- [ ] **Step 1: Write the failing orchestrator sequencing test**

```python
from pathlib import Path

from reelect_pipeline.models import ReelManifest
from reelect_pipeline.orchestrator import PipelineOrchestrator


def test_run_single_pipeline_calls_download_parse_and_analyze_in_order(tmp_path: Path):
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

    orchestrator = PipelineOrchestrator(downloader=Downloader(), parser=Parser(), analyzer=Analyzer())
    orchestrator.run_single_pipeline("https://example.test/reel/clip")

    assert calls == [
        ("download", "https://example.test/reel/clip"),
        ("parse", "clip"),
        ("analyze", "clip"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL because `PipelineOrchestrator` does not exist

- [ ] **Step 3: Implement orchestrator and CLI**

```python
# reelect_pipeline/orchestrator.py
class PipelineOrchestrator:
    def __init__(self, downloader, parser, analyzer):
        self.downloader = downloader
        self.parser = parser
        self.analyzer = analyzer

    def run_single_pipeline(self, url: str):
        manifest = self.downloader.download_single_reel(url)
        manifest = self.parser.parse_media(manifest)
        return self.analyzer.analyze_media(manifest)

    def run_saved_pipeline(self):
        manifests = self.downloader.download_saved_reels()
        results = []
        for manifest in manifests:
            manifest = self.parser.parse_media(manifest)
            results.append(self.analyzer.analyze_media(manifest))
        return results
```

```python
# reelect_pipeline/cli.py
import argparse

from reelect_pipeline.bootstrap import build_orchestrator


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run-saved")
    run_single = subparsers.add_parser("run-single")
    run_single.add_argument("url")

    args = parser.parse_args()
    orchestrator = build_orchestrator()
    if args.command == "run-saved":
        orchestrator.run_saved_pipeline()
        return
    if args.command == "run-single":
        orchestrator.run_single_pipeline(args.url)
        return
    raise SystemExit(f"Unsupported command: {args.command}")
```

- [ ] **Step 4: Repoint cron to Python CLI**

```bash
# entrypoint.sh
CRON_SCHEDULE="$(python3 -c 'from config import load_env; print(load_env(".env").get("CRON_SCHEDULE", "0 * * * *"))')"
echo "$CRON_SCHEDULE cd /app && python3 -m reelect_pipeline.cli run-saved >> /proc/1/fd/1 2>> /proc/1/fd/2" | crontab -
```

- [ ] **Step 5: Update Dockerfile to copy the new package**

```dockerfile
COPY config.py entrypoint.sh trigger_server.py ./
COPY reelect_pipeline ./reelect_pipeline
RUN chmod +x entrypoint.sh
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add reelect_pipeline tests entrypoint.sh Dockerfile
git commit -m "refactor: add python cli orchestration"
```

### Task 6: Convert trigger server into an orchestrator-backed HTTP API

**Files:**
- Modify: `trigger_server.py`
- Test: `tests/test_trigger_server.py`

- [ ] **Step 1: Write the failing HTTP mode test**

```python
from fastapi.testclient import TestClient

from trigger_server import app


def test_run_single_endpoint_requires_url():
    client = TestClient(app)
    response = client.post("/run/single", json={})
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_trigger_server.py -v`
Expected: FAIL because `/run/single` does not exist

- [ ] **Step 3: Replace subprocess shell orchestration with direct service calls**

```python
# trigger_server.py
@app.post("/run/single")
async def run_single(payload: RunSingleRequest):
    if _running:
        return {"status": "already_running"}
    asyncio.create_task(_run_single_pipeline(payload.url))
    return {"status": "started", "mode": "single"}
```

- [ ] **Step 4: Keep stage stats and stop behavior at the orchestrator layer**

```python
_pipeline_state = {
    "running": False,
    "mode": None,
    "stage": "idle",
    "last_run": None,
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_trigger_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add trigger_server.py tests
git commit -m "refactor: move trigger server to orchestrator api"
```

### Task 7: Remove obsolete scripts and update documentation

**Files:**
- Delete: `download.sh`
- Delete: `pipeline.sh`
- Delete or replace: `analyze.py`
- Delete or replace: `batch_analyze.py`
- Modify: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Replace old scripts with compatibility wrappers only if migration still needs them**

```python
# analyze.py
from reelect_pipeline.cli import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Remove shell references from docs**

```markdown
Instagram Saved or Single Reel URL
      ↓
  reelect_pipeline.cli
      ↓
  download -> parse -> analyze
      ↓
  saved_videos/meta/<id>.json
```

- [ ] **Step 3: Ensure `.env.example` remains the authoritative configuration template**

```text
INSTAGRAM_USERNAME=your_instagram_handle
CRON_SCHEDULE="0 * * * *"
MAX_WORKERS=3
LLM_BASE_URL=http://host.docker.internal:1234/v1
LLM_MODEL=qwen2.5-vl-7b-instruct
LLM_CONCURRENCY=1
LLM_NATIVE_VIDEO=false
LLM_THINKING_BUDGET=512
LLM_MAX_TOKENS_VISUAL=4096
LLM_MAX_TOKENS_METADATA=8192
```

- [ ] **Step 4: Run focused regression checks**

Run: `pytest tests -v`
Expected: PASS

Run: `python3 -m reelect_pipeline.cli run-single https://www.instagram.com/reel/test/ --help`
Expected: CLI usage or argument parsing output without import errors

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: finalize python reel pipeline"
```
