"""
Trading Strategies Module
Phase 2 - Strategy Enhancement

This module contains various trading strategies for backtesting:
- multi_indicator_strategy: Combines RSI, MACD, and Bollinger Bands (trend-following)
- mean_reversion_strategy: Bollinger Band bounces with RSI confirmation (mean reversion)
"""

from .multi_indicator_strategy import (
    MultiIndicatorStrategy,
    StrategyConfig,
    IndicatorValues,
    Signal,
    create_multi_indicator_strategy
)

from .mean_reversion_strategy import (
    MeanReversionStrategy,
    MeanReversionConfig,
    create_mean_reversion_strategy
)

__all__ = [
    'MultiIndicatorStrategy',
    'StrategyConfig',
    'IndicatorValues',
    'Signal',
    'create_multi_indicator_strategy',
    'MeanReversionStrategy',
    'MeanReversionConfig',
    'create_mean_reversion_strategy'
]
