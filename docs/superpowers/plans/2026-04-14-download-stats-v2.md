# Download Stats v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace broken SQLite-based stats with file-based counters that show meaningful X/Y progress in the sidebar: "Скачано: 12 / 87" during download phase, "Проанализировано: 8 / 12" during analyze phase, plus a "Retry N failed" button for failed URLs.

**Architecture:** `download.sh` writes per-URL status to `status_cache.txt` (DONE/FAILED) and total URLs to `url_cache.txt`. `trigger_server.py` reads these files every 3s via a background poll task, exposes `/dl-stats`, and provides `POST /retry-failed` that strips FAILED lines and re-runs the pipeline. Frontend polls and renders X/Y counters with a retry button when `failed > 0`.

**Tech Stack:** Python asyncio + pathlib stdlib (backend), FastAPI, React hooks (frontend), CSS custom properties.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `download.sh` | Modify | Fix `$temp_archive` bug, remove ARCHIVE_FILE grep, keep status_cache tracking |
| `trigger_server.py` | Modify | Replace SQLite helpers with file readers, new `_dl_stats` shape, `fetching_urls` phase, `POST /retry-failed` |
| `viewer/api/main.py` | Modify | Add proxy `POST /api/pipeline/retry-failed` |
| `viewer/frontend/src/components/PipelinePanel.css` | Modify | Add `.dl-stats-active`, `.dl-failed-label`, `.dl-failed-value`, `.btn-retry` |
| `viewer/frontend/src/components/PipelinePanel.jsx` | Modify | X/Y counters, failed badge, retry button, `fetching_urls` phase label |

---

## Task 1: Fix download.sh

**Files:**
- Modify: `download.sh`

Current bugs:
1. `download_with_retry()` calls `gallery-dl --download-archive "$temp_archive"` — `$temp_archive` is never defined, so gallery-dl receives an empty string and the flag is silently broken.
2. Lines 96-101 do `cat "$temp_archive" >> "$ARCHIVE_FILE"` on an undefined file — dead code.
3. Lines 176-181 do `grep -qF "$url" "$ARCHIVE_FILE"` to check a plain-text/SQLite file that is not maintained by this script — unreliable and redundant since `status_cache.txt` already tracks this.

- [ ] **Step 1: Rewrite `download_with_retry()` — remove `$temp_archive` entirely**

Replace the entire `download_with_retry` function (lines 70-120) with:

```bash
# Функция загрузки одного URL с повторными попытками
download_with_retry() {
  local url="$1"
  local attempt=1

  while [ $attempt -le $MAX_RETRIES ]; do
    log "INFO" "Попытка $attempt/$MAX_RETRIES: $url"

    gallery-dl \
      --cookies "$COOKIES_FILE" \
      -d "$DOWNLOAD_DIR" \
      --filter "extension == 'mp4'" \
      --retries 1 \
      --sleep 4-8 \
      "$url" \
      2>&1 | tee -a "$LOG_FILE"

    local status=${PIPESTATUS[0]}

    if [ "$status" -eq 0 ]; then
      log "INFO" "Успешно загружено: $url"
      echo "$url|DONE" >>"$STATUS_CACHE_FILE"
      return 0
    else
      log "WARN" "Ошибка при загрузке (код $status): $url"
      if [ $attempt -lt $MAX_RETRIES ]; then
        log "INFO" "Жду $RETRY_DELAY секунд перед следующей попыткой..."
        sleep $RETRY_DELAY
      fi
    fi

    ((attempt++))
  done

  log "ERROR" "Не удалось загрузить после $MAX_RETRIES попыток: $url"
  echo "$url|FAILED" >>"$STATUS_CACHE_FILE"
  return 1
}
```

- [ ] **Step 2: Remove the ARCHIVE_FILE grep check (lines 175-181)**

Remove this block from the main loop (it checks a file that is not written by this script):

