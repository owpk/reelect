#!/usr/bin/env python3
"""
Micro HTTP server inside the pipeline container.
Allows triggering the Python reel pipeline via HTTP and streaming its logs via SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import load_env

logger = logging.getLogger(__name__)

MAX_LOG_LINES = 2000
LM_STATUS_FILE = Path("/tmp/lm_status.json")
RAW_DIR = Path("saved_videos/raw")
META_DIR = Path("saved_videos/meta")
ARCHIVE_DB = Path("saved_videos/downloaded_archive.db")

_dl_stats: dict[str, object] = {
    "phase": "idle",
    "session_downloaded": 0,
    "total_archived": 0,
    "total_videos": 0,
    "analyzed": 0,
}

_pipeline_state: dict[str, object] = {
    "running": False,
    "mode": None,
    "phase": "idle",
    "last_run": None,
}

_log_buffer: list[str] = []
_current_process: asyncio.subprocess.Process | None = None


class RunSingleRequest(BaseModel):
    url: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    _dl_stats["total_archived"] = _count_archive()
    _dl_stats.update(_read_analyze_stats())
    yield


app = FastAPI(lifespan=lifespan)


def _append_log(line: str) -> None:
    _log_buffer.append(line)
    if len(_log_buffer) > MAX_LOG_LINES:
        _log_buffer.pop(0)
    _apply_stage_marker(line)


def _apply_stage_marker(line: str) -> None:
    if line == "STAGE: downloading":
        _pipeline_state["phase"] = "downloading"
        _dl_stats["phase"] = "downloading"
    elif line == "STAGE: parsing":
        _pipeline_state["phase"] = "parsing"
        _dl_stats["phase"] = "parsing"
    elif line == "STAGE: analyzing":
        _pipeline_state["phase"] = "analyzing"
        _dl_stats["phase"] = "analyzing"


def _count_raw_videos() -> int:
    try:
        return len(list(RAW_DIR.rglob("*.mp4")))
    except Exception:
        return 0


def _count_archive() -> int:
    try:
        with sqlite3.connect(ARCHIVE_DB) as con:
            return con.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
    except Exception:
        return 0


def _read_analyze_stats() -> dict[str, int]:
    try:
        total_videos = len(list(RAW_DIR.rglob("*.mp4")))
    except Exception:
        total_videos = 0
    try:
        analyzed = len(list(META_DIR.glob("*.json")))
    except Exception:
        analyzed = 0
    return {"total_videos": total_videos, "analyzed": analyzed}


def _runtime_config() -> dict[str, str]:
    return load_env(".env")


def _build_cli_command(mode: str, url: str | None = None) -> list[str]:
    command = ["python3", "-m", "reelect_pipeline.cli", mode]
    if url:
        command.append(url)
    return command


async def _poll_stats(baseline: int = 0) -> None:
    while True:
        await asyncio.sleep(1)
        phase = _pipeline_state["phase"]
        if phase == "downloading":
            current = _count_raw_videos()
            _dl_stats["session_downloaded"] = current - baseline
            _dl_stats["total_videos"] = current
            _dl_stats["total_archived"] = _count_archive()
        elif phase in {"parsing", "analyzing"}:
            _dl_stats.update(_read_analyze_stats())


async def _run_pipeline_subprocess(mode: str, url: str | None = None) -> None:
    global _current_process

    _pipeline_state["running"] = True
    _pipeline_state["mode"] = "single" if mode == "run-single" else "saved"
    _pipeline_state["last_run"] = datetime.now(timezone.utc).isoformat()
    _pipeline_state["phase"] = "idle"

    _log_buffer.clear()
    _append_log(f"=== started at {_pipeline_state['last_run']} ===")

    baseline = _count_raw_videos()
    _dl_stats.update(
        {
            "phase": "idle",
            "session_downloaded": 0,
            "total_archived": _count_archive(),
            "total_videos": baseline,
            "analyzed": _read_analyze_stats()["analyzed"],
        }
    )
    poll_task = asyncio.create_task(_poll_stats(baseline))

    try:
        process = await asyncio.create_subprocess_exec(
            *_build_cli_command(mode, url),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _current_process = process

        assert process.stdout is not None
        async for raw in process.stdout:
            _append_log(raw.decode(errors="replace").rstrip())

        await process.wait()

        if process.returncode < 0:
            _append_log("=== pipeline stopped by user ===")
        elif process.returncode != 0:
            _append_log(f"=== pipeline failed (exit code {process.returncode}) ===")
        else:
            _append_log(f"=== pipeline finished (mode={_pipeline_state['mode']}) ===")
    except Exception as exc:
        _append_log(f"=== error: {exc} ===")
    finally:
        _current_process = None
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        _dl_stats["total_archived"] = _count_archive()
        _dl_stats.update(_read_analyze_stats())
        _dl_stats["phase"] = "idle"
        _pipeline_state["running"] = False
        _pipeline_state["phase"] = "idle"


@app.post("/run")
async def run_saved_alias():
    if _pipeline_state["running"]:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline_subprocess("run-saved"))
    return {"status": "started", "mode": "saved"}


@app.post("/run/saved")
async def run_saved():
    if _pipeline_state["running"]:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline_subprocess("run-saved"))
    return {"status": "started", "mode": "saved"}


@app.post("/run/single")
async def run_single(payload: RunSingleRequest):
    if _pipeline_state["running"]:
        return {"status": "already_running"}
    asyncio.create_task(_run_pipeline_subprocess("run-single", payload.url))
    return {"status": "started", "mode": "single"}


@app.post("/stop")
async def stop():
    if not _pipeline_state["running"]:
        return {"status": "not_running"}
    process = _current_process
    if process is not None:
        try:
            process.terminate()
        except ProcessLookupError:
            pass
    return {"status": "stopping"}


@app.get("/status")
async def status():
    return {
        "running": _pipeline_state["running"],
        "last_run": _pipeline_state["last_run"],
        "mode": _pipeline_state["mode"],
        "phase": _pipeline_state["phase"],
    }


@app.get("/logs")
async def logs():
    return {
        "lines": list(_log_buffer),
        "running": _pipeline_state["running"],
        "last_run": _pipeline_state["last_run"],
    }


@app.get("/dl-stats")
async def dl_stats():
    return {**_dl_stats, "running": _pipeline_state["running"]}


@app.get("/lm-status")
async def lm_status():
    config = _runtime_config()
    llm_base_url = config.get("LLM_BASE_URL", "http://localhost:1234/v1")
    llm_model = config.get("LLM_MODEL")

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{llm_base_url}/models")
            models = response.json().get("data", [])
            detected_model = models[0]["id"] if models else llm_model
            connected = True
    except Exception as exc:
        logger.debug("lm-status: provider unreachable: %s", exc)
        detected_model = llm_model
        connected = False

    try:
        last_request_at = json.loads(LM_STATUS_FILE.read_text(encoding="utf-8")).get(
            "last_request_at"
        )
    except Exception:
        last_request_at = None

    return {
        "connected": connected,
        "url": llm_base_url,
        "model": detected_model,
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
            if not _pipeline_state["running"] and pos >= len(_log_buffer):
                yield "data: __done__\n\n"
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
