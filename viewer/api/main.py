import os
import json
import httpx
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

PIPELINE_URL = os.environ.get("PIPELINE_URL", "http://pipeline:8001")

BASE_DIR = Path(os.environ.get("BASE_DIR", "/app"))
META_DIR = BASE_DIR / "saved_videos/meta"
STATIC_DIR = Path("/app/static")

app = FastAPI()


@app.get("/api/videos")
def list_videos():
    if not META_DIR.exists():
        return []
    videos = []
    for meta_file in sorted(META_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(meta_file.read_text())
            video_path = BASE_DIR / data["filename"]
            data["has_video"] = video_path.exists()
            videos.append(data)
        except Exception:
            continue
    return videos


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: str):
    meta_file = META_DIR / f"{video_id}.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    data = json.loads(meta_file.read_text())
    path = BASE_DIR / data["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4")


@app.post("/api/pipeline/run")
async def pipeline_run():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{PIPELINE_URL}/run", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")


@app.get("/api/pipeline/status")
async def pipeline_status():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PIPELINE_URL}/status", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")


@app.get("/api/pipeline/logs")
async def pipeline_logs():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PIPELINE_URL}/logs", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")


@app.get("/api/lm/status")
async def lm_status():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PIPELINE_URL}/lm-status", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")


@app.get("/api/pipeline/dl-stats")
async def pipeline_dl_stats():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PIPELINE_URL}/dl-stats", timeout=5)
            return r.json()
    except Exception:
        raise HTTPException(status_code=503, detail="Pipeline server unavailable")


@app.get("/api/pipeline/stream")
async def pipeline_stream():
    async def generate():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", f"{PIPELINE_URL}/stream") as r:
                async for line in r.aiter_lines():
                    if line:
                        yield f"{line}\n\n"
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
