#!/usr/bin/env python3
"""
Debug script to check bucket status and identify missing metadata files.
Run this when hourly summaries show 0 events but logs should exist.
"""

import json
import logging
from pathlib import Path

from mithrillog.config import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_bucket_status():
    """Check the status of ingestion buckets and metadata files."""
    settings = Settings.load(Path("configs/default.yaml"))
    bucket_dir = Path(settings.ingest.bucket_dir)

    logger.info(f"Checking bucket directory: {bucket_dir}")

    if not bucket_dir.exists():
        logger.error(f"Bucket directory does not exist: {bucket_dir}")
        return

    # Find all NDJSON files
    ndjson_files = list(bucket_dir.rglob("*.ndjson"))
    meta_files = list(bucket_dir.rglob("*.meta.json"))

    logger.info(f"Found {len(ndjson_files)} NDJSON files")
    logger.info(f"Found {len(meta_files)} metadata files")

    # Check for NDJSON files without metadata
    missing_meta = []
    for ndjson_file in ndjson_files:
        meta_file = ndjson_file.with_suffix(".meta.json")
        if not meta_file.exists():
            missing_meta.append(ndjson_file)
            logger.warning(f"Missing metadata for: {ndjson_file}")

    if missing_meta:
        logger.error(f"Found {len(missing_meta)} buckets without metadata!")
        logger.info("These buckets won't be included in hourly summaries.")
        logger.info("Solution: Restart the orchestrator container to flush current buckets.")

        # Show some sample content from missing buckets
        for ndjson_file in missing_meta[:3]:  # Show first 3
            try:
                with ndjson_file.open("r", encoding="utf-8") as f:
                    lines = f.readlines()[:5]  # First 5 lines
                    logger.info(f"Sample content from {ndjson_file.name}:")
                    for line in lines:
                        try:
                            event = json.loads(line.strip())
                            logger.info(f"  - {event.get('timestamp', 'unknown')} {event.get('host', 'unknown')} {event.get('message', '')[:50]}...")
                        except json.JSONDecodeError:
                            logger.info(f"  - {line.strip()[:50]}...")
            except Exception as e:
                logger.error(f"Error reading {ndjson_file}: {e}")
    else:
        logger.info("All buckets have metadata files.")

    # Check recent metadata files
    if meta_files:
        logger.info("Recent metadata files:")
        sorted_meta = sorted(meta_files, key=lambda p: p.stat().st_mtime, reverse=True)
        for meta_file in sorted_meta[:5]:
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                    total_events = meta.get("total_events", 0)
                    unique_events = meta.get("unique_events", 0)
                    bucket_time = meta.get("bucket", "unknown")
                    logger.info(f"  {meta_file.name}: {total_events} events ({unique_events} unique) - {bucket_time}")
            except Exception as e:
                logger.error(f"Error reading {meta_file}: {e}")


if __name__ == "__main__":
    check_bucket_status()
