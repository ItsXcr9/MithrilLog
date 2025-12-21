"""
MithrilLog Analytics API

REST endpoints for:
- SQL query execution
- Process mining
- Anomaly detection
- Data discovery
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger("mithrillog.api.analytics")

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


# --- Request/Response Models ---

class QueryRequest(BaseModel):
    """SQL query request."""
    sql: str = Field(..., description="SQL query to execute")
    params: Optional[Dict[str, Any]] = Field(None, description="Query parameters")
    allow_write: bool = Field(False, description="Allow write operations (INSERT/UPDATE/DELETE)")


class QueryResponse(BaseModel):
    """SQL query response."""
    success: bool
    columns: List[str]
    data: List[List[Any]]
    row_count: int
    execution_time_ms: float
    error: Optional[str] = None


class ProcessMiningRequest(BaseModel):
    """Process mining extraction request."""
    tenant_id: str
    start_time: datetime
    end_time: datetime
    case_id_pattern: Optional[str] = None
    activity_field: str = "app"
    limit: int = Field(10000, le=100000)


class AnomalyRequest(BaseModel):
    """Anomaly detection request."""
    metric_name: str
    data: List[Dict[str, Any]]  # [{timestamp, value}]
    method: str = "zscore"  # zscore or iqr
    threshold: float = 3.0


class ForecastRequest(BaseModel):
    """Forecasting request."""
    metric_name: str
    data: List[Dict[str, Any]]  # [{timestamp, value}]
    periods: int = Field(24, le=168)  # Max 1 week
    period_minutes: int = 60
    method: str = "linear"  # linear or seasonal


# --- Analytics Core Client ---

_analytics_core = None


def set_analytics_core(core):
    """Set the analytics core instance."""
    global _analytics_core
    _analytics_core = core


def get_analytics_core():
    """Get the analytics core instance."""
    global _analytics_core
    if _analytics_core is None:
        from mithrillog.analytics.core import AnalyticsCore
        _analytics_core = AnalyticsCore()
    return _analytics_core


# --- Endpoints ---

@router.post("/query", response_model=QueryResponse)
async def execute_query(request: QueryRequest):
    """
    Execute a SQL query against ClickHouse.
    
    Supports:
    - SELECT queries (read-only by default)
    - Parameterized queries with :param syntax
    - Schema discovery queries
    """
    core = get_analytics_core()
    
    result = await core.execute(
        sql=request.sql,
        params=request.params,
        allow_write=request.allow_write,
    )
    
    return QueryResponse(
        success=result.is_success,
        columns=result.columns,
        data=result.data,
        row_count=result.row_count,
        execution_time_ms=result.execution_time_ms,
        error=result.error,
    )


@router.get("/debug/connection")
async def debug_connection():
    """Debug endpoint to test ClickHouse connection directly."""
    import httpx
    import os
    
    host = os.getenv("CLICKHOUSE_HOST", "localhost")
    port = os.getenv("CLICKHOUSE_PORT", "8123")
    db = os.getenv("CLICKHOUSE_DB", "mithrillog")
    user = os.getenv("CLICKHOUSE_USER", "default")
    password = os.getenv("CLICKHOUSE_PASSWORD", "")
    
    url = f"http://{host}:{port}/?query=SELECT+1&user={user}&password={password}"
    
    result = {
        "host": host,
        "port": port,
        "database": db,
        "user": user,
        "url": url,
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            result["status_code"] = response.status_code
            result["response"] = response.text[:500]
            result["connected"] = response.status_code == 200 and response.text.strip() == "1"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["connected"] = False
    
    return result


@router.get("/schemas")
async def discover_schemas():
    """
    Discover all tables and schemas in the database.
    
    Returns table names, columns, types, and statistics.
    """
    core = get_analytics_core()
    schemas = await core.discover_schemas()
    
    return {
        "database": core.database,
        "tables": [
            {
                "name": s.name,
                "columns": s.columns,
                "row_count": s.row_count,
                "size_bytes": s.size_bytes,
                "engine": s.engine,
                "partition_key": s.partition_key,
                "sorting_key": s.sorting_key,
            }
            for s in schemas
        ],
    }


@router.get("/tables/{table}/stats")
async def get_table_stats(table: str):
    """Get statistics for a specific table."""
    core = get_analytics_core()
    return await core.get_table_stats(table)


@router.get("/tables/{table}/columns/{column}/profile")
async def profile_column(
    table: str, 
    column: str,
    limit: int = Query(100, le=1000),
):
    """
    Profile a column for data discovery.
    
    Returns cardinality, null counts, and top values.
    """
    core = get_analytics_core()
    return await core.profile_column(table, column, limit)


@router.get("/health")
async def analytics_health():
    """Check analytics engine health."""
    core = get_analytics_core()
    return await core.health_check()


# --- Process Mining Endpoints ---

@router.post("/process-mining/extract")
async def extract_process_events(request: ProcessMiningRequest):
    """
    Extract process events from log data.
    
    Identifies case IDs and activities for process mining.
    """
    from mithrillog.analytics.process_mining import get_process_mining_engine
    
    engine = get_process_mining_engine()
    events = await engine.extract_events_from_logs(
        tenant_id=request.tenant_id,
        start_time=request.start_time,
        end_time=request.end_time,
        case_id_pattern=request.case_id_pattern,
        activity_field=request.activity_field,
        limit=request.limit,
    )
    
    return {
        "event_count": len(events),
        "events": [
            {
                "case_id": e.case_id,
                "activity": e.activity,
                "timestamp": e.timestamp.isoformat(),
                "resource": e.resource,
                "duration_ms": e.duration_ms,
            }
            for e in events[:100]  # Limit response size
        ],
        "truncated": len(events) > 100,
    }


@router.post("/process-mining/variants")
async def discover_process_variants(request: ProcessMiningRequest):
    """
    Discover process variants from log data.
    
    Returns unique activity sequences with statistics.
    """
    from mithrillog.analytics.process_mining import get_process_mining_engine
    
    engine = get_process_mining_engine()
    events = await engine.extract_events_from_logs(
        tenant_id=request.tenant_id,
        start_time=request.start_time,
        end_time=request.end_time,
        limit=request.limit,
    )
    
    traces = engine.group_into_traces(events)
    variants = engine.discover_variants(traces)
    
    return {
        "case_count": len(traces),
        "variant_count": len(variants),
        "variants": [
            {
                "activities": list(v.activities),
                "case_count": v.case_count,
                "avg_duration_ms": v.avg_duration_ms,
                "example_cases": v.example_case_ids,
            }
            for v in variants[:50]
        ],
    }


@router.post("/process-mining/export/xes")
async def export_xes(request: ProcessMiningRequest):
    """
    Export process data in XES format.
    
    XES is compatible with:
    - Celonis
    - IBM Process Mining
    - Power Automate Process Mining
    - Disco
    - ProM
    """
    from mithrillog.analytics.process_mining import get_process_mining_engine
    from fastapi.responses import Response
    
    engine = get_process_mining_engine()
    events = await engine.extract_events_from_logs(
        tenant_id=request.tenant_id,
        start_time=request.start_time,
        end_time=request.end_time,
        limit=request.limit,
    )
    
    traces = engine.group_into_traces(events)
    xes_content = engine.export_to_xes(traces, process_name=f"MithrilLog-{request.tenant_id}")
    
    return Response(
        content=xes_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=process_{request.tenant_id}.xes"
        }
    )


@router.post("/process-mining/summary")
async def process_mining_summary(request: ProcessMiningRequest):
    """Get high-level process mining summary."""
    from mithrillog.analytics.process_mining import get_process_mining_engine
    
    engine = get_process_mining_engine()
    return await engine.get_process_summary(
        tenant_id=request.tenant_id,
        start_time=request.start_time,
        end_time=request.end_time,
    )


# --- ML Analytics Endpoints ---

@router.post("/anomalies/detect")
async def detect_anomalies(request: AnomalyRequest):
    """
    Detect anomalies in time-series data.
    
    Supports:
    - Z-score method (for normal distributions)
    - IQR method (robust to outliers)
    """
    from mithrillog.analytics.ml_engine import get_ml_engine
    
    engine = get_ml_engine()
    
    # Parse data
    data = []
    for point in request.data:
        ts = point.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        data.append((ts, point.get("value", 0)))
    
    if request.method == "iqr":
        results = engine.detect_anomalies_iqr(request.metric_name, data, request.threshold)
    else:
        results = engine.detect_anomalies_zscore(request.metric_name, data, request.threshold)
    
    anomalies = [r for r in results if r.is_anomaly]
    
    return {
        "total_points": len(data),
        "anomaly_count": len(anomalies),
        "anomalies": [a.to_dict() for a in anomalies],
        "method": request.method,
        "threshold": request.threshold,
    }


@router.post("/forecast")
async def forecast_metric(request: ForecastRequest):
    """
    Forecast future values for a metric.
    
    Supports:
    - Linear regression (for trending data)
    - Seasonal forecasting (for periodic patterns)
    """
    from mithrillog.analytics.ml_engine import get_ml_engine
    
    engine = get_ml_engine()
    
    # Parse data
    data = []
    for point in request.data:
        ts = point.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        data.append((ts, point.get("value", 0)))
    
    if request.method == "seasonal":
        predictions = engine.forecast_seasonal(
            request.metric_name, 
            data, 
            request.periods, 
            request.period_minutes
        )
    else:
        predictions = engine.forecast_linear(
            request.metric_name, 
            data, 
            request.periods, 
            request.period_minutes
        )
    
    return {
        "metric_name": request.metric_name,
        "method": request.method,
        "periods": len(predictions),
        "predictions": [p.to_dict() for p in predictions],
    }


@router.get("/health/summary")
async def ml_health_summary(
    hours: int = Query(24, le=168),
):
    """
    Get ML-powered health summary.
    
    Analyzes recent data for anomalies and patterns.
    """
    # This would typically fetch data from ClickHouse
    # For now, return a placeholder
    return {
        "status": "healthy",
        "period_hours": hours,
        "metrics_analyzed": 0,
        "anomaly_count": 0,
        "message": "Connect to ClickHouse to enable full analysis",
    }
