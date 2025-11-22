"""
Twitter Fetcher with Real Twitter API v2 Integration
Fetches cryptocurrency tweets for sentiment analysis
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import tweepy
from tweepy.errors import TweepyException
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class TwitterFetcher:
    """
    Fetch cryptocurrency tweets from Twitter API v2

    Features:
    - Recent tweets search using Twitter API v2
    - Filtering by crypto symbols and hashtags
    - Engagement metrics (likes, retweets) for weighted sentiment
    - In-memory caching with TTL to respect rate limits
    - Exponential backoff for rate limit handling
    - Fallback to cached data on API errors
    """

    # Twitter API v2 rate limits (per 15-minute window):
    # - Recent search: 450 requests for Essential access, 180 for free
    # - Cache tweets for 10 minutes to minimize API calls
    CACHE_TTL_SECONDS = 600  # 10 minutes
    MAX_CACHE_SIZE = 100  # Store up to 100 different symbol queries

    # Crypto symbol hashtags and keywords for better search
    SYMBOL_SEARCH_TERMS = {
        'BTC': ['#Bitcoin', '#BTC', '$BTC', 'Bitcoin'],
        'ETH': ['#Ethereum', '#ETH', '$ETH', 'Ethereum'],
        'SOL': ['#Solana', '#SOL', '$SOL', 'Solana'],
        'BNB': ['#BNB', '$BNB', 'Binance Coin'],
        'XRP': ['#XRP', '$XRP', 'Ripple'],
        'ADA': ['#Cardano', '#ADA', '$ADA', 'Cardano'],
        'DOGE': ['#Dogecoin', '#DOGE', '$DOGE', 'Dogecoin'],
        'MATIC': ['#Polygon', '#MATIC', '$MATIC', 'Polygon'],
        'DOT': ['#Polkadot', '#DOT', '$DOT', 'Polkadot'],
        'AVAX': ['#Avalanche', '#AVAX', '$AVAX', 'Avalanche']
    }

    # Filter out bot-like behavior
    MIN_FOLLOWERS_COUNT = 10  # Exclude accounts with very few followers
    MAX_TWEETS_PER_USER = 3  # Limit tweets from single user to avoid spam

    def __init__(self, bearer_token: Optional[str] = None):
        """
        Initialize Twitter fetcher with API v2 client

        Args:
            bearer_token: Twitter API v2 Bearer Token
                         Get from https://developer.twitter.com/
        """
        self.bearer_token = bearer_token
        self.client = None
        self.use_real_api = False

        # Initialize Twitter client if bearer token provided
        if bearer_token and bearer_token.strip():
            try:
                # Twitter API v2 client using bearer token authentication
                self.client = tweepy.Client(
                    bearer_token=bearer_token,
                    wait_on_rate_limit=True  # Auto-wait when rate limited
                )
                self.use_real_api = True
                logger.info("Twitter API v2 client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize Twitter client: {e}. Using mock data.")
                self.use_real_api = False
        else:
            logger.info("No Twitter bearer token provided. Using mock data for tweets.")

        # Initialize cache for API responses
        self.tweets_cache: TTLCache = TTLCache(
            maxsize=self.MAX_CACHE_SIZE,
            ttl=self.CACHE_TTL_SECONDS
        )

        # Track API usage for rate limit monitoring
        self.api_call_count = 0
        self.last_reset = datetime.utcnow()

    def _get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """
        Generate cache key for a tweets query

        Args:
            symbol: Crypto symbol
            lookback_hours: Hours to look back

        Returns:
            Cache key string
        """
        # Round to nearest 10 minutes to improve cache hit rate
        now = datetime.utcnow()
        rounded_time = now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0)
        return f"{symbol}_{lookback_hours}_{rounded_time.isoformat()}"

    def _extract_base_symbol(self, symbol: str) -> str:
        """
        Extract base cryptocurrency from trading pair

        Examples:
            BTCUSDT -> BTC
            ETHUSDT -> ETH
        """
        # Remove common quote currencies
        for quote in ['USDT', 'USDC', 'BUSD', 'USD', 'BTC', 'ETH']:
            if symbol.endswith(quote):
                return symbol[:-len(quote)]
        return symbol

    def _build_search_query(self, base_symbol: str) -> str:
        """
        Build Twitter search query for a crypto symbol

        Twitter search syntax:
        - OR: Matches any of the terms
        - -is:retweet: Excludes retweets to avoid duplicates
        - lang:en: English only

        Args:
            base_symbol: Base crypto symbol (BTC, ETH, etc.)

        Returns:
            Twitter search query string
        """
        if base_symbol in self.SYMBOL_SEARCH_TERMS:
            terms = self.SYMBOL_SEARCH_TERMS[base_symbol]
            # Build query: (#Bitcoin OR #BTC OR $BTC OR Bitcoin) -is:retweet lang:en
            terms_query = ' OR '.join(terms)
            query = f"({terms_query}) -is:retweet lang:en"
        else:
            # Fallback for unknown symbols
            query = f"({base_symbol} OR #{base_symbol} OR ${base_symbol}) -is:retweet lang:en"

        return query

    @retry(
        stop=stop_after_attempt(3),  # Retry up to 3 times
        wait=wait_exponential(multiplier=2, min=4, max=30),  # 4s, 8s, 16s
        retry=retry_if_exception_type(TweepyException),  # Only retry on API errors
        reraise=True
    )
    async def _fetch_from_twitter_api(
        self,
        search_query: str,
        lookback_hours: int,
        max_tweets: int
    ) -> List[Dict]:
        """
        Fetch tweets from Twitter API v2 with retry logic

        Uses tenacity for exponential backoff on failures and rate limits

        Args:
            search_query: Twitter search query
            lookback_hours: How far back to search
            max_tweets: Maximum tweets to return

        Returns:
            List of tweet dictionaries

        Raises:
            TweepyException: If API call fails after retries
        """
        # Calculate start time for tweets
        start_time = datetime.utcnow() - timedelta(hours=lookback_hours)

        # Track API call
        self.api_call_count += 1
        logger.info(f"Twitter API call #{self.api_call_count}: query='{search_query[:50]}...', since={start_time}")

        try:
            # Search recent tweets using Twitter API v2
            # Tweet fields: public metrics (likes, retweets), created_at, author_id
            # User fields: username, verified, public metrics (followers)
            # Expansions: author_id to get user data
            tweets_response = self.client.search_recent_tweets(
                query=search_query,
                start_time=start_time,
                max_results=min(max_tweets, 100),  # Max 100 per request
                tweet_fields=['created_at', 'public_metrics', 'author_id', 'lang'],
                user_fields=['username', 'verified', 'public_metrics'],
                expansions=['author_id']
            )

            # Check if tweets were found
            if not tweets_response.data:
                logger.info(f"No tweets found for query: {search_query[:50]}")
                return []

            # Build user lookup dictionary from includes
            users_dict = {}
            if tweets_response.includes and 'users' in tweets_response.includes:
                for user in tweets_response.includes['users']:
                    users_dict[user.id] = user

            # Process tweets
            processed_tweets = []
            user_tweet_count = {}  # Track tweets per user to filter spam

            for tweet in tweets_response.data:
                # Get tweet author
                author = users_dict.get(tweet.author_id)
                if not author:
                    continue  # Skip if author data missing

                # Filter out accounts with very few followers (likely bots/spam)
                follower_count = author.public_metrics.get('followers_count', 0)
                if follower_count < self.MIN_FOLLOWERS_COUNT:
                    continue

                # Limit tweets per user to avoid spam
                user_tweet_count[tweet.author_id] = user_tweet_count.get(tweet.author_id, 0) + 1
                if user_tweet_count[tweet.author_id] > self.MAX_TWEETS_PER_USER:
                    continue

                # Extract engagement metrics
                public_metrics = tweet.public_metrics or {}
                likes = public_metrics.get('like_count', 0)
                retweets = public_metrics.get('retweet_count', 0)
                replies = public_metrics.get('reply_count', 0)

                # Calculate total engagement score
                # Weight: likes=1, retweets=2 (higher reach), replies=1.5 (high engagement)
                engagement_score = likes + (retweets * 2) + (replies * 1.5)

                processed_tweet = {
                    'text': tweet.text,
                    'author': author.username,
                    'author_verified': author.verified or False,
                    'author_followers': follower_count,
                    'created_at': tweet.created_at,
                    'likes': likes,
                    'retweets': retweets,
                    'replies': replies,
                    'engagement_score': engagement_score,
                    'tweet_id': tweet.id,
                    'url': f"https://twitter.com/{author.username}/status/{tweet.id}"
                }
                processed_tweets.append(processed_tweet)

            logger.info(f"Twitter API returned {len(processed_tweets)} tweets (filtered from {len(tweets_response.data)})")
            return processed_tweets

        except TweepyException as e:
            # Twitter API specific errors (rate limit, auth, etc.)
            # Rate limit: 429 status code
            # Auth error: 401 status code
            logger.error(f"Twitter API exception: {e}")
            raise  # Will trigger retry via tenacity

        except Exception as e:
            # Unexpected errors
            logger.error(f"Unexpected error fetching from Twitter: {e}", exc_info=True)
            return []

    async def fetch_crypto_tweets(
        self,
        symbol: str,
        lookback_hours: int = 24,
        max_tweets: int = 100
    ) -> List[Dict]:
        """
        Fetch tweets about a cryptocurrency with caching

        Primary method for fetching tweets. Uses cache when available,
        falls back to mock data if API fails.

        Args:
            symbol: Crypto symbol (e.g., BTCUSDT -> BTC)
            lookback_hours: How far back to look for tweets
            max_tweets: Maximum number of tweets to return

        Returns:
            List of tweets with text, author, engagement metrics, created_at
        """
        # Extract base symbol (BTC from BTCUSDT)
        base_symbol = self._extract_base_symbol(symbol)

        # Check cache first
        cache_key = self._get_cache_key(base_symbol, lookback_hours)
        if cache_key in self.tweets_cache:
            logger.info(f"Returning cached tweets for {base_symbol}")
            return self.tweets_cache[cache_key]

        tweets = []

        # Try fetching from real Twitter API if configured
        if self.use_real_api and self.client:
            try:
                search_query = self._build_search_query(base_symbol)
                tweets = await self._fetch_from_twitter_api(
                    search_query=search_query,
                    lookback_hours=lookback_hours,
                    max_tweets=max_tweets
                )

                # Cache successful results
                if tweets:
                    self.tweets_cache[cache_key] = tweets
                    logger.info(f"Cached {len(tweets)} tweets for {base_symbol}")

            except TweepyException as e:
                logger.error(f"Twitter API failed after retries: {e}")
                # Try to return stale cached data if available
                for key in list(self.tweets_cache.keys()):
                    if key.startswith(f"{base_symbol}_"):
                        logger.warning(f"Using stale cached tweets for {base_symbol}")
                        return self.tweets_cache[key]
                # Fall through to mock data

            except Exception as e:
                logger.error(f"Unexpected error fetching tweets: {e}", exc_info=True)
                # Fall through to mock data

        # Fallback to mock data if API not configured or failed
        if not tweets:
            logger.info(f"Using mock tweet data for {base_symbol}")
            tweets = self._generate_mock_tweets(base_symbol, lookback_hours, max_tweets)
            # Cache mock data
            if tweets:
                self.tweets_cache[cache_key] = tweets

        return tweets

    def _generate_mock_tweets(
        self,
        symbol: str,
        lookback_hours: int,
        max_tweets: int
    ) -> List[Dict]:
        """
        Generate realistic mock tweets for testing

        Used when:
        1. No API token is configured
        2. API rate limit exceeded
        3. API is temporarily unavailable

        Maintains consistent format with real API responses
        """
        now = datetime.utcnow()

        # Get crypto name for better mock tweets
        crypto_name = self.SYMBOL_SEARCH_TERMS.get(symbol, [symbol])[0].lstrip('#$')

        # Mock tweet templates with varied sentiment
        tweet_templates = [
            {
                "text": f"{crypto_name} looking bullish! Breaking resistance levels. #crypto #trading",
                "sentiment_bias": 0.8,
                "engagement": 150
            },
            {
                "text": f"Just bought more ${symbol}. Long term holder here! 💎🙌",
                "sentiment_bias": 0.9,
                "engagement": 80
            },
            {
                "text": f"{crypto_name} price action is weak today. Might see a pullback soon.",
                "sentiment_bias": -0.6,
                "engagement": 45
            },
            {
                "text": f"Analysts predicting {crypto_name} could reach new ATH this cycle 🚀",
                "sentiment_bias": 0.7,
                "engagement": 200
            },
            {
                "text": f"Sold my ${symbol} position. Taking profits before potential correction.",
                "sentiment_bias": -0.5,
                "engagement": 60
            },
            {
                "text": f"{crypto_name} consolidating. Waiting for clear direction before entry.",
                "sentiment_bias": 0.0,
                "engagement": 30
            },
            {
                "text": f"Big whale just moved 10,000 ${symbol} to exchange. Watch out! 👀",
                "sentiment_bias": -0.4,
                "engagement": 120
            },
            {
                "text": f"#{crypto_name} network upgrades looking promising. Bullish for long term.",
                "sentiment_bias": 0.6,
                "engagement": 95
            },
            {
                "text": f"Why is ${symbol} pumping? Did I miss some news? Anyone know?",
                "sentiment_bias": 0.3,
                "engagement": 50
            },
            {
                "text": f"Technical analysis: {crypto_name} forming bullish pattern on 4H chart 📈",
                "sentiment_bias": 0.7,
                "engagement": 110
            },
            {
                "text": f"Be careful with ${symbol} right now. High volatility expected.",
                "sentiment_bias": -0.3,
                "engagement": 70
            },
            {
                "text": f"Institutional interest in {crypto_name} is growing. Bullish indicator!",
                "sentiment_bias": 0.8,
                "engagement": 180
            }
        ]

        # Generate tweets distributed over lookback period
        tweets = []
        for i in range(min(max_tweets, len(tweet_templates) * 3)):
            template = tweet_templates[i % len(tweet_templates)]

            # Distribute tweets over time period
            hours_ago = (i * lookback_hours / max_tweets)
            created_at = now - timedelta(hours=hours_ago)

            # Vary engagement around template value
            import random
            base_engagement = template["engagement"]
            engagement_variation = random.uniform(0.7, 1.3)
            likes = int(base_engagement * engagement_variation * 0.6)
            retweets = int(base_engagement * engagement_variation * 0.2)
            replies = int(base_engagement * engagement_variation * 0.2)
            engagement_score = likes + (retweets * 2) + (replies * 1.5)

            tweet = {
                "text": template["text"],
                "author": f"crypto_trader_{i}",
                "author_verified": i % 5 == 0,  # 20% verified accounts
                "author_followers": random.randint(100, 50000),
                "created_at": created_at,
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "engagement_score": engagement_score,
                "tweet_id": f"mock_{symbol}_{i}",
                "url": f"https://twitter.com/crypto_trader_{i}/status/mock_{i}",
                "_sentiment_bias": template["sentiment_bias"]  # For testing
            }

            tweets.append(tweet)

        return tweets

    def get_api_stats(self) -> Dict:
        """
        Get API usage statistics

        Useful for monitoring rate limits and cache effectiveness

        Returns:
            Dictionary with API call count, cache stats, etc.
        """
        return {
            "api_enabled": self.use_real_api,
            "total_api_calls": self.api_call_count,
            "cache_size": len(self.tweets_cache),
            "cache_maxsize": self.tweets_cache.maxsize,
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "session_start": self.last_reset.isoformat()
        }
