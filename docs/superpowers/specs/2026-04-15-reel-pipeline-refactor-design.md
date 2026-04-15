# Reel Pipeline Refactor Design

**Date:** 2026-04-15

## Goal

Replace the current shell-driven backend with a Python-first pipeline that supports two entry modes:

1. Download and process all saved Instagram reels.
2. Download and process one direct reel URL.

The new backend must preserve the existing high-level product flow:

`download -> ffmpeg parse -> llm analyze`

Frontend compatibility is not a design constraint for this refactor. The backend becomes the source of truth, and the frontend will be adapted later.

## Non-Negotiable Constraints

- Runtime settings must be read from `.env` through the existing file-based config flow, not from process environment variables.
- Existing setting names from `.env.example` must remain supported.
- Final user-facing analysis output must still be written as flat JSON files under `saved_videos/meta/`.
- Downloaded media and parse caches must live next to the downloaded video inside `saved_videos/raw/...`.
- The new architecture should favor reusable Python modules over shell scripts.

## Current Problems

- `pipeline.sh` only chains two coarse steps and hides business logic behind shell calls.
- `download.sh` only supports the "saved reels" scenario.
- `batch_analyze.py` discovers work using a single heuristic: "mp4 without meta json".
- `analyze.py` mixes ffmpeg, Whisper, LLM communication, cache handling, prompt construction, and final persistence in one file.
- `trigger_server.py` orchestrates subprocesses instead of domain operations.
- Cron currently depends on exported environment variables, which conflicts with the `.env`-as-source-of-truth requirement.

## Target Architecture

Use a small Python package with focused modules and thin entrypoints.

### Proposed package layout

```text
reelect_pipeline/
  __init__.py
  settings.py
  paths.py
  models.py
  manifest_store.py
  downloader.py
  parser.py
  analyzer.py
  orchestrator.py
  logging_utils.py
  cli.py
```

Existing top-level scripts become wrappers or are removed after the migration:

- `analyze.py` -> replaced by package modules
- `batch_analyze.py` -> replaced by package CLI entrypoint
- `download.sh` -> removed
- `pipeline.sh` -> removed
- `trigger_server.py` -> kept as HTTP adapter over `orchestrator.py`

## Domain Model

### Reel manifest

Each downloaded reel gets one manifest JSON stored next to the video:

`saved_videos/raw/.../<video_stem>.manifest.json`

This is the internal pipeline state and cache index.

Example shape:

```json
{
  "id": "3781563114878507502",
  "source_type": "saved",
  "source_url": "https://www.instagram.com/reel/...",
  "shortcode": "ABC123",
  "downloaded_at": "2026-04-15T10:00:00+00:00",
  "video_path": "saved_videos/raw/instagram/cinema_hall/3781563114878507502.mp4",
  "download": {
    "status": "completed",
    "gallery_dl_metadata": {}
  },
  "parse": {
    "status": "completed",
    "parsed_at": "2026-04-15T10:01:00+00:00",
    "transcript_path": "saved_videos/raw/instagram/cinema_hall/3781563114878507502.transcript.txt",
    "frames_dir": "saved_videos/raw/instagram/cinema_hall/3781563114878507502.frames",
    "frame_interval_sec": 1.7,
    "frame_count": 22,
    "has_audio": true
  },
  "analysis": {
    "status": "completed",
    "analyzed_at": "2026-04-15T10:02:00+00:00",
    "meta_output_path": "saved_videos/meta/3781563114878507502.json",
    "model": "qwen2.5-vl-7b-instruct"
  }
}
```

### Public analysis result

Viewer-facing JSON remains in:

`saved_videos/meta/<video_id>.json`

This file stays simple and stable:

```json
{
  "id": "...",
  "filename": "saved_videos/raw/instagram/account/file.mp4",
  "analyzed_at": "...",
  "transcript": "...",
  "summary": "...",
  "category": "...",
  "tags": ["..."],
  "actionable": null
}
```

Optional future fields can be added later, but the internal manifest must not leak directly into viewer output.

## Stage Responsibilities

### 1. Download stage

Responsibilities:

- download saved reels from the configured Instagram saved page
- download a single reel from a direct URL
- store the mp4 in `saved_videos/raw/...`
- generate or update the manifest for each downloaded video

Public interface:

- `download_saved_reels() -> list[ReelManifest]`
- `download_single_reel(url: str) -> ReelManifest`

Implementation notes:

- Use `gallery-dl` from Python via `subprocess.run(...)`.
- Use `--write-metadata` or `--dump-json`/`--print` output only as an implementation detail.
- `INSTAGRAM_USERNAME` and all other runtime settings come from `.env`, loaded through the shared config loader.
- Single-url downloads should go to a deterministic folder under `saved_videos/raw/url_submissions/...` unless gallery-dl returns a better target path.

