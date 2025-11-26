"""
Quota Enforcement Service for MithrilLog.

Checks project usage against subscription limits and enforces quota policies.
Sends warnings and alerts as projects approach limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from admin.app.models import Project
from mithrillog.usage_tracker import UsageTracker


class QuotaStatus(str, Enum):
    """Quota status levels."""
    GREEN = "green"  # 0-80% usage
    YELLOW = "yellow"  # 80-90% usage (warning)
    ORANGE = "orange"  # 90-100% usage (critical)
    RED = "red"  # >100% usage (exceeded)


@dataclass
class QuotaCheckResult:
    """Result of quota check."""
    project_id: str
    status: QuotaStatus
    usage_count: int
    limit: int
    usage_percent: float
    exceeded: bool
    should_warn: bool
    should_alert: bool


class QuotaEnforcer:
    """
    Enforces subscription quotas and rate limits.
    
    Usage:
        enforcer = QuotaEnforcer(session, tracker)
        result = enforcer.check_daily_quota("project1")
        if result.exceeded:
            # Reject or throttle request
    """

    # Thresholds
    WARNING_THRESHOLD = 0.80  # 80%
    CRITICAL_THRESHOLD = 0.90  # 90%

    def __init__(self, session: Session, tracker: UsageTracker):
        self.session = session
        self.tracker = tracker
    
    def check_daily_quota(self, project_id: str) -> QuotaCheckResult:
        """Check if project has exceeded daily quota."""
        # Get project and plan
        project = self.session.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        # Check if project is suspended
        if project.status != "active":
            return QuotaCheckResult(
                project_id=project_id,
                status=QuotaStatus.RED,
                usage_count=0,
                limit=0,
                usage_percent=100.0,
                exceeded=True,
                should_warn=False,
                should_alert=False,
            )
        
        # Get current usage
        current_usage = self.tracker.get_current_day_usage(project_id)
        
        # Get effective limit (custom or plan default)
        daily_limit = project.events_per_day_limit
        
        # Calculate usage percentage
        usage_percent = (current_usage / daily_limit) * 100 if daily_limit > 0 else 0
        
        # Determine status
        if usage_percent >= 100:
            status = QuotaStatus.RED
            exceeded = True
            should_warn = False
            should_alert = True
        elif usage_percent >= self.CRITICAL_THRESHOLD * 100:
            status = QuotaStatus.ORANGE
            exceeded = False
            should_warn = False
            should_alert = True
        elif usage_percent >= self.WARNING_THRESHOLD * 100:
            status = QuotaStatus.YELLOW
            exceeded = False
            should_warn = True
            should_alert = False
        else:
            status = QuotaStatus.GREEN
            exceeded = False
            should_warn = False
            should_alert = False
        
        return QuotaCheckResult(
            project_id=project_id,
            status=status,
            usage_count=current_usage,
            limit=daily_limit,
            usage_percent=usage_percent,
            exceeded=exceeded,
            should_warn=should_warn,
            should_alert=should_alert,
        )
    
    def should_reject_event(self, project_id: str) -> bool:
        """Check if incoming event should be rejected due to quota."""
        result = self.check_daily_quota(project_id)
        return result.exceeded
    
    def get_retry_after_seconds(self, project_id: str) -> int:
        """Get seconds until quota resets (for Retry-After header)."""
        # Quota resets at midnight UTC
        now = datetime.utcnow()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        from datetime import timedelta
        tomorrow += timedelta(days=1)
        
        seconds_until_reset = int((tomorrow - now).total_seconds())
        return seconds_until_reset
    
    def send_quota_warning(self, project_id: str, result: QuotaCheckResult) -> None:
        """
        Send warning notification to project owner.
        
        TODO: Implement email/telegram notification
        Args:
            project_id: Project identifier
            result: Quota check result with usage details
        """
        project = self.session.query(Project).filter(Project.id == project_id).first()
        
        if not project or not project.billing_email:
            return
        
        # TODO: Send email via SMTP
        print(f"📧 QUOTA WARNING: {project.name}")
        print(f"   Usage: {result.usage_count:,} / {result.limit:,} ({result.usage_percent:.1f}%)")
        print(f"   Status: {result.status}")
        print(f"   Send email to: {project.billing_email}")
        
        # Log the warning
        # TODO: Add to admin_actions table for audit trail


# Global enforcer instance
_global_enforcer: Optional[QuotaEnforcer] = None


def init_enforcer(session: Session, tracker: UsageTracker) -> QuotaEnforcer:
    """Initialize global quota enforcer."""
    global _global_enforcer
    _global_enforcer = QuotaEnforcer(session, tracker)
    return _global_enforcer


def get_enforcer() -> QuotaEnforcer:
    """Get global quota enforcer instance."""
    if _global_enforcer is None:
        raise RuntimeError("QuotaEnforcer not initialized. Call init_enforcer() first.")
    return _global_enforcer
