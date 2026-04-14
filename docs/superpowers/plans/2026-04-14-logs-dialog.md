# Logs Dialog & LM Studio Status — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 📋 button next to "Run pipeline" that opens a modal dialog showing real-time pipeline logs and LM Studio connection status.

**Architecture:** Add two endpoints (`/logs`, `/lm-status`) to `trigger_server.py`, proxy them through `viewer/api/main.py`, then build a `LogsModal` React component mounted from `PipelinePanel`.

**Tech Stack:** Python/FastAPI (backend), React/JSX + CSS variables (frontend), EventSource SSE (streaming), httpx (HTTP client).

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `trigger_server.py` | Modify | Add `/logs` and `/lm-status` endpoints, track `_last_lm_request_at` |
| `viewer/api/main.py` | Modify | Proxy `/api/pipeline/logs` and `/api/lm/status` |
| `viewer/frontend/src/components/LogsModal.jsx` | Create | Modal dialog component with log terminal + LM status |
| `viewer/frontend/src/components/LogsModal.css` | Create | Styles for the modal |
| `viewer/frontend/src/components/PipelinePanel.jsx` | Modify | Add 📋 button and mount `<LogsModal>` |
| `viewer/frontend/src/components/PipelinePanel.css` | Modify | Style for the icon button |

---

## Task 1: Add `/logs` endpoint and `_last_lm_request_at` tracking to trigger_server.py

**Files:**
- Modify: `trigger_server.py`

- [ ] **Step 1: Write LM request timestamp to a temp file from analyze.py**

`trigger_server.py` runs `pipeline.sh` as a subprocess, so its globals are not shared with `analyze.py`. The solution: write the timestamp to `/tmp/lm_status.json` from `analyze.py`, and read it in `trigger_server.py`.

In `analyze.py`, add this import at the top (it already imports `json` and `datetime`):
```python
import tempfile
```
(already imported via `tempfile.NamedTemporaryFile` — no change needed)

In `analyze.py`, add a helper after the existing module-level variables (around line 43):
```python
_LM_STATUS_FILE = "/tmp/lm_status.json"

def _write_lm_request_time() -> None:
    try:
        import json as _json
        with open(_LM_STATUS_FILE, "w") as f:
            _json.dump({"last_request_at": datetime.now(timezone.utc).isoformat()}, f)
    except Exception:
        pass
```

In `analyze.py`, in `_lm_chat()`, at the top of the function body (before `extra: dict = {}`):
```python
    _write_lm_request_time()
```

- [ ] **Step 2: Add `GET /logs` endpoint to trigger_server.py**

In `trigger_server.py`, after the existing `@app.get("/status")` route, add:

```python
@app.get("/logs")
async def logs():
    return {"lines": list(_log_buffer), "running": _running, "last_run": _last_run}
```

- [ ] **Step 3: Verify `/logs` manually**

```bash
cd /Users/owpk/gh/reelect
uvicorn trigger_server:app --port 8001 &
sleep 1
curl -s http://localhost:8001/logs | python3 -m json.tool
# Expected: {"lines": [], "running": false, "last_run": null}
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add trigger_server.py analyze.py
git commit -m "feat: add /logs endpoint and LM request timestamp tracking"
```

---

## Task 2: Add `/lm-status` endpoint to trigger_server.py

**Files:**
- Modify: `trigger_server.py`

- [ ] **Step 1: Add imports needed for lm-status**

`trigger_server.py` already imports `os`. Add `httpx` import if not present. Check line 1-10 — if `httpx` is missing, add it after `from fastapi.responses import StreamingResponse`:

```python
import httpx
```

Also add these near the top (after existing `os` import):

```python
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-vl-7b-instruct")
```

- [ ] **Step 2: Add `GET /lm-status` endpoint**

In `trigger_server.py`, after the `GET /logs` route, add:

