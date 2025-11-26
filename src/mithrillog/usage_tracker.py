"""
Usage Tracking Service for MithrilLog.

Tracks log events per project in real-time with efficient in-memory counters
and periodic database persistence. Provides hourly and daily aggregates.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from admin.app.models import Project, UsageMetricDaily, UsageMetricHourly


class UsageTracker:
    """
    Thread-safe usage tracker with in-memory counters and periodic DB flush.
    
    Usage:
        tracker = UsageTracker(db_session)
        tracker.record_event("project1", event_count=1)
        tracker.flush()  # Persist to database
    """

    def __init__(self, session: Session):
        self.session = session
        self.lock = threading.Lock()
        
        # In-memory counters: {project_id: {hour_key: count}}
        self.hourly_counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.error_counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    
    def record_event(
        self,
        project_id: str,
        event_count: int = 1,
        is_error: bool = False,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Record events for a project.
        
        Args:
            project_id: Project identifier
            event_count: Number of events to record (default: 1)
            is_error: Whether this is an error event
            timestamp: Event timestamp (default: now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Truncate to hour for bucketing
        hour_key = timestamp.strftime("%Y-%m-%d-%H")
        
        with self.lock:
            self.hourly_counters[project_id][hour_key] += event_count
            if is_error:
                self.error_counters[project_id][hour_key] += event_count
    
    def flush(self) -> None:
        """Flush in-memory counters to database."""
        with self.lock:
            # Copy and clear counters atomically
            hourly_data = dict(self.hourly_counters)
            error_data = dict(self.error_counters)
            self.hourly_counters.clear()
            self.error_counters.clear()
        
        # Persist to database
        for project_id, hours in hourly_data.items():
            for hour_key, count in hours.items():
                timestamp_hour = datetime.strptime(hour_key, "%Y-%m-%d-%H")
                error_count = error_data.get(project_id, {}).get(hour_key, 0)
                
                # Update or insert hourly metric
                metric = (
                    self.session.query(UsageMetricHourly)
                    .filter(
                        UsageMetricHourly.project_id == project_id,
                        UsageMetricHourly.timestamp_hour == timestamp_hour,
                    )
                    .first()
                )
                
                if metric:
                    metric.event_count += count
                    metric.error_count += error_count
                    metric.updated_at = datetime.utcnow()
                else:
                    metric = UsageMetricHourly(
                        project_id=project_id,
                        timestamp_hour=timestamp_hour,
                        event_count=count,
                        error_count=error_count,
                    )
                    self.session.add(metric)
        
        self.session.commit()
    
    def get_current_hour_usage(self, project_id: str) -> int:
        """Get event count for current hour (in-memory + DB)."""
        now = datetime.utcnow()
        hour_key = now.strftime("%Y-%m-%d-%H")
        
        # In-memory count
        with self.lock:
            memory_count = self.hourly_counters[project_id].get(hour_key, 0)
        
        # DB count
        timestamp_hour = datetime.strptime(hour_key, "%Y-%m-%d-%H")
        metric = (
            self.session.query(UsageMetricHourly)
            .filter(
                UsageMetricHourly.project_id == project_id,
                UsageMetricHourly.timestamp_hour == timestamp_hour,
            )
            .first()
        )
        db_count = metric.event_count if metric else 0
        
        return memory_count + db_count
    
    def get_current_day_usage(self, project_id: str) -> int:
        """Get total event count for current day."""
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Sum hourly metrics for today
        hourly_sum = (
            self.session.query(UsageMetricHourly)
            .filter(
                UsageMetricHourly.project_id == project_id,
                UsageMetricHourly.timestamp_hour >= start_of_day,
            )
            .with_entities(UsageMetricHourly.event_count)
            .all()
        )
        
        total = sum(row[0] for row in hourly_sum)
        
        # Add in-memory counts for today
        with self.lock:
            for hour_key, count in self.hourly_counters[project_id].items():
                hour_dt = datetime.strptime(hour_key, "%Y-%m-%d-%H")
                if hour_dt >= start_of_day:
                    total += count
        
        return total
    
    def get_hourly_usage(
        self,
        project_id: str,
        hours: int = 24,
    ) -> List[dict]:
        """
        Get hourly usage for the past N hours.
        
        Returns:
            List of dicts with keys: timestamp_hour, event_count, error_count
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=hours)
        
        metrics = (
            self.session.query(UsageMetricHourly)
            .filter(
                UsageMetricHourly.project_id == project_id,
                UsageMetricHourly.timestamp_hour >= cutoff,
            )
            .order_by(UsageMetricHourly.timestamp_hour)
            .all()
        )
        
        return [
            {
                "timestamp_hour": m.timestamp_hour.isoformat(),
                "event_count": m.event_count,
                "error_count": m.error_count,
            }
            for m in metrics
        ]
    
    def get_daily_usage(
        self,
        project_id: str,
        days: int = 30,
    ) -> List[dict]:
        """
        Get daily usage for the past N days.
        
        Returns:
            List of dicts with keys: date, event_count, error_count, peak_events_per_hour
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(days=days)
        
        metrics = (
            self.session.query(UsageMetricDaily)
            .filter(
                UsageMetricDaily.project_id == project_id,
                UsageMetricDaily.date >= cutoff,
            )
            .order_by(UsageMetricDaily.date)
            .all()
        )
        
        return [
            {
                "date": m.date.isoformat(),
                "event_count": m.event_count,
                "error_count": m.error_count,
                "peak_events_per_hour": m.peak_events_per_hour,
            }
            for m in metrics
        ]
    
    def aggregate_daily_metrics(self) -> None:
        """
        Aggregate hourly metrics into daily rollups.
        Should be run once per day (e.g., at midnight).
        """
        yesterday = datetime.utcnow().date() - timedelta(days=1)
        start_of_day = datetime.combine(yesterday, datetime.min.time())
        end_of_day = start_of_day + timedelta(days=1)
        
        # Get all projects
        projects = self.session.query(Project).all()
        
        for project in projects:
            # Sum hourly metrics for yesterday
            hourly_metrics = (
                self.session.query(UsageMetricHourly)
                .filter(
                    UsageMetricHourly.project_id == project.id,
                    UsageMetricHourly.timestamp_hour >= start_of_day,
                    UsageMetricHourly.timestamp_hour < end_of_day,
                )
                .all()
            )
            
            if not hourly_metrics:
                continue
            
            total_events = sum(m.event_count for m in hourly_metrics)
            total_errors = sum(m.error_count for m in hourly_metrics)
            peak_events = max(m.event_count for m in hourly_metrics)
            
            # Create or update daily metric
            daily_metric = (
                self.session.query(UsageMetricDaily)
                .filter(
                    UsageMetricDaily.project_id == project.id,
                    UsageMetricDaily.date == start_of_day,
                )
                .first()
            )
            
            if daily_metric:
                daily_metric.event_count = total_events
                daily_metric.error_count = total_errors
                daily_metric.peak_events_per_hour = peak_events
                daily_metric.updated_at = datetime.utcnow()
            else:
                daily_metric = UsageMetricDaily(
                    project_id=project.id,
                    date=start_of_day,
                    event_count=total_events,
                    error_count=total_errors,
                    peak_events_per_hour=peak_events,
                )
                self.session.add(daily_metric)
        
        self.session.commit()


# Global tracker instance (will be initialized in app startup)
_global_tracker: Optional[UsageTracker] = None


def init_tracker(session: Session) -> UsageTracker:
    """Initialize global usage tracker."""
    global _global_tracker
    _global_tracker = UsageTracker(session)
    return _global_tracker


def get_tracker() -> UsageTracker:
    """Get global usage tracker instance."""
    if _global_tracker is None:
        raise RuntimeError("UsageTracker not initialized. Call init_tracker() first.")
    return _global_tracker
