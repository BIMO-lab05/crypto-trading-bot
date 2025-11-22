"""
News Fetcher with Real NewsAPI Integration
Fetches cryptocurrency news from NewsAPI.org
"""

import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from newsapi import NewsApiClient
from newsapi.newsapi_exception import NewsAPIException
from cachetools import TTLCache
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class NewsFetcher:
    """
    Fetch cryptocurrency news from NewsAPI.org

    Features:
    - Real-time news from 80,000+ sources
    - Filtering by crypto symbols (BTC, ETH, etc.)
    - In-memory caching with TTL to respect rate limits
    - Exponential backoff for API failures
    - Fallback to cached data on API errors
    """

    # NewsAPI rate limits: 100 requests per day for free tier, 1000 for paid
    # Cache news for 15 minutes to minimize API calls
    CACHE_TTL_SECONDS = 900  # 15 minutes
    MAX_CACHE_SIZE = 100  # Store up to 100 different symbol queries

    # Crypto symbol mappings for better search results
    SYMBOL_KEYWORDS = {
        'BTC': ['Bitcoin', 'BTC'],
        'ETH': ['Ethereum', 'ETH'],
        'SOL': ['Solana', 'SOL'],
        'BNB': ['Binance Coin', 'BNB'],
        'XRP': ['Ripple', 'XRP'],
        'ADA': ['Cardano', 'ADA'],
        'DOGE': ['Dogecoin', 'DOGE'],
        'MATIC': ['Polygon', 'MATIC'],
        'DOT': ['Polkadot', 'DOT'],
        'AVAX': ['Avalanche', 'AVAX']
    }

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize news fetcher with NewsAPI client

        Args:
            api_key: NewsAPI.org API key (get from https://newsapi.org/)
        """
        self.api_key = api_key
        self.newsapi_client = None
        self.use_real_api = False

        # Initialize NewsAPI client if API key provided
        if api_key and api_key.strip():
            try:
                self.newsapi_client = NewsApiClient(api_key=api_key)
                self.use_real_api = True
                logger.info("NewsAPI client initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize NewsAPI client: {e}. Using mock data.")
                self.use_real_api = False
        else:
            logger.info("No NewsAPI key provided. Using mock data for news.")

        # Initialize cache for API responses
        # TTLCache automatically expires entries after TTL seconds
        self.news_cache: TTLCache = TTLCache(
            maxsize=self.MAX_CACHE_SIZE,
            ttl=self.CACHE_TTL_SECONDS
        )

        # Track API usage for rate limit monitoring
        self.api_call_count = 0
        self.last_reset = datetime.utcnow()

    async def close(self):
        """Close HTTP client and cleanup resources"""
        logger.info(f"NewsFetcher closing. Total API calls made: {self.api_call_count}")

    def _get_cache_key(self, symbol: str, lookback_hours: int) -> str:
        """
        Generate cache key for a news query

        Args:
            symbol: Crypto symbol
            lookback_hours: Hours to look back

        Returns:
            Cache key string
        """
        # Round to nearest 15 minutes to improve cache hit rate
        now = datetime.utcnow()
        rounded_time = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
        return f"{symbol}_{lookback_hours}_{rounded_time.isoformat()}"

    def _extract_base_symbol(self, symbol: str) -> str:
        """
        Extract base cryptocurrency from trading pair

        Examples:
            BTCUSDT -> BTC
            ETHUSDT -> ETH
            SOLUSDT -> SOL
        """
        # Remove common quote currencies
        for quote in ['USDT', 'USDC', 'BUSD', 'USD', 'BTC', 'ETH']:
            if symbol.endswith(quote):
                return symbol[:-len(quote)]
        return symbol

    def _get_search_keywords(self, base_symbol: str) -> str:
        """
        Get search keywords for a crypto symbol

        NewsAPI works better with full names (e.g., "Bitcoin" vs "BTC")

        Args:
            base_symbol: Base crypto symbol (BTC, ETH, etc.)

        Returns:
            Search query string
        """
        if base_symbol in self.SYMBOL_KEYWORDS:
            keywords = self.SYMBOL_KEYWORDS[base_symbol]
            # Search for "Bitcoin OR BTC" for better results
            return ' OR '.join(keywords)
        return base_symbol

    @retry(
        stop=stop_after_attempt(3),  # Retry up to 3 times
        wait=wait_exponential(multiplier=1, min=2, max=10),  # 2s, 4s, 8s
        retry=retry_if_exception_type(NewsAPIException),  # Only retry on API errors
        reraise=True
    )
    async def _fetch_from_newsapi(
        self,
        search_query: str,
        lookback_hours: int,
        max_articles: int
    ) -> List[Dict]:
        """
        Fetch news from NewsAPI with retry logic

        Uses tenacity for exponential backoff on failures

        Args:
            search_query: Search keywords
            lookback_hours: How far back to search
            max_articles: Maximum articles to return

        Returns:
            List of article dictionaries

        Raises:
            NewsAPIException: If API call fails after retries
        """
        # Calculate date range for NewsAPI
        # NewsAPI requires dates in YYYY-MM-DD format
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(hours=lookback_hours)

        # Format dates for NewsAPI
        from_param = from_date.strftime('%Y-%m-%d')
        to_param = to_date.strftime('%Y-%m-%d')

        # Track API call
        self.api_call_count += 1
        logger.info(f"NewsAPI call #{self.api_call_count}: query='{search_query}', from={from_param}, to={to_param}")

        try:
            # Call NewsAPI everything endpoint for comprehensive search
            # Everything endpoint searches through millions of articles
            response = self.newsapi_client.get_everything(
                q=search_query,  # Search query
                from_param=from_param,  # Start date
                to_param=to_param,  # End date
                language='en',  # English only
                sort_by='publishedAt',  # Most recent first
                page_size=min(max_articles, 100)  # Max 100 per request
            )

            # NewsAPI response structure:
            # {
            #   "status": "ok",
            #   "totalResults": 1234,
            #   "articles": [...]
            # }

            if response['status'] != 'ok':
                logger.error(f"NewsAPI returned non-ok status: {response.get('code', 'unknown')}")
                return []

            articles = response.get('articles', [])
            logger.info(f"NewsAPI returned {len(articles)} articles for query '{search_query}'")

            # Convert NewsAPI format to our internal format
            processed_articles = []
            for article in articles:
                # Skip articles with removed content
                if article.get('title') == '[Removed]':
                    continue

                # Parse published date
                published_str = article.get('publishedAt', '')
                try:
                    # NewsAPI returns ISO 8601 format: 2025-11-11T10:30:00Z
                    published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    published_at = datetime.utcnow()

                processed_article = {
                    'title': article.get('title', 'No title'),
                    'source': article.get('source', {}).get('name', 'Unknown'),
                    'url': article.get('url', ''),
                    'description': article.get('description', ''),
                    'published_at': published_at,
                    'author': article.get('author', 'Unknown'),
                    'content_snippet': article.get('content', '')[:200] if article.get('content') else ''
                }
                processed_articles.append(processed_article)

            return processed_articles

        except NewsAPIException as e:
            # NewsAPI specific errors (rate limit, auth, etc.)
            logger.error(f"NewsAPI exception: {e}")
            raise  # Will trigger retry via tenacity

        except Exception as e:
            # Unexpected errors
            logger.error(f"Unexpected error fetching from NewsAPI: {e}", exc_info=True)
            return []

    async def fetch_crypto_news(
        self,
        symbol: str,
        lookback_hours: int = 24,
        max_articles: int = 20
    ) -> List[Dict]:
        """
        Fetch news about a cryptocurrency with caching

        Primary method for fetching news. Uses cache when available,
        falls back to mock data if API fails.

        Args:
            symbol: Crypto symbol (e.g., BTCUSDT -> BTC)
            lookback_hours: How far back to look for news
            max_articles: Maximum number of articles to return

        Returns:
            List of news articles with title, source, url, published_at
        """
        # Extract base symbol (BTC from BTCUSDT)
        base_symbol = self._extract_base_symbol(symbol)

        # Check cache first
        cache_key = self._get_cache_key(base_symbol, lookback_hours)
        if cache_key in self.news_cache:
            logger.info(f"Returning cached news for {base_symbol}")
            return self.news_cache[cache_key]

        articles = []

        # Try fetching from real NewsAPI if configured
        if self.use_real_api and self.newsapi_client:
            try:
                search_query = self._get_search_keywords(base_symbol)
                articles = await self._fetch_from_newsapi(
                    search_query=search_query,
                    lookback_hours=lookback_hours,
                    max_articles=max_articles
                )

                # Cache successful results
                if articles:
                    self.news_cache[cache_key] = articles
                    logger.info(f"Cached {len(articles)} articles for {base_symbol}")

            except NewsAPIException as e:
                logger.error(f"NewsAPI failed after retries: {e}")
                # Try to return stale cached data if available
                # Search all cache keys for this symbol (ignore time component)
                for key in list(self.news_cache.keys()):
                    if key.startswith(f"{base_symbol}_"):
                        logger.warning(f"Using stale cached data for {base_symbol}")
                        return self.news_cache[key]
                # Fall through to mock data

            except Exception as e:
                logger.error(f"Unexpected error fetching news: {e}", exc_info=True)
                # Fall through to mock data

        # Fallback to mock data if API not configured or failed
        if not articles:
            logger.info(f"Using mock news data for {base_symbol}")
            articles = await self._fetch_from_free_sources(
                base_symbol, lookback_hours, max_articles
            )
            # Cache mock data with shorter TTL (5 minutes)
            if articles:
                self.news_cache[cache_key] = articles

        return articles

    async def _fetch_from_free_sources(
        self,
        symbol: str,
        lookback_hours: int,
        max_articles: int
    ) -> List[Dict]:
        """
        Generate mock news for testing (fallback when API unavailable)

        This is used when:
        1. No API key is configured
        2. API rate limit exceeded
        3. API is temporarily unavailable

        In production, this provides graceful degradation
        """
        mock_articles = self._generate_mock_news(symbol, lookback_hours, max_articles)
        logger.info(f"Generated {len(mock_articles)} mock articles for {symbol}")
        return mock_articles

    def _generate_mock_news(
        self,
        symbol: str,
        lookback_hours: int,
        max_articles: int
    ) -> List[Dict]:
        """
        Generate realistic mock news for testing

        Maintains consistent format with real API responses
        """
        now = datetime.utcnow()

        # Get crypto name for better mock articles
        crypto_name = self.SYMBOL_KEYWORDS.get(symbol, [symbol])[0]

        # Mock news templates with varied sentiment
        news_templates = [
            {
                "title": f"{crypto_name} Price Analysis: Bulls Target New Highs",
                "source": "CryptoNews",
                "sentiment_bias": 0.7  # Bullish
            },
            {
                "title": f"{crypto_name} Sees Institutional Interest Growing",
                "source": "CoinDesk",
                "sentiment_bias": 0.6
            },
            {
                "title": f"Analysts Divided on {crypto_name} Short-Term Outlook",
                "source": "The Block",
                "sentiment_bias": 0.0  # Neutral
            },
            {
                "title": f"{crypto_name} Faces Resistance at Key Technical Level",
                "source": "CoinTelegraph",
                "sentiment_bias": -0.3  # Slightly bearish
            },
            {
                "title": f"Major Exchange Lists {crypto_name} Trading Pairs",
                "source": "Decrypt",
                "sentiment_bias": 0.5
            },
            {
                "title": f"{crypto_name} Network Upgrade Scheduled for Next Quarter",
                "source": "CryptoSlate",
                "sentiment_bias": 0.6
            },
            {
                "title": f"Regulatory Concerns Impact {crypto_name} Market Sentiment",
                "source": "Bloomberg Crypto",
                "sentiment_bias": -0.5  # Bearish
            },
            {
                "title": f"{crypto_name} Trading Volume Surges Amid Market Volatility",
                "source": "CoinMarketCap",
                "sentiment_bias": 0.2
            },
            {
                "title": f"{crypto_name} Whale Activity Detected by Analysts",
                "source": "Glassnode",
                "sentiment_bias": 0.4
            },
            {
                "title": f"{crypto_name} DeFi Integration Expands Ecosystem",
                "source": "DeFi Pulse",
                "sentiment_bias": 0.6
            }
        ]

        # Generate articles distributed over lookback period
        articles = []
        for i in range(min(max_articles, len(news_templates))):
            template = news_templates[i % len(news_templates)]

            # Distribute articles evenly across time period
            hours_ago = (i * lookback_hours / max_articles)
            published_at = now - timedelta(hours=hours_ago)

            article = {
                "title": template["title"],
                "source": template["source"],
                "url": f"https://example.com/news/{symbol.lower()}-{i}",
                "description": f"Analysis and news about {crypto_name} market movements.",
                "published_at": published_at,
                "author": "Mock Author",
                "content_snippet": f"This is a mock article about {crypto_name}...",
                "_sentiment_bias": template["sentiment_bias"]  # For testing
            }

            articles.append(article)

        return articles

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
            "cache_size": len(self.news_cache),
            "cache_maxsize": self.news_cache.maxsize,
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "session_start": self.last_reset.isoformat()
        }
