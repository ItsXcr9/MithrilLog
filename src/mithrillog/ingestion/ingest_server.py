from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
from asyncio import AbstractEventLoop
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from ..config import IngestConfig
from ..storage import JournalWriter
from ..utils.time import ensure_timezone, floor_to_minute, get_timezone, utc_now
from .dedupe import BloomDeduper, ReservoirSampler


ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})"
)
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HEX_RUN_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
QUOTED_STR_RE = re.compile(r'"[^"]{5,}"')
MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")


def _mask_variable_tokens(text: str) -> str:
    text = UUID_RE.sub("UUID", text)
    text = MAC_RE.sub("MAC", text)
    text = IP_RE.sub("IP", text)
    text = HEX_RUN_RE.sub("HEX", text)
    text = QUOTED_STR_RE.sub('"STR"', text)
    text = re.sub(r"\b0x[0-9a-fA-F]+\b", "0xHEX", text)
    text = re.sub(r"\b\d+\b", "N", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class LogEvent(BaseModel):
    timestamp: datetime
    host: str
    app: str
    severity: str
    facility: str
    message: str
    raw: str
    transport: str

    def normalize_message(self) -> str:
        """Normalize message to extract pattern, removing variable fields like timestamps and numbers."""
        msg = self.message
        
        # Try to parse as JSON (MongoDB logs, structured logs)
        if msg.strip().startswith("{"):
            try:
                data = json.loads(msg)
                # Extract component and message type
                component = data.get("c", "")
                msg_text = ""
                
                # Handle nested MongoDB format: attr.message.msg
                if "attr" in data and isinstance(data["attr"], dict):
                    attr = data["attr"]
                    if "message" in attr and isinstance(attr["message"], dict):
                        msg_data = attr["message"]
                        if "msg" in msg_data:
                            msg_text = str(msg_data["msg"])
                # Direct msg field
                elif "msg" in data:
                    msg_val = data["msg"]
                    if isinstance(msg_val, str):
                        msg_text = msg_val
                    elif isinstance(msg_val, dict) and "msg" in msg_val:
                        msg_text = str(msg_val["msg"])
                
                # Normalize the message text: remove numbers, timestamps, IDs
                # First, extract the core message pattern before normalization
                # For MongoDB checkpoint: "saving checkpoint snapshot min: N, snapshot max: N..."
                # We want: "saving checkpoint snapshot min: N, snapshot max: N snapshot count: N..."
                # Replace all numbers with N (but keep the structure)
                msg_text = re.sub(r'\b\d+\b', 'N', msg_text)
                # Remove timestamp tuples like "(0, 0)"
                msg_text = re.sub(r'\(N, N\)', '', msg_text)
                # Remove specific timestamp fields
                msg_text = re.sub(r'ts_sec:N|ts_usec:N', '', msg_text)
                msg_text = re.sub(r'oldest timestamp:\s*\(N, N\)', 'oldest timestamp: (N, N)', msg_text)
                msg_text = re.sub(r'meta checkpoint timestamp:\s*\(N, N\)', 'meta checkpoint timestamp: (N, N)', msg_text)
                # Remove thread IDs and session names
                msg_text = re.sub(r'0x[0-9a-fA-F]+', '0xHEX', msg_text)
                msg_text = re.sub(r'thread:"[^"]*"', '', msg_text)
                msg_text = re.sub(r'session_name:"[^"]*"', '', msg_text)
                # Remove extra colons and commas
                msg_text = re.sub(r',\s*,', ',', msg_text)  # double commas
                msg_text = re.sub(r'\s+', ' ', msg_text)  # multiple spaces
                
                # Clean up extra spaces
                msg_text = ' '.join(msg_text.split())
                msg_text = _mask_variable_tokens(msg_text)
                
                if component and msg_text:
                    return f"{component}:{msg_text}"
                elif component:
                    return component
                elif msg_text:
                    return msg_text
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        
        # For non-JSON messages, normalize by removing numbers and timestamps
        normalized = msg
        # Replace numbers with N
        normalized = re.sub(r'\d+', 'N', normalized)
        # Remove common timestamp patterns
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*[+-]\d{2}:\d{2}', 'TIMESTAMP', normalized)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*', 'TIMESTAMP', normalized)
        # Clean up extra spaces
        normalized = ' '.join(normalized.split())
        return _mask_variable_tokens(normalized)

    def _pattern_payload(self) -> dict:
        normalized_msg = self.normalize_message()
        return {
            "severity": self.severity,
            "facility": self.facility,
            "message": normalized_msg,
        }

    def dedupe_key(self) -> bytes:
        return json.dumps(self._pattern_payload(), sort_keys=True).encode("utf-8")

    def sample_key(self) -> str:
        return f"{self.host}:{self.severity}:{self.app}"

    def pattern_id(self) -> str:
        return hashlib.sha1(self.dedupe_key()).hexdigest()


