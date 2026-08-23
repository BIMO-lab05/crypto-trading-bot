"""
Unit Tests for Signal Aggregator
Tests signal fetching and aggregation logic with mocked HTTP calls
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
import httpx

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from app.signal_aggregator import SignalAggregator
from app.models import SignalAction, IndicatorSignal, TradingSignal


class TestSignalAggregator:
    """Test suite for SignalAggregator"""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings configuration"""
        settings = Mock()
        settings.technical_analysis_url = "http://localhost:8002"
        settings.min_signal_confidence = 0.7
        return settings

    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client"""
        client = AsyncMock(spec=httpx.AsyncClient)
        client.aclose = AsyncMock()
        return client

    @pytest.fixture
    def mock_core_aggregator(self):
        """Mock CoreAggregator"""
        aggregator = Mock()
        aggregator.voter = Mock()
        aggregator.voter.signal_to_score = Mock(side_effect=lambda s: {
            SignalAction.BUY: 1.0,
            SignalAction.SELL: -1.0,
            SignalAction.HOLD: 0.0
        }.get(s, 0.0))
        aggregator.aggregate_signals = Mock(return_value=TradingSignal(
            symbol="BTCUSDT",
            action=SignalAction.BUY,
            confidence=0.85,
            timestamp=1234567890,
            indicators={},
            aggregated_score=0.75,
            consensus_count=5
        ))
        return aggregator

    @pytest.fixture
    def signal_aggregator(self, mock_settings, mock_http_client, mock_core_aggregator):
        """Create SignalAggregator with mocked dependencies"""
        with patch('app.signal_aggregator.get_settings', return_value=mock_settings), \
             patch('app.signal_aggregator.httpx.AsyncClient', return_value=mock_http_client), \
             patch('app.signal_aggregator.CoreAggregator', return_value=mock_core_aggregator):

            aggregator = SignalAggregator()
            return aggregator

    def test_initialization(self, signal_aggregator, mock_settings):
        """Test signal aggregator initializes correctly"""
        assert signal_aggregator.settings == mock_settings
        assert signal_aggregator.base_url == "http://localhost:8002"
        assert signal_aggregator.client is not None
        assert signal_aggregator.core_aggregator is not None

    @pytest.mark.asyncio
    async def test_close(self, signal_aggregator, mock_http_client):
        """Test closing HTTP client"""
        await signal_aggregator.close()
        mock_http_client.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_health_check_success(self, signal_aggregator, mock_http_client):
        """Test health check with successful response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.health_check()

        assert result is True
        mock_http_client.get.assert_called_once_with("http://localhost:8002/health")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, signal_aggregator, mock_http_client):
        """Test health check with failed response"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self, signal_aggregator, mock_http_client):
        """Test health check with exception"""
        mock_http_client.get = AsyncMock(side_effect=Exception("Connection error"))

        result = await signal_aggregator.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_rsi_success(self, signal_aggregator, mock_http_client):
        """Test fetching RSI indicator successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "signal": "BUY",
            "confidence": 0.85,
            "rsi": 35.5
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_rsi("BTCUSDT", interval="60", period=14)

        assert result is not None
        assert result.name == "RSI"
        assert result.signal == SignalAction.BUY
        assert result.confidence == 0.85
        assert result.value == 35.5

    @pytest.mark.asyncio
    async def test_fetch_rsi_failure(self, signal_aggregator, mock_http_client):
        """Test fetching RSI with error"""
        mock_http_client.get = AsyncMock(side_effect=Exception("API error"))

        result = await signal_aggregator.fetch_rsi("BTCUSDT")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_macd_success(self, signal_aggregator, mock_http_client):
        """Test fetching MACD indicator successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "signal": "SELL",
            "confidence": 0.75,
            "histogram": -2.5,
            "macd_line": 10.2,
            "signal_line": 12.7
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_macd("ETHUSDT")

        assert result is not None
        assert result.name == "MACD"
        assert result.signal == SignalAction.SELL
        assert result.confidence == 0.75
        assert result.value == -2.5
        assert result.metadata["macd_line"] == 10.2

    @pytest.mark.asyncio
    async def test_fetch_bollinger_bands_success(self, signal_aggregator, mock_http_client):
        """Test fetching Bollinger Bands successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "signal": "BUY",
            "confidence": 0.80,
            "current_price": 50000.0,
            "upper_band": 52000.0,
            "middle_band": 50000.0,
            "lower_band": 48000.0
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_bollinger_bands("BTCUSDT")

        assert result is not None
        assert result.name == "BOLLINGER_BANDS"
        assert result.signal == SignalAction.BUY
        assert result.metadata["upper_band"] == 52000.0

    @pytest.mark.asyncio
    async def test_fetch_trend_filter_success(self, signal_aggregator, mock_http_client):
        """Test fetching trend filter successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "signal": "BUY",
                "confidence": 0.90,
                "spread_pct": 5.2,
                "trend": "UPTREND",
                "fast_ema": 50500.0,
                "slow_ema": 48000.0
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_trend_filter("BTCUSDT")

        assert result is not None
        assert result.name == "TREND_FILTER"
        assert result.signal == SignalAction.BUY
        assert result.metadata["trend"] == "UPTREND"
        assert result.metadata["role"] == "GATEKEEPER"

    @pytest.mark.asyncio
    async def test_fetch_volume_confirmation_confirmed(self, signal_aggregator, mock_http_client):
        """Test fetching volume confirmation with confirmed signal"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "confirmed": True,
                "confidence": 0.85,
                "volume_ratio": 2.5,
                "strength": "STRONG",
                "current_volume": 1000000,
                "avg_volume": 400000
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_volume_confirmation("BTCUSDT")

        assert result is not None
        assert result.name == "VOLUME_CONFIRMATION"
        assert result.signal == SignalAction.BUY
        assert result.metadata["confirmed"] is True
        assert result.metadata["role"] == "VALIDATOR"

    @pytest.mark.asyncio
    async def test_fetch_volume_confirmation_not_confirmed(self, signal_aggregator, mock_http_client):
        """Test fetching volume confirmation with unconfirmed signal"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "confirmed": False,
                "confidence": 0.45,
                "volume_ratio": 0.8,
                "strength": "WEAK",
                "current_volume": 300000,
                "avg_volume": 400000
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_volume_confirmation("BTCUSDT")

        assert result is not None
        assert result.signal == SignalAction.HOLD

    @pytest.mark.asyncio
    async def test_fetch_atr_success(self, signal_aggregator, mock_http_client):
        """Test fetching ATR successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "atr": 1250.0,
                "atr_pct": 2.5,
                "stop_loss_long": 48750.0,
                "stop_loss_short": 51250.0,
                "take_profit_long": 53750.0,
                "take_profit_short": 46250.0,
                "volatility": "MODERATE",
                "confidence": 0.95,
                "risk_reward_ratio": 2.0
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_atr("BTCUSDT")

        assert result is not None
        assert isinstance(result, dict)
        assert result["atr"] == 1250.0
        assert result["volatility"] == "MODERATE"
        assert result["risk_reward_ratio"] == 2.0

    @pytest.mark.asyncio
    async def test_fetch_stochastic_success(self, signal_aggregator, mock_http_client):
        """Test fetching stochastic successfully"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": {
                "signal": "BUY",
                "confidence": 0.80,
                "k": 25.0,
                "d": 20.0,
                "condition": "OVERSOLD",
                "crossover": True
            }
        }
        mock_response.raise_for_status = Mock()
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.fetch_stochastic("BTCUSDT")

        assert result is not None
        assert result.name == "STOCHASTIC"
        assert result.signal == SignalAction.BUY
        assert result.metadata["condition"] == "OVERSOLD"
        assert result.metadata["role"] == "MOMENTUM"

    def test_signal_to_score_buy(self, signal_aggregator):
        """Test converting BUY signal to score"""
        score = signal_aggregator.signal_to_score(SignalAction.BUY)
        assert score == 1.0

    def test_signal_to_score_sell(self, signal_aggregator):
        """Test converting SELL signal to score"""
        score = signal_aggregator.signal_to_score(SignalAction.SELL)
        assert score == -1.0

    def test_signal_to_score_hold(self, signal_aggregator):
        """Test converting HOLD signal to score"""
        score = signal_aggregator.signal_to_score(SignalAction.HOLD)
        assert score == 0.0

    def test_aggregate_signals_delegates_to_core(self, signal_aggregator, mock_core_aggregator):
        """Test that aggregate_signals delegates to CoreAggregator"""
        indicators = {
            "RSI": IndicatorSignal(
                name="RSI",
                signal=SignalAction.BUY,
                confidence=0.85,
                value=35.0
            ),
            "MACD": IndicatorSignal(
                name="MACD",
                signal=SignalAction.BUY,
                confidence=0.75,
                value=5.0
            )
        }

        timestamp = 1234567890
        atr_data = {"atr": 1250.0}

        result = signal_aggregator.aggregate_signals(indicators, timestamp, atr_data)

        # Verify CoreAggregator was called
        # symbol added 2026-08-23: the funnel filed every aggregation-stage
        # rejection under the literal "UNKNOWN" without it, killing per-symbol
        # attribution for 7 of the 22 stages.
        mock_core_aggregator.aggregate_signals.assert_called_once_with(
            indicators, timestamp, atr_data, symbol=None
        )

        # Verify result is a TradingSignal
        assert isinstance(result, TradingSignal)
        assert result.action == SignalAction.BUY

    @pytest.mark.asyncio
    async def test_get_trading_signal_integration(self, signal_aggregator, mock_http_client, mock_core_aggregator):
        """Test complete get_trading_signal flow"""
        # Mock all HTTP responses
        mock_response = Mock()
        mock_response.raise_for_status = Mock()

        # Create different responses for different indicators
        def mock_json_response():
            return {
                "signal": "BUY",
                "confidence": 0.80,
                "rsi": 35.0,
                "histogram": 5.0,
                "current_price": 50000.0,
                "upper_band": 52000.0,
                "middle_band": 50000.0,
                "lower_band": 48000.0,
                "value": 50100.0,
                "data": {
                    "signal": "BUY",
                    "confidence": 0.85,
                    "spread_pct": 5.0,
                    "trend": "UPTREND",
                    "fast_ema": 50500.0,
                    "slow_ema": 48000.0,
                    "confirmed": True,
                    "volume_ratio": 2.0,
                    "strength": "STRONG",
                    "current_volume": 1000000,
                    "avg_volume": 500000,
                    "k": 25.0,
                    "d": 20.0,
                    "condition": "OVERSOLD",
                    "crossover": True,
                    "atr": 1250.0,
                    "atr_pct": 2.5,
                    "stop_loss_long": 48750.0,
                    "stop_loss_short": 51250.0,
                    "take_profit_long": 53750.0,
                    "take_profit_short": 46250.0,
                    "volatility": "MODERATE",
                    "risk_reward_ratio": 2.0
                },
                "macd_line": 10.0,
                "signal_line": 5.0
            }

        mock_response.json = mock_json_response
        mock_http_client.get = AsyncMock(return_value=mock_response)

        result = await signal_aggregator.get_trading_signal("BTCUSDT", "60")

        # Verify result
        assert isinstance(result, TradingSignal)
        assert result.symbol == "BTCUSDT"
        assert result.action == SignalAction.BUY


class TestSignalAggregatorExceptionHandling:
    """Test exception handling in SignalAggregator"""

    @pytest.mark.asyncio
    async def test_fetch_rsi_exception(self):
        """Test RSI fetch with HTTP exception"""
        aggregator = SignalAggregator()

        # Mock HTTP client to raise exception
        with patch.object(aggregator.client, 'get', side_effect=Exception("Network error")):
            result = await aggregator.fetch_rsi("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_macd_exception(self):
        """Test MACD fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("API error")):
            result = await aggregator.fetch_macd("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_bollinger_bands_exception(self):
        """Test Bollinger Bands fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("Timeout")):
            result = await aggregator.fetch_bollinger_bands("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_sma_exception(self):
        """Test SMA fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("Connection refused")):
            result = await aggregator.fetch_sma("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_ema_exception(self):
        """Test EMA fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("HTTP 500")):
            result = await aggregator.fetch_ema("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_stochastic_exception(self):
        """Test Stochastic fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("Service unavailable")):
            result = await aggregator.fetch_stochastic("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_volume_confirmation_exception(self):
        """Test Volume confirmation fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("Network timeout")):
            result = await aggregator.fetch_volume_confirmation("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_trend_filter_exception(self):
        """Test Trend filter fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("DNS error")):
            result = await aggregator.fetch_trend_filter("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_fetch_atr_exception(self):
        """Test ATR fetch with HTTP exception"""
        aggregator = SignalAggregator()

        with patch.object(aggregator.client, 'get', side_effect=Exception("SSL error")):
            result = await aggregator.fetch_atr("BTCUSDT", "60")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_trading_signal_aggregator_exception(self):
        """Test get_trading_signal with aggregator exception"""
        aggregator = SignalAggregator()

        # Mock get_aggregator to raise exception
        with patch('app.signal_aggregator.get_aggregator', side_effect=Exception("Core aggregator error")):
            result = await aggregator.get_trading_signal("BTCUSDT", "60")

            # Should return a safe HOLD signal
            assert result is not None
            assert result.action == SignalAction.HOLD



# Test configuration
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
