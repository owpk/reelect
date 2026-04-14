#!/usr/bin/env python3
"""
Micro HTTP server inside the pipeline container.
Allows triggering pipeline.sh via HTTP and streaming its logs via SSE.
"""

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import httpx

from config import load_env

logger = logging.getLogger(__name__)

_config = load_env(".env")
COOKIES_FILE = os.environ.get("COOKIES_FILE", "/cookies/cookies.txt")
MAX_LOG_LINES = 2000
LLM_BASE_URL = _config.get("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = _config.get("LLM_MODEL", "qwen2.5-vl-7b-instruct")
LM_STATUS_FILE = "/tmp/lm_status.json"
ARCHIVE_DB = os.environ.get("ARCHIVE_DB", "saved_videos/downloaded_archive.db")
RAW_DIR = os.environ.get("RAW_DIR", "saved_videos/raw")
META_DIR = os.environ.get("META_DIR", "saved_videos/meta")
DOWNLOAD_CMD = ["/app/download.sh", COOKIES_FILE]
ANALYZE_CMD = ["python3", "/app/batch_analyze.py"]

_dl_stats: dict = {
    "phase": "idle",
    "session_downloaded": 0,
    "total_archived": 0,
    "total_videos": 0,
    "analyzed": 0,
}

app = FastAPI()

_running = False
_last_run: str | None = None
_log_buffer: list[str] = []
_current_process: asyncio.subprocess.Process | None = None


def _append_log(line: str) -> None:
    _log_buffer.append(line)
    if len(_log_buffer) > MAX_LOG_LINES:
        _log_buffer.pop(0)


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


@app.on_event("startup")
async def _startup():
    _dl_stats.update({
        "total_videos": _count_raw_videos(),
        "total_archived": _count_archive(),
    })
    _dl_stats.update(_read_analyze_stats())


@app.post("/run")
async def run():
    if _running:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline())
    return {"status": "started"}



@app.post("/stop")
async def stop():
    if not _running:
        return {"status": "not_running"}
    p = _current_process
    if p is not None:
        try:
            p.terminate()
        except ProcessLookupError:
            pass
    return {"status": "stopping"}


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
            r = await client.get(f"{LLM_BASE_URL}/models")
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
        "url": LLM_BASE_URL,
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
