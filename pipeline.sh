#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
RAW_DIR="$SCRIPT_DIR/saved_videos/raw"
META_DIR="$SCRIPT_DIR/saved_videos/meta"
LOG_FILE="$SCRIPT_DIR/download_log.txt"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $1 | $2" | tee -a "$LOG_FILE"
}

COOKIES_FILE="${1:-}"
if [ -z "$COOKIES_FILE" ]; then
  echo "Usage: ./pipeline.sh <cookies.txt>"
  exit 1
fi

cd "$SCRIPT_DIR"

# Step 1: download new videos
log "INFO" "=== pipeline start ==="
bash "$SCRIPT_DIR/download.sh" "$COOKIES_FILE"

# Step 2: analyze videos that don't have metadata yet
mkdir -p "$META_DIR"
NEW=0
for video in "$RAW_DIR"/*.mp4; do
  [ -f "$video" ] || continue
  stem="$(basename "$video" .mp4)"
  if [ ! -f "$META_DIR/$stem.json" ]; then
    log "INFO" "analyzing: $(basename "$video")"
    "$VENV_PYTHON" "$SCRIPT_DIR/analyze.py" "$video"
    NEW=$((NEW + 1))
  fi
done

log "INFO" "=== pipeline done. analyzed: $NEW video(s) ==="
