"""
Tests for Real Data Provider and Walk-Forward Integration
Tests cover: RealDataProvider, CachedDataProvider, Walk-Forward Analysis
"""

import pytest
from datetime import datetime, timedelta
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.backtesting.data_provider import (
    RealDataProvider,
    CachedDataProvider,
    DataProviderError,
    DataProviderBase,
    create_data_provider
)
from app.backtesting.strategy_base import OHLCV


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_kline_response():
    """Mock kline data response from market-data-service"""
    # Use recent timestamps (within last day) so they pass the time range filter
    import time
    now_ms = int(time.time() * 1000)
    hour_ms = 3600000

    return [
        {
            "timestamp": now_ms - (3 * hour_ms),  # 3 hours ago
            "open": "50000.0",
            "high": "50500.0",
            "low": "49500.0",
            "close": "50200.0",
            "volume": "1000.0"
        },
        {
            "timestamp": now_ms - (2 * hour_ms),  # 2 hours ago
            "open": "50200.0",
            "high": "50700.0",
            "low": "50000.0",
            "close": "50400.0",
            "volume": "1200.0"
        },
        {
            "timestamp": now_ms - hour_ms,  # 1 hour ago
            "open": "50400.0",
            "high": "50800.0",
            "low": "50200.0",
            "close": "50600.0",
            "volume": "1100.0"
        }
    ]


@pytest.fixture
def sample_ohlcv_bars() -> List[OHLCV]:
    """Generate sample OHLCV data"""
    bars = []
    start_time = datetime(2024, 1, 1)
    price = 50000.0

    for i in range(100):
        bar = OHLCV(
            timestamp=start_time + timedelta(hours=i),
            open=price + i * 10,
            high=price + i * 10 + 50,
            low=price + i * 10 - 30,
            close=price + i * 10 + 20,
            volume=1000.0 + i * 10
        )
        bars.append(bar)

    return bars


# =============================================================================
# Test RealDataProvider
# =============================================================================

