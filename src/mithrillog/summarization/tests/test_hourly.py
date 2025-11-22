import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from mithrillog.summarization.hourly import HourlySummarizer

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.ingest.bucket_dir = "/tmp/buckets"
    settings.summary.report_dir = "/tmp/reports"
    settings.timezone = "UTC"
    settings.prompts.hourly = "prompts/hourly.txt"
    settings.prompts.anomaly = "prompts/anomaly.txt"
    settings.prompts.highlight_analysis = "prompts/highlight.txt"
    return settings

@pytest.fixture
def mock_journal():
    return MagicMock()

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.generate.return_value = "Mocked Summary"
    return llm

def test_hourly_summarizer_init(mock_settings, mock_journal, mock_llm):
    with patch("mithrillog.summarization.hourly.load_prompt_template", return_value="template"):
        summarizer = HourlySummarizer(mock_settings, mock_journal, mock_llm)
        assert summarizer.bucket_timezone == timezone.utc

def test_clean_message_truncation():
    long_msg = "A" * 200
    cleaned = HourlySummarizer._clean_message(long_msg)
    assert len(cleaned) <= 100
    assert cleaned.endswith("...")

def test_clean_message_json():
    json_msg = '{"c": "kernel", "msg": "Something happened"}'
    cleaned = HourlySummarizer._clean_message(json_msg)
    assert cleaned == "kernel: Something happened"

def test_format_stats():
    stats = {
        "total_events": 100,
        "unique_events": 10,
        "by_severity": {"error": 5, "info": 95},
        "top_hosts": {"host1": 50},
        "top_apps": {"app1": 50}
    }
    formatted = HourlySummarizer._format_stats(stats)
    assert "Total: 100" in formatted
    assert "Unique: 10" in formatted
    assert "Severity: error:5" in formatted
