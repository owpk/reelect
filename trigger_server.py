#!/usr/bin/env python3
"""
Micro HTTP server inside the pipeline container.
Allows triggering pipeline.sh via HTTP and streaming its logs via SSE.
"""

import asyncio
import os
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

COOKIES_FILE = os.environ.get("COOKIES_FILE", "/cookies/cookies.txt")
PIPELINE_CMD = ["/app/pipeline.sh", COOKIES_FILE]
MAX_LOG_LINES = 2000

app = FastAPI()

_running = False
_last_run: str | None = None
_log_buffer: list[str] = []


def _append_log(line: str) -> None:
    _log_buffer.append(line)
    if len(_log_buffer) > MAX_LOG_LINES:
        _log_buffer.pop(0)


async def _run_pipeline() -> None:
    global _running, _last_run
    _running = True
    _last_run = datetime.now(timezone.utc).isoformat()
    _log_buffer.clear()
    _append_log(f"=== started at {_last_run} ===")

    try:
        process = await asyncio.create_subprocess_exec(
            *PIPELINE_CMD,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for raw in process.stdout:
            _append_log(raw.decode(errors="replace").rstrip())
        await process.wait()
        _append_log(f"=== finished (exit code {process.returncode}) ===")
    except Exception as e:
        _append_log(f"=== error: {e} ===")
    finally:
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
