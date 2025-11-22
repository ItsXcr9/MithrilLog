from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
from functools import lru_cache
from time import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from mithrillog.config import Settings, default_settings

# Try to use orjson for faster JSON parsing, fallback to standard json
try:
    import orjson
    def fast_json_loads(s: str):
        return orjson.loads(s)
except ImportError:
    fast_json_loads = json.loads

# Simple cache with TTL
_cache = {}
_cache_times = {}

app = FastAPI(title="MithrilLog API")

# Add CORS middleware
# Add CORS middleware
# Load settings early to get CORS config
settings = default_settings
allowed_origins = settings.cors.allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex="https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

ERROR_SEVERITIES = {"emerg", "alert", "crit", "err"}
SEVERITY_ORDER = ["emerg", "alert", "crit", "err", "warn", "notice", "info", "debug"]


def _list_reports(base: Path, limit: int) -> List[dict]:
    if not base.exists():
        return []
    reports = []
    for path in sorted(base.rglob("*.json"), reverse=True):
        with path.open("r", encoding="utf-8") as handle:
            reports.append(json.load(handle))
        if len(reports) >= limit:
            break
    return reports


def _hourly_reports(limit: int) -> List[dict]:
    settings = default_settings
    base = Path(settings.summary.report_dir) / "hourly"
    return _list_reports(base, limit)


def _error_insights(limit: int) -> List[dict]:
    insights: List[dict] = []
    reports = _hourly_reports(limit * 3)
    for report in reports:
        stats = report.get("stats") or {}
        severity_counts = stats.get("by_severity") or {}
        error_total = sum(
            count for sev, count in severity_counts.items() if sev in ERROR_SEVERITIES
        )
        if error_total == 0:
            continue
        highlight_errors = [
            {
                "severity": item.get("severity", "info"),
                "host": item.get("host", "unknown"),
                "app": item.get("app", "-"),
                "occurrences": item.get("occurrences", 1),
                "message": item.get("message", ""),
                "sources": item.get("source_hosts")
                or item.get("sources")
                or {item.get("host", "unknown"): item.get("occurrences", 1)},
            }
            for item in report.get("highlights", [])
            if item.get("severity") in ERROR_SEVERITIES
        ]
        host_counts: Counter[str] = Counter()
        app_counts: Counter[str] = Counter()
        for highlight in highlight_errors:
            for host, count in (highlight["sources"] or {}).items():
                host_counts[host] += count
            app_counts[highlight["app"]] += highlight.get("occurrences", 1)
        severity_breakdown = [
            {"severity": sev, "count": severity_counts.get(sev, 0)}
            for sev in SEVERITY_ORDER
            if sev in ERROR_SEVERITIES and severity_counts.get(sev)
        ]
        insights.append(
            {
                "window_start": report.get("window_start"),
                "window_end": report.get("window_end"),
                "total_errors": error_total,
                "severity_breakdown": severity_breakdown,
                "top_hosts": [
                    {"host": host, "count": count}
                    for host, count in host_counts.most_common(5)
                ],
                "top_apps": [
                    {"app": app, "count": count}
                    for app, count in app_counts.most_common(3)
                ],
                "highlights": highlight_errors[:4],
            }
        )
        if len(insights) >= limit:
            break
    return insights


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    # Load config at runtime from mounted volume
    config_path = Path(__file__).parent.parent / "configs" / "default.yaml"
    if config_path.exists():
        settings = Settings.load(config_path)
    else:
        settings = default_settings
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": settings.web.title},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/summaries/hourly")
def hourly_summaries(limit: int = Query(5, ge=1, le=48)) -> dict:
    cache_key = f"hourly_{limit}"
    now = time()
    if cache_key in _cache and (now - _cache_times.get(cache_key, 0)) < 300:
        return _cache[cache_key]
    
    result = {"items": _hourly_reports(limit)}
    _cache[cache_key] = result
    _cache_times[cache_key] = now
    return result


@app.get("/summaries/daily")
def daily_summaries(limit: int = Query(7, ge=1, le=14)) -> dict:
    cache_key = f"daily_{limit}"
    now = time()
    if cache_key in _cache and (now - _cache_times.get(cache_key, 0)) < 300:
        return _cache[cache_key]
    
    settings = default_settings
    base = Path(settings.summary.report_dir) / "daily"
    result = {"items": _list_reports(base, limit)}
    _cache[cache_key] = result
    _cache_times[cache_key] = now
    return result


@app.get("/summaries/trend")
def trend_summaries(limit: int = Query(7, ge=1, le=14)) -> dict:
    cache_key = f"trend_{limit}"
    now = time()
    if cache_key in _cache and (now - _cache_times.get(cache_key, 0)) < 300:
        return _cache[cache_key]
    
    settings = default_settings
    base = Path(settings.summary.report_dir) / "trend"
    result = {"items": _list_reports(base, limit)}
    _cache[cache_key] = result
    _cache_times[cache_key] = now
    return result


