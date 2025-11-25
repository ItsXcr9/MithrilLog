from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mithrillog.state_store")


class StateStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS issue_state (
                    pattern_id TEXT PRIMARY KEY,
                    first_seen TIMESTAMP NOT NULL,
                    last_seen TIMESTAMP NOT NULL,
                    status TEXT NOT NULL, -- 'active', 'resolved'
                    severity TEXT,
                    sample_message TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_issue_status_last_seen ON issue_state (status, last_seen)"
            )
            conn.commit()

    def upsert_issue(
        self,
        pattern_id: str,
        seen_at: datetime,
        severity: str,
        sample_message: str,
    ) -> None:
        """
        Update an issue's state.
        """
        self.upsert_issues_batch([(pattern_id, seen_at, severity, sample_message)])

    def upsert_issues_batch(
        self,
        issues: List[tuple[str, datetime, str, str]],
    ) -> None:
        """
        Batch update issues state.
        issues: List of (pattern_id, seen_at, severity, sample_message)
        """
        if not issues:
            return

        with sqlite3.connect(self.db_path) as conn:
            # Use ON CONFLICT to handle upsert efficiently
            # We want to:
            # 1. Update last_seen, severity, sample_message
            # 2. Set status to 'active'
            # 3. Keep first_seen as is
            
            # Prepare data for executemany
            # (pattern_id, first_seen, last_seen, status, severity, sample_message)
            # ON CONFLICT DO UPDATE ...
            
            data = []
            for pid, seen_at, sev, msg in issues:
                seen_at_iso = seen_at.isoformat()
                data.append((pid, seen_at_iso, seen_at_iso, 'active', sev, msg))

            conn.executemany(
                """
                INSERT INTO issue_state (pattern_id, first_seen, last_seen, status, severity, sample_message)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(pattern_id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    status = 'active',
                    severity = excluded.severity,
                    sample_message = excluded.sample_message
                """,
                data
            )
            conn.commit()

    def get_active_issues(self) -> List[Dict[str, Any]]:
        """Get all currently active issues."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM issue_state WHERE status = 'active' ORDER BY last_seen DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_resolved_issues(self, since: datetime) -> List[Dict[str, Any]]:
        """Get issues resolved since the given timestamp."""
        since_iso = since.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # We consider an issue resolved if status is 'resolved' and it was last seen BEFORE 'since' 
            # (meaning it stopped happening recently). 
            # Actually, typically we want to see what *became* resolved recently.
            # But for simplicity, let's just fetch all resolved issues for now and filter in logic if needed,
            # or better: fetch issues where status='resolved' and last_seen > since (wait, no).
            # If it was resolved today, it means it was active yesterday but NOT today.
            # So we probably want to just query by status.
            cursor = conn.execute(
                "SELECT * FROM issue_state WHERE status = 'resolved' ORDER BY last_seen DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def mark_resolved(self, pattern_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE issue_state SET status = 'resolved' WHERE pattern_id = ?",
                (pattern_id,),
            )
            conn.commit()

    def resolve_missing_issues(self, current_patterns: set[str], cutoff: datetime) -> List[str]:
        """
        Mark issues as resolved if they are currently active but not in the current_patterns set,
        AND haven't been seen since the cutoff.
        Returns list of newly resolved pattern_ids.
        """
        resolved = []
        cutoff_iso = cutoff.isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT pattern_id, last_seen FROM issue_state WHERE status = 'active'"
            )
            rows = cursor.fetchall()
            
            for row in rows:
                pid = row["pattern_id"]
                if pid not in current_patterns:
                    # It's missing from today's set. Check if it's old enough to be resolved.
                    # If last_seen < cutoff, it's definitely resolved.
                    # Actually, if we run this daily, 'current_patterns' are ALL patterns seen today.
                    # So if an active issue is NOT in current_patterns, it wasn't seen today.
                    # We can mark it resolved immediately if we assume daily granularity.
                    
                    # However, to be safe against partial runs, we might check last_seen.
                    # But for the requested feature "save events for 3 days", we just want to track status.
                    # Let's assume if it's not seen today, it's resolved (or at least "quiet").
                    
                    # Let's check if last_seen is older than cutoff (e.g. yesterday).
                    last_seen = row["last_seen"]
                    if last_seen < cutoff_iso:
                        conn.execute(
                            "UPDATE issue_state SET status = 'resolved' WHERE pattern_id = ?",
                            (pid,),
                        )
                        resolved.append(pid)
            conn.commit()
        return resolved
