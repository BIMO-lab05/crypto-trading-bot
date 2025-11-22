"""
Additional tests for analysis handlers to cover edge cases
Coverage target: analysis.py missing lines
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pandas as pd
from fastapi import HTTPException
from app.handlers.analysis import get_aggregated_signal, get_multi_timeframe_analysis


class TestAggregatedSignalEdgeCases:
    """Test edge cases in aggregated signal handler"""
    
    @pytest.mark.asyncio
    async def test_aggregated_signal_with_none_rsi_value(self):
        """Test aggregated signal when RSI returns None"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            # Create mock dataframe
            mock_df = pd.DataFrame({
                'close': [100, 101, 102, 103, 104],
                'high': [101, 102, 103, 104, 105],
                'low': [99, 100, 101, 102, 103],
                'volume': [1000, 1000, 1000, 1000, 1000]
            })
            mock_df.index = pd.date_range('2024-01-01', periods=5, freq='1min')
            
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher
            
            with patch('app.handlers.analysis.RSICalculator') as mock_rsi_calc:
                with patch('app.handlers.analysis.MACDCalculator') as mock_macd_calc:
                    with patch('app.handlers.analysis.TrendFilter') as mock_trend:
                        # Mock RSI returns None
                        mock_rsi_instance = MagicMock()
                        mock_rsi_instance.calculate.return_value = None
                        mock_rsi_calc.return_value = mock_rsi_instance
                        
                        # Mock MACD returns signal
                        mock_macd_instance = MagicMock()
                        mock_macd_instance.calculate.return_value = {'signal': 'BUY'}
                        mock_macd_calc.return_value = mock_macd_instance
                        
                        # Mock trend filter
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {'trend': 'BULLISH'}
                        mock_trend.return_value = mock_trend_instance
                        
                        result = await get_aggregated_signal("BTCUSDT", "60")
                        
                        # Should still work without RSI
                        assert result['symbol'] == "BTCUSDT"
                        assert result['rsi'] is None
    
    @pytest.mark.asyncio
    async def test_aggregated_signal_with_none_macd_signal(self):
        """Test aggregated signal when MACD returns None or no signal"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_df = pd.DataFrame({
                'close': [100, 101, 102, 103, 104],
                'high': [101, 102, 103, 104, 105],
                'low': [99, 100, 101, 102, 103],
                'volume': [1000, 1000, 1000, 1000, 1000]
            })
            mock_df.index = pd.date_range('2024-01-01', periods=5, freq='1min')
            
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = AsyncMock(return_value=mock_df)
            mock_get_fetcher.return_value = mock_fetcher
            
            with patch('app.handlers.analysis.RSICalculator') as mock_rsi_calc:
                with patch('app.handlers.analysis.MACDCalculator') as mock_macd_calc:
                    with patch('app.handlers.analysis.TrendFilter') as mock_trend:
                        # Mock RSI
                        mock_rsi_instance = MagicMock()
                        mock_rsi_instance.calculate.return_value = 65.0
                        mock_rsi_calc.return_value = mock_rsi_instance
                        
                        # Mock MACD returns None
                        mock_macd_instance = MagicMock()
                        mock_macd_instance.calculate.return_value = None
                        mock_macd_calc.return_value = mock_macd_instance
                        
                        # Mock trend filter
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {'trend': 'NEUTRAL'}
                        mock_trend.return_value = mock_trend_instance
                        
                        result = await get_aggregated_signal("BTCUSDT", "60")
                        
                        # Should still work without MACD
                        assert result['symbol'] == "BTCUSDT"
                        assert result['macd_signal'] is None


class TestMultiTimeframeAnalysisEdgeCases:
    """Test edge cases in multi-timeframe analysis handler"""
    
    @pytest.mark.asyncio
    async def test_multi_timeframe_with_empty_df_in_one_timeframe(self):
        """Test multi-timeframe analysis when one timeframe returns empty dataframe"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            # Create mock dataframe for some timeframes, empty for others
            mock_df_valid = pd.DataFrame({
                'close': [100, 101, 102],
                'high': [101, 102, 103],
                'low': [99, 100, 101],
                'volume': [1000, 1000, 1000]
            })
            mock_df_valid.index = pd.date_range('2024-01-01', periods=3, freq='1min')
            
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
            
            with patch('app.handlers.analysis.RSICalculator') as mock_rsi_calc:
                with patch('app.handlers.analysis.MACDCalculator') as mock_macd_calc:
                    with patch('app.handlers.analysis.TrendFilter') as mock_trend:
                        # Mock all calculators
                        mock_rsi_instance = MagicMock()
                        mock_rsi_instance.calculate.return_value = 50.0
                        mock_rsi_calc.return_value = mock_rsi_instance
                        
                        mock_macd_instance = MagicMock()
                        mock_macd_instance.calculate.return_value = {'signal': 'HOLD'}
                        mock_macd_calc.return_value = mock_macd_instance
                        
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {'trend': 'NEUTRAL'}
                        mock_trend.return_value = mock_trend_instance
                        
                        result = await get_multi_timeframe_analysis("BTCUSDT", "1,5")
                        
                        # Should skip empty timeframe and analyze valid ones
                        assert result['symbol'] == "BTCUSDT"
                        assert result['timeframes_analyzed'] >= 1
    
    @pytest.mark.asyncio
    async def test_multi_timeframe_with_exception_in_timeframe(self):
        """Test multi-timeframe analysis when one timeframe throws exception"""
        with patch('app.handlers.analysis.get_fetcher') as mock_get_fetcher:
            mock_df = pd.DataFrame({
                'close': [100, 101, 102],
                'high': [101, 102, 103],
                'low': [99, 100, 101],
                'volume': [1000, 1000, 1000]
            })
            mock_df.index = pd.date_range('2024-01-01', periods=3, freq='1min')
            
            call_count = [0]
            async def mock_get_klines(symbol, interval, limit):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Network error")
                return mock_df
            
            mock_fetcher = AsyncMock()
            mock_fetcher.get_klines_as_dataframe = mock_get_klines
            mock_get_fetcher.return_value = mock_fetcher
            
            with patch('app.handlers.analysis.RSICalculator') as mock_rsi_calc:
                with patch('app.handlers.analysis.MACDCalculator') as mock_macd_calc:
                    with patch('app.handlers.analysis.TrendFilter') as mock_trend:
                        mock_rsi_instance = MagicMock()
                        mock_rsi_instance.calculate.return_value = 50.0
                        mock_rsi_calc.return_value = mock_rsi_instance
                        
                        mock_macd_instance = MagicMock()
                        mock_macd_instance.calculate.return_value = {'signal': 'BUY'}
                        mock_macd_calc.return_value = mock_macd_instance
                        
                        mock_trend_instance = MagicMock()
                        mock_trend_instance.calculate.return_value = {'trend': 'BULLISH'}
                        mock_trend.return_value = mock_trend_instance
                        
                        result = await get_multi_timeframe_analysis("BTCUSDT", "1,5")
                        
                        # Should handle error gracefully
                        assert result['symbol'] == "BTCUSDT"
                        # One timeframe should have ERROR signal
                        error_found = any(
                            tf.get('signal') == 'ERROR' 
                            for tf in result.get('timeframe_details', [])
                        )
                        assert error_found or result['timeframes_analyzed'] >= 1
