import logging
import pytest
import structlog
from mithrillog.logging import LogAction, LogPattern, LogProcessor

def test_log_processor_suppress():
    patterns = [
        LogPattern(pattern="secret", action=LogAction.SUPPRESS)
    ]
    processor = LogProcessor(patterns)
    
    # Should be suppressed
    with pytest.raises(structlog.DropEvent):
        processor(None, None, {"event": "this is a secret message"})

    # Should pass through
    event = {"event": "this is a public message"}
    assert processor(None, None, event) == event

def test_log_processor_allow():
    patterns = [
        LogPattern(pattern="critical", action=LogAction.ALLOW),
        LogPattern(pattern="error", action=LogAction.SUPPRESS)
    ]
    processor = LogProcessor(patterns)
    
    # "critical error" should be allowed because "critical" matches first and is ALLOW
    event = {"event": "critical error occurred"}
    assert processor(None, None, event) == event

    # "simple error" should be suppressed because it doesn't match "critical" but matches "error"
    with pytest.raises(structlog.DropEvent):
        processor(None, None, {"event": "simple error occurred"})

def test_log_processor_reclassify():
    patterns = [
        LogPattern(
            pattern="timeout", 
            action=LogAction.RECLASSIFY, 
            new_level="WARNING",
            extra_fields={"type": "network_issue"}
        )
    ]
    processor = LogProcessor(patterns)
    
    event = {"event": "connection timeout", "level": "info"}
    processed_event = processor(None, None, event)
    
    assert processed_event["level"] == "warning"
    assert processed_event["type"] == "network_issue"
    assert processed_event["event"] == "connection timeout"

def test_log_processor_reclassify_and_suppress():
    # Test that reclassification happens but subsequent suppression can still occur
    # if we don't return early on reclassify.
    # In my implementation, I chose to continue after reclassify.
    patterns = [
        LogPattern(
            pattern="noisy", 
            action=LogAction.RECLASSIFY, 
            extra_fields={"tag": "noise"}
        ),
        LogPattern(pattern="ignore_noise", action=LogAction.SUPPRESS)
    ]
    processor = LogProcessor(patterns)
    
    # "noisy message" gets tagged, but not suppressed by the second pattern yet
    # unless the second pattern matches the message.
    
    # Case 1: Reclassify only
    event = {"event": "noisy message"}
    processed = processor(None, None, event)
    assert processed["tag"] == "noise"
    
    # Case 2: Reclassify then Suppress
    # If the message matches both
    patterns_2 = [
        LogPattern(pattern="bad", action=LogAction.RECLASSIFY, extra_fields={"mark": "seen"}),
        LogPattern(pattern="bad", action=LogAction.SUPPRESS)
    ]
    processor_2 = LogProcessor(patterns_2)
    
    with pytest.raises(structlog.DropEvent):
        processor_2(None, None, {"event": "bad thing"})

def test_log_processor_non_string_message():
    processor = LogProcessor([LogPattern(pattern="foo", action=LogAction.SUPPRESS)])
    event = {"event": 123}
    # Should not crash, just return event
    assert processor(None, None, event) == event
