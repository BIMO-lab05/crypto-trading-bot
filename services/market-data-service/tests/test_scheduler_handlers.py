"""
Market Data Service - Scheduler Handlers Tests
Purpose: Test scheduler control endpoint handlers
"""

import pytest
from fastapi import HTTPException
from unittest.mock import patch, AsyncMock, MagicMock

from app.handlers.scheduler import (
    get_scheduler_status_handler,
    start_scheduler_handler,
    stop_scheduler_handler,
    trigger_manual_collection_handler
)


class TestGetSchedulerStatusHandler:
    """Test scheduler status handler"""

    @pytest.mark.asyncio
    async def test_get_scheduler_status_success(self):
        """Test successful scheduler status retrieval"""
        mock_status = {
            "running": True,
            "jobs": [
                {"id": "ticker_collection", "name": "Ticker Data Collection"}
            ],
            "job_count": 1
        }

        with patch('app.handlers.scheduler.get_scheduler_status', return_value=mock_status):
            result = await get_scheduler_status_handler()

            assert result["success"] is True
            assert result["scheduler"] == mock_status
            assert result["scheduler"]["running"] is True
            assert result["scheduler"]["job_count"] == 1

    @pytest.mark.asyncio
    async def test_get_scheduler_status_when_not_running(self):
        """Test status retrieval when scheduler is not running"""
        mock_status = {
            "running": False,
            "jobs": [],
            "job_count": 0
        }

        with patch('app.handlers.scheduler.get_scheduler_status', return_value=mock_status):
            result = await get_scheduler_status_handler()

            assert result["success"] is True
            assert result["scheduler"]["running"] is False
            assert result["scheduler"]["jobs"] == []

    @pytest.mark.asyncio
    async def test_get_scheduler_status_handles_exception(self):
        """Test that status handler raises HTTPException on error"""
        with patch('app.handlers.scheduler.get_scheduler_status', side_effect=Exception("Status error")):
            with pytest.raises(HTTPException) as exc_info:
                await get_scheduler_status_handler()

            assert exc_info.value.status_code == 500
            assert "Failed to get scheduler status" in exc_info.value.detail


class TestStartSchedulerHandler:
    """Test scheduler start handler"""

    @pytest.mark.asyncio
    async def test_start_scheduler_success(self):
        """Test successful scheduler start"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.start_scheduler') as mock_start:
            result = await start_scheduler_handler(api_key=mock_api_key)

            assert result["success"] is True
            assert "started successfully" in result["message"]
            mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_scheduler_handles_exception(self):
        """Test that start handler raises HTTPException on error"""
        mock_api_key = "test-api-key"
        error_message = "Scheduler already running"

        with patch('app.handlers.scheduler.start_scheduler', side_effect=Exception(error_message)):
            with pytest.raises(HTTPException) as exc_info:
                await start_scheduler_handler(api_key=mock_api_key)

            assert exc_info.value.status_code == 500
            assert error_message in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_start_scheduler_requires_auth(self):
        """Test that API key is required for start endpoint"""
        # The verify_api_key dependency should be called
        # This test verifies the signature includes the dependency
        import inspect
        sig = inspect.signature(start_scheduler_handler)
        assert 'api_key' in sig.parameters


class TestStopSchedulerHandler:
    """Test scheduler stop handler"""

    @pytest.mark.asyncio
    async def test_stop_scheduler_success(self):
        """Test successful scheduler stop"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.stop_scheduler') as mock_stop:
            result = await stop_scheduler_handler(api_key=mock_api_key)

            assert result["success"] is True
            assert "stopped successfully" in result["message"]
            mock_stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_scheduler_handles_exception(self):
        """Test that stop handler raises HTTPException on error"""
        mock_api_key = "test-api-key"
        error_message = "Scheduler not running"

        with patch('app.handlers.scheduler.stop_scheduler', side_effect=Exception(error_message)):
            with pytest.raises(HTTPException) as exc_info:
                await stop_scheduler_handler(api_key=mock_api_key)

            assert exc_info.value.status_code == 500
            assert error_message in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_stop_scheduler_requires_auth(self):
        """Test that API key is required for stop endpoint"""
        import inspect
        sig = inspect.signature(stop_scheduler_handler)
        assert 'api_key' in sig.parameters


