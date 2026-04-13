#!/usr/bin/env bash

USERNAME="${INSTAGRAM_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  echo "Ошибка: переменная INSTAGRAM_USERNAME не задана"
  exit 1
fi
DOWNLOAD_DIR="saved_videos/raw"
ARCHIVE_FILE="saved_videos/downloaded_archive.txt"
LOG_FILE="download_log.txt"

mkdir -p "$DOWNLOAD_DIR" "saved_videos/meta"

log() {
  local level="$1"
  local msg="$2"
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $level | $msg" | tee -a "$LOG_FILE"
}

COOKIES_FILE="${1:-}"
if [ -z "$COOKIES_FILE" ]; then
  echo "Использование: ./download.sh <путь к cookies.txt>"
  exit 1
fi
if [ ! -f "$COOKIES_FILE" ]; then
  echo "Файл не найден: $COOKIES_FILE"
  exit 1
fi

log "INFO" "Начинаю скачивание сохранённых reels для @$USERNAME..."

gallery-dl \
  --cookies "$COOKIES_FILE" \
  --download-archive "$ARCHIVE_FILE" \
  -d "$DOWNLOAD_DIR" \
  --filter "extension == 'mp4'" \
  --sleep 4-8 \
  --retries 2 \
  "https://www.instagram.com/$USERNAME/saved/" \
  2>&1 | tee -a "$LOG_FILE"

STATUS=${PIPESTATUS[0]}

if [ "$STATUS" -eq 0 ]; then
  log "INFO" "Готово! Новые видео в папке: $DOWNLOAD_DIR"
else
  log "ERROR" "gallery-dl завершился с ошибкой (код $STATUS)"
  exit "$STATUS"
fi
