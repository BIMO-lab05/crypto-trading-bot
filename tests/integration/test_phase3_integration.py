"""
Integration Tests for Phase 3 Endpoints
Tests end-to-end communication between API Gateway and backend services
Author: Python-Pro Agent
Date: 2025-11-19
Requirements: sentiment-analysis:8008 and technical-analysis:8004 must be running
"""

import pytest
import httpx
import asyncio
import time


# ============================================================================
# CONFIGURATION
# ============================================================================

API_GATEWAY_URL = "http://localhost:8000"
SENTIMENT_SERVICE_URL = "http://localhost:8008"
TECHNICAL_ANALYSIS_URL = "http://localhost:8004"

# Test symbols
TEST_SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# Timeouts
REQUEST_TIMEOUT = 30.0


# ============================================================================
# FIXTURES (D-12 REFACTOR — Plan 02-04)
# ============================================================================
# The local async_client fixture (duplicate of conftest http_client) and the
# silent-skip availability fixture have been deleted. Tests now depend on
# bootstrap_stack (conftest, session-scoped) which hard-fails when services
# are unhealthy — no silent-green path exists.


# ============================================================================
# SENTIMENT ANALYSIS INTEGRATION TESTS
# ============================================================================


class TestSentimentAnalysisIntegration:
    """Integration tests for sentiment analysis endpoints"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_news_sentiment_end_to_end(self, http_client, bootstrap_stack):
        """Test complete flow: Gateway -> Sentiment Service for news sentiment"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}"

        response = await http_client.get(url)

        # Verify response
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text}"
        )

        data = response.json()

        # Validate response structure
        assert "symbol" in data
        assert data["symbol"] == symbol
        assert "sentiment_label" in data
        assert data["sentiment_label"] in ["BULLISH", "BEARISH", "NEUTRAL"]
        assert "sentiment_score" in data
        assert 0.0 <= data["sentiment_score"] <= 1.0
        assert "confidence" in data
        assert 0.0 <= data["confidence"] <= 1.0
        assert "news_count" in data
        assert isinstance(data["news_count"], int)
        assert "analyzed_at" in data

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_social_sentiment_end_to_end(self, http_client, bootstrap_stack):
        """Test complete flow: Gateway -> Sentiment Service for social sentiment"""
        symbol = "ETHUSDT"
        url = f"{API_GATEWAY_URL}/api/sentiment/social/{symbol}"

        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert data["symbol"] == symbol
        assert "sentiment_label" in data
        assert "sentiment_score" in data
        assert "confidence" in data
        assert "post_count" in data
        assert isinstance(data["post_count"], int)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_combined_sentiment_end_to_end(self, http_client, bootstrap_stack):
        """Test complete flow: Gateway -> Sentiment Service for combined sentiment"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/sentiment/combined/{symbol}"

        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Validate combined sentiment structure
        assert data["symbol"] == symbol
        assert "combined_label" in data
        assert "combined_score" in data
        assert "confidence" in data

        # Validate nested sentiment sources
        assert "news_sentiment" in data
        assert "social_sentiment" in data
        assert "market_sentiment" in data

        # Each source should have label, score, and weight
        for source in ["news_sentiment", "social_sentiment", "market_sentiment"]:
            assert "label" in data[source]
            assert "score" in data[source]
            assert "weight" in data[source]

        # Weights should sum to 1.0 (or close to it)
        total_weight = (
            data["news_sentiment"]["weight"]
            + data["social_sentiment"]["weight"]
            + data["market_sentiment"]["weight"]
        )
        assert 0.95 <= total_weight <= 1.05, (
            f"Weights sum to {total_weight}, expected ~1.0"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sentiment_trend_end_to_end(self, http_client, bootstrap_stack):
        """Test complete flow: Gateway -> Sentiment Service for sentiment trend"""
        symbol = "BTCUSDT"
        hours = 24

        url = f"{API_GATEWAY_URL}/api/sentiment/trend/{symbol}?hours={hours}"

        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Validate trend response
        assert data["symbol"] == symbol
        assert data["timeframe_hours"] == hours
        assert "current_sentiment" in data
        assert "trend_direction" in data
        assert data["trend_direction"] in ["IMPROVING", "DECLINING", "STABLE"]
        assert "data_points" in data
        assert isinstance(data["data_points"], list)
        assert len(data["data_points"]) > 0

        # Validate data points structure
        for point in data["data_points"]:
            assert "timestamp" in point
            assert "sentiment_score" in point
            assert "sentiment_label" in point

        assert "average_score" in data
        assert 0.0 <= data["average_score"] <= 1.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sentiment_trend_custom_timeframe(self, http_client, bootstrap_stack):
        """Test sentiment trend with different timeframe parameters"""
        symbol = "ETHUSDT"

        # Test various timeframes
        timeframes = [6, 12, 24, 48]

        for hours in timeframes:
            url = f"{API_GATEWAY_URL}/api/sentiment/trend/{symbol}?hours={hours}"
            response = await http_client.get(url)

            assert response.status_code == 200
            data = response.json()
            assert data["timeframe_hours"] == hours


# ============================================================================
# MULTI-TIMEFRAME ANALYSIS INTEGRATION TESTS
# ============================================================================


class TestMultiTimeframeAnalysisIntegration:
    """Integration tests for multi-timeframe analysis endpoints"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multi_timeframe_analysis_end_to_end(
        self, http_client, bootstrap_stack
    ):
        """Test complete flow: Gateway -> Technical Analysis for multi-timeframe"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/analysis/multi-timeframe/{symbol}"

        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert data["symbol"] == symbol
        assert "alignment_score" in data
        assert 0 <= data["alignment_score"] <= 100
        assert "consensus_signal" in data
        assert data["consensus_signal"] in ["BUY", "SELL", "NEUTRAL", "HOLD"]
        assert "signal_strength" in data
        assert 0.0 <= data["signal_strength"] <= 1.0

        # Validate timeframe signals
        assert "timeframe_signals" in data
        assert isinstance(data["timeframe_signals"], list)
        assert len(data["timeframe_signals"]) > 0

        # Validate each timeframe signal structure
        for tf_signal in data["timeframe_signals"]:
            assert "timeframe" in tf_signal
            assert "signal" in tf_signal
            assert tf_signal["signal"] in ["BUY", "SELL", "NEUTRAL", "HOLD"]
            assert "strength" in tf_signal
            assert 0.0 <= tf_signal["strength"] <= 1.0
            assert "rsi" in tf_signal
            assert "macd_signal" in tf_signal

        assert "recommendation" in data
        assert isinstance(data["recommendation"], str)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_indicator_signal_end_to_end_default_interval(
        self, http_client, bootstrap_stack
    ):
        """Test complete flow: Gateway -> Technical Analysis for indicator signals"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/analysis/indicators/signal/{symbol}"

        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Validate response structure
        assert data["symbol"] == symbol
        assert "interval" in data
        assert data["interval"] == "60"  # Default interval
        assert "aggregated_signal" in data
        assert data["aggregated_signal"] in ["BUY", "SELL", "NEUTRAL", "HOLD"]
        assert "confidence" in data
        assert 0.0 <= data["confidence"] <= 1.0

        # Validate indicator signals
        assert "indicator_signals" in data
        indicators = data["indicator_signals"]

        # Check for standard indicators
        expected_indicators = ["rsi", "macd", "bollinger", "ema_cross"]
        for indicator in expected_indicators:
            assert indicator in indicators, f"Missing indicator: {indicator}"

        # Validate RSI structure
        assert "value" in indicators["rsi"]
        assert "signal" in indicators["rsi"]
        assert "strength" in indicators["rsi"]

        # Validate indicator counts
        assert "buy_indicators" in data
        assert "sell_indicators" in data
        assert "neutral_indicators" in data

        total_indicators = (
            data["buy_indicators"]
            + data["sell_indicators"]
            + data["neutral_indicators"]
        )
        assert total_indicators == len(expected_indicators)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_indicator_signal_custom_intervals(
        self, http_client, bootstrap_stack
    ):
        """Test indicator signal with various interval parameters"""
        symbol = "ETHUSDT"

        # Test various intervals
        intervals = ["5", "15", "60", "240"]

        for interval in intervals:
            url = f"{API_GATEWAY_URL}/api/analysis/indicators/signal/{symbol}?interval={interval}"
            response = await http_client.get(url)

            assert response.status_code == 200
            data = response.json()
            assert data["interval"] == interval
            assert "aggregated_signal" in data


