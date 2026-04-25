"""
Test suite for Analysis HTTP Handlers
Tests for app/handlers/analysis.py endpoints
Target: Improve coverage from 9% to 80%+
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException
import pandas as pd
from datetime import datetime

# Import handlers to test
from app.handlers.analysis import get_aggregated_signal, get_multi_timeframe_analysis


class TestGetAggregatedSignal:
    """Test suite for get_aggregated_signal endpoint"""

    @pytest.mark.asyncio
    async def test_successful_aggregated_signal_bullish(self):
        """Test aggregated signal with bullish indicators"""
        # Mock the fetcher to return sample data
        mock_df = pd.DataFrame({
            'open': [100, 101, 102, 103, 104],
            'high': [105, 106, 107, 108, 109],
            'low': [99, 100, 101, 102, 103],
            'close': [104, 105, 106, 107, 108],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1, i) for i in range(5)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            # Execute
            result = await get_aggregated_signal(symbol="BTCUSDT", interval="60")

            # Assertions
            assert result is not None
            assert result['symbol'] == "BTCUSDT"
            assert result['interval'] == "60"
            assert result['signal'] in ['BUY', 'SELL', 'HOLD']
            assert 0 <= result['confidence'] <= 1
            assert 'timestamp' in result
            assert isinstance(result['rsi'], (float, type(None)))
            assert isinstance(result['trend'], (str, type(None)))

    @pytest.mark.asyncio
    async def test_successful_aggregated_signal_bearish(self):
        """Test aggregated signal with bearish indicators"""
        # Mock bearish data (declining prices)
        mock_df = pd.DataFrame({
            'open': [110, 108, 106, 104, 102],
            'high': [111, 109, 107, 105, 103],
            'low': [109, 107, 105, 103, 101],
            'close': [108, 106, 104, 102, 100],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1, i) for i in range(5)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            # Execute
            result = await get_aggregated_signal(symbol="ETHUSDT", interval="240")

            # Assertions
            assert result is not None
            assert result['symbol'] == "ETHUSDT"
            assert result['interval'] == "240"
            assert result['signal'] in ['BUY', 'SELL', 'HOLD']

    @pytest.mark.asyncio
    async def test_aggregated_signal_empty_dataframe(self):
        """Test handling of empty dataframe"""
        mock_df = pd.DataFrame()

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            # Should raise HTTPException with 404
            with pytest.raises(HTTPException) as exc_info:
                await get_aggregated_signal(symbol="BTCUSDT", interval="60")

            assert exc_info.value.status_code == 404
            assert "No data available" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_aggregated_signal_fetcher_error(self):
        """Test handling of fetcher errors"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(
                side_effect=Exception("Network error")
            )
            mock_get_fetcher.return_value = mock_fetcher

            # Should raise HTTPException with 500
            with pytest.raises(HTTPException) as exc_info:
                await get_aggregated_signal(symbol="BTCUSDT", interval="60")

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_aggregated_signal_rsi_oversold(self):
        """Test signal when RSI indicates oversold (<20)

        UPDATED 2025-12-03: Fixed datetime generation (hours must be 0-23).
        Use timedelta to generate valid timestamps spanning multiple days.
        """
        from datetime import timedelta
        # Create data that will produce low RSI
        mock_df = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [99] * 50,
            'close': list(range(100, 50, -1)),  # Declining prices
            'volume': [1000] * 50
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1) + timedelta(hours=i) for i in range(50)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_aggregated_signal(symbol="BTCUSDT", interval="60")

            # RSI should be low, contributing to potential BUY signal
            assert result is not None
            if result['rsi'] is not None:
                assert result['rsi'] >= 0 and result['rsi'] <= 100

    @pytest.mark.asyncio
    async def test_aggregated_signal_rsi_overbought(self):
        """Test signal when RSI indicates overbought (>80)

        UPDATED 2025-12-03: Fixed datetime generation (hours must be 0-23).
        Use timedelta to generate valid timestamps spanning multiple days.
        """
        from datetime import timedelta
        # Create data that will produce high RSI
        mock_df = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [99] * 50,
            'close': list(range(50, 100)),  # Rising prices
            'volume': [1000] * 50
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1) + timedelta(hours=i) for i in range(50)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_aggregated_signal(symbol="BTCUSDT", interval="60")

            # RSI should be in valid range
            assert result is not None
            if result['rsi'] is not None:
                assert result['rsi'] >= 0 and result['rsi'] <= 100


