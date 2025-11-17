from __future__ import annotations

import json
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


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/summaries/hourly")
def hourly_summaries(limit: int = Query(5, ge=1, le=48)) -> dict:
    settings = default_settings
    base = Path(settings.summary.report_dir) / "hourly"
    return {"items": _list_reports(base, limit)}


@app.get("/summaries/daily")
def daily_summaries(limit: int = Query(7, ge=1, le=14)) -> dict:
    settings = default_settings
    base = Path(settings.summary.report_dir) / "daily"
    return {"items": _list_reports(base, limit)}

