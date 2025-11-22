"""
Tests for Twitter Fetcher with Real API v2 Integration
Tests both real Twitter API and fallback to mock data
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from app.analyzers.twitter_fetcher import TwitterFetcher


@pytest.fixture
def twitter_fetcher_no_api():
    """
    Creates Twitter fetcher without bearer token (uses mock data)
    """
    return TwitterFetcher(bearer_token=None)


@pytest.fixture
def twitter_fetcher_with_api():
    """
    Creates Twitter fetcher with mocked Twitter API client
    """
    with patch('app.analyzers.twitter_fetcher.tweepy.Client') as mock_client:
        # Mock the Client constructor
        mock_instance = Mock()
        mock_client.return_value = mock_instance

        fetcher = TwitterFetcher(bearer_token="test_bearer_token")
        fetcher.client = mock_instance
        return fetcher


class TestTwitterFetcherInitialization:
    """Tests for Twitter fetcher initialization"""

    def test_init_without_bearer_token(self, twitter_fetcher_no_api):
        """
        Test initialization without bearer token uses mock data
        """
        assert twitter_fetcher_no_api.use_real_api is False
        assert twitter_fetcher_no_api.client is None
        assert twitter_fetcher_no_api.bearer_token is None

    def test_init_with_bearer_token(self, twitter_fetcher_with_api):
        """
        Test initialization with bearer token enables real API
        """
        assert twitter_fetcher_with_api.use_real_api is True
        assert twitter_fetcher_with_api.client is not None
        assert twitter_fetcher_with_api.bearer_token == "test_bearer_token"

    def test_cache_initialized(self, twitter_fetcher_no_api):
        """
        Test that cache is initialized on startup
        """
        assert twitter_fetcher_no_api.tweets_cache is not None
        assert len(twitter_fetcher_no_api.tweets_cache) == 0

    def test_api_call_counter_initialized(self, twitter_fetcher_no_api):
        """
        Test that API call counter starts at zero
        """
        assert twitter_fetcher_no_api.api_call_count == 0


class TestSymbolExtraction:
    """Tests for extracting base symbol from trading pairs"""

    def test_extract_btc_from_btcusdt(self, twitter_fetcher_no_api):
        """
        Test extracting BTC from BTCUSDT
        """
        result = twitter_fetcher_no_api._extract_base_symbol("BTCUSDT")
        assert result == "BTC"

    def test_extract_eth_from_ethusdt(self, twitter_fetcher_no_api):
        """
        Test extracting ETH from ETHUSDT
        """
        result = twitter_fetcher_no_api._extract_base_symbol("ETHUSDT")
        assert result == "ETH"

    def test_symbol_without_quote(self, twitter_fetcher_no_api):
        """
        Test symbol that doesn't have a quote currency
        """
        result = twitter_fetcher_no_api._extract_base_symbol("SOL")
        assert result == "SOL"


class TestSearchQueryBuilding:
    """Tests for building Twitter search queries"""

    def test_bitcoin_search_query(self, twitter_fetcher_no_api):
        """
        Test building search query for Bitcoin
        """
        query = twitter_fetcher_no_api._build_search_query("BTC")

        # Should include hashtags, cashtags, and keywords
        assert "#Bitcoin" in query or "Bitcoin" in query
        assert "OR" in query
        assert "-is:retweet" in query
        assert "lang:en" in query

    def test_ethereum_search_query(self, twitter_fetcher_no_api):
        """
        Test building search query for Ethereum
        """
        query = twitter_fetcher_no_api._build_search_query("ETH")

        assert "#Ethereum" in query or "Ethereum" in query
        assert "OR" in query
        assert "-is:retweet" in query

    def test_unknown_symbol_fallback(self, twitter_fetcher_no_api):
        """
        Test fallback search query for unknown symbol
        """
        query = twitter_fetcher_no_api._build_search_query("UNKNOWN")

        # Should still build valid query
        assert "UNKNOWN" in query
        assert "-is:retweet" in query
        assert "lang:en" in query


class TestMockTweetGeneration:
    """Tests for mock tweet generation (fallback mode)"""

    @pytest.mark.asyncio
    async def test_fetch_mock_tweets(self, twitter_fetcher_no_api):
        """
        Test fetching mock tweets
        """
        tweets = await twitter_fetcher_no_api.fetch_crypto_tweets(
            symbol="BTCUSDT",
            lookback_hours=24,
            max_tweets=50
        )

        assert len(tweets) > 0
        assert len(tweets) <= 50

        # Check tweet structure
        tweet = tweets[0]
        assert "text" in tweet
        assert "author" in tweet
        assert "created_at" in tweet
        assert "engagement_score" in tweet
        assert "likes" in tweet
        assert "retweets" in tweet

    @pytest.mark.asyncio
    async def test_mock_tweets_have_varied_sentiment(self, twitter_fetcher_no_api):
        """
        Test that mock tweets have varied sentiment
        """
        tweets = await twitter_fetcher_no_api.fetch_crypto_tweets(
            symbol="BTC",
            lookback_hours=24,
            max_tweets=20
        )

        # Extract sentiment biases
        biases = [t.get("_sentiment_bias", 0) for t in tweets]

        # Should have varied sentiment
        assert any(b > 0 for b in biases), "Should have positive sentiment tweets"
        assert any(b < 0 for b in biases), "Should have negative sentiment tweets"
        assert any(abs(b) < 0.2 for b in biases), "Should have neutral tweets"

    @pytest.mark.asyncio
    async def test_mock_tweets_have_engagement(self, twitter_fetcher_no_api):
        """
        Test that mock tweets have realistic engagement metrics
        """
        tweets = await twitter_fetcher_no_api.fetch_crypto_tweets(
            symbol="BTC",
            lookback_hours=24,
            max_tweets=10
        )

        for tweet in tweets:
            # Engagement metrics should be non-negative
            assert tweet["likes"] >= 0
            assert tweet["retweets"] >= 0
            assert tweet["replies"] >= 0
            assert tweet["engagement_score"] >= 0

            # Engagement score should be calculated correctly
            expected_score = tweet["likes"] + (tweet["retweets"] * 2) + (tweet["replies"] * 1.5)
            assert abs(tweet["engagement_score"] - expected_score) < 0.1


class TestRealAPIIntegration:
    """Tests for real Twitter API v2 integration (mocked)"""

    @pytest.mark.asyncio
    async def test_fetch_from_twitter_api_success(self, twitter_fetcher_with_api):
        """
        Test successful fetch from Twitter API
        """
        # Mock tweet objects
        mock_tweet1 = Mock()
        mock_tweet1.id = "123456789"
        mock_tweet1.text = "Bitcoin is going to the moon! #BTC 🚀"
        mock_tweet1.author_id = "user1"
        mock_tweet1.created_at = datetime.utcnow()
        mock_tweet1.public_metrics = {
            'like_count': 100,
            'retweet_count': 50,
            'reply_count': 20
        }

        mock_tweet2 = Mock()
        mock_tweet2.id = "987654321"
        mock_tweet2.text = "Bearish on Bitcoin short term #BTC"
        mock_tweet2.author_id = "user2"
        mock_tweet2.created_at = datetime.utcnow() - timedelta(hours=1)
        mock_tweet2.public_metrics = {
            'like_count': 80,
            'retweet_count': 30,
            'reply_count': 15
        }

        # Mock user objects
        mock_user1 = Mock()
        mock_user1.id = "user1"
        mock_user1.username = "crypto_whale"
        mock_user1.verified = True
        mock_user1.public_metrics = {'followers_count': 10000}

        mock_user2 = Mock()
        mock_user2.id = "user2"
        mock_user2.username = "trader_joe"
        mock_user2.verified = False
        mock_user2.public_metrics = {'followers_count': 5000}

        # Mock response
        mock_response = Mock()
        mock_response.data = [mock_tweet1, mock_tweet2]
        mock_response.includes = {'users': [mock_user1, mock_user2]}

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        # Fetch tweets
        tweets = await twitter_fetcher_with_api._fetch_from_twitter_api(
            search_query="#Bitcoin OR #BTC",
            lookback_hours=24,
            max_tweets=10
        )

        # Verify results
        assert len(tweets) == 2
        assert tweets[0]['text'] == "Bitcoin is going to the moon! #BTC 🚀"
        assert tweets[0]['author'] == "crypto_whale"
        assert tweets[0]['author_verified'] is True
        assert tweets[0]['likes'] == 100
        assert tweets[1]['text'] == "Bearish on Bitcoin short term #BTC"

        # Verify API was called
        assert twitter_fetcher_with_api.api_call_count == 1

    @pytest.mark.asyncio
    async def test_twitter_api_filters_low_follower_accounts(self, twitter_fetcher_with_api):
        """
        Test that tweets from accounts with very few followers are filtered
        """
        # Mock tweet from low-follower account
        mock_tweet = Mock()
        mock_tweet.id = "123"
        mock_tweet.text = "Spam tweet"
        mock_tweet.author_id = "spammer"
        mock_tweet.created_at = datetime.utcnow()
        mock_tweet.public_metrics = {'like_count': 1, 'retweet_count': 0, 'reply_count': 0}

        # Mock low-follower user
        mock_user = Mock()
        mock_user.id = "spammer"
        mock_user.username = "spam_bot"
        mock_user.verified = False
        mock_user.public_metrics = {'followers_count': 5}  # Below MIN_FOLLOWERS_COUNT

        mock_response = Mock()
        mock_response.data = [mock_tweet]
        mock_response.includes = {'users': [mock_user]}

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        tweets = await twitter_fetcher_with_api._fetch_from_twitter_api(
            search_query="Bitcoin",
            lookback_hours=24,
            max_tweets=10
        )

        # Should be filtered out
        assert len(tweets) == 0

    @pytest.mark.asyncio
    async def test_twitter_api_limits_tweets_per_user(self, twitter_fetcher_with_api):
        """
        Test that service limits tweets per user to avoid spam
        """
        # Create multiple tweets from same user
        mock_tweets = []
        for i in range(5):  # More than MAX_TWEETS_PER_USER
            tweet = Mock()
            tweet.id = f"tweet_{i}"
            tweet.text = f"Tweet number {i}"
            tweet.author_id = "prolific_user"
            tweet.created_at = datetime.utcnow()
            tweet.public_metrics = {'like_count': 10, 'retweet_count': 5, 'reply_count': 2}
            mock_tweets.append(tweet)

        # Mock user with good follower count
        mock_user = Mock()
        mock_user.id = "prolific_user"
        mock_user.username = "active_trader"
        mock_user.verified = False
        mock_user.public_metrics = {'followers_count': 1000}

        mock_response = Mock()
        mock_response.data = mock_tweets
        mock_response.includes = {'users': [mock_user]}

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        tweets = await twitter_fetcher_with_api._fetch_from_twitter_api(
            search_query="Bitcoin",
            lookback_hours=24,
            max_tweets=10
        )

        # Should be limited to MAX_TWEETS_PER_USER (3)
        assert len(tweets) <= 3

    @pytest.mark.asyncio
    async def test_twitter_api_no_tweets_found(self, twitter_fetcher_with_api):
        """
        Test handling when no tweets are found
        """
        mock_response = Mock()
        mock_response.data = None  # No tweets found

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        tweets = await twitter_fetcher_with_api._fetch_from_twitter_api(
            search_query="Bitcoin",
            lookback_hours=24,
            max_tweets=10
        )

        assert len(tweets) == 0

    @pytest.mark.asyncio
    async def test_twitter_api_error_handling(self, twitter_fetcher_with_api):
        """
        Test error handling when Twitter API raises exception
        """
        from tweepy.errors import TweepyException

        # Mock API to raise exception
        twitter_fetcher_with_api.client.search_recent_tweets.side_effect = TweepyException("Rate limit")

        # Should raise exception (will be caught by retry logic in real usage)
        with pytest.raises(TweepyException):
            await twitter_fetcher_with_api._fetch_from_twitter_api(
                search_query="Bitcoin",
                lookback_hours=24,
                max_tweets=10
            )


class TestEngagementCalculation:
    """Tests for engagement score calculation"""

    @pytest.mark.asyncio
    async def test_engagement_score_weighting(self, twitter_fetcher_no_api):
        """
        Test that engagement score correctly weights metrics
        """
        tweets = await twitter_fetcher_no_api.fetch_crypto_tweets("BTC", 24, 5)

        for tweet in tweets:
            likes = tweet["likes"]
            retweets = tweet["retweets"]
            replies = tweet["replies"]
            engagement = tweet["engagement_score"]

            # Verify formula: likes + (retweets * 2) + (replies * 1.5)
            expected = likes + (retweets * 2) + (replies * 1.5)
            assert abs(engagement - expected) < 0.1


class TestCaching:
    """Tests for caching mechanism"""

    @pytest.mark.asyncio
    async def test_cache_stores_results(self, twitter_fetcher_no_api):
        """
        Test that results are cached
        """
        # First fetch
        tweets1 = await twitter_fetcher_no_api.fetch_crypto_tweets("BTC", 24, 10)

        # Cache should now have one entry
        assert len(twitter_fetcher_no_api.tweets_cache) == 1

        # Second fetch (should use cache)
        tweets2 = await twitter_fetcher_no_api.fetch_crypto_tweets("BTC", 24, 10)

        # Results should be identical (from cache)
        assert tweets1 == tweets2

    @pytest.mark.asyncio
    async def test_cache_different_symbols(self, twitter_fetcher_no_api):
        """
        Test that different symbols have separate cache entries
        """
        # Fetch for BTC
        await twitter_fetcher_no_api.fetch_crypto_tweets("BTC", 24, 10)

        # Fetch for ETH
        await twitter_fetcher_no_api.fetch_crypto_tweets("ETH", 24, 10)

        # Should have two cache entries
        assert len(twitter_fetcher_no_api.tweets_cache) == 2

    def test_cache_key_generation(self, twitter_fetcher_no_api):
        """
        Test cache key generation
        """
        key = twitter_fetcher_no_api._get_cache_key("BTC", 24)

        assert "BTC" in key
        assert "24" in key
        assert isinstance(key, str)


class TestAPIStats:
    """Tests for API statistics tracking"""

    def test_get_api_stats(self, twitter_fetcher_no_api):
        """
        Test getting API usage statistics
        """
        stats = twitter_fetcher_no_api.get_api_stats()

        assert "api_enabled" in stats
        assert "total_api_calls" in stats
        assert "cache_size" in stats
        assert "cache_ttl_seconds" in stats

        assert stats["api_enabled"] is False
        assert stats["total_api_calls"] == 0

    @pytest.mark.asyncio
    async def test_api_call_counter_increments(self, twitter_fetcher_with_api):
        """
        Test that API call counter increments
        """
        # Mock successful response with no tweets
        mock_response = Mock()
        mock_response.data = None

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        initial_count = twitter_fetcher_with_api.api_call_count

        await twitter_fetcher_with_api._fetch_from_twitter_api("Bitcoin", 24, 10)

        assert twitter_fetcher_with_api.api_call_count == initial_count + 1


class TestFallbackBehavior:
    """Tests for fallback to mock data on API failure"""

    @pytest.mark.asyncio
    async def test_fallback_to_mock_on_api_error(self, twitter_fetcher_with_api):
        """
        Test that service falls back to mock data when API fails
        """
        from tweepy.errors import TweepyException

        # Mock API to raise exception
        twitter_fetcher_with_api.client.search_recent_tweets.side_effect = TweepyException("Error")

        # Should fall back to mock data (not raise exception)
        tweets = await twitter_fetcher_with_api.fetch_crypto_tweets("BTC", 24, 10)

        # Should return mock tweets
        assert len(tweets) > 0
        assert isinstance(tweets, list)

    @pytest.mark.asyncio
    async def test_uses_stale_cache_on_failure(self, twitter_fetcher_with_api):
        """
        Test that service uses stale cached data when API fails
        """
        # First, populate cache with successful fetch
        mock_tweet = Mock()
        mock_tweet.id = "123"
        mock_tweet.text = "Cached tweet"
        mock_tweet.author_id = "user1"
        mock_tweet.created_at = datetime.utcnow()
        mock_tweet.public_metrics = {'like_count': 10, 'retweet_count': 5, 'reply_count': 2}

        mock_user = Mock()
        mock_user.id = "user1"
        mock_user.username = "test_user"
        mock_user.verified = False
        mock_user.public_metrics = {'followers_count': 1000}

        mock_response = Mock()
        mock_response.data = [mock_tweet]
        mock_response.includes = {'users': [mock_user]}

        twitter_fetcher_with_api.client.search_recent_tweets.return_value = mock_response

        tweets1 = await twitter_fetcher_with_api.fetch_crypto_tweets("BTC", 24, 10)

        # Now make API fail
        from tweepy.errors import TweepyException
        twitter_fetcher_with_api.client.search_recent_tweets.side_effect = TweepyException("Rate limit")

        # Should try to use stale cache or fall back to mock
        tweets2 = await twitter_fetcher_with_api.fetch_crypto_tweets("BTC", 24, 10)

        # Should still get tweets
        assert len(tweets2) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
