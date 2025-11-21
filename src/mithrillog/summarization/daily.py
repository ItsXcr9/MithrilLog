from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..llm import LLMClient
from ..storage import JournalWriter
from ..utils.time import get_timezone
from .prompts import load_prompt_template

logger = logging.getLogger("mithrillog.summarization.daily")


class DailySummarizer:
    def __init__(self, settings: Settings, journal: JournalWriter, llm: LLMClient) -> None:
        self.settings = settings
        self.journal = journal
        self.llm = llm
        self.hourly_dir = Path(settings.summary.report_dir) / "hourly"
        self.report_dir = Path(settings.summary.report_dir) / "daily"
        self.bucket_timezone = get_timezone(settings.timezone)
        self._needs_utc_fallback = self.bucket_timezone.key not in {"UTC", "Etc/UTC"}
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.prompt = load_prompt_template(Path(settings.prompts.daily))

    def summarize_day(self, target: datetime) -> Dict[str, Any]:
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=self.bucket_timezone)
        day_start = day_start.astimezone(self.bucket_timezone)
        day_end = day_start + timedelta(days=1)

        # Check if summary already exists to prevent re-summarization
        report_path = self.report_dir / f"{day_start:%Y/%m/%d}.json"
        if report_path.exists():
            logger.info("Daily summary already exists for %s, skipping", day_start)
            with report_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

        ERROR_SEVERITIES = {"emerg", "alert", "crit", "err"}
        stats_counter = Counter()
        severity_counter = Counter()
        host_counter = Counter()
        app_counter = Counter()
        hourly_links: List[Dict[str, Any]] = []
        highlights: List[Dict[str, Any]] = []
        notable_incidents: List[Dict[str, Any]] = []

        for hour in range(24):
            hour_start = day_start + timedelta(hours=hour)
            report_path = self.hourly_dir / f"{hour_start:%Y/%m/%d/%H}.json"
            if not report_path.exists() and self._needs_utc_fallback:
                legacy_path = self.hourly_dir / f"{hour_start.astimezone(timezone.utc):%Y/%m/%d/%H}.json"
                if legacy_path.exists():
                    report_path = legacy_path
                else:
                    continue
            if not report_path.exists():
                continue
            with report_path.open("r", encoding="utf-8") as handle:
                report = json.load(handle)
            stats = report.get("stats", {})
            stats_counter["total_events"] += stats.get("total_events", 0)
            stats_counter["unique_events"] += stats.get("unique_events", 0)
            severity_counter.update(stats.get("by_severity", {}))
            host_counter.update(stats.get("top_hosts", {}))
            app_counter.update(stats.get("top_apps", {}))
            hourly_links.append(
                {
                    "hour": hour_start.isoformat(),
                    "summary": report.get("summary", ""),
                    "anomalies": report.get("anomalies", ""),
                }
            )
            highlights.extend(report.get("highlights", []))
            
            # Identify Notable Incidents (hours with errors)
            severity_counts = stats.get("by_severity", {})
            error_total = sum(
                count for sev, count in severity_counts.items() if sev in ERROR_SEVERITIES
            )
            if error_total > 0:
                error_highlights = [
                    {
                        "severity": item.get("severity", "info"),
                        "host": item.get("host", "unknown"),
                        "app": item.get("app", "-"),
                        "occurrences": item.get("occurrences", 1),
                        "message": item.get("message", ""),
                    }
                    for item in report.get("highlights", [])
                    if item.get("severity") in ERROR_SEVERITIES
                ]
                notable_incidents.append(
                    {
                        "window_start": report.get("window_start"),
                        "window_end": report.get("window_end"),
                        "total_errors": error_total,
                        "severity_breakdown": {
                            sev: severity_counts.get(sev, 0)
                            for sev in ERROR_SEVERITIES
                            if severity_counts.get(sev, 0) > 0
                        },
                        "highlights": error_highlights[:4],
                    }
                )

        # Severity priority: error > warning > crit > alert > emerg > notice > info > debug
        # Same priority as hourly summaries for consistency
        severity_priority = {
            "error": 0, "err": 0, "warning": 1, "warn": 1, "crit": 2, "critical": 2,
            "alert": 3, "emerg": 4, "emergency": 4, "notice": 5, "info": 6, "debug": 7
        }
        
        def sort_key(item: Dict[str, Any]) -> tuple:
            severity = item.get("severity", "info").lower()
            priority = severity_priority.get(severity, 6)
            occurrences = item.get("occurrences", 1)
            # Sort by priority first (lower is higher priority), then by occurrences (descending)
            return (priority, -occurrences)
        
        highlights_sorted = sorted(highlights, key=sort_key)
        limited_highlights = highlights_sorted[:15]
        condensed_highlights = [
            {
                "severity": item.get("severity", "info"),
                "host": item.get("host", "unknown"),
                "app": item.get("app", "-"),
                "occurrences": item.get("occurrences", 1),
                "message": (item.get("message", "") or "")[:200],
            }
            for item in limited_highlights
        ]

        stats_struct = {
            "total_events": stats_counter["total_events"],
            "unique_events": stats_counter["unique_events"],
            "by_severity": dict(severity_counter.most_common()),
            "top_hosts": dict(host_counter.most_common(10)),
            "top_apps": dict(app_counter.most_common(10)),
        }

        # Format Notable Incidents for prompt
        notable_incidents_text = self._format_notable_incidents(notable_incidents)

        variables = {
            "day_start": day_start.isoformat(),
            "day_end": day_end.isoformat(),
            "hourly_digest": self._format_hourly(hourly_links[-12:]),
            "notable_incidents": notable_incidents_text,
            "stats": stats_struct,
            "highlights": condensed_highlights,
        }

        summary_text = self.llm.generate(self.prompt, variables)

        report = {
            "day_start": day_start.isoformat(),
            "day_end": day_end.isoformat(),
            "summary": summary_text,
            "stats": stats_struct,
            "hourly_links": hourly_links,
            "highlights": highlights_sorted[:30],
            "notable_incidents": notable_incidents,
        }

        report_path = self.report_dir / f"{day_start:%Y/%m/%d}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal.write_summary(report_path, report)
        return report

    @staticmethod
    def _format_stats(stats: Dict[str, Any]) -> str:
        lines = [
            f"Total events: {stats.get('total_events', 0)}",
            f"Unique events: {stats.get('unique_events', 0)}",
            "By severity:",
        ]
        for severity, count in stats.get("by_severity", {}).items():
            lines.append(f"  - {severity}: {count}")
        lines.append("Top hosts:")
        for host, count in stats.get("top_hosts", {}).items():
            lines.append(f"  - {host}: {count}")
        lines.append("Top apps:")
        for app, count in stats.get("top_apps", {}).items():
            lines.append(f"  - {app}: {count}")
        return "\n".join(lines)

    @staticmethod
    def _format_hourly(entries: List[Dict[str, Any]]) -> str:
        if not entries:
            return "No hourly summaries available."
        lines = ["Hourly highlights (latest 12):"]
        for entry in entries:
            hour = entry["hour"]
            summary = entry.get("summary", "")
            lines.append(f"  - {hour}: {summary[:160]}")
        return "\n".join(lines)

    @staticmethod
    def _format_highlights(highlights: List[Dict[str, Any]]) -> str:
        if not highlights:
            return "No daily highlights."
        lines = ["Top samples:"]
        for item in highlights[:30]:
            host = item.get("host", "unknown")
            app = item.get("app", "-")
            severity = item.get("severity", "info")
            occ = item.get("occurrences", 1)
            message = item.get("message", "")
            lines.append(f"  - [{severity}] {host}/{app} ({occ}x): {message[:200]}")
        return "\n".join(lines)

    @staticmethod
    def _format_notable_incidents(incidents: List[Dict[str, Any]]) -> str:
        if not incidents:
            return "No notable incidents (error-level events) occurred during this day."
        lines = [f"Notable Incidents ({len(incidents)} hours with errors):"]
        for incident in incidents:
            window_start = incident.get("window_start", "")
            window_end = incident.get("window_end", "")
            total_errors = incident.get("total_errors", 0)
            severity_breakdown = incident.get("severity_breakdown", {})
            highlights = incident.get("highlights", [])
            
            severity_list = ", ".join([f"{sev}: {count}" for sev, count in severity_breakdown.items()])
            lines.append(f"\n  Time window: {window_start} → {window_end}")
            lines.append(f"  Total errors: {total_errors}")
            if severity_list:
                lines.append(f"  Severity breakdown: {severity_list}")
            if highlights:
                top_error = highlights[0]
                lines.append(f"  Top error: [{top_error.get('severity', 'err')}] {top_error.get('host', 'unknown')}/{top_error.get('app', '-')} - {top_error.get('message', '')[:150]}")
        return "\n".join(lines)