```python
@app.get("/lm-status")
async def lm_status():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{LM_STUDIO_URL}/models")
            models = r.json().get("data", [])
            model_id = models[0]["id"] if models else LM_STUDIO_MODEL
            connected = True
    except Exception:
        model_id = None
        connected = False

    try:
        import json as _json
        with open("/tmp/lm_status.json") as f:
            last_request_at = _json.load(f).get("last_request_at")
    except Exception:
        last_request_at = None

    return {
        "connected": connected,
        "url": LLM_BASE_URL,
        "model": model_id,
        "last_request_at": last_request_at,
    }
```

- [ ] **Step 3: Verify `/lm-status` manually**

```bash
cd /Users/owpk/gh/reelect
uvicorn trigger_server:app --port 8001 &
sleep 1
curl -s http://localhost:8001/lm-status | python3 -m json.tool
# Expected when LM Studio is off:
# {"connected": false, "url": "http://localhost:1234/v1", "model": null, "last_request_at": null}
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add trigger_server.py
git commit -m "feat: add /lm-status endpoint to trigger_server"
```

---

## Task 3: Add proxy endpoints to viewer/api/main.py

**Files:**
- Modify: `viewer/api/main.py`

- [ ] **Step 1: Add `GET /api/pipeline/logs` proxy**

In `viewer/api/main.py`, after the existing `GET /api/pipeline/status` route (line ~57), add:

```python
@app.get("/api/pipeline/logs")
async def pipeline_logs():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PIPELINE_URL}/logs", timeout=5)
        return r.json()
```

- [ ] **Step 2: Add `GET /api/lm/status` proxy**

Directly after the above, add:

```python
@app.get("/api/lm/status")
async def lm_status():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{PIPELINE_URL}/lm-status", timeout=5)
        return r.json()
```

- [ ] **Step 3: Verify endpoints exist**

```bash
cd /Users/owpk/gh/reelect/viewer
uvicorn api.main:app --port 8000 &
sleep 1
curl -s http://localhost:8000/api/pipeline/logs
# Expected: connection error to pipeline (that's fine — endpoint exists)
curl -s http://localhost:8000/api/lm/status
# Expected: connection error to pipeline (that's fine — endpoint exists)
kill %1
```

- [ ] **Step 4: Commit**

```bash
git add viewer/api/main.py
git commit -m "feat: proxy /api/pipeline/logs and /api/lm/status in viewer API"
```

---

## Task 4: Create LogsModal.css

**Files:**
- Create: `viewer/frontend/src/components/LogsModal.css`

- [ ] **Step 1: Create the CSS file**

```css
/* LogsModal.css */
.logs-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 24px;
}

.logs-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: 100%;
  max-width: 760px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}

.logs-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.logs-modal-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.logs-modal-close {
  background: var(--surface2);
  border: none;
  color: var(--text-muted);
  width: 28px;
  height: 28px;
  border-radius: 50%;
  cursor: pointer;
  font-size: 12px;
  transition: color 0.1s;
}
.logs-modal-close:hover { color: var(--text); }

/* LM Studio section */
.lm-section {
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.lm-section-title {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.lm-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.lm-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.lm-dot.connected { background: #22c55e; box-shadow: 0 0 5px #22c55e; }
.lm-dot.disconnected { background: #ef4444; }

.lm-model {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}

.lm-meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 4px;
}

.lm-meta-line {
  font-size: 11px;
  color: var(--text-muted);
}

/* Pipeline status row */
.logs-status-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.logs-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.logs-status-dot.running {
  background: #22c55e;
  box-shadow: 0 0 6px #22c55e;
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
.logs-status-dot.idle { background: #444; }

.logs-status-label {
  font-size: 12px;
  color: var(--text-muted);
}

.logs-last-run {
  font-size: 11px;
  color: var(--text-muted);
  margin-left: auto;
}

/* Terminal */
.logs-terminal {
  flex: 1;
  overflow-y: auto;
  background: #0a0a0a;
  padding: 12px 16px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px;
  line-height: 1.7;
}

.logs-empty {
  color: #555;
  font-style: italic;
}

.logs-line {
  color: #9a9a9a;
  white-space: pre-wrap;
  word-break: break-all;
}
.logs-line:last-child { color: #e0e0e0; }
.logs-line.error { color: #f87171; }
.logs-line.info { color: #9a9a9a; }
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/LogsModal.css
git commit -m "feat: add LogsModal styles"
```

