"""
Sentiment Analysis Module for ML Prediction Service
Provides sentiment features to enhance ML model accuracy

Components:
- SentimentAnalyzer: Main analyzer combining multiple sources
- FearGreedIndex: Fear & Greed Index integration
- DataSources: Twitter, News, Reddit data fetchers

Author: Phase 6.1 Implementation
Date: 2025-12-11
"""

from .sentiment_analyzer import (
    SentimentAnalyzer,
    SentimentScore,
    SentimentFeatures,
    AggregatedSentiment
)
from .fear_greed import FearGreedIndex, FearGreedData
from .data_sources import (
    TwitterSentimentSource,
    NewsSentimentSource,
    RedditSentimentSource,
    SentimentDataSource
)

__all__ = [
    # Main analyzer
    'SentimentAnalyzer',
    'SentimentScore',
    'SentimentFeatures',
    'AggregatedSentiment',
    # Fear & Greed
    'FearGreedIndex',
    'FearGreedData',
    # Data sources
    'TwitterSentimentSource',
    'NewsSentimentSource',
    'RedditSentimentSource',
    'SentimentDataSource'
]
