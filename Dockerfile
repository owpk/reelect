FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    cron \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download Whisper base model so first run doesn't need internet
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

COPY config.py entrypoint.sh trigger_server.py ./
COPY reelect_pipeline ./reelect_pipeline
RUN chmod +x entrypoint.sh

# /cookies/cookies.txt  — mounted read-only at runtime
# /app/saved_videos     — mounted read-write at runtime
ENTRYPOINT ["./entrypoint.sh"]
