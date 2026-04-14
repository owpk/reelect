#!/usr/bin/env bash

USERNAME="${INSTAGRAM_USERNAME:-}"
if [ -z "$USERNAME" ]; then
  echo "Ошибка: переменная INSTAGRAM_USERNAME не задана"
  exit 1
fi

DOWNLOAD_DIR="saved_videos/raw"
LOG_FILE="download_log.txt"
URL_CACHE_FILE="saved_videos/url_cache.txt"
STATUS_CACHE_FILE="saved_videos/status_cache.txt"

# Константы
MAX_RETRIES=1
RETRY_DELAY=5

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

# Функция получения списка URL из Instagram
get_all_urls() {
  log "INFO" "Получаю список URL из Instagram..."
  local temp_file=$(mktemp)

  # Используем --get-url для получения списка URL
  gallery-dl \
    --cookies "$COOKIES_FILE" \
    --get-url \
    "https://www.instagram.com/$USERNAME/saved/" \
    2>&1 | tee "$temp_file"

  local status=${PIPESTATUS[0]}

  if [ "$status" -ne 0 ]; then
    log "ERROR" "Не удалось получить список URL (код $status)"
    rm -f "$temp_file"
    return 1
  fi

  # Фильтруем только URL видео (mp4)
  grep -E '\.mp4' "$temp_file" >"$URL_CACHE_FILE"
  rm -f "$temp_file"

  local count=$(wc -l <"$URL_CACHE_FILE")
  log "INFO" "Найдено $count URL для загрузки"

  return 0
}

# Функция загрузки одного URL с повторными попытками
download_with_retry() {
  local url="$1"
  local attempt=1

  while [ $attempt -le $MAX_RETRIES ]; do
    log "INFO" "Попытка $attempt/$MAX_RETRIES: $url"

    gallery-dl \
      --cookies "$COOKIES_FILE" \
      -d "$DOWNLOAD_DIR" \
      --filter "extension == 'mp4'" \
      --retries 1 \
      --sleep 4-8 \
      "$url" \
      2>&1 | tee -a "$LOG_FILE"

    local status=${PIPESTATUS[0]}

    if [ "$status" -eq 0 ]; then
      log "INFO" "Успешно загружено: $url"
      echo "$url|DONE" >>"$STATUS_CACHE_FILE"
      return 0
    else
      log "WARN" "Ошибка при загрузке (код $status): $url"
      if [ $attempt -lt $MAX_RETRIES ]; then
        log "INFO" "Жду $RETRY_DELAY секунд перед следующей попыткой..."
        sleep $RETRY_DELAY
      fi
    fi

    ((attempt++))
  done

  log "ERROR" "Не удалось загрузить после $MAX_RETRIES попыток: $url"
  echo "$url|FAILED" >>"$STATUS_CACHE_FILE"
  return 1
}

# Проверка/получение кэша URL
if [ -f "$URL_CACHE_FILE" ]; then
  log "INFO" "Найден существующий кэш URL: $URL_CACHE_FILE"

  # Проверяем, актуален ли кэш (не старше 24 часов)
  cache_age=$(($(date +%s) - $(stat -f%m "$URL_CACHE_FILE" 2>/dev/null || stat -c%Y "$URL_CACHE_FILE" 2>/dev/null)))
  max_age=$((24 * 60 * 60)) # 24 часа

  if [ $cache_age -gt $max_age ]; then
    log "WARN" "Кэш устарел (>24 часов), обновляю..."
    rm -f "$URL_CACHE_FILE" "$STATUS_CACHE_FILE"
  fi
fi

# Получаем список URL если нет кэша
if [ ! -f "$URL_CACHE_FILE" ]; then
  if ! get_all_urls; then
    log "ERROR" "Не удалось получить список URL. Завершаю."
    exit 1
  fi
fi

# Получаем список URL
urls=()
while IFS= read -r url; do
  [ -n "$url" ] && urls+=("$url")
done <"$URL_CACHE_FILE"

total=${#urls[@]}
log "INFO" "Всего URL в кэше: $total"

# Обработка каждого URL
successful=0
failed=0
skipped=0

for url in "${urls[@]}"; do
  # Проверяем, не был ли уже обработан этот URL
  if [ -f "$STATUS_CACHE_FILE" ]; then
    if grep -q "^$url|" "$STATUS_CACHE_FILE"; then
      status=$(grep "^$url|" "$STATUS_CACHE_FILE" | cut -d'|' -f2)
      if [ "$status" = "DONE" ]; then
        log "INFO" "Пропускаю (уже загружено): $url"
        ((skipped++))
        continue
      elif [ "$status" = "FAILED" ]; then
        log "INFO" "Пропускаю (предыдущая неудача): $url"
        ((skipped++))
        continue
      fi
    fi
  fi

  # Скачиваем с ретраями
  if download_with_retry "$url"; then
    ((successful++))
  else
    ((failed++))
  fi
done

# Итоги
log "INFO" "========================================="
log "INFO" "Скачивание завершено!"
log "INFO" "Успешно: $successful"
log "INFO" "Пропущено: $skipped"
log "INFO" "Неудачи: $failed"
log "INFO" "========================================="

if [ $failed -gt 0 ]; then
  log "WARN" "Есть неудачные загрузки. Проверь лог для деталей."
fi
