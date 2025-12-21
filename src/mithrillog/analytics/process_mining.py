"""
MithrilLog Process Mining Engine

Extract process mining-ready event logs from MithrilLog data.
Supports XES format export for Celonis, IBM Process Mining, and Power Automate Mining.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from io import StringIO

from .core import AnalyticsCore, get_analytics_core

logger = logging.getLogger("mithrillog.analytics.process_mining")


@dataclass
class ProcessEvent:
    """A single event in a process trace."""
    case_id: str
    activity: str
    timestamp: datetime
    resource: Optional[str] = None
    duration_ms: Optional[int] = None
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessTrace:
    """A sequence of events forming a process instance."""
    case_id: str
    events: List[ProcessEvent]
    
    @property
    def duration_ms(self) -> int:
        """Total duration from first to last event."""
        if len(self.events) < 2:
            return 0
        sorted_events = sorted(self.events, key=lambda e: e.timestamp)
        return int((sorted_events[-1].timestamp - sorted_events[0].timestamp).total_seconds() * 1000)
    
    @property
    def activity_count(self) -> int:
        return len(self.events)


@dataclass
class ProcessVariant:
    """A unique sequence of activities."""
    activities: Tuple[str, ...]
    case_count: int
    avg_duration_ms: float
    example_case_ids: List[str]


class ProcessMiningEngine:
    """
    Process Mining Engine for MithrilLog.
    
    Extracts event logs from system logs and exports in XES format
    for compatibility with:
    - Celonis
    - IBM Process Mining
    - Power Automate Process Mining
    """
    
    def __init__(self, analytics_core: Optional[AnalyticsCore] = None):
        self.analytics = analytics_core or get_analytics_core()
    
    async def extract_events_from_logs(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        case_id_pattern: Optional[str] = None,
        activity_field: str = "app",
        limit: int = 100000,
    ) -> List[ProcessEvent]:
        """
        Extract process events from log data.
        
        Logs are parsed to identify:
        - Case IDs (from transaction IDs, request IDs, session IDs)
        - Activities (from app/service names or log messages)
        - Resources (from host)
        """
        # First, try to get events from the process_events table if it exists
        result = await self.analytics.execute(f"""
            SELECT 
                case_id,
                activity,
                timestamp,
                resource,
                duration_ms,
                attributes
            FROM process_events
            WHERE tenant_id = :tenant_id
              AND timestamp >= :start_time
              AND timestamp <= :end_time
            ORDER BY case_id, timestamp
            LIMIT {limit}
        """, params={
            "tenant_id": tenant_id,
            "start_time": start_time,
            "end_time": end_time,
        })
        
        if result.is_success and result.row_count > 0:
            events = []
            for row in result.data:
                events.append(ProcessEvent(
                    case_id=row[0],
                    activity=row[1],
                    timestamp=row[2] if isinstance(row[2], datetime) else datetime.fromisoformat(str(row[2])),
                    resource=row[3],
                    duration_ms=row[4],
                    attributes=row[5] if isinstance(row[5], dict) else {},
                ))
            return events
        
        # Fallback: Extract from raw logs table
        logger.info("process_events table empty, extracting from logs...")
        return await self._extract_from_raw_logs(
            tenant_id, start_time, end_time, case_id_pattern, activity_field, limit
        )
    
    async def _extract_from_raw_logs(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
        case_id_pattern: Optional[str],
        activity_field: str,
        limit: int,
    ) -> List[ProcessEvent]:
        """Extract events from raw logs table using pattern matching."""
        # Try common case ID patterns in log messages
        case_patterns = [
            r"request_id[=:\s]+([a-zA-Z0-9\-]+)",
            r"transaction_id[=:\s]+([a-zA-Z0-9\-]+)",
            r"trace_id[=:\s]+([a-zA-Z0-9\-]+)",
            r"session[=:\s]+([a-zA-Z0-9\-]+)",
            r"order_id[=:\s]+([a-zA-Z0-9\-]+)",
        ]
        
        result = await self.analytics.execute(f"""
            SELECT 
                timestamp,
                host,
                app,
                message,
                severity
            FROM logs
            WHERE tenant_id = :tenant_id
              AND timestamp >= :start_time
              AND timestamp <= :end_time
            ORDER BY timestamp
            LIMIT {limit}
        """, params={
            "tenant_id": tenant_id,
            "start_time": start_time,
            "end_time": end_time,
        })
        
        if not result.is_success:
            logger.error(f"Failed to extract logs: {result.error}")
            return []
        
        events = []
        import re
        
        for row in result.data:
            timestamp, host, app, message, severity = row
            
            # Try to extract case ID from message
            case_id = None
            if case_id_pattern:
                match = re.search(case_id_pattern, message)
                if match:
                    case_id = match.group(1)
            else:
                for pattern in case_patterns:
                    match = re.search(pattern, message, re.IGNORECASE)
                    if match:
                        case_id = match.group(1)
                        break
            
            # Skip logs without case ID (can't correlate)
            if not case_id:
                continue
            
            # Use app as activity, or extract from message
            activity = app or "unknown"
            
            events.append(ProcessEvent(
                case_id=case_id,
                activity=activity,
                timestamp=timestamp if isinstance(timestamp, datetime) else datetime.fromisoformat(str(timestamp)),
                resource=host,
                attributes={"severity": severity, "message": message[:200]},
            ))
        
        logger.info(f"Extracted {len(events)} process events from logs")
        return events
    
    def group_into_traces(self, events: List[ProcessEvent]) -> List[ProcessTrace]:
        """Group events into process traces by case_id."""
        traces_dict: Dict[str, List[ProcessEvent]] = {}
        
        for event in events:
            if event.case_id not in traces_dict:
                traces_dict[event.case_id] = []
            traces_dict[event.case_id].append(event)
        
        traces = []
        for case_id, case_events in traces_dict.items():
            sorted_events = sorted(case_events, key=lambda e: e.timestamp)
            traces.append(ProcessTrace(case_id=case_id, events=sorted_events))
        
        return traces
    
    def discover_variants(self, traces: List[ProcessTrace]) -> List[ProcessVariant]:
        """Discover process variants (unique activity sequences)."""
        variant_stats: Dict[Tuple[str, ...], Dict] = {}
        
        for trace in traces:
            activity_seq = tuple(e.activity for e in trace.events)
            
            if activity_seq not in variant_stats:
                variant_stats[activity_seq] = {
                    "count": 0,
                    "total_duration": 0,
                    "examples": [],
                }
            
            stats = variant_stats[activity_seq]
            stats["count"] += 1
            stats["total_duration"] += trace.duration_ms
            if len(stats["examples"]) < 5:
                stats["examples"].append(trace.case_id)
        
        variants = []
        for activities, stats in sorted(
            variant_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        ):
            variants.append(ProcessVariant(
                activities=activities,
                case_count=stats["count"],
                avg_duration_ms=stats["total_duration"] / stats["count"] if stats["count"] > 0 else 0,
                example_case_ids=stats["examples"],
            ))
        
        return variants
    
    def export_to_xes(self, traces: List[ProcessTrace], process_name: str = "MithrilLog Process") -> str:
        """
        Export traces to XES (eXtensible Event Stream) format.
        
        XES is the standard format supported by:
        - Celonis
        - IBM Process Mining
        - ProM
        - Disco
        - Power Automate Process Mining
        """
        # Create root element
        log = ET.Element("log")
        log.set("xes.version", "1.0")
        log.set("xes.features", "nested-attributes")
        log.set("openxes.version", "1.0RC7")
        
        # Add standard extensions
        extensions = [
            ("Concept", "http://www.xes-standard.org/concept.xesext", "concept"),
            ("Lifecycle", "http://www.xes-standard.org/lifecycle.xesext", "lifecycle"),
            ("Time", "http://www.xes-standard.org/time.xesext", "time"),
            ("Organizational", "http://www.xes-standard.org/org.xesext", "org"),
        ]
        
        for name, uri, prefix in extensions:
            ext = ET.SubElement(log, "extension")
            ext.set("name", name)
            ext.set("uri", uri)
            ext.set("prefix", prefix)
        
        # Add global event attributes
        global_event = ET.SubElement(log, "global")
        global_event.set("scope", "event")
        
        for attr_name, attr_type in [
            ("concept:name", "string"),
            ("time:timestamp", "date"),
            ("lifecycle:transition", "string"),
        ]:
            attr = ET.SubElement(global_event, attr_type)
            attr.set("key", attr_name)
            attr.set("value", "")
        
        # Add process name
        name_attr = ET.SubElement(log, "string")
        name_attr.set("key", "concept:name")
        name_attr.set("value", process_name)
        
        # Add traces
        for trace in traces:
            trace_elem = ET.SubElement(log, "trace")
            
            # Case ID
            case_name = ET.SubElement(trace_elem, "string")
            case_name.set("key", "concept:name")
            case_name.set("value", trace.case_id)
            
            # Events
            for event in trace.events:
                event_elem = ET.SubElement(trace_elem, "event")
                
                # Activity name
                activity_name = ET.SubElement(event_elem, "string")
                activity_name.set("key", "concept:name")
                activity_name.set("value", event.activity)
                
                # Timestamp
                timestamp = ET.SubElement(event_elem, "date")
                timestamp.set("key", "time:timestamp")
                timestamp.set("value", event.timestamp.isoformat())
                
                # Lifecycle (complete by default)
                lifecycle = ET.SubElement(event_elem, "string")
                lifecycle.set("key", "lifecycle:transition")
                lifecycle.set("value", "complete")
                
                # Resource (if available)
                if event.resource:
                    resource = ET.SubElement(event_elem, "string")
                    resource.set("key", "org:resource")
                    resource.set("value", event.resource)
                
                # Duration (custom attribute)
                if event.duration_ms:
                    duration = ET.SubElement(event_elem, "int")
                    duration.set("key", "duration_ms")
                    duration.set("value", str(event.duration_ms))
                
                # Additional attributes
                for key, value in event.attributes.items():
                    if isinstance(value, (int, float)):
                        attr = ET.SubElement(event_elem, "float" if isinstance(value, float) else "int")
                    else:
                        attr = ET.SubElement(event_elem, "string")
                    attr.set("key", key)
                    attr.set("value", str(value))
        
        # Convert to string with declaration
        tree = ET.ElementTree(log)
        output = StringIO()
        output.write('<?xml version="1.0" encoding="UTF-8" ?>\n')
        tree.write(output, encoding="unicode", xml_declaration=False)
        
        return output.getvalue()
    
    async def get_process_summary(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Dict[str, Any]:
        """Get high-level process mining summary statistics."""
        events = await self.extract_events_from_logs(tenant_id, start_time, end_time)
        traces = self.group_into_traces(events)
        variants = self.discover_variants(traces)
        
        return {
            "tenant_id": tenant_id,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "statistics": {
                "total_events": len(events),
                "total_cases": len(traces),
                "unique_activities": len(set(e.activity for e in events)),
                "variant_count": len(variants),
            },
            "top_variants": [
                {
                    "activities": list(v.activities),
                    "case_count": v.case_count,
                    "avg_duration_ms": v.avg_duration_ms,
                }
                for v in variants[:10]
            ],
            "activity_frequency": self._count_activities(events),
        }
    
    def _count_activities(self, events: List[ProcessEvent]) -> Dict[str, int]:
        """Count frequency of each activity."""
        counts: Dict[str, int] = {}
        for event in events:
            counts[event.activity] = counts.get(event.activity, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True)[:20])


# Singleton instance
_process_mining_engine: Optional[ProcessMiningEngine] = None


def get_process_mining_engine() -> ProcessMiningEngine:
    """Get or create the singleton ProcessMiningEngine instance."""
    global _process_mining_engine
    if _process_mining_engine is None:
        _process_mining_engine = ProcessMiningEngine()
    return _process_mining_engine
