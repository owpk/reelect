# Instagram Saved Reels Downloader & Analyzer

A self-hosted pipeline that automatically downloads your saved Instagram Reels and uses AI to transcribe, describe, and categorize each video — so you can search and organize your saved content by topic.

## What it does

```
Instagram Saved →  download.sh  →  saved_videos/raw/*.mp4
                                          ↓
                   analyze.py   →  saved_videos/meta/*.json
                                   {transcript, summary, category, tags}
```

1. **Download** — `download.sh` fetches only new videos from your Instagram Saved collection using [gallery-dl](https://github.com/mikf/gallery-dl), skipping anything already downloaded.
2. **Analyze** — `analyze.py` processes each new video:
   - Extracts audio → transcribes with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (runs locally, no API cost)
   - Samples frames → describes visually with Claude
   - Combines both → Claude generates a summary, category, and tags
3. **Orchestrate** — `pipeline.sh` runs both steps in sequence. Point a cron job at it and forget about it.

### Example output (`saved_videos/meta/<id>.json`)

```json
{
  "id": "3581234567890",
  "filename": "saved_videos/raw/3581234567890.mp4",
  "analyzed_at": "2026-04-08T12:00:00Z",
  "transcript": "Today I'm making a classic carbonara...",
  "visual_description": "A person cooking pasta in a pan on a stovetop...",
  "summary": "A quick tutorial on making authentic Roman carbonara. The creator shows the technique for emulsifying eggs without scrambling them.",
  "category": "cooking",
  "tags": ["pasta", "italian", "carbonara", "recipe", "tutorial"]
}
```

## Tech stack

| Component | Tool |
|---|---|
| Video download | [gallery-dl](https://github.com/mikf/gallery-dl) |
| Audio transcription | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (base model, CPU) |
| Frame extraction | ffmpeg |
| AI analysis | [Claude API](https://www.anthropic.com/) (claude-opus-4-6) |
| Runtime | Docker |

## Getting started

### Prerequisites

- Docker & Docker Compose
- An Anthropic API key → [console.anthropic.com](https://console.anthropic.com)
- A `cookies.txt` file exported from your browser while logged into Instagram (Netscape format)

> To export cookies: install the [Cookie-Editor](https://cookie-editor.com/) extension, open instagram.com, and export in **Netscape** format.

### Setup

```bash
git clone https://github.com/your-username/instagram-dw.git
cd instagram-dw

cp .env.example .env
# fill in your values
```

**.env**
```
ANTHROPIC_API_KEY=sk-ant-...
INSTAGRAM_USERNAME=your_instagram_handle
```

### Run

```bash
# place your cookies.txt in the project root, then:
docker compose build
docker compose run --rm pipeline
```

Downloaded videos land in `saved_videos/raw/`, metadata in `saved_videos/meta/`.

### Automate with cron

Run the pipeline every 12 hours:

```bash
crontab -e
```

```
0 */12 * * * cd /path/to/instagram-dw && docker compose run --rm pipeline >> cron.log 2>&1
```

## Project structure

```
instagram-dw/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── download.sh          # step 1: download new videos via gallery-dl
├── analyze.py           # step 2: transcribe + describe + categorize one video
├── pipeline.sh          # orchestrator: runs download → analyze loop
├── .env.example
└── saved_videos/        # created at runtime, gitignored
    ├── raw/             # mp4 files
    ├── meta/            # json metadata per video
    └── downloaded_archive.txt
```

Each script can be run independently:

```bash
# download only
./download.sh cookies.txt

# analyze a specific video
python analyze.py saved_videos/raw/some_video.mp4

# full pipeline
./pipeline.sh cookies.txt
```

## Notes

- `downloaded_archive.txt` tracks what has already been downloaded — safe to run the pipeline repeatedly.
- The Whisper `base` model is baked into the Docker image (~150 MB) so no internet is needed for transcription.
- `cookies.txt` and `.env` are gitignored and mounted as Docker volumes — never committed.
