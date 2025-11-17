from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
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

    def dedupe_key(self) -> bytes:
        payload = {
            "host": self.host,
            "app": self.app,
            "severity": self.severity,
            "facility": self.facility,
            "message": self.message,
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

