"""
Multi-Strategy Orchestration Models
====================================
Purpose: Data models for strategy orchestration, configuration, and state management

This module defines all data structures used by the orchestration engine:
- Strategy configuration and metadata
- Allocation and budgeting structures
- Signal aggregation and conflict resolution
- Performance metrics and tracking

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMERATIONS
# =============================================================================


class StrategyStatus(str, Enum):
    """
    Operational status of a strategy

    ACTIVE: Strategy is generating signals and can trade
    PAUSED: Temporarily disabled (manual or automatic)
    DISABLED: Permanently disabled until re-enabled
    WARMING_UP: Gathering initial data, not yet trading
    ERROR: Strategy encountered an error
    COOLDOWN: Temporarily paused after losses
    """

    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    WARMING_UP = "warming_up"
    ERROR = "error"
    COOLDOWN = "cooldown"


class StrategyType(str, Enum):
    """
    Classification of strategy types

    TREND_FOLLOWING: Follows established trends
    MEAN_REVERSION: Trades back to mean/average
    MOMENTUM: Capitalizes on price momentum
    ARBITRAGE: Exploits price discrepancies
    GRID: Grid-based trading
    BREAKOUT: Trades on breakouts from ranges
    SCALPING: High-frequency small gains
    """

    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    MOMENTUM = "momentum"
    ARBITRAGE = "arbitrage"
    GRID = "grid"
    BREAKOUT = "breakout"
    SCALPING = "scalping"


class RiskProfile(str, Enum):
    """
    Risk profile classification for strategies

    CONSERVATIVE: Low risk, lower returns (max 1% per trade)
    MODERATE: Balanced risk/return (max 2% per trade)
    AGGRESSIVE: Higher risk, higher potential returns (max 3% per trade)
    VERY_AGGRESSIVE: Very high risk (max 5% per trade)
    """

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"
    VERY_AGGRESSIVE = "very_aggressive"


class Timeframe(str, Enum):
    """
    Trading timeframes supported
    """

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class SignalDirection(str, Enum):
    """
    Direction of a trading signal
    """

    LONG = "long"
    SHORT = "short"
    FLAT = "flat"  # Close positions, go neutral


class ConflictResolutionMethod(str, Enum):
    """
    Methods for resolving signal conflicts

    WEIGHTED_VOTING: Weight signals by strategy performance/allocation
    PRIORITY_BASED: Use signal from highest priority strategy
    STRONGEST_SIGNAL: Use signal with highest confidence
    AVERAGE: Average all signals
    UNANIMOUS: Only act on unanimous signals
    MAJORITY: Use signal with majority agreement
    VETO: Any opposing signal cancels action
    """

    WEIGHTED_VOTING = "weighted_voting"
    PRIORITY_BASED = "priority_based"
    STRONGEST_SIGNAL = "strongest_signal"
    AVERAGE = "average"
    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    VETO = "veto"


class AllocationMethod(str, Enum):
    """
    Methods for allocating capital across strategies

    EQUAL: Equal allocation to all strategies
    RISK_PARITY: Allocate inversely to volatility
    PERFORMANCE_BASED: Allocate based on historical performance
    KELLY: Use Kelly criterion for optimal allocation
    FIXED: Use fixed predefined allocations
    DYNAMIC: Continuously adjust based on conditions
    """

    EQUAL = "equal"
    RISK_PARITY = "risk_parity"
    PERFORMANCE_BASED = "performance_based"
    KELLY = "kelly"
    FIXED = "fixed"
    DYNAMIC = "dynamic"


class RebalanceTrigger(str, Enum):
    """
    Triggers for portfolio rebalancing

    THRESHOLD: Rebalance when drift exceeds threshold
    PERIODIC: Rebalance on schedule (daily, weekly)
    PERFORMANCE: Rebalance based on strategy performance changes
    VOLATILITY: Rebalance when volatility regime changes
    MANUAL: Manual rebalancing only
    """

    THRESHOLD = "threshold"
    PERIODIC = "periodic"
    PERFORMANCE = "performance"
    VOLATILITY = "volatility"
    MANUAL = "manual"


# =============================================================================
# STRATEGY CONFIGURATION
# =============================================================================


@dataclass
class StrategyMetadata:
    """
    Metadata describing a strategy's characteristics

    Used for:
    - Strategy categorization
    - Risk assessment
    - Allocation decisions
    - Conflict resolution
    """

    # Identification
    strategy_id: str
    name: str
    version: str = "1.0.0"
    description: str = ""

    # Classification
    strategy_type: StrategyType = StrategyType.TREND_FOLLOWING
    risk_profile: RiskProfile = RiskProfile.MODERATE

    # Trading parameters
    supported_symbols: List[str] = field(default_factory=list)
    primary_timeframe: Timeframe = Timeframe.H1
    supported_timeframes: List[Timeframe] = field(default_factory=lambda: [Timeframe.H1])

    # Risk parameters
    max_position_size_pct: float = 5.0  # Max % of capital per position
    max_drawdown_pct: float = 10.0  # Max acceptable drawdown
    typical_hold_period_hours: float = 24.0  # Average holding period
    expected_win_rate: float = 0.5  # Expected win rate
    expected_profit_factor: float = 1.5  # Expected avg_win / avg_loss

    # Performance characteristics
    expected_sharpe: float = 1.0  # Expected Sharpe ratio
    expected_trades_per_day: float = 2.0  # Expected trade frequency
    typical_slippage_pct: float = 0.05  # Expected slippage

    # Dependencies
    required_indicators: List[str] = field(default_factory=list)
    required_data_history_days: int = 30  # Days of data needed

    # Priority and conflict resolution
    priority: int = 50  # 1-100, higher = more important
    can_override: bool = True  # Can override lower priority strategies
    correlation_group: Optional[str] = None  # Strategies that correlate

    # Status tracking
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "strategy_type": self.strategy_type.value,
            "risk_profile": self.risk_profile.value,
            "supported_symbols": self.supported_symbols,
            "primary_timeframe": self.primary_timeframe.value,
            "max_position_size_pct": self.max_position_size_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "priority": self.priority,
            "expected_sharpe": self.expected_sharpe,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class StrategyConfig:
    """
    Runtime configuration for a strategy instance

    Combines metadata with runtime settings:
    - Allocation parameters
    - Risk limits
    - Activation settings
    """

    # Core identification
    metadata: StrategyMetadata

    # Allocation settings
    target_allocation_pct: float = 10.0  # Target % of total capital
    min_allocation_pct: float = 5.0  # Minimum allocation
    max_allocation_pct: float = 20.0  # Maximum allocation
    current_allocation_pct: float = 10.0  # Current allocation

    # Risk limits
    max_daily_loss_pct: float = 2.0  # Max daily loss before pause
    max_consecutive_losses: int = 5  # Max losses before cooldown
    cooldown_hours: int = 4  # Hours to pause after max losses

    # Activation settings
    auto_activate: bool = True  # Auto-activate when conditions met
    auto_pause_on_drawdown: bool = True  # Auto-pause on drawdown
    drawdown_pause_threshold_pct: float = 5.0  # Drawdown % to trigger pause

    # Signal settings
    min_signal_confidence: float = 0.5  # Minimum confidence to act
    signal_aggregation_weight: float = 1.0  # Weight in signal aggregation

    # Enabled symbols (subset of supported)
    enabled_symbols: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "metadata": self.metadata.to_dict(),
            "target_allocation_pct": self.target_allocation_pct,
            "min_allocation_pct": self.min_allocation_pct,
            "max_allocation_pct": self.max_allocation_pct,
            "current_allocation_pct": self.current_allocation_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_consecutive_losses": self.max_consecutive_losses,
            "enabled_symbols": list(self.enabled_symbols),
        }


# =============================================================================
# STRATEGY STATE
# =============================================================================


@dataclass
class StrategyState:
    """
    Runtime state of a strategy

    Tracks:
    - Current operational status
    - Performance metrics
    - Position information
    - Error states
    """

    # Identification
    strategy_id: str

    # Status
    status: StrategyStatus = StrategyStatus.DISABLED
    status_reason: str = ""
    status_changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Performance (rolling window)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    consecutive_wins: int = 0
    consecutive_losses: int = 0

    # PnL tracking
    total_pnl: float = 0.0
    today_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    peak_equity: float = 0.0
    current_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0

    # Position tracking
    open_positions: int = 0
    total_position_value: float = 0.0

    # Risk metrics
    current_risk_budget_used_pct: float = 0.0
    daily_loss_pct: float = 0.0

    # Timing
    last_signal_at: Optional[datetime] = None
    last_trade_at: Optional[datetime] = None
    cooldown_until: Optional[datetime] = None
    warming_up_until: Optional[datetime] = None

    # Error tracking
    error_count: int = 0
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0,
            "consecutive_losses": self.consecutive_losses,
            "total_pnl": self.total_pnl,
            "today_pnl": self.today_pnl,
            "current_drawdown_pct": self.current_drawdown_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "open_positions": self.open_positions,
            "last_trade_at": self.last_trade_at.isoformat() if self.last_trade_at else None,
        }

    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def is_in_cooldown(self) -> bool:
        """Check if strategy is in cooldown"""
        if self.cooldown_until is None:
            return False
        return datetime.now(timezone.utc) < self.cooldown_until

    @property
    def is_warming_up(self) -> bool:
        """Check if strategy is warming up"""
        if self.warming_up_until is None:
            return False
        return datetime.now(timezone.utc) < self.warming_up_until


# =============================================================================
# SIGNAL MODELS
# =============================================================================


@dataclass
class StrategySignal:
    """
    Signal generated by a single strategy

    Contains:
    - Direction and strength
    - Entry/exit parameters
    - Risk parameters
    - Confidence metrics
    """

    # Identification
    signal_id: str
    strategy_id: str
    symbol: str
    timestamp: datetime

    # Direction
    direction: SignalDirection
    action: str  # BUY, SELL, CLOSE_LONG, CLOSE_SHORT

    # Strength and confidence
    strength: float = 0.0  # -1 to +1 scale
    confidence: float = 0.5  # 0 to 1 scale

    # Entry parameters
    entry_price: Optional[Decimal] = None
    suggested_quantity: Optional[Decimal] = None
    position_size_pct: Optional[float] = None

    # Risk parameters
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None

    # Urgency
    urgency: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    expiry_seconds: int = 300  # Signal validity period

    # Metadata
    timeframe: str = "1h"
    indicators_used: List[str] = field(default_factory=list)
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "signal_id": self.signal_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "action": self.action,
            "strength": self.strength,
            "confidence": self.confidence,
            "entry_price": str(self.entry_price) if self.entry_price else None,
            "stop_loss": str(self.stop_loss) if self.stop_loss else None,
            "take_profit": str(self.take_profit) if self.take_profit else None,
            "urgency": self.urgency,
            "reasoning": self.reasoning,
        }

    @property
    def is_expired(self) -> bool:
        """Check if signal has expired"""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > self.expiry_seconds

    @property
    def is_actionable(self) -> bool:
        """Check if signal is actionable"""
        return not self.is_expired and self.direction != SignalDirection.FLAT


@dataclass
class AggregatedSignal:
    """
    Aggregated signal from multiple strategies

    Result of conflict resolution when multiple strategies
    provide signals for the same symbol.
    """

    # Core data
    symbol: str
    timestamp: datetime

    # Aggregated direction
    direction: SignalDirection
    action: str

    # Strength and confidence (aggregated)
    aggregated_strength: float = 0.0
    aggregated_confidence: float = 0.0

    # Source signals
    source_signals: List[StrategySignal] = field(default_factory=list)
    agreeing_strategies: List[str] = field(default_factory=list)
    opposing_strategies: List[str] = field(default_factory=list)

    # Conflict resolution info
    resolution_method: ConflictResolutionMethod = ConflictResolutionMethod.WEIGHTED_VOTING
    conflict_detected: bool = False
    resolution_reasoning: str = ""

    # Execution parameters (aggregated)
    suggested_position_size_pct: float = 0.0
    weighted_stop_loss_pct: Optional[float] = None
    weighted_take_profit_pct: Optional[float] = None

    # Quality metrics
    strategy_agreement_ratio: float = 0.0  # % of strategies agreeing
    signal_quality_score: float = 0.0  # Overall quality score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "action": self.action,
            "aggregated_strength": self.aggregated_strength,
            "aggregated_confidence": self.aggregated_confidence,
            "source_signals_count": len(self.source_signals),
            "agreeing_strategies": self.agreeing_strategies,
            "opposing_strategies": self.opposing_strategies,
            "conflict_detected": self.conflict_detected,
            "resolution_method": self.resolution_method.value,
            "strategy_agreement_ratio": self.strategy_agreement_ratio,
            "signal_quality_score": self.signal_quality_score,
        }


# =============================================================================
# ALLOCATION MODELS
# =============================================================================


@dataclass
class StrategyAllocation:
    """
    Capital allocation for a single strategy
    """

    strategy_id: str

    # Allocation percentages
    target_pct: float = 0.0  # Target allocation %
    current_pct: float = 0.0  # Current allocation %
    min_pct: float = 0.0  # Minimum allocation %
    max_pct: float = 100.0  # Maximum allocation %

    # Dollar amounts
    allocated_capital: float = 0.0  # Allocated capital in USD
    used_capital: float = 0.0  # Capital currently in use
    available_capital: float = 0.0  # Available for new positions

    # Risk budget
    risk_budget_pct: float = 0.0  # Risk budget as % of capital
    risk_budget_used_pct: float = 0.0  # Used risk budget

    # Rebalancing
    needs_rebalancing: bool = False
    rebalance_amount: float = 0.0  # + to add, - to remove

    # Timestamps
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_rebalanced: Optional[datetime] = None


@dataclass
class AllocationSnapshot:
    """
    Snapshot of all strategy allocations at a point in time
    """

    timestamp: datetime
    total_capital: float
    allocations: Dict[str, StrategyAllocation] = field(default_factory=dict)

    # Summary metrics
    total_allocated_pct: float = 0.0
    total_used_pct: float = 0.0
    cash_reserve_pct: float = 0.0

    # Rebalancing info
    requires_rebalancing: bool = False
    total_rebalance_amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_capital": self.total_capital,
            "total_allocated_pct": self.total_allocated_pct,
            "total_used_pct": self.total_used_pct,
            "cash_reserve_pct": self.cash_reserve_pct,
            "requires_rebalancing": self.requires_rebalancing,
            "strategy_count": len(self.allocations),
        }


# =============================================================================
# PERFORMANCE METRICS
# =============================================================================


@dataclass
class StrategyPerformanceMetrics:
    """
    Comprehensive performance metrics for a strategy
    """

    strategy_id: str
    period_start: datetime
    period_end: datetime

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0

    # PnL metrics
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0

    # Average trade metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_trade: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_hours: float = 0.0
    calmar_ratio: float = 0.0  # Annual return / max drawdown

    # Consistency metrics
    win_streak_max: int = 0
    loss_streak_max: int = 0
    consecutive_profitable_days: int = 0

    # Correlation metrics
    correlation_to_market: float = 0.0
    correlation_to_other_strategies: Dict[str, float] = field(default_factory=dict)

    # Risk-adjusted returns
    return_on_risk: float = 0.0  # Return / risk taken
    kelly_fraction: float = 0.0  # Optimal bet size

    # Timing metrics
    avg_hold_time_hours: float = 0.0
    avg_trades_per_day: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "period": f"{self.period_start.isoformat()} to {self.period_end.isoformat()}",
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "total_pnl": self.total_pnl,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown_pct": self.max_drawdown_pct,
            "calmar_ratio": self.calmar_ratio,
            "kelly_fraction": self.kelly_fraction,
        }


# =============================================================================
# ORCHESTRATOR CONFIGURATION
# =============================================================================

#: Mirrors config.py `paper_initial_balance`. Used only when `get_settings()`
#: cannot be constructed (host-run session without the container env).
_FALLBACK_TOTAL_CAPITAL_USD = 10000.0


def default_total_capital() -> float:
    """Declared account size, resolved lazily from Settings — never at import."""
    try:
        from app.config import get_settings

        return float(get_settings().paper_initial_balance)
    except Exception:
        return _FALLBACK_TOTAL_CAPITAL_USD


@dataclass
class OrchestratorConfig:
    """
    Configuration for the Strategy Orchestrator
    """

    # Capital management
    total_capital: float = field(default_factory=default_total_capital)
    max_total_exposure_pct: float = 80.0  # Max 80% deployed
    cash_reserve_pct: float = 10.0  # Always keep 10% cash

    # Allocation settings
    allocation_method: AllocationMethod = AllocationMethod.PERFORMANCE_BASED
    rebalance_trigger: RebalanceTrigger = RebalanceTrigger.THRESHOLD
    rebalance_threshold_pct: float = 5.0  # Rebalance when drift > 5%
    rebalance_interval_hours: int = 24  # For periodic rebalancing

    # Conflict resolution
    default_conflict_resolution: ConflictResolutionMethod = ConflictResolutionMethod.WEIGHTED_VOTING
    min_agreement_ratio: float = 0.5  # Min ratio of strategies agreeing

    # Risk management
    max_daily_loss_pct: float = 5.0  # Max portfolio daily loss
    max_total_drawdown_pct: float = 15.0  # Max portfolio drawdown
    correlation_limit: float = 0.7  # Max correlation between strategies

    # Auto-pause settings
    auto_pause_on_drawdown: bool = True
    auto_pause_underperformers: bool = True
    underperformer_threshold_sharpe: float = 0.0  # Pause if Sharpe < 0
    underperformer_min_trades: int = 20  # Min trades before evaluation

    # Signal settings
    signal_timeout_seconds: int = 300  # Signals expire after 5 min
    max_signals_per_symbol: int = 5  # Max concurrent signals per symbol

    # Logging and monitoring
    metrics_update_interval_seconds: int = 60
    persist_state_interval_seconds: int = 300

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_capital": self.total_capital,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "allocation_method": self.allocation_method.value,
            "rebalance_trigger": self.rebalance_trigger.value,
            "default_conflict_resolution": self.default_conflict_resolution.value,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_total_drawdown_pct": self.max_total_drawdown_pct,
        }


# =============================================================================
# PYDANTIC MODELS FOR API
# =============================================================================


class RegisterStrategyRequest(BaseModel):
    """Request to register a new strategy"""

    strategy_id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., description="Strategy display name")
    strategy_type: str = Field("trend_following", description="Strategy type")
    risk_profile: str = Field("moderate", description="Risk profile")
    supported_symbols: List[str] = Field(default_factory=list)
    primary_timeframe: str = Field("1h", description="Primary timeframe")
    target_allocation_pct: float = Field(10.0, ge=0.0, le=100.0)
    priority: int = Field(50, ge=1, le=100)
    description: str = Field("", description="Strategy description")


class UpdateStrategyStatusRequest(BaseModel):
    """Request to update strategy status"""

    status: str = Field(..., description="New status")
    reason: str = Field("", description="Reason for status change")


class UpdateAllocationRequest(BaseModel):
    """Request to update strategy allocation"""

    target_allocation_pct: float = Field(..., ge=0.0, le=100.0)
    min_allocation_pct: float = Field(0.0, ge=0.0, le=100.0)
    max_allocation_pct: float = Field(100.0, ge=0.0, le=100.0)


class SubmitSignalRequest(BaseModel):
    """Request to submit a strategy signal"""

    strategy_id: str
    symbol: str
    direction: str = Field(..., description="long, short, or flat")
    action: str = Field(..., description="BUY, SELL, CLOSE_LONG, CLOSE_SHORT")
    strength: float = Field(0.0, ge=-1.0, le=1.0)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    entry_price: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    position_size_pct: Optional[float] = None
    urgency: str = Field("MEDIUM", description="LOW, MEDIUM, HIGH, CRITICAL")
    reasoning: str = Field("", description="Signal reasoning")


class OrchestratorStatusResponse(BaseModel):
    """Response with orchestrator status"""

    is_active: bool
    total_capital: float
    total_allocated_pct: float
    active_strategies: int
    paused_strategies: int
    total_open_positions: int
    today_pnl: float
    total_pnl: float
    current_drawdown_pct: float
    last_updated: str


class StrategyStatusResponse(BaseModel):
    """Response with single strategy status"""

    strategy_id: str
    name: str
    status: str
    status_reason: str
    current_allocation_pct: float
    total_trades: int
    win_rate: float
    total_pnl: float
    today_pnl: float
    current_drawdown_pct: float
    open_positions: int
    last_trade_at: Optional[str]


class SignalAggregationResponse(BaseModel):
    """Response with aggregated signals"""

    symbol: str
    direction: str
    action: str
    aggregated_strength: float
    aggregated_confidence: float
    source_strategies: List[str]
    conflict_detected: bool
    resolution_method: str
    suggested_position_size_pct: float
    signal_quality_score: float
