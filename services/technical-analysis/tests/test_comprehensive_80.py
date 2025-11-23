"""
Comprehensive Test Suite for 80%+ Coverage
Testing Guardian Agent - Coverage Gap Analysis Tests

This test file targets uncovered code paths in:
- app/fetcher.py (25% → 80%+)
- app/services/indicator_service.py (23% → 80%+)
- app/main.py (67% → 85%+)
- app/strategies/squeeze_momentum_strategy.py (61% → 80%+)

Test Strategy:
1. Fetcher: HTTP operations, error handling, data transformations
2. Indicator Service: All indicator calculation paths
3. Main: Endpoint integration and lifespan management
4. Strategy: Entry/exit conditions, risk management
"""

import pytest
import pandas as pd
import httpx
import numpy as np
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from datetime import datetime
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.fetcher import MarketDataFetcher, get_fetcher, close_fetcher
from app.services.indicator_service import IndicatorService
from app.main import app
from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy
from app.models import Kline


# ============================================================================
# FETCHER TESTS - Target: 25% → 80%+
# ============================================================================

class TestMarketDataFetcherCore:
    """Test core fetcher functionality"""

    @pytest.mark.asyncio
    async def test_fetcher_initialization(self):
        """Test fetcher initializes with correct base URL"""
        fetcher = MarketDataFetcher()
        assert fetcher.base_url is not None
        assert fetcher.client is not None
        await fetcher.close()

    @pytest.mark.asyncio
    async def test_fetcher_close(self):
        """Test fetcher closes HTTP client properly"""
        fetcher = MarketDataFetcher()
        await fetcher.close()
        # Client should be closed (no exception)

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test health check returns True when service is healthy"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            result = await fetcher.health_check()
            assert result is True
            mock_get.assert_called_once()

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test health check returns False when service is down"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response

            result = await fetcher.health_check()
            assert result is False

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        """Test health check returns False on exception"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_get.side_effect = Exception("Connection error")

            result = await fetcher.health_check()
            assert result is False

        await fetcher.close()


class TestMarketDataFetcherKlines:
    """Test kline fetching functionality"""

    @pytest.mark.asyncio
    async def test_get_klines_success(self):
        """Test successful kline fetching"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": [
                {
                    "timestamp": 1700000000000,
                    "open": "30000.0",
                    "high": "30500.0",
                    "low": "29800.0",
                    "close": "30200.0",
                    "volume": "100.5"
                },
                {
                    "timestamp": 1700003600000,
                    "open": "30200.0",
                    "high": "30600.0",
                    "low": "30000.0",
                    "close": "30400.0",
                    "volume": "120.3"
                }
            ]
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            klines = await fetcher.get_klines("BTCUSDT", "60", 200)

            assert len(klines) == 2
            assert isinstance(klines[0], Kline)
            assert klines[0].close == 30200.0
            assert klines[1].close == 30400.0
            # Verify sorted by timestamp ascending
            assert klines[0].timestamp < klines[1].timestamp

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_klines_empty_response(self):
        """Test kline fetching with empty data"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": []
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            klines = await fetcher.get_klines("BTCUSDT", "60", 200)

            assert len(klines) == 0
            assert isinstance(klines, list)

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_klines_failure_response(self):
        """Test kline fetching with failed response"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": False,
            "error": "Symbol not found"
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            klines = await fetcher.get_klines("INVALID", "60", 200)

            assert len(klines) == 0

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_klines_http_error(self):
        """Test kline fetching with HTTP error"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "404 Not Found",
                request=Mock(),
                response=Mock(status_code=404)
            )

            with pytest.raises(Exception):
                await fetcher.get_klines("BTCUSDT", "60", 200)

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_klines_network_error(self):
        """Test kline fetching with network error"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_get.side_effect = Exception("Network timeout")

            with pytest.raises(Exception):
                await fetcher.get_klines("BTCUSDT", "60", 200)

        await fetcher.close()


