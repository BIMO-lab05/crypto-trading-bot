"""
Market Data Service - Scheduler Tests
Purpose: Test automated data collection scheduling
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.scheduler import (
    collect_ticker_data,
    collect_kline_data,
    collect_all_data,
    start_scheduler,
    stop_scheduler,
    get_scheduler_status,
    run_manual_collection,
    _trading_pairs,
    KLINE_INTERVALS,
)


# Deterministic symbol set used by the collect_* tests. Decoupled from
# settings so the test assertions don't drift when default_symbols changes.
TEST_PAIRS = ["BTCUSDT", "ETHUSDT"]


def _patch_trading_pairs(symbols=None):
    """Patch the scheduler's _trading_pairs accessor to a fixed list."""
    return patch("app.scheduler._trading_pairs", return_value=symbols or TEST_PAIRS)


class TestCollectTickerData:
    """Test ticker data collection job"""

    @pytest.mark.asyncio
    async def test_collect_ticker_data_success(self):
        """Test successful ticker data collection for all symbols"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_ticker = AsyncMock(
            return_value={"symbol": "BTCUSDT", "last_price": "50000"}
        )

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.TickerRepository", return_value=mock_ticker_repo),
        ):
            await collect_ticker_data()

            assert mock_fetcher.get_ticker.call_count == len(TEST_PAIRS)
            assert mock_ticker_repo.save_ticker.call_count == len(TEST_PAIRS)

    @pytest.mark.asyncio
    async def test_collect_ticker_data_handles_no_data(self):
        """Test handling when ticker returns None"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_ticker = AsyncMock(return_value=None)

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.TickerRepository", return_value=mock_ticker_repo),
        ):
            await collect_ticker_data()

            assert mock_ticker_repo.save_ticker.call_count == 0

    @pytest.mark.asyncio
    async def test_collect_ticker_data_handles_exceptions(self):
        """Test that exceptions don't stop collection for other symbols"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_ticker = AsyncMock(
            side_effect=[
                Exception("Connection error"),
                {"symbol": "ETHUSDT", "last_price": "3000"},
            ]
        )

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.TickerRepository", return_value=mock_ticker_repo),
        ):
            await collect_ticker_data()

            assert mock_fetcher.get_ticker.call_count == len(TEST_PAIRS)

    @pytest.mark.asyncio
    async def test_collect_ticker_data_calls_all_symbols(self):
        """Test that all trading pairs are processed"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_ticker = AsyncMock(return_value={"data": "value"})

        mock_ticker_repo = MagicMock()
        mock_ticker_repo.save_ticker = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.TickerRepository", return_value=mock_ticker_repo),
        ):
            await collect_ticker_data()

            called_symbols = [
                ca[1]["symbol"] for ca in mock_fetcher.get_ticker.call_args_list
            ]
            for symbol in TEST_PAIRS:
                assert symbol in called_symbols


