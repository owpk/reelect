from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import json

META_DIR = Path("/app/saved_videos/meta")
RAW_DIR = Path("/app/saved_videos/raw")
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
            video_path = RAW_DIR / f"{data['id']}.mp4"
            data["has_video"] = video_path.exists()
            videos.append(data)
        except Exception:
            continue
    return videos


@app.get("/api/videos/{video_id}/stream")
def stream_video(video_id: str):
    path = RAW_DIR / f"{video_id}.mp4"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(path, media_type="video/mp4")


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
