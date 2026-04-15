#!/bin/bash
set -e

CRON_SCHEDULE="$(python3 -c 'from config import load_env; print(load_env(".env").get("CRON_SCHEDULE", "0 * * * *"))')"

# Write crontab — pipe output to container stdout/stderr
echo "$CRON_SCHEDULE cd /app && python3 -m reelect_pipeline.cli run-saved >> /proc/1/fd/1 2>> /proc/1/fd/2" | crontab -

echo "$(date '+%Y-%m-%d %H:%M:%S') | INFO | cron started with schedule: $CRON_SCHEDULE"

uvicorn trigger_server:app --host 0.0.0.0 --port 8001 &

exec cron -f
