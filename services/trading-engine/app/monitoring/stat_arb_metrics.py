"""
Statistical Arbitrage Prometheus Metrics Module

Purpose: Expose Prometheus metrics for Statistical Arbitrage paper trading
Author: DevOps Automation Agent
Date: 2025-12-11

Metrics Exposed:
- stat_arb_total_capital: Total capital allocated to stat arb
- stat_arb_allocated_capital: Currently allocated capital
- stat_arb_total_profit: Total profit/loss
- stat_arb_total_trades: Total number of trades
- stat_arb_win_rate: Win rate percentage
- stat_arb_signals_generated: Number of signals generated
- stat_arb_strategy_count: Number of active strategies by type
- stat_arb_strategy_profit: Profit by strategy
"""

import logging
from typing import Dict, Any, Optional
from prometheus_client import Gauge, Counter, Histogram, Info

logger = logging.getLogger(__name__)

# ============================================================================
# Prometheus Metrics Definition
# ============================================================================

# Manager-level metrics
stat_arb_total_capital = Gauge(
    'stat_arb_total_capital',
    'Total capital allocated to statistical arbitrage (USD)'
)

stat_arb_allocated_capital = Gauge(
    'stat_arb_allocated_capital',
    'Currently allocated capital (USD)'
)

stat_arb_available_capital = Gauge(
    'stat_arb_available_capital',
    'Available capital for new trades (USD)'
)

stat_arb_total_profit = Gauge(
    'stat_arb_total_profit',
    'Total profit/loss from statistical arbitrage (USD)'
)

stat_arb_roi_percent = Gauge(
    'stat_arb_roi_percent',
    'Return on investment percentage'
)

stat_arb_total_trades = Counter(
    'stat_arb_total_trades',
    'Total number of trades executed'
)

stat_arb_winning_trades = Counter(
    'stat_arb_winning_trades',
    'Number of winning trades'
)

stat_arb_losing_trades = Counter(
    'stat_arb_losing_trades',
    'Number of losing trades'
)

stat_arb_win_rate = Gauge(
    'stat_arb_win_rate',
    'Win rate percentage'
)

# Signal metrics
stat_arb_signals_generated = Counter(
    'stat_arb_signals_generated',
    'Number of signals generated',
    ['strategy_type']
)

stat_arb_signals_executed = Counter(
    'stat_arb_signals_executed',
    'Number of signals that resulted in trades',
    ['strategy_type']
)

stat_arb_signals_rejected = Counter(
    'stat_arb_signals_rejected',
    'Number of signals rejected (e.g., below threshold)',
    ['strategy_type', 'reason']
)

# Strategy-level metrics
stat_arb_strategy_count = Gauge(
    'stat_arb_strategy_count',
    'Number of active strategies',
    ['strategy_type']
)

stat_arb_strategy_profit = Gauge(
    'stat_arb_strategy_profit',
    'Profit by strategy',
    ['strategy_id', 'strategy_type']
)

stat_arb_strategy_trades = Gauge(
    'stat_arb_strategy_trades',
    'Number of trades by strategy',
    ['strategy_id', 'strategy_type']
)

stat_arb_strategy_win_rate = Gauge(
    'stat_arb_strategy_win_rate',
    'Win rate by strategy',
    ['strategy_id', 'strategy_type']
)

# Pairs Trading specific metrics
stat_arb_pairs_zscore = Gauge(
    'stat_arb_pairs_zscore',
    'Current Z-score for pairs trading strategy',
    ['strategy_id']
)

stat_arb_pairs_spread = Gauge(
    'stat_arb_pairs_spread',
    'Current spread for pairs trading strategy',
    ['strategy_id']
)

stat_arb_pairs_hedge_ratio = Gauge(
    'stat_arb_pairs_hedge_ratio',
    'Hedge ratio for pairs trading strategy',
    ['strategy_id']
)

stat_arb_pairs_cointegration = Gauge(
    'stat_arb_pairs_cointegration',
    'Cointegration status (1=cointegrated, 0=not)',
    ['strategy_id']
)

# Funding Rate specific metrics
stat_arb_funding_rate = Gauge(
    'stat_arb_funding_rate',
    'Current funding rate for symbol',
    ['symbol']
)

stat_arb_funding_annualized_yield = Gauge(
    'stat_arb_funding_annualized_yield',
    'Annualized yield from funding rate arbitrage',
    ['symbol']
)

stat_arb_funding_basis_pct = Gauge(
    'stat_arb_funding_basis_pct',
    'Current basis percentage (spot vs futures)',
    ['symbol']
)

# Triangular Arbitrage specific metrics
stat_arb_triangular_paths = Gauge(
    'stat_arb_triangular_paths',
    'Number of triangular arbitrage paths discovered'
)

