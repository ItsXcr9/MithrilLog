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
        
        # 1. Identify today's patterns from daily report highlights
        today_patterns = set()
        highlights = daily_report.get("highlights", [])
        
        new_issues_list = []
        ongoing_issues_list = []
        
        # We need to reconstruct pattern_ids or rely on what's in the report.
        # The daily report highlights usually contain 'pattern_id' if it was preserved,
        # but let's check if it is. If not, we might need to re-derive or just use the message/severity as key.
        # Looking at ingest_server.py, 'pattern_id' IS stored in the record.
        # Looking at daily.py, it passes 'highlights' which are records.
        # So 'pattern_id' should be there.
        
        for item in highlights:
            pattern_id = item.get("pattern_id")
            if not pattern_id:
                # Fallback if pattern_id is missing (shouldn't happen with new ingestion)
                continue
                
            today_patterns.add(pattern_id)
            severity = item.get("severity", "info")
            message = item.get("message", "")
            
            # Check if it's new or ongoing
            # We check the DB *before* upserting to know the previous state
            # Actually, upsert handles state update. We can query first.
            # Optimization: Fetch all active issues first.
            
            # For simplicity, let's just upsert and check first_seen vs today.
            # But we need to know if it WAS active before today.
            
            # Let's just upsert everything seen today.
            self.state_store.upsert_issue(
                pattern_id=pattern_id,
                seen_at=day_start, # Use day_start as the "seen" time for daily granularity
                severity=severity,
                sample_message=message
            )

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
            msg = i.get("sample_message", "")[:100]
            lines.append(f"- [{sev}] {msg}")
        if len(issues) > 10:
            lines.append(f"... and {len(issues) - 10} more.")
        return "\n".join(lines)
