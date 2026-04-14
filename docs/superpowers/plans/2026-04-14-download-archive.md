# Download via gallery-dl archive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken get-url → per-URL download approach with a single gallery-dl call using `--download-archive` (SQLite). gallery-dl handles audio+video merging automatically. Progress tracked by counting new mp4 files in `saved_videos/raw/` (session delta) and querying the SQLite archive for the total.

**Architecture:** `download.sh` is a simple single-command wrapper around gallery-dl. `trigger_server.py` counts raw mp4 files before/during/after download for session progress, and queries SQLite for the archive total. No more url_cache.txt / status_cache.txt / retry-failed logic — gallery-dl's archive guarantees idempotency natively.

**New `_dl_stats` shape:**
```json
{
  "phase": "idle",
  "session_downloaded": 0,
  "total_archived": 0,
  "total_videos": 0,
  "analyzed": 0
}
```

**Phases:** `idle → downloading → analyzing → idle` (no more `fetching_urls`).

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `download.sh` | Rewrite | Single gallery-dl call with --download-archive |
| `trigger_server.py` | Modify | Replace file-based stats with mp4 count + SQLite, remove retry-failed |
| `viewer/api/main.py` | Modify | Remove /api/pipeline/retry-failed proxy |
| `viewer/frontend/src/components/PipelinePanel.jsx` | Modify | Show session_downloaded + total_archived, remove failed/retry UI |

---

## Task 1: Rewrite download.sh

**Files:**
- Modify: `download.sh`

- [ ] **Step 1: Replace the entire file**

```bash
#!/usr/bin/env bash

USERNAME="${INSTAGRAM_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  echo "Ошибка: переменная INSTAGRAM_USERNAME не задана"
  exit 1
fi

COOKIES_FILE="${1:-}"
if [ -z "$COOKIES_FILE" ]; then
  echo "Использование: ./download.sh <путь к cookies.txt>"
  exit 1
fi
if [ ! -f "$COOKIES_FILE" ]; then
  echo "Файл не найден: $COOKIES_FILE"
  exit 1
fi

DOWNLOAD_DIR="saved_videos/raw"
ARCHIVE_FILE="saved_videos/downloaded_archive.db"
LOG_FILE="download_log.txt"

mkdir -p "$DOWNLOAD_DIR" "saved_videos/meta"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $1 | $2" | tee -a "$LOG_FILE"
}

log "INFO" "Начинаю скачивание сохранённых reels для @$USERNAME..."

gallery-dl \
  --cookies "$COOKIES_FILE" \
  --download-archive "$ARCHIVE_FILE" \
  -d "$DOWNLOAD_DIR" \
  --filter "extension == 'mp4'" \
  --retries 3 \
  --sleep 4-8 \
  "https://www.instagram.com/$USERNAME/saved/" \
  2>&1 | tee -a "$LOG_FILE"

STATUS=$?
log "INFO" "gallery-dl завершён с кодом $STATUS"
exit $STATUS
```

- [ ] **Step 2: Verify syntax**

```bash
bash -n download.sh && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add download.sh
git commit -m "refactor: rewrite download.sh as single gallery-dl call with --download-archive"
```

---

## Task 2: Update trigger_server.py

**Files:**
- Modify: `trigger_server.py`

- [ ] **Step 1: Update imports — add back sqlite3, remove unused**

The current file has `from pathlib import Path` but no `sqlite3`. Add `import sqlite3` back to the imports block.

- [ ] **Step 2: Replace constants block**

Replace everything from `URL_CACHE_FILE` through `ANALYZE_CMD` with:

```python
ARCHIVE_DB = os.environ.get("ARCHIVE_DB", "saved_videos/downloaded_archive.db")
RAW_DIR = os.environ.get("RAW_DIR", "saved_videos/raw")
META_DIR = os.environ.get("META_DIR", "saved_videos/meta")
DOWNLOAD_CMD = ["/app/download.sh", COOKIES_FILE]
ANALYZE_CMD = ["python3", "/app/batch_analyze.py"]
```

- [ ] **Step 3: Replace `_dl_stats`**

```python
_dl_stats: dict = {
    "phase": "idle",
    "session_downloaded": 0,
    "total_archived": 0,
    "total_videos": 0,
    "analyzed": 0,
}
```

- [ ] **Step 4: Replace stat helper functions**

Remove `_read_download_stats()`, `_clear_failed_from_status_cache()`.
Keep `_read_analyze_stats()`.
Add `_count_raw_videos()` and `_count_archive()`.

After `_append_log`, the helpers should be:

