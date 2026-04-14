# Project Memory — reelect

> Автоматически загружено из Obsidian vault при старте сессии.
> Последние сессии по этому проекту:



---
### 📄 2026-04-14-reelect-14-36.md
---
date: 2026-04-14
time: 14-36
project: reelect
tags: [claude-session, reelect]
related: []
---

# reelect — 2026-04-14 14-36

## Что было сделано
Готово. Итоговые изменения:

**`download.sh`** — 173 строки → 42. Один `gallery-dl` вызов с `--download-archive saved_videos/downloaded_archive.db`. Audio+video склеивается автоматически через ffmpeg внутри gallery-dl.

**`trigger_server.py`** — убраны `url_cache`, `status_cache`, `retry-failed`. Прогресс теперь через:
- `_count_raw_videos()` — количество mp4 в `raw/` (до и после = delta за сессию)
- `_count_archive()` — `SELECT COUNT(*) FROM archive` (SQLite gallery-dl)

**Сайдбар теперь показывает:**
```
Загрузка
  Скачано:   5 новых    ← зелёный во время downloading
  В архиве:  92

Анализ
  Проанализировано: 8 / 12   ← зелёный во время analyzing
```

## Git
- Branch: main
- Последний коммит: b1d202c refactor: use mp4 count + SQLite archive for stats, remove retry-failed
- Изменённые файлы:
- CLAUDE.md

## Связанные проекты


## Предыдущая сессия
[[claude-sessions/2026-04-14-reelect-12-02]]

## TODO на следующую сессию
- [ ] 

---
*← [[claude-sessions/2026-04-14-reelect-12-02]]*


---
### 📄 2026-04-14-reelect-12-02.md
---
date: 2026-04-14
time: 12-02
project: reelect
tags: [claude-session, reelect]
related: []
---

# reelect — 2026-04-14 12-02

## Что было сделано
Да, это два отдельных потока — **видео без звука** и **аудио без видео**. Instagram использует DASH-стриминг для хранения их раздельно. gallery-dl при обычном скачивании (без `--get-url`) сам скачивает оба потока и склеивает их через ffmpeg автоматически.

Проблема с текущим подходом глубже: мы используем `--get-url` чтобы получить список URL для трекинга прогресса, а потом передаём эти CDN-ссылки обратно в gallery-dl поштучно — но gallery-dl тогда качает только видео-поток без знания о парном аудио. Результат: **видео без звука**.

Нужно переделать подход. Вместо CDN URL использовать оригинальные URL страниц Instagram:

```
gallery-dl --get-url https://instagram.com/user/saved/
→ выдаёт CDN URLs (неудобно, пары)

Правильно:
gallery-dl --dump-json https://instagram.com/user/saved/
→ выдаёт метаданные с post_url каждого рила
```

Или ещё проще — вообще отказаться от get-url и качать gallery-dl'ом нормально с `--download-archive` (SQLite), а прогресс считать по файлам в `saved_videos/raw/`.

Хочешь переделать `download.sh` на нормальный флоу с архивом? Тогда:
- gallery-dl сам склеивает аудио+видео
- прогресс = считаем mp4 файлы в `raw/` пока идёт скачивание
- total = берём из `--dump-json` или просто не показываем (N скачано, total неизвестен до конца)

## Git
- Branch: main
- Последний коммит: 2e11898 fix: anchor grep to ^https?:// to skip gallery-dl audio stream lines (| https://...)
- Изменённые файлы:
- CLAUDE.md
- download.sh

## Связанные проекты


## Предыдущая сессия
[[claude-sessions/2026-04-14-reelect-11-16]]

## TODO на следующую сессию
- [ ] 

---
*← [[claude-sessions/2026-04-14-reelect-11-16]]*


---
### 📄 2026-04-14-reelect-11-16.md
---
date: 2026-04-14
time: 11-16
project: reelect
tags: [claude-session, reelect]
related: []
---

# reelect — 2026-04-14 11-16

## Что было сделано
Снова удали `url_cache.txt` и запусти. Теперь `grep -E '^https?://.*\.mp4'` берёт только строки начинающиеся с `http` — аудио-строки вида `| https://...` отфильтруются.

## Git
- Branch: main
- Последний коммит: 2e11898 fix: anchor grep to ^https?:// to skip gallery-dl audio stream lines (| https://...)
- Изменённые файлы:
- CLAUDE.md

## Связанные проекты


## Предыдущая сессия
[[claude-sessions/2026-04-14-reelect-11-15]]

## TODO на следующую сессию
- [ ] 

---
*← [[claude-sessions/2026-04-14-reelect-11-15]]*


---
## Инструкция
Используй эти заметки как контекст. Обрати особое внимание на TODO
из последней сессии — спроси пользователя хочет ли он продолжить с них.
