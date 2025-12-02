"""
Backtesting Framework for Crypto Trading Bot
Research-backed implementation for strategy validation (2025-12-02)

Features:
- Event-driven backtesting engine
- Realistic order execution simulation
- Slippage and commission modeling
- Performance metrics (Sharpe, Sortino, Max Drawdown, etc.)
- Walk-forward optimization support
- Multi-timeframe strategy testing
"""

from app.backtesting.backtest_engine import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    Trade,
    Position,
    OrderType,
    OrderSide
)

from app.backtesting.strategy_base import (
    StrategyBase,
    Signal,
    SignalType
)

from app.backtesting.performance_metrics import (
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_max_drawdown,
    calculate_win_rate,
    calculate_profit_factor,
    PerformanceMetrics
)

from app.backtesting.data_provider import (
    DataProviderBase,
    DataProviderError,
    RealDataProvider,
    CachedDataProvider,
    create_data_provider
)

__all__ = [
    "BacktestEngine",
    "BacktestConfig",
    "BacktestResult",
    "Trade",
    "Position",
    "OrderType",
    "OrderSide",
    "StrategyBase",
    "Signal",
    "SignalType",
    "calculate_sharpe_ratio",
    "calculate_sortino_ratio",
    "calculate_max_drawdown",
    "calculate_win_rate",
    "calculate_profit_factor",
    "PerformanceMetrics",
    "DataProviderBase",
    "DataProviderError",
    "RealDataProvider",
    "CachedDataProvider",
    "create_data_provider"
]
