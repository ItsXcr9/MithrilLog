#!/usr/bin/env python3
"""
Rebuild missing bucket metadata files so hourly summaries can see events.

Usage: python scripts/rebuild_bucket_metadata.py [--config configs/default.yaml]
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from mithrillog.config import Settings
except Exception:  # pragma: no cover - fallback when deps missing
    Settings = None  # type: ignore[assignment]
    import yaml
else:
    import yaml

HAS_MODEL_VALIDATE = bool(Settings and hasattr(Settings, "model_validate"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.yaml"),
        help="Path to settings file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild metadata even if file already exists",
    )
    return parser.parse_args()


def bucket_time_from_path(path: Path) -> datetime:
    year, month, day, hour, minute_file = path.parts[-5:]
    minute = minute_file.split(".")[0]
    return datetime(
        int(year),
        int(month),
        int(day),
        int(hour),
        int(minute),
        tzinfo=timezone.utc,
    )


def rebuild_meta(ndjson_path: Path, force: bool = False) -> bool:
    meta_path = ndjson_path.with_suffix(".meta.json")
    if meta_path.exists() and not force:
        return False

    events: list[dict] = []
    with ndjson_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not events:
        logger.warning("No events found in %s", ndjson_path)
        return False

    severity_counts: Counter[str] = Counter()
    host_counts: Counter[str] = Counter()
    app_counts: Counter[str] = Counter()
    pattern_totals: dict[str, int] = defaultdict(int)
    highlights: list[dict] = []
    total_events = 0

    for event in events:
        occ = int(event.get("occurrences") or 1)
        pattern = event.get("pattern_id") or event.get("pattern") or "unknown"
        pattern_totals[pattern] += occ
        severity = event.get("severity", "info")
        host = event.get("host", "unknown")
        app = event.get("app", "-")
        severity_counts[severity] += occ
        host_counts[host] += occ
        app_counts[app] += occ
        total_events += occ
        event["occurrences"] = occ
        highlights.append(event)

    bucket_meta = {
        "bucket": bucket_time_from_path(ndjson_path).isoformat(),
        "patterns": dict(pattern_totals),
        "severity": dict(severity_counts),
        "hosts": dict(host_counts),
        "apps": dict(app_counts),
        "total_events": total_events,
        "unique_events": len(events),
        "highlights": sorted(highlights, key=lambda item: item.get("occurrences", 1), reverse=True)[
            :50
        ],
    }

    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with meta_path.open("w", encoding="utf-8") as handle:
        json.dump(bucket_meta, handle, indent=2, default=str)
    logger.info("Rebuilt %s", meta_path)
    return True


def load_bucket_dir(config_path: Path) -> Path:
    if Settings is not None and HAS_MODEL_VALIDATE:
        settings = Settings.load(config_path)
        return Path(settings.ingest.bucket_dir)

    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    bucket_dir = (
        data.get("ingest", {}).get("bucket_dir")
        or data.get("ingest", {}).get("bucketDir")
    )
    if not bucket_dir:
        raise RuntimeError("bucket_dir missing in config")
    return Path(bucket_dir)


def main() -> None:
    args = parse_args()
    bucket_dir = load_bucket_dir(args.config)

    rebuilt = 0
    checked = 0

    for ndjson_path in sorted(bucket_dir.rglob("*.ndjson")):
        checked += 1
        rebuilt += rebuild_meta(ndjson_path, force=args.force) or 0

    logger.info("Checked %s buckets, rebuilt %s metadata files", checked, rebuilt)


if __name__ == "__main__":
    main()


