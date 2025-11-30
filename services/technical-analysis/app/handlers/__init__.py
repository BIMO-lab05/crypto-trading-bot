"""
Endpoint Handlers Package
Extracted from main.py using Strangler Fig pattern

This package contains all HTTP endpoint handlers for the technical-analysis service.
Handlers are thin orchestration layers that delegate business logic to service layer.

Architecture:
    Request -> Handler (this package) -> Service Layer -> Domain Logic
"""

from .health import health_check, readiness_check
from .indicators import (
    get_rsi,
    get_macd,
    get_bollinger_bands,
    get_sma,
    get_ema
)
from .advanced import (
    get_trend_filter,
    get_volume_confirmation,
    get_atr,
    get_stochastic,
    get_rsi_divergence,
    get_ichimoku,
    get_enhanced_sqzmom,
    get_adx
)
from .analysis import (
    get_aggregated_signal,
    get_multi_timeframe_analysis
)
from .sqzmom import (
    get_sqzmom,
    get_sqzmom_strategy_signal,
    get_sqzmom_backtest_data
)

__all__ = [
    # Health Endpoints
    "health_check",
    "readiness_check",
    # Basic Indicator Endpoints
    "get_rsi",
    "get_macd",
    "get_bollinger_bands",
    "get_sma",
    "get_ema",
    # Advanced Indicator Endpoints
    "get_trend_filter",
    "get_volume_confirmation",
    "get_atr",
    "get_stochastic",
    "get_rsi_divergence",
    "get_ichimoku",
    "get_enhanced_sqzmom",
    "get_adx",
    # Analysis Endpoints
    "get_aggregated_signal",
    "get_multi_timeframe_analysis",
    # Squeeze Momentum Endpoints
    "get_sqzmom",
    "get_sqzmom_strategy_signal",
    "get_sqzmom_backtest_data",
]
