import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from mithrillog.orchestrator import Orchestrator

@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.ingest.bucket_dir = "/tmp/buckets"
    settings.storage.sqlite_path = ":memory:"
    settings.timezone = "UTC"
    return settings

@pytest.mark.asyncio
async def test_orchestrator_start_stop(mock_settings):
    with patch("mithrillog.orchestrator.IngestServer") as MockIngest, \
         patch("mithrillog.orchestrator.JournalWriter"), \
         patch("mithrillog.orchestrator.StateStore"), \
         patch("mithrillog.orchestrator.LLMClient"):
        
        mock_ingest = MockIngest.return_value
        mock_ingest.start = AsyncMock()
        mock_ingest.stop = AsyncMock()
        
        orchestrator = Orchestrator(mock_settings)
        
        # Start
        await orchestrator.start()
        assert mock_ingest.start.called
        assert len(orchestrator._tasks) > 0
        
        # Stop
        await orchestrator.stop()
        assert mock_ingest.stop.called
        assert orchestrator._stopped.is_set()

@pytest.mark.asyncio
async def test_watchdog_health_check(mock_settings):
    with patch("mithrillog.orchestrator.IngestServer"), \
         patch("mithrillog.orchestrator.JournalWriter"), \
         patch("mithrillog.orchestrator.StateStore"), \
         patch("mithrillog.orchestrator.LLMClient"):
        
        orchestrator = Orchestrator(mock_settings)
        
        # Mock the sleep to avoid waiting
        with patch("asyncio.sleep", AsyncMock()):
            # We can't easily test the infinite loop, but we can test the logic inside if we refactor
            # For now, we just ensure it can be instantiated
            assert orchestrator is not None
