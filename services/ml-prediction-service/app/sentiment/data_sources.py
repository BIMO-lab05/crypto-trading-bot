"""
Sentiment Data Sources - External API Integration
Fetches sentiment data from Twitter/X, News APIs, and Reddit

Features:
- Rate limiting and retry logic
- Caching to minimize API calls
- Graceful fallback on API failures
- Mock data generation for testing/development

Author: Phase 6.1 Implementation
Date: 2025-12-11
"""

import asyncio
import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass
class SentimentPost:
    """
    Single post/article with sentiment data

    Attributes:
        text: Post/article text content
        source: Source platform (twitter, reddit, news)
        timestamp: When the post was created
        sentiment_score: Pre-analyzed sentiment (-1 to 1)
        engagement: Engagement metrics (likes, retweets, etc.)
        author: Author username/name
        url: Link to original post
    """
    text: str
    source: str
    timestamp: datetime
    sentiment_score: float = 0.0
    engagement: float = 0.0
    author: Optional[str] = None
    url: Optional[str] = None


@dataclass
class SourceResult:
    """
    Result from a sentiment data source

    Attributes:
        source_name: Name of the data source
        posts: List of sentiment posts
        average_sentiment: Average sentiment score across posts
        weighted_sentiment: Engagement-weighted sentiment
        total_volume: Total number of posts/mentions
        timestamp: When the data was fetched
        is_cached: Whether data came from cache
        error: Error message if fetch failed
    """
    source_name: str
    posts: List[SentimentPost] = field(default_factory=list)
    average_sentiment: float = 0.0
    weighted_sentiment: float = 0.0
    total_volume: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_cached: bool = False
    error: Optional[str] = None