class TestRealDataProvider:
    """Tests for RealDataProvider class"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test provider initialization with default config"""
        provider = RealDataProvider()
        assert provider.base_url is not None
        assert provider._client is not None
        await provider.close()

    @pytest.mark.asyncio
    async def test_initialization_with_custom_url(self):
        """Test provider initialization with custom URL"""
        custom_url = "http://custom-service:9000"
        provider = RealDataProvider(base_url=custom_url)
        assert provider.base_url == custom_url
        await provider.close()

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await provider.health_check()
            assert result is True
            mock_get.assert_called_once_with("/health")

        await provider.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get') as mock_get:
            mock_get.side_effect = Exception("Connection failed")

            result = await provider.health_check()
            assert result is False

        await provider.close()

    @pytest.mark.asyncio
    async def test_convert_to_ohlcv(self, mock_kline_response):
        """Test kline to OHLCV conversion"""
        provider = RealDataProvider()

        bars = provider._convert_to_ohlcv(mock_kline_response, "BTCUSDT")

        assert len(bars) == 3
        assert all(isinstance(bar, OHLCV) for bar in bars)
        assert bars[0].open == 50000.0
        assert bars[0].high == 50500.0
        assert bars[0].low == 49500.0
        assert bars[0].close == 50200.0
        assert bars[0].volume == 1000.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_convert_to_ohlcv_handles_invalid_data(self):
        """Test conversion handles invalid kline data gracefully"""
        provider = RealDataProvider()

        invalid_data = [
            {"timestamp": 1704067200000, "open": "invalid", "high": "50500.0",
             "low": "49500.0", "close": "50200.0", "volume": "1000.0"},
            {"timestamp": 1704070800000, "open": "50200.0", "high": "50700.0",
             "low": "50000.0", "close": "50400.0", "volume": "1200.0"}
        ]

        bars = provider._convert_to_ohlcv(invalid_data, "BTCUSDT")

        # Should skip invalid bar and return only valid one
        assert len(bars) == 1
        assert bars[0].open == 50200.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_convert_to_ohlcv_validates_price_data(self):
        """Test conversion validates OHLCV price relationships"""
        provider = RealDataProvider()

        # High < Low is invalid
        invalid_data = [
            {"timestamp": 1704067200000, "open": "50000.0", "high": "49000.0",
             "low": "51000.0", "close": "50200.0", "volume": "1000.0"}
        ]

        bars = provider._convert_to_ohlcv(invalid_data, "BTCUSDT")

        # Should skip bar with invalid high/low relationship
        assert len(bars) == 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_historical_data_success(self, mock_kline_response):
        """Test successful historical data fetch"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_kline_response
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

            assert len(bars) > 0
            assert all(isinstance(bar, OHLCV) for bar in bars)

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_historical_data_wrapped_response(self, mock_kline_response):
        """Test handling wrapped response format"""
        provider = RealDataProvider()

        wrapped_response = {
            "success": True,
            "data": mock_kline_response
        }

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = wrapped_response
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

            assert len(bars) > 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_historical_data_http_error(self):
        """Test handling HTTP errors"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_get.return_value = mock_response

            with pytest.raises(DataProviderError) as exc_info:
                await provider.get_historical_data(
                    symbol="BTCUSDT",
                    interval="60",
                    days=1
                )

            assert "HTTP 500" in str(exc_info.value)

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_historical_data_network_error(self):
        """Test handling network errors"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.RequestError("Network error")

            with pytest.raises(DataProviderError) as exc_info:
                await provider.get_historical_data(
                    symbol="BTCUSDT",
                    interval="60",
                    days=1
                )

            assert "Network error" in str(exc_info.value)

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_historical_data_deduplicates(self, mock_kline_response):
        """Test that duplicate bars are removed"""
        provider = RealDataProvider()

        # Response with duplicate timestamps
        duplicate_response = mock_kline_response + mock_kline_response

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = duplicate_response
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

            # Should deduplicate
            assert len(bars) == 3

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_latest_price_success(self):
        """Test getting latest price"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"last_price": "50000.50"}
            mock_get.return_value = mock_response

            price = await provider.get_latest_price("BTCUSDT")

            assert price == 50000.50

        await provider.close()

    @pytest.mark.asyncio
    async def test_get_latest_price_error(self):
        """Test handling price fetch error"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Error")

            price = await provider.get_latest_price("BTCUSDT")

            assert price is None

        await provider.close()


# =============================================================================
# Test CachedDataProvider
# =============================================================================

class TestCachedDataProvider:
    """Tests for CachedDataProvider class"""

    @pytest.mark.asyncio
    async def test_cache_hit(self, sample_ohlcv_bars):
        """Test cache hit returns cached data"""
        mock_provider = MagicMock(spec=DataProviderBase)
        mock_provider.get_historical_data = AsyncMock(return_value=sample_ohlcv_bars)

        cached_provider = CachedDataProvider(mock_provider)

        # First call - should fetch from provider
        bars1 = await cached_provider.get_historical_data(
            symbol="BTCUSDT",
            interval="60",
            days=1
        )

        # Second call - should hit cache
        bars2 = await cached_provider.get_historical_data(
            symbol="BTCUSDT",
            interval="60",
            days=1
        )

        # Provider should only be called once
        assert mock_provider.get_historical_data.call_count == 1
        assert bars1 == bars2

    @pytest.mark.asyncio
    async def test_cache_miss_different_params(self, sample_ohlcv_bars):
        """Test cache miss for different parameters"""
        mock_provider = MagicMock(spec=DataProviderBase)
        mock_provider.get_historical_data = AsyncMock(return_value=sample_ohlcv_bars)

        cached_provider = CachedDataProvider(mock_provider)

        # First call
        await cached_provider.get_historical_data(
            symbol="BTCUSDT",
            interval="60",
            days=1
        )

        # Second call with different params - cache miss
        await cached_provider.get_historical_data(
            symbol="ETHUSDT",  # Different symbol
            interval="60",
            days=1
        )

        # Provider should be called twice
        assert mock_provider.get_historical_data.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_size_limit(self, sample_ohlcv_bars):
        """Test cache evicts old entries when full"""
        mock_provider = MagicMock(spec=DataProviderBase)
        mock_provider.get_historical_data = AsyncMock(return_value=sample_ohlcv_bars)

        cached_provider = CachedDataProvider(mock_provider, max_cache_size=2)

        # Fill cache
        await cached_provider.get_historical_data("BTCUSDT", "60", 1)
        await cached_provider.get_historical_data("ETHUSDT", "60", 1)
        await cached_provider.get_historical_data("SOLUSDT", "60", 1)  # Should evict first

        # First entry should be evicted
        assert len(cached_provider._cache) == 2
        assert "BTCUSDT:60:1" not in cached_provider._cache

    def test_clear_cache(self):
        """Test cache clearing"""
        mock_provider = MagicMock(spec=DataProviderBase)
        cached_provider = CachedDataProvider(mock_provider)

        cached_provider._cache["key1"] = []
        cached_provider._cache["key2"] = []

        cached_provider.clear_cache()

        assert len(cached_provider._cache) == 0

    @pytest.mark.asyncio
    async def test_health_check_delegates(self):
        """Test health check delegates to underlying provider"""
        mock_provider = MagicMock(spec=DataProviderBase)
        mock_provider.health_check = AsyncMock(return_value=True)

        cached_provider = CachedDataProvider(mock_provider)

        result = await cached_provider.health_check()

        assert result is True
        mock_provider.health_check.assert_called_once()


# =============================================================================
# Test Factory Function
# =============================================================================

class TestCreateDataProvider:
    """Tests for create_data_provider factory function"""

    def test_create_real_provider(self):
        """Test creating real data provider"""
        provider = create_data_provider("real", use_cache=False)
        assert isinstance(provider, RealDataProvider)

    def test_create_cached_provider(self):
        """Test creating cached provider"""
        provider = create_data_provider("real", use_cache=True)
        assert isinstance(provider, CachedDataProvider)

    def test_create_unknown_provider_raises(self):
        """Test unknown provider type raises error"""
        with pytest.raises(ValueError) as exc_info:
            create_data_provider("unknown")

        assert "Unknown provider type" in str(exc_info.value)


# =============================================================================
# Integration Tests
# =============================================================================

class TestDataProviderIntegration:
    """Integration tests for data provider with backtest engine"""

    @pytest.mark.asyncio
    async def test_provider_output_compatible_with_backtest(self, mock_kline_response):
        """Test that provider output is compatible with BacktestEngine"""
        from app.backtesting import BacktestEngine, BacktestConfig

        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_kline_response
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

        await provider.close()

        # Verify each bar has required fields for BacktestEngine
        for bar in bars:
            assert hasattr(bar, 'timestamp')
            assert hasattr(bar, 'open')
            assert hasattr(bar, 'high')
            assert hasattr(bar, 'low')
            assert hasattr(bar, 'close')
            assert hasattr(bar, 'volume')
            assert isinstance(bar.timestamp, datetime)
            assert isinstance(bar.open, float)
            assert isinstance(bar.high, float)
            assert isinstance(bar.low, float)
            assert isinstance(bar.close, float)
            assert isinstance(bar.volume, float)

    @pytest.mark.asyncio
    async def test_bars_sorted_by_timestamp(self, mock_kline_response):
        """Test that returned bars are sorted by timestamp"""
        provider = RealDataProvider()

        # Reverse the response to test sorting
        reversed_response = list(reversed(mock_kline_response))

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = reversed_response
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

        await provider.close()

        # Verify bars are sorted (oldest first)
        for i in range(1, len(bars)):
            assert bars[i].timestamp > bars[i-1].timestamp


# =============================================================================
# Walk-Forward Integration Tests
# =============================================================================

class TestWalkForwardIntegration:
    """Tests for walk-forward analysis integration with backtest"""

    @pytest.mark.asyncio
    async def test_backtest_to_walk_forward_conversion(self):
        """Test converting backtest trades to walk-forward TradeData"""
        from app.backtesting import BacktestEngine, BacktestConfig, Trade
        from app.backtesting.strategy_base import RSIMomentumStrategy
        from app.backtesting.backtest_engine import generate_sample_data
        from app.handlers.backtest import _convert_trades_to_trade_data
        from app.trading_enhancements.walk_forward_tester import TradeData

        # Run a backtest
        config = BacktestConfig(initial_equity=10000.0)
        strategy = RSIMomentumStrategy(symbol="BTCUSDT")
        data = generate_sample_data(symbol="BTCUSDT", days=90)

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Convert trades
        trade_data = _convert_trades_to_trade_data(
            result.trades,
            strategy.get_name()
        )

        # Verify conversion
        assert len(trade_data) == len(result.trades)

        for i, td in enumerate(trade_data):
            assert isinstance(td, TradeData)
            assert td.trade_id == result.trades[i].trade_id
            assert td.symbol == result.trades[i].symbol
            assert td.side == result.trades[i].side
            assert td.entry_price == result.trades[i].entry_price
            assert td.exit_price == result.trades[i].exit_price
            assert td.strategy == strategy.get_name()

    @pytest.mark.asyncio
    async def test_walk_forward_with_backtest_trades(self):
        """Test running walk-forward analysis on backtest results"""
        from app.backtesting import BacktestEngine, BacktestConfig
        from app.backtesting.strategy_base import RSIMomentumStrategy
        from app.backtesting.backtest_engine import generate_sample_data
        from app.handlers.backtest import _convert_trades_to_trade_data
        from app.trading_enhancements.walk_forward_tester import (
            WalkForwardTester,
            WFEConfig,
            WFEStatus
        )

        # Run a longer backtest to get more trades
        config = BacktestConfig(initial_equity=10000.0)
        strategy = RSIMomentumStrategy(symbol="BTCUSDT")
        data = generate_sample_data(symbol="BTCUSDT", days=365)

        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Skip if insufficient trades
        if len(result.trades) < 30:
            pytest.skip("Insufficient trades for walk-forward test")

        # Convert trades
        trade_data = _convert_trades_to_trade_data(
            result.trades,
            strategy.get_name()
        )

        # Run walk-forward analysis
        wfe_config = WFEConfig(
            in_sample_pct=0.70,
            out_of_sample_pct=0.30,
            rolling_windows=3
        )

        tester = WalkForwardTester(config=wfe_config, strategy_name=strategy.get_name())
        tester.add_trades(trade_data)
        window_results = tester.run_walk_forward_test()
        report = tester.get_robustness_report()

        # Verify results
        assert len(window_results) > 0
        assert report.total_trades > 0
        assert report.overall_status in [
            WFEStatus.ROBUST,
            WFEStatus.MARGINAL,
            WFEStatus.OVERFIT,
            WFEStatus.INSUFFICIENT_DATA
        ]
        assert 0 <= report.avg_wfe_return <= 2.0
        assert 0 <= report.robust_percentage <= 100


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_empty_response_handling(self):
        """Test handling empty response from service"""
        provider = RealDataProvider()

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = []
            mock_get.return_value = mock_response

            bars = await provider.get_historical_data(
                symbol="BTCUSDT",
                interval="60",
                days=1
            )

            assert len(bars) == 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_malformed_timestamp_handling(self):
        """Test handling malformed timestamps"""
        provider = RealDataProvider()

        malformed_data = [
            {"timestamp": "invalid", "open": "50000.0", "high": "50500.0",
             "low": "49500.0", "close": "50200.0", "volume": "1000.0"}
        ]

        bars = provider._convert_to_ohlcv(malformed_data, "BTCUSDT")

        # Should skip malformed bar
        assert len(bars) == 0

        await provider.close()

    @pytest.mark.asyncio
    async def test_iso_timestamp_format(self):
        """Test handling ISO format timestamps"""
        provider = RealDataProvider()

        iso_data = [
            {"timestamp": "2024-01-01T00:00:00Z", "open": "50000.0", "high": "50500.0",
             "low": "49500.0", "close": "50200.0", "volume": "1000.0"}
        ]

        bars = provider._convert_to_ohlcv(iso_data, "BTCUSDT")

        assert len(bars) == 1
        assert bars[0].open == 50000.0

        await provider.close()

    @pytest.mark.asyncio
    async def test_service_error_response(self):
        """Test handling service error response"""
        provider = RealDataProvider()

        error_response = {
            "success": False,
            "error": "Symbol not found"
        }

        with patch.object(provider._client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = error_response
            mock_get.return_value = mock_response

            with pytest.raises(DataProviderError) as exc_info:
                await provider.get_historical_data(
                    symbol="INVALID",
                    interval="60",
                    days=1
                )

            assert "Symbol not found" in str(exc_info.value)

        await provider.close()
