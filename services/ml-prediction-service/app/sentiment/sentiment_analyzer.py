"""
Sentiment Analyzer - Main Module for ML Sentiment Integration
Aggregates sentiment from multiple sources and generates ML features

Features Generated:
- sentiment_score: Aggregated sentiment (-1 to 1)
- sentiment_momentum: Rate of change in sentiment
- sentiment_divergence: Price vs sentiment divergence
- fear_greed_index: Market-wide sentiment (0-100)
- social_volume: Mentions/discussions volume
- sentiment_volatility: Stability of sentiment

Author: Phase 6.1 Implementation
Date: 2025-12-11
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .data_sources import (
    NewsSentimentSource,
    RedditSentimentSource,
    SentimentDataSource,
    SourceResult,
    TwitterSentimentSource
)
from .fear_greed import FearGreedData, FearGreedHistory, FearGreedIndex

logger = logging.getLogger(__name__)


@dataclass
class SentimentScore:
    """
    Individual sentiment score from a source

    Attributes:
        source: Source name (twitter, news, reddit, fear_greed)
        score: Sentiment score (-1 to 1)
        confidence: Confidence in the score (0 to 1)
        volume: Number of data points used
        timestamp: When the score was calculated
    """
    source: str
    score: float
    confidence: float = 0.5
    volume: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SentimentFeatures:
    """
    Sentiment features for ML model input

    All features are normalized to appropriate ranges for ML models:
    - sentiment_score: -1 to 1 (aggregated sentiment)
    - sentiment_momentum: -1 to 1 (rate of change)
    - sentiment_divergence: -1 to 1 (price vs sentiment)
    - fear_greed_index: 0 to 100 (raw index)
    - fear_greed_normalized: -1 to 1 (normalized index)
    - social_volume: normalized log scale
    - sentiment_volatility: 0 to 1 (stability)
    """
    sentiment_score: float = 0.0
    sentiment_momentum: float = 0.0
    sentiment_divergence: float = 0.0
    fear_greed_index: float = 50.0
    fear_greed_normalized: float = 0.0
    social_volume: float = 0.0
    sentiment_volatility: float = 0.0
    twitter_sentiment: float = 0.0
    news_sentiment: float = 0.0
    reddit_sentiment: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for DataFrame"""
        return {
            'sentiment_score': self.sentiment_score,
            'sentiment_momentum': self.sentiment_momentum,
            'sentiment_divergence': self.sentiment_divergence,
            'fear_greed_index': self.fear_greed_index,
            'fear_greed_normalized': self.fear_greed_normalized,
            'social_volume': self.social_volume,
            'sentiment_volatility': self.sentiment_volatility,
            'twitter_sentiment': self.twitter_sentiment,
            'news_sentiment': self.news_sentiment,
            'reddit_sentiment': self.reddit_sentiment
        }


@dataclass
class AggregatedSentiment:
    """
    Complete aggregated sentiment analysis

    Attributes:
        symbol: Trading pair analyzed
        timestamp: Analysis timestamp
        overall_score: Weighted average sentiment (-1 to 1)
        overall_label: Sentiment label (BULLISH, BEARISH, NEUTRAL)
        confidence: Confidence in the analysis (0 to 1)
        sources: Individual source scores
        features: ML-ready features
        metadata: Additional analysis metadata
    """
    symbol: str
    timestamp: datetime
    overall_score: float
    overall_label: str
    confidence: float
    sources: List[SentimentScore]
    features: SentimentFeatures
    metadata: Dict[str, Any] = field(default_factory=dict)