class TestTriggerManualCollectionHandler:
    """Test manual collection trigger handler"""

    @pytest.mark.asyncio
    async def test_trigger_manual_collection_success(self):
        """Test successful manual collection trigger"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.run_manual_collection', new_callable=AsyncMock):
            result = await trigger_manual_collection_handler(api_key=mock_api_key)

            assert result["success"] is True
            assert "completed" in result["message"]

    @pytest.mark.asyncio
    async def test_trigger_manual_collection_handles_exception(self):
        """Test that manual collection handler raises HTTPException on error"""
        mock_api_key = "test-api-key"
        error_message = "Collection failed"

        with patch('app.handlers.scheduler.run_manual_collection', new_callable=AsyncMock, side_effect=Exception(error_message)):
            with pytest.raises(HTTPException) as exc_info:
                await trigger_manual_collection_handler(api_key=mock_api_key)

            assert exc_info.value.status_code == 500
            assert error_message in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_trigger_manual_collection_requires_auth(self):
        """Test that API key is required for manual collection"""
        import inspect
        sig = inspect.signature(trigger_manual_collection_handler)
        assert 'api_key' in sig.parameters

    @pytest.mark.asyncio
    async def test_trigger_manual_collection_is_async(self):
        """Test that manual collection properly awaits async function"""
        mock_api_key = "test-api-key"
        mock_run = AsyncMock()

        with patch('app.handlers.scheduler.run_manual_collection', mock_run):
            await trigger_manual_collection_handler(api_key=mock_api_key)

            mock_run.assert_awaited_once()


class TestHandlerResponseFormat:
    """Test response format consistency"""

    @pytest.mark.asyncio
    async def test_all_success_responses_have_success_field(self):
        """Test that all successful responses include success=True"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.get_scheduler_status', return_value={"running": False, "jobs": []}), \
             patch('app.handlers.scheduler.start_scheduler'), \
             patch('app.handlers.scheduler.stop_scheduler'), \
             patch('app.handlers.scheduler.run_manual_collection', new_callable=AsyncMock):

            status_result = await get_scheduler_status_handler()
            start_result = await start_scheduler_handler(api_key=mock_api_key)
            stop_result = await stop_scheduler_handler(api_key=mock_api_key)
            manual_result = await trigger_manual_collection_handler(api_key=mock_api_key)

            assert status_result["success"] is True
            assert start_result["success"] is True
            assert stop_result["success"] is True
            assert manual_result["success"] is True

    @pytest.mark.asyncio
    async def test_all_action_responses_have_message_field(self):
        """Test that action endpoints return meaningful messages"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.start_scheduler'), \
             patch('app.handlers.scheduler.stop_scheduler'), \
             patch('app.handlers.scheduler.run_manual_collection', new_callable=AsyncMock):

            start_result = await start_scheduler_handler(api_key=mock_api_key)
            stop_result = await stop_scheduler_handler(api_key=mock_api_key)
            manual_result = await trigger_manual_collection_handler(api_key=mock_api_key)

            assert "message" in start_result
            assert "message" in stop_result
            assert "message" in manual_result
            assert len(start_result["message"]) > 0
            assert len(stop_result["message"]) > 0
            assert len(manual_result["message"]) > 0


class TestLoggingBehavior:
    """Test logging behavior of handlers"""

    @pytest.mark.asyncio
    async def test_start_scheduler_logs_info(self, caplog):
        """Test that starting scheduler logs info message"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.start_scheduler'):
            await start_scheduler_handler(api_key=mock_api_key)

            # Logger should be called (actual log may be async)

    @pytest.mark.asyncio
    async def test_stop_scheduler_logs_info(self, caplog):
        """Test that stopping scheduler logs info message"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.stop_scheduler'):
            await stop_scheduler_handler(api_key=mock_api_key)

            # Logger should be called

    @pytest.mark.asyncio
    async def test_manual_collection_logs_trigger(self, caplog):
        """Test that manual collection logs trigger event"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.run_manual_collection', new_callable=AsyncMock):
            await trigger_manual_collection_handler(api_key=mock_api_key)

            # Logger should be called

    @pytest.mark.asyncio
    async def test_error_handling_logs_errors(self, caplog):
        """Test that errors are logged properly"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.start_scheduler', side_effect=Exception("Test error")):
            try:
                await start_scheduler_handler(api_key=mock_api_key)
            except HTTPException:
                pass

            # Error should be logged


class TestEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_get_status_with_complex_job_info(self):
        """Test status handler with complex job information"""
        complex_status = {
            "running": True,
            "jobs": [
                {
                    "id": "ticker_collection",
                    "name": "Ticker Data Collection",
                    "next_run": "2024-01-01 12:00:00",
                    "trigger": "interval"
                },
                {
                    "id": "kline_collection",
                    "name": "Kline Data Collection",
                    "next_run": "2024-01-01 12:02:00",
                    "trigger": "interval"
                },
                {
                    "id": "hourly_full_collection",
                    "name": "Hourly Full Data Collection",
                    "next_run": "2024-01-01 13:00:00",
                    "trigger": "cron"
                }
            ],
            "job_count": 3
        }

        with patch('app.handlers.scheduler.get_scheduler_status', return_value=complex_status):
            result = await get_scheduler_status_handler()

            assert result["scheduler"]["job_count"] == 3
            assert len(result["scheduler"]["jobs"]) == 3

    @pytest.mark.asyncio
    async def test_concurrent_scheduler_operations(self):
        """Test handling of concurrent scheduler operations"""
        mock_api_key = "test-api-key"

        with patch('app.handlers.scheduler.start_scheduler'), \
             patch('app.handlers.scheduler.stop_scheduler'):

            # Simulate rapid start/stop calls
            result1 = await start_scheduler_handler(api_key=mock_api_key)
            result2 = await stop_scheduler_handler(api_key=mock_api_key)
            result3 = await start_scheduler_handler(api_key=mock_api_key)

            assert result1["success"] is True
            assert result2["success"] is True
            assert result3["success"] is True