class TestCollectKlineData:
    """Test kline data collection job"""

    @pytest.mark.asyncio
    async def test_collect_kline_data_success(self):
        """Test successful kline data collection"""
        mock_klines = [{"timestamp": 123, "open": "50000", "close": "50500"}]

        mock_fetcher = MagicMock()

        # scheduler closes the fetcher's httpx pool in a finally block

        # (`await fetcher.close()`), so close() must be awaitable.

        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_kline = AsyncMock(return_value=mock_klines)

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=len(mock_klines))

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.KlineRepository", return_value=mock_kline_repo),
            patch("app.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            await collect_kline_data()

            expected_calls = len(TEST_PAIRS) * len(KLINE_INTERVALS)
            assert mock_fetcher.get_kline.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_collect_kline_data_adds_metadata(self):
        """Test that symbol and interval are added to klines"""
        mock_klines = [{"timestamp": 123, "open": "50000"}]

        mock_fetcher = MagicMock()

        # scheduler closes the fetcher's httpx pool in a finally block

        # (`await fetcher.close()`), so close() must be awaitable.

        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_kline = AsyncMock(return_value=mock_klines.copy())

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.KlineRepository", return_value=mock_kline_repo),
            patch("app.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            await collect_kline_data()

            if mock_kline_repo.bulk_upsert.call_count > 0:
                first_call_klines = mock_kline_repo.bulk_upsert.call_args_list[0][0][0]
                assert "symbol" in first_call_klines[0]
                assert "interval" in first_call_klines[0]

    @pytest.mark.asyncio
    async def test_collect_kline_data_handles_empty_response(self):
        """Test handling when no klines are returned"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_kline = AsyncMock(return_value=[])

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.KlineRepository", return_value=mock_kline_repo),
            patch("app.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            await collect_kline_data()

            assert mock_kline_repo.bulk_upsert.call_count == 0

    @pytest.mark.asyncio
    async def test_collect_kline_data_respects_rate_limiting(self):
        """Test that sleep is called between requests for rate limiting"""
        mock_fetcher = MagicMock()
        # scheduler closes the fetcher's httpx pool in a finally block
        # (`await fetcher.close()`), so close() must be awaitable.
        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_kline = AsyncMock(return_value=[{"data": "value"}])

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        mock_sleep = AsyncMock()

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.KlineRepository", return_value=mock_kline_repo),
            patch("app.scheduler.asyncio.sleep", mock_sleep),
        ):
            await collect_kline_data()

            expected_calls = len(TEST_PAIRS) * len(KLINE_INTERVALS)
            assert mock_sleep.call_count == expected_calls
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

        # scheduler closes the fetcher's httpx pool in a finally block

        # (`await fetcher.close()`), so close() must be awaitable.

        mock_fetcher.close = AsyncMock()
        mock_fetcher.get_kline = AsyncMock(side_effect=side_effect_get_kline)

        mock_kline_repo = MagicMock()
        mock_kline_repo.bulk_upsert = AsyncMock(return_value=1)

        with (
            _patch_trading_pairs(),
            patch("app.scheduler.BybitDataFetcher", return_value=mock_fetcher),
            patch("app.scheduler.KlineRepository", return_value=mock_kline_repo),
            patch("app.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            await collect_kline_data()


class TestCollectAllData:
    """Test combined data collection job"""

    @pytest.mark.asyncio
    async def test_collect_all_data_calls_both_collectors(self):
        """Test that collect_all_data calls both ticker and kline collectors"""
        mock_sleep = AsyncMock()

        with (
            patch(
                "app.scheduler.collect_ticker_data", new_callable=AsyncMock
            ) as mock_ticker,
            patch(
                "app.scheduler.collect_kline_data", new_callable=AsyncMock
            ) as mock_kline,
            patch("app.scheduler.asyncio.sleep", mock_sleep),
        ):
            await collect_all_data()

            mock_ticker.assert_called_once()
            mock_kline.assert_called_once()
            mock_sleep.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_collect_all_data_handles_exceptions(self):
        """Test that collect_all_data handles exceptions gracefully"""
        with (
            patch(
                "app.scheduler.collect_ticker_data",
                new_callable=AsyncMock,
                side_effect=Exception("Error"),
            ),
            patch("app.scheduler.collect_kline_data", new_callable=AsyncMock),
            patch("app.scheduler.asyncio.sleep", new_callable=AsyncMock),
        ):
            await collect_all_data()


class TestSchedulerManagement:
    """Test scheduler start/stop/status"""

    def test_start_scheduler_creates_scheduler(self):
        """Test that start_scheduler initializes the scheduler"""
        with patch("app.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.get_jobs.return_value = []

            import app.scheduler

            app.scheduler._scheduler = None

            start_scheduler()

            mock_scheduler_class.assert_called_once()
            mock_scheduler.start.assert_called_once()

    def test_start_scheduler_adds_jobs(self):
        """Test that start_scheduler adds all required jobs"""
        with patch("app.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler_class.return_value = mock_scheduler
            mock_scheduler.get_jobs.return_value = []

            import app.scheduler

            app.scheduler._scheduler = None

            start_scheduler()

            # 5 jobs: ticker, kline, orderbook snapshots, open interest
            # (edge-search v2 A2), hourly full collection
            assert mock_scheduler.add_job.call_count == 5

    def test_start_scheduler_prevents_double_start(self):
        """Test that start_scheduler doesn't create duplicate scheduler"""
        mock_scheduler = MagicMock()

        import app.scheduler

        app.scheduler._scheduler = mock_scheduler

        start_scheduler()

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
        with patch(
            "app.scheduler.collect_all_data", new_callable=AsyncMock
        ) as mock_collect:
            await run_manual_collection()

            mock_collect.assert_called_once()


class TestTradingPairsAccessor:
    """Test the _trading_pairs accessor and exclusion rules.

    Source of truth is settings.default_symbols. The 2026-05-15 rewrite
    removed the hardcoded TRADING_PAIRS list that was silently re-adding
    XRPUSDT + DOGEUSDT in violation of the project rule. Regression tests
    here pin that behavior.
    """

    def test_trading_pairs_non_empty(self):
        pairs = _trading_pairs()
        assert len(pairs) > 0

    def test_core_majors_present(self):
        pairs = _trading_pairs()
        assert "BTCUSDT" in pairs
        assert "ETHUSDT" in pairs

    def test_excluded_symbols_absent(self):
        """XRP and DOGE must stay out — re-add must be deliberate, never silent."""
        pairs = _trading_pairs()
        assert "XRPUSDT" not in pairs, (
            "XRPUSDT re-introduced — violates exclusion rule (CLAUDE.md)"
        )
        assert "DOGEUSDT" not in pairs, (
            "DOGEUSDT re-introduced — violates exclusion rule (CLAUDE.md)"
        )

    def test_pairs_are_uppercase(self):
        for pair in _trading_pairs():
            assert pair == pair.upper()

    def test_no_duplicate_pairs(self):
        pairs = _trading_pairs()
        assert len(pairs) == len(set(pairs))

    def test_pairs_match_settings_default_symbols(self):
        """The accessor must read straight from settings, not a hardcoded constant."""
        from app.config import get_settings

        assert _trading_pairs() == get_settings().symbols_list

    def test_backward_compat_TRADING_PAIRS_attr_resolves(self):
        """`from app.scheduler import TRADING_PAIRS` must still work via __getattr__."""
        from app.scheduler import TRADING_PAIRS

        assert isinstance(TRADING_PAIRS, list)
        assert TRADING_PAIRS == _trading_pairs()


class TestKlineIntervals:
    """Test kline interval constant."""

    def test_kline_intervals_defined(self):
        assert len(KLINE_INTERVALS) > 0
        assert "1" in KLINE_INTERVALS
        assert "60" in KLINE_INTERVALS
        assert "D" in KLINE_INTERVALS

    def test_no_duplicate_intervals(self):
        assert len(KLINE_INTERVALS) == len(set(KLINE_INTERVALS))
