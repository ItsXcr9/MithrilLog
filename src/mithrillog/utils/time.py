from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def minute_bucket_path(base_dir: str | bytes, dt: datetime) -> str:
    rounded = floor_to_minute(dt)
    return (
        f"{base_dir}/{rounded.year:04d}/{rounded.month:02d}/"
        f"{rounded.day:02d}/{rounded.hour:02d}/{rounded.minute:02d}.ndjson"
    )