def _extract_structured_timestamp(raw: str) -> datetime | None:
    match = ISO_TIMESTAMP_RE.search(raw)
    if not match:
        return None
    iso_str = match.group(0)
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso_str)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _looks_like_iso_token(token: str) -> bool:
    """Return True if token resembles an ISO timestamp fragment."""
    return bool(ISO_TIMESTAMP_RE.fullmatch(token))


def _select_app_token(tag: str, host: str) -> str:
    """
    Given the raw tag portion before the ':' delimiter, attempt to extract a usable app name.
    Handles RFC3164 and RFC5424 style tags where additional fields (version, ISO timestamp,
    hostname, etc.) may precede the actual app token.
    """
    tag = tag.strip()
    if not tag:
        return "-"
    tokens = tag.split()
    candidate = None
    for token in reversed(tokens):
        tok = token.strip()
        if not tok:
            continue
        # Skip obvious non-app tokens
        if tok == host or tok == "-":
            continue
        if tok.isdigit() or _looks_like_iso_token(tok):
            continue
        if not any(ch.isalpha() for ch in tok) and "[" not in tok and "]" not in tok:
            continue
        candidate = tok
        break
    if candidate:
        return candidate
    return tokens[-1]


def _split_tag_and_message(message_part: str) -> tuple[str, str]:
    """
    Split the portion after the syslog header into (tag, message) using heuristics that favor
    the first colon followed by whitespace (to avoid timestamps like HH:MM:SS).
    Returns (tag, remainder_without_tag).
    """
    for delimiter in (": ", ":\t"):
        idx = message_part.find(delimiter)
        if idx != -1:
            return message_part[:idx], message_part[idx + len(delimiter) :]
    idx = message_part.find(":")
    if idx == -1:
        return "", message_part
    return message_part[:idx], message_part[idx + 1 :]


def parse_syslog(payload: bytes, addr: str, transport: str, syslog_tz: Optional[ZoneInfo] = None) -> LogEvent:
    """
    Parse syslog message. If syslog_tz is provided, syslog timestamps without timezone
    will be interpreted as being in that timezone (defaults to UTC).
    """
    
    raw = payload.decode("utf-8", errors="replace").strip()
    timestamp = utc_now()
    host = addr
    app = "-"
    severity = "info"
    facility = "user"
    message = raw

    if raw.startswith("<"):
        try:
            pri_end = raw.index(">")
            pri = int(raw[1:pri_end])
            severity = ["emerg", "alert", "crit", "err", "warn", "notice", "info", "debug"][
                pri % 8
            ]
            facility = str(pri // 8)
            remainder = raw[pri_end + 1 :].strip()
        except (ValueError, IndexError):
            remainder = raw
    else:
        remainder = raw

    parts = remainder.split(" ", 4)
    if len(parts) >= 4:
        try:
            timestamp = datetime.strptime(" ".join(parts[:3]), "%b %d %H:%M:%S")
            # Use syslog_tz if provided, otherwise UTC
            tz = syslog_tz if syslog_tz else timezone.utc
            timestamp = timestamp.replace(year=utc_now().year, tzinfo=tz)
            host = parts[3]
            if len(parts) == 5:
                message_part = parts[4]
            else:
                message_part = ""
            if ":" in message_part:
                tag_part, remainder = _split_tag_and_message(message_part)
                candidate = _select_app_token(tag_part, host)
                if candidate:
                    app = candidate
                message = remainder.strip()
            else:
                message = message_part.strip()
        except ValueError:
            host = parts[0]
            message = remainder

    structured_ts = _extract_structured_timestamp(raw)
    if structured_ts is not None:
        timestamp = structured_ts
    elif timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)

    return LogEvent(
        timestamp=timestamp,
        host=host,
        app=app,
        severity=severity,
        facility=facility,
        message=message,
        raw=raw,
        transport=transport,
    )


