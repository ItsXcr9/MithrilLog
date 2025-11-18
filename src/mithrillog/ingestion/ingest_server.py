from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import re
from asyncio import AbstractEventLoop
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..config import IngestConfig
from ..storage import JournalWriter
from ..utils.time import floor_to_minute, utc_now
from .dedupe import BloomDeduper, ReservoirSampler


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
        return normalized

    def dedupe_key(self) -> bytes:
        normalized_msg = self.normalize_message()
        payload = {
            "host": self.host,
            "app": self.app,
            "severity": self.severity,
            "facility": self.facility,
            "message": normalized_msg,
        }
        return json.dumps(payload, sort_keys=True).encode("utf-8")

    def sample_key(self) -> str:
        return f"{self.host}:{self.severity}:{self.app}"

    def pattern_id(self) -> str:
        return hashlib.sha1(self.dedupe_key()).hexdigest()


def parse_syslog(payload: bytes, addr: str, transport: str) -> LogEvent:
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
            timestamp = timestamp.replace(year=utc_now().year, tzinfo=utc_now().tzinfo)
            host = parts[3]
            if len(parts) == 5:
                message_part = parts[4]
            else:
                message_part = ""
            if ":" in message_part:
                app_part, message_part = message_part.split(":", 1)
                app = app_part.strip()
                message = message_part.strip()
            else:
                message = message_part.strip()
        except ValueError:
            host = parts[0]
            message = remainder

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
        self._queue: asyncio.Queue[tuple[bytes, str, str]] = asyncio.Queue(maxsize=50_000)
        self._udp_transport: Optional[asyncio.DatagramTransport] = None
        self._tcp_server: Optional[asyncio.AbstractServer] = None
        self._consumer_task: Optional[asyncio.Task[None]] = None
        self._current_bucket = floor_to_minute(utc_now())
        self._last_bucket_path: Optional[str] = None

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
        class _Protocol(asyncio.DatagramProtocol):
            def __init__(self, queue: asyncio.Queue[tuple[bytes, str, str]]) -> None:
                self.queue = queue

            def datagram_received(self, data: bytes, addr) -> None:  # type: ignore[override]
                host, _port = addr
                try:
                    self.queue.put_nowait((data, host, "udp"))
                except asyncio.QueueFull:
                    pass

        if self.loop is None:
            raise RuntimeError("Event loop not initialized before starting UDP server")
        transport, _ = await self.loop.create_datagram_endpoint(  # type: ignore[arg-type]
            lambda: _Protocol(self._queue),
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
                    try:
                        self._queue.put_nowait((line.strip(), host, "tcp"))
                    except asyncio.QueueFull:
                        break
            finally:
                writer.close()
                await writer.wait_closed()

        self._tcp_server = await asyncio.start_server(
            handle, host=self.config.host, port=self.config.tcp_port
        )

    async def _consume_queue(self) -> None:
        while True:
            data, host, transport = await self._queue.get()
            event = parse_syslog(data, host, transport)
            await self._handle_event(event)

    async def _handle_event(self, event: LogEvent) -> None:
        bucket_time = floor_to_minute(event.timestamp)
        if bucket_time > self._current_bucket:
            await self._flush_bucket()
            self.deduper.reset()
            self.sampler.reset()
            self._current_bucket = bucket_time
        pattern = event.pattern_id()
        if self.deduper.seen(event.dedupe_key()):
            self.sampler.register_duplicate(pattern)
            return
        record = event.model_dump()
        record["pattern_id"] = pattern
        record["occurrences"] = self.sampler.totals().get(pattern, 0) + 1
        self.sampler.add(event.sample_key(), pattern, record)
        path = self.journal.append(record)
        self._last_bucket_path = str(path)
        _ = path  # placeholder for future metrics

    async def _flush_bucket(self) -> None:
        if not self._last_bucket_path:
            return
        path = Path(self._last_bucket_path)
        if not path.exists():
            self._last_bucket_path = None
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
        from collections import Counter

        severity_counts: Counter[str] = Counter()
        host_counts: Counter[str] = Counter()
        app_counts: Counter[str] = Counter()
        highlights: list[dict] = []
        for event in events:
            pattern = event.get("pattern_id")
            occurrences = totals.get(pattern, 1)
            event["occurrences"] = occurrences
            severity = event.get("severity", "info")
            severity_counts[severity] += occurrences
            host_counts[event.get("host", "unknown")] += occurrences
            app_counts[event.get("app", "-")] += occurrences
            highlights.append(event)
        total_events = sum(totals.values()) or len(events)
        bucket_meta = {
            "bucket": self._current_bucket.isoformat(),
            "patterns": totals,
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

