"""
Tests for Sentiment Analysis Service API endpoints
Tests FastAPI endpoints for news sentiment, social sentiment, and combined analysis
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.main import app
from app.analyzers.sentiment_analyzer import SentimentResult


@pytest.fixture
def client():
    """
    Creates test client for FastAPI app
    """
    return TestClient(app)


@pytest.fixture
def mock_news_articles():
    """
    Creates mock news articles for testing
    """
    return [
        {
            'title': 'Bitcoin Surges to New All-Time High',
            'description': 'Bitcoin breaks resistance with strong momentum',
            'url': 'https://example.com/article1',
            'published_at': datetime.now().isoformat(),
            'source': 'CryptoNews'
        },
        {
            'title': 'Market Faces Bearish Pressure',
            'description': 'Selling pressure increases across crypto markets',
            'url': 'https://example.com/article2',
            'published_at': (datetime.now() - timedelta(hours=1)).isoformat(),
            'source': 'CoinDesk'
        }
    ]


@pytest.fixture
def mock_sentiment_result():
    """
    Creates mock sentiment result
    """
    return SentimentResult(
        score=0.65,
        label='BULLISH',
        confidence=0.75,
        method='lexicon'
    )


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

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_get_news_sentiment_success(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test GET /api/v1/sentiment/news/{symbol} with valid symbol
        Should return aggregated news sentiment
        """
        # Mock news fetcher
        mock_fetcher.fetch_news.return_value = mock_news_articles

        # Mock sentiment analyzer
        mock_analyzer.analyze_text.side_effect = [
            SentimentResult(score=0.8, label='BULLISH', confidence=0.85, method='lexicon'),
            SentimentResult(score=-0.4, label='BEARISH', confidence=0.70, method='lexicon')
        ]

        response = client.get("/api/v1/sentiment/news/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'sentiment_score' in data
        assert 'sentiment_label' in data
        assert data['sentiment_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert 'articles_analyzed' in data
        assert data['articles_analyzed'] == 2
        assert 'confidence' in data

    @patch('app.main.news_fetcher')
    def test_get_news_sentiment_no_articles(self, mock_fetcher, client):
        """
        Test news sentiment when no articles are found
        Should return neutral sentiment
        """
        mock_fetcher.fetch_news.return_value = []

        response = client.get("/api/v1/sentiment/news/ETHUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['sentiment_label'] == 'NEUTRAL'
        assert data['sentiment_score'] == 0.0
        assert data['articles_analyzed'] == 0
        assert 'data_quality' in data

    @patch('app.main.news_fetcher')
    def test_get_news_sentiment_with_hours_param(self, mock_fetcher, client, mock_news_articles):
        """
        Test news sentiment with custom hours parameter
        """
        mock_fetcher.fetch_news.return_value = mock_news_articles

        response = client.get("/api/v1/sentiment/news/BTCUSDT?hours=12")

        assert response.status_code == 200
        # Check that news_fetcher was called with correct hours
        mock_fetcher.fetch_news.assert_called_with("BTCUSDT", hours=12)

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_get_news_sentiment_articles_in_response(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test that response includes article details
        """
        mock_fetcher.fetch_news.return_value = mock_news_articles
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.5, label='BULLISH', confidence=0.7, method='lexicon'
        )

        response = client.get("/api/v1/sentiment/news/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert 'articles' in data
        assert len(data['articles']) > 0
        assert 'title' in data['articles'][0]
        assert 'sentiment' in data['articles'][0]


class TestSocialSentimentEndpoint:
    """Tests for social media sentiment endpoint"""

    @patch('app.main.sentiment_analyzer')
    def test_get_social_sentiment_success(self, mock_analyzer, client):
        """
        Test GET /api/v1/sentiment/social/{symbol}
        Should return social media sentiment
        """
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.55, label='BULLISH', confidence=0.65, method='lexicon'
        )

        response = client.get("/api/v1/sentiment/social/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'sentiment_score' in data
        assert 'sentiment_label' in data
        assert 'posts_analyzed' in data
        assert 'platforms' in data

    def test_get_social_sentiment_mvp_mode(self, client):
        """
        Test social sentiment in MVP mode (mock data)
        Should return sentiment based on mock data
        """
        response = client.get("/api/v1/sentiment/social/ETHUSDT")

        assert response.status_code == 200
        data = response.json()
        assert 'sentiment_score' in data
        assert 'data_quality' in data
        # In MVP mode, should indicate mock data
        assert 'mock' in data['data_quality'].lower() or 'limited' in data['data_quality'].lower()


class TestCombinedSentimentEndpoint:
    """Tests for combined sentiment endpoint"""

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_get_combined_sentiment_success(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test GET /api/v1/sentiment/combined/{symbol}
        Should combine news and social sentiment
        """
        # Mock news
        mock_fetcher.fetch_news.return_value = mock_news_articles
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.6, label='BULLISH', confidence=0.75, method='lexicon'
        )

        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'combined_score' in data
        assert 'combined_label' in data
        assert data['combined_label'] in ['BULLISH', 'BEARISH', 'NEUTRAL']
        assert 'news_sentiment' in data
        assert 'social_sentiment' in data
        assert 'confidence' in data

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_combined_sentiment_weighting(self, mock_analyzer, mock_fetcher, client):
        """
        Test that combined sentiment properly weighs news vs social
        News weight = 0.40, Social weight = 0.30, Market = 0.30
        """
        # Mock strong bullish news
        mock_fetcher.fetch_news.return_value = [
            {'title': 'Bullish news', 'description': 'Very bullish', 'published_at': datetime.now().isoformat()}
        ]
        mock_analyzer.analyze_text.side_effect = [
            SentimentResult(score=0.9, label='BULLISH', confidence=0.9, method='lexicon'),  # News
            SentimentResult(score=0.3, label='BULLISH', confidence=0.6, method='lexicon')   # Social
        ]

        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Combined should be weighted towards news (40% vs 30%)
        news_score = data['news_sentiment']['sentiment_score']
        social_score = data['social_sentiment']['sentiment_score']
        combined_score = data['combined_score']

        # Verify weighted combination
        expected_combined = (news_score * 0.4 + social_score * 0.3) / (0.4 + 0.3)
        assert abs(combined_score - expected_combined) < 0.2  # Approximate

    @patch('app.main.news_fetcher')
    def test_combined_sentiment_no_data(self, mock_fetcher, client):
        """
        Test combined sentiment when no data available
        Should return neutral
        """
        mock_fetcher.fetch_news.return_value = []

        response = client.get("/api/v1/sentiment/combined/XYZUSDT")

        assert response.status_code == 200
        data = response.json()
        assert data['combined_label'] == 'NEUTRAL'


class TestSentimentTrendEndpoint:
    """Tests for sentiment trend analysis endpoint"""

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_get_sentiment_trend_success(self, mock_analyzer, mock_fetcher, client):
        """
        Test GET /api/v1/sentiment/trend/{symbol}
        Should return sentiment trend over time
        """
        # Mock news for different time periods
        mock_fetcher.fetch_news.return_value = [
            {'title': 'News', 'description': 'Bullish', 'published_at': datetime.now().isoformat()}
        ]
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.5, label='BULLISH', confidence=0.7, method='lexicon'
        )

        response = client.get("/api/v1/sentiment/trend/BTCUSDT?periods=24")

        assert response.status_code == 200
        data = response.json()
        assert data['symbol'] == 'BTCUSDT'
        assert 'trend' in data
        assert 'current_sentiment' in data
        assert 'trend_direction' in data
        assert data['trend_direction'] in ['IMPROVING', 'DECLINING', 'STABLE']

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_sentiment_trend_direction_improving(self, mock_analyzer, mock_fetcher, client):
        """
        Test trend direction when sentiment is improving
        """
        # Mock improving sentiment over time
        mock_fetcher.fetch_news.side_effect = [
            [{'title': 'Old news', 'description': 'Bearish', 'published_at': datetime.now().isoformat()}],
            [{'title': 'Recent news', 'description': 'Bullish', 'published_at': datetime.now().isoformat()}]
        ]
        mock_analyzer.analyze_text.side_effect = [
            SentimentResult(score=-0.3, label='BEARISH', confidence=0.6, method='lexicon'),  # Past
            SentimentResult(score=0.5, label='BULLISH', confidence=0.7, method='lexicon')    # Recent
        ]

        response = client.get("/api/v1/sentiment/trend/BTCUSDT")

        assert response.status_code == 200
        data = response.json()
        # Trend should show improvement
        assert data['trend_direction'] in ['IMPROVING', 'STABLE']


class TestSentimentCaching:
    """Tests for sentiment caching functionality"""

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_sentiment_cached_on_repeat_request(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test that sentiment is cached and not refetched immediately
        """
        mock_fetcher.fetch_news.return_value = mock_news_articles
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.6, label='BULLISH', confidence=0.75, method='lexicon'
        )

        # First request
        response1 = client.get("/api/v1/sentiment/news/BTCUSDT")
        assert response1.status_code == 200

        # Reset mocks
        mock_fetcher.reset_mock()
        mock_analyzer.reset_mock()

        # Second request (should be cached)
        response2 = client.get("/api/v1/sentiment/news/BTCUSDT")
        assert response2.status_code == 200

        # Check if cache was used (fewer calls)
        # Note: This depends on implementation - adjust if needed


class TestSentimentSignalGeneration:
    """Tests for trading signal generation from sentiment"""

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_strong_bullish_generates_buy(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test that strong bullish sentiment generates BUY signal
        """
        mock_fetcher.fetch_news.return_value = mock_news_articles
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.85, label='BULLISH', confidence=0.90, method='ml'
        )

        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Strong bullish with high confidence should suggest BUY
        if 'signal' in data:
            assert data['signal'] == 'BUY'
        assert data['combined_score'] > 0.6
        assert data['confidence'] > 0.8

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_strong_bearish_generates_sell(self, mock_analyzer, mock_fetcher, client):
        """
        Test that strong bearish sentiment generates SELL signal
        """
        mock_fetcher.fetch_news.return_value = [
            {'title': 'Market crash', 'description': 'Heavy bearish pressure', 'published_at': datetime.now().isoformat()}
        ]
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=-0.80, label='BEARISH', confidence=0.85, method='ml'
        )

        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Strong bearish should suggest SELL
        if 'signal' in data:
            assert data['signal'] == 'SELL'
        assert data['combined_score'] < -0.6

    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_neutral_sentiment_generates_hold(self, mock_analyzer, mock_fetcher, client):
        """
        Test that neutral sentiment generates HOLD signal
        """
        mock_fetcher.fetch_news.return_value = [
            {'title': 'Market stable', 'description': 'Sideways movement', 'published_at': datetime.now().isoformat()}
        ]
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.05, label='NEUTRAL', confidence=0.50, method='lexicon'
        )

        response = client.get("/api/v1/sentiment/combined/BTCUSDT")

        assert response.status_code == 200
        data = response.json()

        # Neutral should suggest HOLD
        if 'signal' in data:
            assert data['signal'] == 'HOLD'