class SentimentAnalyzer:
    """
    Main sentiment analyzer combining multiple data sources

    Combines:
    - Twitter/X sentiment (weight: 25%)
    - News sentiment (weight: 25%)
    - Reddit sentiment (weight: 20%)
    - Fear & Greed Index (weight: 30%)

    Features:
    - Async parallel fetching
    - Redis caching for sentiment data
    - Graceful fallback on API failures
    - Historical sentiment tracking
    """

    def __init__(
        self,
        twitter_weight: float = 0.25,
        news_weight: float = 0.25,
        reddit_weight: float = 0.20,
        fear_greed_weight: float = 0.30,
        redis_client: Optional[Any] = None,
        cache_ttl_seconds: int = 300
    ):
        """
        Initialize sentiment analyzer

        Args:
            twitter_weight: Weight for Twitter sentiment
            news_weight: Weight for news sentiment
            reddit_weight: Weight for Reddit sentiment
            fear_greed_weight: Weight for Fear & Greed Index
            redis_client: Optional Redis client for caching
            cache_ttl_seconds: Cache TTL in seconds
        """
        # Normalize weights
        total = twitter_weight + news_weight + reddit_weight + fear_greed_weight
        self.twitter_weight = twitter_weight / total
        self.news_weight = news_weight / total
        self.reddit_weight = reddit_weight / total
        self.fear_greed_weight = fear_greed_weight / total

        # Initialize data sources
        self.twitter_source = TwitterSentimentSource(cache_ttl_seconds=cache_ttl_seconds)
        self.news_source = NewsSentimentSource(cache_ttl_seconds=cache_ttl_seconds * 2)
        self.reddit_source = RedditSentimentSource(cache_ttl_seconds=cache_ttl_seconds)
        self.fear_greed = FearGreedIndex(cache_ttl_seconds=3600)

        # Redis caching
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds

        # Historical sentiment tracking (in-memory)
        self._history: Dict[str, List[Tuple[datetime, float]]] = {}
        self._max_history_points = 100

        logger.info(
            f"SentimentAnalyzer initialized with weights: "
            f"Twitter={self.twitter_weight:.2f}, News={self.news_weight:.2f}, "
            f"Reddit={self.reddit_weight:.2f}, FearGreed={self.fear_greed_weight:.2f}"
        )

    async def close(self):
        """Close all HTTP clients"""
        await asyncio.gather(
            self.twitter_source.close(),
            self.news_source.close(),
            self.reddit_source.close(),
            self.fear_greed.close()
        )

    async def get_twitter_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> float:
        """
        Get Twitter sentiment for a symbol

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            lookback_hours: Hours of data to analyze

        Returns:
            Sentiment score from -1 to 1
        """
        result = await self.twitter_source.fetch_sentiment(symbol, lookback_hours)

        if result.error:
            logger.warning(f"Twitter sentiment error: {result.error}")
            return 0.0

        return result.weighted_sentiment

    async def get_news_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> float:
        """
        Get news sentiment for a symbol

        Args:
            symbol: Trading pair
            lookback_hours: Hours of news to analyze

        Returns:
            Sentiment score from -1 to 1
        """
        result = await self.news_source.fetch_sentiment(symbol, lookback_hours)

        if result.error:
            logger.warning(f"News sentiment error: {result.error}")
            return 0.0

        return result.average_sentiment

    async def get_social_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24
    ) -> SentimentScore:
        """
        Get combined social media sentiment (Twitter + Reddit)

        Args:
            symbol: Trading pair
            lookback_hours: Hours of data to analyze

        Returns:
            SentimentScore with combined social sentiment
        """
        # Fetch Twitter and Reddit in parallel
        twitter_task = self.twitter_source.fetch_sentiment(symbol, lookback_hours)
        reddit_task = self.reddit_source.fetch_sentiment(symbol, lookback_hours)

        twitter_result, reddit_result = await asyncio.gather(
            twitter_task, reddit_task
        )

        # Combine scores (Twitter: 55%, Reddit: 45%)
        twitter_score = twitter_result.weighted_sentiment if not twitter_result.error else 0.0
        reddit_score = reddit_result.weighted_sentiment if not reddit_result.error else 0.0

        combined_score = (twitter_score * 0.55) + (reddit_score * 0.45)

        # Calculate confidence based on data availability
        confidence = 0.0
        if not twitter_result.error:
            confidence += 0.55
        if not reddit_result.error:
            confidence += 0.45

        # Calculate total volume
        volume = twitter_result.total_volume + reddit_result.total_volume

        return SentimentScore(
            source='social',
            score=round(combined_score, 4),
            confidence=confidence,
            volume=volume
        )

    async def get_aggregated_sentiment(
        self,
        symbol: str,
        lookback_hours: int = 24,
        price_change_24h: Optional[float] = None
    ) -> float:
        """
        Get aggregated sentiment from all sources

        This is the main method for getting a single sentiment score
        that combines all available data sources.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            lookback_hours: Hours of data to analyze
            price_change_24h: Optional 24h price change for divergence calculation

        Returns:
            Aggregated sentiment score from -1 to 1
        """
        analysis = await self.analyze(symbol, lookback_hours, price_change_24h)
        return analysis.overall_score

    async def analyze(
        self,
        symbol: str,
        lookback_hours: int = 24,
        price_change_24h: Optional[float] = None
    ) -> AggregatedSentiment:
        """
        Perform complete sentiment analysis

        Fetches data from all sources, calculates weighted sentiment,
        and generates ML features.

        Args:
            symbol: Trading pair
            lookback_hours: Hours of data to analyze
            price_change_24h: Optional 24h price change for divergence

        Returns:
            AggregatedSentiment with complete analysis
        """
        logger.info(f"Analyzing sentiment for {symbol} ({lookback_hours}h lookback)")

        # Fetch all sources in parallel
        twitter_task = self.twitter_source.fetch_sentiment(symbol, lookback_hours)
        news_task = self.news_source.fetch_sentiment(symbol, lookback_hours)
        reddit_task = self.reddit_source.fetch_sentiment(symbol, lookback_hours)
        fear_greed_task = self.fear_greed.get_history(limit=30)

        results = await asyncio.gather(
            twitter_task, news_task, reddit_task, fear_greed_task,
            return_exceptions=True
        )

        twitter_result = results[0] if not isinstance(results[0], Exception) else None
        news_result = results[1] if not isinstance(results[1], Exception) else None
        reddit_result = results[2] if not isinstance(results[2], Exception) else None
        fear_greed_result = results[3] if not isinstance(results[3], Exception) else None

        # Build source scores
        sources = []
        weighted_sum = 0.0
        total_weight = 0.0
        total_volume = 0

        # Twitter
        if twitter_result and not twitter_result.error:
            twitter_score = SentimentScore(
                source='twitter',
                score=twitter_result.weighted_sentiment,
                confidence=min(1.0, twitter_result.total_volume / 50),
                volume=twitter_result.total_volume
            )
            sources.append(twitter_score)
            weighted_sum += twitter_result.weighted_sentiment * self.twitter_weight
            total_weight += self.twitter_weight
            total_volume += twitter_result.total_volume

        # News
        if news_result and not news_result.error:
            news_score = SentimentScore(
                source='news',
                score=news_result.average_sentiment,
                confidence=min(1.0, news_result.total_volume / 20),
                volume=news_result.total_volume
            )
            sources.append(news_score)
            weighted_sum += news_result.average_sentiment * self.news_weight
            total_weight += self.news_weight
            total_volume += news_result.total_volume

        # Reddit
        if reddit_result and not reddit_result.error:
            reddit_score = SentimentScore(
                source='reddit',
                score=reddit_result.weighted_sentiment,
                confidence=min(1.0, reddit_result.total_volume / 30),
                volume=reddit_result.total_volume
            )
            sources.append(reddit_score)
            weighted_sum += reddit_result.weighted_sentiment * self.reddit_weight
            total_weight += self.reddit_weight
            total_volume += reddit_result.total_volume

        # Fear & Greed
        if fear_greed_result:
            fg_normalized = fear_greed_result.current.normalized_score
            fg_score = SentimentScore(
                source='fear_greed',
                score=fg_normalized,
                confidence=0.9,  # High confidence for this source
                volume=1
            )
            sources.append(fg_score)
            weighted_sum += fg_normalized * self.fear_greed_weight
            total_weight += self.fear_greed_weight

        # Calculate overall score
        if total_weight > 0:
            overall_score = weighted_sum / total_weight
        else:
            overall_score = 0.0

        # Normalize to -1 to 1
        overall_score = max(-1, min(1, overall_score))

        # Determine label
        if overall_score > 0.3:
            overall_label = "BULLISH"
        elif overall_score < -0.3:
            overall_label = "BEARISH"
        else:
            overall_label = "NEUTRAL"

        # Calculate confidence
        confidence = total_weight / (self.twitter_weight + self.news_weight +
                                      self.reddit_weight + self.fear_greed_weight)

        # Calculate momentum (change from historical data)
        momentum = self._calculate_momentum(symbol, overall_score)

        # Calculate divergence (if price data available)
        divergence = 0.0
        if price_change_24h is not None and fear_greed_result:
            divergence = self.fear_greed.calculate_divergence(
                fear_greed_result.current.value,
                price_change_24h
            )

        # Calculate sentiment volatility
        volatility = self._calculate_volatility(symbol)

        # Build features
        features = SentimentFeatures(
            sentiment_score=round(overall_score, 4),
            sentiment_momentum=round(momentum, 4),
            sentiment_divergence=round(divergence, 4),
            fear_greed_index=fear_greed_result.current.value if fear_greed_result else 50,
            fear_greed_normalized=fear_greed_result.current.normalized_score if fear_greed_result else 0.0,
            social_volume=self._normalize_volume(total_volume),
            sentiment_volatility=round(volatility, 4),
            twitter_sentiment=twitter_result.weighted_sentiment if twitter_result and not twitter_result.error else 0.0,
            news_sentiment=news_result.average_sentiment if news_result and not news_result.error else 0.0,
            reddit_sentiment=reddit_result.weighted_sentiment if reddit_result and not reddit_result.error else 0.0
        )

        # Store in history for momentum calculation
        self._add_to_history(symbol, overall_score)

        # Build metadata
        metadata = {
            'lookback_hours': lookback_hours,
            'sources_available': len(sources),
            'total_data_points': total_volume,
            'fear_greed_trend': fear_greed_result.trend if fear_greed_result else "UNKNOWN"
        }

        return AggregatedSentiment(
            symbol=symbol,
            timestamp=datetime.utcnow(),
            overall_score=round(overall_score, 4),
            overall_label=overall_label,
            confidence=round(confidence, 4),
            sources=sources,
            features=features,
            metadata=metadata
        )

    def _add_to_history(self, symbol: str, score: float):
        """Add score to history for momentum calculation"""
        if symbol not in self._history:
            self._history[symbol] = []

        self._history[symbol].append((datetime.utcnow(), score))

        # Keep only recent history
        if len(self._history[symbol]) > self._max_history_points:
            self._history[symbol] = self._history[symbol][-self._max_history_points:]

    def _calculate_momentum(self, symbol: str, current_score: float) -> float:
        """
        Calculate sentiment momentum (rate of change)

        Compares current sentiment to historical average

        Returns:
            Momentum from -1 to 1 (positive = improving, negative = declining)
        """
        if symbol not in self._history or len(self._history[symbol]) < 3:
            return 0.0

        # Get recent history (last 3 points)
        recent = self._history[symbol][-3:]
        historical_avg = sum(score for _, score in recent) / len(recent)

        # Momentum = current - historical average
        momentum = current_score - historical_avg

        # Normalize to -1 to 1
        return max(-1, min(1, momentum * 2))

    def _calculate_volatility(self, symbol: str) -> float:
        """
        Calculate sentiment volatility

        Higher volatility = less stable sentiment = lower confidence

        Returns:
            Volatility from 0 to 1
        """
        if symbol not in self._history or len(self._history[symbol]) < 5:
            return 0.0

        # Get recent scores
        scores = [score for _, score in self._history[symbol][-10:]]

        if len(scores) < 2:
            return 0.0

        # Calculate standard deviation
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std_dev = variance ** 0.5

        # Normalize to 0-1 (max expected std is ~0.5 for -1 to 1 range)
        return min(1.0, std_dev * 2)

    def _normalize_volume(self, volume: int) -> float:
        """
        Normalize social volume to 0-1 scale using log scale

        Args:
            volume: Total number of posts/articles

        Returns:
            Normalized volume (0-1)
        """
        import math

        if volume <= 0:
            return 0.0

        # Log scale normalization
        # 10 posts = ~0.23, 100 posts = ~0.46, 1000 posts = ~0.69
        normalized = math.log10(volume + 1) / 4  # Assumes max ~10000 posts

        return min(1.0, normalized)

    async def get_features_for_ml(
        self,
        symbol: str,
        price_change_24h: Optional[float] = None
    ) -> Dict[str, float]:
        """
        Get sentiment features ready for ML model input

        This is the primary method for integrating sentiment into GRU/LSTM models.

        Args:
            symbol: Trading pair
            price_change_24h: Optional 24h price change for divergence

        Returns:
            Dictionary of normalized features for ML model
        """
        analysis = await self.analyze(symbol, lookback_hours=24, price_change_24h=price_change_24h)
        return analysis.features.to_dict()

    async def get_historical_features(
        self,
        symbol: str,
        timestamps: List[datetime],
        price_changes: Optional[List[float]] = None
    ) -> List[Dict[str, float]]:
        """
        Get historical sentiment features for training data

        Note: This method is limited because we can't fetch historical
        social media data. It returns current sentiment for all timestamps
        or uses cached historical data if available.

        For proper training, historical sentiment should be collected
        and stored in TimescaleDB over time.

        Args:
            symbol: Trading pair
            timestamps: List of timestamps to get features for
            price_changes: Optional list of price changes at each timestamp

        Returns:
            List of feature dictionaries
        """
        # For now, get current sentiment and repeat for all timestamps
        # In production, this should query historical sentiment from database
        current_features = await self.get_features_for_ml(symbol)

        features_list = []
        for i, ts in enumerate(timestamps):
            # Make a copy of current features
            features = current_features.copy()

            # If we have price changes, calculate divergence
            if price_changes and i < len(price_changes):
                fg_data = await self.fear_greed.get_current()
                features['sentiment_divergence'] = self.fear_greed.calculate_divergence(
                    fg_data.value,
                    price_changes[i]
                )

            features_list.append(features)

        return features_list
