"""
Configuration for Sentiment Analysis Service
Manages environment variables and service settings
"""

import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Service configuration with environment variables

    All sensitive data (API keys) should be loaded from .env file
    """

    # Service info
    service_name: str = "Sentiment Analysis Service"
    service_port: int = 8008
    environment: str = os.getenv("ENVIRONMENT", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # ===== External API Keys =====
    # These are optional and will be used if available
    # Service falls back to mock data if keys are not provided

    # NewsAPI.org - Fetch crypto news articles
    # Get key from: https://newsapi.org/
    # Rate limits: 100 req/day (free), 250 req/day (developer), 1000 req/day (business)
    news_api_key: str = os.getenv("NEWS_API_KEY", "")

    # Twitter API v2 - Fetch tweets for social sentiment
    # Get bearer token from: https://developer.twitter.com/
    # Rate limits: 450 requests per 15-min window (Essential access)
    twitter_bearer_token: str = os.getenv("TWITTER_BEARER_TOKEN", "")

    # Reddit API - Future integration (optional)
    # Get credentials from: https://www.reddit.com/prefs/apps
    reddit_client_id: str = os.getenv("REDDIT_CLIENT_ID", "")
    reddit_client_secret: str = os.getenv("REDDIT_CLIENT_SECRET", "")

    # ===== Sentiment Analysis Settings =====

    # Cache TTL for sentiment scores (in minutes)
    # Longer cache = fewer API calls but less fresh data
    sentiment_cache_ttl_minutes: int = 15

    # Minimum news articles required to calculate sentiment
    # Below this threshold, sentiment confidence is reduced
    min_news_count: int = 3

    # How many hours back to analyze sentiment
    # Longer period = more data but potentially less relevant
    sentiment_lookback_hours: int = 24

    # ===== Scoring Weights =====
    # These weights control how different sources influence combined sentiment
    # Should sum to 1.0 for proper weighted average

    # Weight for news sentiment in combined score
    news_weight: float = 0.4

    # Weight for social media sentiment in combined score
    social_weight: float = 0.3

    # Weight for technical indicators in combined score
    technical_weight: float = 0.3

    # ===== Sentiment Thresholds =====
    # These thresholds determine sentiment labels

    # Sentiment score above this = BULLISH label
    bullish_threshold: float = 0.6

    # Sentiment score below this = BEARISH label
    bearish_threshold: float = 0.4

    # Between bullish and bearish thresholds = NEUTRAL label

    class Config:
        """Pydantic configuration"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # Allow lowercase env vars


@lru_cache()
def get_settings() -> Settings:
    """
    Cached settings instance

    Using lru_cache ensures we only load settings once
    """
    return Settings()