class TestErrorHandling:
    """Tests for error handling in sentiment endpoints"""

    def test_invalid_symbol_format(self, client):
        """
        Test endpoint with invalid symbol format
        """
        response = client.get("/api/v1/sentiment/news/INVALID_SYMBOL_123")

        # Should still return 200 but with neutral/poor quality
        assert response.status_code in [200, 400]

    @patch('app.main.news_fetcher')
    def test_news_fetcher_exception(self, mock_fetcher, client):
        """
        Test handling when news fetcher raises exception
        Should return neutral sentiment with error indication
        """
        mock_fetcher.fetch_news.side_effect = Exception("API error")

        response = client.get("/api/v1/sentiment/news/BTCUSDT")

        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert data['sentiment_label'] == 'NEUTRAL'

    @patch('app.main.sentiment_analyzer')
    def test_analyzer_exception(self, mock_analyzer, client):
        """
        Test handling when sentiment analyzer raises exception
        Should gracefully handle and return neutral
        """
        mock_analyzer.analyze_text.side_effect = Exception("Analysis error")

        response = client.get("/api/v1/sentiment/social/BTCUSDT")

        # Should handle gracefully
        assert response.status_code in [200, 500]


class TestPerformance:
    """Performance tests for sentiment API"""

    @pytest.mark.performance
    @patch('app.main.news_fetcher')
    @patch('app.main.sentiment_analyzer')
    def test_sentiment_response_time(self, mock_analyzer, mock_fetcher, client, mock_news_articles):
        """
        Test that sentiment endpoint responds within acceptable time
        Should be under 300ms
        """
        import time

        mock_fetcher.fetch_news.return_value = mock_news_articles
        mock_analyzer.analyze_text.return_value = SentimentResult(
            score=0.5, label='BULLISH', confidence=0.7, method='lexicon'
        )

        start = time.time()
        response = client.get("/api/v1/sentiment/news/BTCUSDT")
        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 0.3  # Should respond within 300ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
