# Download Stats Tracking — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show real-time download statistics (phase, session downloads, archive total) in the PipelinePanel sidebar and append a summary line to the log buffer after each download phase.

**Architecture:** Split the single `pipeline.sh` subprocess in `trigger_server.py` into two sequential calls (download.sh then batch_analyze.py) so we can track phase transitions. Poll the gallery-dl SQLite archive every 3s during downloading to compute delta counts. Expose via `/dl-stats` endpoint → proxy in viewer API → polled by PipelinePanel frontend.

**Tech Stack:** Python asyncio + sqlite3 stdlib (backend), FastAPI, React hooks (frontend), CSS variables.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `trigger_server.py` | Modify | Add `_dl_stats`, `_count_archive()`, `_poll_archive()`, split subprocess, `/dl-stats` endpoint |
| `viewer/api/main.py` | Modify | Add proxy `GET /api/pipeline/dl-stats` |
| `viewer/frontend/src/components/PipelinePanel.jsx` | Modify | Add `dlStats` state, fetch/poll, stats JSX section |
| `viewer/frontend/src/components/PipelinePanel.css` | Modify | Add `.dl-stats` block styles |

---

## Task 1: Add download stats tracking to trigger_server.py

**Files:**
- Modify: `trigger_server.py`

- [ ] **Step 1: Add new globals and constants after existing ones**

In `trigger_server.py`, after line 23 (`LM_STATUS_FILE = "/tmp/lm_status.json"`), add:

```python
ARCHIVE_FILE = os.environ.get("ARCHIVE_FILE", "saved_videos/downloaded_archive.txt")
DOWNLOAD_CMD = ["/app/download.sh", COOKIES_FILE]
ANALYZE_CMD = ["python3", "/app/batch_analyze.py"]

_dl_stats: dict = {
    "session_downloaded": 0,
    "total_archived": 0,
    "phase": "idle",
}
```

- [ ] **Step 2: Add `_count_archive()` helper after `_append_log`**

After the `_append_log` function (around line 36), add:

```python
def _count_archive() -> int:
    try:
        import sqlite3 as _sqlite3
        con = _sqlite3.connect(ARCHIVE_FILE)
        count = con.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
        con.close()
        return count
    except Exception:
        return 0


async def _poll_archive(baseline: int) -> None:
    """Background task: update _dl_stats every 3s during download phase."""
    while True:
        await asyncio.sleep(3)
        current = _count_archive()
        _dl_stats["session_downloaded"] = current - baseline
        _dl_stats["total_archived"] = current
```

- [ ] **Step 3: Replace `_run_pipeline()` with the split two-phase version**

Replace the entire existing `_run_pipeline` function with:

```python
async def _run_pipeline() -> None:
    global _running, _last_run
    _running = True
    _last_run = datetime.now(timezone.utc).isoformat()
    _log_buffer.clear()
    _dl_stats.update({"session_downloaded": 0, "total_archived": _count_archive(), "phase": "idle"})
    _append_log(f"=== started at {_last_run} ===")

    try:
        # ── Phase 1: Download ──────────────────────────────────────────────
        _dl_stats["phase"] = "downloading"
        baseline = _count_archive()
        poll_task = asyncio.create_task(_poll_archive(baseline))

        try:
            process = await asyncio.create_subprocess_exec(
                *DOWNLOAD_CMD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in process.stdout:
                _append_log(raw.decode(errors="replace").rstrip())
            await process.wait()
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

        final_downloaded = _count_archive() - baseline
        total = _count_archive()
        _dl_stats["session_downloaded"] = final_downloaded
        _dl_stats["total_archived"] = total
        _append_log(
            f"=== download: скачано {final_downloaded} новых, итого в архиве {total} ==="
        )
        _append_log(f"=== download.sh finished (exit code {process.returncode}) ===")

        # ── Phase 2: Analyze ───────────────────────────────────────────────
        _dl_stats["phase"] = "analyzing"

        process2 = await asyncio.create_subprocess_exec(
            *ANALYZE_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in process2.stdout:
            _append_log(raw.decode(errors="replace").rstrip())
        await process2.wait()
        _append_log(f"=== batch_analyze.py finished (exit code {process2.returncode}) ===")

    except Exception as e:
        _append_log(f"=== error: {e} ===")
    finally:
        _dl_stats["phase"] = "idle"
        _running = False
```

- [ ] **Step 4: Add `GET /dl-stats` endpoint after `GET /logs`**

