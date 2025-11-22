"""
Trading Strategies Module
Purpose: Strategy implementations for automated trading

Available Strategies:
- SQZMOM: Squeeze Momentum strategy (optimized for SOLUSDT, DOGEUSDT, BNBUSDT)
"""

from .sqzmom_config import sqzmom_config, SQZMOMConfig
from .sqzmom_strategy_integration import sqzmom_strategy, SQZMOMStrategy

__all__ = [
    "sqzmom_config",
    "SQZMOMConfig",
    "sqzmom_strategy",
    "SQZMOMStrategy"
]
