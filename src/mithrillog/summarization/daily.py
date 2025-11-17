from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..llm import LLMClient
from ..storage import JournalWriter
from .prompts import load_prompt_template


class DailySummarizer:
    def __init__(self, settings: Settings, journal: JournalWriter, llm: LLMClient) -> None:
        self.settings = settings
        self.journal = journal
        self.llm = llm
        self.hourly_dir = Path(settings.summary.report_dir) / "hourly"
        self.report_dir = Path(settings.summary.report_dir) / "daily"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.prompt = load_prompt_template(Path(settings.prompts.daily))

    def summarize_day(self, target: datetime) -> Dict[str, Any]:
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        stats_counter = Counter()
        severity_counter = Counter()
        host_counter = Counter()
        app_counter = Counter()
        hourly_links: List[Dict[str, Any]] = []
        highlights: List[Dict[str, Any]] = []

        for hour in range(24):
            hour_start = day_start + timedelta(hours=hour)
            report_path = self.hourly_dir / f"{hour_start:%Y/%m/%d/%H}.json"
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

        highlights_sorted = sorted(
            highlights, key=lambda item: item.get("occurrences", 1), reverse=True
        )[:50]

        stats_struct = {
            "total_events": stats_counter["total_events"],
            "unique_events": stats_counter["unique_events"],
            "by_severity": dict(severity_counter.most_common()),
            "top_hosts": dict(host_counter.most_common(10)),
            "top_apps": dict(app_counter.most_common(10)),
        }

        variables = {
            "day_start": day_start.isoformat(),
            "day_end": day_end.isoformat(),
            "stats_table": self._format_stats(stats_struct),
            "hourly_digest": self._format_hourly(hourly_links[-12:]),
            "highlight_table": self._format_highlights(highlights_sorted),
            "stats": stats_struct,
            "highlights": highlights_sorted,
        }

        summary_text = self.llm.generate(self.prompt, variables)

        report = {
            "day_start": day_start.isoformat(),
            "day_end": day_end.isoformat(),
            "summary": summary_text,
            "stats": stats_struct,
            "hourly_links": hourly_links,
            "highlights": highlights_sorted,
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

