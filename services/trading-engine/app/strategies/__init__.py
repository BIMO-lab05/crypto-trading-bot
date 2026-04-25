"""
Trading Strategies Module
Purpose: Strategy implementations for automated trading

=============================================================================
Phase 9: Multi-Strategy Orchestration System (2025-12-11)
=============================================================================

NEW Components:
- StrategyBase: Abstract base class for all strategies
- MeanReversionStrategy: Trade price reversions to statistical mean
- TrendFollowingStrategy: Follow market trends using EMAs
- BreakoutStrategy: Trade breakouts from consolidation
- ArbitrageStrategy: Statistical arbitrage on correlated pairs
- SignalAggregator: Combine signals from multiple strategies
- StrategyCoordinator: Coordinate signal flow and risk budget
- StrategyBacktester: Historical simulation framework

Available Strategies:

Technical Analysis Strategies:
- SQZMOM: Squeeze Momentum strategy (optimized for SOLUSDT, DOGEUSDT, BNBUSDT)
- ResearchOptimizedStrategy: Research-backed strategy with:
  - RSI: Short-period (6) with 15/85 thresholds - 91% win rate in backtests
  - MACD: Confirmation filter, not primary signal
  - ADX: >25 for trend confirmation, regime-based strategy selection
  - ATR-Based Stops: 2x ATR instead of fixed percentage
  - Position Sizing: Quarter Kelly with volatility adjustment
  - Multi-Timeframe: 4:1 ratio, higher TF for trend, lower for entry
- SupportResistanceStrategy: S/R level trading with:
  - Multi-touch S/R detection for high-probability zones
  - RSI confirmation for entry timing
  - EMA trend alignment filter
  - Volume confirmation
  - ATR-based dynamic stops
  - Take profit at next S/R level

Statistical Arbitrage Strategies (Phase 2.2):
- PairsTradingStrategy: Mean reversion trading on cointegrated pairs
  - Engle-Granger cointegration testing
  - Z-score based entry/exit signals
  - Automatic recalibration
  - Hedge ratio management
- FundingRateArbitrageStrategy: Collect funding payments via hedged positions
  - Spot + Futures hedge
  - Funding rate monitoring (8h intervals)
  - Basis risk management
  - Annualized yield calculation
- TriangularArbitrageStrategy: Exploit circular price inefficiencies
  - Automated path discovery
  - Real-time arbitrage detection
  - Ultra-low latency execution
  - Profit calculation with fees

Grid Trading Strategies (Phase 2.3):
- GridTradingStrategy: Basic grid trading for ranging markets
  - ATR-based dynamic grid spacing
  - Market regime detection with ADX
  - Multiple position management
- GridTradingStrategyV2: Enhanced grid trading with dynamic grid levels
  - Dynamic grid calculation (ATR/Bollinger/Geometric/Arithmetic)
  - Comprehensive market regime detection
  - Volatility-adaptive grid spacing
  - Per-level performance tracking
  - Smart rebalancing with multiple triggers
  - Grid-wide and per-level risk management

Momentum Trading Strategies (Phase 2.4):
- MomentumBreakoutStrategy: Capture breakouts from consolidation ranges
  - Bollinger Band squeeze detection (BB inside Keltner Channel)
  - Volume confirmation (1.5x+ average required)
  - ADX trend strength measurement
  - Multi-indicator momentum confirmation (RSI, MACD, ROC)
  - Measured move targets (2x range height)
  - ATR-based trailing stops after 1R profit
- TrendFollowingStrategy (existing): Trade pullbacks in established trends
  - Multi-timeframe trend alignment (EMA 20/50/200)
  - Pullback entry at key EMAs
  - RSI oversold/overbought in trending markets
  - Pyramiding logic for adding to winners
  - Fibonacci extension targets (161.8%, 261.8%, 423.6%)
  - Parabolic SAR trailing stop alternative

Phase 9 Strategies (Multi-Strategy Orchestration):
- MeanReversionStrategy: Bollinger Bands + RSI mean reversion
- TrendFollowingStrategyV2: EMA alignment + ADX + MACD trend following
- BreakoutStrategy: Consolidation/level breakout trading
- ArbitrageStrategy: Statistical arbitrage on correlated pairs

Updated: 2025-12-11
"""

# =============================================================================
# Phase 9: Multi-Strategy Orchestration Components
# =============================================================================

# Base Strategy Class
from .base import (
    StrategyBase,
    StrategyMetadata,
    StrategySignal,
    AnalysisResult,
    StrategyPerformance,
    StrategyRiskLevel,
    StrategyCategory,
    SignalType,
    MarketCondition as BaseMarketCondition,
    create_signal,
)

# Mean Reversion Strategy
from .mean_reversion import (
    MeanReversionStrategy,
    MeanReversionConfig,
    create_mean_reversion_strategy,
)

# Trend Following Strategy (New V2 for orchestration)
from .trend_following import (
    TrendFollowingStrategy as TrendFollowingStrategyV2,
    TrendFollowingConfig,
    create_trend_following_strategy,
)

# Breakout Strategy
from .breakout import (
    BreakoutStrategy,
    BreakoutConfig,
    create_breakout_strategy,
)

# Arbitrage Strategy
from .arbitrage import (
    ArbitrageStrategy,
    ArbitrageConfig,
    create_arbitrage_strategy,
)

# Signal Aggregator
from .aggregator import (
    SignalAggregator,
    AggregatorConfig,
    AggregatedSignal,
    NormalizedSignal,
    AggregationMethod,
    SignalDirection,
    get_signal_aggregator,
    reset_signal_aggregator,
)

