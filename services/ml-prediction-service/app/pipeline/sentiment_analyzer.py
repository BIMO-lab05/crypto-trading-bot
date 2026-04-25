"""
Sentiment Analyzer - Phase 6.1 Feature Extraction
Purpose: Extract sentiment features from news, social media, and market data
Author: Phase 6.4 Implementation
Date: 2025-12-11

Provides 6 sentiment features:
- sentiment_score: Aggregated sentiment (-1 to 1)
- sentiment_momentum: Change in sentiment over time
- sentiment_divergence: Price vs sentiment divergence
- fear_greed_index: Market-wide sentiment indicator
- social_volume: Discussion volume metric
- sentiment_volatility: Sentiment stability measure
"""

import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class SentimentFeatures:
    """
    Sentiment feature set for ML models

    All values are normalized to appropriate ranges for ML input:
    - sentiment_score: [-1, 1] where -1 = bearish, 1 = bullish
    - sentiment_momentum: [-1, 1] rate of change in sentiment
    - sentiment_divergence: [-1, 1] price vs sentiment correlation
    - fear_greed_index: [0, 100] traditional market fear/greed scale
    - social_volume: [0, 1] normalized discussion volume
    - sentiment_volatility: [0, 1] stability of sentiment
    """
    # Core sentiment score
    sentiment_score: float = 0.0  # -1.0 (bearish) to 1.0 (bullish)

    # Momentum of sentiment change
    sentiment_momentum: float = 0.0  # Rate of change in sentiment

    # Divergence between price and sentiment
    sentiment_divergence: float = 0.0  # Price vs sentiment correlation

    # Market-wide fear/greed indicator
    fear_greed_index: float = 50.0  # 0 (extreme fear) to 100 (extreme greed)

    # Social media discussion volume
    social_volume: float = 0.5  # Normalized [0, 1]

    # Volatility of sentiment
    sentiment_volatility: float = 0.0  # [0, 1] stability measure

    # Timestamp of extraction
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Source availability flags
    news_available: bool = False
    social_available: bool = False

    def to_array(self) -> np.ndarray:
        """Convert to numpy array for ML model input"""
        return np.array([
            self.sentiment_score,
            self.sentiment_momentum,
            self.sentiment_divergence,
            self.fear_greed_index / 100.0,  # Normalize to [0, 1]
            self.social_volume,
            self.sentiment_volatility
        ], dtype=np.float32)

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for API response"""
        return {
            'sentiment_score': self.sentiment_score,
            'sentiment_momentum': self.sentiment_momentum,
            'sentiment_divergence': self.sentiment_divergence,
            'fear_greed_index': self.fear_greed_index,
            'social_volume': self.social_volume,
            'sentiment_volatility': self.sentiment_volatility,
            'timestamp': self.timestamp.isoformat(),
            'news_available': self.news_available,
            'social_available': self.social_available
        }

    @classmethod
    def feature_names(cls) -> List[str]:
        """Return list of feature names for dataframe columns"""
        return [
            'sentiment_score',
            'sentiment_momentum',
            'sentiment_divergence',
            'fear_greed_index_norm',  # Normalized to [0, 1]
            'social_volume',
            'sentiment_volatility'
        ]


class SentimentAnalyzer:
    """
    Sentiment feature extractor for ML models

    Integrates with:
    - Sentiment Analysis Service (internal)
    - Alternative.me Fear & Greed API (external)
    - Fallback to neutral values when services unavailable

    Example usage:
        analyzer = SentimentAnalyzer(sentiment_service_url="http://localhost:8006")
        features = await analyzer.get_aggregated_sentiment("BTCUSDT")
    """

    def __init__(
        self,
        sentiment_service_url: str = "http://localhost:8006",
        fear_greed_api_url: str = "https://api.alternative.me/fng/",
        timeout: float = 10.0,
        cache_ttl_seconds: int = 300  # 5 minutes
    ):
        """
        Initialize sentiment analyzer

        Args:
            sentiment_service_url: URL of internal sentiment analysis service
            fear_greed_api_url: URL of Fear & Greed Index API
            timeout: HTTP request timeout in seconds
            cache_ttl_seconds: Cache time-to-live for sentiment data
        """
        # Service URLs
        self.sentiment_service_url = sentiment_service_url
        self.fear_greed_api_url = fear_greed_api_url

        # HTTP client configuration
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

        # Caching
        self.cache_ttl_seconds = cache_ttl_seconds
        self._sentiment_cache: Dict[str, Tuple[SentimentFeatures, datetime]] = {}
        self._fear_greed_cache: Optional[Tuple[float, datetime]] = None

        # Historical sentiment for momentum calculation
        self._sentiment_history: Dict[str, List[Tuple[float, datetime]]] = {}
        self._max_history_length = 24  # Keep 24 data points for momentum

        logger.info(f"SentimentAnalyzer initialized (service_url={sentiment_service_url})")

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client connections"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_aggregated_sentiment(
        self,
        symbol: str,
        include_fear_greed: bool = True,
        use_cache: bool = True
    ) -> SentimentFeatures:
        """
        Get aggregated sentiment features for a symbol

        Combines multiple sentiment sources:
        1. Internal sentiment service (news + social)
        2. Fear & Greed Index (market-wide)
        3. Historical data for momentum/volatility

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            include_fear_greed: Whether to fetch Fear & Greed Index
            use_cache: Whether to use cached data

        Returns:
            SentimentFeatures with all 6 sentiment indicators
        """
        # Check cache first
        if use_cache and symbol in self._sentiment_cache:
            cached_features, cached_time = self._sentiment_cache[symbol]
            age_seconds = (datetime.utcnow() - cached_time).total_seconds()
            if age_seconds < self.cache_ttl_seconds:
                logger.debug(f"Using cached sentiment for {symbol} (age={age_seconds:.1f}s)")
                return cached_features

        # Fetch sentiment data in parallel
        tasks = [
            self._fetch_symbol_sentiment(symbol),
        ]

        if include_fear_greed:
            tasks.append(self._fetch_fear_greed_index())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Parse results
        symbol_sentiment = results[0] if not isinstance(results[0], Exception) else None
        fear_greed = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else None

        # Build features
        features = self._build_sentiment_features(symbol, symbol_sentiment, fear_greed)

        # Update cache
        self._sentiment_cache[symbol] = (features, datetime.utcnow())

        # Update history for momentum calculation
        self._update_sentiment_history(symbol, features.sentiment_score)

        return features

    async def _fetch_symbol_sentiment(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Fetch sentiment from internal sentiment analysis service

        Args:
            symbol: Trading pair

        Returns:
            Sentiment data dict or None if unavailable
        """
        try:
            client = await self._get_client()

            # Call sentiment analysis service
            url = f"{self.sentiment_service_url}/api/v1/sentiment/{symbol}"
            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                logger.debug(f"Fetched sentiment for {symbol}: score={data.get('sentiment_score', 'N/A')}")
                return data
            else:
                logger.warning(f"Sentiment service returned {response.status_code} for {symbol}")
                return None

        except httpx.TimeoutException:
            logger.warning(f"Sentiment service timeout for {symbol}")
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch sentiment for {symbol}: {e}")
            return None

    async def _fetch_fear_greed_index(self) -> Optional[float]:
        """
        Fetch Fear & Greed Index from Alternative.me API

        Returns:
            Fear & Greed value (0-100) or None if unavailable
        """
        # Check cache
        if self._fear_greed_cache:
            cached_value, cached_time = self._fear_greed_cache
            age_seconds = (datetime.utcnow() - cached_time).total_seconds()
            if age_seconds < self.cache_ttl_seconds:
                return cached_value

        try:
            client = await self._get_client()

            # Fetch Fear & Greed Index
            response = await client.get(self.fear_greed_api_url)

            if response.status_code == 200:
                data = response.json()
                # API returns: {"data": [{"value": "73", ...}]}
                if 'data' in data and len(data['data']) > 0:
                    value = float(data['data'][0]['value'])
                    self._fear_greed_cache = (value, datetime.utcnow())
                    logger.debug(f"Fetched Fear & Greed Index: {value}")
                    return value

            return None

        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index: {e}")
            return None

    def _build_sentiment_features(
        self,
        symbol: str,
        symbol_sentiment: Optional[Dict[str, Any]],
        fear_greed: Optional[float]
    ) -> SentimentFeatures:
        """
        Build SentimentFeatures from raw data

        Args:
            symbol: Trading pair
            symbol_sentiment: Data from sentiment service
            fear_greed: Fear & Greed Index value

        Returns:
            Complete SentimentFeatures object
        """
        features = SentimentFeatures()

        # Process symbol-specific sentiment
        if symbol_sentiment:
            features.sentiment_score = float(symbol_sentiment.get('sentiment_score', 0.0))
            features.social_volume = self._normalize_social_volume(
                symbol_sentiment.get('social_volume', 0),
                symbol_sentiment.get('social_volume_avg', 1)
            )
            features.news_available = symbol_sentiment.get('news_count', 0) > 0
            features.social_available = symbol_sentiment.get('social_count', 0) > 0

        # Process Fear & Greed Index
        if fear_greed is not None:
            features.fear_greed_index = fear_greed

        # Calculate momentum from history
        features.sentiment_momentum = self._calculate_sentiment_momentum(symbol)

        # Calculate volatility from history
        features.sentiment_volatility = self._calculate_sentiment_volatility(symbol)

        # Calculate divergence (requires price data - set to 0 if not available)
        features.sentiment_divergence = 0.0  # Will be calculated externally with price data

        features.timestamp = datetime.utcnow()

        return features

    def _normalize_social_volume(self, current_volume: float, avg_volume: float) -> float:
        """
        Normalize social volume to [0, 1] range

        Args:
            current_volume: Current discussion volume
            avg_volume: Average discussion volume

        Returns:
            Normalized volume [0, 1]
        """
        if avg_volume <= 0:
            return 0.5

        # Ratio capped between 0 and 3x average
        ratio = min(current_volume / avg_volume, 3.0)

        # Normalize to [0, 1]
        return min(ratio / 3.0, 1.0)

    def _update_sentiment_history(self, symbol: str, score: float):
        """Update sentiment history for a symbol"""
        if symbol not in self._sentiment_history:
            self._sentiment_history[symbol] = []

        history = self._sentiment_history[symbol]
        history.append((score, datetime.utcnow()))

        # Trim to max length
        if len(history) > self._max_history_length:
            self._sentiment_history[symbol] = history[-self._max_history_length:]

    def _calculate_sentiment_momentum(self, symbol: str) -> float:
        """
        Calculate sentiment momentum (rate of change)

        Returns:
            Momentum value [-1, 1]
        """
        if symbol not in self._sentiment_history:
            return 0.0

        history = self._sentiment_history[symbol]

        if len(history) < 2:
            return 0.0

        # Calculate rate of change over available history
        scores = [h[0] for h in history]

        # Simple momentum: current - mean of previous
        current = scores[-1]
        previous_mean = np.mean(scores[:-1])

        momentum = current - previous_mean

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, momentum))

    def _calculate_sentiment_volatility(self, symbol: str) -> float:
        """
        Calculate sentiment volatility (stability measure)

        Returns:
            Volatility value [0, 1]
        """
        if symbol not in self._sentiment_history:
            return 0.0

        history = self._sentiment_history[symbol]

        if len(history) < 3:
            return 0.0

        # Standard deviation of sentiment scores
        scores = [h[0] for h in history]
        volatility = np.std(scores)

        # Normalize: 0.5 std dev maps to 0.5 volatility, 1.0 std dev maps to 1.0
        normalized = min(volatility * 2.0, 1.0)

        return float(normalized)

    def calculate_price_sentiment_divergence(
        self,
        sentiment_change: float,
        price_change_pct: float
    ) -> float:
        """
        Calculate divergence between price and sentiment

        When price and sentiment move in opposite directions,
        divergence is high (potential reversal signal)

        Args:
            sentiment_change: Change in sentiment [-1, 1]
            price_change_pct: Price change percentage

        Returns:
            Divergence score [-1, 1]
            - Positive: Sentiment positive but price down (bullish divergence)
            - Negative: Sentiment negative but price up (bearish divergence)
        """
        # Normalize price change to [-1, 1] range
        # Assuming 5% price move = maximum (1.0)
        normalized_price_change = max(-1.0, min(1.0, price_change_pct / 5.0))

        # Divergence = sentiment - price_direction
        # High positive: sentiment bullish + price falling (bullish divergence)
        # High negative: sentiment bearish + price rising (bearish divergence)
        divergence = sentiment_change - normalized_price_change

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, divergence))

    async def get_batch_sentiment(
        self,
        symbols: List[str]
    ) -> Dict[str, SentimentFeatures]:
        """
        Get sentiment features for multiple symbols in parallel

        Args:
            symbols: List of trading pairs

        Returns:
            Dictionary mapping symbol to SentimentFeatures
        """
        tasks = [self.get_aggregated_sentiment(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sentiment_dict = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to get sentiment for {symbol}: {result}")
                sentiment_dict[symbol] = SentimentFeatures()  # Return default values
            else:
                sentiment_dict[symbol] = result

        return sentiment_dict

    def get_sentiment_signal(self, features: SentimentFeatures) -> str:
        """
        Derive trading signal from sentiment features

        Args:
            features: SentimentFeatures object

        Returns:
            Signal string: "BULLISH", "BEARISH", or "NEUTRAL"
        """
        # Weighted score
        score = (
            features.sentiment_score * 0.4 +
            features.sentiment_momentum * 0.2 +
            (features.fear_greed_index / 100.0 - 0.5) * 0.4  # Center around 0
        )

        if score > 0.2:
            return "BULLISH"
        elif score < -0.2:
            return "BEARISH"
        else:
            return "NEUTRAL"