@app.get("/insights/errors")
def error_insights(limit: int = Query(8, ge=1, le=48)) -> dict:
    cache_key = f"errors_{limit}"
    now = time()
    if cache_key in _cache and (now - _cache_times.get(cache_key, 0)) < 300:
        return _cache[cache_key]
    
    result = {"items": _error_insights(limit)}
    _cache[cache_key] = result
    _cache_times[cache_key] = now
    return result


def _get_hourly_log_counts(days: int = 30) -> List[dict]:
    """Get hourly log counts for the past N days from hourly summary reports."""
    settings = default_settings
    report_dir = Path(settings.summary.report_dir) / "hourly"
    if not report_dir.exists():
        return []
    
    from mithrillog.utils.time import get_timezone
    
    local_tz = get_timezone(settings.timezone)
    cutoff = datetime.now(local_tz) - timedelta(days=days)
    
    # Collect all hourly reports with their counts
    hourly_data: dict[str, int] = {}
    
    # Use glob to find all JSON files more efficiently
    for report_file in report_dir.glob("**/*.json"):
        try:
            # Parse path: YYYY/MM/DD/HH.json
            parts = report_file.relative_to(report_dir).parts
            if len(parts) != 4:
                continue
            
            year, month, day, hour_file = parts
            hour_str = report_file.stem
            
            if not (year.isdigit() and month.isdigit() and day.isdigit() and hour_str.isdigit()):
                continue
            
            year_int, month_int, day_int, hour_int = int(year), int(month), int(day), int(hour_str)
            hour_time = datetime(year_int, month_int, day_int, hour_int, tzinfo=local_tz)
            
            # Skip if outside time range
            if hour_time < cutoff:
                continue
            
            # Only open and parse if within range
            with report_file.open("r", encoding="utf-8") as f:
                report = json.load(f)
                stats = report.get("stats", {})
                total_events = stats.get("total_events", 0)
                if total_events > 0:
                    time_key = hour_time.isoformat()
                    hourly_data[time_key] = total_events
        except (ValueError, json.JSONDecodeError, KeyError, OSError):
            continue
    
    # Convert to sorted list
    result = [
        {"timestamp": ts, "count": count}
        for ts, count in sorted(hourly_data.items())
    ]
    return result


@app.get("/api/stats/counts")
def log_counts(days: int = Query(30, ge=1, le=90)) -> dict:
    """Get hourly log counts for the past N days."""
    cache_key = f"log_counts_{days}"
    now = time()
    if cache_key in _cache and (now - _cache_times.get(cache_key, 0)) < 900:
        return _cache[cache_key]
    
    result = {"items": _get_hourly_log_counts(days)}
    _cache[cache_key] = result
    _cache_times[cache_key] = now
    return result


# --- Log Search ---


@app.get("/logs/search")
def search_logs(
    q: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=500),
    hours: int = Query(6, ge=1, le=24),
    severity: str = Query("", regex="^(emerg|alert|crit|err|warn|notice|info|debug)?$")
) -> dict:
    """Search for logs in the last N hours matching the query string."""
    settings = default_settings
    bucket_dir = Path(settings.ingest.bucket_dir)
    if not bucket_dir.exists():
        return {"items": [], "stats": {"total": 0, "searched_minutes": 0}}
    
    from mithrillog.utils.time import get_timezone
    
    local_tz = get_timezone(settings.timezone)
    now = datetime.now(local_tz)
    cutoff = now - timedelta(hours=hours)
    
    results = []
    searched_minutes = 0
    
    # Pre-compute lowercase query and severity for efficiency
    q_lower = q.lower()
    severity_lower = severity.lower() if severity else None
    
    # Walk backwards from now
    current = now
    while current > cutoff and len(results) < limit:
        year = current.strftime("%Y")
        month = current.strftime("%m")
        day = current.strftime("%d")
        hour = current.strftime("%H")
        minute = current.strftime("%M")
        
        bucket_path = bucket_dir / year / month / day / hour / f"{minute}.ndjson"
        
        if bucket_path.exists():
            searched_minutes += 1
            try:
                # Stream file line by line instead of loading all into memory
                with bucket_path.open("r", encoding="utf-8") as f:
                    # Read lines in reverse order (newest first)
                    lines = []
                    for line in f:
                        lines.append(line)
                    
                    for line in reversed(lines):
                        if not line.strip():
                            continue
                        
                        try:
                            record = fast_json_loads(line)
                            
                            # Filter by severity FIRST (before building searchable string)
                            if severity_lower:
                                record_sev = record.get("severity", "").lower()
                                if record_sev != severity_lower:
                                    continue
                            
                            # Build searchable string only if severity matches
                            searchable = " ".join([
                                record.get('message', ''),
                                record.get('host', ''),
                                record.get('app', ''),
                                record.get('user_id', '')
                            ]).lower()
                            
                            # Use pre-computed lowercase query
                            if q_lower in searchable:
                                results.append(record)
                                if len(results) >= limit:
                                    break
                        except (json.JSONDecodeError, ValueError):
                            continue
            except Exception:
                pass
        
        # Early exit if we have enough results
        if len(results) >= limit:
            break
            
        current -= timedelta(minutes=1)
    
    return {
        "items": results,
        "stats": {
            "total": len(results),
            "searched_minutes": searched_minutes,
            "time_range_hours": hours
        }
    }

