"""
Admin Panel Backend API for MithrilLog.

FastAPI application providing admin dashboard endpoints for:
- Project management
- Usage analytics  
- Billing and invoices
- Admin authentication
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

# Add admin app to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.models import Project, SubscriptionPlan, UsageMetricDaily, UsageMetricHourly, init_db

# Real usage tracking from database
from sqlalchemy import func
from datetime import datetime

def get_real_usage(project_id: str, db):
    """Get usage from database metrics."""
    # Use Asia/Tehran timezone for "today"
    import pytz
    tehran_tz = pytz.timezone("Asia/Tehran")
    today = datetime.now(tehran_tz).date()
    today_midnight = datetime(today.year, today.month, today.day)
    
    # Get daily usage for today
    daily = db.query(UsageMetricDaily).filter(
        UsageMetricDaily.project_id == project_id,
        UsageMetricDaily.date == today_midnight
    ).first()
    
    current_day = daily.event_count if daily else 0
    
    return {"current_hour": 0, "current_day": current_day}

# Initialize database
import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./admin.db")
engine, SessionLocal = init_db(DATABASE_URL)

# Initialize app
app = FastAPI(title="MithrilLog Admin", version="1.0.0")

# Mount static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic models for API requests
class UpdatePlanRequest(BaseModel):
    plan_id: str


class UpdateQuotaRequest(BaseModel):
    daily_limit: int


class UpdateStatusRequest(BaseModel):
    status: str


# Pydantic models for API responses
class ProjectResponse(BaseModel):
    id: str
    name: str
    upstream_url: str
    plan_id: str
    plan_name: str
    billing_email: Optional[str]
    status: str
    created_at: str
    last_event_at: Optional[str]
    
    # Current usage
    current_hour_events: int
    current_day_events: int
    daily_limit: int
    usage_percent: float
    quota_status: str  # green, yellow, orange, red

    class Config:
        from_attributes = True


class DashboardStatsResponse(BaseModel):
    total_projects: int
    active_projects: int
    suspended_projects: int
    total_events_today: int
    total_events_this_month: int
    monthly_recurring_revenue: float


class UsageHourlyResponse(BaseModel):
    timestamp_hour: str
    event_count: int
    error_count: int


class UsageDailyResponse(BaseModel):
    date: str
    event_count: int
    error_count: int
    peak_events_per_hour: int


# ===== ROUTES =====

@app.get("/", response_class=HTMLResponse)
async def admin_dashboard():
    """Serve admin dashboard HTML."""
    html_path = Path(__file__).parent / "templates" / "admin.html"
    if html_path.exists():
        return html_path.read_text()
    return "<h1>MithrilLog Admin</h1><p>Dashboard coming soon...</p>"


@app.get("/api/admin/stats/overview")
async def get_dashboard_stats(db: Session = Depends(get_db)) -> DashboardStatsResponse:
    """Get overview statistics for admin dashboard."""
    
    # Project counts
    total_projects = db.query(Project).count()
    active_projects = db.query(Project).filter(Project.status == "active").count()
    suspended_projects = db.query(Project).filter(Project.status == "suspended").count()
    
    # Usage statistics
    from datetime import datetime, timedelta
    
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    
    # Events today across all projects
    # Note: This uses UTC today for aggregation across all projects for simplicity,
    # or we could update this to use Tehran time as well if needed.
    # For now, let's keep it consistent with the individual project usage.
    import pytz
    tehran_tz = pytz.timezone("Asia/Tehran")
    today_tehran = datetime.now(tehran_tz).date()
    today_midnight = datetime(today_tehran.year, today_tehran.month, today_tehran.day)

    events_today = db.query(func.sum(UsageMetricDaily.event_count)).filter(
        UsageMetricDaily.date == today_midnight
    ).scalar() or 0
    
    # Events this month
    events_month = db.query(func.sum(UsageMetricDaily.event_count)).filter(
        UsageMetricDaily.date >= month_start
    ).scalar() or 0
    
    # Calculate MRR
    projects = db.query(Project).filter(Project.status == "active").all()
    mrr = sum(project.plan.price_monthly for project in projects if project.plan)
    
    return DashboardStatsResponse(
        total_projects=total_projects,
        active_projects=active_projects,
        suspended_projects=suspended_projects,
        total_events_today=events_today,
        total_events_this_month=events_month,
        monthly_recurring_revenue=mrr,
    )


@app.get("/api/admin/projects", response_model=List[ProjectResponse])
async def list_projects(
    status: Optional[str] = Query(None, regex="^(active|suspended|cancelled)?$"),
    db: Session = Depends(get_db),
) -> List[ProjectResponse]:
    """List all projects with usage and quota info."""
    
    query = db.query(Project)
    if status:
        query = query.filter(Project.status == status)
    
    projects = query.all()
    
    result = []
    for project in projects:
        # Check if plan exists
        if not project.plan:
            # Skip projects without a valid plan or log error
            continue
        
        # Get current usage
        usage = get_real_usage(project.id, db)
        current_hour = usage["current_hour"]
        current_day = usage["current_day"]
        daily_limit = project.events_per_day_limit
        usage_percent = (current_day / daily_limit * 100) if daily_limit > 0 else 0
        
        # Determine quota status
        if usage_percent >= 100:
            quota_status = "red"
        elif usage_percent >= 90:
            quota_status = "orange"
        elif usage_percent >= 80:
            quota_status = "yellow"
        else:
            quota_status = "green"
        
        result.append(ProjectResponse(
            id=project.id,
            name=project.name,
            upstream_url=project.upstream_url,
            plan_id=project.plan_id,
            plan_name=project.plan.name,
            billing_email=project.billing_email,
            status=project.status,
            created_at=project.created_at.isoformat() if project.created_at else "",
            last_event_at=project.last_event_at.isoformat() if project.last_event_at else None,
            current_hour_events=current_hour,
            current_day_events=current_day,
            daily_limit=daily_limit,
            usage_percent=round(usage_percent, 2),
            quota_status=quota_status,
        ))
    
    return result


@app.get("/api/admin/projects/{project_id}")
async def get_project_detail(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectResponse:
    """Get detailed information for a single project."""
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if not project.plan:
        raise HTTPException(status_code=500, detail="Project has no associated plan")
    
    usage = get_real_usage(project.id, db)
    current_hour = usage["current_hour"]
    current_day = usage["current_day"]
    daily_limit = project.events_per_day_limit
    usage_percent = (current_day / daily_limit * 100) if daily_limit > 0 else 0
    
    if usage_percent >= 100:
        quota_status = "red"
    elif usage_percent >= 90:
        quota_status = "orange"
    elif usage_percent >= 80:
        quota_status = "yellow"
    else:
        quota_status = "green"
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        upstream_url=project.upstream_url,
        plan_id=project.plan_id,
        plan_name=project.plan.name,
        billing_email=project.billing_email,
        status=project.status,
        created_at=project.created_at.isoformat() if project.created_at else "",
        last_event_at=project.last_event_at.isoformat() if project.last_event_at else None,
        current_hour_events=current_hour,
        current_day_events=current_day,
        daily_limit=daily_limit,
        usage_percent=round(usage_percent, 2),
        quota_status=quota_status,
    )


@app.get("/api/admin/projects/{project_id}/usage/hourly", response_model=List[UsageHourlyResponse])
async def get_project_hourly_usage(
    project_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
) -> List[UsageHourlyResponse]:
    """Get hourly usage metrics for a project."""
    
    # Get hourly usage from DB
    metrics = db.query(UsageMetricHourly).filter(
        UsageMetricHourly.project_id == project_id
    ).order_by(UsageMetricHourly.timestamp_hour.desc()).limit(hours).all()
    
    return [UsageHourlyResponse(
        timestamp_hour=m.timestamp_hour.isoformat(),
        event_count=m.event_count,
        error_count=m.error_count
    ) for m in metrics]


@app.get("/api/admin/projects/{project_id}/usage/daily", response_model=List[UsageDailyResponse])
def get_project_usage_daily(
    project_id: str,
    days: int = 30,
    db: Session = Depends(get_db)
) -> List[UsageDailyResponse]:
    """Get daily usage metrics for a project."""
    
    # Get daily usage from DB
    metrics = db.query(UsageMetricDaily).filter(
        UsageMetricDaily.project_id == project_id
    ).order_by(UsageMetricDaily.date.desc()).limit(days).all()
    
    return [UsageDailyResponse(
        date=m.date.isoformat(),
        event_count=m.event_count,
        error_count=m.error_count,
        peak_events_per_hour=m.peak_events_per_hour
    ) for m in metrics]


@app.put("/api/admin/projects/{project_id}/quota")
async def update_project_quota(
    project_id: str,
    request: UpdateQuotaRequest,
    db: Session = Depends(get_db),
):
    """Update custom quota limit for a project."""
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if request.daily_limit <= 0:
        raise HTTPException(status_code=400, detail="Daily limit must be greater than 0")
    
    project.custom_quota_events_per_day = request.daily_limit
    db.commit()
    
    return {"message": "Quota updated successfully", "new_daily_limit": request.daily_limit}


@app.put("/api/admin/projects/{project_id}/plan")
async def update_project_plan(
    project_id: str,
    request: UpdatePlanRequest,
    db: Session = Depends(get_db),
):
    """Change subscription plan for a project."""
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == request.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    old_plan = project.plan.name
    project.plan_id = request.plan_id
    project.custom_quota_events_per_day = None  # Reset to plan default
    db.commit()
    
    return {
        "message": "Plan updated successfully",
        "old_plan": old_plan,
        "new_plan": plan.name,
        "new_daily_limit": plan.events_per_day_limit,
    }


@app.put("/api/admin/projects/{project_id}/status")
async def update_project_status(
    project_id: str,
    request: UpdateStatusRequest,
    db: Session = Depends(get_db),
):
    """Activate, suspend, or cancel a project."""
    
    if request.status not in ("active", "suspended", "cancelled"):
        raise HTTPException(status_code=400, detail="Invalid status. Must be: active, suspended, or cancelled")
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    old_status = project.status
    project.status = request.status
    db.commit()
    
    return {
        "message": "Status updated successfully",
        "old_status": old_status,
        "new_status": request.status,
    }


@app.get("/api/admin/plans", response_model=List[dict])
async def list_subscription_plans(db: Session = Depends(get_db)):
    """List all available subscription plans."""
    
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
    
    return [
        {
            "id": plan.id,
            "name": plan.name,
            "description": plan.description,
            "price_monthly": plan.price_monthly,
            "price_annual": plan.price_annual,
            "events_per_day_limit": plan.events_per_day_limit,
            "retention_days": plan.retention_days,
            "alert_channels_limit": plan.alert_channels_limit,
            "features": plan.features,
        }
        for plan in plans
    ]


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "mithrillog-admin"}


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(app, host="0.0.0.0", port=9999)
