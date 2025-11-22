import pytest
from datetime import datetime, timezone
from mithrillog.ingestion.ingest_server import LogEvent, parse_syslog, _mask_variable_tokens

def test_mask_variable_tokens():
    # Test IP masking
    assert _mask_variable_tokens("Connection from 192.168.1.1") == "Connection from IP"
    
    # Test UUID masking
    assert _mask_variable_tokens("Session 123e4567-e89b-12d3-a456-426614174000 started") == "Session UUID started"
    
    # Test MAC masking
    assert _mask_variable_tokens("Device 00:1A:2B:3C:4D:5E connected") == "Device MAC connected"
    
    # Test Hex masking
    assert _mask_variable_tokens("Memory at 0x7fff5fbff7c0") == "Memory at 0xHEX"
    
    # Test Number masking
    assert _mask_variable_tokens("Processed 12345 items") == "Processed N items"

def test_log_event_normalization():
    event = LogEvent(
        timestamp=datetime.now(timezone.utc),
        host="test-host",
        app="test-app",
        severity="info",
        facility="user",
        message="User 123 logged in at 2023-10-27 10:00:00",
        raw="raw log",
        transport="tcp"
    )
    
    # Should mask ID and timestamp
    normalized = event.normalize_message()
    assert "User N logged in at TIMESTAMP" in normalized or "User N logged in at" in normalized

def test_syslog_parsing_rfc3164():
    # RFC3164: <PRI>TIMESTAMP HOST TAG: MESSAGE
    raw = b"<34>Oct 11 22:14:15 mymachine su: 'su root' failed for lonvick on /dev/pts/8"
    event = parse_syslog(raw, "127.0.0.1", "udp")
    
    assert event.app == "su"
    assert event.host == "mymachine"
    assert event.severity == "crit"  # 34 -> facility 4 (auth), severity 2 (crit)
    assert event.message == "'su root' failed for lonvick on /dev/pts/8"

def test_syslog_parsing_no_header():
    # Just a raw message
    raw = b"Simple log message"
    event = parse_syslog(raw, "192.168.1.5", "tcp")
    
    assert event.host == "192.168.1.5"
    assert event.message == "Simple log message"
    assert event.severity == "info"

def test_json_log_normalization():
    json_msg = '{"c": "kernel", "msg": "Out of memory: Kill process 1234 (node) score 500"}'
    event = LogEvent(
        timestamp=datetime.now(timezone.utc),
        host="host",
        app="app",
        severity="err",
        facility="user",
        message=json_msg,
        raw=json_msg,
        transport="tcp"
    )
    
    normalized = event.normalize_message()
    # Should extract component and normalize numbers
    assert normalized == "kernel:Out of memory: Kill process N (node) score N"
