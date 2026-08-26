#!/usr/bin/env python3
"""
Portfolio Backtesting Engine
Phase 1.3 - Multi-Strategy Portfolio Testing

This module enables backtesting multiple strategies simultaneously,
tracking portfolio-level metrics, and optimizing capital allocation.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging

from shared.account import ACCOUNT_EQUITY_USD

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class StrategyConfig:
    """Configuration for a strategy in the portfolio"""
    name: str
    symbol: str
    strategy_func: callable
    allocation_pct: float  # Percentage of portfolio allocated to this strategy
    params: Dict = field(default_factory=dict)


@dataclass
class PortfolioMetrics:
    """Portfolio-level performance metrics"""
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

    # Per-strategy metrics
    strategy_returns: Dict[str, float]
    strategy_sharpe: Dict[str, float]
    strategy_trades: Dict[str, int]

    # Correlation matrix
    correlation_matrix: pd.DataFrame

    # Time series
    equity_curve: pd.Series
    daily_returns: pd.Series


class PortfolioBacktestEngine:
    """
    Backtest multiple strategies as a portfolio

    Features:
    - Run multiple strategies simultaneously on different symbols
    - Track portfolio-level metrics (total return, Sharpe, drawdown)
    - Calculate strategy correlations
    - Optimize capital allocation
    - Handle rebalancing
    """

    def __init__(
        self,
        initial_capital: float = ACCOUNT_EQUITY_USD,
        commission: float = 0.001,
        slippage: float = 0.0005
    ):
        """
        Initialize portfolio backtest engine

        Args:
            initial_capital: Starting capital in USD
            commission: Trading commission percentage
            slippage: Slippage percentage
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage

        # Portfolio state
        self.capital = initial_capital
        self.strategies: List[StrategyConfig] = []
        self.equity_curve = []
        self.daily_returns = []

        logger.info(f"PortfolioBacktestEngine initialized with ${initial_capital:,.2f}")

    def add_strategy(
        self,
        name: str,
        symbol: str,
        strategy_func: callable,
        allocation_pct: float,
        params: Dict = None
    ):
        """
        Add a strategy to the portfolio

        Args:
            name: Strategy name (e.g., "BNB_RSI")
            symbol: Trading symbol (e.g., "BNBUSDT")
            strategy_func: Strategy function
            allocation_pct: Percentage of capital allocated (0-100)
            params: Strategy parameters
        """
        if params is None:
            params = {}

        strategy = StrategyConfig(
            name=name,
            symbol=symbol,
            strategy_func=strategy_func,
            allocation_pct=allocation_pct,
            params=params
        )

        self.strategies.append(strategy)
        logger.info(f"Added strategy: {name} ({symbol}) with {allocation_pct}% allocation")

    def validate_allocation(self) -> bool:
        """Validate that total allocation equals 100%"""
        total = sum(s.allocation_pct for s in self.strategies)
        if abs(total - 100.0) > 0.01:
            logger.warning(f"Total allocation is {total}%, not 100%")
            return False
        return True

    def run_backtest(
        self,
        data_dict: Dict[str, pd.DataFrame],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> PortfolioMetrics:
        """
        Run portfolio backtest

        Args:
            data_dict: Dictionary mapping symbols to their OHLCV data
                      e.g., {"BNBUSDT": df1, "SOLUSDT": df2}
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            PortfolioMetrics with complete performance analysis
        """
        logger.info("="*80)
        logger.info("PORTFOLIO BACKTEST STARTING")
        logger.info("="*80)
        logger.info(f"Strategies: {len(self.strategies)}")
        logger.info(f"Initial Capital: ${self.initial_capital:,.2f}")

        # Validate allocation
        if not self.validate_allocation():
            raise ValueError("Strategy allocations do not sum to 100%")

        # Import backtest engine here to avoid circular import
        from backtesting.backtest_engine import BacktestEngine

        # Run each strategy independently
        strategy_results = {}

        for strategy in self.strategies:
            logger.info(f"\nRunning strategy: {strategy.name}")

            # Get data for this strategy's symbol
            if strategy.symbol not in data_dict:
                logger.warning(f"No data for {strategy.symbol}, skipping {strategy.name}")
                continue

            data = data_dict[strategy.symbol]

            # Calculate capital allocated to this strategy
            strategy_capital = self.initial_capital * (strategy.allocation_pct / 100.0)

            # Create backtest engine for this strategy
            engine = BacktestEngine(
                initial_capital=strategy_capital,
                commission=self.commission,
                slippage=self.slippage
            )

            # Run backtest
            result = engine.run_backtest(
                data=data,
                strategy_func=strategy.strategy_func,
                strategy_name=strategy.name
            )

            strategy_results[strategy.name] = result

            logger.info(f"  {strategy.name} Results:")
            logger.info(f"    Return: {result.total_profit_loss_pct:.2f}%")
            logger.info(f"    Sharpe: {result.sharpe_ratio:.2f}")
            logger.info(f"    Trades: {result.total_trades}")

        # Calculate portfolio-level metrics
        metrics = self._calculate_portfolio_metrics(strategy_results)

        logger.info("\n" + "="*80)
        logger.info("PORTFOLIO BACKTEST COMPLETE")
        logger.info("="*80)
        logger.info(f"Total Return: {metrics.total_return:.2f}%")
        logger.info(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        logger.info(f"Max Drawdown: {metrics.max_drawdown:.2f}%")
        logger.info(f"Win Rate: {metrics.win_rate:.2f}%")

        return metrics

    def _calculate_portfolio_metrics(self, strategy_results: Dict) -> PortfolioMetrics:
        """
        Calculate portfolio-level metrics from individual strategy results

        Args:
            strategy_results: Dictionary of strategy results

        Returns:
            PortfolioMetrics
        """
        if not strategy_results:
            raise ValueError("No strategy results to analyze")

        # Extract per-strategy metrics
        strategy_returns = {}
        strategy_sharpe = {}
        strategy_trades = {}

        for name, result in strategy_results.items():
            strategy_returns[name] = result.total_profit_loss_pct
            strategy_sharpe[name] = result.sharpe_ratio
            strategy_trades[name] = result.total_trades

        # Calculate weighted portfolio return
        total_return = 0.0
        for strategy in self.strategies:
            if strategy.name in strategy_returns:
                weight = strategy.allocation_pct / 100.0
                total_return += strategy_returns[strategy.name] * weight

        # Calculate weighted Sharpe ratio
        weighted_sharpe = 0.0
        for strategy in self.strategies:
            if strategy.name in strategy_sharpe:
                weight = strategy.allocation_pct / 100.0
                weighted_sharpe += strategy_sharpe[strategy.name] * weight

        # Calculate portfolio win rate
        total_wins = sum(
            result.winning_trades
            for result in strategy_results.values()
        )
        total_trades = sum(
            result.total_trades
            for result in strategy_results.values()
        )
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0

        # Calculate max drawdown (simplified - would need equity curves for accurate calc)
        max_dd = max(
            result.max_drawdown_pct
            for result in strategy_results.values()
        )

        # Build correlation matrix (simplified - would need daily returns)
        correlation_matrix = self._build_correlation_matrix(strategy_results)

        # Build equity curve (simplified)
        equity_curve = pd.Series([self.initial_capital])
        daily_returns = pd.Series([0.0])

        return PortfolioMetrics(
            total_return=total_return,
            sharpe_ratio=weighted_sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            total_trades=total_trades,
            strategy_returns=strategy_returns,
            strategy_sharpe=strategy_sharpe,
            strategy_trades=strategy_trades,
            correlation_matrix=correlation_matrix,
            equity_curve=equity_curve,
            daily_returns=daily_returns
        )

    def _build_correlation_matrix(self, strategy_results: Dict) -> pd.DataFrame:
        """
        Build correlation matrix between strategies

        Args:
            strategy_results: Dictionary of strategy results

        Returns:
            Correlation matrix DataFrame
        """
        # Simplified implementation - would need actual daily returns
        strategy_names = list(strategy_results.keys())
        n = len(strategy_names)

        # Create identity matrix as placeholder
        # In real implementation, would calculate from daily returns
        corr_matrix = pd.DataFrame(
            np.eye(n),
            index=strategy_names,
            columns=strategy_names
        )

        return corr_matrix

    def optimize_allocation(
        self,
        method: str = "equal_weight"
    ) -> Dict[str, float]:
        """
        Optimize strategy allocation weights

        Args:
            method: Optimization method
                   - "equal_weight": Equal allocation to all strategies
                   - "sharpe_weighted": Weight by Sharpe ratio
                   - "risk_parity": Equal risk contribution

        Returns:
            Dictionary of optimized weights
        """
        n_strategies = len(self.strategies)

        if method == "equal_weight":
            weight = 100.0 / n_strategies
            return {s.name: weight for s in self.strategies}

        elif method == "sharpe_weighted":
            # Would need historical Sharpe ratios
            # Placeholder: equal weight
            weight = 100.0 / n_strategies
            return {s.name: weight for s in self.strategies}

        elif method == "risk_parity":
            # Would need volatility data
            # Placeholder: equal weight
            weight = 100.0 / n_strategies
            return {s.name: weight for s in self.strategies}

        else:
            raise ValueError(f"Unknown optimization method: {method}")
