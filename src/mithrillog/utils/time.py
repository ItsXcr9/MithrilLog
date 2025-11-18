from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_timezone(name: str | None) -> ZoneInfo:
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def floor_to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def ensure_timezone(dt: datetime, tz: ZoneInfo) -> datetime:
    """Ensure datetime is in the specified timezone, converting from UTC if naive."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _ensure_timezone(dt: datetime, tz: ZoneInfo) -> datetime:
    """Internal alias for backward compatibility."""
    return ensure_timezone(dt, tz)


def minute_bucket_path(base_dir: str | bytes, dt: datetime, tz: ZoneInfo | None = None) -> str:
    tz = tz or ZoneInfo("UTC")
    localized = _ensure_timezone(dt, tz)
    rounded = floor_to_minute(localized)
    return (
        f"{base_dir}/{rounded.year:04d}/{rounded.month:02d}/"
        f"{rounded.day:02d}/{rounded.hour:02d}/{rounded.minute:02d}.ndjson"
    )

