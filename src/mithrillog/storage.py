from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .utils.time import get_timezone, minute_bucket_path


@dataclass
class BucketRecord:
    path: Path
    count: int
    samples: dict[str, list[dict[str, Any]]]


class JournalWriter:
    def __init__(self, base_dir: Path, timezone_name: str = "UTC") -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.bucket_timezone = get_timezone(timezone_name)

    def append(self, event: dict[str, Any]) -> Path:
        timestamp = event["timestamp"]
        bucket = minute_bucket_path(str(self.base_dir), timestamp, tz=self.bucket_timezone)
        path = Path(bucket)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, separators=(",", ":"), default=str)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return path

    def write_summary(self, path: Path, summary: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2, default=str)

    def write_metadata(self, path: Path, metadata: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(metadata, handle, indent=2, default=str)

    def list_buckets(self, start: Path) -> Iterable[Path]:
        for file in sorted(start.rglob("*.ndjson")):
            yield file

