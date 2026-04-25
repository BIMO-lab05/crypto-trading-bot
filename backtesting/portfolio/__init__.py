"""
Portfolio Backtesting Module
Phase 1.3 - Multi-Strategy Portfolio Testing

This module provides portfolio-level backtesting capabilities,
allowing multiple strategies to be tested simultaneously with
proper capital allocation and correlation analysis.
"""

from .portfolio_backtest import PortfolioBacktestEngine
from .strategy_allocation import StrategyAllocator

__all__ = ['PortfolioBacktestEngine', 'StrategyAllocator']