---

## Task 5: Create LogsModal.jsx

**Files:**
- Create: `viewer/frontend/src/components/LogsModal.jsx`

- [ ] **Step 1: Create the component**

```jsx
import { useState, useEffect, useRef } from "react";
import "./LogsModal.css";

export default function LogsModal({ onClose }) {
  const [lines, setLines] = useState([]);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [lmStatus, setLmStatus] = useState(null);
  const endRef = useRef(null);
  const esRef = useRef(null);
  const pollRef = useRef(null);

  // Close on Escape
  useEffect(() => {
    const handler = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Auto-scroll
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  // Fetch LM status
  function fetchLmStatus() {
    fetch("/api/lm/status")
      .then((r) => r.json())
      .then(setLmStatus)
      .catch(() => setLmStatus({ connected: false, url: null, model: null, last_request_at: null }));
  }

  // Connect to SSE stream
  function connectStream() {
    if (esRef.current) esRef.current.close();
    const es = new EventSource("/api/pipeline/stream");
    esRef.current = es;
    es.onmessage = (e) => {
      if (e.data === "__done__") {
        setRunning(false);
        es.close();
        esRef.current = null;
        return;
      }
      setLines((prev) => [...prev, e.data]);
    };
    es.onerror = () => {
      setRunning(false);
      es.close();
      esRef.current = null;
    };
  }

  // Initial load
  useEffect(() => {
    fetch("/api/pipeline/logs")
      .then((r) => r.json())
      .then((d) => {
        setLines(d.lines ?? []);
        setRunning(d.running ?? false);
        setLastRun(d.last_run ?? null);
        if (d.running) connectStream();
      })
      .catch(() => {});

    fetchLmStatus();

    // Poll LM status every 10s
    const lmInterval = setInterval(fetchLmStatus, 10_000);

    // Poll pipeline status every 5s to detect if it starts while modal is open
    pollRef.current = setInterval(() => {
      if (esRef.current) return; // already streaming
      fetch("/api/pipeline/status")
        .then((r) => r.json())
        .then((d) => {
          setRunning(d.running);
          setLastRun(d.last_run);
          if (d.running) connectStream();
        })
        .catch(() => {});
    }, 5_000);

    return () => {
      esRef.current?.close();
      clearInterval(lmInterval);
      clearInterval(pollRef.current);
    };
  }, []);

  function formatTime(iso) {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div className="logs-overlay" onClick={onClose}>
      <div className="logs-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="logs-modal-header">
          <span className="logs-modal-title">Pipeline Logs</span>
          <button className="logs-modal-close" onClick={onClose}>✕</button>
        </div>

        {/* LM Studio section */}
        <div className="lm-section">
          <div className="lm-section-title">LM Studio</div>
          {lmStatus === null ? (
            <div className="lm-row"><span className="logs-status-label">Loading...</span></div>
          ) : (
            <>
              <div className="lm-row">
                <span className={`lm-dot ${lmStatus.connected ? "connected" : "disconnected"}`} />
                <span className="lm-model">
                  {lmStatus.connected ? (lmStatus.model ?? "connected") : "Disconnected"}
                </span>
              </div>
              <div className="lm-meta">
                {lmStatus.url && (
                  <span className="lm-meta-line">URL: {lmStatus.url}</span>
                )}
                {lmStatus.last_request_at && (
                  <span className="lm-meta-line">
                    Last request: {formatTime(lmStatus.last_request_at)}
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {/* Pipeline status row */}
        <div className="logs-status-row">
          <span className={`logs-status-dot ${running ? "running" : "idle"}`} />
          <span className="logs-status-label">{running ? "Running..." : "Idle"}</span>
          {lastRun && !running && (
            <span className="logs-last-run">last: {formatTime(lastRun)}</span>
          )}
        </div>

        {/* Log terminal */}
        <div className="logs-terminal">
          {lines.length === 0 ? (
            <div className="logs-empty">No logs yet.</div>
          ) : (
            lines.map((line, i) => {
              const cls = line.includes("ERROR") || line.includes("error")
                ? "error"
                : "info";
              return <div key={i} className={`logs-line ${cls}`}>{line}</div>;
            })
          )}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/LogsModal.jsx
git commit -m "feat: add LogsModal component"
```