```bash
  # Проверяем, не было ли видео уже загружено ранее (из archive)
  if [ -f "$ARCHIVE_FILE" ] && grep -qF "$url" "$ARCHIVE_FILE"; then
    log "INFO" "Пропускаю (уже в архиве): $url"
    echo "$url|DONE" >>"$STATUS_CACHE_FILE"
    ((skipped++))
    continue
  fi
```

- [ ] **Step 3: Verify the script is syntactically valid**

```bash
bash -n download.sh && echo "OK"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add download.sh
git commit -m "fix: remove undefined \$temp_archive and dead ARCHIVE_FILE grep in download.sh"
```

---

## Task 2: Rework trigger_server.py stats

**Files:**
- Modify: `trigger_server.py`

- [ ] **Step 1: Update imports and constants**

Replace the top of the file (lines 1-33) with:

```python
#!/usr/bin/env python3
"""
Micro HTTP server inside the pipeline container.
Allows triggering pipeline.sh via HTTP and streaming its logs via SSE.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import httpx

logger = logging.getLogger(__name__)

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/cookies/cookies.txt")
MAX_LOG_LINES = 2000
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-vl-7b-instruct")
LM_STATUS_FILE = "/tmp/lm_status.json"
URL_CACHE_FILE = os.environ.get("URL_CACHE_FILE", "saved_videos/url_cache.txt")
STATUS_CACHE_FILE = os.environ.get("STATUS_CACHE_FILE", "saved_videos/status_cache.txt")
RAW_DIR = os.environ.get("RAW_DIR", "saved_videos/raw")
META_DIR = os.environ.get("META_DIR", "saved_videos/meta")
DOWNLOAD_CMD = ["/app/download.sh", COOKIES_FILE]
ANALYZE_CMD = ["python3", "/app/batch_analyze.py"]

_dl_stats: dict = {
    "phase": "idle",
    "total_urls": 0,
    "downloaded": 0,
    "failed": 0,
    "total_videos": 0,
    "analyzed": 0,
}
```

- [ ] **Step 2: Replace `_count_archive` and `_poll_archive` with file-based helpers**

Remove `_count_archive()` and `_poll_archive()`. After `_append_log`, add:

```python
def _read_download_stats() -> dict:
    total_urls = 0
    downloaded = 0
    failed = 0
    try:
        with open(URL_CACHE_FILE) as f:
            total_urls = sum(1 for line in f if line.strip())
    except Exception:
        pass
    try:
        with open(STATUS_CACHE_FILE) as f:
            for line in f:
                if "|DONE" in line:
                    downloaded += 1
                elif "|FAILED" in line:
                    failed += 1
    except Exception:
        pass
    return {"total_urls": total_urls, "downloaded": downloaded, "failed": failed}


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


def _clear_failed_from_status_cache() -> int:
    """Remove FAILED lines from status_cache.txt. Returns count of removed lines."""
    try:
        path = Path(STATUS_CACHE_FILE)
        if not path.exists():
            return 0
        lines = path.read_text().splitlines()
        kept = [ln for ln in lines if "|FAILED" not in ln]
        removed = len(lines) - len(kept)
        path.write_text("\n".join(kept) + ("\n" if kept else ""))
        return removed
    except Exception as exc:
        logger.debug("_clear_failed_from_status_cache failed: %s", exc)
        return 0


async def _poll_stats() -> None:
    """Background task: update _dl_stats every 3s. Auto-transitions fetching_urls→downloading."""
    while True:
        await asyncio.sleep(3)
        ds = _read_download_stats()
        _dl_stats["total_urls"] = ds["total_urls"]
        _dl_stats["downloaded"] = ds["downloaded"]
        _dl_stats["failed"] = ds["failed"]
        if _dl_stats["phase"] == "fetching_urls" and ds["total_urls"] > 0:
            _dl_stats["phase"] = "downloading"
        if _dl_stats["phase"] == "analyzing":
            as_ = _read_analyze_stats()
            _dl_stats["total_videos"] = as_["total_videos"]
            _dl_stats["analyzed"] = as_["analyzed"]
```

