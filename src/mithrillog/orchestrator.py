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
from .state_store import StateStore
from .summarization import DailySummarizer, HourlySummarizer, TrendSummarizer
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
        self.state_store = StateStore(Path(self.settings.storage.sqlite_path))
        
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
        self.trend_summarizer = TrendSummarizer(self.settings, self.journal, self.llm_client, self.state_store)
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
        self._tasks.append(asyncio.create_task(self._retention_cleanup()))
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
            report = await asyncio.to_thread(self.daily_summarizer.summarize_day, target)
            # Run trend analysis after daily summary
            logger.info("Running trend analysis for %s", target)
            await asyncio.to_thread(self.trend_summarizer.summarize_trend, target, report)
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

    async def _retention_cleanup(self) -> None:
        """Periodically clean up logs older than retention_days."""
        retention_days = self.settings.ingest.retention_days
        bucket_dir = Path(self.settings.ingest.bucket_dir)
        while True:
            try:
                # Run cleanup once per hour
                await asyncio.sleep(3600)
                cutoff_date = utc_now() - timedelta(days=retention_days)
                cutoff_date = cutoff_date.astimezone(self.local_tz)
                
                deleted_count = 0
                if bucket_dir.exists():
                    for year_dir in bucket_dir.iterdir():
                        if not year_dir.is_dir() or not year_dir.name.isdigit():
                            continue
                        year = int(year_dir.name)
                        if year < cutoff_date.year:
                            # Delete entire year directory
                            import shutil
                            shutil.rmtree(year_dir)
                            deleted_count += 1
                            logger.info("Deleted year directory: %s", year_dir)
                            continue
                        
                        for month_dir in year_dir.iterdir():
                            if not month_dir.is_dir() or not month_dir.name.isdigit():
                                continue
                            month = int(month_dir.name)
                            if year == cutoff_date.year and month < cutoff_date.month:
                                import shutil
                                shutil.rmtree(month_dir)
                                deleted_count += 1
                                logger.info("Deleted month directory: %s", month_dir)
                                continue
                            
                            for day_dir in month_dir.iterdir():
                                if not day_dir.is_dir() or not day_dir.name.isdigit():
                                    continue
                                day = int(day_dir.name)
                                try:
                                    dir_date = datetime(year, month, day, tzinfo=self.local_tz)
                                    if dir_date < cutoff_date:
                                        import shutil
                                        shutil.rmtree(day_dir)
                                        deleted_count += 1
                                        logger.debug("Deleted day directory: %s", day_dir)
                                except ValueError:
                                    continue
                
                if deleted_count > 0:
                    logger.info("Retention cleanup: deleted %d directories older than %d days", deleted_count, retention_days)
            except Exception:  # noqa: BLE001
                logger.exception("Retention cleanup failed")

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(60)
            # hook for health checks, metrics

    async def run_forever(self) -> None:
        await self.start()
        await self._stopped.wait()

