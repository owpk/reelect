#!/usr/bin/env bash

USERNAME="${INSTAGRAM_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  echo "Ошибка: переменная INSTAGRAM_USERNAME не задана"
  exit 1
fi

COOKIES_FILE="${1:-}"
if [ -z "$COOKIES_FILE" ]; then
  echo "Использование: ./download.sh <путь к cookies.txt>"
  exit 1
fi
if [ ! -f "$COOKIES_FILE" ]; then
  echo "Файл не найден: $COOKIES_FILE"
  exit 1
fi

DOWNLOAD_DIR="saved_videos/raw"
ARCHIVE_FILE="saved_videos/downloaded_archive.db"
LOG_FILE="download_log.txt"

mkdir -p "$DOWNLOAD_DIR" "saved_videos/meta"

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') | $1 | $2" | tee -a "$LOG_FILE"
}

log "INFO" "Начинаю скачивание сохранённых reels для @$USERNAME..."

gallery-dl \
  --cookies "$COOKIES_FILE" \
  --download-archive "$ARCHIVE_FILE" \
  -d "$DOWNLOAD_DIR" \
  --filter "extension == 'mp4'" \
  --retries 3 \
  --sleep 4-8 \
  "https://www.instagram.com/$USERNAME/saved/" \
  2>&1 | tee -a "$LOG_FILE"

STATUS=$?
log "INFO" "gallery-dl завершён с кодом $STATUS"
exit $STATUS
