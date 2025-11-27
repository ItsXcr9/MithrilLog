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

from app.models import Project, SubscriptionPlan, UsageMetricDaily, UsageMetricHourly, GlobalSettings, init_db

# YAML handling
import yaml

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


def get_project_storage(project_id: str, db) -> float:
    """Get storage usage in MB from latest daily metric (updated hourly by scheduler)."""
    from datetime import date, timedelta
    
    # Get most recent metric (within last 2 days to handle timezone issues)
    recent_date = date.today() - timedelta(days=2)
    
    latest = db.query(UsageMetricDaily).filter(
        UsageMetricDaily.project_id == project_id,
        UsageMetricDaily.date >= recent_date
    ).order_by(UsageMetricDaily.date.desc()).first()
    
    if latest and hasattr(latest, 'storage_bytes') and latest.storage_bytes:
        return round(latest.storage_bytes / (1024 * 1024), 2)  # Convert to MB
    
    # Fallback: calculate on-demand if not in DB yet
    project_dir = Path(f"/host_home/MithrilLog-{project_id}")
    if not project_dir.exists():
        return 0.0
    
    try:
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(project_dir):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                try:
                    total_size += filepath.stat().st_size
                except (OSError, FileNotFoundError):
                    continue
        return round(total_size / (1024 * 1024), 2)
    except Exception as e:
        print(f"Error calculating storage for {project_id}: {e}")
        return 0.0


def update_project_config_file(project_id: str, settings: dict):
    """Update project's default.yaml file with new settings."""
    config_path = Path(f"/host_home/MithrilLog-{project_id}/configs/default.yaml")
    
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return False
    
    try:
        # Load existing config
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f) or {}
        
        # Update LLM settings
        if 'llm' in settings and settings['llm']:
            if 'llm' not in config:
                config['llm'] = {}
            
            llm = settings['llm']
            if llm.get('backend'):
                config['llm']['backend'] = llm['backend']
            if llm.get('model'):
                if llm['backend'] == 'gemini':
                    config['llm']['gemini_model'] = llm['model']
                elif llm['backend'] == 'openai':
                    config['llm']['openai_model'] = llm['model']
            if llm.get('temperature') is not None:
                config['llm']['temperature'] = llm['temperature']
            if llm.get('gemini_key'):
                config['llm']['gemini_api_key'] = llm['gemini_key']
            if llm.get('openai_key'):
                config['llm']['openai_api_key'] = llm['openai_key']
        
        # Update ingestion settings
        if 'ingest' in settings and settings['ingest']:
            if 'ingest' not in config:
                config['ingest'] = {}
            if settings['ingest'].get('retention_days'):
                config['ingest']['retention_days'] = settings['ingest']['retention_days']
        
        # Update alert settings
        if 'alert' in settings and settings['alert']:
            if 'alert' not in config:
                config['alert'] = {}
            if settings['alert'].get('telegram_token'):
                config['alert']['telegram_bot_token'] = settings['alert']['telegram_token']
            if settings['alert'].get('telegram_chat'):
                config['alert']['telegram_chat_id'] = settings['alert']['telegram_chat']
        
        # Update summary interval (mapped to summary.hourly_at_minute)
        if 'summary_interval' in settings and settings['summary_interval']:
            if 'summary' not in config:
                config['summary'] = {}
            # Convert seconds to minutes for hourly summary
            interval_minutes = settings['summary_interval'] // 60
            config['summary']['hourly_at_minute'] = interval_minutes % 60
        
        # Update web title
        if 'web_title' in settings and settings['web_title']:
            if 'web' not in config:
                config['web'] = {}
            config['web']['title'] = settings['web_title']
        
        # Update cores (add as new field if not exists)
        if 'cores' in settings and settings['cores']:
            config['cores'] = settings['cores']
        
        # Update log pattern (add to logging.patterns)
        if 'log_pattern' in settings and settings['log_pattern']:
            if 'logging' not in config:
                config['logging'] = {}
            config['logging']['filter_pattern'] = settings['log_pattern']
        
        # Write back to file
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        print(f"Updated config file: {config_path}")
        return True
        
    except Exception as e:
        print(f"Error updating config file: {e}")
        return False

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
    daily_limit: int
    usage_percent: float
    usage_percent: float
    quota_status: str  # green, yellow, orange, red
    settings: Optional[dict] = {}
    storage_mb: Optional[float] = 0.0

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
            settings=project.settings or {},
            storage_mb=get_project_storage(project.id, db),
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
        settings=project.settings or {},
        storage_mb=get_project_storage(project_id, db),
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