---

## Task 6: Update PipelinePanel.jsx — add 📋 button and mount LogsModal

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.jsx`

- [ ] **Step 1: Replace PipelinePanel.jsx with updated version**

The full updated file (adds `logsOpen` state, imports `LogsModal`, adds the icon button, removes the old inline log terminal and show/hide button):

```jsx
import { useState, useEffect } from "react";
import LogsModal from "./LogsModal.jsx";
import "./PipelinePanel.css";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [logsOpen, setLogsOpen] = useState(false);

  useEffect(() => {
    fetch("/api/pipeline/status")
      .then((r) => r.json())
      .then((d) => { setRunning(d.running); setLastRun(d.last_run); })
      .catch(() => {});
  }, []);

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

      {logsOpen && <LogsModal onClose={() => setLogsOpen(false)} />}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/PipelinePanel.jsx
git commit -m "feat: add logs dialog button to PipelinePanel"
```

---

## Task 7: Update PipelinePanel.css — style the icon button

**Files:**
- Modify: `viewer/frontend/src/components/PipelinePanel.css`

- [ ] **Step 1: Change `.pipeline-actions` to row layout and add `.btn-logs-icon`**

Replace the current `.pipeline-actions` rule:
```css
.pipeline-actions { display: flex; flex-direction: column; gap: 6px; }
```

With:
```css
.pipeline-actions { display: flex; flex-direction: row; gap: 6px; align-items: center; }
```

Then replace the entire `.btn-logs` rule (which is no longer used):
```css
.btn-logs {
  width: 100%;
  padding: 6px 0;
  background: var(--surface2);
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
}
.btn-logs:hover { color: var(--text); }
```

With:
```css
.btn-logs-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}
.btn-logs-icon:hover { background: var(--surface); }
```

Also update `.btn-run` to use `flex: 1` instead of `width: 100%` so it fills available space alongside the icon button:

Replace:
```css
.btn-run {
  width: 100%;
```
With:
```css
.btn-run {
  flex: 1;
```

- [ ] **Step 2: Commit**

```bash
git add viewer/frontend/src/components/PipelinePanel.css
git commit -m "feat: style logs icon button in PipelinePanel"
```

---

## Task 8: End-to-end verification

- [ ] **Step 1: Build and start Docker Compose**

```bash
cd /Users/owpk/gh/reelect
docker compose build
docker compose up
```

- [ ] **Step 2: Open browser at http://localhost:8000**

Verify:
- "▶ Run pipeline" and 📋 buttons appear side by side in the sidebar
- Clicking 📋 opens the logs modal
- LM Studio section shows "Disconnected" (red dot) if LM Studio is not running, or "Connected" + model name if it is
- The log terminal shows previous run logs (or "No logs yet")

- [ ] **Step 3: Click "▶ Run pipeline"**

Verify:
- Modal opens automatically
- Logs appear in real time as pipeline runs
- Status row shows "Running..." with green pulsing dot
- When pipeline finishes, status changes to "Idle"

- [ ] **Step 4: Close and reopen modal**

Verify that previous run logs are still visible (buffer persists in `trigger_server.py`).
