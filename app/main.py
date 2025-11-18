from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from mithrillog.config import Settings, default_settings

app = FastAPI(title="MithrilLog API")

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
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/summaries/hourly")
def hourly_summaries(limit: int = Query(5, ge=1, le=48)) -> dict:
    return {"items": _hourly_reports(limit)}


@app.get("/summaries/daily")
def daily_summaries(limit: int = Query(7, ge=1, le=14)) -> dict:
    settings = default_settings
    base = Path(settings.summary.report_dir) / "daily"
    return {"items": _list_reports(base, limit)}


@app.get("/insights/errors")
def error_insights(limit: int = Query(8, ge=1, le=48)) -> dict:
    return {"items": _error_insights(limit)}