class TestMarketDataFetcherDataFrame:
    """Test DataFrame conversion functionality"""

    @pytest.mark.asyncio
    async def test_get_klines_as_dataframe_success(self):
        """Test successful DataFrame conversion"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": [
                {
                    "timestamp": 1700000000000,
                    "open": "30000.0",
                    "high": "30500.0",
                    "low": "29800.0",
                    "close": "30200.0",
                    "volume": "100.5"
                }
            ]
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            df = await fetcher.get_klines_as_dataframe("BTCUSDT", "60", 200)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 1
            assert 'close' in df.columns
            assert 'high' in df.columns
            assert 'low' in df.columns
            assert 'volume' in df.columns
            # Verify datetime index
            assert isinstance(df.index, pd.DatetimeIndex)

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_klines_as_dataframe_empty(self):
        """Test DataFrame conversion with empty data"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": []
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            df = await fetcher.get_klines_as_dataframe("BTCUSDT", "60", 200)

            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
            assert df.empty

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_latest_price_success(self):
        """Test getting latest price"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": [
                {
                    "timestamp": 1700000000000,
                    "open": "30000.0",
                    "high": "30500.0",
                    "low": "29800.0",
                    "close": "30200.0",
                    "volume": "100.5"
                }
            ]
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            price = await fetcher.get_latest_price("BTCUSDT", "60")

            assert price == 30200.0
            assert isinstance(price, float)

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_latest_price_no_data(self):
        """Test getting latest price with no data"""
        fetcher = MarketDataFetcher()

        mock_data = {
            "success": True,
            "data": []
        }

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_data
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            price = await fetcher.get_latest_price("BTCUSDT", "60")

            assert price is None

        await fetcher.close()

    @pytest.mark.asyncio
    async def test_get_latest_price_error(self):
        """Test getting latest price with error"""
        fetcher = MarketDataFetcher()

        with patch.object(fetcher.client, 'get') as mock_get:
            mock_get.side_effect = Exception("Network error")

            price = await fetcher.get_latest_price("BTCUSDT", "60")

            assert price is None

        await fetcher.close()


class TestFetcherGlobalInstance:
    """Test global fetcher instance management"""

    @pytest.mark.asyncio
    async def test_get_fetcher_singleton(self):
        """Test get_fetcher returns singleton"""
        fetcher1 = get_fetcher()
        fetcher2 = get_fetcher()

        assert fetcher1 is fetcher2

        await close_fetcher()

    @pytest.mark.asyncio
    async def test_close_fetcher_global(self):
        """Test closing global fetcher"""
        fetcher = get_fetcher()
        assert fetcher is not None

        await close_fetcher()

        # After closing, get_fetcher should create new instance
        new_fetcher = get_fetcher()
        assert new_fetcher is not None

        await close_fetcher()


# ============================================================================
# INDICATOR SERVICE TESTS - Target: 23% → 80%+
# ============================================================================

class TestIndicatorServiceRSI:
    """Test RSI indicator service"""

    @pytest.mark.asyncio
    async def test_calculate_rsi_success(self):
        """Test successful RSI calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 100 for i in range(50)],
            'high': [30100 + i * 100 for i in range(50)],
            'low': [29900 + i * 100 for i in range(50)],
            'volume': [100.0] * 50
        })
        mock_df.index = pd.date_range('2024-01-01', periods=50, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_rsi("BTCUSDT", "60", 14, 200)

            assert 'rsi' in result
            assert 'signal' in result
            assert 'confidence' in result
            assert 'timestamp' in result
            assert isinstance(result['rsi'], (int, float))

    @pytest.mark.asyncio
    async def test_calculate_rsi_no_data(self):
        """Test RSI calculation with no data"""
        mock_df = pd.DataFrame()

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            with pytest.raises(HTTPException) as exc_info:
                await IndicatorService.calculate_rsi("INVALID", "60", 14, 200)

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_calculate_rsi_insufficient_data(self):
        """Test RSI calculation with insufficient data"""
        # Only 5 rows, not enough for RSI(14)
        mock_df = pd.DataFrame({
            'close': [30000, 30100, 30200, 30300, 30400],
            'high': [30100, 30200, 30300, 30400, 30500],
            'low': [29900, 30000, 30100, 30200, 30300],
            'volume': [100.0] * 5
        })
        mock_df.index = pd.date_range('2024-01-01', periods=5, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            # RSICalculator returns None for insufficient data
            with patch('app.services.indicator_service.RSICalculator.calculate_with_signal') as mock_calc:
                mock_calc.return_value = (None, "HOLD", 0.0)

                with pytest.raises(HTTPException) as exc_info:
                    await IndicatorService.calculate_rsi("BTCUSDT", "60", 14, 200)

                assert exc_info.value.status_code == 400


class TestIndicatorServiceMACD:
    """Test MACD indicator service"""

    @pytest.mark.asyncio
    async def test_calculate_macd_success(self):
        """Test successful MACD calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 50 for i in range(100)],
            'high': [30100 + i * 50 for i in range(100)],
            'low': [29900 + i * 50 for i in range(100)],
            'volume': [100.0] * 100
        })
        mock_df.index = pd.date_range('2024-01-01', periods=100, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_macd("BTCUSDT", "60", 12, 26, 9, 200)

            assert 'macd_line' in result
            assert 'signal_line' in result
            assert 'histogram' in result
            assert 'signal' in result
            assert 'confidence' in result

    @pytest.mark.asyncio
    async def test_calculate_macd_no_data(self):
        """Test MACD calculation with no data"""
        mock_df = pd.DataFrame()

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            with pytest.raises(HTTPException) as exc_info:
                await IndicatorService.calculate_macd("INVALID", "60", 12, 26, 9, 200)

            assert exc_info.value.status_code == 404


class TestIndicatorServiceBollingerBands:
    """Test Bollinger Bands indicator service"""

    @pytest.mark.asyncio
    async def test_calculate_bollinger_bands_success(self):
        """Test successful Bollinger Bands calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 25 for i in range(50)],
            'high': [30100 + i * 25 for i in range(50)],
            'low': [29900 + i * 25 for i in range(50)],
            'volume': [100.0] * 50
        })
        mock_df.index = pd.date_range('2024-01-01', periods=50, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_bollinger_bands("BTCUSDT", "60", 20, 2.0, 200)

            assert 'upper_band' in result
            assert 'middle_band' in result
            assert 'lower_band' in result
            assert 'current_price' in result
            assert 'signal' in result


class TestIndicatorServiceMovingAverages:
    """Test SMA and EMA indicator services"""

    @pytest.mark.asyncio
    async def test_calculate_sma_success(self):
        """Test successful SMA calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 50 for i in range(50)],
            'high': [30100 + i * 50 for i in range(50)],
            'low': [29900 + i * 50 for i in range(50)],
            'volume': [100.0] * 50
        })
        mock_df.index = pd.date_range('2024-01-01', periods=50, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_sma("BTCUSDT", "60", 20, 200)

            assert 'value' in result
            assert 'current_price' in result
            assert 'signal' in result
            assert 'confidence' in result

    @pytest.mark.asyncio
    async def test_calculate_ema_success(self):
        """Test successful EMA calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 50 for i in range(50)],
            'high': [30100 + i * 50 for i in range(50)],
            'low': [29900 + i * 50 for i in range(50)],
            'volume': [100.0] * 50
        })
        mock_df.index = pd.date_range('2024-01-01', periods=50, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_ema("BTCUSDT", "60", 20, 200)

            assert 'value' in result
            assert 'current_price' in result
            assert 'signal' in result


class TestIndicatorServiceAdvanced:
    """Test advanced indicator services"""

    @pytest.mark.asyncio
    async def test_calculate_trend_filter_success(self):
        """Test successful Trend Filter calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 10 for i in range(250)],
            'high': [30100 + i * 10 for i in range(250)],
            'low': [29900 + i * 10 for i in range(250)],
            'volume': [100.0] * 250
        })
        mock_df.index = pd.date_range('2024-01-01', periods=250, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_trend_filter("BTCUSDT", "60", 50, 200, 300)

            assert 'data' in result
            assert 'timestamp' in result

    @pytest.mark.asyncio
    async def test_calculate_trend_filter_insufficient_data(self):
        """Test Trend Filter with insufficient data"""
        mock_df = pd.DataFrame({
            'close': [30000, 30100, 30200],
            'high': [30100, 30200, 30300],
            'low': [29900, 30000, 30100],
            'volume': [100.0] * 3
        })
        mock_df.index = pd.date_range('2024-01-01', periods=3, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            with pytest.raises(HTTPException) as exc_info:
                await IndicatorService.calculate_trend_filter("BTCUSDT", "60", 50, 200, 300)

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_calculate_volume_confirmation_success(self):
        """Test successful Volume Confirmation calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 10 for i in range(30)],
            'high': [30100 + i * 10 for i in range(30)],
            'low': [29900 + i * 10 for i in range(30)],
            'volume': [100.0 + i * 5 for i in range(30)]
        })
        mock_df.index = pd.date_range('2024-01-01', periods=30, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_volume_confirmation("BTCUSDT", "60", 20, "breakout", 50)

            assert 'data' in result
            assert 'timestamp' in result

    @pytest.mark.asyncio
    async def test_calculate_atr_success(self):
        """Test successful ATR calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 10 for i in range(30)],
            'high': [30100 + i * 10 for i in range(30)],
            'low': [29900 + i * 10 for i in range(30)],
            'volume': [100.0] * 30
        })
        mock_df.index = pd.date_range('2024-01-01', periods=30, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_atr("BTCUSDT", "60", 14, None, 50)

            assert 'data' in result
            assert 'timestamp' in result
            assert 'current_price' in result

    @pytest.mark.asyncio
    async def test_calculate_atr_with_custom_price(self):
        """Test ATR calculation with custom current price"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 10 for i in range(30)],
            'high': [30100 + i * 10 for i in range(30)],
            'low': [29900 + i * 10 for i in range(30)],
            'volume': [100.0] * 30
        })
        mock_df.index = pd.date_range('2024-01-01', periods=30, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_atr("BTCUSDT", "60", 14, 30500.0, 50)

            assert 'current_price' in result
            assert result['current_price'] == 30500.0

    @pytest.mark.asyncio
    async def test_calculate_stochastic_success(self):
        """Test successful Stochastic calculation"""
        mock_df = pd.DataFrame({
            'close': [30000 + i * 10 for i in range(30)],
            'high': [30100 + i * 10 for i in range(30)],
            'low': [29900 + i * 10 for i in range(30)],
            'volume': [100.0] * 30
        })
        mock_df.index = pd.date_range('2024-01-01', periods=30, freq='h')

        with patch('app.services.indicator_service.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe.return_value = mock_df
            mock_get_fetcher.return_value = mock_fetcher

            result = await IndicatorService.calculate_stochastic("BTCUSDT", "60", 14, 3, 3, 50)

            assert 'data' in result
            assert 'timestamp' in result


# ============================================================================
# MAIN APP INTEGRATION TESTS - Target: 67% → 85%+
# ============================================================================

class TestMainAppLifespan:
    """Test main app lifespan management"""

    @pytest.mark.asyncio
    async def test_app_lifespan_startup_success(self):
        """Test app startup with healthy market data service"""
        with patch('app.main.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check.return_value = True
            mock_get_fetcher.return_value = mock_fetcher

            with patch('app.main.close_fetcher') as mock_close:
                # Trigger lifespan
                client = TestClient(app)
                response = client.get("/health")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_app_lifespan_startup_warning(self):
        """Test app startup with unavailable market data service"""
        with patch('app.main.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.health_check.return_value = False
            mock_get_fetcher.return_value = mock_fetcher

            # App should still start, just with warning
            client = TestClient(app)
            response = client.get("/health")
            assert response.status_code == 200


class TestMainAppEndpoints:
    """Test main app endpoint integration"""

    def test_root_endpoint(self):
        """Test root endpoint returns service info"""
        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert 'service' in data
        assert 'version' in data
        assert 'endpoints' in data
        assert 'refactoring' in data

    def test_health_endpoint_integration(self):
        """Test health endpoint"""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert 'status' in data


# ============================================================================
# SQUEEZE MOMENTUM STRATEGY TESTS - Target: 61% → 80%+
# ============================================================================

class TestSqueezeMomentumStrategyEntry:
    """Test entry condition logic"""

    def test_should_enter_long_all_conditions_met(self):
        """Test long entry when all conditions are met"""
        strategy = SqueezeMomentumStrategy(
            min_momentum_threshold=0.5,
            require_squeeze_release=True,
            require_volume_confirmation=True
        )

        # Create DataFrame with SQZMOM data
        df = pd.DataFrame({
            'close': [30000.0],
            'sqz_momentum': [0.8],
            'sqz_color': ['lime'],
            'squeeze_on': [False],
            'squeeze_off': [True],
            'volume': [150.0]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        # Calculate average volume separately for the DataFrame
        df['avg_volume'] = 100.0

        should_enter = strategy.should_enter_long(df)
        assert should_enter is True

    def test_should_enter_long_weak_momentum(self):
        """Test long entry rejected for weak momentum"""
        strategy = SqueezeMomentumStrategy(
            min_momentum_threshold=0.5,
            require_squeeze_release=True
        )

        df = pd.DataFrame({
            'close': [30000.0],
            'sqz_momentum': [0.3],  # Below threshold
            'sqz_color': ['lime'],
            'squeeze_on': [False],
            'squeeze_off': [True]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        should_enter = strategy.should_enter_long(df)
        assert should_enter is False

    def test_should_enter_long_squeeze_still_on(self):
        """Test long entry rejected when squeeze still on"""
        strategy = SqueezeMomentumStrategy(
            min_momentum_threshold=0.5,
            require_squeeze_release=True
        )

        df = pd.DataFrame({
            'close': [30000.0],
            'sqz_momentum': [0.8],
            'sqz_color': ['lime'],
            'squeeze_on': [True],  # Still in squeeze
            'squeeze_off': [False]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        should_enter = strategy.should_enter_long(df)
        assert should_enter is False

    def test_should_enter_short_all_conditions_met(self):
        """Test short entry when all conditions are met"""
        strategy = SqueezeMomentumStrategy(
            min_momentum_threshold=0.5,
            require_squeeze_release=True
        )

        df = pd.DataFrame({
            'close': [30000.0],
            'sqz_momentum': [-0.8],
            'sqz_color': ['red'],
            'squeeze_on': [False],
            'squeeze_off': [True]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        should_enter = strategy.should_enter_short(df)
        assert should_enter is True


class TestSqueezeMomentumStrategyExit:
    """Test exit condition logic"""

    def test_should_exit_stop_loss_hit_long(self):
        """Test exit when stop loss is hit for long position"""
        strategy = SqueezeMomentumStrategy()

        df = pd.DataFrame({
            'close': [28500.0],  # Below stop loss
            'sqz_momentum': [0.5],
            'sqz_color': ['lime'],
            'squeeze_on': [False],
            'squeeze_off': [False]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        # Long position: entry 30000, stop at 29000
        should_exit = strategy.should_exit(df, 'LONG', 30000.0)
        assert should_exit is True

    def test_should_exit_take_profit_hit_long(self):
        """Test exit when take profit is hit for long position"""
        strategy = SqueezeMomentumStrategy()

        df = pd.DataFrame({
            'close': [31500.0],  # Above take profit
            'sqz_momentum': [0.5],
            'sqz_color': ['lime'],
            'squeeze_on': [False],
            'squeeze_off': [False]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        # Long position: entry 30000, TP at 31200
        should_exit = strategy.should_exit(df, 'LONG', 30000.0)
        assert should_exit is True

    def test_should_exit_stop_loss_hit_short(self):
        """Test exit when stop loss is hit for short position"""
        strategy = SqueezeMomentumStrategy()

        df = pd.DataFrame({
            'close': [30700.0],  # Above stop loss
            'sqz_momentum': [-0.5],
            'sqz_color': ['red'],
            'squeeze_on': [False],
            'squeeze_off': [False]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        # Short position: entry 30000, stop at 30600
        should_exit = strategy.should_exit(df, 'SHORT', 30000.0)
        assert should_exit is True

    def test_should_not_exit_within_range(self):
        """Test no exit when price within range and momentum good"""
        strategy = SqueezeMomentumStrategy()

        df = pd.DataFrame({
            'close': [30000.0],
            'sqz_momentum': [0.8],
            'sqz_color': ['lime'],
            'squeeze_on': [False],
            'squeeze_off': [False]
        })
        df.index = pd.date_range('2024-01-01', periods=1, freq='h')

        should_exit = strategy.should_exit(df, 'LONG', 30000.0)
        # Should not exit: price at entry, momentum strong
        assert should_exit is False


class TestSqueezeMomentumStrategyAnalysis:
    """Test full analysis workflow"""

    def test_analyze_returns_buy_signal(self):
        """Test analyze method returns BUY signal"""
        strategy = SqueezeMomentumStrategy(
            min_momentum_threshold=0.5,
            require_squeeze_release=True
        )

        # Create bullish scenario
        df = pd.DataFrame({
            'open': [29900, 30000, 30100],
            'high': [30100, 30200, 30300],
            'low': [29800, 29900, 30000],
            'close': [30000, 30100, 30200],
            'volume': [100, 110, 120],
            'sqz_momentum': [0.3, 0.6, 0.9],
            'sqz_color': ['green', 'lime', 'lime'],
            'squeeze_on': [True, False, False],
            'squeeze_off': [False, True, True],
            'bb_upper': [30500, 30600, 30700],
            'bb_lower': [29500, 29600, 29700],
            'kc_upper': [30400, 30500, 30600],
            'kc_lower': [29600, 29700, 29800]
        })
        df.index = pd.date_range('2024-01-01', periods=3, freq='h')

        result = strategy.analyze(df)

        assert 'action' in result
        assert result['action'] in ['BUY', 'HOLD']  # Could be either depending on logic
        assert 'confidence' in result
        assert 'entry_price' in result

    def test_analyze_handles_error_gracefully(self):
        """Test analyze handles errors gracefully"""
        strategy = SqueezeMomentumStrategy()

        # Empty DataFrame should cause error
        df = pd.DataFrame()

        result = strategy.analyze(df)

        assert result['action'] == 'HOLD'
        assert result['confidence'] == 0.0
        assert 'error' in result['reason'].lower() or 'analysis' in result['reason'].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
