"""
MithrilLog Dashboards API

Custom dashboard builder with:
- Chart configuration
- Data binding to analytics queries
- Power BI-compatible data export (OData)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

logger = logging.getLogger("mithrillog.api.dashboards")

router = APIRouter(prefix="/api/dashboards", tags=["Dashboards"])


# --- Enums and Models ---

class ChartType(str, Enum):
    """Supported chart types."""
    LINE = "line"
    BAR = "bar"
    PIE = "pie"
    AREA = "area"
    SCATTER = "scatter"
    TABLE = "table"
    KPI = "kpi"
    GAUGE = "gauge"
    HEATMAP = "heatmap"


class AggregationType(str, Enum):
    """Data aggregation types."""
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"
    LAST = "last"


@dataclass
class ChartWidget:
    """A chart widget configuration."""
    id: str
    title: str
    chart_type: ChartType
    query: str  # SQL query or metric name
    x_field: str = "timestamp"
    y_field: str = "value"
    group_by: Optional[str] = None
    aggregation: AggregationType = AggregationType.AVG
    time_range_hours: int = 24
    refresh_seconds: int = 60
    color_scheme: str = "default"
    position: Dict[str, int] = field(default_factory=lambda: {"x": 0, "y": 0, "w": 4, "h": 3})
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "chart_type": self.chart_type.value,
            "query": self.query,
            "x_field": self.x_field,
            "y_field": self.y_field,
            "group_by": self.group_by,
            "aggregation": self.aggregation.value,
            "time_range_hours": self.time_range_hours,
            "refresh_seconds": self.refresh_seconds,
            "color_scheme": self.color_scheme,
            "position": self.position,
        }


@dataclass
class Dashboard:
    """A custom dashboard."""
    id: str
    tenant_id: str
    name: str
    description: str = ""
    widgets: List[ChartWidget] = field(default_factory=list)
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "widgets": [w.to_dict() for w in self.widgets],
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# --- In-Memory Storage ---

_dashboards: Dict[str, Dashboard] = {}


# --- Request Models ---

class CreateWidgetRequest(BaseModel):
    """Create widget request."""
    title: str
    chart_type: str = "line"
    query: str
    x_field: str = "timestamp"
    y_field: str = "value"
    group_by: Optional[str] = None
    aggregation: str = "avg"
    time_range_hours: int = Field(24, ge=1, le=720)
    refresh_seconds: int = Field(60, ge=10, le=3600)
    color_scheme: str = "default"
    position: Dict[str, int] = {"x": 0, "y": 0, "w": 4, "h": 3}


class CreateDashboardRequest(BaseModel):
    """Create dashboard request."""
    tenant_id: str
    name: str
    description: str = ""
    created_by: str = ""
    widgets: List[CreateWidgetRequest] = []


class UpdateDashboardRequest(BaseModel):
    """Update dashboard request."""
    name: Optional[str] = None
    description: Optional[str] = None
    widgets: Optional[List[CreateWidgetRequest]] = None


class ChartDataRequest(BaseModel):
    """Request chart data."""
    query: str
    x_field: str = "timestamp"
    y_field: str = "value"
    group_by: Optional[str] = None
    aggregation: str = "avg"
    time_range_hours: int = Field(24, ge=1, le=720)
    limit: int = Field(1000, ge=1, le=10000)


# --- Dashboard Endpoints ---

@router.post("/")
async def create_dashboard(request: CreateDashboardRequest):
    """Create a new custom dashboard."""
    dashboard_id = str(uuid.uuid4())
    
    widgets = []
    for w in request.widgets:
        widget = ChartWidget(
            id=str(uuid.uuid4()),
            title=w.title,
            chart_type=ChartType(w.chart_type),
            query=w.query,
            x_field=w.x_field,
            y_field=w.y_field,
            group_by=w.group_by,
            aggregation=AggregationType(w.aggregation),
            time_range_hours=w.time_range_hours,
            refresh_seconds=w.refresh_seconds,
            color_scheme=w.color_scheme,
            position=w.position,
        )
        widgets.append(widget)
    
    dashboard = Dashboard(
        id=dashboard_id,
        tenant_id=request.tenant_id,
        name=request.name,
        description=request.description,
        widgets=widgets,
        created_by=request.created_by,
    )
    
    _dashboards[dashboard_id] = dashboard
    logger.info(f"Created dashboard: {request.name} ({dashboard_id})")
    
    return {"success": True, "dashboard": dashboard.to_dict()}


@router.get("/")
async def list_dashboards(tenant_id: Optional[str] = None):
    """List all dashboards."""
    dashboards = list(_dashboards.values())
    
    if tenant_id:
        dashboards = [d for d in dashboards if d.tenant_id == tenant_id]
    
    return {
        "count": len(dashboards),
        "dashboards": [d.to_dict() for d in dashboards],
    }


@router.get("/{dashboard_id}")
async def get_dashboard(dashboard_id: str):
    """Get a specific dashboard."""
    dashboard = _dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, f"Dashboard not found: {dashboard_id}")
    
    return {"dashboard": dashboard.to_dict()}


@router.patch("/{dashboard_id}")
async def update_dashboard(dashboard_id: str, request: UpdateDashboardRequest):
    """Update a dashboard."""
    dashboard = _dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, f"Dashboard not found: {dashboard_id}")
    
    if request.name is not None:
        dashboard.name = request.name
    if request.description is not None:
        dashboard.description = request.description
    if request.widgets is not None:
        widgets = []
        for w in request.widgets:
            widget = ChartWidget(
                id=str(uuid.uuid4()),
                title=w.title,
                chart_type=ChartType(w.chart_type),
                query=w.query,
                x_field=w.x_field,
                y_field=w.y_field,
                group_by=w.group_by,
                aggregation=AggregationType(w.aggregation),
                time_range_hours=w.time_range_hours,
                refresh_seconds=w.refresh_seconds,
                color_scheme=w.color_scheme,
                position=w.position,
            )
            widgets.append(widget)
        dashboard.widgets = widgets
    
    dashboard.updated_at = datetime.utcnow()
    
    return {"success": True, "dashboard": dashboard.to_dict()}


@router.delete("/{dashboard_id}")
async def delete_dashboard(dashboard_id: str):
    """Delete a dashboard."""
    if dashboard_id not in _dashboards:
        raise HTTPException(404, f"Dashboard not found: {dashboard_id}")
    
    del _dashboards[dashboard_id]
    
    return {"success": True}


# --- Widget Endpoints ---

@router.post("/{dashboard_id}/widgets")
async def add_widget(dashboard_id: str, request: CreateWidgetRequest):
    """Add a widget to a dashboard."""
    dashboard = _dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, f"Dashboard not found: {dashboard_id}")
    
    widget = ChartWidget(
        id=str(uuid.uuid4()),
        title=request.title,
        chart_type=ChartType(request.chart_type),
        query=request.query,
        x_field=request.x_field,
        y_field=request.y_field,
        group_by=request.group_by,
        aggregation=AggregationType(request.aggregation),
        time_range_hours=request.time_range_hours,
        refresh_seconds=request.refresh_seconds,
        color_scheme=request.color_scheme,
        position=request.position,
    )
    
    dashboard.widgets.append(widget)
    dashboard.updated_at = datetime.utcnow()
    
    return {"success": True, "widget": widget.to_dict()}


@router.delete("/{dashboard_id}/widgets/{widget_id}")
async def remove_widget(dashboard_id: str, widget_id: str):
    """Remove a widget from a dashboard."""
    dashboard = _dashboards.get(dashboard_id)
    if not dashboard:
        raise HTTPException(404, f"Dashboard not found: {dashboard_id}")
    
    dashboard.widgets = [w for w in dashboard.widgets if w.id != widget_id]
    dashboard.updated_at = datetime.utcnow()
    
    return {"success": True}


# --- Chart Data Endpoints ---

@router.post("/chart-data")
async def get_chart_data(request: ChartDataRequest):
    """
    Fetch data for a chart widget.
    
    Executes the query and formats data for charting.
    """
    try:
        from mithrillog.analytics.core import get_analytics_core
        
        core = get_analytics_core()
        result = await core.execute(request.query)
        
        if not result.is_success:
            return {
                "success": False,
                "error": result.error,
                "data": [],
            }
        
        # Format for charting
        chart_data = []
        columns = result.columns
        
        x_idx = columns.index(request.x_field) if request.x_field in columns else 0
        y_idx = columns.index(request.y_field) if request.y_field in columns else 1
        
        for row in result.data:
            point = {
                "x": row[x_idx] if x_idx < len(row) else None,
                "y": row[y_idx] if y_idx < len(row) else None,
            }
            
            # Add group if specified
            if request.group_by and request.group_by in columns:
                group_idx = columns.index(request.group_by)
                point["group"] = row[group_idx]
            
            chart_data.append(point)
        
        return {
            "success": True,
            "data": chart_data,
            "columns": columns,
            "row_count": len(chart_data),
        }
        
    except ImportError:
        # Fallback: return sample data for testing
        return {
            "success": True,
            "data": [
                {"x": "2024-01-01T00:00:00", "y": 10},
                {"x": "2024-01-01T01:00:00", "y": 15},
                {"x": "2024-01-01T02:00:00", "y": 12},
            ],
            "columns": [request.x_field, request.y_field],
            "row_count": 3,
            "note": "Sample data - ClickHouse not connected",
        }


@router.get("/chart-templates")
async def get_chart_templates():
    """Get predefined chart templates."""
    return {
        "templates": [
            {
                "id": "log_volume",
                "name": "Log Volume",
                "chart_type": "area",
                "query": "SELECT toStartOfHour(timestamp) as hour, count() as count FROM logs GROUP BY hour ORDER BY hour",
                "x_field": "hour",
                "y_field": "count",
                "description": "Hourly log volume over time",
            },
            {
                "id": "error_rate",
                "name": "Error Rate",
                "chart_type": "line",
                "query": "SELECT toStartOfHour(timestamp) as hour, countIf(severity IN ('err', 'crit', 'emerg')) / count() * 100 as error_rate FROM logs GROUP BY hour ORDER BY hour",
                "x_field": "hour",
                "y_field": "error_rate",
                "description": "Error percentage by hour",
            },
            {
                "id": "top_hosts",
                "name": "Top Hosts",
                "chart_type": "bar",
                "query": "SELECT host, count() as count FROM logs GROUP BY host ORDER BY count DESC LIMIT 10",
                "x_field": "host",
                "y_field": "count",
                "description": "Top 10 hosts by log count",
            },
            {
                "id": "severity_dist",
                "name": "Severity Distribution",
                "chart_type": "pie",
                "query": "SELECT severity, count() as count FROM logs GROUP BY severity",
                "x_field": "severity",
                "y_field": "count",
                "description": "Log distribution by severity",
            },
            {
                "id": "process_variants",
                "name": "Process Variants",
                "chart_type": "bar",
                "query": "SELECT activity, count() as count FROM process_events GROUP BY activity ORDER BY count DESC LIMIT 20",
                "x_field": "activity",
                "y_field": "count",
                "description": "Process activity frequency",
            },
        ]
    }


# --- Power BI / OData Export ---

@router.get("/odata/{table_name}")
async def odata_query(
    table_name: str,
    top: int = Query(100, alias="$top", le=10000),
    skip: int = Query(0, alias="$skip"),
    orderby: str = Query("", alias="$orderby"),
    select: str = Query("", alias="$select"),
    filter: str = Query("", alias="$filter"),
):
    """
    OData-compatible endpoint for Power BI DirectQuery.
    
    Supports:
    - $top: Limit results
    - $skip: Offset for pagination
    - $orderby: Sort column
    - $select: Select specific columns
    - $filter: Basic filtering (limited)
    """
    try:
        from mithrillog.analytics.core import get_analytics_core
        
        core = get_analytics_core()
        
        # Build SQL from OData params
        columns = "*" if not select else select.replace(",", ", ")
        
        query = f"SELECT {columns} FROM {table_name}"
        
        if filter:
            # Basic OData filter translation
            sql_filter = filter.replace(" eq ", " = ").replace(" ne ", " != ")
            query += f" WHERE {sql_filter}"
        
        if orderby:
            order_parts = orderby.split(" ")
            order_col = order_parts[0]
            order_dir = "DESC" if len(order_parts) > 1 and order_parts[1].lower() == "desc" else "ASC"
            query += f" ORDER BY {order_col} {order_dir}"
        
        query += f" LIMIT {top} OFFSET {skip}"
        
        result = await core.execute(query)
        
        if not result.is_success:
            raise HTTPException(400, result.error)
        
        # Convert to OData format
        values = result.to_records()
        
        return {
            "@odata.context": f"$metadata#{table_name}",
            "@odata.count": len(values),
            "value": values,
        }
        
    except ImportError:
        return {
            "@odata.context": f"$metadata#{table_name}",
            "@odata.count": 0,
            "value": [],
            "note": "ClickHouse not connected",
        }


@router.get("/export/{format}")
async def export_data(
    format: str,
    query: str = Query(...),
    filename: str = Query("export"),
):
    """
    Export query results in various formats.
    
    Formats: csv, json, parquet (placeholder)
    """
    try:
        from mithrillog.analytics.core import get_analytics_core
        import csv
        from io import StringIO
        
        core = get_analytics_core()
        result = await core.execute(query)
        
        if not result.is_success:
            raise HTTPException(400, result.error)
        
        if format == "csv":
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(result.columns)
            writer.writerows(result.data)
            
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}.csv"}
            )
        
        elif format == "json":
            import json
            records = result.to_records()
            
            return Response(
                content=json.dumps(records, indent=2, default=str),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}.json"}
            )
        
        else:
            raise HTTPException(400, f"Unsupported format: {format}. Use csv or json.")
            
    except ImportError:
        raise HTTPException(503, "Analytics engine not available")