After the `/logs` route (around line 76), add:

```python
@app.get("/dl-stats")
async def dl_stats():
    return {**_dl_stats, "running": _running}
```

- [ ] **Step 5: Verify syntax**

```bash
python3 -m py_compile trigger_server.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add trigger_server.py
git commit -m "feat: add download stats tracking with SQLite archive polling"
```

---

## Task 2: Add proxy endpoint in viewer/api/main.py

**Files:**
- Modify: `viewer/api/main.py`

- [ ] **Step 1: Add `GET /api/pipeline/dl-stats` after `GET /api/lm/status`**

In `viewer/api/main.py`, after the `/api/lm/status` route (around line 83), add:

```python
@app.get("/api/pipeline/dl-stats")
async def pipeline_dl_stats():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PIPELINE_URL}/dl-stats", timeout=5)
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
git commit -m "feat: proxy /api/pipeline/dl-stats in viewer API"
```

---

## Task 3: Add dl-stats CSS to PipelinePanel.css

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.css`

- [ ] **Step 1: Append new CSS classes at the end of the file**

Append after the last existing rule:

```css
.dl-stats {
  border-top: 1px solid var(--border);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dl-stats-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 2px;
}

.dl-stats-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dl-stats-label {
  font-size: 11px;
  color: var(--text-muted);
}

.dl-stats-value {
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
}

.dl-stats-counter {
  font-size: 12px;
  font-weight: 600;
  color: #22c55e;
}

.dl-phase {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/PipelinePanel.css
git commit -m "feat: add download stats styles to PipelinePanel"
```

---

## Task 4: Add dl-stats UI to PipelinePanel.jsx

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.jsx`

- [ ] **Step 1: Add `dlStats` state and fetch logic**

The updated `PipelinePanel.jsx` (full file — replaces existing content):

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

  // Initial dl-stats fetch
  useEffect(() => {
    fetch("/api/pipeline/dl-stats")
      .then((r) => r.json())
      .then(setDlStats)
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

  // One final dl-stats fetch when run ends
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

  const phaseLabel =
    dlStats?.phase === "downloading" ? "Downloading..." :
    dlStats?.phase === "analyzing"   ? "Analyzing..."   : null;

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
        <button className="btn-run" onClick={handleRun} disabled={running}>
          {running ? "Running..." : "▶ Run pipeline"}
        </button>
        <button className="btn-logs-icon" onClick={() => setLogsOpen(true)} title="Show logs">
          📋
        </button>
      </div>

      {dlStats && (
        <div className="dl-stats">
          <div className="dl-stats-title">Download</div>
          <div className="dl-stats-row">
            <span className="dl-stats-label">Всего в архиве</span>
            <span className="dl-stats-value">{dlStats.total_archived} видео</span>
          </div>
          {!running && dlStats.session_downloaded > 0 && (
            <div className="dl-stats-row">
              <span className="dl-stats-label">Последний запуск</span>
              <span className="dl-stats-value">+{dlStats.session_downloaded} новых</span>
            </div>
          )}
          {running && dlStats.phase === "downloading" && (
            <div className="dl-stats-counter">
              {dlStats.session_downloaded} скачано
            </div>
          )}
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
git commit -m "feat: show download stats in PipelinePanel sidebar"
```

---

## Task 5: End-to-end verification

- [ ] **Step 1: Build and start Docker Compose**

```bash
cd /Users/owpk/gh/reelect
docker compose build
docker compose up
```

- [ ] **Step 2: Open browser at http://localhost:8000**

Verify:
- Sidebar shows "Download" section with "Всего в архиве: N видео"
- "Последний запуск" only appears after a run that downloads something

- [ ] **Step 3: Verify `/dl-stats` endpoint directly**

```bash
curl -s http://localhost:8000/api/pipeline/dl-stats | python3 -m json.tool
```

Expected:
```json
{
  "session_downloaded": 0,
  "total_archived": 151,
  "phase": "idle",
  "running": false
}
```

- [ ] **Step 4: Click "▶ Run pipeline"**

Verify during run:
- Phase label shows "Downloading..." while download.sh runs
- Counter `N скачано` updates every 3s if new reels found
- Phase changes to "Analyzing..." when batch_analyze.py starts
- After completion: "Последний запуск: +N новых" appears (or nothing if 0 new)

- [ ] **Step 5: Verify log line in modal**

Open 📋 modal after run. Verify log contains:
```
=== download: скачано N новых, итого в архиве K ===
```
