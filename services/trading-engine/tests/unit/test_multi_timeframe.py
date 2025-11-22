"""
Unit tests for Multi-Timeframe Analysis Module
Tests trend analysis across multiple timeframes
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import httpx

from app.multi_timeframe import (
    TrendDirection,
    MultiTimeframeAnalyzer,
    get_multi_timeframe_analyzer,
    close_multi_timeframe_analyzer
)


class TestTrendDirection:
    """Test TrendDirection enum"""

    def test_trend_direction_values(self):
        """Test all trend direction enum values exist"""
        assert TrendDirection.STRONG_BULLISH == "STRONG_BULLISH"
        assert TrendDirection.BULLISH == "BULLISH"
        assert TrendDirection.NEUTRAL == "NEUTRAL"
        assert TrendDirection.BEARISH == "BEARISH"
        assert TrendDirection.STRONG_BEARISH == "STRONG_BEARISH"


class TestMultiTimeframeAnalyzer:
    """Test MultiTimeframeAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        return MultiTimeframeAnalyzer()

    @pytest.fixture
    def mock_http_client(self):
        """Create mock HTTP client"""
        client = AsyncMock()
        return client

    def test_initialization_default_url(self, analyzer):
        """Test analyzer initialization with default TA service URL"""
        assert analyzer.ta_service_url == "http://localhost:8004"

    def test_initialization_custom_url(self):
        """Test analyzer initialization with custom URL"""
        analyzer = MultiTimeframeAnalyzer(ta_service_url="http://custom:9000")
        assert analyzer.ta_service_url == "http://custom:9000"

    def test_timeframes_defined(self, analyzer):
        """Test that all 6 timeframes are defined"""
        assert len(analyzer.TIMEFRAMES) == 6
        assert "1m" in analyzer.TIMEFRAMES
        assert "5m" in analyzer.TIMEFRAMES
        assert "15m" in analyzer.TIMEFRAMES
        assert "60m" in analyzer.TIMEFRAMES
        assert "4h" in analyzer.TIMEFRAMES
        assert "1d" in analyzer.TIMEFRAMES

    def test_timeframe_weights_defined(self, analyzer):
        """Test that weights are defined for all timeframes"""
        assert len(analyzer.TIMEFRAME_WEIGHTS) == 6
        # Longer timeframes should have higher weights
        assert analyzer.TIMEFRAME_WEIGHTS["1d"] > analyzer.TIMEFRAME_WEIGHTS["4h"]
        assert analyzer.TIMEFRAME_WEIGHTS["4h"] > analyzer.TIMEFRAME_WEIGHTS["60m"]
        assert analyzer.TIMEFRAME_WEIGHTS["60m"] > analyzer.TIMEFRAME_WEIGHTS["1m"]

    @pytest.mark.asyncio
    async def test_close_client(self, analyzer):
        """Test closing HTTP client"""
        # Should not raise error
        await analyzer.close()

    def test_calculate_alignment_all_bullish(self, analyzer):
        """Test alignment calculation with all bullish timeframes"""
        timeframes = {
            "1m": {"trend": TrendDirection.BULLISH, "strength": 70},
            "5m": {"trend": TrendDirection.BULLISH, "strength": 75},
            "15m": {"trend": TrendDirection.STRONG_BULLISH, "strength": 85},
            "60m": {"trend": TrendDirection.BULLISH, "strength": 80},
            "4h": {"trend": TrendDirection.STRONG_BULLISH, "strength": 90},
            "1d": {"trend": TrendDirection.STRONG_BULLISH, "strength": 95}
        }

        analysis = analyzer._calculate_alignment(timeframes)

        assert analysis["bullish_count"] == 6
        assert analysis["bearish_count"] == 0
        assert analysis["neutral_count"] == 0
        assert analysis["weighted_score"] > 0  # Positive for bullish
        assert analysis["alignment_percentage"] == 100.0  # All agree

    def test_calculate_alignment_all_bearish(self, analyzer):
        """Test alignment calculation with all bearish timeframes"""
        timeframes = {
            "1m": {"trend": TrendDirection.BEARISH, "strength": 70},
            "5m": {"trend": TrendDirection.BEARISH, "strength": 75},
            "15m": {"trend": TrendDirection.STRONG_BEARISH, "strength": 85},
            "60m": {"trend": TrendDirection.BEARISH, "strength": 80},
            "4h": {"trend": TrendDirection.STRONG_BEARISH, "strength": 90},
            "1d": {"trend": TrendDirection.STRONG_BEARISH, "strength": 95}
        }

        analysis = analyzer._calculate_alignment(timeframes)

        assert analysis["bullish_count"] == 0
        assert analysis["bearish_count"] == 6
        assert analysis["neutral_count"] == 0
        assert analysis["weighted_score"] < 0  # Negative for bearish
        assert analysis["alignment_percentage"] == 100.0

    def test_calculate_alignment_mixed_signals(self, analyzer):
        """Test alignment calculation with mixed signals"""
        timeframes = {
            "1m": {"trend": TrendDirection.BULLISH, "strength": 60},
            "5m": {"trend": TrendDirection.BEARISH, "strength": 65},
            "15m": {"trend": TrendDirection.NEUTRAL, "strength": 50},
            "60m": {"trend": TrendDirection.BULLISH, "strength": 70},
            "4h": {"trend": TrendDirection.BEARISH, "strength": 75},
            "1d": {"trend": TrendDirection.NEUTRAL, "strength": 50}
        }

        analysis = analyzer._calculate_alignment(timeframes)

        assert analysis["bullish_count"] == 2
        assert analysis["bearish_count"] == 2
        assert analysis["neutral_count"] == 2
        assert analysis["alignment_percentage"] < 100.0  # Not all agree

    def test_determine_overall_trend_strong_bullish(self, analyzer):
        """Test determining trend with strong bullish signal"""
        analysis = {
            "weighted_score": 75.0,
            "bullish_count": 5,
            "bearish_count": 0,
            "neutral_count": 1
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.STRONG_BULLISH

    def test_determine_overall_trend_strong_bearish(self, analyzer):
        """Test determining trend with strong bearish signal"""
        analysis = {
            "weighted_score": -75.0,
            "bullish_count": 0,
            "bearish_count": 5,
            "neutral_count": 1
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.STRONG_BEARISH

    def test_determine_overall_trend_bullish(self, analyzer):
        """Test determining trend with moderate bullish signal"""
        analysis = {
            "weighted_score": 45.0,
            "bullish_count": 4,
            "bearish_count": 1,
            "neutral_count": 1
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.BULLISH

    def test_determine_overall_trend_bearish(self, analyzer):
        """Test determining trend with moderate bearish signal"""
        analysis = {
            "weighted_score": -45.0,
            "bullish_count": 1,
            "bearish_count": 4,
            "neutral_count": 1
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.BEARISH

    def test_determine_overall_trend_neutral_by_score(self, analyzer):
        """Test determining trend with neutral weighted score"""
        analysis = {
            "weighted_score": 10.0,  # Weak score
            "bullish_count": 2,
            "bearish_count": 2,
            "neutral_count": 2
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.NEUTRAL

    def test_determine_overall_trend_majority_vote_fallback(self, analyzer):
        """Test determining trend using majority vote when score is weak"""
        # Weak weighted score but clear majority
        analysis = {
            "weighted_score": 15.0,  # Weak score (< 30)
            "bullish_count": 4,  # Clear majority
            "bearish_count": 1,
            "neutral_count": 1
        }

        trend = analyzer._determine_overall_trend({}, analysis)
        assert trend == TrendDirection.BULLISH

    def test_calculate_confidence_perfect_alignment(self, analyzer):
        """Test confidence calculation with perfect alignment"""
        analysis = {
            "alignment_percentage": 100.0,
            "weighted_score": 80.0
        }

        confidence = analyzer._calculate_confidence(analysis, successful_analyses=6)

        assert confidence >= 100  # Will be clamped to 100
        # After clamping
        assert confidence == 100

    def test_calculate_confidence_low_alignment(self, analyzer):
        """Test confidence calculation with low alignment"""
        analysis = {
            "alignment_percentage": 33.0,
            "weighted_score": 20.0
        }

        confidence = analyzer._calculate_confidence(analysis, successful_analyses=6)

        assert confidence < 50

    def test_calculate_confidence_with_failed_analyses(self, analyzer):
        """Test confidence calculation with some failed analyses"""
        analysis = {
            "alignment_percentage": 80.0,
            "weighted_score": 60.0
        }

        # Only 4 out of 6 successful
        confidence = analyzer._calculate_confidence(analysis, successful_analyses=4)

        # Should have penalty: (6 - 4) * 5 = 10 points
        assert confidence < 95  # Base would be ~95, minus 10 penalty

    def test_get_recommendation_strong_buy(self, analyzer):
        """Test recommendation for strong buy signal"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.STRONG_BULLISH,
            confidence=80,
            weighted_score=70.0
        )

        assert "STRONG BUY" in recommendation

    def test_get_recommendation_buy(self, analyzer):
        """Test recommendation for buy signal"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.BULLISH,
            confidence=65,
            weighted_score=40.0
        )

        assert "BUY" in recommendation

    def test_get_recommendation_strong_sell(self, analyzer):
        """Test recommendation for strong sell signal"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.STRONG_BEARISH,
            confidence=80,
            weighted_score=-70.0
        )

        assert "STRONG SELL" in recommendation

    def test_get_recommendation_sell(self, analyzer):
        """Test recommendation for sell signal"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.BEARISH,
            confidence=65,
            weighted_score=-40.0
        )

        assert "SELL" in recommendation

    def test_get_recommendation_hold_neutral(self, analyzer):
        """Test recommendation for neutral trend"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.NEUTRAL,
            confidence=60,
            weighted_score=5.0
        )

        assert "HOLD" in recommendation

    def test_get_recommendation_avoid_low_confidence(self, analyzer):
        """Test recommendation when confidence is too low"""
        recommendation = analyzer._get_recommendation(
            TrendDirection.BULLISH,
            confidence=40,  # Below 50
            weighted_score=30.0
        )

        assert "AVOID" in recommendation

    def test_create_low_confidence_response(self, analyzer):
        """Test creating low confidence response"""
        timeframes = {"1m": {"trend": TrendDirection.NEUTRAL, "strength": 0}}

        response = analyzer._create_low_confidence_response(timeframes)

        assert response["confidence"] == 0
        assert response["trend_direction"] == TrendDirection.NEUTRAL
        assert response["alignment_score"] == 0
        assert "HOLD" in response["recommendation"]
        assert "error" in response

    def test_create_error_response(self, analyzer):
        """Test creating error response"""
        response = analyzer._create_error_response("BTCUSDT", "API timeout")

        assert response["symbol"] == "BTCUSDT"
        assert response["confidence"] == 0
        assert response["trend_direction"] == TrendDirection.NEUTRAL
        assert "ERROR" in response["recommendation"]
        assert response["error"] == "API timeout"

    @pytest.mark.asyncio
    async def test_get_timeframe_trend_successful(self, analyzer):
        """Test getting trend for a timeframe with successful API response"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "trend": "BULLISH",
                "strength": 75,
                "ema_50": 50000,
                "ema_200": 48000,
                "current_price": 51000
            }
        }
        mock_response.raise_for_status = Mock()

        with patch.object(analyzer.client, 'get', return_value=mock_response):
            result = await analyzer._get_timeframe_trend("BTCUSDT", "60m", 60)

            assert result["trend"] == TrendDirection.BULLISH
            assert result["strength"] == 75
            assert "indicators" in result

    @pytest.mark.asyncio
    async def test_get_timeframe_trend_strong_bullish(self, analyzer):
        """Test trend mapping to STRONG_BULLISH"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "trend": "BULLISH",
                "strength": 85  # >= 80 = strong
            }
        }
        mock_response.raise_for_status = Mock()

        with patch.object(analyzer.client, 'get', return_value=mock_response):
            result = await analyzer._get_timeframe_trend("BTCUSDT", "60m", 60)

            assert result["trend"] == TrendDirection.STRONG_BULLISH

    @pytest.mark.asyncio
    async def test_get_timeframe_trend_strong_bearish(self, analyzer):
        """Test trend mapping to STRONG_BEARISH"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "trend": "BEARISH",
                "strength": 90  # >= 80 = strong
            }
        }
        mock_response.raise_for_status = Mock()

        with patch.object(analyzer.client, 'get', return_value=mock_response):
            result = await analyzer._get_timeframe_trend("BTCUSDT", "60m", 60)

            assert result["trend"] == TrendDirection.STRONG_BEARISH

    @pytest.mark.asyncio
    async def test_get_timeframe_trend_404_response(self, analyzer):
        """Test handling 404 response (no data available)"""
        mock_response = Mock()
        mock_response.status_code = 404

        http_error = httpx.HTTPStatusError(
            "Not found",
            request=Mock(),
            response=mock_response
        )

        with patch.object(analyzer.client, 'get', side_effect=http_error):
            result = await analyzer._get_timeframe_trend("BTCUSDT", "60m", 60)

            assert result["trend"] == TrendDirection.NEUTRAL
            assert result["strength"] == 0
            assert "note" in result

    @pytest.mark.asyncio
    async def test_get_timeframe_trend_api_error(self, analyzer):
        """Test handling API error response"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "success": False,
            "message": "API rate limit exceeded"
        }
        mock_response.raise_for_status = Mock()

        with patch.object(analyzer.client, 'get', return_value=mock_response):
            with pytest.raises(ValueError, match="API rate limit exceeded"):
                await analyzer._get_timeframe_trend("BTCUSDT", "60m", 60)


@pytest.mark.asyncio
class TestMultiTimeframeSingleton:
    """Test multi-timeframe analyzer singleton pattern"""

    async def test_get_analyzer_returns_instance(self):
        """Test that get_multi_timeframe_analyzer returns instance"""
        analyzer = await get_multi_timeframe_analyzer()
        assert isinstance(analyzer, MultiTimeframeAnalyzer)

    async def test_get_analyzer_returns_same_instance(self):
        """Test singleton behavior"""
        analyzer1 = await get_multi_timeframe_analyzer()
        analyzer2 = await get_multi_timeframe_analyzer()

        assert analyzer1 is analyzer2

    async def test_close_analyzer(self):
        """Test closing analyzer"""
        # Get instance
        analyzer = await get_multi_timeframe_analyzer()
        assert analyzer is not None

        # Close it
        await close_multi_timeframe_analyzer()

        # Getting again should create new instance
        new_analyzer = await get_multi_timeframe_analyzer()
        assert new_analyzer is not analyzer


class TestIntegrationScenarios:
    """Test integrated multi-timeframe analysis scenarios"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        return MultiTimeframeAnalyzer()

    def test_weighted_score_calculation_long_term_dominance(self, analyzer):
        """Test that longer timeframes dominate weighted score"""
        # 1d (weight=5.0) is bullish, all others bearish (weights: 1.0, 1.5, 2.0, 3.0, 4.0)
        timeframes = {
            "1m": {"trend": TrendDirection.BEARISH, "strength": 80},  # weight 1.0
            "5m": {"trend": TrendDirection.BEARISH, "strength": 80},  # weight 1.5
            "15m": {"trend": TrendDirection.BEARISH, "strength": 80}, # weight 2.0
            "60m": {"trend": TrendDirection.BEARISH, "strength": 80}, # weight 3.0
            "4h": {"trend": TrendDirection.BEARISH, "strength": 80},  # weight 4.0
            "1d": {"trend": TrendDirection.BULLISH, "strength": 100}  # weight 5.0
        }

        analysis = analyzer._calculate_alignment(timeframes)

        # Even though 5 are bearish and only 1 is bullish,
        # the 1d timeframe's high weight should make the score less bearish
        # Total bearish weight: 1+1.5+2+3+4 = 11.5 * 0.8 = 9.2
        # Total bullish weight: 5.0 * 1.0 = 5.0
        # Should be negative but not extremely negative
        assert analysis["weighted_score"] < 0
        assert analysis["weighted_score"] > -60  # Not too bearish due to 1d influence


