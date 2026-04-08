#!/bin/bash
set -e

CRON_SCHEDULE="${CRON_SCHEDULE:-0 */12 * * *}"

# cron runs in a clean environment — export current env vars so pipeline.sh sees them
printenv | grep -v "^_=" > /etc/environment

# Write crontab — pipe output to container stdout/stderr
echo "$CRON_SCHEDULE . /etc/environment; /app/pipeline.sh /cookies/cookies.txt >> /proc/1/fd/1 2>> /proc/1/fd/2" | crontab -

echo "$(date '+%Y-%m-%d %H:%M:%S') | INFO | cron started with schedule: $CRON_SCHEDULE"

exec cron -f
