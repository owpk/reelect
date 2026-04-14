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
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234/v1")
LM_STUDIO_MODEL = os.environ.get("LM_STUDIO_MODEL", "qwen2.5-vl-7b-instruct")
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

app = FastAPI()

_running = False
_last_run: str | None = None
_log_buffer: list[str] = []
_current_process: asyncio.subprocess.Process | None = None


def _append_log(line: str) -> None:
    _log_buffer.append(line)
    if len(_log_buffer) > MAX_LOG_LINES:
        _log_buffer.pop(0)


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


async def _run_pipeline() -> None:
    global _running, _last_run, _current_process
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

        ds = _read_download_stats()
        _dl_stats.update(ds)
        _append_log(
            f"=== download: скачано {ds['downloaded']}, ошибок {ds['failed']}, всего URL {ds['total_urls']} ==="
        )
        if process.returncode < 0:
            _append_log("=== pipeline остановлен пользователем ===")
            return
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
    _dl_stats.update(_read_download_stats())
    _dl_stats.update(_read_analyze_stats())


@app.post("/run")
async def run():
    if _running:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline())
    return {"status": "started"}


@app.post("/retry-failed")
async def retry_failed():
    if _running:
        return {"status": "already_running"}
    removed = _clear_failed_from_status_cache()
    asyncio.create_task(_run_pipeline())
    return {"status": "started", "cleared_failed": removed}


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