# Strategy Coordinator
from .coordinator import (
    StrategyCoordinator,
    CoordinatorConfig,
    RiskBudget,
    TrackedPosition,
    get_strategy_coordinator,
    reset_strategy_coordinator,
)

# Strategy Backtester
from .backtester import (
    StrategyBacktester,
    BacktestConfig,
    BacktestResult,
    BacktestTrade,
    BacktestCandle,
    compare_backtest_results,
    create_backtester,
)

# =============================================================================
# Existing Strategies (Phases 1-2.4)
# =============================================================================

from .sqzmom_config import sqzmom_config, SQZMOMConfig
from .sqzmom_strategy_integration import sqzmom_strategy, SQZMOMStrategy
from .research_optimized_strategy import (
    ResearchOptimizedStrategy,
    MarketCondition,
    SignalStrength,
    TradeSetup,
)
from .support_resistance_strategy import (
    SupportResistanceStrategy,
    get_sr_strategy,
    generate_sr_signal,
)
from .pairs_trading import (
    PairsTradingStrategy,
    PairsTradeSignal,
)
from .funding_rate_arbitrage import (
    FundingRateArbitrageStrategy,
    FundingRateSignal,
)
from .triangular_arbitrage import (
    TriangularArbitrageStrategy,
    TriangularPath,
    TriangularArbitrageSignal,
)
# Grid Trading Strategies (Phase 2.3 - 2025-12-11)
from .grid_trading_strategy import GridTradingStrategy
from .grid_trading_strategy_v2 import (
    GridTradingStrategyV2,
    GridLevelV2,
    GridStateV2,
    GridSpacingType,
    GridLevelStatus,
    MarketRegime as GridMarketRegime,
    create_grid_trading_strategy_v2,
)
# Momentum Trading Strategies (Phase 2.4 - 2025-12-11)
from .momentum_breakout_strategy import (
    MomentumBreakoutStrategy,
    BreakoutDirection,
    SqueezeState,
    ConsolidationRange,
    BreakoutSignal,
    get_breakout_strategy,
    generate_breakout_signal,
)
from .trend_following_strategy import (
    TrendFollowingStrategy,
    TrendDirection,
    TrendStrength,
    PullbackState,
    TrendAnalysis,
    PullbackAnalysis,
    PyramidLevel,
    get_trend_strategy,
    generate_trend_signal,
)

__all__ = [
    # ==========================================================================
    # Phase 9: Multi-Strategy Orchestration (2025-12-11)
    # ==========================================================================
    # Base Strategy Components
    "StrategyBase",
    "StrategyMetadata",
    "StrategySignal",
    "AnalysisResult",
    "StrategyPerformance",
    "StrategyRiskLevel",
    "StrategyCategory",
    "SignalType",
    "BaseMarketCondition",
    "create_signal",
    # Mean Reversion Strategy
    "MeanReversionStrategy",
    "MeanReversionConfig",
    "create_mean_reversion_strategy",
    # Trend Following Strategy V2
    "TrendFollowingStrategyV2",
    "TrendFollowingConfig",
    "create_trend_following_strategy",
    # Breakout Strategy
    "BreakoutStrategy",
    "BreakoutConfig",
    "create_breakout_strategy",
    # Arbitrage Strategy
    "ArbitrageStrategy",
    "ArbitrageConfig",
    "create_arbitrage_strategy",
    # Signal Aggregator
    "SignalAggregator",
    "AggregatorConfig",
    "AggregatedSignal",
    "NormalizedSignal",
    "AggregationMethod",
    "SignalDirection",
    "get_signal_aggregator",
    "reset_signal_aggregator",
    # Strategy Coordinator
    "StrategyCoordinator",
    "CoordinatorConfig",
    "RiskBudget",
    "TrackedPosition",
    "get_strategy_coordinator",
    "reset_strategy_coordinator",
    # Strategy Backtester
    "StrategyBacktester",
    "BacktestConfig",
    "BacktestResult",
    "BacktestTrade",
    "BacktestCandle",
    "compare_backtest_results",
    "create_backtester",
    # ==========================================================================
    # Existing Strategies (Phases 1-2.4)
    # ==========================================================================
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
    # Support/Resistance Strategy (2025-12-07)
    "SupportResistanceStrategy",
    "get_sr_strategy",
    "generate_sr_signal",
    # Statistical Arbitrage Strategies (Phase 2.2, 2025-12-07)
    "PairsTradingStrategy",
    "PairsTradeSignal",
    "FundingRateArbitrageStrategy",
    "FundingRateSignal",
    "TriangularArbitrageStrategy",
    "TriangularPath",
    "TriangularArbitrageSignal",
    # Grid Trading Strategies (Phase 2.3, 2025-12-11)
    "GridTradingStrategy",
    "GridTradingStrategyV2",
    "GridLevelV2",
    "GridStateV2",
    "GridSpacingType",
    "GridLevelStatus",
    "GridMarketRegime",
    "create_grid_trading_strategy_v2",
    # Momentum Breakout Strategy (Phase 2.4, 2025-12-11)
    "MomentumBreakoutStrategy",
    "BreakoutDirection",
    "SqueezeState",
    "ConsolidationRange",
    "BreakoutSignal",
    "get_breakout_strategy",
    "generate_breakout_signal",
    # Trend Following Strategy (Phase 2.4, 2025-12-11)
    "TrendFollowingStrategy",
    "TrendDirection",
    "TrendStrength",
    "PullbackState",
    "TrendAnalysis",
    "PullbackAnalysis",
    "PyramidLevel",
    "get_trend_strategy",
    "generate_trend_signal",
]
