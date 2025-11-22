"""
Test suite for Advanced Indicator HTTP Handlers
Tests for app/handlers/advanced.py endpoints
Target: Improve coverage from 22% to 80%+
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException

# Import handlers to test
from app.handlers.advanced import (
    get_trend_filter,
    get_volume_confirmation,
    get_atr,
    get_stochastic
)


class TestGetTrendFilter:
    """Test suite for get_trend_filter endpoint"""

    @pytest.mark.asyncio
    async def test_successful_trend_filter_default_params(self):
        """Test trend filter with default parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "trend": "BULLISH",
                "fast_ema": 50000.0,
                "slow_ema": 48000.0,
                "spread_percent": 4.17
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_trend_filter = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_trend_filter(symbol="BTCUSDT")

            # Assertions
            assert result is not None
            assert result['success'] is True
            assert result['symbol'] == "BTCUSDT"
            assert result['interval'] == "60"
            assert result['timestamp'] == mock_data['timestamp']
            assert result['data'] == mock_data['data']
            assert 'parameters' in result
            assert result['parameters']['fast_period'] == 50
            assert result['parameters']['slow_period'] == 200

    @pytest.mark.asyncio
    async def test_successful_trend_filter_custom_params(self):
        """Test trend filter with custom parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "trend": "BEARISH",
                "fast_ema": 48000.0,
                "slow_ema": 50000.0,
                "spread_percent": -4.17
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_trend_filter = AsyncMock(return_value=mock_data)

            # Execute with custom parameters
            result = await get_trend_filter(
                symbol="ETHUSDT",
                interval="240",
                fast_period=20,
                slow_period=100,
                limit=500
            )

            # Assertions
            assert result is not None
            assert result['success'] is True
            assert result['symbol'] == "ETHUSDT"
            assert result['interval'] == "240"
            assert result['parameters']['fast_period'] == 20
            assert result['parameters']['slow_period'] == 100

            # Verify service was called with correct params
            mock_service.calculate_trend_filter.assert_called_once_with(
                "ETHUSDT", "240", 20, 100, 500
            )

    @pytest.mark.asyncio
    async def test_trend_filter_http_exception_passthrough(self):
        """Test that HTTPException is passed through"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_trend_filter = AsyncMock(
                side_effect=HTTPException(status_code=404, detail="Symbol not found")
            )

            # Should re-raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_trend_filter(symbol="INVALID")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_trend_filter_generic_error_handling(self):
        """Test error handling for non-HTTP exceptions"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_trend_filter = AsyncMock(
                side_effect=Exception("Database connection failed")
            )

            # Should convert to HTTPException 500
            with pytest.raises(HTTPException) as exc_info:
                await get_trend_filter(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500
            assert "Database connection failed" in str(exc_info.value.detail)


class TestGetVolumeConfirmation:
    """Test suite for get_volume_confirmation endpoint"""

    @pytest.mark.asyncio
    async def test_successful_volume_confirmation_default(self):
        """Test volume confirmation with default parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "current_volume": 15000.0,
                "average_volume": 10000.0,
                "volume_ratio": 1.5,
                "confirmation": "STRONG"
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_volume_confirmation = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_volume_confirmation(symbol="BTCUSDT")

            # Assertions
            assert result is not None
            assert result['success'] is True
            assert result['symbol'] == "BTCUSDT"
            assert result['signal_type'] == "breakout"
            assert result['data'] == mock_data['data']

    @pytest.mark.asyncio
    async def test_volume_confirmation_custom_params(self):
        """Test volume confirmation with custom parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "current_volume": 12000.0,
                "average_volume": 10000.0,
                "volume_ratio": 1.2,
                "confirmation": "MODERATE"
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_volume_confirmation = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_volume_confirmation(
                symbol="ETHUSDT",
                interval="15",
                period=30,
                signal_type="continuation",
                limit=100
            )

            # Assertions
            assert result['signal_type'] == "continuation"
            assert result['parameters']['period'] == 30

            # Verify service was called correctly
            mock_service.calculate_volume_confirmation.assert_called_once_with(
                "ETHUSDT", "15", 30, "continuation", 100
            )

    @pytest.mark.asyncio
    async def test_volume_confirmation_error_handling(self):
        """Test error handling in volume confirmation"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_volume_confirmation = AsyncMock(
                side_effect=ValueError("Invalid period")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_volume_confirmation(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetATR:
    """Test suite for get_atr endpoint"""

    @pytest.mark.asyncio
    async def test_successful_atr_without_entry_price(self):
        """Test ATR calculation without entry price"""
        mock_data = {
            "timestamp": 1234567890000,
            "current_price": 50000.0,
            "data": {
                "atr": 1500.0,
                "atr_percent": 3.0,
                "volatility": "MODERATE",
                "stop_loss_long": None,
                "stop_loss_short": None,
                "take_profit_long": None,
                "take_profit_short": None
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_atr = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_atr(symbol="BTCUSDT")

            # Assertions
            assert result is not None
            assert result['success'] is True
            assert result['symbol'] == "BTCUSDT"
            assert result['current_price'] == 50000.0
            assert result['data']['atr'] == 1500.0

    @pytest.mark.asyncio
    async def test_successful_atr_with_entry_price(self):
        """Test ATR calculation with entry price for position sizing"""
        mock_data = {
            "timestamp": 1234567890000,
            "current_price": 50000.0,
            "data": {
                "atr": 1500.0,
                "atr_percent": 3.0,
                "volatility": "MODERATE",
                "stop_loss_long": 47000.0,
                "stop_loss_short": 53000.0,
                "take_profit_long": 56000.0,
                "take_profit_short": 44000.0
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_atr = AsyncMock(return_value=mock_data)

            # Execute with entry price
            result = await get_atr(
                symbol="BTCUSDT",
                current_price=50000.0
            )

            # Assertions
            assert result['data']['stop_loss_long'] is not None
            assert result['data']['take_profit_long'] is not None

            # Verify service was called with entry price
            mock_service.calculate_atr.assert_called_once()
            call_args = mock_service.calculate_atr.call_args
            assert call_args[0][3] == 50000.0  # current_price argument

    @pytest.mark.asyncio
    async def test_atr_custom_period(self):
        """Test ATR with custom period"""
        mock_data = {
            "timestamp": 1234567890000,
            "current_price": 3000.0,
            "data": {
                "atr": 100.0,
                "atr_percent": 3.33,
                "volatility": "HIGH"
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_atr = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_atr(
                symbol="ETHUSDT",
                period=7,
                limit=100
            )

            # Assertions
            assert result['parameters']['period'] == 7

    @pytest.mark.asyncio
    async def test_atr_error_handling(self):
        """Test error handling in ATR calculation"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_atr = AsyncMock(
                side_effect=Exception("Insufficient data")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_atr(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetStochastic:
    """Test suite for get_stochastic endpoint"""

    @pytest.mark.asyncio
    async def test_successful_stochastic_default_params(self):
        """Test stochastic oscillator with default parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "k": 75.5,
                "d": 72.3,
                "condition": "OVERBOUGHT",
                "crossover": "BULLISH"
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(return_value=mock_data)

            # Execute
            result = await get_stochastic(symbol="BTCUSDT")

            # Assertions
            assert result is not None
            assert result['success'] is True
            assert result['symbol'] == "BTCUSDT"
            assert result['data']['k'] == 75.5
            assert result['data']['d'] == 72.3
            assert result['data']['condition'] == "OVERBOUGHT"
            assert result['parameters']['period'] == 14
            assert result['parameters']['smooth_k'] == 3
            assert result['parameters']['smooth_d'] == 3

    @pytest.mark.asyncio
    async def test_stochastic_custom_smoothing(self):
        """Test stochastic with custom smoothing parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "k": 25.5,
                "d": 28.3,
                "condition": "OVERSOLD",
                "crossover": "BEARISH"
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(return_value=mock_data)

            # Execute with custom smoothing
            result = await get_stochastic(
                symbol="ETHUSDT",
                interval="240",
                period=21,
                smooth_k=5,
                smooth_d=5,
                limit=100
            )

            # Assertions
            assert result['parameters']['period'] == 21
            assert result['parameters']['smooth_k'] == 5
            assert result['parameters']['smooth_d'] == 5

            # Verify service call
            mock_service.calculate_stochastic.assert_called_once_with(
                "ETHUSDT", "240", 21, 5, 5, 100
            )

    @pytest.mark.asyncio
    async def test_stochastic_oversold_condition(self):
        """Test stochastic in oversold condition"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "k": 15.0,
                "d": 18.0,
                "condition": "OVERSOLD",
                "crossover": None
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(return_value=mock_data)

            result = await get_stochastic(symbol="BTCUSDT")

            assert result['data']['condition'] == "OVERSOLD"
            assert result['data']['k'] < 20

    @pytest.mark.asyncio
    async def test_stochastic_neutral_condition(self):
        """Test stochastic in neutral condition"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "k": 50.0,
                "d": 52.0,
                "condition": "NEUTRAL",
                "crossover": None
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(return_value=mock_data)

            result = await get_stochastic(symbol="BTCUSDT")

            assert result['data']['condition'] == "NEUTRAL"
            assert 20 < result['data']['k'] < 80

    @pytest.mark.asyncio
    async def test_stochastic_http_exception_passthrough(self):
        """Test that HTTPException is passed through"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(
                side_effect=HTTPException(status_code=400, detail="Invalid parameters")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_stochastic(symbol="BTCUSDT")

            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_stochastic_error_handling(self):
        """Test error handling for generic exceptions"""
        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(
                side_effect=ValueError("Period must be positive")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_stochastic(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500
            assert "Period must be positive" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_stochastic_crossover_signals(self):
        """Test stochastic with crossover signals"""
        mock_data = {
            "timestamp": 1234567890000,
            "data": {
                "k": 65.0,
                "d": 60.0,
                "condition": "NEUTRAL",
                "crossover": "BULLISH",
                "k_crossed_above_d": True
            }
        }

        with patch('app.handlers.advanced.IndicatorService') as mock_service:
            mock_service.calculate_stochastic = AsyncMock(return_value=mock_data)

            result = await get_stochastic(symbol="BTCUSDT")

            assert result['data']['crossover'] == "BULLISH"