```python
def _count_raw_videos() -> int:
    try:
        return len(list(Path(RAW_DIR).rglob("*.mp4")))
    except Exception:
        return 0


def _count_archive() -> int:
    try:
        with sqlite3.connect(ARCHIVE_DB) as con:
            return con.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
    except Exception:
        return 0


def _read_analyze_stats() -> dict:
    try:
        total_videos = len(list(Path(RAW_DIR).rglob("*.mp4")))
    except Exception:
        total_videos = 0
    try:
        analyzed = len(list(Path(META_DIR).glob("*.json")))
    except Exception:
        analyzed = 0
    return {"total_videos": total_videos, "analyzed": analyzed}
```

- [ ] **Step 5: Replace `_poll_stats()`**

```python
async def _poll_stats(baseline: int = 0) -> None:
    """Background task: update _dl_stats every 3s."""
    while True:
        await asyncio.sleep(3)
        if _dl_stats["phase"] == "downloading":
            current = _count_raw_videos()
            _dl_stats["session_downloaded"] = current - baseline
            _dl_stats["total_videos"] = current
            _dl_stats["total_archived"] = _count_archive()
        elif _dl_stats["phase"] == "analyzing":
            as_ = _read_analyze_stats()
            _dl_stats["total_videos"] = as_["total_videos"]
            _dl_stats["analyzed"] = as_["analyzed"]
```

- [ ] **Step 6: Replace `_run_pipeline()`**

```python
async def _run_pipeline() -> None:
    global _running, _last_run, _current_process
    _running = True
    _last_run = datetime.now(timezone.utc).isoformat()
    _log_buffer.clear()
    _append_log(f"=== started at {_last_run} ===")

    try:
        # ── Phase 1: Download ──────────────────────────────────────────────
        baseline = _count_raw_videos()
        _dl_stats.update({
            "phase": "downloading",
            "session_downloaded": 0,
            "total_archived": _count_archive(),
            "total_videos": baseline,
        })
        poll_task = asyncio.create_task(_poll_stats(baseline))

        try:
            process = await asyncio.create_subprocess_exec(
                *DOWNLOAD_CMD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _current_process = process
            async for raw in process.stdout:
                _append_log(raw.decode(errors="replace").rstrip())
            await process.wait()
        finally:
            _current_process = None
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

        final_videos = _count_raw_videos()
        session_downloaded = final_videos - baseline
        total_archived = _count_archive()
        _dl_stats.update({
            "session_downloaded": session_downloaded,
            "total_archived": total_archived,
            "total_videos": final_videos,
        })

        if process.returncode < 0:
            _append_log("=== pipeline остановлен пользователем ===")
            return

        _append_log(
            f"=== download: скачано {session_downloaded} новых, всего в архиве {total_archived} ==="
        )
        _append_log(f"=== download.sh finished (exit code {process.returncode}) ===")

        if process.returncode != 0:
            _append_log("=== download.sh failed — skipping analyze phase ===")
            return

        # ── Phase 2: Analyze ───────────────────────────────────────────────
        as_ = _read_analyze_stats()
        _dl_stats.update({"phase": "analyzing", **as_})
        poll_task2 = asyncio.create_task(_poll_stats())

        try:
            process2 = await asyncio.create_subprocess_exec(
                *ANALYZE_CMD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            _current_process = process2
            async for raw in process2.stdout:
                _append_log(raw.decode(errors="replace").rstrip())
            await process2.wait()
        finally:
            _current_process = None
            poll_task2.cancel()
            try:
                await poll_task2
            except asyncio.CancelledError:
                pass

        as_ = _read_analyze_stats()
        _dl_stats.update(as_)

        if process2.returncode < 0:
            _append_log("=== pipeline остановлен пользователем ===")
            return

        _append_log(
            f"=== analyze: проанализировано {as_['analyzed']} / {as_['total_videos']} видео ==="
        )
        _append_log(f"=== batch_analyze.py finished (exit code {process2.returncode}) ===")

    except Exception as e:
        _append_log(f"=== error: {e} ===")
    finally:
        _dl_stats["phase"] = "idle"
        _running = False
```

- [ ] **Step 7: Remove `POST /retry-failed` endpoint entirely**

- [ ] **Step 8: Update `@app.on_event("startup")`**

```python
@app.on_event("startup")
async def _startup():
    _dl_stats.update({
        "total_videos": _count_raw_videos(),
        "total_archived": _count_archive(),
    })
    _dl_stats.update(_read_analyze_stats())
```

- [ ] **Step 9: Verify syntax**

```bash
python3 -m py_compile trigger_server.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add trigger_server.py
git commit -m "refactor: use mp4 count + SQLite archive for stats, remove retry-failed"
```

---

## Task 3: Remove retry-failed proxy from viewer/api/main.py

**Files:**
- Modify: `viewer/api/main.py`

- [ ] **Step 1: Remove the `POST /api/pipeline/retry-failed` route**

Delete this block:

```python
@app.post("/api/pipeline/retry-failed")
async def pipeline_retry_failed():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{PIPELINE_URL}/retry-failed", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")
```

- [ ] **Step 2: Verify syntax**

