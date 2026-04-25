"""
Fear & Greed Index Integration
Fetches and processes crypto market Fear & Greed Index

Data Source: Alternative.me API (free, no auth required)
https://alternative.me/crypto/fear-and-greed-index/

Index Values:
- 0-24: Extreme Fear
- 25-49: Fear
- 50-54: Neutral
- 55-74: Greed
- 75-100: Extreme Greed

Author: Phase 6.1 Implementation
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FearGreedData:
    """
    Fear & Greed Index data point

    Attributes:
        value: Index value (0-100)
        value_classification: Text classification (Extreme Fear, Fear, Neutral, Greed, Extreme Greed)
        timestamp: When this value was recorded
        normalized_score: Normalized to -1 (extreme fear) to 1 (extreme greed)
    """
    value: int
    value_classification: str
    timestamp: datetime
    normalized_score: float = 0.0

    def __post_init__(self):
        """Calculate normalized score from value"""
        # Normalize 0-100 to -1 to 1
        self.normalized_score = round((self.value - 50) / 50, 4)


@dataclass
class FearGreedHistory:
    """
    Historical Fear & Greed Index data

    Attributes:
        current: Current index value
        history: List of historical values
        trend: Direction of movement (INCREASING, DECREASING, STABLE)
        trend_strength: How strong the trend is (0-1)
        average_7d: 7-day average
        average_30d: 30-day average
        volatility: How much the index has changed recently
    """
    current: FearGreedData
    history: List[FearGreedData] = field(default_factory=list)
    trend: str = "STABLE"
    trend_strength: float = 0.0
    average_7d: float = 50.0
    average_30d: float = 50.0
    volatility: float = 0.0


class FearGreedIndex:
    """
    Fear & Greed Index fetcher and analyzer

    Fetches data from Alternative.me API and provides:
    - Current index value
    - Historical data
    - Trend analysis
    - Normalized scores for ML features
    """

    API_URL = "https://api.alternative.me/fng/"

    def __init__(self, cache_ttl_seconds: int = 3600):
        """
        Initialize Fear & Greed Index fetcher

        Args:
            cache_ttl_seconds: Cache TTL (default: 1 hour - data updates daily)
        """
        self.cache_ttl_seconds = cache_ttl_seconds
        self._http_client: Optional[httpx.AsyncClient] = None

        # Cache
        self._cache: Optional[Tuple[FearGreedHistory, datetime]] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def _get_cached_data(self) -> Optional[FearGreedHistory]:
        """Get cached data if available and not expired"""
        if self._cache:
            data, cached_time = self._cache
            age = (datetime.utcnow() - cached_time).total_seconds()

            if age < self.cache_ttl_seconds:
                logger.debug(f"Fear & Greed cache HIT (age: {age:.1f}s)")
                return data

        return None

    def _cache_data(self, data: FearGreedHistory):
        """Cache the data"""
        self._cache = (data, datetime.utcnow())
        logger.debug("Cached Fear & Greed data")

    async def get_current(self) -> FearGreedData:
        """
        Get current Fear & Greed Index value

        Returns:
            FearGreedData with current index
        """
        history = await self.get_history(limit=1)
        return history.current

    async def get_history(self, limit: int = 30) -> FearGreedHistory:
        """
        Get Fear & Greed Index with history

        Args:
            limit: Number of historical days to fetch (max 100)

        Returns:
            FearGreedHistory with current and historical data
        """
        # Check cache for default query
        if limit == 30:
            cached = self._get_cached_data()
            if cached:
                return cached

        try:
            client = await self._get_http_client()

            params = {
                'limit': min(limit, 100),  # API max is 100
                'format': 'json'
            }

            response = await client.get(self.API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Parse response
            data_points = data.get('data', [])

            if not data_points:
                logger.warning("No Fear & Greed data returned - using fallback")
                return self._generate_fallback_data()

            # Parse historical data
            history = []
            for point in data_points:
                try:
                    history.append(FearGreedData(
                        value=int(point.get('value', 50)),
                        value_classification=point.get('value_classification', 'Neutral'),
                        timestamp=datetime.fromtimestamp(int(point.get('timestamp', 0)))
                    ))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing Fear & Greed data point: {e}")
                    continue

            if not history:
                return self._generate_fallback_data()

            # Current is the first (most recent) entry
            current = history[0]

            # Calculate statistics
            result = FearGreedHistory(
                current=current,
                history=history
            )

            # Calculate 7-day and 30-day averages
            if len(history) >= 7:
                result.average_7d = sum(h.value for h in history[:7]) / 7
            else:
                result.average_7d = sum(h.value for h in history) / len(history)

            if len(history) >= 30:
                result.average_30d = sum(h.value for h in history[:30]) / 30
            else:
                result.average_30d = sum(h.value for h in history) / len(history)

            # Calculate trend
            if len(history) >= 7:
                recent_avg = sum(h.value for h in history[:3]) / 3
                older_avg = sum(h.value for h in history[4:7]) / 3

                change = recent_avg - older_avg

                if change > 5:
                    result.trend = "INCREASING"
                    result.trend_strength = min(1.0, change / 20)
                elif change < -5:
                    result.trend = "DECREASING"
                    result.trend_strength = min(1.0, abs(change) / 20)
                else:
                    result.trend = "STABLE"
                    result.trend_strength = 0.3

            # Calculate volatility (standard deviation of recent values)
            if len(history) >= 7:
                values = [h.value for h in history[:7]]
                mean = sum(values) / len(values)
                variance = sum((v - mean) ** 2 for v in values) / len(values)
                result.volatility = round(variance ** 0.5, 2)

            # Cache the result
            if limit == 30:
                self._cache_data(result)

            logger.info(
                f"Fear & Greed Index: {current.value} ({current.value_classification}) "
                f"- Trend: {result.trend}"
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"Fear & Greed API HTTP error: {e}")
            return self._generate_fallback_data()
        except Exception as e:
            logger.error(f"Error fetching Fear & Greed Index: {e}")
            return self._generate_fallback_data()

    def _generate_fallback_data(self) -> FearGreedHistory:
        """
        Generate fallback data when API is unavailable

        Uses neutral values to avoid impacting predictions
        """
        logger.warning("Using fallback Fear & Greed data")

        now = datetime.utcnow()
        history = []

        # Generate 30 days of neutral data
        for i in range(30):
            history.append(FearGreedData(
                value=50,
                value_classification="Neutral",
                timestamp=now - timedelta(days=i)
            ))

        return FearGreedHistory(
            current=history[0],
            history=history,
            trend="STABLE",
            trend_strength=0.0,
            average_7d=50.0,
            average_30d=50.0,
            volatility=0.0
        )

    def get_normalized_score(self, data: FearGreedData) -> float:
        """
        Get normalized sentiment score from Fear & Greed data

        Args:
            data: FearGreedData instance

        Returns:
            Normalized score from -1 (extreme fear) to 1 (extreme greed)
        """
        return data.normalized_score

    def get_market_sentiment_label(self, value: int) -> str:
        """
        Get human-readable market sentiment label

        Args:
            value: Fear & Greed index value (0-100)

        Returns:
            Sentiment label string
        """
        if value <= 24:
            return "EXTREME_FEAR"
        elif value <= 49:
            return "FEAR"
        elif value <= 54:
            return "NEUTRAL"
        elif value <= 74:
            return "GREED"
        else:
            return "EXTREME_GREED"

    def calculate_divergence(
        self,
        fear_greed_value: int,
        price_change_24h: float
    ) -> float:
        """
        Calculate price vs sentiment divergence

        Divergence occurs when:
        - High fear but price going up (bullish divergence)
        - High greed but price going down (bearish divergence)

        Args:
            fear_greed_value: Fear & Greed index value (0-100)
            price_change_24h: 24h price change percentage

        Returns:
            Divergence score from -1 to 1
            - Positive: Bullish divergence (price up + fear = potential buy)
            - Negative: Bearish divergence (price down + greed = potential sell)
        """
        # Normalize fear/greed to -1 to 1
        sentiment = (fear_greed_value - 50) / 50

        # Normalize price change (-10% to +10% maps to -1 to 1)
        price_signal = max(-1, min(1, price_change_24h / 10))

        # Divergence = opposite signs indicate divergence
        # If sentiment is negative (fear) but price positive (up) = bullish
        # If sentiment is positive (greed) but price negative (down) = bearish
        divergence = price_signal - sentiment

        return round(divergence / 2, 4)  # Normalize to -1 to 1

    async def get_features_for_ml(self) -> dict:
        """
        Get Fear & Greed features for ML model input

        Returns:
            Dictionary of features:
            - fear_greed_index: Raw index value (0-100)
            - fear_greed_normalized: Normalized score (-1 to 1)
            - fear_greed_trend: Trend score (-1 to 1)
            - fear_greed_volatility: Index volatility
            - fear_greed_7d_avg: 7-day average
            - fear_greed_30d_avg: 30-day average
        """
        history = await self.get_history(limit=30)

        # Trend score
        if history.trend == "INCREASING":
            trend_score = history.trend_strength
        elif history.trend == "DECREASING":
            trend_score = -history.trend_strength
        else:
            trend_score = 0.0

        return {
            'fear_greed_index': history.current.value,
            'fear_greed_normalized': history.current.normalized_score,
            'fear_greed_trend': round(trend_score, 4),
            'fear_greed_volatility': history.volatility,
            'fear_greed_7d_avg': round((history.average_7d - 50) / 50, 4),
            'fear_greed_30d_avg': round((history.average_30d - 50) / 50, 4)
        }
