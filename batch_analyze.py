#!/usr/bin/env python3
"""
batch_analyze.py

Finds all unprocessed videos in saved_videos/raw/ (recursively)
and analyzes them in parallel with a concurrency limit.
"""

import logging
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import load_env
from analyze import analyze

RAW_DIR = Path("saved_videos/raw")
META_DIR = Path("saved_videos/meta")
_config = load_env(".env")
MAX_WORKERS = int(_config.get("MAX_WORKERS", "3"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("download_log.txt", encoding="utf-8", mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def find_pending(raw_dir: Path, meta_dir: Path) -> list[Path]:
    all_videos = sorted(raw_dir.rglob("*.mp4"))
    return [v for v in all_videos if not (meta_dir / f"{v.stem}.json").exists()]


def main():
    META_DIR.mkdir(parents=True, exist_ok=True)

    pending = find_pending(RAW_DIR, META_DIR)
    if not pending:
        logger.info("No new videos to analyze.")
        return

    logger.info(f"Found {len(pending)} video(s) to analyze (max_workers={MAX_WORKERS})")

    done, failed = 0, 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(analyze, v): v for v in pending}
        for future in as_completed(futures):
            video = futures[future]
            try:
                future.result()
                done += 1
            except Exception as e:
                logger.error(f"[error] {video.name}: {e}")
                failed += 1

    logger.info(f"Batch done. analyzed={done} failed={failed}")


if __name__ == "__main__":
    main()