```bash
python3 -m py_compile viewer/api/main.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add viewer/api/main.py
git commit -m "chore: remove /api/pipeline/retry-failed proxy (no longer needed)"
```

---

## Task 4: Update PipelinePanel.jsx

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.jsx`

The `_dl_stats` shape changed. New fields: `session_downloaded`, `total_archived`. Removed: `total_urls`, `downloaded`, `failed`. No more `fetching_urls` phase.

- [ ] **Step 1: Replace the entire file**

```jsx
import { useState, useEffect } from "react";
import LogsModal from "./LogsModal.jsx";
import "./PipelinePanel.css";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [dlStats, setDlStats] = useState(null);

  // Initial status fetch
  useEffect(() => {
    fetch("/api/pipeline/status")
      .then((r) => r.json())
      .then((d) => { setRunning(d.running); setLastRun(d.last_run); })
      .catch(() => {});
  }, []);

  // Poll status + dl-stats every 3s while running
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      fetch("/api/pipeline/status")
        .then((r) => r.json())
        .then((d) => {
          if (!d.running) {
            setRunning(false);
            setLastRun(d.last_run);
          }
        })
        .catch(() => {});
      fetch("/api/pipeline/dl-stats")
        .then((r) => r.json())
        .then(setDlStats)
        .catch(() => {});
    }, 3_000);
    return () => clearInterval(id);
  }, [running]);

  // Fetch dl-stats on mount and when run ends
  useEffect(() => {
    if (running) return;
    fetch("/api/pipeline/dl-stats")
      .then((r) => r.json())
      .then(setDlStats)
      .catch(() => {});
  }, [running]);

  async function handleRun() {
    try {
      const r = await fetch("/api/pipeline/run", { method: "POST" });
      const d = await r.json();
      if (d.status === "started" || d.status === "already_running") {
        setRunning(true);
        setLogsOpen(true);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function handleStop() {
    try {
      await fetch("/api/pipeline/stop", { method: "POST" });
    } catch (e) {
      console.error(e);
    }
  }

  const phase = dlStats?.phase;
  const phaseLabel =
    phase === "downloading" ? "Загрузка..." :
    phase === "analyzing"   ? "Анализ..."   : null;

  return (
    <div className="pipeline">
      <div className="pipeline-title">Pipeline</div>
      <div className="pipeline-status">
        <span className={`status-dot ${running ? "running" : "idle"}`} />
        <span className="status-label">{running ? "Running..." : "Idle"}</span>
      </div>
      {lastRun && !running && (
        <span className="last-run">last: {new Date(lastRun).toLocaleString()}</span>
      )}
      <div className="pipeline-actions">
        {running ? (
          <button className="btn-stop" onClick={handleStop}>■ Stop</button>
        ) : (
          <button className="btn-run" onClick={handleRun}>▶ Run pipeline</button>
        )}
        <button className="btn-logs-icon" onClick={() => setLogsOpen(true)} title="Show logs">
          📋
        </button>
      </div>

      {dlStats && (
        <div className="dl-stats">
          {/* Download section */}
          <div className="dl-stats-section">
            <div className="dl-stats-title">Загрузка</div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">Скачано</span>
              <span className={`dl-stats-value${phase === "downloading" ? " active" : ""}`}>
                {dlStats.session_downloaded} новых
              </span>
            </div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">В архиве</span>
              <span className="dl-stats-value">{dlStats.total_archived}</span>
            </div>
          </div>

          {/* Analyze section */}
          <div className="dl-stats-section">
            <div className="dl-stats-title">Анализ</div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">Проанализировано</span>
              <span className={`dl-stats-value${phase === "analyzing" ? " active" : ""}`}>
                {dlStats.analyzed} / {dlStats.total_videos}
              </span>
            </div>
          </div>

          {/* Phase label while running */}
          {running && phaseLabel && (
            <div className="dl-phase">{phaseLabel}</div>
          )}
        </div>
      )}

      {logsOpen && <LogsModal onClose={() => setLogsOpen(false)} />}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/PipelinePanel.jsx
git commit -m "feat: update PipelinePanel for archive-based stats (session_downloaded, total_archived)"
```

---

## Task 5: End-to-end verification

- [ ] **Step 1: Build**

```bash
docker compose build && echo "OK"
```

- [ ] **Step 2: Check /dl-stats on startup**

```bash
docker compose up -d
curl -s http://localhost:8000/api/pipeline/dl-stats | python3 -m json.tool
```

Expected:
```json
{
  "phase": "idle",
  "session_downloaded": 0,
  "total_archived": 87,
  "total_videos": 87,
  "analyzed": 80,
  "running": false
}
```

- [ ] **Step 3: Run pipeline and verify**

- sidebar shows "Скачано: 0 новых / В архиве: 87" during downloading
- counter increments as new files appear in raw/
- after completion: "Скачано: N новых / В архиве: 87+N"
- analyze section shows "Проанализировано: X / Y"