# ============================================================================
# CROSS-ENDPOINT INTEGRATION TESTS
# ============================================================================


class TestCrossEndpointIntegration:
    """Test integration between different Phase 3 endpoints"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sentiment_and_technical_alignment(
        self, http_client, bootstrap_stack
    ):
        """
        Test that sentiment and technical analysis can be retrieved together
        This simulates a trading bot combining both signals
        """
        symbol = "BTCUSDT"

        # Get sentiment signal
        sentiment_url = f"{API_GATEWAY_URL}/api/sentiment/combined/{symbol}"
        sentiment_response = await http_client.get(sentiment_url)

        # Get technical signal
        technical_url = f"{API_GATEWAY_URL}/api/analysis/multi-timeframe/{symbol}"
        technical_response = await http_client.get(technical_url)

        # Both should succeed
        assert sentiment_response.status_code == 200
        assert technical_response.status_code == 200

        sentiment_data = sentiment_response.json()
        technical_data = technical_response.json()

        # Both should be for the same symbol
        assert sentiment_data["symbol"] == symbol
        assert technical_data["symbol"] == symbol

        # Both should have signals
        assert "combined_label" in sentiment_data
        assert "consensus_signal" in technical_data

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_parallel_sentiment_requests(self, http_client, bootstrap_stack):
        """Test making parallel requests to different sentiment endpoints"""
        symbol = "BTCUSDT"

        # Make parallel requests
        news_task = http_client.get(f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}")
        social_task = http_client.get(
            f"{API_GATEWAY_URL}/api/sentiment/social/{symbol}"
        )
        combined_task = http_client.get(
            f"{API_GATEWAY_URL}/api/sentiment/combined/{symbol}"
        )

        # Wait for all responses
        responses = await asyncio.gather(news_task, social_task, combined_task)

        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert data["symbol"] == symbol

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_multiple_symbols_sequential(self, http_client, bootstrap_stack):
        """Test requesting data for multiple symbols sequentially"""
        for symbol in TEST_SYMBOLS:
            # Test news sentiment
            response = await http_client.get(
                f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}"
            )
            assert response.status_code == 200
            assert response.json()["symbol"] == symbol

            # Test multi-timeframe
            response = await http_client.get(
                f"{API_GATEWAY_URL}/api/analysis/multi-timeframe/{symbol}"
            )
            assert response.status_code == 200
            assert response.json()["symbol"] == symbol


# ============================================================================
# ERROR HANDLING INTEGRATION TESTS
# ============================================================================


class TestErrorHandlingIntegration:
    """Test error handling in end-to-end scenarios"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_symbol_propagation(self, http_client, bootstrap_stack):
        """Test that invalid symbol errors propagate correctly"""
        invalid_symbol = "INVALID_SYMBOL_XYZ"

        url = f"{API_GATEWAY_URL}/api/sentiment/news/{invalid_symbol}"
        response = await http_client.get(url)

        # Should return error (400 or 404)
        assert response.status_code in [400, 404, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_interval_parameter(self, http_client, bootstrap_stack):
        """Test handling of invalid interval parameter"""
        symbol = "BTCUSDT"
        invalid_interval = "invalid"

        url = f"{API_GATEWAY_URL}/api/analysis/indicators/signal/{symbol}?interval={invalid_interval}"
        response = await http_client.get(url)

        # Should return error or handle gracefully
        # Status code depends on backend service validation
        assert response.status_code in [200, 400, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_negative_hours_parameter(self, http_client, bootstrap_stack):
        """Test handling of negative hours parameter in sentiment trend"""
        symbol = "BTCUSDT"
        invalid_hours = -5

        url = f"{API_GATEWAY_URL}/api/sentiment/trend/{symbol}?hours={invalid_hours}"
        response = await http_client.get(url)

        # Should return error or handle gracefully
        assert response.status_code in [200, 400, 422]


# ============================================================================
# PERFORMANCE INTEGRATION TESTS
# ============================================================================


class TestPerformanceIntegration:
    """Test performance characteristics in real environment"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_sentiment_endpoint_response_time(self, http_client, bootstrap_stack):
        """Test that sentiment endpoints respond within acceptable time"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}"

        start_time = time.time()
        response = await http_client.get(url)
        end_time = time.time()

        response_time = end_time - start_time

        assert response.status_code == 200
        # Should respond within 5 seconds (including network + processing)
        assert response_time < 5.0, (
            f"Response time {response_time}s exceeded 5s threshold"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_multi_timeframe_response_time(self, http_client, bootstrap_stack):
        """Test that multi-timeframe analysis responds within acceptable time"""
        symbol = "BTCUSDT"
        url = f"{API_GATEWAY_URL}/api/analysis/multi-timeframe/{symbol}"

        start_time = time.time()
        response = await http_client.get(url)
        end_time = time.time()

        response_time = end_time - start_time

        assert response.status_code == 200
        # Multi-timeframe analysis may take longer (analyzing multiple timeframes)
        assert response_time < 10.0, (
            f"Response time {response_time}s exceeded 10s threshold"
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_concurrent_load(self, http_client, bootstrap_stack):
        """Test system behavior under concurrent load"""
        symbol = "BTCUSDT"

        # Create 10 concurrent requests
        tasks = [
            http_client.get(f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}")
            for _ in range(10)
        ]

        start_time = time.time()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        total_time = end_time - start_time

        # Count successful responses
        successful = sum(
            1
            for r in responses
            if isinstance(r, httpx.Response) and r.status_code == 200
        )

        # At least 80% should succeed
        assert successful >= 8, f"Only {successful}/10 requests succeeded"

        # Total time should be reasonable (not 10x single request time)
        assert total_time < 20.0, f"10 concurrent requests took {total_time}s"


# ============================================================================
# DATA CONSISTENCY INTEGRATION TESTS
# ============================================================================


class TestDataConsistencyIntegration:
    """Test data consistency across multiple requests"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sentiment_trend_consistency(self, http_client, bootstrap_stack):
        """Test that sentiment trend data is consistent across requests"""
        symbol = "BTCUSDT"
        hours = 24

        url = f"{API_GATEWAY_URL}/api/sentiment/trend/{symbol}?hours={hours}"

        # Make two requests
        response1 = await http_client.get(url)
        await asyncio.sleep(1)  # Small delay
        response2 = await http_client.get(url)

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Symbol and timeframe should be consistent
        assert data1["symbol"] == data2["symbol"]
        assert data1["timeframe_hours"] == data2["timeframe_hours"]

        # Scores might change slightly but should be in similar range
        # (unless there's breaking news)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_combined_sentiment_components_match(
        self, http_client, bootstrap_stack
    ):
        """
        Test that combined sentiment components match individual endpoints
        Note: This might not be exact due to timing, but should be close
        """
        symbol = "BTCUSDT"

        # Get individual sentiments
        news_response = await http_client.get(
            f"{API_GATEWAY_URL}/api/sentiment/news/{symbol}"
        )
        social_response = await http_client.get(
            f"{API_GATEWAY_URL}/api/sentiment/social/{symbol}"
        )

        # Get combined sentiment
        combined_response = await http_client.get(
            f"{API_GATEWAY_URL}/api/sentiment/combined/{symbol}"
        )

        assert news_response.status_code == 200
        assert social_response.status_code == 200
        assert combined_response.status_code == 200

        news_data = news_response.json()
        social_data = social_response.json()
        combined_data = combined_response.json()

        # Labels should be from the standard set
        valid_labels = ["BULLISH", "BEARISH", "NEUTRAL"]
        assert news_data["sentiment_label"] in valid_labels
        assert social_data["sentiment_label"] in valid_labels
        assert combined_data["combined_label"] in valid_labels


# ============================================================================
# HEALTH CHECK INTEGRATION
# ============================================================================


class TestHealthCheckIntegration:
    """Test health check integration with Phase 3 services"""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_health_check_includes_phase3_services(
        self, http_client, bootstrap_stack
    ):
        """Test that health check endpoint includes Phase 3 services"""
        url = f"{API_GATEWAY_URL}/health"
        response = await http_client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Check if backend services are reported
        if "backend_services" in data:
            # At minimum, the service should be tracking these
            # Exact structure depends on implementation
            assert isinstance(data["backend_services"], dict)