stat_arb_triangular_opportunity = Gauge(
    'stat_arb_triangular_opportunity',
    'Current triangular arbitrage opportunity profit percentage',
    ['path']
)

stat_arb_triangular_latency_ms = Histogram(
    'stat_arb_triangular_latency_ms',
    'Execution latency for triangular arbitrage (ms)',
    buckets=[10, 25, 50, 75, 100, 150, 200, 500, 1000]
)

# Performance metrics
stat_arb_sharpe_ratio = Gauge(
    'stat_arb_sharpe_ratio',
    'Sharpe ratio of the portfolio'
)

stat_arb_max_drawdown = Gauge(
    'stat_arb_max_drawdown',
    'Maximum drawdown percentage'
)

# Manager info
stat_arb_manager_info = Info(
    'stat_arb_manager',
    'Statistical Arbitrage Manager information'
)

# ============================================================================
# Metrics Update Functions
# ============================================================================


class StatArbMetricsCollector:
    """
    Collector class to update Prometheus metrics from StatisticalArbitrageManager
    """

    def __init__(self):
        """Initialize metrics collector"""
        self.last_total_trades = 0
        self.last_winning_trades = 0
        self.last_losing_trades = 0
        logger.info("StatArbMetricsCollector initialized")

    def update_from_manager(self, manager) -> None:
        """
        Update all metrics from StatisticalArbitrageManager

        Args:
            manager: StatisticalArbitrageManager instance
        """
        if manager is None:
            logger.warning("Manager is None, skipping metrics update")
            return

        try:
            # Get status summary
            status = manager.get_status_summary()

            # Update manager-level metrics
            self._update_manager_metrics(status)

            # Update strategy counts
            self._update_strategy_counts(status)

            # Update performance metrics
            self._update_performance_metrics(status)

            # Update individual strategy metrics
            self._update_pairs_metrics(manager)
            self._update_funding_metrics(manager)
            self._update_triangular_metrics(manager)

            logger.debug("Metrics updated successfully")

        except Exception as e:
            logger.error(f"Error updating metrics: {e}")

    def _update_manager_metrics(self, status: Dict[str, Any]) -> None:
        """Update manager-level metrics"""
        manager_data = status.get('manager', {})

        total_capital = manager_data.get('total_capital', 0)
        allocated = manager_data.get('allocated_capital', 0)
        profit = manager_data.get('total_profit', 0)
        trades = manager_data.get('total_trades', 0)
        win_rate = manager_data.get('win_rate', 0)

        stat_arb_total_capital.set(total_capital)
        stat_arb_allocated_capital.set(allocated)
        stat_arb_available_capital.set(total_capital - allocated)
        stat_arb_total_profit.set(profit)
        stat_arb_win_rate.set(win_rate * 100)

        # ROI calculation
        if total_capital > 0:
            roi = (profit / total_capital) * 100
            stat_arb_roi_percent.set(roi)

        # Update trade counters (only increment by difference)
        if trades > self.last_total_trades:
            new_trades = trades - self.last_total_trades
            stat_arb_total_trades._value._value += new_trades
            self.last_total_trades = trades

        # Manager info
        allocation = status.get('allocation', {})
        stat_arb_manager_info.info({
            'pairs_allocation': str(allocation.get('pairs_trading', 0)),
            'funding_allocation': str(allocation.get('funding_rate', 0)),
            'triangular_allocation': str(allocation.get('triangular', 0))
        })

    def _update_strategy_counts(self, status: Dict[str, Any]) -> None:
        """Update strategy count metrics"""
        strategies = status.get('strategies', {})

        # Pairs count
        pairs = strategies.get('pairs', {})
        stat_arb_strategy_count.labels(strategy_type='pairs').set(
            pairs.get('count', 0)
        )

        # Funding count
        funding = strategies.get('funding', {})
        stat_arb_strategy_count.labels(strategy_type='funding').set(
            funding.get('count', 0)
        )

        # Triangular paths count
        triangular = strategies.get('triangular', {})
        stat_arb_strategy_count.labels(strategy_type='triangular').set(
            triangular.get('num_paths', 0)
        )
        stat_arb_triangular_paths.set(triangular.get('num_paths', 0))

    def _update_performance_metrics(self, status: Dict[str, Any]) -> None:
        """Update performance-related metrics"""
        performance = status.get('performance', {})

        # Update by strategy type
        for strategy_type in ['pairs', 'funding', 'triangular']:
            type_perf = performance.get(strategy_type, {})
            for strategy_id, perf_data in type_perf.items():
                profit = perf_data.get('total_profit', 0)
                trades = perf_data.get('trades', 0)
                win_rate = perf_data.get('win_rate', 0)

                stat_arb_strategy_profit.labels(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type
                ).set(profit)

                stat_arb_strategy_trades.labels(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type
                ).set(trades)

                stat_arb_strategy_win_rate.labels(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type
                ).set(win_rate * 100)

    def _update_pairs_metrics(self, manager) -> None:
        """Update pairs trading specific metrics"""
        if not hasattr(manager, 'pairs_strategies'):
            return

        for strategy_id, strategy in manager.pairs_strategies.items():
            try:
                status = strategy.get_status()

                # Z-score
                if status.get('current_z_score') is not None:
                    stat_arb_pairs_zscore.labels(
                        strategy_id=strategy_id
                    ).set(status['current_z_score'])

                # Spread
                if status.get('current_spread') is not None:
                    stat_arb_pairs_spread.labels(
                        strategy_id=strategy_id
                    ).set(status['current_spread'])

                # Hedge ratio
                if status.get('hedge_ratio') is not None:
                    stat_arb_pairs_hedge_ratio.labels(
                        strategy_id=strategy_id
                    ).set(status['hedge_ratio'])

                # Cointegration status
                is_cointegrated = 1 if status.get('is_cointegrated', False) else 0
                stat_arb_pairs_cointegration.labels(
                    strategy_id=strategy_id
                ).set(is_cointegrated)

            except Exception as e:
                logger.debug(f"Error updating pairs metrics for {strategy_id}: {e}")

    def _update_funding_metrics(self, manager) -> None:
        """Update funding rate specific metrics"""
        if not hasattr(manager, 'funding_strategies'):
            return

        for strategy_id, strategy in manager.funding_strategies.items():
            try:
                status = strategy.get_status()
                symbol = status.get('symbol', strategy_id)

                # Current funding rate
                if status.get('current_funding_rate') is not None:
                    stat_arb_funding_rate.labels(symbol=symbol).set(
                        status['current_funding_rate']
                    )

                # Annualized yield
                if status.get('annualized_yield') is not None:
                    stat_arb_funding_annualized_yield.labels(symbol=symbol).set(
                        status['annualized_yield'] * 100
                    )

                # Basis percentage
                if status.get('current_basis_pct') is not None:
                    stat_arb_funding_basis_pct.labels(symbol=symbol).set(
                        status['current_basis_pct']
                    )

            except Exception as e:
                logger.debug(f"Error updating funding metrics for {strategy_id}: {e}")

    def _update_triangular_metrics(self, manager) -> None:
        """Update triangular arbitrage specific metrics"""
        if not hasattr(manager, 'triangular_strategy') or manager.triangular_strategy is None:
            return

        try:
            strategy = manager.triangular_strategy

            # Number of paths
            if hasattr(strategy, 'triangular_paths'):
                stat_arb_triangular_paths.set(len(strategy.triangular_paths))

            # Current opportunities (if available)
            if hasattr(strategy, 'last_opportunities'):
                for opportunity in strategy.last_opportunities:
                    path_str = ' -> '.join(opportunity.get('path', []))
                    profit = opportunity.get('profit_pct', 0)
                    stat_arb_triangular_opportunity.labels(
                        path=path_str
                    ).set(profit * 100)

        except Exception as e:
            logger.debug(f"Error updating triangular metrics: {e}")

    def record_signal(self, strategy_type: str, executed: bool = False,
                      rejected: bool = False, rejection_reason: str = "") -> None:
        """
        Record a signal generation event

        Args:
            strategy_type: Type of strategy (pairs, funding, triangular)
            executed: Whether the signal resulted in a trade
            rejected: Whether the signal was rejected
            rejection_reason: Reason for rejection if applicable
        """
        stat_arb_signals_generated.labels(strategy_type=strategy_type).inc()

        if executed:
            stat_arb_signals_executed.labels(strategy_type=strategy_type).inc()

        if rejected:
            stat_arb_signals_rejected.labels(
                strategy_type=strategy_type,
                reason=rejection_reason
            ).inc()

    def record_triangular_execution(self, latency_ms: float) -> None:
        """Record triangular arbitrage execution latency"""
        stat_arb_triangular_latency_ms.observe(latency_ms)

    def update_sharpe_ratio(self, value: float) -> None:
        """Update Sharpe ratio metric"""
        stat_arb_sharpe_ratio.set(value)

    def update_max_drawdown(self, value: float) -> None:
        """Update max drawdown metric"""
        stat_arb_max_drawdown.set(value * 100)


# Global metrics collector instance
_metrics_collector: Optional[StatArbMetricsCollector] = None


def get_metrics_collector() -> StatArbMetricsCollector:
    """
    Get or create the global metrics collector instance

    Returns:
        StatArbMetricsCollector instance
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = StatArbMetricsCollector()
    return _metrics_collector


def update_metrics_from_manager(manager) -> None:
    """
    Convenience function to update metrics from manager

    Args:
        manager: StatisticalArbitrageManager instance
    """
    collector = get_metrics_collector()
    collector.update_from_manager(manager)
