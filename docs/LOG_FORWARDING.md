# Log Forwarding Architecture

## Overview

MithrilLog has **TWO SEPARATE log forwarding mechanisms** that serve different purposes:

1. **Ingested Log Forwarding** (`forward_to_host` / `forward_to_port`) - Forward logs YOU RECEIVE
2. **Application Log Forwarding** (`remote_logging`) - Forward YOUR OWN application logs

---

## 1. Ingested Log Forwarding

### Purpose
Forward logs that MithrilLog **receives and processes** to another destination in real-time (e.g., for live tail, backup, or feeding another system).

### Configuration
```yaml
ingest:
  forward_to_host: null  # Hostname or IP to forward to
  forward_to_port: null  # Port to forward to
```

### How It Works
**Location**: [`ingest_server.py` lines 450-464](file:///Users/saeed/Library/Mobile%20Documents/com~apple~CloudDocs/saeed/MithrilLog/src/mithrillog/ingestion/ingest_server.py#L450-L464)

```python
# After processing each log event
if self.config.forward_to_host and self.config.forward_to_port:
    self._forward_log(record)

def _forward_log(self, record: dict) -> None:
    """Forward processed log record as JSON via UDP"""
    payload = json.dumps(record).encode("utf-8")
    self._udp_transport.sendto(
        payload, (self.config.forward_to_host, self.config.forward_to_port)
    )
```

### Data Format
- **Protocol**: UDP
- **Format**: JSON-encoded log records
- **Content**: Processed log with pattern_id, occurrences, normalized fields

### Example Record
```json
{
  "timestamp": "2025-11-28T10:00:00Z",
  "host": "server1",
  "app": "nginx",
  "severity": "error",
  "message": "Connection timeout",
  "pattern_id": "abc123...",
  "occurrences": 5,
  "source_hosts": {"server1": 3, "server2": 2}
}
```

### Use Cases
- **Live Tail**: Send to a WebSocket endpoint for real-time UI updates
- **Backup**: Forward to another MithrilLog instance
- **Integration**: Feed processed logs to external systems

### Historical Note: `forward_to_host: api` / `forward_to_port: 9999`

The old configuration:
```yaml
forward_to_host: api
forward_to_port: 9999
```

**Purpose**: Was likely intended to forward logs to the API service for live tail functionality.

**Problem**: 
- Port 9999 is the **Admin Panel API** (see `admin/app/main.py:696`)
- The admin API doesn't have a syslog/log ingestion endpoint
- It expects HTTP requests, not UDP JSON packets
- **Result**: Forwarded logs were discarded/ignored

**Current Status**: Disabled (`null`) because:
1. It was forwarding to the wrong service
2. We don't want to forward ALL ingested logs (creates a loop if forwarding to another MithrilLog)
3. Use `remote_logging` instead for self-monitoring

---

## 2. Application Log Forwarding (Remote Logging)

### Purpose
Send MithrilLog's **own application logs** (Python logging output) to a central syslog server for self-monitoring.

### Configuration
```yaml
remote_logging:
  enabled: true           # Enable/disable remote logging
  host: 65.109.200.75    # Central syslog server
  port: 5515              # Syslog port (5514 internal, 5515 external)
  protocol: udp           # udp or tcp
```

### How It Works
**Location**: [`logging.py` lines 112-123](file:///Users/saeed/Library/Mobile%20Documents/com~apple~CloudDocs/saeed/MithrilLog/src/mithrillog/logging.py#L112-L123)

```python
if remote_config and remote_config.enabled and remote_config.host:
    from logging.handlers import SysLogHandler
    import socket
    socktype = socket.SOCK_DGRAM if remote_config.protocol == "udp" else socket.SOCK_STREAM
    syslog_handler = SysLogHandler(
        address=(remote_config.host, remote_config.port),
        socktype=socktype
    )
    syslog_handler.setFormatter(formatter)
    root_logger.addHandler(syslog_handler)
```

### Data Format
- **Protocol**: Syslog (RFC 3164/5424)
- **Format**: JSON-formatted log messages
- **Handler**: Python `SysLogHandler`

### What Gets Sent
All Python application logs from:
- **Orchestrator**: Startup, scheduling, shutdown
- **Hourly Summarizer**: "Running hourly summary for...", errors
- **Daily Summarizer**: Daily report generation
- **Trend Analysis**: "Trend analysis processing X ERROR/CRITICAL highlights..."
- **Ingestion Server**: UDP/TCP server events
- **API Server**: HTTP requests, errors
- **LLM Client**: AI generation logs

### Example Application Logs
```json
{"asctime": "2025-11-28T10:09:00", "levelname": "INFO", "name": "mithrillog.orchestrator", "message": "Running hourly summary for 2025-11-28 09:00:00"}
{"asctime": "2025-11-28T10:09:05", "levelname": "INFO", "name": "mithrillog.summarization.trend", "message": "Trend analysis processing 15 ERROR/CRITICAL highlights out of 127 total highlights"}
```

---

## Comparison Table

| Feature | Ingested Log Forwarding | Application Log Forwarding |
|---------|------------------------|---------------------------|
| **Config Section** | `ingest.forward_to_*` | `remote_logging` |
| **Source** | Logs received from other systems | MithrilLog's own Python logs |
| **Protocol** | UDP (raw) | Syslog (UDP or TCP) |
| **Format** | JSON records | Syslog-formatted JSON |
| **Trigger** | After processing each log | Python logging events |
| **Use Case** | Backup, live tail, integration | Self-monitoring, dogfooding |
| **Current Status** | Disabled (`null`) | Enabled → 65.109.200.75:5515 |

---

## Best Practices

### Ingested Log Forwarding
✅ **DO**: Use for live tail to WebSocket endpoints  
✅ **DO**: Use for backup to secondary MithrilLog  
❌ **DON'T**: Forward to the same MithrilLog instance (creates loop)  
❌ **DON'T**: Send to HTTP endpoints (use UDP-compatible receivers)  

### Application Log Forwarding
✅ **DO**: Enable for production self-monitoring  
✅ **DO**: Use for centralized logging of all instances  
✅ **DO**: Monitor MithrilLog health with MithrilLog  
❌ **DON'T**: Disable in production (you need to see errors!)  

---

## Common Configurations

### Standalone Instance (No Forwarding)
```yaml
ingest:
  forward_to_host: null
  forward_to_port: null
remote_logging:
  enabled: false
```

### Self-Monitoring Setup (Current)
```yaml
ingest:
  forward_to_host: null  # Don't forward ingested logs
  forward_to_port: null
remote_logging:
  enabled: true          # Send app logs to central server
  host: 65.109.200.75
  port: 5515
  protocol: udp
```

### Full Forwarding (Caution!)
```yaml
ingest:
  forward_to_host: backup.example.com  # Forward ingested logs to backup
  forward_to_port: 5514
remote_logging:
  enabled: true                          # Also send app logs
  host: central.example.com
  port: 5514
  protocol: udp
```

---

## Troubleshooting

### Ingested Logs Not Forwarding
1. Check `forward_to_host` and `forward_to_port` are set
2. Verify destination accepts UDP JSON packets
3. Check firewall/network connectivity
4. Look for errors in `mithrillog.ingest` logs

### Application Logs Not Reaching Central Server
1. Verify `remote_logging.enabled: true`
2. Check `remote_logging.host` is reachable
3. Verify destination port accepts syslog (5514/5515)
4. Check if UDP or TCP protocol matches server
5. Look for: `"Failed to setup syslog handler for central logging"` error

### Logs Disappearing / Loop Detected
- **Cause**: `forward_to_host` pointing back to same instance
- **Solution**: Set `forward_to_host: null` or point to different server

---

## Migration Guide

### From Old Config (`api:9999`)
**Before** (doesn't work):
```yaml
forward_to_host: api
forward_to_port: 9999
```

**After** (for self-monitoring):
```yaml
forward_to_host: null
forward_to_port: null
remote_logging:
  enabled: true
  host: 65.109.200.75
  port: 5515
  protocol: udp
```

**Rationale**: 
- Port 9999 is admin panel, not a log receiver
- Use `remote_logging` for application logs
- Disable ingested log forwarding to avoid loops
