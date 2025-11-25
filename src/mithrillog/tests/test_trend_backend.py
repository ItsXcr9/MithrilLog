import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from mithrillog.state_store import StateStore
from mithrillog.summarization.trend import TrendSummarizer
from mithrillog.config import Settings

@pytest.fixture
def state_store(tmp_path):
    db_path = tmp_path / "test.db"
    return StateStore(db_path)

def test_upsert_issues_batch(state_store):
    now = datetime.now(timezone.utc)
    issues = [
        ("p1", now, "error", "msg1"),
        ("p2", now, "warning", "msg2")
    ]
    
    state_store.upsert_issues_batch(issues)
    
    active = state_store.get_active_issues()
    assert len(active) == 2
    
    # Verify content
    p1 = next(i for i in active if i["pattern_id"] == "p1")
    assert p1["severity"] == "error"
    assert p1["sample_message"] == "msg1"
    
    # Update p1
    later = datetime.now(timezone.utc)
    state_store.upsert_issues_batch([("p1", later, "critical", "msg1_updated")])
    
    active = state_store.get_active_issues()
    assert len(active) == 2
    p1_updated = next(i for i in active if i["pattern_id"] == "p1")
    assert p1_updated["severity"] == "critical"
    assert p1_updated["sample_message"] == "msg1_updated"
    assert p1_updated["last_seen"] == later.isoformat()

def test_trend_summarizer_caching(tmp_path):
    settings = Settings()
    settings.summary.report_dir = tmp_path / "reports"
    
    journal = MagicMock()
    llm = MagicMock()
    state_store = MagicMock()
    
    summarizer = TrendSummarizer(settings, journal, llm, state_store)
    
    target = datetime(2023, 1, 1, tzinfo=timezone.utc)
    
    # 1. First run: Should generate report
    daily_report = {"highlights": []}
    llm.generate.return_value = "Trend summary"
    
    summarizer.summarize_trend(target, daily_report)
    
    assert llm.generate.called
    assert journal.write_summary.called
    
    # 2. Second run: Should use cache
    # We need to simulate the file existing. 
    # Since journal.write_summary writes to file, and we mocked it, the file won't exist unless we write it.
    # But summarizer checks file existence directly.
    
    report_path = summarizer.report_dir / "2023/01/01.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with report_path.open("w") as f:
        json.dump({"summary": "Cached summary"}, f)
        
    llm.reset_mock()
    journal.reset_mock()
    
    result = summarizer.summarize_trend(target, daily_report)
    
    assert not llm.generate.called
    assert result["summary"] == "Cached summary"