- [ ] **Step 3: Replace `_run_pipeline()` with the new version**

Replace the entire `_run_pipeline` function with:

```python
async def _run_pipeline() -> None:
    global _running, _last_run
    _running = True
    _last_run = datetime.now(timezone.utc).isoformat()
    _log_buffer.clear()
    _append_log(f"=== started at {_last_run} ===")

    try:
        # ── Phase 1: Download (fetching_urls → downloading) ────────────────
        _dl_stats["phase"] = "fetching_urls"
        _dl_stats.update({"total_urls": 0, "downloaded": 0, "failed": 0})
        poll_task = asyncio.create_task(_poll_stats())

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

        ds = _read_download_stats()
        _dl_stats.update(ds)
        _dl_stats["phase"] = "downloading"  # ensure phase is correct in final snapshot
        _append_log(
            f"=== download: скачано {ds['downloaded']}, ошибок {ds['failed']}, всего URL {ds['total_urls']} ==="
        )
        _append_log(f"=== download.sh finished (exit code {process.returncode}) ===")

        if process.returncode != 0:
            _append_log("=== download.sh failed — skipping analyze phase ===")
            return

        # ── Phase 2: Analyze ───────────────────────────────────────────────
        _dl_stats["phase"] = "analyzing"
        as_ = _read_analyze_stats()
        _dl_stats.update(as_)
        poll_task2 = asyncio.create_task(_poll_stats())

        try:
            process2 = await asyncio.create_subprocess_exec(
                *ANALYZE_CMD,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for raw in process2.stdout:
                _append_log(raw.decode(errors="replace").rstrip())
            await process2.wait()
        finally:
            poll_task2.cancel()
            try:
                await poll_task2
            except asyncio.CancelledError:
                pass

        as_ = _read_analyze_stats()
        _dl_stats.update(as_)
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

- [ ] **Step 4: Add `POST /retry-failed` endpoint after `POST /run`**

After the `/run` route, add:

```python
@app.post("/retry-failed")
async def retry_failed():
    if _running:
        return {"status": "already_running"}
    removed = _clear_failed_from_status_cache()
    asyncio.create_task(_run_pipeline())
    return {"status": "started", "cleared_failed": removed}
```

- [ ] **Step 5: Initialize `_dl_stats` from files on module load**

Add a startup event to pre-populate stats from existing files (so the sidebar shows correct numbers immediately after container restart):

After `app = FastAPI()`, add:

```python
@app.on_event("startup")
async def _startup():
    _dl_stats.update(_read_download_stats())
    _dl_stats.update(_read_analyze_stats())
```

- [ ] **Step 6: Verify syntax**

```bash
python3 -m py_compile trigger_server.py && echo "OK"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add trigger_server.py
git commit -m "feat: replace SQLite stats with file-based counters, add /retry-failed endpoint"
```

---

## Task 3: Add retry-failed proxy in viewer/api/main.py

**Files:**
- Modify: `viewer/api/main.py`

- [ ] **Step 1: Add `POST /api/pipeline/retry-failed` after `/api/pipeline/dl-stats`**

After the `pipeline_dl_stats` route (around line 93), add:

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
git commit -m "feat: proxy POST /api/pipeline/retry-failed in viewer API"
```

---

