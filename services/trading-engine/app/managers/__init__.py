"""
Managers Module

Strategy and portfolio managers for orchestrating trading strategies.

Author: Trading Bot Development Team
Date: 2025-12-07
"""

from .statistical_arbitrage_manager import (
    StatisticalArbitrageManager,
    StrategyAllocation,
    PortfolioPerformance,
)

__all__ = [
    "StatisticalArbitrageManager",
    "StrategyAllocation",
    "PortfolioPerformance",
]