class SentimentDataSource(ABC):
    """
    Abstract base class for sentiment data sources

    All data sources must implement:
    - fetch_sentiment(): Async method to fetch sentiment data
    - get_cache_key(): Generate cache key for symbol
    - _analyze_text(): Basic sentiment analysis for text
    """

    def __init__(
        self,
        cache_ttl_seconds: int = 300,
        rate_limit_calls: int = 10,
        rate_limit_period: int = 60
    ):
        """
        Initialize data source

        Args:
            cache_ttl_seconds: Cache time-to-live in seconds (default: 5 minutes)
            rate_limit_calls: Max API calls per period
            rate_limit_period: Rate limit period in seconds
        """
        self.cache_ttl_seconds = cache_ttl_seconds
        self.rate_limit_calls = rate_limit_calls
        self.rate_limit_period = rate_limit_period

        # Internal cache (in-memory)
        self._cache: Dict[str, Tuple[SourceResult, datetime]] = {}

        # Rate limiting tracking
        self._call_timestamps: List[datetime] = []

        # HTTP client
        self._http_client: Optional[httpx.AsyncClient] = None

        # Sentiment keywords for basic analysis
        self._bullish_keywords = {
            'bullish', 'moon', 'buy', 'long', 'pump', 'surge', 'rally',
            'breakout', 'bullrun', 'hodl', 'accumulate', 'strong',
            'profit', 'gain', 'growth', 'adoption', 'partnership',
            'launch', 'upgrade', 'success', 'breakthrough', 'optimistic'
        }

        self._bearish_keywords = {
            'bearish', 'dump', 'sell', 'short', 'crash', 'drop', 'fall',
            'breakdown', 'weak', 'loss', 'risk', 'warning', 'scam',
            'fraud', 'hack', 'vulnerability', 'ban', 'regulation',
            'lawsuit', 'collapse', 'fear', 'panic', 'pessimistic'
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=10)
            )
        return self._http_client

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within rate limits

        Returns:
            True if we can make a call, False if rate limited
        """
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=self.rate_limit_period)

        # Remove old timestamps
        self._call_timestamps = [
            ts for ts in self._call_timestamps if ts > cutoff
        ]

        # Check if we can make a call
        return len(self._call_timestamps) < self.rate_limit_calls

    def _record_api_call(self):
        """Record an API call for rate limiting"""
        self._call_timestamps.append(datetime.utcnow())

    def _get_cached_result(self, cache_key: str) -> Optional[SourceResult]:
        """
        Get cached result if available and not expired

        Args:
            cache_key: Cache key to lookup

        Returns:
            Cached SourceResult or None if not found/expired
        """
        if cache_key in self._cache:
            result, cached_time = self._cache[cache_key]
            age = (datetime.utcnow() - cached_time).total_seconds()

            if age < self.cache_ttl_seconds:
                logger.debug(f"Cache HIT for {cache_key} (age: {age:.1f}s)")
                result.is_cached = True
                return result
            else:
                # Cache expired, remove it
                del self._cache[cache_key]

        return None

    def _cache_result(self, cache_key: str, result: SourceResult):
        """
        Cache a result

        Args:
            cache_key: Cache key
            result: Result to cache
        """
        self._cache[cache_key] = (result, datetime.utcnow())
        logger.debug(f"Cached result for {cache_key}")

    def _analyze_text(self, text: str) -> float:
        """
        Basic lexicon-based sentiment analysis

        Args:
            text: Text to analyze

        Returns:
            Sentiment score from -1 (bearish) to 1 (bullish)
        """
        if not text:
            return 0.0

        # Clean and lowercase
        text_lower = text.lower()

        # Remove URLs and mentions
        text_clean = re.sub(r'http\S+|www\S+|@\w+|#(\w+)', r'\1', text_lower)

        # Count keywords
        bullish_count = sum(
            1 for keyword in self._bullish_keywords if keyword in text_clean
        )
        bearish_count = sum(
            1 for keyword in self._bearish_keywords if keyword in text_clean
        )

        # Calculate sentiment
        total = bullish_count + bearish_count
        if total == 0:
            return 0.0

        return (bullish_count - bearish_count) / total

    def _get_symbol_keywords(self, symbol: str) -> List[str]:
        """
        Get search keywords for a trading symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)

        Returns:
            List of search keywords
        """
        # Remove USDT suffix to get base currency
        base = symbol.replace('USDT', '').replace('USD', '')

        # Common mappings
        keyword_map = {
            'BTC': ['bitcoin', 'btc', '$btc'],
            'ETH': ['ethereum', 'eth', '$eth'],
            'SOL': ['solana', 'sol', '$sol'],
            'XRP': ['ripple', 'xrp', '$xrp'],
            'ADA': ['cardano', 'ada', '$ada'],
            'DOGE': ['dogecoin', 'doge', '$doge'],
            'DOT': ['polkadot', 'dot', '$dot'],
            'LINK': ['chainlink', 'link', '$link'],
            'AVAX': ['avalanche', 'avax', '$avax'],
            'MATIC': ['polygon', 'matic', '$matic'],
            'ARB': ['arbitrum', 'arb', '$arb'],
            'OP': ['optimism', 'op', '$op'],
            'SUI': ['sui', '$sui'],
            'APT': ['aptos', 'apt', '$apt'],
        }

        return keyword_map.get(base, [base.lower(), f'${base.lower()}'])

    @abstractmethod
    async def fetch_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> SourceResult:
        """
        Fetch sentiment data for a symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            lookback_hours: Hours of data to fetch

        Returns:
            SourceResult with sentiment data
        """
        pass

    @abstractmethod
    def get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """
        Generate cache key for symbol

        Args:
            symbol: Trading pair
            lookback_hours: Hours of lookback

        Returns:
            Cache key string
        """
        pass


class TwitterSentimentSource(SentimentDataSource):
    """
    Twitter/X sentiment data source

    Uses Twitter API v2 (requires Bearer Token) or falls back to mock data

    Features:
    - Search recent tweets by crypto keywords
    - Engagement-weighted sentiment
    - Handles rate limiting gracefully
    """

    def __init__(
        self,
        bearer_token: Optional[str] = None,
        cache_ttl_seconds: int = 300
    ):
        """
        Initialize Twitter sentiment source

        Args:
            bearer_token: Twitter API Bearer Token (optional)
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

        self.bearer_token = bearer_token or os.environ.get('TWITTER_BEARER_TOKEN')
        self.api_enabled = bool(self.bearer_token)

        if not self.api_enabled:
            logger.warning("Twitter API not configured - using mock data")

    def get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """Generate cache key"""
        return f"twitter:{symbol}:{lookback_hours}"

    async def fetch_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> SourceResult:
        """
        Fetch Twitter sentiment for symbol

        Args:
            symbol: Trading pair
            lookback_hours: Hours of tweets to analyze

        Returns:
            SourceResult with Twitter sentiment
        """
        cache_key = self.get_cache_key(symbol, lookback_hours)

        # Check cache first
        cached = self._get_cached_result(cache_key)
        if cached:
            return cached

        try:
            if self.api_enabled and self._check_rate_limit():
                # Use real API
                result = await self._fetch_from_api(symbol, lookback_hours)
            else:
                # Use mock data
                result = self._generate_mock_data(symbol, lookback_hours)

            # Cache the result
            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching Twitter sentiment: {e}")
            return SourceResult(
                source_name="twitter",
                error=str(e)
            )

    async def _fetch_from_api(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """
        Fetch from Twitter API v2

        Note: Requires elevated access for search_recent_tweets endpoint
        """
        self._record_api_call()

        client = await self._get_http_client()
        keywords = self._get_symbol_keywords(symbol)
        query = ' OR '.join(keywords) + ' -is:retweet lang:en'

        # Calculate start time
        start_time = datetime.utcnow() - timedelta(hours=lookback_hours)

        headers = {
            'Authorization': f'Bearer {self.bearer_token}',
            'Content-Type': 'application/json'
        }

        params = {
            'query': query,
            'max_results': 100,
            'start_time': start_time.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'tweet.fields': 'created_at,public_metrics,author_id',
        }

        try:
            response = await client.get(
                'https://api.twitter.com/2/tweets/search/recent',
                headers=headers,
                params=params
            )

            if response.status_code == 429:
                logger.warning("Twitter rate limited - using mock data")
                return self._generate_mock_data(symbol, lookback_hours)

            response.raise_for_status()
            data = response.json()

            posts = []
            tweets = data.get('data', [])

            for tweet in tweets:
                # Calculate engagement
                metrics = tweet.get('public_metrics', {})
                engagement = (
                    metrics.get('like_count', 0) +
                    metrics.get('retweet_count', 0) * 2 +
                    metrics.get('reply_count', 0) * 0.5
                )

                # Analyze sentiment
                sentiment = self._analyze_text(tweet.get('text', ''))

                posts.append(SentimentPost(
                    text=tweet.get('text', ''),
                    source='twitter',
                    timestamp=datetime.fromisoformat(
                        tweet.get('created_at', '').replace('Z', '+00:00')
                    ),
                    sentiment_score=sentiment,
                    engagement=engagement,
                    author=tweet.get('author_id')
                ))

            return self._aggregate_posts(posts, 'twitter')

        except httpx.HTTPStatusError as e:
            logger.error(f"Twitter API error: {e}")
            return self._generate_mock_data(symbol, lookback_hours)

    def _generate_mock_data(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """
        Generate realistic mock Twitter data

        Uses deterministic randomness based on symbol for consistency
        """
        # Use symbol hash for deterministic "randomness"
        seed = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)

        # Generate mock posts
        posts = []
        num_posts = 50 + (seed % 100)  # 50-150 posts

        base_sentiment = ((seed % 200) - 100) / 100  # -1 to 1

        for i in range(num_posts):
            # Vary sentiment around base
            variation = ((i * seed) % 50 - 25) / 100
            sentiment = max(-1, min(1, base_sentiment + variation))

            # Generate engagement (higher for earlier posts)
            engagement = max(1, 100 - i + (seed % 50))

            posts.append(SentimentPost(
                text=f"Mock tweet about {symbol} #{i}",
                source='twitter',
                timestamp=datetime.utcnow() - timedelta(hours=i * lookback_hours / num_posts),
                sentiment_score=sentiment,
                engagement=engagement
            ))

        return self._aggregate_posts(posts, 'twitter')

    def _aggregate_posts(
        self,
        posts: List[SentimentPost],
        source_name: str
    ) -> SourceResult:
        """Aggregate posts into a single result"""
        if not posts:
            return SourceResult(source_name=source_name)

        # Calculate average sentiment
        avg_sentiment = sum(p.sentiment_score for p in posts) / len(posts)

        # Calculate engagement-weighted sentiment
        total_engagement = sum(p.engagement for p in posts)
        if total_engagement > 0:
            weighted_sentiment = sum(
                p.sentiment_score * p.engagement for p in posts
            ) / total_engagement
        else:
            weighted_sentiment = avg_sentiment

        return SourceResult(
            source_name=source_name,
            posts=posts,
            average_sentiment=round(avg_sentiment, 4),
            weighted_sentiment=round(weighted_sentiment, 4),
            total_volume=len(posts),
            timestamp=datetime.utcnow()
        )


class NewsSentimentSource(SentimentDataSource):
    """
    News sentiment data source

    Uses NewsAPI or CryptoCompare News API for crypto news sentiment
    Falls back to mock data if API not configured
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_ttl_seconds: int = 600  # 10 minutes for news
    ):
        """
        Initialize news sentiment source

        Args:
            api_key: NewsAPI or CryptoCompare API key
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

        self.api_key = api_key or os.environ.get('NEWS_API_KEY')
        self.api_enabled = bool(self.api_key)

        # CryptoCompare news is free
        self.cryptocompare_enabled = True

        if not self.api_enabled:
            logger.warning("NewsAPI not configured - using CryptoCompare/mock data")

    def get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """Generate cache key"""
        return f"news:{symbol}:{lookback_hours}"

    async def fetch_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> SourceResult:
        """
        Fetch news sentiment for symbol

        Args:
            symbol: Trading pair
            lookback_hours: Hours of news to analyze

        Returns:
            SourceResult with news sentiment
        """
        cache_key = self.get_cache_key(symbol, lookback_hours)

        # Check cache first
        cached = self._get_cached_result(cache_key)
        if cached:
            return cached

        try:
            # Try CryptoCompare first (free API)
            if self._check_rate_limit():
                result = await self._fetch_from_cryptocompare(symbol, lookback_hours)
                if not result.error:
                    self._cache_result(cache_key, result)
                    return result

            # Fall back to mock data
            result = self._generate_mock_data(symbol, lookback_hours)
            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching news sentiment: {e}")
            return SourceResult(
                source_name="news",
                error=str(e)
            )

    async def _fetch_from_cryptocompare(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """Fetch from CryptoCompare news API (free)"""
        self._record_api_call()

        client = await self._get_http_client()

        # Get base currency
        base = symbol.replace('USDT', '').replace('USD', '')

        params = {
            'categories': base,
            'excludeCategories': 'Sponsored',
            'lang': 'EN'
        }

        try:
            response = await client.get(
                'https://min-api.cryptocompare.com/data/v2/news/',
                params=params
            )
            response.raise_for_status()
            data = response.json()

            posts = []
            articles = data.get('Data', [])[:50]  # Limit to 50 articles

            cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)

            for article in articles:
                # Parse timestamp
                published = datetime.fromtimestamp(article.get('published_on', 0))

                if published < cutoff_time:
                    continue

                # Combine title and body for sentiment
                text = f"{article.get('title', '')} {article.get('body', '')[:200]}"
                sentiment = self._analyze_text(text)

                posts.append(SentimentPost(
                    text=article.get('title', ''),
                    source='news',
                    timestamp=published,
                    sentiment_score=sentiment,
                    engagement=1.0,  # News doesn't have engagement metrics
                    author=article.get('source_info', {}).get('name'),
                    url=article.get('url')
                ))

            return self._aggregate_posts(posts, 'news')

        except Exception as e:
            logger.error(f"CryptoCompare API error: {e}")
            return SourceResult(
                source_name="news",
                error=str(e)
            )

    def _generate_mock_data(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """Generate realistic mock news data"""
        seed = int(hashlib.md5(f"news_{symbol}".encode()).hexdigest()[:8], 16)

        posts = []
        num_articles = 10 + (seed % 20)  # 10-30 articles

        base_sentiment = ((seed % 200) - 100) / 100

        for i in range(num_articles):
            variation = ((i * seed) % 30 - 15) / 100
            sentiment = max(-1, min(1, base_sentiment + variation))

            posts.append(SentimentPost(
                text=f"Mock news article about {symbol} #{i}",
                source='news',
                timestamp=datetime.utcnow() - timedelta(hours=i * lookback_hours / num_articles),
                sentiment_score=sentiment,
                engagement=1.0
            ))

        return self._aggregate_posts(posts, 'news')

    def _aggregate_posts(
        self,
        posts: List[SentimentPost],
        source_name: str
    ) -> SourceResult:
        """Aggregate posts into a single result"""
        if not posts:
            return SourceResult(source_name=source_name)

        avg_sentiment = sum(p.sentiment_score for p in posts) / len(posts)

        return SourceResult(
            source_name=source_name,
            posts=posts,
            average_sentiment=round(avg_sentiment, 4),
            weighted_sentiment=round(avg_sentiment, 4),  # News is equally weighted
            total_volume=len(posts),
            timestamp=datetime.utcnow()
        )


class RedditSentimentSource(SentimentDataSource):
    """
    Reddit sentiment data source

    Monitors r/cryptocurrency, r/bitcoin, and asset-specific subreddits
    Uses Reddit API with OAuth2 or falls back to mock data
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        cache_ttl_seconds: int = 300
    ):
        """
        Initialize Reddit sentiment source

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            cache_ttl_seconds: Cache TTL
        """
        super().__init__(cache_ttl_seconds=cache_ttl_seconds)

        self.client_id = client_id or os.environ.get('REDDIT_CLIENT_ID')
        self.client_secret = client_secret or os.environ.get('REDDIT_CLIENT_SECRET')
        self.api_enabled = bool(self.client_id and self.client_secret)

        # Subreddit mappings
        self._subreddit_map = {
            'BTC': ['bitcoin', 'cryptocurrency', 'CryptoMarkets'],
            'ETH': ['ethereum', 'cryptocurrency', 'ethtrader'],
            'SOL': ['solana', 'cryptocurrency'],
            'XRP': ['ripple', 'cryptocurrency'],
            'DOGE': ['dogecoin', 'cryptocurrency'],
            'ADA': ['cardano', 'cryptocurrency'],
        }

        self._default_subreddits = ['cryptocurrency', 'CryptoMarkets']

        if not self.api_enabled:
            logger.warning("Reddit API not configured - using mock data")

    def get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """Generate cache key"""
        return f"reddit:{symbol}:{lookback_hours}"

    async def fetch_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> SourceResult:
        """
        Fetch Reddit sentiment for symbol

        Args:
            symbol: Trading pair
            lookback_hours: Hours of posts to analyze

        Returns:
            SourceResult with Reddit sentiment
        """
        cache_key = self.get_cache_key(symbol, lookback_hours)

        # Check cache first
        cached = self._get_cached_result(cache_key)
        if cached:
            return cached

        try:
            if self.api_enabled and self._check_rate_limit():
                result = await self._fetch_from_api(symbol, lookback_hours)
            else:
                result = self._generate_mock_data(symbol, lookback_hours)

            self._cache_result(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error fetching Reddit sentiment: {e}")
            return SourceResult(
                source_name="reddit",
                error=str(e)
            )

    async def _fetch_from_api(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """Fetch from Reddit API"""
        self._record_api_call()

        client = await self._get_http_client()

        # Get OAuth token first
        auth_data = {
            'grant_type': 'client_credentials'
        }

        try:
            auth_response = await client.post(
                'https://www.reddit.com/api/v1/access_token',
                auth=(self.client_id, self.client_secret),
                data=auth_data,
                headers={'User-Agent': 'CryptoTradingBot/1.0'}
            )
            auth_response.raise_for_status()
            token = auth_response.json().get('access_token')

            if not token:
                return self._generate_mock_data(symbol, lookback_hours)

            # Get subreddits for this symbol
            base = symbol.replace('USDT', '').replace('USD', '')
            subreddits = self._subreddit_map.get(base, self._default_subreddits)

            posts = []
            headers = {
                'Authorization': f'Bearer {token}',
                'User-Agent': 'CryptoTradingBot/1.0'
            }

            for subreddit in subreddits[:2]:  # Limit to 2 subreddits
                response = await client.get(
                    f'https://oauth.reddit.com/r/{subreddit}/hot',
                    headers=headers,
                    params={'limit': 25}
                )

                if response.status_code != 200:
                    continue

                data = response.json()

                for post_data in data.get('data', {}).get('children', []):
                    post = post_data.get('data', {})

                    # Calculate engagement (upvotes + comments)
                    engagement = post.get('score', 0) + post.get('num_comments', 0) * 2

                    # Analyze sentiment
                    text = f"{post.get('title', '')} {post.get('selftext', '')[:200]}"
                    sentiment = self._analyze_text(text)

                    posts.append(SentimentPost(
                        text=post.get('title', ''),
                        source='reddit',
                        timestamp=datetime.fromtimestamp(post.get('created_utc', 0)),
                        sentiment_score=sentiment,
                        engagement=engagement,
                        author=post.get('author'),
                        url=f"https://reddit.com{post.get('permalink', '')}"
                    ))

            return self._aggregate_posts(posts, 'reddit')

        except Exception as e:
            logger.error(f"Reddit API error: {e}")
            return self._generate_mock_data(symbol, lookback_hours)

    def _generate_mock_data(
        self,
        symbol: str,
        lookback_hours: int
    ) -> SourceResult:
        """Generate realistic mock Reddit data"""
        seed = int(hashlib.md5(f"reddit_{symbol}".encode()).hexdigest()[:8], 16)

        posts = []
        num_posts = 30 + (seed % 50)  # 30-80 posts

        base_sentiment = ((seed % 200) - 100) / 100

        for i in range(num_posts):
            variation = ((i * seed) % 40 - 20) / 100
            sentiment = max(-1, min(1, base_sentiment + variation))

            # Reddit has high variance in engagement
            engagement = max(1, (seed % 1000) - i * 10)

            posts.append(SentimentPost(
                text=f"Mock Reddit post about {symbol} #{i}",
                source='reddit',
                timestamp=datetime.utcnow() - timedelta(hours=i * lookback_hours / num_posts),
                sentiment_score=sentiment,
                engagement=engagement
            ))

        return self._aggregate_posts(posts, 'reddit')

    def _aggregate_posts(
        self,
        posts: List[SentimentPost],
        source_name: str
    ) -> SourceResult:
        """Aggregate posts into a single result"""
        if not posts:
            return SourceResult(source_name=source_name)

        avg_sentiment = sum(p.sentiment_score for p in posts) / len(posts)

        total_engagement = sum(p.engagement for p in posts)
        if total_engagement > 0:
            weighted_sentiment = sum(
                p.sentiment_score * p.engagement for p in posts
            ) / total_engagement
        else:
            weighted_sentiment = avg_sentiment

        return SourceResult(
            source_name=source_name,
            posts=posts,
            average_sentiment=round(avg_sentiment, 4),
            weighted_sentiment=round(weighted_sentiment, 4),
            total_volume=len(posts),
            timestamp=datetime.utcnow()
        )