@pytest.mark.asyncio
class TestGetTimeframeAlignment:
    """Test the main get_timeframe_alignment method"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        return MultiTimeframeAnalyzer()

    async def test_get_timeframe_alignment_success(self, analyzer):
        """Test successful multi-timeframe analysis"""
        # Mock _get_timeframe_trend to return successful results
        async def mock_get_trend(symbol, tf_name, interval):
            return {
                "trend": TrendDirection.BULLISH,
                "strength": 75,
                "indicators": {}
            }

        with patch.object(analyzer, '_get_timeframe_trend', side_effect=mock_get_trend):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            assert result["symbol"] == "BTCUSDT"
            assert result["trend_direction"] == TrendDirection.STRONG_BULLISH
            assert result["confidence"] > 0
            assert "timeframes" in result
            assert "analysis" in result
            assert "recommendation" in result

    async def test_get_timeframe_alignment_insufficient_successful_analyses(self, analyzer):
        """Test when less than 4 timeframes succeed"""
        call_count = 0

        async def mock_get_trend(symbol, tf_name, interval):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:  # Only first 3 succeed
                return {"trend": TrendDirection.NEUTRAL, "strength": 50}
            raise Exception("Timeframe failed")

        with patch.object(analyzer, '_get_timeframe_trend', side_effect=mock_get_trend):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            # Should return low confidence response
            assert result["confidence"] == 0
            assert result["trend_direction"] == TrendDirection.NEUTRAL
            assert "error" in result

    async def test_get_timeframe_alignment_partial_failures(self, analyzer):
        """Test when some timeframes fail but still have enough"""
        call_count = 0

        async def mock_get_trend(symbol, tf_name, interval):
            nonlocal call_count
            call_count += 1
            if call_count <= 4:  # First 4 succeed
                return {"trend": TrendDirection.BULLISH, "strength": 80}
            raise Exception("Timeframe failed")

        with patch.object(analyzer, '_get_timeframe_trend', side_effect=mock_get_trend):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            # Should still analyze with 4 successful timeframes
            assert result["confidence"] > 0
            assert "timeframes" in result
            assert len(result["timeframes"]) == 6  # All timeframes reported

    async def test_get_timeframe_alignment_all_timeframes_fail(self, analyzer):
        """Test when all timeframes fail"""
        # Mock _get_timeframe_trend to always raise exception
        with patch.object(analyzer, '_get_timeframe_trend', side_effect=Exception("Critical error")):
            result = await analyzer.get_timeframe_alignment("BTCUSDT")

            # Should return low confidence response (0/6 successful)
            assert result["confidence"] == 0
            assert result["trend_direction"] == TrendDirection.NEUTRAL
            assert "HOLD" in result["recommendation"]
            assert "error" in result  # Has error field
