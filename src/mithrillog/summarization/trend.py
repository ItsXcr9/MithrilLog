from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from ..config import Settings
from ..llm import LLMClient
from ..state_store import StateStore
from ..storage import JournalWriter
from ..utils.time import get_timezone
from .prompts import load_prompt_template

logger = logging.getLogger("mithrillog.summarization.trend")


class TrendSummarizer:
    def __init__(
        self,
        settings: Settings,
        journal: JournalWriter,
        llm: LLMClient,
        state_store: StateStore,
    ) -> None:
        self.settings = settings
        self.journal = journal
        self.llm = llm
        self.state_store = state_store
        self.report_dir = Path(settings.summary.report_dir) / "trend"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.prompt = load_prompt_template(Path(settings.prompts.trend))
        self.timezone = get_timezone(settings.timezone)

    def summarize_trend(self, target: datetime, daily_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a trend report based on the daily report and historical state.
        """
        day_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        if day_start.tzinfo is None:
            day_start = day_start.replace(tzinfo=self.timezone)
        
        report_path = self.report_dir / f"{day_start:%Y/%m/%d}.json"
        
        # Optimization: Check if report already exists
        # If it exists and we are not forcing a re-run (which we assume we aren't unless specified),
        # we could return it. However, daily summaries might be re-run.
        # Let's assume if it exists and is recent enough, we skip?
        # Actually, for "trend", it depends on the daily summary. If daily summary changed, trend should change.
        # But trend is expensive (LLM).
        # Let's check if we have a report for this day.
        if report_path.exists():
            try:
                with report_path.open("r") as f:
                    existing_report = json.load(f)
                logger.info("Trend report for %s already exists, skipping generation.", day_start)
                return existing_report
            except Exception:
                logger.warning("Failed to load existing trend report, regenerating.")

        # 1. Identify today's patterns from daily report highlights
        # TREND ANALYSIS: Only process ERROR and CRITICAL levels
        ERROR_CRITICAL_SEVERITIES = {"err", "error", "crit", "critical", "alert", "emerg", "emergency"}
        
        today_patterns = set()
        highlights = daily_report.get("highlights", [])
        
        # Filter to only ERROR/CRITICAL highlights for trend analysis
        error_critical_highlights = [
            h for h in highlights 
            if h.get("severity", "").lower() in ERROR_CRITICAL_SEVERITIES
        ]
        
        logger.info(
            "Trend analysis processing %d ERROR/CRITICAL highlights out of %d total highlights",
            len(error_critical_highlights), len(highlights)
        )
        
        issues_to_upsert = []
        
        for item in error_critical_highlights:
            pattern_id = item.get("pattern_id")
            if not pattern_id:
                continue
                
            today_patterns.add(pattern_id)  # pattern_id ensures unique event detection
            severity = item.get("severity", "info")
            message = item.get("message", "")
            
            issues_to_upsert.append((pattern_id, day_start, severity, message))
            
        # Batch upsert
        if issues_to_upsert:
            self.state_store.upsert_issues_batch(issues_to_upsert)

        # 2. Resolve missing issues
        # Mark issues as resolved if they were active but NOT seen today.
        # We assume 'target' is the day we are summarizing.
        # Any active issue not in 'today_patterns' is effectively resolved (for now).
        resolved_ids = self.state_store.resolve_missing_issues(today_patterns, day_start)
        
        # 3. Fetch lists for the report
        # We want:
        # - New: First seen today
        # - Ongoing: Active, first seen < today
        # - Resolved: Status resolved, last seen recently (e.g. yesterday)
        
        active_issues = self.state_store.get_active_issues()
        day_start_iso = day_start.isoformat()
        
        new_issues = []
        ongoing_issues = []
        
        for issue in active_issues:
            if issue["first_seen"] >= day_start_iso:
                new_issues.append(issue)
            else:
                ongoing_issues.append(issue)
                
        # For resolved, we want those resolved *just now* (i.e. in step 2)
        # OR those resolved recently.
        # The resolve_missing_issues returns IDs. Let's fetch details for them.
        # Or just fetch all resolved issues and filter by last_seen >= yesterday.
        yesterday = day_start - timedelta(days=1)
        yesterday_iso = yesterday.isoformat()
        
        all_resolved = self.state_store.get_resolved_issues(yesterday)
        # Filter to relevant ones (e.g. last seen recently)
        recent_resolved = [
            i for i in all_resolved 
            if i["last_seen"] >= yesterday_iso
        ]
        
        # 4. Generate LLM Report
        variables = {
            "report_date": day_start.strftime("%Y-%m-%d"),
            "new_issues": self._format_issues(new_issues),
            "ongoing_issues": self._format_issues(ongoing_issues),
            "resolved_issues": self._format_issues(recent_resolved),
        }
        
        trend_summary = self.llm.generate(self.prompt, variables)
        
        report = {
            "date": day_start_iso,
            "summary": trend_summary,
            "new_count": len(new_issues),
            "ongoing_count": len(ongoing_issues),
            "resolved_count": len(recent_resolved),
            "details": {
                "new": new_issues,
                "ongoing": ongoing_issues,
                "resolved": recent_resolved
            }
        }
        
        report_path = self.report_dir / f"{day_start:%Y/%m/%d}.json"
        self.journal.write_summary(report_path, report)
        
        return report

    def _format_issues(self, issues: List[Dict[str, Any]]) -> str:
        if not issues:
            return "None."
        lines = []
        for i in issues[:10]: # Limit to 10
            sev = i.get("severity", "info")
            msg = i.get("sample_message", "")[:500]
            lines.append(f"- [{sev}] {msg}")
        if len(issues) > 10:
            lines.append(f"... and {len(issues) - 10} more.")
        return "\n".join(lines)
