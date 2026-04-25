"""
Feature Engineering Pipeline Module
Purpose: Comprehensive feature extraction for ML models
Author: Phase 6.4 Implementation
Date: 2025-12-11

This module provides production-grade feature pipeline that integrates:
- Price features (12 features)
- Technical indicators (15 features)
- Sentiment features (6 features) [Phase 6.1]
- Order book features (8 features) [Phase 6.2]
- Market regime features (9 features) [Phase 6.3]

Total: ~50 features for ML model input
"""

from app.pipeline.feature_pipeline import (
    FeaturePipeline,
    FeatureSet,
    PriceFeatures,
    TechnicalFeatures,
    SentimentFeatures,
    OrderBookFeatures,
    MarketRegime,
    ValidationResult,
    FeatureConfig,
)

from app.pipeline.sentiment_analyzer import SentimentAnalyzer
from app.pipeline.orderbook_extractor import OrderBookFeatureExtractor
from app.pipeline.regime_detector import MarketRegimeDetector

__all__ = [
    # Main pipeline
    "FeaturePipeline",
    "FeatureSet",
    "FeatureConfig",
    "ValidationResult",
    # Feature data classes
    "PriceFeatures",
    "TechnicalFeatures",
    "SentimentFeatures",
    "OrderBookFeatures",
    "MarketRegime",
    # Extractors
    "SentimentAnalyzer",
    "OrderBookFeatureExtractor",
    "MarketRegimeDetector",
]
