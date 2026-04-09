# Reelect

> Turn your saved Instagram Reels into a searchable, categorized knowledge base — running entirely on your machine.

<!-- screenshot: main viewer grid -->
![Reelect viewer](.github/assets/viewer.png)

---

## The problem

You save a reel. Then another. And another. A week later you can't find that cooking technique, that travel spot, that workout routine. Instagram's saved feed is a black hole — no search, no categories, no memory.

## What Reelect does

Reelect runs in the background and automatically:

1. **Downloads** new videos from your Instagram Saved collection
2. **Transcribes** the audio locally with Whisper (no API cost)
3. **Analyzes** frames and generates a summary, category, and tags using a local LLM via LM Studio
4. **Surfaces** everything in a clean web UI — searchable by content, filterable by category

Every video becomes a structured entry you can actually find later.

```
Instagram Saved
      ↓
  download.sh  →  saved_videos/raw/instagram/<user>/<id>.mp4
                                    +  <id>.transcript.txt  (Whisper cache)
                                    +  <id>.visual.txt      (LLM vision cache)
      ↓
  batch_analyze.py  →  saved_videos/meta/<id>.json
                        {transcript, visual_description, summary, category, tags}
      ↓
  viewer  →  http://localhost:8000
```

### Example metadata output

```json
{
  "id": "3762391109024717972",
  "filename": "saved_videos/raw/instagram/zaika_stories/3762391109024717972.mp4",
  "analyzed_at": "2026-04-08T12:26:37Z",
  "transcript": "Если хотите сэкономить 15 тысяч рублей...",
  "visual_description": "A person preparing a burnt basque cheesecake...",
  "summary": "Рецепт сан-себастьяна без специального оборудования — только венчик и духовка.",
  "category": "cooking",
  "tags": ["cheesecake", "выпечка", "рецепт", "десерт"]
}
```

---

## Tech stack

| | Tool |
|---|---|
| Video download | [gallery-dl](https://github.com/mikf/gallery-dl) |
| Audio transcription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — local, free |
| Frame extraction | ffmpeg |
| AI analysis | Local LLM via [LM Studio](https://lmstudio.ai) (vision model) |
| Web UI | React + FastAPI |
| Runtime | Docker |

Everything runs locally. No cloud APIs required.

---

## Getting started

### 1. Prerequisites

- **Docker & Docker Compose**
- **[LM Studio](https://lmstudio.ai)** with a vision-capable model loaded and server running on port `1234`
  - Recommended: `Qwen3.5-9B` or `Llama-3.2-11B-Vision-Instruct`
- A `cookies.txt` exported from your browser while logged into Instagram
  - Install [Cookie-Editor](https://cookie-editor.com/), open instagram.com, export in **Netscape** format

### 2. Install

```bash
git clone https://github.com/your-username/reelect.git
cd reelect
cp .env.example .env
```

### 3. Configure `.env`

```bash
INSTAGRAM_USERNAME=your_handle

LM_STUDIO_URL=http://host.docker.internal:1234/v1
LM_STUDIO_MODEL=qwen3.5-9b

CRON_SCHEDULE=0 */12 * * *
```

See `.env.example` for all options including token limits, concurrency, and native video input.

### 4. Run

```bash
# place cookies.txt in the project root, then:
docker compose build
docker compose up -d
```

- **Viewer** → [http://localhost:8000](http://localhost:8000)
- **Pipeline** runs automatically on the configured cron schedule
- Or trigger it manually from the UI with the **▶ Run pipeline** button

<!-- screenshot: pipeline panel with logs -->
![Pipeline panel](.github/assets/pipeline.png)

---

## UI

- **Grid view** — all videos with hover-to-play, category badge, summary, tags
- **Sidebar** — filter by category with counts
- **Search** — full-text across summaries, transcripts, and tags
- **Detail modal** — full transcript, visual description, metadata
- **Pipeline panel** — trigger runs and watch live logs from the browser

---

## Project structure

```
reelect/
├── Dockerfile               # pipeline container
├── docker-compose.yml
├── requirements.txt
├── download.sh              # fetches new videos via gallery-dl
├── analyze.py               # analyzes a single video (whisper + LLM)
├── batch_analyze.py         # parallel analysis of all pending videos
├── pipeline.sh              # orchestrator: download → analyze
├── trigger_server.py        # micro HTTP server for UI-triggered runs
├── entrypoint.sh            # starts cron + trigger server
├── .env.example
├── viewer/                  # web UI
│   ├── Dockerfile
│   ├── api/main.py          # FastAPI — videos API + pipeline proxy
│   └── frontend/            # React + Vite
└── saved_videos/            # runtime data, gitignored
    ├── raw/                 # downloaded mp4s (organized by instagram username)
    └── meta/                # json metadata per video
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `INSTAGRAM_USERNAME` | — | Your Instagram handle |
| `CRON_SCHEDULE` | `0 */12 * * *` | How often to run the pipeline |
| `LM_STUDIO_URL` | `http://host.docker.internal:1234/v1` | LM Studio endpoint |
| `LM_STUDIO_MODEL` | — | Exact model name from LM Studio |
| `LM_STUDIO_NATIVE_VIDEO` | `false` | Send full video instead of frames |
| `LM_STUDIO_THINKING_BUDGET` | `-1` | Reasoning token budget (-1 = unlimited) |
| `LM_STUDIO_MAX_TOKENS_VISUAL` | `4096` | Max tokens for frame/video description |
| `LM_STUDIO_MAX_TOKENS_METADATA` | `8192` | Max tokens for summary/category/tags |
| `MAX_WORKERS` | `3` | Parallel Whisper + ffmpeg workers |
| `LM_STUDIO_CONCURRENCY` | `1` | Parallel LLM requests |

---

## Notes

- Intermediate results (transcript, visual description) are **cached next to each video file** — if analysis fails midway, it resumes from where it stopped on the next run.
- `cookies.txt` and `.env` are gitignored and never committed.
- The Whisper model is baked into the Docker image — transcription works fully offline.
