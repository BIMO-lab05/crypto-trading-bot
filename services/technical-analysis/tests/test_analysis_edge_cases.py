"""
Additional tests for analysis handlers to cover edge cases
Coverage target: analysis.py missing lines

UPDATED 2026-05-05: Tests now mock generate_signal() on RSI/MACD calculators.
Previous test bodies relied on a bug where the handler read `macd.get('signal')`
from the raw calculate() output (which never had a `signal` key). That bug
silently dropped MACD votes from per-timeframe analysis. After the audit fix,
the handler uses *_calc.generate_signal(...), so the mocks must supply that
return value.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from app.handlers.analysis import get_aggregated_signal, get_multi_timeframe_analysis
from app.models import SignalType


def _make_rsi_mock(rsi_value, signal=SignalType.HOLD, confidence=0.5):
    """Build a MagicMock RSICalculator returning given values."""
    inst = MagicMock()
    inst.calculate.return_value = rsi_value
    inst.generate_signal.return_value = (signal, confidence)
    return inst


def _make_macd_mock(macd_dict, signal=SignalType.HOLD, confidence=0.5):
    """Build a MagicMock MACDCalculator returning given values."""
    inst = MagicMock()
    inst.calculate.return_value = macd_dict
    inst.generate_signal.return_value = (signal, confidence)
    return inst


class TestAggregatedSignalEdgeCases:
    """Test edge cases in aggregated signal handler"""

    @pytest.mark.asyncio
    async def test_aggregated_signal_with_none_rsi_value(self):
        """Test aggregated signal when RSI returns None"""
        with patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher:
            # Create mock dataframe
            mock_df = pd.DataFrame(
                {
                    "close": [100, 101, 102, 103, 104],
                    "high": [101, 102, 103, 104, 105],
                    "low": [99, 100, 101, 102, 103],
                    "volume": [1000, 1000, 1000, 1000, 1000],
                }
            )
            mock_df.index = pd.date_range("2024-01-01", periods=5, freq="1min")

            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            with patch("app.handlers.analysis.RSICalculator") as mock_rsi_calc:
                with patch("app.handlers.analysis.MACDCalculator") as mock_macd_calc:
                    with patch("app.handlers.analysis.TrendFilter") as mock_trend:
                        # RSI calculate -> None (insufficient data path)
                        mock_rsi_calc.return_value = _make_rsi_mock(None)

                        # MACD returns a real-shaped dict + BUY/0.6 signal
                        mock_macd_calc.return_value = _make_macd_mock(
                            {"macd_line": 1.0, "signal_line": 0.5, "histogram": 0.5},
                            signal=SignalType.BUY,
                            confidence=0.6,
                        )

                        # Trend filter returns a real-shaped result
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {
                            "trend": "BULLISH",
                            "signal": "BUY",
                            "confidence": 0.7,
                        }
                        mock_trend.return_value = mock_trend_instance

                        result = await get_aggregated_signal("BTCUSDT", "60")

                        # Should still work without RSI
                        assert result["symbol"] == "BTCUSDT"
                        assert result["rsi"] is None
                        # MACD label is now derived from generate_signal()
                        assert result["macd_signal"] == "BUY"

    @pytest.mark.asyncio
    async def test_aggregated_signal_with_none_macd_signal(self):
        """Test aggregated signal when MACD returns None or no signal"""
        with patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher:
            mock_df = pd.DataFrame(
                {
                    "close": [100, 101, 102, 103, 104],
                    "high": [101, 102, 103, 104, 105],
                    "low": [99, 100, 101, 102, 103],
                    "volume": [1000, 1000, 1000, 1000, 1000],
                }
            )
            mock_df.index = pd.date_range("2024-01-01", periods=5, freq="1min")

            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            with patch("app.handlers.analysis.RSICalculator") as mock_rsi_calc:
                with patch("app.handlers.analysis.MACDCalculator") as mock_macd_calc:
                    with patch("app.handlers.analysis.TrendFilter") as mock_trend:
                        # RSI returns valid value
                        mock_rsi_calc.return_value = _make_rsi_mock(
                            65.0, signal=SignalType.SELL, confidence=0.5
                        )

                        # MACD calculate -> None (insufficient data path)
                        mock_macd_calc.return_value = _make_macd_mock(None)

                        # Trend filter neutral
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {
                            "trend": "NEUTRAL",
                            "signal": "HOLD",
                            "confidence": 0.3,
                        }
                        mock_trend.return_value = mock_trend_instance

                        result = await get_aggregated_signal("BTCUSDT", "60")

                        # Should still work without MACD
                        assert result["symbol"] == "BTCUSDT"
                        assert result["macd_signal"] is None


class TestMultiTimeframeAnalysisEdgeCases:
    """Test edge cases in multi-timeframe analysis handler"""

    @pytest.mark.asyncio
    async def test_multi_timeframe_with_empty_df_in_one_timeframe(self):
        """Test multi-timeframe analysis when one timeframe returns empty dataframe"""
        with patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher:
            # Create mock dataframe for some timeframes, empty for others
            mock_df_valid = pd.DataFrame(
                {
                    "close": [100, 101, 102],
                    "high": [101, 102, 103],
                    "low": [99, 100, 101],
                    "volume": [1000, 1000, 1000],
                }
            )
            mock_df_valid.index = pd.date_range("2024-01-01", periods=3, freq="1min")

            mock_df_empty = pd.DataFrame()

            call_count = [0]

            async def mock_get_klines(symbol, interval, limit):
                call_count[0] += 1
                # Return empty for first call, valid for rest
                if call_count[0] == 1:
                    return mock_df_empty
                return mock_df_valid

            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = mock_get_klines
            mock_get_fetcher.return_value = mock_fetcher

            with patch("app.handlers.analysis.RSICalculator") as mock_rsi_calc:
                with patch("app.handlers.analysis.MACDCalculator") as mock_macd_calc:
                    with patch("app.handlers.analysis.TrendFilter") as mock_trend:
                        mock_rsi_calc.return_value = _make_rsi_mock(
                            50.0, signal=SignalType.HOLD, confidence=0.3
                        )
                        mock_macd_calc.return_value = _make_macd_mock(
                            {"macd_line": 0.0, "signal_line": 0.0, "histogram": 0.0},
                            signal=SignalType.HOLD,
                            confidence=0.1,
                        )

                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {
                            "trend": "NEUTRAL",
                            "signal": "HOLD",
                            "confidence": 0.3,
                        }
                        mock_trend.return_value = mock_trend_instance

                        result = await get_multi_timeframe_analysis("BTCUSDT", "1,5")

                        # Should skip empty timeframe and analyze valid ones
                        assert result["symbol"] == "BTCUSDT"
                        assert result["timeframes_analyzed"] >= 1

    @pytest.mark.asyncio
    async def test_multi_timeframe_with_exception_in_timeframe(self):
        """Test multi-timeframe analysis when one timeframe throws exception"""
        with patch("app.handlers.analysis.get_fetcher") as mock_get_fetcher:
            mock_df = pd.DataFrame(
                {
                    "close": [100, 101, 102],
                    "high": [101, 102, 103],
                    "low": [99, 100, 101],
                    "volume": [1000, 1000, 1000],
                }
            )
            mock_df.index = pd.date_range("2024-01-01", periods=3, freq="1min")

            call_count = [0]

            async def mock_get_klines(symbol, interval, limit):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Network error")
                return mock_df

            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = mock_get_klines
            mock_get_fetcher.return_value = mock_fetcher

            with patch("app.handlers.analysis.RSICalculator") as mock_rsi_calc:
                with patch("app.handlers.analysis.MACDCalculator") as mock_macd_calc:
                    with patch("app.handlers.analysis.TrendFilter") as mock_trend:
                        mock_rsi_calc.return_value = _make_rsi_mock(
                            50.0, signal=SignalType.HOLD, confidence=0.3
                        )
                        mock_macd_calc.return_value = _make_macd_mock(
                            {"macd_line": 1.0, "signal_line": 0.5, "histogram": 0.5},
                            signal=SignalType.BUY,
                            confidence=0.6,
                        )

                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {
                            "trend": "BULLISH",
                            "signal": "BUY",
                            "confidence": 0.7,
                        }
                        mock_trend.return_value = mock_trend_instance

                        result = await get_multi_timeframe_analysis("BTCUSDT", "1,5")

                        # Should handle error gracefully
                        assert result["symbol"] == "BTCUSDT"
                        # One timeframe should have ERROR signal
                        error_found = any(
                            tf.get("signal") == "ERROR"
                            for tf in result.get("timeframe_details", [])
                        )
                        assert error_found or result["timeframes_analyzed"] >= 1
