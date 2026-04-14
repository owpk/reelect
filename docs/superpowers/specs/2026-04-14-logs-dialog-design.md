# Logs Dialog & LM Studio Status — Design Spec

**Date:** 2026-04-14  
**Status:** Approved

## Problem

When running in Docker, pipeline logs are not visible. The current inline log terminal in `PipelinePanel` only appears after clicking "Run pipeline" and is too small for diagnosing issues. LM Studio connection status is completely invisible.

## Goal

Add a logs button next to "Run pipeline" that opens a modal dialog showing:
1. Real-time and historical pipeline logs
2. LM Studio connection status (connected/disconnected, model name, last request time)

## Chosen Approach

**Backend + Frontend (Approach B):** Add `/logs` and `/lm-status` endpoints to `trigger_server.py`, proxy them through `viewer/api/main.py`, and build a new `LogsModal` React component.

---

## Backend Changes

### trigger_server.py

**New global variable:**
```python
_last_lm_request_at: str | None = None
```
Updated in `_lm_chat()` each time a request is made to LM Studio.

**New endpoint `GET /logs`:**
```json
{
  "lines": ["2026-04-14 12:00:00 | INFO | === started ===", "..."],
  "running": true,
  "last_run": "2026-04-14T12:00:00+00:00"
}
```
Returns current `_log_buffer`, `_running`, and `_last_run`.

**New endpoint `GET /lm-status`:**
- Makes `GET {LLM_BASE_URL}/v1/models` with 3s timeout
- Returns:
```json
{
  "connected": true,
  "url": "http://host.docker.internal:1234/v1",
  "model": "qwen2.5-vl-7b-instruct",
  "last_request_at": "2026-04-14T12:34:01+00:00"
}
```
- On timeout/error: `{ "connected": false, "url": "...", "model": null, "last_request_at": null }`

### viewer/api/main.py

Two new proxy endpoints:
- `GET /api/pipeline/logs` → `{PIPELINE_URL}/logs`
- `GET /api/lm/status` → `{PIPELINE_URL}/lm-status`

---

## Frontend Changes

### New files
- `viewer/frontend/src/components/LogsModal.jsx`
- `viewer/frontend/src/components/LogsModal.css`

### Modified files
- `viewer/frontend/src/components/PipelinePanel.jsx` — add 📋 button + `<LogsModal>`
- `viewer/frontend/src/components/PipelinePanel.css` — style for the icon button

### LogsModal layout

```
┌─────────────────────────────────────────┐
│  Pipeline Logs                    [✕]   │
├─────────────────────────────────────────┤
│  LM Studio                              │
│  ● Connected  qwen2.5-vl-7b-instruct   │
│  URL: http://host.docker.internal:1234  │
│  Last request: 14.04.2026 12:34:01      │
├─────────────────────────────────────────┤
│  ● Running... / Last run: ...           │
│                                         │
│  [log terminal ~400px scrollable]       │
│  > 2026-04-14 12:30:00 | INFO | start  │
│  > ...                                  │
└─────────────────────────────────────────┘
```

### LogsModal behavior

**On open:**
1. `GET /api/pipeline/logs` — load buffer into terminal, get `running` state
2. `GET /api/lm/status` — populate LM Studio section
3. If `running: true` — connect to `EventSource("/api/pipeline/stream")` and append lines in real time

**While open:**
- LM Studio status refreshed every 10 seconds
- SSE auto-connects if pipeline starts while modal is open (poll `/api/pipeline/status` every 5s when not streaming)

**On close:**
- Close SSE connection
- Clear polling intervals

### Button placement

In `PipelinePanel`, the `.pipeline-actions` div gets two buttons side by side:
```
[ ▶ Run pipeline ] [ 📋 ]
```
The 📋 button is always enabled (not disabled when pipeline is running).

---

## Data Flow

```
trigger_server.py (_log_buffer, _running, _last_lm_request_at)
    │
    ├── GET /logs          → viewer GET /api/pipeline/logs  → LogsModal (initial load)
    ├── GET /stream (SSE)  → viewer GET /api/pipeline/stream → LogsModal (live tail)
    └── GET /lm-status     → viewer GET /api/lm/status      → LogsModal (LM section)
```

---

## Out of Scope

- Persistent log storage across container restarts
- Log filtering or search
- Multiple concurrent run history