## Task 4: Update PipelinePanel.css

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.css`

- [ ] **Step 1: Replace existing `.dl-stats` block and add new classes**

Replace everything from `.dl-stats {` to the end of the file with:

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

.dl-stats-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 6px;
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

.dl-stats-value.active {
  color: #22c55e;
}

.dl-failed-label {
  font-size: 11px;
  color: #f87171;
}

.dl-failed-value {
  font-size: 11px;
  font-weight: 600;
  color: #f87171;
}

.dl-phase {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.btn-retry {
  width: 100%;
  padding: 5px 0;
  background: transparent;
  border: 1px solid #f87171;
  border-radius: 6px;
  color: #f87171;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 2px;
}

.btn-retry:hover {
  background: rgba(248, 113, 113, 0.1);
}
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/PipelinePanel.css
git commit -m "feat: update PipelinePanel styles for X/Y counters, failed badge, retry button"
```

---

## Task 5: Update PipelinePanel.jsx

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.jsx`

- [ ] **Step 1: Replace the entire file with the updated version**

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

  async function handleRetryFailed() {
    try {
      const r = await fetch("/api/pipeline/retry-failed", { method: "POST" });
      const d = await r.json();
      if (d.status === "started" || d.status === "already_running") {
        setRunning(true);
        setLogsOpen(true);
      }
    } catch (e) {
      console.error(e);
    }
  }

  const phase = dlStats?.phase;
  const phaseLabel =
    phase === "fetching_urls" ? "Получаю список URL..." :
    phase === "downloading"   ? "Загрузка..."           :
    phase === "analyzing"     ? "Анализ..."             : null;

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
          {/* Download section */}
          <div className="dl-stats-section">
            <div className="dl-stats-title">Загрузка</div>
            {phase === "fetching_urls" ? (
              <div className="dl-phase">Получаю список URL...</div>
            ) : (
              <>
                <div className="dl-stats-row">
                  <span className="dl-stats-label">Скачано</span>
                  <span className={`dl-stats-value${phase === "downloading" ? " active" : ""}`}>
                    {dlStats.downloaded} / {dlStats.total_urls}
                  </span>
                </div>
                {dlStats.failed > 0 && (
                  <div className="dl-stats-row">
                    <span className="dl-failed-label">Ошибок</span>
                    <span className="dl-failed-value">{dlStats.failed}</span>
                  </div>
                )}
              </>
            )}
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
          {running && phaseLabel && phase !== "fetching_urls" && (
            <div className="dl-phase">{phaseLabel}</div>
          )}

          {/* Retry failed button */}
          {!running && dlStats.failed > 0 && (
            <button className="btn-retry" onClick={handleRetryFailed}>
              ↺ Retry {dlStats.failed} failed
            </button>
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
git commit -m "feat: show X/Y download and analyze counters with retry-failed button"
```

---

## Task 6: End-to-end verification

- [ ] **Step 1: Build Docker**

```bash
docker compose build
```

Expected: build completes without errors.

- [ ] **Step 2: Start and check `/dl-stats`**

```bash
docker compose up -d
curl -s http://localhost:8000/api/pipeline/dl-stats | python3 -m json.tool
```

Expected (values will vary based on existing files):
```json
{
  "phase": "idle",
  "total_urls": 0,
  "downloaded": 0,
  "failed": 0,
  "total_videos": 12,
  "analyzed": 12,
  "running": false
}
```

- [ ] **Step 3: Open browser at http://localhost:8000**

Verify sidebar shows:
```
Загрузка
  Скачано: 0 / 0

Анализ
  Проанализировано: 12 / 12
```

- [ ] **Step 4: Click "▶ Run pipeline" and verify phases**

- `fetching_urls`: label "Получаю список URL..." appears, counters show 0/0
- `downloading`: counter updates to `N / M` every 3s, active value turns green
- `analyzing`: analyze counter updates, download counter stays at final value
- After completion: counters show final state, "Retry N failed" button appears if any failed

- [ ] **Step 5: Verify log summary lines**

Open 📋 modal. Verify log contains:
```
=== download: скачано N, ошибок 0, всего URL M ===
=== analyze: проанализировано K / K видео ===
```

- [ ] **Step 6: Test retry-failed (if any failed URLs)**

Curl to verify endpoint works:
```bash
curl -s -X POST http://localhost:8000/api/pipeline/retry-failed | python3 -m json.tool
```

Expected:
```json
{
  "status": "started",
  "cleared_failed": 0
}
```