@dataclass
class IngestServer:
    config: IngestConfig
    journal: JournalWriter
    deduper: BloomDeduper
    sampler: ReservoirSampler
    loop: Optional[AbstractEventLoop] = None

    def __post_init__(self) -> None:
        # Large queue to ensure no logs are dropped - store all logs first, deduplicate later
        self._queue: asyncio.Queue[tuple[bytes, str, str]] = asyncio.Queue(maxsize=1_000_000)
        self._udp_transport: Optional[asyncio.DatagramTransport] = None
        self._tcp_server: Optional[asyncio.AbstractServer] = None
        self._consumer_task: Optional[asyncio.Task[None]] = None
        # Initialize _current_bucket in the journal's bucket timezone
        now_utc = utc_now()
        bucket_tz = self.journal.bucket_timezone
        now_bucket_tz = ensure_timezone(now_utc, bucket_tz)
        self._current_bucket = floor_to_minute(now_bucket_tz)
        self._last_bucket_path: Optional[str] = None
        self._bucket_stats = self._new_bucket_stats()

    @staticmethod
    def _new_bucket_stats():
        return {
            "severity": Counter(),
            "hosts": Counter(),
            "apps": Counter(),
            "patterns": Counter(),
            "pattern_hosts": defaultdict(Counter),
            "pattern_apps": defaultdict(Counter),
        }

    def _reset_bucket_stats(self) -> None:
        self._bucket_stats = self._new_bucket_stats()

    def _update_bucket_stats(self, event: LogEvent, pattern: str) -> None:
        stats = self._bucket_stats
        host = event.host or "unknown"
        app = event.app or "-"
        stats["severity"][event.severity] += 1
        stats["hosts"][host] += 1
        stats["apps"][app] += 1
        stats["patterns"][pattern] += 1
        stats["pattern_hosts"][pattern][host] += 1
        stats["pattern_apps"][pattern][app] += 1

    async def start(self) -> None:
        self.loop = self.loop or asyncio.get_running_loop()
        await self._start_udp()
        await self._start_tcp()
        self._consumer_task = asyncio.create_task(self._consume_queue())

    async def stop(self) -> None:
        await self._flush_bucket()
        if self._udp_transport:
            self._udp_transport.close()
        if self._tcp_server:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
        if self._consumer_task:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task

    async def _start_udp(self) -> None:
        import logging
        logger = logging.getLogger("mithrillog.ingest.udp")
        
        class _Protocol(asyncio.DatagramProtocol):
            def __init__(self, queue: asyncio.Queue[tuple[bytes, str, str]], loop: AbstractEventLoop) -> None:
                self.queue = queue
                self.loop = loop
                self._put_tasks = set()

            def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
                host, _port = addr
                # Try non-blocking first (queue is 1M, should rarely fail)
                try:
                    self.queue.put_nowait((data, host, "udp"))
                except asyncio.QueueFull:
                    # Queue full - schedule async put to avoid blocking protocol handler
                    # This should be extremely rare with 1M queue size
                    task_ref = [None]  # Use list for mutable reference
                    async def put_log():
                        try:
                            await self.queue.put((data, host, "udp"))
                        finally:
                            if task_ref[0]:
                                self._put_tasks.discard(task_ref[0])
                    task = self.loop.create_task(put_log())
                    task_ref[0] = task
                    self._put_tasks.add(task)
                    logger.warning(f"UDP queue full, using async put (queue size: {self.queue.qsize()})")

        if self.loop is None:
            raise RuntimeError("Event loop not initialized before starting UDP server")
        transport, _ = await self.loop.create_datagram_endpoint(  # type: ignore[arg-type]
            lambda: _Protocol(self._queue, self.loop),
            local_addr=(self.config.host, self.config.udp_port),
        )
        self._udp_transport = transport

    async def _start_tcp(self) -> None:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            peer = writer.get_extra_info("peername")
            host = peer[0] if peer else "unknown"
            try:
                while not reader.at_eof():
                    line = await reader.readline()
                    if not line:
                        break
                    # Use blocking put to ensure no logs are dropped
                    await self._queue.put((line.strip(), host, "tcp"))
            finally:
                writer.close()
                await writer.wait_closed()

        self._tcp_server = await asyncio.start_server(
            handle, host=self.config.host, port=self.config.tcp_port
        )

    async def _consume_queue(self) -> None:
        # Use bucket timezone for syslog timestamps (assumes log sources use same timezone)
        syslog_tz = self.journal.bucket_timezone
        while True:
            data, host, transport = await self._queue.get()
            event = parse_syslog(data, host, transport, syslog_tz=syslog_tz)
            await self._handle_event(event)

    async def _handle_event(self, event: LogEvent) -> None:
        # Use server receive time (in bucket timezone) for bucket path, not log timestamp
        bucket_tz = self.journal.bucket_timezone
        server_now = utc_now()
        server_tz = ensure_timezone(server_now, bucket_tz)
        bucket_time = floor_to_minute(server_tz)
        
        if bucket_time > self._current_bucket:
            await self._flush_bucket()
            self.deduper.reset()
            self.sampler.reset()
            self._current_bucket = bucket_time
            self._reset_bucket_stats()
        
        pattern = event.pattern_id()
        self._update_bucket_stats(event, pattern)
        
        # Strong deduplication: check if duplicate BEFORE storing
        if self.deduper.seen(event.dedupe_key()):
            # Duplicate detected - only count it, don't store
            self.sampler.register_duplicate(pattern)
            return
        
        # Unique log - store it
        record = event.model_dump()
        record["pattern_id"] = pattern
        record["occurrences"] = self.sampler.totals().get(pattern, 0) + 1
        self.sampler.add(event.sample_key(), pattern, record)
        
        # Use server receive time for bucket path, but keep original log timestamp in record
        path = self.journal.append(record, bucket_time=server_tz)
        self._last_bucket_path = str(path)
        
        # Forward to live tail if configured
        if self.config.forward_to_host and self.config.forward_to_port:
            self._forward_log(record)

    def _forward_log(self, record: dict) -> None:
        if not self._udp_transport:
            return
        try:
            payload = json.dumps(record).encode("utf-8")
            self._udp_transport.sendto(
                payload, (self.config.forward_to_host, self.config.forward_to_port)
            )
        except Exception:
            # Best effort forwarding, don't crash ingestion
            pass

    async def _flush_bucket(self) -> None:
        if not self._last_bucket_path:
            self._reset_bucket_stats()
            return
        path = Path(self._last_bucket_path)
        if not path.exists():
            self._last_bucket_path = None
            self._reset_bucket_stats()
            return
        totals = self.sampler.totals()
        events: list[dict] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    events.append(json.loads(line))
        except json.JSONDecodeError:
            events = []

        stats = self._bucket_stats
        severity_counts: Counter[str] = stats["severity"]
        host_counts: Counter[str] = stats["hosts"]
        app_counts: Counter[str] = stats["apps"]
        pattern_counts: Counter[str] = stats["patterns"]
        highlights: list[dict] = []
        for event in events:
            pattern = event.get("pattern_id")
            occurrences = pattern_counts.get(pattern, totals.get(pattern, 1))
            event["occurrences"] = occurrences
            sources = stats["pattern_hosts"].get(pattern, Counter())
            apps = stats["pattern_apps"].get(pattern, Counter())
            event["source_hosts"] = dict(sources.most_common(5))
            event["source_apps"] = dict(apps.most_common(5))
            highlights.append(event)
        total_events = (
            sum(pattern_counts.values()) or sum(totals.values()) or len(events)
        )
        bucket_meta = {
            "bucket": self._current_bucket.isoformat(),
            "patterns": dict(pattern_counts) or totals,
            "severity": dict(severity_counts),
            "hosts": dict(host_counts),
            "apps": dict(app_counts),
            "total_events": total_events,
            "unique_events": len(events),
            "highlights": sorted(highlights, key=lambda item: item.get("occurrences", 1), reverse=True)[
                :50
            ],
        }
        meta_path = path.with_suffix(".meta.json")
        self.journal.write_metadata(meta_path, bucket_meta)
        self._last_bucket_path = None
        self._reset_bucket_stats()

