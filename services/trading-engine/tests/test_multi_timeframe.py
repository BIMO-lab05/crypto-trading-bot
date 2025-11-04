"""
Tests for Multi-Timeframe Analysis Module
Purpose: Test timeframe alignment analysis and trend confirmation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.multi_timeframe import (
    MultiTimeframeAnalyzer,
    TrendDirection,
    get_multi_timeframe_analyzer,
    close_multi_timeframe_analyzer
)


@pytest.fixture
def analyzer():
    """Create multi-timeframe analyzer"""
    return MultiTimeframeAnalyzer(ta_service_url="http://localhost:8004")


@pytest.fixture
def mock_httpx_response():
    """Mock httpx response"""
    def create_response(trend="BULLISH", strength=70):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "trend": trend,
            "strength": strength,
            "indicators": {
                "RSI": {"value": 55, "signal": "NEUTRAL"},
                "MACD": {"value": 0.5, "signal": "BUY"}
            }
        }
        return response
    return create_response


class TestTrendDirection:
    """Test TrendDirection enum"""

    def test_trend_direction_values(self):
        """Test all trend direction values"""
        assert TrendDirection.STRONG_BULLISH == "STRONG_BULLISH"
        assert TrendDirection.BULLISH == "BULLISH"
        assert TrendDirection.NEUTRAL == "NEUTRAL"
        assert TrendDirection.BEARISH == "BEARISH"
        assert TrendDirection.STRONG_BEARISH == "STRONG_BEARISH"


class TestMultiTimeframeAnalyzerInitialization:
    """Test analyzer initialization"""

    def test_initialization_default_url(self):
        """Test initialization with default TA service URL"""
        analyzer = MultiTimeframeAnalyzer()
        assert analyzer.ta_service_url == "http://localhost:8004"
        assert analyzer.client is not None

    def test_initialization_custom_url(self):
        """Test initialization with custom TA service URL"""
        custom_url = "http://custom-ta-service:9000"
        analyzer = MultiTimeframeAnalyzer(ta_service_url=custom_url)
        assert analyzer.ta_service_url == custom_url

    def test_timeframes_configured(self):
        """Test that all timeframes are configured"""
        assert "1m" in MultiTimeframeAnalyzer.TIMEFRAMES
        assert "5m" in MultiTimeframeAnalyzer.TIMEFRAMES
        assert "15m" in MultiTimeframeAnalyzer.TIMEFRAMES
        assert "60m" in MultiTimeframeAnalyzer.TIMEFRAMES
        assert "4h" in MultiTimeframeAnalyzer.TIMEFRAMES
        assert "1d" in MultiTimeframeAnalyzer.TIMEFRAMES

    def test_timeframe_weights_configured(self):
        """Test that timeframe weights are configured"""
        weights = MultiTimeframeAnalyzer.TIMEFRAME_WEIGHTS
        assert weights["1m"] < weights["5m"]
        assert weights["5m"] < weights["15m"]
        assert weights["15m"] < weights["60m"]
        assert weights["60m"] < weights["4h"]
        assert weights["4h"] < weights["1d"]


class TestClientLifecycle:
    """Test HTTP client lifecycle"""

    @pytest.mark.asyncio
    async def test_close_client(self, analyzer):
        """Test closing HTTP client"""
        await analyzer.close()
        # Should not raise exception


class TestTimeframeAlignment:
    """Test timeframe alignment analysis"""

    @pytest.mark.asyncio
    async def test_get_timeframe_alignment_all_bullish(self, analyzer, mock_httpx_response):
        """Test alignment when all timeframes are bullish"""
        # Mock all timeframe responses as bullish
        async def mock_get(*args, **kwargs):
            return mock_httpx_response(trend="BULLISH", strength=80)

        with patch.object(analyzer.client, 'get', side_effect=mock_get):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            assert "alignment_score" in result
            assert "trend_direction" in result
            assert "confidence" in result
            assert "timeframes" in result
            assert result["alignment_score"] > 70  # High alignment
            assert result["trend_direction"] in ["BULLISH", "STRONG_BULLISH"]

    @pytest.mark.asyncio
    async def test_get_timeframe_alignment_all_bearish(self, analyzer, mock_httpx_response):
        """Test alignment when all timeframes are bearish"""
        async def mock_get(*args, **kwargs):
            return mock_httpx_response(trend="BEARISH", strength=75)

        with patch.object(analyzer.client, 'get', side_effect=mock_get):
            result = await analyzer.get_timeframe_alignment("ETHUSDT")

            assert result["trend_direction"] in ["BEARISH", "STRONG_BEARISH"]
            assert result["alignment_score"] > 70

    @pytest.mark.asyncio
    async def test_get_timeframe_alignment_mixed_signals(self, analyzer):
        """Test alignment with mixed signals across timeframes"""
        # Return different trends for different timeframes
        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"trend": "BULLISH", "strength": 60}
            else:
                response = MagicMock()
                response.status_code = 200
                response.json.return_value = {"trend": "BEARISH", "strength": 60}
            return response

        with patch.object(analyzer.client, 'get', side_effect=mock_get):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            # Mixed signals should result in lower alignment score
            assert result["alignment_score"] < 50
            assert result["trend_direction"] in ["NEUTRAL", "BULLISH", "BEARISH"]

    @pytest.mark.asyncio
    async def test_get_timeframe_alignment_error_handling(self, analyzer):
        """Test alignment with API errors"""
        async def mock_get_error(*args, **kwargs):
            raise httpx.RequestError("Connection failed", request=None)

        with patch.object(analyzer.client, 'get', side_effect=mock_get_error):
            # Should handle errors gracefully
            with pytest.raises(Exception):
                await analyzer.get_timeframe_alignment("BTCUSDT")

    @pytest.mark.asyncio
    async def test_get_timeframe_alignment_timeout(self, analyzer):
        """Test alignment with timeout"""
        async def mock_get_timeout(*args, **kwargs):
            raise httpx.TimeoutException("Request timeout", request=None)

        with patch.object(analyzer.client, 'get', side_effect=mock_get_timeout):
            with pytest.raises(Exception):
                await analyzer.get_timeframe_alignment("BTCUSDT")


class TestWeightedScoring:
    """Test weighted scoring logic"""

    @pytest.mark.asyncio
    async def test_longer_timeframes_have_more_weight(self, analyzer, mock_httpx_response):
        """Test that longer timeframes influence score more"""
        # This is implicit in the TIMEFRAME_WEIGHTS configuration
        weights = analyzer.TIMEFRAME_WEIGHTS
        assert weights["1d"] > weights["1m"]


class TestTrendClassification:
    """Test trend classification logic"""

    @pytest.mark.asyncio
    async def test_classify_trend_strong_bullish(self, analyzer, mock_httpx_response):
        """Test strong bullish classification"""
        async def mock_get(*args, **kwargs):
            return mock_httpx_response(trend="BULLISH", strength=95)

        with patch.object(analyzer.client, 'get', side_effect=mock_get):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            # High strength + alignment = strong trend
            assert result["alignment_score"] > 80

    @pytest.mark.asyncio
    async def test_classify_trend_neutral(self, analyzer):
        """Test neutral trend classification"""
        async def mock_get(*args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {"trend": "NEUTRAL", "strength": 50}
            return response

        with patch.object(analyzer.client, 'get', side_effect=mock_get):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            assert result["trend_direction"] == "NEUTRAL"


class TestSingletonPattern:
    """Test analyzer singleton"""

    @patch('app.multi_timeframe.MultiTimeframeAnalyzer')
    def test_get_analyzer_singleton(self, mock_analyzer_class):
        """Test that get_multi_timeframe_analyzer returns singleton"""
        mock_instance = MagicMock()
        mock_analyzer_class.return_value = mock_instance

        analyzer1 = get_multi_timeframe_analyzer()
        analyzer2 = get_multi_timeframe_analyzer()

        # Should return same instance
        assert analyzer1 is analyzer2

    @pytest.mark.asyncio
    async def test_close_analyzer_singleton(self):
        """Test closing analyzer singleton"""
        # Should handle close gracefully
        await close_multi_timeframe_analyzer()


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_invalid_symbol(self, analyzer):
        """Test alignment with invalid symbol"""
        async def mock_get_404(*args, **kwargs):
            response = MagicMock()
            response.status_code = 404
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not found", request=None, response=response
            )
            return response

        with patch.object(analyzer.client, 'get', side_effect=mock_get_404):
            # Should handle 404 errors
            with pytest.raises(Exception):
                await analyzer.get_timeframe_alignment("INVALID")

    @pytest.mark.asyncio
    async def test_empty_response(self, analyzer):
        """Test alignment with empty response"""
        async def mock_get_empty(*args, **kwargs):
            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {}
            return response

        with patch.object(analyzer.client, 'get', side_effect=mock_get_empty):
            # Should handle empty responses gracefully
            result = await analyzer.get_timeframe_alignment("BTCUSDT")
            # Implementation should handle this case


class TestConcurrentAnalysis:
    """Test concurrent timeframe analysis"""

    @pytest.mark.asyncio
    async def test_parallel_timeframe_requests(self, analyzer, mock_httpx_response):
        """Test that timeframe analyses run in parallel"""
        call_times = []

        async def mock_get_with_delay(*args, **kwargs):
            import asyncio
            call_times.append(len(call_times))
            await asyncio.sleep(0.1)  # Simulate network delay
            return mock_httpx_response()

        with patch.object(analyzer.client, 'get', side_effect=mock_get_with_delay):
            import time
            start = time.time()
            await analyzer.get_timeframe_alignment("BTCUSDT")
            elapsed = time.time() - start

            # If running in parallel, should take ~0.1s, not 0.6s (6 timeframes)
            # Allow some overhead
            assert elapsed < 0.5, "Timeframes should be analyzed in parallel"


class TestConfidenceCalculation:
    """Test confidence score calculation"""

    @pytest.mark.asyncio
    async def test_confidence_increases_with_alignment(self, analyzer, mock_httpx_response):
        """Test that confidence increases when timeframes align"""
        # All aligned bullish
        async def mock_get_aligned(*args, **kwargs):
            return mock_httpx_response(trend="BULLISH", strength=80)

        with patch.object(analyzer.client, 'get', side_effect=mock_get_aligned):
            aligned_result = await analyzer.get_timeframe_alignment("BTCUSDT")

        # Mixed signals
        call_count = [0]

        async def mock_get_mixed(*args, **kwargs):
            call_count[0] += 1
            trend = "BULLISH" if call_count[0] % 2 == 0 else "BEARISH"
            return mock_httpx_response(trend=trend, strength=60)

        with patch.object(analyzer.client, 'get', side_effect=mock_get_mixed):
            mixed_result = await analyzer.get_timeframe_alignment("BTCUSDT")

        # Aligned should have higher confidence
        assert aligned_result["confidence"] > mixed_result["confidence"]