class UpdateSettingsRequest(BaseModel):
    settings: dict


@app.put("/api/admin/projects/{project_id}/settings")
async def update_project_settings(
    project_id: str,
    request: UpdateSettingsRequest,
    db: Session = Depends(get_db),
):
    """Update settings for a project."""
    
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Update settings
    project.settings = request.settings
    db.commit()
    
    # Update project's config file
    update_project_config_file(project_id, request.settings)
    
    return {
        "message": "Settings updated successfully",
        "settings": project.settings,
    }


# Global Settings Endpoints
class GlobalSettingsRequest(BaseModel):
    prompts: Optional[dict] = None
    default_llm: Optional[dict] = None


@app.get("/api/admin/settings")
async def get_global_settings(db: Session = Depends(get_db)):
    """Get global settings."""
    settings = db.query(GlobalSettings).first()
    
    # Load prompts from files if they exist
    prompts_dir = Path("/app/prompts") if Path("/app/prompts").exists() else Path("../prompts")
    default_prompts = {}
    
    if prompts_dir.exists():
        summary_file = prompts_dir / "daily_summary.txt"
        trend_file = prompts_dir / "trend_analysis.txt"
        
        if summary_file.exists():
            default_prompts["summary"] = summary_file.read_text()
        else:
            default_prompts["summary"] = "Analyze and summarize the following logs. Focus on errors, warnings, and patterns."
        
        if trend_file.exists():
            default_prompts["trend"] = trend_file.read_text()
        else:
            default_prompts["trend"] = "Compare these time periods and identify significant trends, anomalies, and changes in error patterns."
    else:
        default_prompts = {
            "summary": "Analyze and summarize the following logs. Focus on errors, warnings, and patterns.",
            "trend": "Compare these time periods and identify significant trends, anomalies, and changes in error patterns."
        }
    
    if not settings:
        # Return defaults if not found
        return {
            "prompts": default_prompts,
            "default_llm": {
                "backend": "gemini",
                "model": "gemini-2.5-flash-lite",
                "temperature": 0.2
            }
        }
    
    # Use saved prompts if available, otherwise use defaults from files
    return {
        "prompts": settings.prompts if settings.prompts else default_prompts,
        "default_llm": settings.default_llm or {}
    }


@app.put("/api/admin/settings")
async def update_global_settings(
    request: GlobalSettingsRequest,
    db: Session = Depends(get_db),
):
    """Update global settings."""
    settings = db.query(GlobalSettings).first()
    
    if not settings:
        # Create new settings
        settings = GlobalSettings(
            prompts=request.prompts or {},
            default_llm=request.default_llm or {}
        )
        db.add(settings)
    else:
        # Update existing
        if request.prompts is not None:
            settings.prompts = request.prompts
        if request.default_llm is not None:
            settings.default_llm = request.default_llm
    
    db.commit()
    
    # Save prompts to files if provided
    if request.prompts:
        prompts_dir = Path("/app/prompts") if Path("/app/prompts").exists() else Path("../prompts")
        if prompts_dir.exists():
            if "summary" in request.prompts:
                summary_file = prompts_dir / "daily_summary.txt"
                summary_file.write_text(request.prompts["summary"])
            if "trend" in request.prompts:
                trend_file = prompts_dir / "trend_analysis.txt"
                trend_file.write_text(request.prompts["trend"])
    
    return {
        "message": "Global settings updated successfully",
        "prompts": settings.prompts,
        "default_llm": settings.default_llm
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