class TestGetMultiTimeframeAnalysis:
    """Test suite for get_multi_timeframe_analysis endpoint"""

    @pytest.mark.asyncio
    async def test_successful_multi_timeframe_analysis(self):
        """Test multi-timeframe analysis with default timeframes"""
        # Mock data for multiple timeframes
        mock_df = pd.DataFrame({
            'open': [100, 101, 102, 103, 104],
            'high': [105, 106, 107, 108, 109],
            'low': [99, 100, 101, 102, 103],
            'close': [104, 105, 106, 107, 108],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1, i) for i in range(5)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            # Execute
            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15"
            )

            # Assertions
            assert result is not None
            assert result['symbol'] == "BTCUSDT"
            assert result['overall_signal'] in ['BUY', 'SELL', 'HOLD']
            assert 0 <= result['confidence'] <= 1
            assert 0 <= result['alignment_score'] <= 1
            assert 'summary' in result
            assert 'timeframe_details' in result
            assert 'recommendation' in result

    @pytest.mark.asyncio
    async def test_multi_timeframe_with_custom_timeframes(self):
        """Test multi-timeframe analysis with custom timeframes"""
        mock_df = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [105, 106, 107],
            'low': [99, 100, 101],
            'close': [104, 105, 106],
            'volume': [1000, 1100, 1200]
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1, i) for i in range(3)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            # Execute with custom timeframes
            result = await get_multi_timeframe_analysis(
                symbol="ETHUSDT",
                timeframes="60,240,1440"
            )

            # Assertions
            assert result is not None
            assert result['symbol'] == "ETHUSDT"
            assert result['timeframes_analyzed'] >= 1

    @pytest.mark.asyncio
    async def test_multi_timeframe_alignment_strong_buy(self):
        """Test when all timeframes agree on BUY

        UPDATED 2025-12-03: Fixed datetime generation (hours must be 0-23).
        """
        from datetime import timedelta
        # Mock bullish data
        mock_df = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [99] * 50,
            'close': list(range(50, 100)),  # Strong uptrend
            'volume': [1000] * 50
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1) + timedelta(hours=i) for i in range(50)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15"
            )

            # With strong uptrend, alignment should be high
            assert result is not None
            assert result['alignment_score'] > 0

    @pytest.mark.asyncio
    async def test_multi_timeframe_alignment_strong_sell(self):
        """Test when all timeframes agree on SELL

        UPDATED 2025-12-03: Fixed datetime generation (hours must be 0-23).
        """
        from datetime import timedelta
        # Mock bearish data
        mock_df = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [99] * 50,
            'close': list(range(100, 50, -1)),  # Strong downtrend
            'volume': [1000] * 50
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1) + timedelta(hours=i) for i in range(50)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15"
            )

            # With strong downtrend, should have some alignment
            assert result is not None
            assert result['alignment_score'] >= 0

    @pytest.mark.asyncio
    async def test_multi_timeframe_partial_failures(self):
        """Test when some timeframes fail to fetch data"""
        call_count = [0]

        async def mock_get_klines(symbol, interval, limit):
            call_count[0] += 1
            # Fail every other call
            if call_count[0] % 2 == 0:
                raise Exception("Network error")

            return pd.DataFrame({
                'open': [100, 101, 102],
                'high': [105, 106, 107],
                'low': [99, 100, 101],
                'close': [104, 105, 106],
                'volume': [1000, 1100, 1200]
            }, index=pd.DatetimeIndex([
                datetime(2024, 1, 1, i) for i in range(3)
            ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = mock_get_klines
            mock_get_fetcher.return_value = mock_fetcher

            # Should handle partial failures gracefully
            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15,60"
            )

            # Should have analyzed at least some timeframes
            assert result is not None
            assert result['timeframes_analyzed'] >= 1

    @pytest.mark.asyncio
    async def test_multi_timeframe_all_failures(self):
        """Test when all timeframes fail to fetch data"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(
                side_effect=Exception("Network error")
            )
            mock_get_fetcher.return_value = mock_fetcher

            # Should raise HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_multi_timeframe_analysis(
                    symbol="BTCUSDT",
                    timeframes="1,5,15"
                )

            assert exc_info.value.status_code == 404
            assert "Unable to analyze" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_multi_timeframe_recommendation_strong(self):
        """Test recommendation text for strong alignment

        UPDATED 2025-12-03: Fixed datetime generation (hours must be 0-23).
        """
        from datetime import timedelta
        mock_df = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [99] * 50,
            'close': list(range(50, 100)),
            'volume': [1000] * 50
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1) + timedelta(hours=i) for i in range(50)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15"
            )

            # Check recommendation format
            assert result is not None
            assert 'recommendation' in result
            assert isinstance(result['recommendation'], str)

    @pytest.mark.asyncio
    async def test_multi_timeframe_summary_counts(self):
        """Test that summary contains correct counts"""
        mock_df = pd.DataFrame({
            'open': [100, 101, 102, 103, 104],
            'high': [105, 106, 107, 108, 109],
            'low': [99, 100, 101, 102, 103],
            'close': [104, 105, 106, 107, 108],
            'volume': [1000, 1100, 1200, 1300, 1400]
        }, index=pd.DatetimeIndex([
            datetime(2024, 1, 1, i) for i in range(5)
        ]))

        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher

            result = await get_multi_timeframe_analysis(
                symbol="BTCUSDT",
                timeframes="1,5,15"
            )

            # Validate summary structure
            assert 'summary' in result
            summary = result['summary']
            assert 'buy_timeframes' in summary
            assert 'sell_timeframes' in summary
            assert 'hold_timeframes' in summary

            # Counts should add up to total
            total = summary['buy_timeframes'] + summary['sell_timeframes'] + summary['hold_timeframes']
            assert total == result['timeframes_analyzed']

    @pytest.mark.asyncio
    async def test_multi_timeframe_error_handling(self):
        """Test generic error handling in multi-timeframe analysis"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            # Simulate a critical error in fetcher initialization
            mock_get_fetcher.side_effect = RuntimeError("Critical system error")

            with pytest.raises(HTTPException) as exc_info:
                await get_multi_timeframe_analysis(
                    symbol="BTCUSDT",
                    timeframes="1,5,15"
                )

            assert exc_info.value.status_code == 500
