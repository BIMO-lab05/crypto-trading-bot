"""
Technical Indicators Module

This module provides various technical analysis indicators for
cryptocurrency trading signals. Each indicator follows consistent
patterns for calculation and signal generation.

Available Indicators:
- RSICalculator: Relative Strength Index
- MACDCalculator: Moving Average Convergence Divergence
- BollingerBandsCalculator: Bollinger Bands
- SMACalculator: Simple Moving Average
- EMACalculator: Exponential Moving Average
- SqueezeMomentumIndicator: Original Squeeze Momentum
- EnhancedSqueezeMomentum: Enhanced Squeeze Momentum with firing detection
- RSIDivergenceCalculator: RSI Divergence detection
- IchimokuCalculator: Ichimoku Cloud
- ADXCalculator: Average Directional Index (trend strength)
"""

from app.indicators.rsi import RSICalculator
from app.indicators.macd import MACDCalculator
from app.indicators.bollinger_bands import BollingerBandsCalculator
from app.indicators.moving_averages import SMACalculator, EMACalculator
from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.indicators.sqzmom_enhanced import (
    EnhancedSqueezeMomentum,
    SqueezeState,
    MomentumDirection,
    SqueezeMetadata,
    calculate_squeeze_momentum
)
from app.indicators.rsi_divergence import RSIDivergenceCalculator
from app.indicators.ichimoku import IchimokuCalculator
from app.indicators.adx import ADXCalculator, MarketRegime, TrendDirection

__all__ = [
    # Core indicators
    "RSICalculator",
    "MACDCalculator",
    "BollingerBandsCalculator",
    "SMACalculator",
    "EMACalculator",
    # Squeeze Momentum indicators
    "SqueezeMomentumIndicator",
    "EnhancedSqueezeMomentum",
    "SqueezeState",
    "MomentumDirection",
    "SqueezeMetadata",
    "calculate_squeeze_momentum",
    # Advanced indicators
    "RSIDivergenceCalculator",
    "IchimokuCalculator",
    # ADX (trend strength) indicator
    "ADXCalculator",
    "MarketRegime",
    "TrendDirection"
]
