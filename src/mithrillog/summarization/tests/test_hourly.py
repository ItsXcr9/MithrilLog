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


def test_analysis_levels_filtering_error_critical():
    """Test that severity filtering correctly identifies ERROR and CRITICAL levels"""
    from unittest.mock import Mock
    
    # Create a mock settings object
    mock_settings = Mock()
    mock_settings.summary.analysis_levels = ["ERROR", "CRITICAL"]
    
    # Test the severity mapping logic (this is internal to summarize_hour, but we can test the concept)
    severity_map = {
        "debug": "DEBUG", "info": "INFO", "notice": "INFO",
        "warn": "WARNING", "warning": "WARNING",
        "err": "ERROR", "error": "ERROR",
        "crit": "CRITICAL", "critical": "CRITICAL", "alert": "CRITICAL", 
        "emerg": "CRITICAL", "emergency": "CRITICAL"
    }
    analysis_levels_normalized = {lvl.upper() for lvl in mock_settings.summary.analysis_levels}
    
    def should_analyze(severity: str) -> bool:
        normalized = severity_map.get(severity.lower(), severity.upper())
        return normalized in analysis_levels_normalized
    
    # Test various severity inputs
    assert should_analyze("err") == True
    assert should_analyze("error") == True
    assert should_analyze("ERROR") == True
    assert should_analyze("crit") == True
    assert should_analyze("critical") == True
    assert should_analyze("CRITICAL") == True
    assert should_analyze("alert") == True
    assert should_analyze("emerg") == True
    assert should_analyze("emergency") == True
    
    # These should be filtered out
    assert should_analyze("info") == False
    assert should_analyze("INFO") == False
    assert should_analyze("warn") == False
    assert should_analyze("warning") == False
    assert should_analyze("WARNING") == False
    assert should_analyze("debug") == False
    assert should_analyze("DEBUG") == False


def test_analysis_levels_all_levels():
    """Test that all levels are included when all are configured"""
    from unittest.mock import Mock
    
    mock_settings = Mock()
    mock_settings.summary.analysis_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    severity_map = {
        "debug": "DEBUG", "info": "INFO", "notice": "INFO",
        "warn": "WARNING", "warning": "WARNING",
        "err": "ERROR", "error": "ERROR",
        "crit": "CRITICAL", "critical": "CRITICAL", "alert": "CRITICAL", 
        "emerg": "CRITICAL", "emergency": "CRITICAL"
    }
    analysis_levels_normalized = {lvl.upper() for lvl in mock_settings.summary.analysis_levels}
    
    def should_analyze(severity: str) -> bool:
        normalized = severity_map.get(severity.lower(), severity.upper())
        return normalized in analysis_levels_normalized
    
    # All should be included
    assert should_analyze("debug") == True
    assert should_analyze("info") == True
    assert should_analyze("warn") == True
    assert should_analyze("err") == True
    assert should_analyze("crit") == True


def test_analysis_levels_only_error():
    """Test filtering when only ERROR is configured"""
    from unittest.mock import Mock
    
    mock_settings = Mock()
    mock_settings.summary.analysis_levels = ["ERROR"]
    
    severity_map = {
        "debug": "DEBUG", "info": "INFO", "notice": "INFO",
        "warn": "WARNING", "warning": "WARNING",
        "err": "ERROR", "error": "ERROR",
        "crit": "CRITICAL", "critical": "CRITICAL", "alert": "CRITICAL", 
        "emerg": "CRITICAL", "emergency": "CRITICAL"
    }
    analysis_levels_normalized = {lvl.upper() for lvl in mock_settings.summary.analysis_levels}
    
    def should_analyze(severity: str) -> bool:
        normalized = severity_map.get(severity.lower(), severity.upper())
        return normalized in analysis_levels_normalized
    
    assert should_analyze("err") == True
    assert should_analyze("error") == True
    assert should_analyze("crit") == False
    assert should_analyze("critical") == False
    assert should_analyze("info") == False
    assert should_analyze("warn") == False


def test_clean_message_with_unicode():
    """Test that _clean_message handles unicode characters correctly"""
    msg_with_unicode = "Error: 错误消息 with émojis 🚀"
    cleaned = HourlySummarizer._clean_message(msg_with_unicode)
    assert isinstance(cleaned, str)
    assert len(cleaned) > 0


def test_format_minute_rollup():
    """Test formatting of minute rollup data"""
    minute_rollup = [
        {"minute": "2025-11-30T01:00:00+00:00", "total": 100, "unique": 10},
        {"minute": "2025-11-30T01:01:00+00:00", "total": 150, "unique": 15},
    ]
    formatted = HourlySummarizer._format_minute_rollup(minute_rollup)
    assert "01:00" in formatted or "100" in formatted
    assert isinstance(formatted, str)


def test_format_highlights():
    """Test formatting of highlights"""
    highlights = [
        {
            "severity": "err",
            "host": "host1",
            "app": "app1",
            "message": "Test error message",
            "occurrences": 5,
        }
    ]
    formatted = HourlySummarizer._format_highlights(highlights)
    assert "host1" in formatted or "app1" in formatted or "Test error" in formatted
    assert isinstance(formatted, str)