### 2. Parse stage

Responsibilities:

- inspect the downloaded video
- detect audio presence with `ffprobe`
- extract transcript with ffmpeg + faster-whisper
- extract frame images with ffmpeg into a persistent cache directory
- write parse results back into the manifest

Public interface:

- `parse_media(manifest: ReelManifest) -> ReelManifest`
- `collect_pending_parse_manifests() -> list[ReelManifest]`

Artifacts stored next to the video:

- `<stem>.transcript.txt`
- `<stem>.frames/frame_001.jpg`
- `<stem>.frames/frame_002.jpg`
- `<stem>.manifest.json`

Cache rules:

- If transcript already exists and manifest says parse completed, reuse it.
- If frames directory exists and manifest matches current frame parameters, reuse it.
- If the video file changed or parameters changed, regenerate parse artifacts and refresh manifest fields.

### 3. LLM analyze stage

Responsibilities:

- load transcript text and frame image paths from parse artifacts
- build one multimodal prompt using transcript + frames
- call the configured OpenAI-compatible LLM
- parse JSON response
- write final viewer result into `saved_videos/meta/<id>.json`
- update manifest analysis state

Public interface:

- `analyze_media(manifest: ReelManifest) -> ReelManifest`
- `collect_pending_analysis_manifests() -> list[ReelManifest]`

Important change:

- The new design treats visual inputs as parse artifacts, not as a separate "visual description" LLM pass.
- Existing `LLM_MAX_TOKENS_VISUAL` remains supported in settings for backward compatibility during migration, but the main analysis path should be a single final multimodal call driven by transcript + frames.

### 4. Orchestration stage

Responsibilities:

- run end-to-end flows
- expose stage-level progress
- keep the business flow independent from CLI and HTTP

Public interface:

- `run_saved_pipeline()`
- `run_single_pipeline(url: str)`
- `run_parse_pending()`
- `run_analysis_pending()`

Behavior:

- `run_saved_pipeline()` executes download saved -> parse pending from those downloads -> analyze pending from those downloads.
- `run_single_pipeline(url)` executes download single -> parse downloaded reel -> analyze downloaded reel.
- Stage commands can also run independently for recovery and debugging.

## Configuration Strategy

Runtime config must be loaded from `.env` by Python code, using the existing file-based config module as the source of truth.

### Supported existing keys

- `INSTAGRAM_USERNAME`
- `CRON_SCHEDULE`
- `MAX_WORKERS`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_CONCURRENCY`
- `LLM_NATIVE_VIDEO`
- `LLM_THINKING_BUDGET`
- `LLM_MAX_TOKENS_VISUAL`
- `LLM_MAX_TOKENS_METADATA`

### Additional settings

Avoid introducing new settings unless implementation proves they are necessary. If a new setting is required, it must also be added to `.env.example` and to the UI config API.

## HTTP API Direction

`trigger_server.py` becomes a thin transport layer over the orchestrator.

Target endpoints:

- `POST /run/saved`
- `POST /run/single`
- `POST /stop`
- `GET /status`
- `GET /logs`
- `GET /dl-stats`

`POST /run/single` request body:

```json
{
  "url": "https://www.instagram.com/reel/..."
}
```

The server should track:

- current run mode: `saved` or `single`
- current stage: `idle`, `downloading`, `parsing`, `analyzing`
- stage counters
- stop requests

## Cron Direction

Cron should no longer invoke shell scripts that depend on exported environment variables.

Instead:

- `entrypoint.sh` reads `CRON_SCHEDULE` from `.env` using Python or a small helper command
- cron runs a Python CLI command, for example:
  `python3 -m reelect_pipeline.cli run-saved`

This keeps `.env` as the only runtime configuration source.

## Migration Strategy

1. Introduce Python package and keep current scripts temporarily.
2. Move logic behind new service interfaces.
3. Repoint `trigger_server.py` and cron to Python entrypoints.
4. Remove obsolete shell orchestration.
5. Update README and frontend later.

## Testing Strategy

Focus automated tests on deterministic logic:

- settings loading from `.env`
- manifest persistence and state transitions
- pending item selection
- downloader result parsing
- parser cache reuse decisions
- analysis result parsing and fallback behavior
- orchestrator stage sequencing

External commands and LLM calls should be mocked in unit tests.

## Out of Scope

- Frontend UI changes
- Reworking viewer data model beyond keeping the flat meta JSON output
- Replacing gallery-dl, ffmpeg, or faster-whisper with other tools
