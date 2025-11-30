"""
Trading Strategies Module
Purpose: Strategy implementations for automated trading

Available Strategies:
- SQZMOM: Squeeze Momentum strategy (optimized for SOLUSDT, DOGEUSDT, BNBUSDT)
- ResearchOptimizedStrategy: Research-backed strategy with:
  - RSI: Short-period (6) with 15/85 thresholds - 91% win rate in backtests
  - MACD: Confirmation filter, not primary signal
  - ADX: >25 for trend confirmation, regime-based strategy selection
  - ATR-Based Stops: 2x ATR instead of fixed percentage
  - Position Sizing: Quarter Kelly with volatility adjustment
  - Multi-Timeframe: 4:1 ratio, higher TF for trend, lower for entry

Updated: 2025-11-28
"""

from .sqzmom_config import sqzmom_config, SQZMOMConfig
from .sqzmom_strategy_integration import sqzmom_strategy, SQZMOMStrategy
from .research_optimized_strategy import (
    ResearchOptimizedStrategy,
    MarketCondition,
    SignalStrength,
    TradeSetup,
)

__all__ = [
    # SQZMOM Strategy
    "sqzmom_config",
    "SQZMOMConfig",
    "sqzmom_strategy",
    "SQZMOMStrategy",
    # Research-Optimized Strategy (2025-11-28)
    "ResearchOptimizedStrategy",
    "MarketCondition",
    "SignalStrength",
    "TradeSetup",
]
