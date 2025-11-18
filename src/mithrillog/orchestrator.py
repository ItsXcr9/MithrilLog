from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .config import Settings, default_settings
from .ingestion import BloomDeduper, IngestServer, ReservoirSampler
from .llm import LLMClient
from .storage import JournalWriter
from .summarization import DailySummarizer, HourlySummarizer
from .utils.time import get_timezone, utc_now

logger = logging.getLogger("mithrillog.orchestrator")


class Orchestrator:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or default_settings
        self.local_tz = get_timezone(self.settings.timezone)
        self.journal = JournalWriter(
            Path(self.settings.ingest.bucket_dir), timezone_name=self.settings.timezone
        )
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
        # Catch up on missed summaries (run in background, don't block startup)
        self._tasks.append(asyncio.create_task(self._catchup_summaries()))
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
            now_utc = utc_now()
            now_local = now_utc.astimezone(self.local_tz)
            run_at_local = now_local.replace(minute=minute, second=0, microsecond=0)
            if run_at_local <= now_local:
                run_at_local += timedelta(hours=1)
            run_at_utc = run_at_local.astimezone(timezone.utc)
            await asyncio.sleep(max(0, (run_at_utc - now_utc).total_seconds()))
            await self._run_hourly(run_at_local - timedelta(hours=1))

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
            now_utc = utc_now()
            now_local = now_utc.astimezone(self.local_tz)
            run_at_local = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_at_local <= now_local:
                run_at_local += timedelta(days=1)
            run_at_utc = run_at_local.astimezone(timezone.utc)
            await asyncio.sleep(max(0, (run_at_utc - now_utc).total_seconds()))
            await self._run_daily(run_at_local - timedelta(days=1))

    async def _run_daily(self, target: datetime) -> None:
        logger.info("Running daily summary for %s", target)
        try:
            await asyncio.to_thread(self.daily_summarizer.summarize_day, target)
        except Exception:  # noqa: BLE001
            logger.exception("Daily summary failed for %s", target)

    async def _catchup_summaries(self) -> None:
        """Catch up on missed hourly and daily summaries."""
        logger.info("Catching up on missed summaries...")
        now_local = utc_now().astimezone(self.local_tz)
        
        # Catch up hourly summaries (last 24 hours)
        for hours_back in range(24, 0, -1):
            target = now_local - timedelta(hours=hours_back)
            target = target.replace(minute=self.settings.summary.hourly_at_minute, second=0, microsecond=0)
            if target < now_local:
                try:
                    await self._run_hourly(target)
                except Exception:  # noqa: BLE001
                    logger.exception("Catchup hourly summary failed for %s", target)
                await asyncio.sleep(1)  # Small delay between summaries
        
        # Catch up daily summaries (last 7 days)
        for days_back in range(7, 0, -1):
            target = now_local - timedelta(days=days_back)
            target = target.replace(
                hour=self.settings.summary.daily_at_hour,
                minute=self.settings.summary.daily_at_minute,
                second=0,
                microsecond=0
            )
            if target < now_local:
                try:
                    await self._run_daily(target)
                except Exception:  # noqa: BLE001
                    logger.exception("Catchup daily summary failed for %s", target)
                await asyncio.sleep(1)  # Small delay between summaries
        
        logger.info("Catchup complete")

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(60)
            # hook for health checks, metrics

    async def run_forever(self) -> None:
        await self.start()
        await self._stopped.wait()

