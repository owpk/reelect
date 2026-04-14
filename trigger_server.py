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
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import httpx

logger = logging.getLogger(__name__)

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/cookies/cookies.txt")
PIPELINE_CMD = ["/app/pipeline.sh", COOKIES_FILE]
MAX_LOG_LINES = 2000
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-vl-7b-instruct")
LM_STATUS_FILE = "/tmp/lm_status.json"
ARCHIVE_FILE = os.environ.get("ARCHIVE_FILE", "saved_videos/downloaded_archive.txt")
DOWNLOAD_CMD = ["/app/download.sh", COOKIES_FILE]
ANALYZE_CMD = ["python3", "/app/batch_analyze.py"]

_dl_stats: dict = {
    "session_downloaded": 0,
    "total_archived": 0,
    "phase": "idle",
}

app = FastAPI()

_running = False
_last_run: str | None = None
_log_buffer: list[str] = []


def _append_log(line: str) -> None:
    _log_buffer.append(line)
    if len(_log_buffer) > MAX_LOG_LINES:
        _log_buffer.pop(0)


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


@app.post("/run")
async def run():
    if _running:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline())
    return {"status": "started"}


@app.get("/status")
async def status():
    return {"running": _running, "last_run": _last_run}


@app.get("/logs")
async def logs():
    return {"lines": list(_log_buffer), "running": _running, "last_run": _last_run}


@app.get("/dl-stats")
async def dl_stats():
    return {**_dl_stats, "running": _running}


@app.get("/lm-status")
async def lm_status():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{LM_STUDIO_URL}/models")
            models = r.json().get("data", [])
            model_id = models[0]["id"] if models else None
            connected = True
    except Exception as exc:
        logger.debug("lm-status: LM Studio unreachable: %s", exc)
        model_id = None
        connected = False

    try:
        with open(LM_STATUS_FILE) as f:
            last_request_at = json.load(f).get("last_request_at")
    except Exception:
        last_request_at = None

    return {
        "connected": connected,
        "url": LM_STUDIO_URL,
        "model": model_id,
        "last_request_at": last_request_at,
    }


@app.get("/stream")
async def stream():
    async def generate():
        pos = 0
        while True:
            while pos < len(_log_buffer):
                yield f"data: {_log_buffer[pos]}\n\n"
                pos += 1
            if not _running and pos >= len(_log_buffer):
                yield "data: __done__\n\n"
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
