"""
Test suite for Basic Indicator HTTP Handlers
Tests for app/handlers/indicators.py endpoints
Target: Improve coverage from 20% to 80%+
"""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

# Import handlers to test
from app.handlers.indicators import (
    get_rsi,
    get_macd,
    get_bollinger_bands,
    get_sma,
    get_ema
)


class TestGetRSI:
    """Test suite for get_rsi endpoint"""

    @pytest.mark.asyncio
    async def test_successful_rsi_default_params(self):
        """Test RSI calculation with default parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        Note: RSI period default changed from 14 to 9 (crypto-optimized).
        """
        mock_data = {
            "timestamp": 1234567890000,
            "rsi": 65.5,
            "signal": "HOLD",
            "confidence": 0.6
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(return_value=mock_data)

            # Execute with explicit parameters
            result = await get_rsi(symbol="BTCUSDT", interval="60", period=9, limit=200)

            # Assertions
            assert result.symbol == "BTCUSDT"
            assert result.interval == "60"
            assert result.rsi == 65.5
            assert result.signal == "HOLD"
            assert result.confidence == 0.6
            assert result.parameters["period"] == 9  # Changed from 14

    @pytest.mark.asyncio
    async def test_rsi_oversold_signal(self):
        """Test RSI with oversold signal

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "rsi": 25.0,
            "signal": "BUY",
            "confidence": 0.8
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(return_value=mock_data)

            result = await get_rsi(symbol="BTCUSDT", interval="60", period=14, limit=200)

            assert result.rsi == 25.0
            assert result.signal == "BUY"
            assert result.confidence == 0.8

    @pytest.mark.asyncio
    async def test_rsi_overbought_signal(self):
        """Test RSI with overbought signal

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "rsi": 78.5,
            "signal": "SELL",
            "confidence": 0.75
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(return_value=mock_data)

            result = await get_rsi(symbol="ETHUSDT", interval="60", period=14, limit=200)

            assert result.rsi == 78.5
            assert result.signal == "SELL"

    @pytest.mark.asyncio
    async def test_rsi_custom_params(self):
        """Test RSI with custom parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "rsi": 55.0,
            "signal": "HOLD",
            "confidence": 0.5
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(return_value=mock_data)

            result = await get_rsi(
                symbol="ETHUSDT",
                interval="240",
                period=21,
                limit=500
            )

            assert result.interval == "240"
            assert result.parameters["period"] == 21
            mock_service.calculate_rsi.assert_called_once_with(
                "ETHUSDT", "240", 21, 500
            )

    @pytest.mark.asyncio
    async def test_rsi_http_exception_passthrough(self):
        """Test that HTTPException is passed through"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(
                side_effect=HTTPException(status_code=404, detail="No data")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_rsi(symbol="INVALID")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_rsi_error_handling(self):
        """Test error handling for generic exceptions"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_rsi = AsyncMock(
                side_effect=Exception("Calculation error")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_rsi(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetMACD:
    """Test suite for get_macd endpoint"""

    @pytest.mark.asyncio
    async def test_successful_macd_default_params(self):
        """Test MACD calculation with default parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        MACD defaults changed from 12/26/9 to 5/35/5 (Kang 2021 study).
        """
        mock_data = {
            "timestamp": 1234567890000,
            "macd_line": 150.5,
            "signal_line": 145.2,
            "histogram": 5.3,
            "signal": "BUY",
            "confidence": 0.7
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_macd = AsyncMock(return_value=mock_data)

            # Execute with explicit parameters
            result = await get_macd(symbol="BTCUSDT", interval="60", fast=5, slow=35, signal=5, limit=200)

            # Assertions
            assert result.symbol == "BTCUSDT"
            assert result.macd_line == 150.5
            assert result.signal_line == 145.2
            assert result.histogram == 5.3
            assert result.signal == "BUY"
            assert result.parameters["fast"] == 5   # Changed from 12
            assert result.parameters["slow"] == 35  # Changed from 26
            assert result.parameters["signal"] == 5 # Changed from 9

    @pytest.mark.asyncio
    async def test_macd_bullish_crossover(self):
        """Test MACD with bullish crossover

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "macd_line": 100.0,
            "signal_line": 95.0,
            "histogram": 5.0,
            "signal": "BUY",
            "confidence": 0.85
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_macd = AsyncMock(return_value=mock_data)

            result = await get_macd(symbol="BTCUSDT", interval="60", fast=5, slow=35, signal=5, limit=200)

            assert result.histogram > 0
            assert result.signal == "BUY"

    @pytest.mark.asyncio
    async def test_macd_bearish_crossover(self):
        """Test MACD with bearish crossover

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "macd_line": 95.0,
            "signal_line": 100.0,
            "histogram": -5.0,
            "signal": "SELL",
            "confidence": 0.8
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_macd = AsyncMock(return_value=mock_data)

            result = await get_macd(symbol="ETHUSDT", interval="60", fast=5, slow=35, signal=5, limit=200)

            assert result.histogram < 0
            assert result.signal == "SELL"

    @pytest.mark.asyncio
    async def test_macd_custom_params(self):
        """Test MACD with custom parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "macd_line": 50.0,
            "signal_line": 48.0,
            "histogram": 2.0,
            "signal": "HOLD",
            "confidence": 0.5
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_macd = AsyncMock(return_value=mock_data)

            result = await get_macd(
                symbol="ETHUSDT",
                interval="15",
                fast=8,
                slow=21,
                signal=5,
                limit=300
            )

            assert result.parameters["fast"] == 8
            assert result.parameters["slow"] == 21
            assert result.parameters["signal"] == 5

    @pytest.mark.asyncio
    async def test_macd_error_handling(self):
        """Test error handling in MACD calculation"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_macd = AsyncMock(
                side_effect=ValueError("Invalid parameters")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_macd(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetBollingerBands:
    """Test suite for get_bollinger_bands endpoint"""

    @pytest.mark.asyncio
    async def test_successful_bollinger_bands_default(self):
        """Test Bollinger Bands with default parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        Std dev default changed from 2.0 to 2.5 for crypto volatility.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "upper_band": 52000.0,
            "middle_band": 50000.0,
            "lower_band": 48000.0,
            "current_price": 49500.0,
            "signal": "HOLD",
            "confidence": 0.6
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_bollinger_bands = AsyncMock(return_value=mock_data)

            # Execute with explicit parameters
            result = await get_bollinger_bands(symbol="BTCUSDT", interval="60", period=20, std_dev=2.5, limit=200)

            # Assertions
            assert result.symbol == "BTCUSDT"
            assert result.upper_band == 52000.0
            assert result.middle_band == 50000.0
            assert result.lower_band == 48000.0
            assert result.current_price == 49500.0
            assert result.parameters["period"] == 20
            assert result.parameters["std_dev"] == 2.5  # Changed from 2.0 for crypto

    @pytest.mark.asyncio
    async def test_bollinger_bands_oversold(self):
        """Test Bollinger Bands when price is near lower band

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "upper_band": 52000.0,
            "middle_band": 50000.0,
            "lower_band": 48000.0,
            "current_price": 48100.0,
            "signal": "BUY",
            "confidence": 0.75
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_bollinger_bands = AsyncMock(return_value=mock_data)

            result = await get_bollinger_bands(symbol="BTCUSDT", interval="60", period=20, std_dev=2.5, limit=200)

            assert result.current_price < result.middle_band
            assert result.signal == "BUY"

    @pytest.mark.asyncio
    async def test_bollinger_bands_overbought(self):
        """Test Bollinger Bands when price is near upper band

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "upper_band": 52000.0,
            "middle_band": 50000.0,
            "lower_band": 48000.0,
            "current_price": 51900.0,
            "signal": "SELL",
            "confidence": 0.8
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_bollinger_bands = AsyncMock(return_value=mock_data)

            result = await get_bollinger_bands(symbol="ETHUSDT", interval="60", period=20, std_dev=2.5, limit=200)

            assert result.current_price > result.middle_band
            assert result.signal == "SELL"

    @pytest.mark.asyncio
    async def test_bollinger_bands_custom_params(self):
        """Test Bollinger Bands with custom parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "upper_band": 3200.0,
            "middle_band": 3000.0,
            "lower_band": 2800.0,
            "current_price": 3050.0,
            "signal": "HOLD",
            "confidence": 0.5
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_bollinger_bands = AsyncMock(return_value=mock_data)

            result = await get_bollinger_bands(
                symbol="ETHUSDT",
                interval="60",
                period=50,
                std_dev=2.5,
                limit=200
            )

            assert result.parameters["period"] == 50
            assert result.parameters["std_dev"] == 2.5

    @pytest.mark.asyncio
    async def test_bollinger_bands_error_handling(self):
        """Test error handling in Bollinger Bands calculation"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_bollinger_bands = AsyncMock(
                side_effect=Exception("Insufficient data")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_bollinger_bands(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetSMA:
    """Test suite for get_sma endpoint"""

    @pytest.mark.asyncio
    async def test_successful_sma_default(self):
        """Test SMA calculation with default parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 50000.0,
            "current_price": 50500.0,
            "signal": "BUY",
            "confidence": 0.6
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_sma = AsyncMock(return_value=mock_data)

            # Execute with explicit parameters
            result = await get_sma(symbol="BTCUSDT", interval="60", period=20, limit=200)

            # Assertions
            assert result.symbol == "BTCUSDT"
            assert result.ma_type == "SMA"
            assert result.value == 50000.0
            assert result.current_price == 50500.0
            assert result.signal == "BUY"
            assert result.parameters["period"] == 20

    @pytest.mark.asyncio
    async def test_sma_bullish_signal(self):
        """Test SMA with bullish signal (price > SMA)

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 49000.0,
            "current_price": 50000.0,
            "signal": "BUY",
            "confidence": 0.7
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_sma = AsyncMock(return_value=mock_data)

            result = await get_sma(symbol="BTCUSDT", interval="60", period=20, limit=200)

            assert result.current_price > result.value
            assert result.signal == "BUY"

    @pytest.mark.asyncio
    async def test_sma_bearish_signal(self):
        """Test SMA with bearish signal (price < SMA)

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 51000.0,
            "current_price": 50000.0,
            "signal": "SELL",
            "confidence": 0.65
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_sma = AsyncMock(return_value=mock_data)

            result = await get_sma(symbol="ETHUSDT", interval="60", period=20, limit=200)

            assert result.current_price < result.value
            assert result.signal == "SELL"

    @pytest.mark.asyncio
    async def test_sma_custom_period(self):
        """Test SMA with custom period

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 3000.0,
            "current_price": 3020.0,
            "signal": "HOLD",
            "confidence": 0.5
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_sma = AsyncMock(return_value=mock_data)

            result = await get_sma(
                symbol="ETHUSDT",
                interval="60",
                period=50,
                limit=300
            )

            assert result.parameters["period"] == 50
            mock_service.calculate_sma.assert_called_once_with(
                "ETHUSDT", "60", 50, 300
            )

    @pytest.mark.asyncio
    async def test_sma_error_handling(self):
        """Test error handling in SMA calculation"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_sma = AsyncMock(
                side_effect=Exception("Network error")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_sma(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500


class TestGetEMA:
    """Test suite for get_ema endpoint"""

    @pytest.mark.asyncio
    async def test_successful_ema_default(self):
        """Test EMA calculation with default parameters

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 50200.0,
            "current_price": 50500.0,
            "signal": "BUY",
            "confidence": 0.65
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(return_value=mock_data)

            # Execute with explicit parameters
            result = await get_ema(symbol="BTCUSDT", interval="60", period=20, limit=200)

            # Assertions
            assert result.symbol == "BTCUSDT"
            assert result.ma_type == "EMA"
            assert result.value == 50200.0
            assert result.current_price == 50500.0
            assert result.signal == "BUY"
            assert result.parameters["period"] == 20

    @pytest.mark.asyncio
    async def test_ema_bullish_signal(self):
        """Test EMA with bullish signal

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 49500.0,
            "current_price": 50000.0,
            "signal": "BUY",
            "confidence": 0.7
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(return_value=mock_data)

            result = await get_ema(symbol="BTCUSDT", interval="60", period=20, limit=200)

            assert result.current_price > result.value

    @pytest.mark.asyncio
    async def test_ema_bearish_signal(self):
        """Test EMA with bearish signal

        UPDATED 2025-12-03: Pass explicit params to avoid FastAPI Query object issues.
        """
        mock_data = {
            "timestamp": 1234567890000,
            "value": 50500.0,
            "current_price": 50000.0,
            "signal": "SELL",
            "confidence": 0.7
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(return_value=mock_data)

            result = await get_ema(symbol="ETHUSDT", interval="60", period=20, limit=200)

            assert result.current_price < result.value

    @pytest.mark.asyncio
    async def test_ema_custom_params(self):
        """Test EMA with custom parameters"""
        mock_data = {
            "timestamp": 1234567890000,
            "value": 3000.0,
            "current_price": 3050.0,
            "signal": "HOLD",
            "confidence": 0.5
        }

        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(return_value=mock_data)

            result = await get_ema(
                symbol="ETHUSDT",
                interval="15",
                period=12,
                limit=500
            )

            assert result.interval == "15"
            assert result.parameters["period"] == 12
            mock_service.calculate_ema.assert_called_once_with(
                "ETHUSDT", "15", 12, 500
            )

    @pytest.mark.asyncio
    async def test_ema_http_exception_passthrough(self):
        """Test that HTTPException is passed through"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(
                side_effect=HTTPException(status_code=404, detail="Not found")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_ema(symbol="INVALID")

            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_ema_error_handling(self):
        """Test error handling for generic exceptions"""
        with patch('app.handlers.indicators.IndicatorService') as mock_service:
            mock_service.calculate_ema = AsyncMock(
                side_effect=Exception("Calculation failed")
            )

            with pytest.raises(HTTPException) as exc_info:
                await get_ema(symbol="BTCUSDT")

            assert exc_info.value.status_code == 500
