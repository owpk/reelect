#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
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

log "INFO" "=== pipeline start ==="

bash "$SCRIPT_DIR/download.sh" "$COOKIES_FILE"

python3 "$SCRIPT_DIR/batch_analyze.py"

log "INFO" "=== pipeline done ==="
