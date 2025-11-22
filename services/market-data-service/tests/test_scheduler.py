"""
Market Data Service - Scheduler Tests
Purpose: Test automated data collection scheduling
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock, call
import asyncio

from app.scheduler import (
    collect_ticker_data,
    collect_kline_data,
    collect_all_data,
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    run_manual_collection,
    TRADING_PAIRS,
    KLINE_INTERVALS
)


class TestCollectTickerData:
    """Test ticker data collection job"""

    @pytest.mark.asyncio
    async def test_collect_ticker_data_success(self):
        """Test successful ticker data collection for all symbols"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_ticker = AsyncMock(return_value={
            "symbol": "BTCUSDT",
            "last_price": "50000"
        })

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.TickerRepository', return_value=mock_ticker_repo):

            await collect_ticker_data()

            # Verify fetcher was called for each trading pair
            assert mock_fetcher.get_ticker.call_count == len(TRADING_PAIRS)
            # Verify repo save was called for each symbol
            assert mock_ticker_repo.save_ticker.call_count == len(TRADING_PAIRS)

    @pytest.mark.asyncio
    async def test_collect_ticker_data_handles_no_data(self):
        """Test handling when ticker returns None"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_ticker = AsyncMock(return_value=None)

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.TickerRepository', return_value=mock_ticker_repo):

            await collect_ticker_data()

            # Repo save should not be called if no data
            assert mock_ticker_repo.save_ticker.call_count == 0

    @pytest.mark.asyncio
    async def test_collect_ticker_data_handles_exceptions(self):
        """Test that exceptions don't stop collection for other symbols"""
        mock_fetcher = MagicMock()

        # First call fails, second succeeds
        mock_fetcher.get_ticker = AsyncMock(
            side_effect=[
                Exception("Connection error"),
                {"symbol": "ETHUSDT", "last_price": "3000"}
            ]
        )

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.TickerRepository', return_value=mock_ticker_repo):

            # Should not raise exception
            await collect_ticker_data()

    @pytest.mark.asyncio
    async def test_collect_ticker_data_calls_all_symbols(self):
        """Test that all trading pairs are processed"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_ticker = AsyncMock(return_value={"data": "value"})

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.TickerRepository', return_value=mock_ticker_repo):

            await collect_ticker_data()

            # Check that get_ticker was called with each symbol
            called_symbols = [call_args[1]['symbol'] for call_args in mock_fetcher.get_ticker.call_args_list]
            for symbol in TRADING_PAIRS:
                assert symbol in called_symbols


class TestCollectKlineData:
    """Test kline data collection job"""

    @pytest.mark.asyncio
    async def test_collect_kline_data_success(self):
        """Test successful kline data collection"""
        mock_klines = [
            {"timestamp": 123, "open": "50000", "close": "50500"}
        ]

        mock_fetcher = MagicMock()
        mock_fetcher.get_kline = AsyncMock(return_value=mock_klines)

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=len(mock_klines))

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.KlineRepository', return_value=mock_kline_repo), \
             patch('app.scheduler.asyncio.sleep', new_callable=AsyncMock):

            await collect_kline_data()

            # Should call for all symbols and intervals
            expected_calls = len(TRADING_PAIRS) * len(KLINE_INTERVALS)
            assert mock_fetcher.get_kline.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_collect_kline_data_adds_metadata(self):
        """Test that symbol and interval are added to klines"""
        mock_klines = [
            {"timestamp": 123, "open": "50000"}
        ]

        mock_fetcher = MagicMock()
        mock_fetcher.get_kline = AsyncMock(return_value=mock_klines.copy())

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.KlineRepository', return_value=mock_kline_repo), \
             patch('app.scheduler.asyncio.sleep', new_callable=AsyncMock):

            await collect_kline_data()

            # Check that bulk_upsert was called with klines containing symbol and interval
            if mock_kline_repo.bulk_upsert.call_count > 0:
                first_call_klines = mock_kline_repo.bulk_upsert.call_args_list[0][0][0]
                assert 'symbol' in first_call_klines[0]
                assert 'interval' in first_call_klines[0]

    @pytest.mark.asyncio
    async def test_collect_kline_data_handles_empty_response(self):
        """Test handling when no klines are returned"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_kline = AsyncMock(return_value=[])

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.KlineRepository', return_value=mock_kline_repo), \
             patch('app.scheduler.asyncio.sleep', new_callable=AsyncMock):

            await collect_kline_data()

            # bulk_upsert should not be called for empty responses
            assert mock_kline_repo.bulk_upsert.call_count == 0

    @pytest.mark.asyncio
    async def test_collect_kline_data_respects_rate_limiting(self):
        """Test that sleep is called between requests for rate limiting"""
        mock_fetcher = MagicMock()
        mock_fetcher.get_kline = AsyncMock(return_value=[{"data": "value"}])

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        mock_sleep = AsyncMock()

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.KlineRepository', return_value=mock_kline_repo), \
             patch('app.scheduler.asyncio.sleep', mock_sleep):

            await collect_kline_data()

            # Sleep should be called between each interval fetch
            expected_calls = len(TRADING_PAIRS) * len(KLINE_INTERVALS)
            assert mock_sleep.call_count == expected_calls
            # Check sleep duration is 0.5 seconds
            for call_args in mock_sleep.call_args_list:
                assert call_args[0][0] == 0.5

    @pytest.mark.asyncio
    async def test_collect_kline_data_handles_exceptions_per_interval(self):
        """Test that exceptions don't stop collection for other intervals"""
        call_count = [0]

        async def side_effect_get_kline(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Network error")
            return [{"data": "value"}]

        mock_fetcher = MagicMock()
        mock_fetcher.get_kline = AsyncMock(side_effect=side_effect_get_kline)

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        with patch('app.scheduler.BybitDataFetcher', return_value=mock_fetcher), \
             patch('app.scheduler.KlineRepository', return_value=mock_kline_repo), \
             patch('app.scheduler.asyncio.sleep', new_callable=AsyncMock):

            # Should not raise exception
            await collect_kline_data()


class TestCollectAllData:
    """Test combined data collection job"""

    @pytest.mark.asyncio
    async def test_collect_all_data_calls_both_collectors(self):
        """Test that collect_all_data calls both ticker and kline collectors"""
        mock_sleep = AsyncMock()

        with patch('app.scheduler.collect_ticker_data', new_callable=AsyncMock) as mock_ticker, \
             patch('app.scheduler.collect_kline_data', new_callable=AsyncMock) as mock_kline, \
             patch('app.scheduler.asyncio.sleep', mock_sleep):

            await collect_all_data()

            mock_ticker.assert_called_once()
            mock_kline.assert_called_once()
            # Check that sleep is called between collections
            mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_collect_all_data_handles_exceptions(self):
        """Test that collect_all_data handles exceptions gracefully"""
        with patch('app.scheduler.collect_ticker_data', new_callable=AsyncMock, side_effect=Exception("Error")), \
             patch('app.scheduler.collect_kline_data', new_callable=AsyncMock), \
             patch('app.scheduler.asyncio.sleep', new_callable=AsyncMock):

            # Should not raise exception
            await collect_all_data()


class TestSchedulerManagement:
    """Test scheduler start/stop/status"""

    def test_start_scheduler_creates_scheduler(self):
        """Test that start_scheduler initializes the scheduler"""
        with patch('app.scheduler.AsyncIOScheduler') as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.get_jobs.return_value = []

            # Reset global scheduler
            import app.scheduler
            app.scheduler._scheduler = None

            start_scheduler()

            mock_scheduler_class.assert_called_once()
            mock_scheduler.start.assert_called_once()

    def test_start_scheduler_adds_jobs(self):
        """Test that start_scheduler adds all required jobs"""
        with patch('app.scheduler.AsyncIOScheduler') as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.get_jobs.return_value = []

            import app.scheduler
            app.scheduler._scheduler = None

            start_scheduler()

            # Should add 3 jobs: ticker, kline, and hourly full collection
            assert mock_scheduler.add_job.call_count == 3

    def test_start_scheduler_prevents_double_start(self):
        """Test that start_scheduler doesn't create duplicate scheduler"""
        mock_scheduler = MagicMock()

        import app.scheduler
        app.scheduler._scheduler = mock_scheduler

        start_scheduler()

        # Should not create new scheduler or start again
        mock_scheduler.start.assert_not_called()

    def test_stop_scheduler_shuts_down(self):
        """Test that stop_scheduler properly shuts down"""
        mock_scheduler = MagicMock()

        import app.scheduler
        app.scheduler._scheduler = mock_scheduler

        stop_scheduler()

        mock_scheduler.shutdown.assert_called_once_with(wait=True)

    def test_stop_scheduler_handles_no_scheduler(self):
        """Test that stop_scheduler handles case when scheduler is None"""
        import app.scheduler
        app.scheduler._scheduler = None

        # Should not raise exception
        stop_scheduler()

    def test_get_scheduler_status_when_not_running(self):
        """Test get_scheduler_status returns correct status when not running"""
        import app.scheduler
        app.scheduler._scheduler = None

        status = get_scheduler_status()

        assert status["running"] is False
        assert status["jobs"] == []

    def test_get_scheduler_status_when_running(self):
        """Test get_scheduler_status returns job information when running"""
        mock_job = MagicMock()
        mock_job.id = "test_job"
        mock_job.name = "Test Job"
        mock_job.next_run_time = None
        mock_job.trigger = "interval"

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.get_jobs.return_value = [mock_job]

        import app.scheduler
        app.scheduler._scheduler = mock_scheduler

        status = get_scheduler_status()

        assert status["running"] is True
        assert len(status["jobs"]) == 1
        assert status["job_count"] == 1
        assert status["jobs"][0]["id"] == "test_job"


class TestRunManualCollection:
    """Test manual data collection trigger"""

    @pytest.mark.asyncio
    async def test_run_manual_collection_calls_collect_all(self):
        """Test that manual collection triggers collect_all_data"""
        with patch('app.scheduler.collect_all_data', new_callable=AsyncMock) as mock_collect:
            await run_manual_collection()

            mock_collect.assert_called_once()


class TestTradingPairsAndIntervals:
    """Test trading pairs and interval constants"""

    def test_trading_pairs_defined(self):
        """Test that trading pairs are defined"""
        assert len(TRADING_PAIRS) > 0
        assert "BTCUSDT" in TRADING_PAIRS
        assert "ETHUSDT" in TRADING_PAIRS

    def test_kline_intervals_defined(self):
        """Test that kline intervals are defined"""
        assert len(KLINE_INTERVALS) > 0
        assert "1" in KLINE_INTERVALS
        assert "60" in KLINE_INTERVALS
        assert "D" in KLINE_INTERVALS

    def test_trading_pairs_are_uppercase(self):
        """Test that all trading pairs are uppercase"""
        for pair in TRADING_PAIRS:
            assert pair == pair.upper()

    def test_no_duplicate_trading_pairs(self):
        """Test that there are no duplicate trading pairs"""
        assert len(TRADING_PAIRS) == len(set(TRADING_PAIRS))

    def test_no_duplicate_intervals(self):
        """Test that there are no duplicate intervals"""
        assert len(KLINE_INTERVALS) == len(set(KLINE_INTERVALS))
