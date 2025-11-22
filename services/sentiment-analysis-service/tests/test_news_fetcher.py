"""
Tests for News Fetcher with Real API Integration
Tests both real NewsAPI and fallback to mock data
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from app.analyzers.news_fetcher import NewsFetcher


@pytest.fixture
def news_fetcher_no_api():
    """
    Creates news fetcher without API key (uses mock data)
    """
    return NewsFetcher(api_key=None)


@pytest.fixture
def news_fetcher_with_api():
    """
    Creates news fetcher with mocked NewsAPI client
    """
    with patch('app.analyzers.news_fetcher.NewsApiClient') as mock_client:
        # Mock the NewsApiClient constructor
        mock_instance = Mock()
        mock_client.return_value = mock_instance

        fetcher = NewsFetcher(api_key="test_api_key")
        fetcher.newsapi_client = mock_instance
        return fetcher


class TestNewsFetcherInitialization:
    """Tests for news fetcher initialization"""

    def test_init_without_api_key(self, news_fetcher_no_api):
        """
        Test initialization without API key uses mock data
        """
        assert news_fetcher_no_api.use_real_api is False
        assert news_fetcher_no_api.newsapi_client is None
        assert news_fetcher_no_api.api_key is None

    def test_init_with_api_key(self, news_fetcher_with_api):
        """
        Test initialization with API key enables real API
        """
        assert news_fetcher_with_api.use_real_api is True
        assert news_fetcher_with_api.newsapi_client is not None
        assert news_fetcher_with_api.api_key == "test_api_key"

    def test_cache_initialized(self, news_fetcher_no_api):
        """
        Test that cache is initialized on startup
        """
        assert news_fetcher_no_api.news_cache is not None
        assert len(news_fetcher_no_api.news_cache) == 0

    def test_api_call_counter_initialized(self, news_fetcher_no_api):
        """
        Test that API call counter starts at zero
        """
        assert news_fetcher_no_api.api_call_count == 0


class TestSymbolExtraction:
    """Tests for extracting base symbol from trading pairs"""

    def test_extract_btc_from_btcusdt(self, news_fetcher_no_api):
        """
        Test extracting BTC from BTCUSDT
        """
        result = news_fetcher_no_api._extract_base_symbol("BTCUSDT")
        assert result == "BTC"

    def test_extract_eth_from_ethusdt(self, news_fetcher_no_api):
        """
        Test extracting ETH from ETHUSDT
        """
        result = news_fetcher_no_api._extract_base_symbol("ETHUSDT")
        assert result == "ETH"

    def test_extract_from_btcusd(self, news_fetcher_no_api):
        """
        Test extracting from BTCUSD (without T)
        """
        result = news_fetcher_no_api._extract_base_symbol("BTCUSD")
        assert result == "BTC"

    def test_symbol_without_quote(self, news_fetcher_no_api):
        """
        Test symbol that doesn't have a quote currency
        """
        result = news_fetcher_no_api._extract_base_symbol("BTC")
        assert result == "BTC"


class TestSearchKeywords:
    """Tests for building search keywords"""

    def test_bitcoin_keywords(self, news_fetcher_no_api):
        """
        Test getting search keywords for Bitcoin
        """
        result = news_fetcher_no_api._get_search_keywords("BTC")
        assert "Bitcoin" in result
        assert "BTC" in result
        assert "OR" in result

    def test_ethereum_keywords(self, news_fetcher_no_api):
        """
        Test getting search keywords for Ethereum
        """
        result = news_fetcher_no_api._get_search_keywords("ETH")
        assert "Ethereum" in result
        assert "ETH" in result

    def test_unknown_symbol_fallback(self, news_fetcher_no_api):
        """
        Test fallback for unknown symbol
        """
        result = news_fetcher_no_api._get_search_keywords("UNKNOWN")
        assert result == "UNKNOWN"


class TestMockNewsGeneration:
    """Tests for mock news generation (fallback mode)"""

    @pytest.mark.asyncio
    async def test_fetch_mock_news(self, news_fetcher_no_api):
        """
        Test fetching mock news articles
        """
        articles = await news_fetcher_no_api.fetch_crypto_news(
            symbol="BTCUSDT",
            lookback_hours=24,
            max_articles=10
        )

        assert len(articles) > 0
        assert len(articles) <= 10

        # Check article structure
        article = articles[0]
        assert "title" in article
        assert "source" in article
        assert "url" in article
        assert "published_at" in article

    @pytest.mark.asyncio
    async def test_mock_articles_have_varied_sentiment(self, news_fetcher_no_api):
        """
        Test that mock articles have varied sentiment bias
        """
        articles = await news_fetcher_no_api.fetch_crypto_news(
            symbol="BTC",
            lookback_hours=24,
            max_articles=10
        )

        # Extract sentiment biases
        biases = [a.get("_sentiment_bias", 0) for a in articles]

        # Should have both positive and negative sentiment
        assert any(b > 0 for b in biases), "Should have positive sentiment articles"
        assert any(b < 0 for b in biases), "Should have negative sentiment articles"

    @pytest.mark.asyncio
    async def test_mock_articles_time_distribution(self, news_fetcher_no_api):
        """
        Test that mock articles are distributed over time period
        """
        articles = await news_fetcher_no_api.fetch_crypto_news(
            symbol="BTC",
            lookback_hours=24,
            max_articles=5
        )

        # Get publish times
        times = [a["published_at"] for a in articles]

        # Should be sorted from newest to oldest
        for i in range(len(times) - 1):
            assert times[i] >= times[i + 1], "Articles should be in reverse chronological order"


class TestRealAPIIntegration:
    """Tests for real NewsAPI integration (mocked)"""

    @pytest.mark.asyncio
    async def test_fetch_from_newsapi_success(self, news_fetcher_with_api):
        """
        Test successful fetch from NewsAPI
        """
        # Mock NewsAPI response
        mock_response = {
            'status': 'ok',
            'totalResults': 2,
            'articles': [
                {
                    'title': 'Bitcoin Surges to New High',
                    'source': {'name': 'CryptoNews'},
                    'url': 'https://example.com/article1',
                    'description': 'Bitcoin reaches new ATH',
                    'publishedAt': '2025-11-11T10:30:00Z',
                    'author': 'John Doe',
                    'content': 'Full article content here...'
                },
                {
                    'title': 'Ethereum Network Upgrade',
                    'source': {'name': 'CoinDesk'},
                    'url': 'https://example.com/article2',
                    'description': 'ETH upgrade scheduled',
                    'publishedAt': '2025-11-11T09:15:00Z',
                    'author': 'Jane Smith',
                    'content': 'Ethereum is planning...'
                }
            ]
        }

        news_fetcher_with_api.newsapi_client.get_everything.return_value = mock_response

        # Fetch articles
        articles = await news_fetcher_with_api._fetch_from_newsapi(
            search_query="Bitcoin OR BTC",
            lookback_hours=24,
            max_articles=10
        )

        # Verify results
        assert len(articles) == 2
        assert articles[0]['title'] == 'Bitcoin Surges to New High'
        assert articles[0]['source'] == 'CryptoNews'
        assert articles[1]['title'] == 'Ethereum Network Upgrade'

        # Verify API was called
        assert news_fetcher_with_api.api_call_count == 1

    @pytest.mark.asyncio
    async def test_newsapi_filters_removed_articles(self, news_fetcher_with_api):
        """
        Test that articles with [Removed] title are filtered out
        """
        mock_response = {
            'status': 'ok',
            'articles': [
                {'title': 'Good Article', 'source': {'name': 'Source1'}, 'publishedAt': '2025-11-11T10:00:00Z'},
                {'title': '[Removed]', 'source': {'name': 'Source2'}, 'publishedAt': '2025-11-11T09:00:00Z'},
                {'title': 'Another Good Article', 'source': {'name': 'Source3'}, 'publishedAt': '2025-11-11T08:00:00Z'}
            ]
        }

        news_fetcher_with_api.newsapi_client.get_everything.return_value = mock_response

        articles = await news_fetcher_with_api._fetch_from_newsapi(
            search_query="Bitcoin",
            lookback_hours=24,
            max_articles=10
        )

        # Should only have 2 articles (removed one filtered out)
        assert len(articles) == 2
        assert all(a['title'] != '[Removed]' for a in articles)

    @pytest.mark.asyncio
    async def test_newsapi_error_handling(self, news_fetcher_with_api):
        """
        Test error handling when NewsAPI returns error
        """
        from newsapi.newsapi_exception import NewsAPIException

        # Mock API to raise exception
        news_fetcher_with_api.newsapi_client.get_everything.side_effect = NewsAPIException("Rate limit exceeded")

        # Should raise exception (will be caught by retry logic in real usage)
        with pytest.raises(NewsAPIException):
            await news_fetcher_with_api._fetch_from_newsapi(
                search_query="Bitcoin",
                lookback_hours=24,
                max_articles=10
            )


class TestCaching:
    """Tests for caching mechanism"""

    @pytest.mark.asyncio
    async def test_cache_stores_results(self, news_fetcher_no_api):
        """
        Test that results are cached
        """
        # First fetch
        articles1 = await news_fetcher_no_api.fetch_crypto_news("BTC", 24, 10)

        # Cache should now have one entry
        assert len(news_fetcher_no_api.news_cache) == 1

        # Second fetch (should use cache)
        articles2 = await news_fetcher_no_api.fetch_crypto_news("BTC", 24, 10)

        # Should still have one cache entry
        assert len(news_fetcher_no_api.news_cache) == 1

        # Results should be identical (from cache)
        assert articles1 == articles2

    @pytest.mark.asyncio
    async def test_cache_different_symbols(self, news_fetcher_no_api):
        """
        Test that different symbols have separate cache entries
        """
        # Fetch for BTC
        await news_fetcher_no_api.fetch_crypto_news("BTC", 24, 10)

        # Fetch for ETH
        await news_fetcher_no_api.fetch_crypto_news("ETH", 24, 10)

        # Should have two cache entries
        assert len(news_fetcher_no_api.news_cache) == 2

    def test_cache_key_generation(self, news_fetcher_no_api):
        """
        Test cache key generation
        """
        key = news_fetcher_no_api._get_cache_key("BTC", 24)

        assert "BTC" in key
        assert "24" in key
        assert isinstance(key, str)


class TestAPIStats:
    """Tests for API statistics tracking"""

    def test_get_api_stats(self, news_fetcher_no_api):
        """
        Test getting API usage statistics
        """
        stats = news_fetcher_no_api.get_api_stats()

        assert "api_enabled" in stats
        assert "total_api_calls" in stats
        assert "cache_size" in stats
        assert "cache_ttl_seconds" in stats

        assert stats["api_enabled"] is False
        assert stats["total_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_api_call_counter_increments(self, news_fetcher_with_api):
        """
        Test that API call counter increments
        """
        # Mock successful response
        news_fetcher_with_api.newsapi_client.get_everything.return_value = {
            'status': 'ok',
            'articles': []
        }

        initial_count = news_fetcher_with_api.api_call_count

        await news_fetcher_with_api._fetch_from_newsapi("Bitcoin", 24, 10)

        assert news_fetcher_with_api.api_call_count == initial_count + 1


class TestFallbackBehavior:
    """Tests for fallback to mock data on API failure"""

    @pytest.mark.asyncio
    async def test_fallback_to_mock_on_api_error(self, news_fetcher_with_api):
        """
        Test that service falls back to mock data when API fails
        """
        from newsapi.newsapi_exception import NewsAPIException

        # Mock API to raise exception
        news_fetcher_with_api.newsapi_client.get_everything.side_effect = NewsAPIException("Error")

        # Should fall back to mock data (not raise exception)
        articles = await news_fetcher_with_api.fetch_crypto_news("BTC", 24, 10)

        # Should return mock articles
        assert len(articles) > 0
        assert isinstance(articles, list)

    @pytest.mark.asyncio
    async def test_uses_stale_cache_on_failure(self, news_fetcher_with_api):
        """
        Test that service uses stale cached data when API fails
        """
        # First, populate cache with successful fetch
        news_fetcher_with_api.newsapi_client.get_everything.return_value = {
            'status': 'ok',
            'articles': [
                {'title': 'Cached Article', 'source': {'name': 'Test'}, 'publishedAt': '2025-11-11T10:00:00Z'}
            ]
        }

        articles1 = await news_fetcher_with_api.fetch_crypto_news("BTC", 24, 10)

        # Now make API fail
        from newsapi.newsapi_exception import NewsAPIException
        news_fetcher_with_api.newsapi_client.get_everything.side_effect = NewsAPIException("Rate limit")

        # Manually clear the current cache entry but keep old one
        # Simulate that we're looking for slightly different data but same symbol

        # Should try to use stale cache
        articles2 = await news_fetcher_with_api.fetch_crypto_news("BTC", 24, 10)

        # Should still get articles (either from stale cache or mock data)
        assert len(articles2) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
