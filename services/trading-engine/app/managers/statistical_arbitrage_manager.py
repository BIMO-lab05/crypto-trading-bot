"""
Statistical Arbitrage Strategy Manager

Orchestrates all Phase 2.2 statistical arbitrage strategies:
- Pairs Trading
- Funding Rate Arbitrage
- Triangular Arbitrage

Provides unified interface for:
- Strategy initialization and configuration
- Signal generation across all strategies
- Performance monitoring and reporting
- Risk management and position tracking

Author: Trading Bot Development Team
Date: 2025-12-07
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import numpy as np
import pandas as pd

from app.config import get_settings
from app.strategies.pairs_trading import PairsTradingStrategy, PairsTradeSignal
from app.strategies.funding_rate_arbitrage import FundingRateArbitrageStrategy, FundingRateSignal
from app.strategies.triangular_arbitrage import TriangularArbitrageStrategy, TriangularArbitrageSignal
from app.utils.statistical.cointegration import PairScanner

logger = logging.getLogger(__name__)


@dataclass
class StrategyAllocation:
    """Capital allocation across strategies"""
    pairs_trading: float = 0.4      # 40%
    funding_rate: float = 0.4        # 40%
    triangular: float = 0.2          # 20%

    def validate(self) -> bool:
        """Ensure allocations sum to 1.0"""
        total = self.pairs_trading + self.funding_rate + self.triangular
        return abs(total - 1.0) < 0.001


@dataclass
class PortfolioPerformance:
    """Aggregate performance metrics"""
    total_capital: float
    allocated_capital: float
    total_profit: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    sharpe_ratio: Optional[float]
    max_drawdown: float
    strategies_performance: Dict[str, Dict]


class StatisticalArbitrageManager:
    """
    Manager for all statistical arbitrage strategies

    Responsibilities:
    - Initialize and configure strategies
    - Allocate capital across strategies
    - Generate and aggregate signals
    - Monitor performance
    - Track positions and P&L

    Usage:
        manager = StatisticalArbitrageManager(total_capital=100.0)

        # Add strategies
        manager.add_pairs_strategy('BTCUSDT', 'ETHUSDT')
        manager.add_funding_strategy('BTCUSDT')
        manager.setup_triangular_arbitrage(['BTC', 'ETH', 'BNB', 'USDT'])

        # Generate signals
        signals = manager.generate_all_signals(market_data)

        # Get performance
        performance = manager.get_portfolio_performance()
    """

    def __init__(
        self,
        total_capital: Optional[float] = None,
        allocation: Optional[StrategyAllocation] = None,
        enable_pairs: bool = True,
        enable_funding: bool = True,
        enable_triangular: bool = True
    ):
        """
        Initialize Statistical Arbitrage Manager

        Args:
            total_capital: Total capital available for trading. Defaults to
                the configured paper-trading balance
                (PAPER_INITIAL_BALANCE).
            allocation: Capital allocation across strategies
            enable_pairs: Enable pairs trading strategies
            enable_funding: Enable funding rate arbitrage
            enable_triangular: Enable triangular arbitrage
        """
        # FIX 2026-08-03 (capital audit A2): the default was 10000.0, 100x the
        # real account. Resolved here rather than in the signature because
        # Python evaluates parameter defaults at MODULE IMPORT, which would
        # create an import-time settings dependency and freeze the value.
        if total_capital is None:
            total_capital = get_settings().paper_initial_balance

        self.total_capital = total_capital
        self.allocation = allocation or StrategyAllocation()

        if not self.allocation.validate():
            raise ValueError("Strategy allocations must sum to 1.0")

        # Strategy enablement
        self.enable_pairs = enable_pairs
        self.enable_funding = enable_funding
        self.enable_triangular = enable_triangular

        # Strategy storage
        self.pairs_strategies: Dict[str, PairsTradingStrategy] = {}
        self.funding_strategies: Dict[str, FundingRateArbitrageStrategy] = {}
        self.triangular_strategy: Optional[TriangularArbitrageStrategy] = None

        # Performance tracking
        self.signals_history: List[Dict] = []
        self.trades_executed: List[Dict] = []
        self.total_profit: float = 0.0

        logger.info(
            f"StatisticalArbitrageManager initialized: "
            f"Capital=${total_capital:,.2f}, "
            f"Allocation={asdict(self.allocation)}"
        )

    def add_pairs_strategy(
        self,
        symbol_x: str,
        symbol_y: str,
        **kwargs
    ) -> str:
        """
        Add a pairs trading strategy

        Args:
            symbol_x: Symbol for asset X
            symbol_y: Symbol for asset Y
            **kwargs: Additional parameters for PairsTradingStrategy

        Returns:
            Strategy ID (e.g., 'BTCUSDT_ETHUSDT')
        """
        if not self.enable_pairs:
            logger.warning("Pairs trading is disabled")
            return ""

        strategy_id = f"{symbol_x}_{symbol_y}"

        if strategy_id in self.pairs_strategies:
            logger.warning(f"Pairs strategy {strategy_id} already exists")
            return strategy_id

        strategy = PairsTradingStrategy(
            symbol_x=symbol_x,
            symbol_y=symbol_y,
            **kwargs
        )

        self.pairs_strategies[strategy_id] = strategy
        logger.info(f"Added pairs strategy: {strategy_id}")

        return strategy_id

    def add_funding_strategy(
        self,
        symbol: str,
        **kwargs
    ) -> str:
        """
        Add a funding rate arbitrage strategy

        Args:
            symbol: Trading symbol
            **kwargs: Additional parameters for FundingRateArbitrageStrategy

        Returns:
            Strategy ID (e.g., 'BTCUSDT_funding')
        """
        if not self.enable_funding:
            logger.warning("Funding rate arbitrage is disabled")
            return ""

        strategy_id = f"{symbol}_funding"

        if strategy_id in self.funding_strategies:
            logger.warning(f"Funding strategy {strategy_id} already exists")
            return strategy_id

        strategy = FundingRateArbitrageStrategy(
            symbol=symbol,
            **kwargs
        )

        self.funding_strategies[strategy_id] = strategy
        logger.info(f"Added funding strategy: {strategy_id}")

        return strategy_id

    def setup_triangular_arbitrage(
        self,
        assets: List[str],
        **kwargs
    ) -> bool:
        """
        Setup triangular arbitrage strategy

        Args:
            assets: List of assets for triangular paths
            **kwargs: Additional parameters for TriangularArbitrageStrategy

        Returns:
            True if setup successful, False otherwise
        """
        if not self.enable_triangular:
            logger.warning("Triangular arbitrage is disabled")
            return False

        if self.triangular_strategy is not None:
            logger.warning("Triangular strategy already exists")
            return False

        self.triangular_strategy = TriangularArbitrageStrategy(**kwargs)
        paths = self.triangular_strategy.discover_paths(assets)

        logger.info(f"Triangular arbitrage setup: {len(paths)} paths discovered")
        return len(paths) > 0

    def calibrate_pairs_strategy(
        self,
        strategy_id: str,
        historical_data_x: pd.Series,
        historical_data_y: pd.Series
    ) -> bool:
        """
        Calibrate a pairs trading strategy

        Args:
            strategy_id: Strategy ID (e.g., 'BTCUSDT_ETHUSDT')
            historical_data_x: Historical prices for asset X
            historical_data_y: Historical prices for asset Y

        Returns:
            True if calibration successful, False otherwise
        """
        if strategy_id not in self.pairs_strategies:
            logger.error(f"Strategy {strategy_id} not found")
            return False

        strategy = self.pairs_strategies[strategy_id]
        calibrated = strategy.calibrate(historical_data_x, historical_data_y)

        if calibrated:
            logger.info(
                f"✓ {strategy_id} calibrated: "
                f"hedge_ratio={strategy.hedge_ratio:.4f}, "
                f"half_life={strategy.half_life:.2f}"
            )
        else:
            logger.warning(f"✗ {strategy_id} calibration failed (not cointegrated)")

        return calibrated

    def generate_all_signals(
        self,
        market_data: Dict[str, Any]
    ) -> Dict[str, List]:
        """
        Generate signals from all enabled strategies

        Args:
            market_data: Dictionary containing all required market data:
                - pairs_data: Dict with pairs trading data
                - funding_data: Dict with funding rate data
                - triangular_prices: Dict with prices for triangular arb

        Returns:
            Dictionary with signals by strategy type:
                {
                    'pairs': [...],
                    'funding': [...],
                    'triangular': [...]
                }
        """
        signals = {
            'pairs': [],
            'funding': [],
            'triangular': []
        }

        # Pairs trading signals
        if self.enable_pairs:
            pairs_data = market_data.get('pairs_data', {})
            for strategy_id, strategy in self.pairs_strategies.items():
                try:
                    data = pairs_data.get(strategy_id, {})
                    if not data:
                        continue

                    signal = strategy.generate_signal(
                        current_price_x=data['current_price_x'],
                        current_price_y=data['current_price_y'],
                        historical_data_x=data['historical_data_x'],
                        historical_data_y=data['historical_data_y'],
                        portfolio_value=self.total_capital * self.allocation.pairs_trading
                    )

                    if signal and signal.action != 'HOLD':
                        signals['pairs'].append({
                            'strategy_id': strategy_id,
                            'signal': signal,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    logger.error(f"Error generating pairs signal for {strategy_id}: {e}")

        # Funding rate signals
        if self.enable_funding:
            funding_data = market_data.get('funding_data', {})
            for strategy_id, strategy in self.funding_strategies.items():
                try:
                    data = funding_data.get(strategy_id, {})
                    if not data:
                        continue

                    signal = strategy.generate_signal(
                        current_funding_rate=data['funding_rate'],
                        spot_price=data['spot_price'],
                        futures_price=data['futures_price'],
                        portfolio_value=self.total_capital * self.allocation.funding_rate
                    )

                    if signal and signal.action != 'HOLD':
                        signals['funding'].append({
                            'strategy_id': strategy_id,
                            'signal': signal,
                            'timestamp': datetime.now()
                        })

                except Exception as e:
                    logger.error(f"Error generating funding signal for {strategy_id}: {e}")

        # Triangular arbitrage signals
        if self.enable_triangular and self.triangular_strategy:
            try:
                triangular_prices = market_data.get('triangular_prices', {})
                if triangular_prices:
                    signal = self.triangular_strategy.generate_signal(
                        triangular_prices,
                        capital=self.total_capital * self.allocation.triangular
                    )

                    if signal:
                        signals['triangular'].append({
                            'strategy_id': 'triangular',
                            'signal': signal,
                            'timestamp': datetime.now()
                        })

            except Exception as e:
                logger.error(f"Error generating triangular signal: {e}")

        # Record signals
        total_signals = sum(len(s) for s in signals.values())
        if total_signals > 0:
            self.signals_history.append({
                'timestamp': datetime.now(),
                'signals': signals,
                'total_count': total_signals
            })

        logger.info(
            f"Generated {total_signals} signals: "
            f"Pairs={len(signals['pairs'])}, "
            f"Funding={len(signals['funding'])}, "
            f"Triangular={len(signals['triangular'])}"
        )

        return signals

    def record_trade_execution(
        self,
        strategy_type: str,
        strategy_id: str,
        signal: Any,
        execution_result: Dict
    ):
        """
        Record trade execution for performance tracking

        Args:
            strategy_type: 'pairs', 'funding', or 'triangular'
            strategy_id: Strategy identifier
            signal: Original signal that triggered trade
            execution_result: Execution results including P&L
        """
        trade_record = {
            'timestamp': datetime.now(),
            'strategy_type': strategy_type,
            'strategy_id': strategy_id,
            'signal': signal,
            'execution': execution_result,
            'profit': execution_result.get('profit', 0.0),
            'status': execution_result.get('status', 'unknown')
        }

        self.trades_executed.append(trade_record)

        if trade_record['profit'] != 0:
            self.total_profit += trade_record['profit']

        logger.info(
            f"Trade executed: {strategy_type}/{strategy_id}, "
            f"Profit=${trade_record['profit']:.2f}, "
            f"Total P&L=${self.total_profit:.2f}"
        )

    def get_portfolio_performance(self) -> PortfolioPerformance:
        """
        Calculate aggregate portfolio performance

        Returns:
            PortfolioPerformance with comprehensive metrics
        """
        # Calculate overall metrics
        total_trades = len(self.trades_executed)
        winning_trades = sum(1 for t in self.trades_executed if t['profit'] > 0)
        losing_trades = sum(1 for t in self.trades_executed if t['profit'] < 0)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        # Calculate allocated capital
        allocated = 0.0
        if self.pairs_strategies:
            allocated += self.total_capital * self.allocation.pairs_trading
        if self.funding_strategies:
            allocated += self.total_capital * self.allocation.funding_rate
        if self.triangular_strategy:
            allocated += self.total_capital * self.allocation.triangular

        # Get strategy-specific performance
        strategies_performance = {
            'pairs': self._get_pairs_performance(),
            'funding': self._get_funding_performance(),
            'triangular': self._get_triangular_performance()
        }

        sharpe_ratio, max_drawdown = self._compute_sharpe_and_drawdown()

        return PortfolioPerformance(
            total_capital=self.total_capital,
            allocated_capital=allocated,
            total_profit=self.total_profit,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            strategies_performance=strategies_performance
        )

    def _compute_sharpe_and_drawdown(self) -> tuple[Optional[float], float]:
        """
        Compute per-trade Sharpe ratio and maximum drawdown from
        ``self.trades_executed``.

        - Sharpe is the per-trade ratio: mean(return) / stdev(return),
          where return_i = profit_i / total_capital. NOT annualised — the
          DSR pipeline (PSR/DSR in risk-metrics-service) is the right tool
          for de-biased reporting; this value is the input.
        - Max drawdown is computed on the cumulative equity curve
          ``total_capital + cumsum(profits)`` and returned as a positive
          fraction (0.10 == 10% drawdown).

        Returns ``(None, 0.0)`` when there are fewer than two trades, when
        total_capital is non-positive, or when return variance is zero.
        """
        n = len(self.trades_executed)
        if n < 2 or self.total_capital <= 0:
            return None, 0.0

        profits = np.array(
            [float(t.get("profit", 0.0)) for t in self.trades_executed],
            dtype=float,
        )

        returns = profits / float(self.total_capital)
        std = float(np.std(returns, ddof=1))
        sharpe: Optional[float] = float(np.mean(returns) / std) if std > 0 else None

        equity = float(self.total_capital) + np.cumsum(profits)
        running_max = np.maximum.accumulate(equity)
        # Guard against running_max == 0 (cannot happen with positive
        # total_capital, but be defensive).
        with np.errstate(divide="ignore", invalid="ignore"):
            drawdowns = np.where(running_max > 0, (equity - running_max) / running_max, 0.0)
        max_drawdown = float(abs(np.min(drawdowns))) if drawdowns.size else 0.0

        return sharpe, max_drawdown

    def _get_pairs_performance(self) -> Dict:
        """Get performance metrics for pairs trading strategies"""
        performance = {}

        for strategy_id, strategy in self.pairs_strategies.items():
            status = strategy.get_status()
            trades = [t for t in self.trades_executed
                     if t['strategy_type'] == 'pairs' and t['strategy_id'] == strategy_id]

            performance[strategy_id] = {
                'current_position': status['current_position'],
                'is_cointegrated': status['is_cointegrated'],
                'needs_recalibration': status['needs_recalibration'],
                'total_trades': len(trades),
                'profit': sum(t['profit'] for t in trades)
            }

        return performance

    def _get_funding_performance(self) -> Dict:
        """Get performance metrics for funding rate strategies"""
        performance = {}

        for strategy_id, strategy in self.funding_strategies.items():
            status = strategy.get_status()
            trades = [t for t in self.trades_executed
                     if t['strategy_type'] == 'funding' and t['strategy_id'] == strategy_id]

            performance[strategy_id] = {
                'current_position': status['current_position'],
                'total_funding_collected': status['total_funding_collected'],
                'num_funding_payments': status['num_funding_payments'],
                'total_trades': len(trades),
                'profit': sum(t['profit'] for t in trades)
            }

        return performance

    def _get_triangular_performance(self) -> Dict:
        """Get performance metrics for triangular arbitrage"""
        if not self.triangular_strategy:
            return {}

        status = self.triangular_strategy.get_status()
        trades = [t for t in self.trades_executed if t['strategy_type'] == 'triangular']

        return {
            'total_arbitrages': status['total_arbitrages_executed'],
            'total_profit': status['total_profit'],
            'average_latency_ms': status['average_latency_ms'],
            'num_paths': status['num_paths_discovered'],
            'total_trades': len(trades)
        }

    def get_status_summary(self) -> Dict:
        """
        Get comprehensive status summary

        Returns:
            Dictionary with manager and all strategies status
        """
        performance = self.get_portfolio_performance()

        return {
            'manager': {
                'total_capital': self.total_capital,
                'allocated_capital': performance.allocated_capital,
                'total_profit': performance.total_profit,
                'total_trades': performance.total_trades,
                'win_rate': performance.win_rate,
            },
            'allocation': asdict(self.allocation),
            'strategies': {
                'pairs': {
                    'enabled': self.enable_pairs,
                    'count': len(self.pairs_strategies),
                    'strategy_ids': list(self.pairs_strategies.keys())
                },
                'funding': {
                    'enabled': self.enable_funding,
                    'count': len(self.funding_strategies),
                    'strategy_ids': list(self.funding_strategies.keys())
                },
                'triangular': {
                    'enabled': self.enable_triangular,
                    'configured': self.triangular_strategy is not None,
                    'num_paths': self.triangular_strategy.get_status()['num_paths_discovered']
                    if self.triangular_strategy else 0
                }
            },
            'performance': performance.strategies_performance,
            'signals_history_count': len(self.signals_history),
            'last_signal_time': self.signals_history[-1]['timestamp'].isoformat()
            if self.signals_history else None
        }

    def reset_performance(self):
        """Reset performance tracking (use with caution!)"""
        self.signals_history = []
        self.trades_executed = []
        self.total_profit = 0.0
        logger.warning("Performance tracking reset")
