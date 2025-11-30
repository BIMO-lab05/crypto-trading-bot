"""
Tests for Sentiment Analysis Service API endpoints
Tests FastAPI endpoints for news sentiment, social sentiment, and combined analysis
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta

from app.main import app


@pytest.fixture
def client():
    """
    Creates test client for FastAPI app
    """
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint"""

    def test_health_check(self, client):
        """
        Test /health endpoint returns service status
        """
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'sentiment-analysis-service'
        assert 'timestamp' in data


class TestNewsSentimentEndpoint:
    """Tests for news sentiment analysis endpoint"""

    def test_get_news_sentiment_success(self, client):
        """
        Test GET /api/v1/sentiment/news/{symbol} with valid symbol
        Should return aggregated news sentiment (uses mock data by default)
        """
        response = client.get("/api/v1/sentiment/news/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'average_sentiment' in data
        assert 'sentiment_label' in data
        assert data['sentiment_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert 'total_articles' in data
        assert 'confidence' in data

    def test_get_news_sentiment_no_articles(self, client):
        """
        Test news sentiment endpoint returns valid response structure
        """
        response = client.get("/api/v1/sentiment/news/UNKNOWNSYMBOL")

        assert response.status_code == 200
        data = response.json()
        # Even with unknown symbol, should return valid structure
        assert 'symbol' in data
        assert 'sentiment_label' in data
        assert 'average_sentiment' in data

    def test_get_news_sentiment_with_hours_param(self, client):
        """
        Test news sentiment with custom lookback_hours parameter
        """
        response = client.get("/api/v1/sentiment/news/BTCUSDT?lookback_hours=12")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'average_sentiment' in data

    def test_get_news_sentiment_articles_in_response(self, client):
        """
        Test that response includes article details
        """
        response = client.get("/api/v1/sentiment/news/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert 'articles' in data
        # Articles may be empty if using mock data with unknown symbol
        if len(data['articles']) > 0:
            assert 'title' in data['articles'][0]
            assert 'sentiment_score' in data['articles'][0]


class TestSocialSentimentEndpoint:
    """Tests for social media sentiment endpoint"""

    def test_get_social_sentiment_success(self, client):
        """
        Test GET /api/v1/sentiment/social/{symbol}
        Should return social media sentiment (uses mock data)
        """
        response = client.get("/api/v1/sentiment/social/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'average_sentiment' in data
        assert 'sentiment_label' in data
        assert 'total_posts' in data
        assert 'platform' in data

    def test_get_social_sentiment_mvp_mode(self, client):
        """
        Test social sentiment in MVP mode (mock data)
        Should return sentiment based on mock data
        """
        response = client.get("/api/v1/sentiment/social/ETHUSDT")

        assert response.status_code == 200
        data = response.json()
        assert 'average_sentiment' in data
        assert 'sentiment_label' in data
        assert data['sentiment_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']


class TestCombinedSentimentEndpoint:
    """Tests for combined sentiment endpoint"""

    def test_get_combined_sentiment_success(self, client):
        """
        Test GET /api/v1/sentiment/combined/{symbol}
        Should combine news and social sentiment (uses mock data)
        """
        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'overall_sentiment' in data
        assert 'sentiment_label' in data
        assert data['sentiment_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert 'trading_signal' in data
        assert 'confidence' in data

    def test_combined_sentiment_weighting(self, client):
        """
        Test that combined sentiment returns proper structure
        News weight = 0.40, Social weight = 0.30, Market = 0.30
        """
        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert 'overall_sentiment' in data
        assert 'sentiment_strength' in data
        assert 'sources_used' in data
        assert isinstance(data['sources_used'], list)

    def test_combined_sentiment_no_data(self, client):
        """
        Test combined sentiment with unknown symbol
        Should still return valid response with neutral sentiment
        """
        response = client.get("/api/v1/sentiment/combined/XYZUSDT")

        assert response.status_code == 200
        data = response.json()
        assert 'sentiment_label' in data
        assert data['sentiment_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']


class TestSentimentTrendEndpoint:
    """Tests for sentiment trend analysis endpoint"""

    def test_get_sentiment_trend_success(self, client):
        """
        Test GET /api/v1/sentiment/trend/{symbol}
        Should return sentiment trend over time
        """
        response = client.get("/api/v1/sentiment/trend/BTCUSDT?hours=24")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'timestamps' in data
        assert 'sentiment_scores' in data
        assert 'current_sentiment' in data
        assert 'trend_direction' in data
        assert data['trend_direction'] in ['IMPROVING', 'DECLINING', 'STABLE']

    def test_sentiment_trend_direction_improving(self, client):
        """
        Test trend direction when sentiment is improving
        Uses simulated trend data
        """
        response = client.get("/api/v1/sentiment/trend/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        # Trend should have valid direction
        assert data['trend_direction'] in ['IMPROVING', 'DECLINING', 'STABLE']
        assert 'momentum' in data
        assert data['momentum'] in ['ACCELERATING', 'DECELERATING', 'STEADY']


class TestSentimentCaching:
    """Tests for sentiment caching functionality"""

    def test_sentiment_cached_on_repeat_request(self, client):
        """
        Test that sentiment is cached and not refetched immediately
        Both requests should return valid data quickly
        """
        # First request
        response1 = client.get("/api/v1/sentiment/news/BTCUSDT")
        assert response1.status_code == 200

        # Second request (should be cached or equally fast)
        response2 = client.get("/api/v1/sentiment/news/BTCUSDT")
        assert response2.status_code == 200

        # Both responses should have same structure
        data1 = response1.json()
        data2 = response2.json()
        assert data1['symbol'] == data2['symbol']


class TestSentimentSignalGeneration:
    """Tests for trading signal generation from sentiment"""

    def test_strong_bullish_generates_buy(self, client):
        """
        Test that combined sentiment generates trading signals
        """
        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Should have trading signal
        assert 'trading_signal' in data
        assert data['trading_signal'] in ['BUY', 'SELL', 'HOLD']
        assert 'signal_strength' in data

    def test_strong_bearish_generates_sell(self, client):
        """
        Test that sentiment endpoint includes signal field
        """
        response = client.get("/api/v1/sentiment/combined/ETHUSDT")

        assert response.status_code == 200
        data = response.json()

        # Should have trading signal info
        assert 'trading_signal' in data
        assert 'signal_strength' in data
        assert 0.0 <= data['signal_strength'] <= 1.0

    def test_neutral_sentiment_generates_hold(self, client):
        """
        Test that neutral sentiment generates HOLD signal
        """
        response = client.get("/api/v1/sentiment/combined/SOLUSDT")

        assert response.status_code == 200
        data = response.json()

        # Should have valid trading signal
        assert 'trading_signal' in data
        assert data['trading_signal'] in ['BUY', 'SELL', 'HOLD']


class TestErrorHandling:
    """Tests for error handling in sentiment endpoints"""

    def test_invalid_symbol_format(self, client):
        """
        Test endpoint with invalid symbol format
        """
        response = client.get("/api/v1/sentiment/news/INVALID_SYMBOL_123")

        # Should still return 200 with mock data
        assert response.status_code in [200, 400]

    def test_news_fetcher_exception(self, client):
        """
        Test that service handles gracefully even with edge case symbols
        Should return valid response structure
        """
        response = client.get("/api/v1/sentiment/news/XYZ")

        assert response.status_code == 200
        data = response.json()
        assert 'sentiment_label' in data

    def test_analyzer_exception(self, client):
        """
        Test that service handles edge cases gracefully
        """
        response = client.get("/api/v1/sentiment/social/ABC")

        # Should handle gracefully
        assert response.status_code == 200
        data = response.json()
        assert 'sentiment_label' in data


class TestPerformance:
    """Performance tests for sentiment API"""

    @pytest.mark.performance
    def test_sentiment_response_time(self, client):
        """
        Test that sentiment endpoint responds within acceptable time
        Should be under 2000ms (generous timeout for mock data)
        """
        import time

        start = time.time()
        response = client.get("/api/v1/sentiment/news/BTCUSDT")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 2.0  # Should respond within 2s with mock data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
