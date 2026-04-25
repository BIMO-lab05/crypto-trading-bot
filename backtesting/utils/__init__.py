"""
Backtesting Utilities
Created: 2025-12-06
Purpose: Supporting utilities for advanced backtesting

This module provides utility tools for:
- Portfolio-level backtesting (multiple strategies simultaneously)
- Strategy correlation analysis
- Capital allocation optimization
- Performance attribution
"""

__version__ = "1.0.0"
__author__ = "Crypto Trading Bot - Phase 1 Enhancement"

from .portfolio_backtest import PortfolioBacktester
from .strategy_correlation import StrategyCorrelationAnalyzer
from .capital_allocation import CapitalAllocationOptimizer

__all__ = [
    'PortfolioBacktester',
    'StrategyCorrelationAnalyzer',
    'CapitalAllocationOptimizer',
]
