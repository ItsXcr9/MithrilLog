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
from ..utils.time import get_timezone, minute_bucket_path
from .prompts import load_prompt_template

logger = logging.getLogger("mithrillog.summarization.hourly")


class HourlySummarizer:
    def __init__(self, settings: Settings, journal: JournalWriter, llm: LLMClient) -> None:
        self.settings = settings
        self.journal = journal
        self.llm = llm
        self.bucket_dir = Path(settings.ingest.bucket_dir)
        self.bucket_timezone = get_timezone(settings.timezone)
        self._needs_utc_fallback = self.bucket_timezone.key not in {"UTC", "Etc/UTC"}
        self.report_dir = Path(settings.summary.report_dir) / "hourly"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.prompt = load_prompt_template(Path(settings.prompts.hourly))
        self.anomaly_prompt = load_prompt_template(Path(settings.prompts.anomaly))
        self.highlight_prompt = load_prompt_template(Path(settings.prompts.highlight_analysis))

    def summarize_hour(self, target: datetime) -> Dict[str, Any]:
        start = target.replace(minute=0, second=0, microsecond=0)
        if start.tzinfo is None:
            start = start.replace(tzinfo=self.bucket_timezone)
        start = start.astimezone(self.bucket_timezone)
        end = start + timedelta(hours=1)

        # Check if summary already exists to prevent re-summarization
        report_path = self.report_dir / f"{start:%Y/%m/%d/%H}.json"
        if report_path.exists():
            logger.info("Hourly summary already exists for %s, skipping", start)
            with report_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)

        severity_counter: Counter[str] = Counter()
        host_counter: Counter[str] = Counter()
        app_counter: Counter[str] = Counter()
        host_app_counter: Counter[str] = Counter()
        total_events = 0
        unique_events = 0
        highlights: List[Dict[str, Any]] = []
        minute_rollup: List[Dict[str, Any]] = []

        # Aggregate pattern occurrences across all minutes
        pattern_aggregates: Dict[str, Dict[str, Any]] = {}
        pattern_occurrences: Counter[str] = Counter()
        
        for minute in range(60):
            bucket_time = start + timedelta(minutes=minute)
            bucket_meta_path = Path(
                minute_bucket_path(str(self.bucket_dir), bucket_time, tz=self.bucket_timezone)
            ).with_suffix(".meta.json")
            if not bucket_meta_path.exists() and self._needs_utc_fallback:
                legacy_path = Path(
                    minute_bucket_path(str(self.bucket_dir), bucket_time, tz=timezone.utc)
                ).with_suffix(".meta.json")
                if legacy_path.exists():
                    bucket_meta_path = legacy_path
                else:
                    continue
            if not bucket_meta_path.exists():
                continue
            with bucket_meta_path.open("r", encoding="utf-8") as handle:
                meta = json.load(handle)
            total_events += meta.get("total_events", 0)
            unique_events += meta.get("unique_events", 0)
            severity_counter.update(meta.get("severity", {}))
            host_counter.update(meta.get("hosts", {}))
            app_counter.update(meta.get("apps", {}))
            host_app_counter.update(meta.get("host_apps", {}))
            
            # Aggregate highlights by pattern_id
            for highlight in meta.get("highlights", []):
                pattern_id = highlight.get("pattern_id")
                if not pattern_id:
                    continue
                occ = highlight.get("occurrences", 1)
                pattern_occurrences[pattern_id] += occ
                
                # Keep the most recent sample for each pattern
                if pattern_id not in pattern_aggregates:
                    pattern_aggregates[pattern_id] = highlight.copy()
                    # Remove old source_hosts/apps, we'll rebuild them
                    pattern_aggregates[pattern_id]["source_hosts"] = Counter()
                    pattern_aggregates[pattern_id]["source_apps"] = Counter()
                
                # Merge source hosts/apps (they might be dicts or Counters)
                source_hosts = highlight.get("source_hosts") or {}
                source_apps = highlight.get("source_apps") or {}
                if isinstance(source_hosts, dict):
                    for host, count in source_hosts.items():
                        pattern_aggregates[pattern_id]["source_hosts"][host] += count
                if isinstance(source_apps, dict):
                    for app, count in source_apps.items():
                        pattern_aggregates[pattern_id]["source_apps"][app] += count
            
            minute_rollup.append(
                {
                    "minute": bucket_time.isoformat(),
                    "total": meta.get("total_events", 0),
                    "unique": meta.get("unique_events", 0),
                }
            )

        # Update aggregated highlights with total occurrences
        for pattern_id, highlight in pattern_aggregates.items():
            highlight["occurrences"] = pattern_occurrences[pattern_id]
            highlight["source_hosts"] = dict(highlight["source_hosts"].most_common(5))
            highlight["source_apps"] = dict(highlight["source_apps"].most_common(5))
        
        highlights = list(pattern_aggregates.values())
        
        # Severity priority: error > warning > crit > alert > emerg > notice > info > debug
        severity_priority = {
            "error": 0, "err": 0, "warning": 1, "warn": 1, "crit": 2, "critical": 2,
            "alert": 3, "emerg": 4, "emergency": 4, "notice": 5, "info": 6, "debug": 7
        }
        # Note: "err" is already in the map above, but ensure it's prioritized
        
        def sort_key(item: Dict[str, Any]) -> tuple:
            severity = item.get("severity", "info").lower()
            priority = severity_priority.get(severity, 6)
            occurrences = item.get("occurrences", 1)
            # Sort by priority first (lower is higher priority), then by occurrences (descending)
            return (priority, -occurrences)
        
        highlights_sorted = sorted(highlights, key=sort_key)
        # Show top 5 highlights (prioritizing errors/warnings)
        limited_highlights = highlights_sorted[:5]
        condensed_highlights = [
            {
                "severity": item.get("severity", "info"),
                "host": item.get("host", "unknown"),
                "app": item.get("app", "-"),
                "occurrences": item.get("occurrences", 1),
                "message": self._clean_message(item.get("message", ""))[:100],
                "sources": item.get("source_hosts", {}),
            }
            for item in limited_highlights
        ]
        # Show top 10 highlights for context (prioritizing errors/warnings)
        highlight_lines = [
            f"[{item.get('severity', 'info')}] {item.get('host', 'unknown')}/{item.get('app', '-')}"
            f" ({item.get('occurrences', 1)}x) - {self._clean_message(item.get('message', ''))[:160]}"
            for item in highlights_sorted[:10]
        ]
        highlight_context = "\n".join(highlight_lines).strip()

        stats_struct = {
            "total_events": total_events,
            "unique_events": unique_events,
            "by_severity": dict(severity_counter.most_common(5)),
            "top_hosts": dict(host_counter.most_common(5)),
            "top_apps": dict(app_counter.most_common(5)),
            "top_host_apps": dict(host_app_counter.most_common(5)),
        }

        variables = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "stats_table": self._clip_text(self._format_stats(stats_struct), max_chars=300),
            "minute_rollup": self._clip_text(self._format_minute_rollup(minute_rollup[-2:]), max_chars=200),
            "highlight_table": self._clip_text(self._format_highlights(limited_highlights), max_chars=300),
            "stats": stats_struct,
            "highlights": condensed_highlights,
        }

        summary_text = self.llm.generate(self.prompt, variables)
        anomaly_text = self.llm.generate(self.anomaly_prompt, variables)
        if highlight_context:
            highlight_analysis = self.llm.generate(
                self.highlight_prompt,
                {
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "highlights_text": highlight_context,
                },
            )
        else:
            highlight_analysis = "No notable highlights."

        report = {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "summary": summary_text,
            "anomalies": anomaly_text,
            "stats": stats_struct,
            "minute_rollup": minute_rollup,
            "highlights": highlights_sorted[:15],  # Show more highlights in report
            "highlight_analysis": highlight_analysis,
        }

        report_path = self.report_dir / f"{start:%Y/%m/%d/%H}.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        self.journal.write_summary(report_path, report)
        return report

    @staticmethod
    def _format_stats(stats: Dict[str, Any]) -> str:
        lines = [
            f"Total: {stats.get('total_events', 0)}, Unique: {stats.get('unique_events', 0)}",
        ]
        sev_items = list(stats.get("by_severity", {}).items())[:3]
        if sev_items:
            sev_str = ", ".join(f"{s}:{c}" for s, c in sev_items)
            lines.append(f"Severity: {sev_str}")
        host_items = list(stats.get("top_hosts", {}).items())[:3]
        if host_items:
            host_str = ", ".join(f"{h}:{c}" for h, c in host_items)
            lines.append(f"Hosts: {host_str}")
        app_items = list(stats.get("top_apps", {}).items())[:3]
        if app_items:
            app_str = ", ".join(f"{a}:{c}" for a, c in app_items)
            lines.append(f"Apps: {app_str}")
        return "\n".join(lines)

    @staticmethod
    def _format_minute_rollup(rollup: List[Dict[str, Any]]) -> str:
        if not rollup:
            return "No minute data."
        lines = ["Latest minutes:"]
        for entry in rollup:
            time_str = entry['minute'].split('T')[1][:5] if 'T' in entry['minute'] else entry['minute']
            lines.append(f"{time_str}: t={entry['total']} u={entry['unique']}")
        return "\n".join(lines)

    @staticmethod
    def _format_highlights(highlights: List[Dict[str, Any]]) -> str:
        if not highlights:
            return "No samples."
        lines = ["Samples:"]
        for item in highlights:
            host = item.get("host", "unknown")[:10]
            app = item.get("app", "-")[:8]
            severity = item.get("severity", "info")
            occ = item.get("occurrences", 1)
            message = HourlySummarizer._clean_message(item.get("message", ""))[:50]
            sources = item.get("sources") or item.get("source_hosts") or {}
            if sources:
                source_str = ", ".join(
                    f"{h}:{c}" for h, c in list(sources.items())[:3]
                )
                lines.append(f"[{severity}] {host}/{app} ({occ}x) – {message} | {source_str}")
            else:
                lines.append(f"[{severity}] {host}/{app} ({occ}x) – {message}")
        return "\n".join(lines)

    @staticmethod
    def _clean_message(message: str) -> str:
        # Remove syslog prefix if present
        if "] " in message:
            message = message.split("] ", 1)[-1]
        
        # Try to extract key info from JSON logs
        if message.strip().startswith("{"):
            try:
                import json
                data = json.loads(message)
                # MongoDB format: check nested attr.message.msg
                if "attr" in data and isinstance(data["attr"], dict):
                    attr = data["attr"]
                    if "message" in attr and isinstance(attr["message"], dict):
                        msg_data = attr["message"]
                        if "msg" in msg_data:
                            msg_text = str(msg_data["msg"])
                            # Extract key part (e.g., "saving checkpoint snapshot min: 162")
                            if len(msg_text) > 60:
                                # Take first meaningful part
                                parts = msg_text.split(",")
                                if parts:
                                    msg_text = parts[0]
                            return f"{data.get('c', '')}: {msg_text}"[:80]
                
                # Direct msg field
                if "msg" in data:
                    msg_val = data["msg"]
                    if isinstance(msg_val, str):
                        return msg_val[:80]
                    elif isinstance(msg_val, dict) and "msg" in msg_val:
                        return str(msg_val["msg"])[:80]
                
                # message field
                if "message" in data:
                    msg = data["message"]
                    if isinstance(msg, dict) and "msg" in msg:
                        return str(msg["msg"])[:80]
                    return str(msg)[:80]
                
                # MongoDB format: c + msg
                if "c" in data:
                    component = data.get("c", "")
                    msg_text = data.get("msg", "")
                    if msg_text:
                        return f"{component}: {msg_text}"[:80]
                    return component[:80]
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        
        # For very long messages, try to extract first meaningful part
        message = message.replace("  ", " ").strip()
        # If it's still very long, take first sentence or first 80 chars
        if len(message) > 100:
            # Try to find first sentence
            for sep in [". ", "! ", "? ", "\n", "; "]:
                if sep in message:
                    message = message.split(sep, 1)[0]
                    break
            # Final truncation
            if len(message) > 80:
                message = message[:77] + "..."
        
        return message

    @staticmethod
    def _clip_text(text: str, max_chars: int = 1200) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 30] + "\n... truncated ..."

