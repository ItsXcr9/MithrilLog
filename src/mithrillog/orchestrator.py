from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .config import Settings, default_settings
from .ingestion import BloomDeduper, IngestServer, ReservoirSampler
from .llm import LLMClient
from .storage import JournalWriter
from .summarization import DailySummarizer, HourlySummarizer
from .utils.time import utc_now

logger = logging.getLogger("mithrillog.orchestrator")


class Orchestrator:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or default_settings
        self.journal = JournalWriter(Path(self.settings.ingest.bucket_dir))
        self.llm_client = LLMClient(self.settings.llm)
        self.ingest_server = IngestServer(
            config=self.settings.ingest,
            journal=self.journal,
            deduper=BloomDeduper(
                capacity=1_000_000, error_rate=self.settings.ingest.bloom_error_rate
            ),
            sampler=ReservoirSampler(size=self.settings.ingest.reservoir_size),
        )
        self.hourly_summarizer = HourlySummarizer(self.settings, self.journal, self.llm_client)
        self.daily_summarizer = DailySummarizer(self.settings, self.journal, self.llm_client)
        self._tasks: list[asyncio.Task] = []
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        logger.info("Starting orchestrator")
        self._stopped.clear()
        await self.ingest_server.start()
        self._tasks.append(asyncio.create_task(self._hourly_scheduler()))
        self._tasks.append(asyncio.create_task(self._daily_scheduler()))
        self._tasks.append(asyncio.create_task(self._watchdog()))

    async def stop(self) -> None:
        logger.info("Stopping orchestrator")
        for task in self._tasks:
            task.cancel()
        await self.ingest_server.stop()
        with contextlib.suppress(asyncio.CancelledError):
            for task in self._tasks:
                await task
        self._tasks.clear()
        self._stopped.set()

    async def _hourly_scheduler(self) -> None:
        minute = self.settings.summary.hourly_at_minute
        while True:
            now = utc_now()
            run_at = now.replace(minute=minute, second=0, microsecond=0)
            if run_at <= now:
                run_at += timedelta(hours=1)
            await asyncio.sleep((run_at - now).total_seconds())
            await self._run_hourly(run_at - timedelta(hours=1))

    async def _run_hourly(self, target: datetime) -> None:
        logger.info("Running hourly summary for %s", target)
        try:
            await asyncio.to_thread(self.hourly_summarizer.summarize_hour, target)
        except Exception:  # noqa: BLE001
            logger.exception("Hourly summary failed for %s", target)

    async def _daily_scheduler(self) -> None:
        minute = self.settings.summary.daily_at_minute
        hour = self.settings.summary.daily_at_hour
        while True:
            now = utc_now()
            run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_at <= now:
                run_at += timedelta(days=1)
            await asyncio.sleep((run_at - now).total_seconds())
            await self._run_daily(run_at - timedelta(days=1))

    async def _run_daily(self, target: datetime) -> None:
        logger.info("Running daily summary for %s", target)
        try:
            await asyncio.to_thread(self.daily_summarizer.summarize_day, target)
        except Exception:  # noqa: BLE001
            logger.exception("Daily summary failed for %s", target)

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(60)
            # hook for health checks, metrics

    async def run_forever(self) -> None:
        await self.start()
        await self._stopped.wait()

