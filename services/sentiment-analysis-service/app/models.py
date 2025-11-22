"""
Pydantic models for Sentiment Analysis Service
"""

from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


# Health check models
class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    service: str = "sentiment-analysis-service"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ReadyResponse(BaseModel):
    """Readiness check response"""
    ready: bool
    apis_configured: Dict[str, bool]


# News models
class NewsArticle(BaseModel):
    """Single news article"""
    title: str
    source: str
    url: Optional[str] = None
    published_at: datetime
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment score (-1 to 1)")
    sentiment_label: str = Field(..., description="POSITIVE, NEGATIVE, or NEUTRAL")


class NewsSentiment(BaseModel):
    """Aggregated news sentiment"""
    symbol: str
    total_articles: int
    articles: List[NewsArticle]

    # Aggregated scores
    average_sentiment: float = Field(..., ge=-1.0, le=1.0)
    sentiment_label: str = Field(..., description="BULLISH, BEARISH, or NEUTRAL")

    # Distribution
    positive_count: int
    negative_count: int
    neutral_count: int

    # Confidence
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in sentiment")

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Social media models
class SocialPost(BaseModel):
    """Single social media post"""
    platform: str = Field(..., description="twitter, reddit, telegram, etc.")
    text: str
    author: Optional[str] = None
    posted_at: datetime
    engagement_score: float = Field(default=0.0, description="Likes, upvotes, retweets, etc.")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0)
    sentiment_label: str


class SocialSentiment(BaseModel):
    """Aggregated social media sentiment"""
    symbol: str
    platform: str
    total_posts: int
    posts: List[SocialPost] = Field(default_factory=list, max_length=20)  # Return top 20 posts

    # Aggregated scores
    average_sentiment: float = Field(..., ge=-1.0, le=1.0)
    weighted_sentiment: float = Field(..., ge=-1.0, le=1.0, description="Weighted by engagement")
    sentiment_label: str

    # Distribution
    positive_count: int
    negative_count: int
    neutral_count: int

    # Engagement stats
    total_engagement: float
    average_engagement: float

    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Combined sentiment
class CombinedSentiment(BaseModel):
    """Combined sentiment from all sources"""
    symbol: str

    # Individual sentiments
    news_sentiment: Optional[NewsSentiment] = None
    social_sentiment: Optional[Dict[str, SocialSentiment]] = None  # Keyed by platform

    # Combined score
    overall_sentiment: float = Field(..., ge=-1.0, le=1.0, description="Weighted combined sentiment")
    sentiment_label: str = Field(..., description="BULLISH, BEARISH, or NEUTRAL")
    sentiment_strength: float = Field(..., ge=0.0, le=1.0, description="How strong is the sentiment")

    # Confidence
    confidence: float = Field(..., ge=0.0, le=1.0)
    data_quality: str = Field(..., description="EXCELLENT, GOOD, FAIR, POOR")

    # Trading signal
    trading_signal: str = Field(..., description="BUY, SELL, or HOLD")
    signal_strength: float = Field(..., ge=0.0, le=1.0)

    # Metadata
    sources_used: List[str]
    analysis_timestamp: datetime = Field(default_factory=datetime.utcnow)
    next_update_at: datetime


class SentimentTrend(BaseModel):
    """Sentiment trend over time"""
    symbol: str
    timeframe: str = Field(..., description="1h, 4h, 24h, etc.")

    # Historical data points
    timestamps: List[datetime]
    sentiment_scores: List[float]

    # Trend analysis
    trend_direction: str = Field(..., description="IMPROVING, DECLINING, or STABLE")
    trend_strength: float = Field(..., ge=0.0, le=1.0)

    # Statistics
    current_sentiment: float
    average_sentiment: float
    sentiment_volatility: float  # Standard deviation

    # Momentum
    momentum: str = Field(..., description="ACCELERATING, DECELERATING, or STEADY")

    generated_at: datetime = Field(default_factory=datetime.utcnow)


class SentimentAlert(BaseModel):
    """Sentiment alert for significant changes"""
    symbol: str
    alert_type: str = Field(..., description="SPIKE, DROP, REVERSAL, EXTREME")
    severity: str = Field(..., description="LOW, MEDIUM, HIGH, CRITICAL")

    # Details
    current_sentiment: float
    previous_sentiment: float
    change_magnitude: float

    description: str
    recommendation: str

    triggered_at: datetime = Field(default_factory=datetime.utcnow)
