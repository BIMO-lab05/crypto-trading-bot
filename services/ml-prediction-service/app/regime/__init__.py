"""
Market Regime Detection Module
Classifies market conditions (trending/ranging/volatile) for adaptive ML models

Author: Phase 6.3 ML Team
Date: 2025-12-11
Version: 1.0.0
"""

from .regime_detector import (
    MarketRegimeDetector,
    MarketRegime,
    TrendRegime,
    VolatilityRegime,
    VolumeRegime,
    RegimeHistory,
    RegimeTransitionMatrix,
)

from .hmm_detector import (
    HMMRegimeDetector,
    HMMRegimeState,
)

__all__ = [
    # Main detector class
    'MarketRegimeDetector',

    # Data models
    'MarketRegime',
    'TrendRegime',
    'VolatilityRegime',
    'VolumeRegime',
    'RegimeHistory',
    'RegimeTransitionMatrix',

    # HMM detector (optional enhancement)
    'HMMRegimeDetector',
    'HMMRegimeState',
]
