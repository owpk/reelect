# Download Stats Tracking — Design Spec

**Date:** 2026-04-14  
**Status:** Approved

## Problem

When the pipeline runs in Docker, there is no visibility into how many reels have been downloaded in the current session, how many are in the archive, or what phase (downloading vs analyzing) the pipeline is in. The logs dialog shows raw text but no structured progress.

## Goal

Show download statistics in two places:
1. **Sidebar** (`PipelinePanel`) — persistent stats block with archive total, last-run delta, real-time phase label, and counter during active download
2. **Logs** — a summary line appended to the log buffer after `download.sh` completes

## Approach

Use the gallery-dl SQLite archive as the source of truth for counts. No stdout parsing (fragile, version-dependent). Instead, poll `SELECT COUNT(*) FROM archive` at the start and periodically during the run to compute the delta.

---

## Backend Changes

### trigger_server.py

**New globals:**
```python
_dl_stats: dict = {
    "session_downloaded": 0,  # new downloads in current run
    "total_archived": 0,      # absolute count from SQLite archive
    "phase": "idle",          # "idle" | "downloading" | "analyzing"
}
ARCHIVE_FILE = os.environ.get("ARCHIVE_FILE", "saved_videos/downloaded_archive.txt")
```

**Archive query helper:**
```python
def _count_archive() -> int:
    try:
        import sqlite3
        con = sqlite3.connect(ARCHIVE_FILE)
        count = con.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
        con.close()
        return count
    except Exception:
        return 0
```

**Pipeline flow changes in `_run_pipeline()`:**

1. Before `download.sh` subprocess:
   - Set `_dl_stats["phase"] = "downloading"`
   - Snapshot `baseline = _count_archive()`
   - Start background polling task (every 3s): update `_dl_stats["session_downloaded"] = _count_archive() - baseline` and `_dl_stats["total_archived"] = _count_archive()`

2. After `download.sh` completes:
   - Stop polling task
   - Final count: `_dl_stats["session_downloaded"] = _count_archive() - baseline`
   - `_dl_stats["total_archived"] = _count_archive()`
   - Append summary to log buffer: `=== download: скачано {N} новых, итого в архиве {K} ===`
   - Set `_dl_stats["phase"] = "analyzing"`

3. After `batch_analyze.py` completes:
   - Set `_dl_stats["phase"] = "idle"`

**Note:** `pipeline.sh` calls `download.sh` and `batch_analyze.py` sequentially in one subprocess. To distinguish phases, we need to split into two separate subprocess calls in `_run_pipeline()` instead of running `pipeline.sh` as a single process.

**New endpoint `GET /dl-stats`:**
```json
{
  "phase": "downloading",
  "session_downloaded": 5,
  "total_archived": 156,
  "running": true
}
```

### viewer/api/main.py

New proxy: `GET /api/pipeline/dl-stats → GET {PIPELINE_URL}/dl-stats` (with 503 on failure, matching existing pattern).

---

## Frontend Changes

### PipelinePanel.jsx

New state: `dlStats` (initially `null`).

Fetching logic:
- On mount: `GET /api/pipeline/dl-stats` once
- While `running === true`: poll every 3s
- When `running` transitions to `false`: one final fetch, then stop

New JSX section below `.pipeline-actions`:

```
── Download stats ──────────────────────
  Всего в архиве:   156 видео
  Последний запуск: +5 новых

  [████████░░] 5 скачано    ← only when phase === "downloading"
  Фаза: Downloading...       ← when phase !== "idle"
```

Phase labels:
- `"downloading"` → "Downloading..."
- `"analyzing"` → "Analyzing..."
- `"idle"` → (no label, show last-run stats only)

Progress display when `phase === "downloading"`:
- Counter: `{session_downloaded} скачано` (no percentage — total unknown)
- Animated dots or simple text counter (no % bar since denominator is unknown)

### PipelinePanel.css

New classes:
- `.dl-stats` — container with top border separator
- `.dl-stats-title` — section label, same style as `.pipeline-title`
- `.dl-stats-row` — each stat line
- `.dl-stats-value` — number, slightly highlighted
- `.dl-phase` — phase label, muted, small

---

## Data Flow

```
trigger_server.py (_dl_stats, _count_archive every 3s)
    │
    └── GET /dl-stats → viewer GET /api/pipeline/dl-stats → PipelinePanel (poll 3s while running)
```

Log summary line flows through existing `_log_buffer` → SSE → LogsModal.

---

## Implementation Notes

- `pipeline.sh` must be split into two subprocess calls in `_run_pipeline()` so we can change phase between them. `pipeline.sh` itself is left unchanged.
- The background polling task uses `asyncio.create_task` with a cancel mechanism.
- `sqlite3` is a Python stdlib module — no new dependency.
- `ARCHIVE_FILE` path must be consistent with what `download.sh` uses: `saved_videos/downloaded_archive.txt` (relative to `/app` in Docker).

---

## Out of Scope

- "Remaining to download" percentage (unknown total without `--simulate`)
- Per-account breakdown
- Historical run stats (only last run is tracked)
