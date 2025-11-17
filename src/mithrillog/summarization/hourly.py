from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..llm import LLMClient
from ..storage import JournalWriter
from ..utils.time import minute_bucket_path
from .prompts import load_prompt_template


class HourlySummarizer:
    def __init__(self, settings: Settings, journal: JournalWriter, llm: LLMClient) -> None:
        self.settings = settings
        self.journal = journal
        self.llm = llm
        self.bucket_dir = Path(settings.ingest.bucket_dir)
        self.report_dir = Path(settings.summary.report_dir) / "hourly"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.prompt = load_prompt_template(Path(settings.prompts.hourly))
        self.anomaly_prompt = load_prompt_template(Path(settings.prompts.anomaly))

    def summarize_hour(self, target: datetime) -> Dict[str, Any]:
        start = target.replace(minute=0, second=0, microsecond=0)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

        severity_counter: Counter[str] = Counter()
        host_counter: Counter[str] = Counter()
        app_counter: Counter[str] = Counter()
        total_events = 0
        unique_events = 0
        highlights: List[Dict[str, Any]] = []
        minute_rollup: List[Dict[str, Any]] = []

        for minute in range(60):
            bucket_time = start + timedelta(minutes=minute)
            bucket_meta_path = Path(
                minute_bucket_path(str(self.bucket_dir), bucket_time)
            ).with_suffix(".meta.json")
            if not bucket_meta_path.exists():
                continue
            with bucket_meta_path.open("r", encoding="utf-8") as handle:
                meta = json.load(handle)
            total_events += meta.get("total_events", 0)
            unique_events += meta.get("unique_events", 0)
            severity_counter.update(meta.get("severity", {}))
            host_counter.update(meta.get("hosts", {}))
            app_counter.update(meta.get("apps", {}))
            highlights.extend(meta.get("highlights", []))
            minute_rollup.append(
                {
                    "minute": bucket_time.isoformat(),
                    "total": meta.get("total_events", 0),
                    "unique": meta.get("unique_events", 0),
                }
            )

        highlights_sorted = sorted(
            highlights, key=lambda item: item.get("occurrences", 1), reverse=True
        )
        limited_highlights = highlights_sorted[:5]
        condensed_highlights = [
            {
                "severity": item.get("severity", "info"),
                "host": item.get("host", "unknown"),
                "app": item.get("app", "-"),
                "occurrences": item.get("occurrences", 1),
                "message": self._clean_message(item.get("message", ""))[:160],
            }
            for item in limited_highlights
        ]

        stats_struct = {
            "total_events": total_events,
            "unique_events": unique_events,
            "by_severity": dict(severity_counter.most_common()),
            "top_hosts": dict(host_counter.most_common(10)),
            "top_apps": dict(app_counter.most_common(10)),
        }

        variables = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "stats_table": self._format_stats(stats_struct),
            "minute_rollup": self._clip_text(self._format_minute_rollup(minute_rollup[-5:])),
            "highlight_table": self._clip_text(self._format_highlights(limited_highlights)),
            "stats": stats_struct,
            "highlights": condensed_highlights,
        }

        summary_text = self.llm.generate(self.prompt, variables)
        anomaly_text = self.llm.generate(self.anomaly_prompt, variables)

        report = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "summary": summary_text,
            "anomalies": anomaly_text,
            "stats": stats_struct,
            "minute_rollup": minute_rollup,
            "highlights": highlights_sorted[:10],
        }

        report_path = self.report_dir / f"{start:%Y/%m/%d/%H}.json"
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
    def _format_minute_rollup(rollup: List[Dict[str, Any]]) -> str:
        if not rollup:
            return "No minute data available."
        lines = ["Minute rollup (latest 10):"]
        for entry in rollup:
            lines.append(
                f"  - {entry['minute']}: total={entry['total']} unique={entry['unique']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_highlights(highlights: List[Dict[str, Any]]) -> str:
        if not highlights:
            return "No highlight samples captured."
        lines = ["Samples:"]
        for item in highlights:
            host = item.get("host", "unknown")
            app = item.get("app", "-")
            severity = item.get("severity", "info")
            occ = item.get("occurrences", 1)
            message = HourlySummarizer._clean_message(item.get("message", ""))
            lines.append(
                f"  - [{severity}] {host}/{app} ({occ}x): {message[:200]}"
            )
        return "\n".join(lines)

    @staticmethod
    def _clean_message(message: str) -> str:
        if "] " in message:
            message = message.split("] ", 1)[-1]
        return message.replace("  ", " ").strip()

    @staticmethod
    def _clip_text(text: str, max_chars: int = 1200) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 30] + "\n... truncated ..."

