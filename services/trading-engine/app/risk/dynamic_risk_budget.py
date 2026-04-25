"""
Dynamic Risk Budgeting Module - Phase 3.3
Purpose: Implement dynamic risk allocation system that adjusts position sizing
based on market conditions, portfolio health, and recent performance.

Features:
- Base risk budget calculation (starting capital x risk percentage)
- Dynamic adjustments based on:
  - Market volatility (VIX-style indicator)
  - Recent drawdown (reduce risk after losses)
  - Win streak (increase risk cautiously after wins)
  - Portfolio correlation (reduce if highly correlated)
  - Time of day (reduce during low liquidity hours)
- Risk budget allocation across strategies
- Per-strategy risk limits
- Emergency risk reduction triggers
- Risk ladder: Scale from 0.5% (defensive) to 2.5% (aggressive)

API Endpoints (6):
- GET /api/v1/risk/budget/current - Current risk budget
- GET /api/v1/risk/budget/utilization - Risk used vs available
- GET /api/v1/risk/budget/allocation - Per-strategy allocation
- POST /api/v1/risk/budget/calculate - Calculate for conditions
- POST /api/v1/risk/budget/adjust - Manual adjustment
- GET /api/v1/risk/budget/history - Historical risk budget

Integration:
- Kelly Criterion (use budget as max position size)
- Correlation Manager (reduce budget if high correlation)

Phase 3.3 - Dynamic Risk Budgeting Implementation
Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
import os
from datetime import datetime, timezone, timedelta, time
from decimal import Decimal
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple, Any, Union
from enum import Enum
from collections import deque
import json
import asyncio
from threading import RLock
import statistics

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS AND CONSTANTS
# =============================================================================

class MarketRegime(str, Enum):
    """Market regime classification for risk adjustment"""
    LOW_VOLATILITY = "LOW_VOLATILITY"        # Calm markets - can increase risk
    NORMAL = "NORMAL"                         # Standard conditions
    ELEVATED_VOLATILITY = "ELEVATED_VOLATILITY"  # Caution warranted
    HIGH_VOLATILITY = "HIGH_VOLATILITY"       # Reduce risk significantly
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY" # Emergency risk reduction


class RiskBudgetAlertSeverity(str, Enum):
    """Alert severity levels for risk budget alerts"""
    INFO = "INFO"           # Informational, no action needed
    WARNING = "WARNING"     # Attention recommended
    HIGH = "HIGH"           # Action recommended
    CRITICAL = "CRITICAL"   # Immediate action required
    EMERGENCY = "EMERGENCY" # Emergency stop triggered


class EmergencyTrigger(str, Enum):
    """Reasons for emergency risk reduction"""
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"       # Daily loss exceeded threshold
    MAX_DRAWDOWN = "MAX_DRAWDOWN"                # Portfolio drawdown too high
    EXTREME_VOLATILITY = "EXTREME_VOLATILITY"   # Market volatility spiked
    CORRELATION_SPIKE = "CORRELATION_SPIKE"     # Correlation increased suddenly
    MANUAL_TRIGGER = "MANUAL_TRIGGER"           # Manually triggered
    SYSTEM_ERROR = "SYSTEM_ERROR"               # System detected anomaly


# Risk ladder levels (defensive to aggressive)
RISK_LADDER = {
    "ultra_defensive": 0.5,   # 0.5% max risk per trade
    "defensive": 1.0,          # 1.0% max risk per trade
    "conservative": 1.5,       # 1.5% max risk per trade
    "normal": 2.0,             # 2.0% max risk per trade (standard)
    "aggressive": 2.5,         # 2.5% max risk per trade
}

# Low liquidity hours (UTC) - typically Asian session end / European pre-market
LOW_LIQUIDITY_HOURS = [(4, 7), (20, 22)]  # 4-7 UTC and 20-22 UTC


# =============================================================================
# PYDANTIC-STYLE MODELS (using dataclasses for compatibility)
# =============================================================================

@dataclass
class RiskBudgetConfig:
    """
    Configuration for Dynamic Risk Budgeting System

    Attributes:
        base_equity: Base equity/capital for calculations
        base_risk_pct: Base risk percentage (default 2.0%)
        max_risk_pct: Maximum risk percentage ever allowed
        min_risk_pct: Minimum risk percentage (floor)
        volatility_adjustment_enabled: Enable volatility-based adjustments
        drawdown_adjustment_enabled: Enable drawdown-based adjustments
        streak_adjustment_enabled: Enable win/loss streak adjustments
        correlation_adjustment_enabled: Enable correlation-based adjustments
        liquidity_adjustment_enabled: Enable time-of-day liquidity adjustments
        max_daily_loss_pct: Maximum daily loss before emergency stop
        max_drawdown_pct: Maximum portfolio drawdown allowed
        emergency_reduction_factor: Factor to reduce risk in emergency
        streak_bonus_per_win: Risk increase per consecutive win (capped)
        streak_penalty_per_loss: Risk decrease per consecutive loss
        max_streak_adjustment: Maximum adjustment from streaks
    """
    base_equity: float = field(default_factory=lambda: float(os.getenv('RISK_BUDGET_INITIAL', '100.0')))
    base_risk_pct: float = 2.0
    max_risk_pct: float = 2.5
    min_risk_pct: float = 0.5
    volatility_adjustment_enabled: bool = True
    drawdown_adjustment_enabled: bool = True
    streak_adjustment_enabled: bool = True
    correlation_adjustment_enabled: bool = True
    liquidity_adjustment_enabled: bool = True
    max_daily_loss_pct: float = 5.0
    max_drawdown_pct: float = 15.0
    emergency_reduction_factor: float = 0.25
    streak_bonus_per_win: float = 0.05
    streak_penalty_per_loss: float = 0.10
    max_streak_adjustment: float = 0.5

    def __post_init__(self):
        """Validate configuration values"""
        if self.base_equity <= 0:
            raise ValueError(f"base_equity must be positive, got {self.base_equity}")
        if not (0 < self.base_risk_pct <= 100):
            raise ValueError(f"base_risk_pct must be between 0 and 100, got {self.base_risk_pct}")
        if self.min_risk_pct >= self.max_risk_pct:
            raise ValueError(f"min_risk_pct must be less than max_risk_pct")
        if not (0 < self.emergency_reduction_factor <= 1):
            raise ValueError(f"emergency_reduction_factor must be between 0 and 1")

        logger.info(
            f"RiskBudgetConfig initialized: equity=${self.base_equity:,.0f}, "
            f"base_risk={self.base_risk_pct}%, range=[{self.min_risk_pct}%, {self.max_risk_pct}%]"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)


@dataclass
class RiskBudgetRequest:
    """Request model for risk budget calculation"""
    equity: float
    volatility_percentile: Optional[float] = None
    current_drawdown: Optional[float] = None
    win_streak: Optional[int] = None
    loss_streak: Optional[int] = None
    avg_correlation: Optional[float] = None
    market_regime: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskBudgetResponse:
    """Response model for risk budget calculation"""
    base_budget_pct: float
    base_budget_usd: float
    adjusted_budget_pct: float
    adjusted_budget_usd: float
    volatility_multiplier: float
    drawdown_multiplier: float
    streak_multiplier: float
    correlation_multiplier: float
    liquidity_multiplier: float
    combined_multiplier: float
    market_regime: str
    risk_level: str
    max_position_size: float
    recommendations: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskAllocation:
    """Model for strategy risk allocation"""
    strategy_name: str
    allocation_pct: float
    allocated_budget_usd: float
    current_usage_usd: float
    available_budget_usd: float
    utilization_pct: float
    performance_multiplier: float
    effective_budget_usd: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskUtilization:
    """Model for overall risk utilization"""
    total_budget_usd: float
    used_budget_usd: float
    available_budget_usd: float
    utilization_pct: float
    by_strategy: Dict[str, Dict[str, float]]
    by_asset: Dict[str, Dict[str, float]]
    emergency_mode: bool
    current_risk_level: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskAdjustment:
    """Model for manual risk adjustment"""
    adjustment_type: str  # 'increase', 'decrease', 'set_level', 'emergency_stop'
    previous_risk_pct: float
    new_risk_pct: float
    reason: str
    adjusted_by: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskBudgetAlert:
    """Alert generated by risk budget system"""
    severity: RiskBudgetAlertSeverity
    message: str
    timestamp: datetime
    trigger: Optional[str] = None
    current_value: Optional[float] = None
    threshold: Optional[float] = None
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            "trigger": self.trigger,
            "current_value": self.current_value,
            "threshold": self.threshold,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


@dataclass
class RiskBudgetHistoryEntry:
    """Historical risk budget record"""
    timestamp: datetime
    equity: float
    risk_budget_pct: float
    risk_budget_usd: float
    market_regime: str
    volatility_percentile: float
    drawdown_pct: float
    multipliers: Dict[str, float]
    emergency_mode: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp
        }


# =============================================================================
# MAIN CLASS: DynamicRiskBudget
# =============================================================================

class DynamicRiskBudget:
    """
    Dynamic Risk Budget Management System

    Implements a sophisticated risk allocation system that dynamically adjusts
    position sizing based on multiple market and portfolio factors.

    Key Features:
    1. Base Risk Budget: Calculated from equity and base risk percentage
    2. Volatility Adjustment: VIX-style indicator reduces/increases budget
    3. Drawdown Adjustment: Reduces risk after losses
    4. Streak Adjustment: Cautiously increases after wins, decreases after losses
    5. Correlation Adjustment: Reduces if portfolio highly correlated
    6. Liquidity Adjustment: Reduces during low-liquidity hours
    7. Emergency Triggers: Auto-reduces risk on extreme conditions
    8. Strategy Allocation: Distributes budget across strategies

    Usage:
        config = RiskBudgetConfig(base_equity=100000, base_risk_pct=2.0)
        budget_manager = DynamicRiskBudget(config)

        # Calculate risk budget
        result = budget_manager.calculate_risk_budget(
            equity=100000,
            volatility=60,
            drawdown=0.05
        )

        # Allocate to strategies
        budget_manager.allocate_to_strategies({
            "pairs_trading": 0.4,
            "mean_reversion": 0.3,
            "momentum": 0.3
        })

        # Check if can place trade
        can_trade, reason = budget_manager.can_place_trade(
            strategy="pairs_trading",
            symbol="BTCUSDT",
            risk_amount=500
        )
    """

    # History retention (keep 30 days of hourly records)
    MAX_HISTORY_ENTRIES = 720

    def __init__(self, config: Optional[RiskBudgetConfig] = None):
        """
        Initialize Dynamic Risk Budget Manager

        Args:
            config: Configuration (uses defaults if None)
        """
        self.config = config or RiskBudgetConfig()
        self._lock = RLock()

        # Current state
        self._current_equity: float = self.config.base_equity
        self._current_risk_pct: float = self.config.base_risk_pct
        self._current_regime: MarketRegime = MarketRegime.NORMAL
        self._emergency_mode: bool = False
        self._emergency_trigger: Optional[EmergencyTrigger] = None

        # Market data
        self._volatility_data: Dict[str, float] = {}
        self._volatility_percentile: float = 50.0
        self._current_drawdown: float = 0.0
        self._peak_equity: float = self.config.base_equity
        self._daily_pnl: float = 0.0

        # Streak tracking
        self._win_streak: int = 0
        self._loss_streak: int = 0

        # Correlation data
        self._avg_correlation: float = 0.5
        self._correlation_data: Dict[str, float] = {}

        # Strategy allocations
        self._strategy_allocations: Dict[str, float] = {}  # strategy -> allocation_pct
        self._strategy_usage: Dict[str, float] = {}  # strategy -> current_usage_usd
        self._strategy_performance: Dict[str, Dict[str, float]] = {}  # strategy -> metrics

        # Asset tracking
        self._asset_usage: Dict[str, float] = {}  # symbol -> usage_usd

        # History
        self._budget_history: deque = deque(maxlen=self.MAX_HISTORY_ENTRIES)
        self._adjustment_history: List[RiskAdjustment] = []
        self._alerts: List[RiskBudgetAlert] = []

        # Kelly integration reference
        self._kelly_data: Dict[str, Dict[str, float]] = {}

        logger.info(
            f"DynamicRiskBudget initialized: equity=${self.config.base_equity:,.0f}, "
            f"base_risk={self.config.base_risk_pct}%"
        )

    # =========================================================================
    # CORE BUDGET CALCULATION
    # =========================================================================

    def calculate_risk_budget(
        self,
        equity: Optional[float] = None,
        volatility_percentile: Optional[float] = None,
        drawdown_pct: Optional[float] = None,
        win_streak: Optional[int] = None,
        loss_streak: Optional[int] = None,
        avg_correlation: Optional[float] = None,
        market_regime: Optional[MarketRegime] = None,
        check_liquidity: bool = True,
    ) -> RiskBudgetResponse:
        """
        Calculate dynamic risk budget with all adjustments applied

        Formula:
            base_risk = equity * base_risk_pct
            volatility_adj = 1.0 - (volatility_percentile / 100)  # Reduce in high vol
            drawdown_adj = 1.0 - (current_drawdown / max_drawdown) # Reduce after losses
            streak_adj = min(1.2, 1.0 + (win_streak * 0.05))       # Increase cautiously
            correlation_adj = 1.0 - (avg_correlation - 0.5) * 0.5  # Reduce if correlated
            liquidity_adj = 0.7 if low_liquidity_hours else 1.0

            final_budget = base_risk * vol_adj * dd_adj * streak_adj * corr_adj * liq_adj

        Args:
            equity: Current equity (uses stored if None)
            volatility_percentile: Current volatility as percentile (0-100)
            drawdown_pct: Current drawdown as percentage
            win_streak: Number of consecutive winning trades
            loss_streak: Number of consecutive losing trades
            avg_correlation: Average portfolio correlation (0-1)
            market_regime: Market regime classification
            check_liquidity: Whether to apply liquidity adjustment

        Returns:
            RiskBudgetResponse with complete budget calculation
        """
        with self._lock:
            # Update state with provided values
            if equity is not None:
                self._current_equity = equity
                # Update peak equity for drawdown calculation
                if equity > self._peak_equity:
                    self._peak_equity = equity

            if volatility_percentile is not None:
                self._volatility_percentile = volatility_percentile

            if drawdown_pct is not None:
                self._current_drawdown = drawdown_pct

            if win_streak is not None:
                self._win_streak = win_streak
                self._loss_streak = 0

            if loss_streak is not None:
                self._loss_streak = loss_streak
                self._win_streak = 0

            if avg_correlation is not None:
                self._avg_correlation = avg_correlation

            if market_regime is not None:
                self._current_regime = market_regime
            else:
                # Auto-detect regime from volatility
                self._current_regime = self._detect_market_regime()

            # Emergency check first
            if self._emergency_mode:
                return self._get_emergency_budget()

            # Calculate base budget
            base_budget_pct = self.config.base_risk_pct
            base_budget_usd = self._current_equity * (base_budget_pct / 100)

            # Calculate multipliers
            vol_mult = self._calculate_volatility_multiplier()
            dd_mult = self._calculate_drawdown_multiplier()
            streak_mult = self._calculate_streak_multiplier()
            corr_mult = self._calculate_correlation_multiplier()
            liq_mult = self._calculate_liquidity_multiplier() if check_liquidity else 1.0

            # Combined multiplier with bounds
            combined_mult = vol_mult * dd_mult * streak_mult * corr_mult * liq_mult
            combined_mult = max(0.1, min(2.0, combined_mult))  # Bound to 10%-200%

            # Calculate adjusted budget
            adjusted_budget_pct = base_budget_pct * combined_mult
            # Apply min/max limits
            adjusted_budget_pct = max(
                self.config.min_risk_pct,
                min(self.config.max_risk_pct, adjusted_budget_pct)
            )
            adjusted_budget_usd = self._current_equity * (adjusted_budget_pct / 100)

            # Update current risk
            self._current_risk_pct = adjusted_budget_pct

            # Determine risk level name
            risk_level = self._get_risk_level_name(adjusted_budget_pct)

            # Calculate max position size (for Kelly integration)
            max_position_size = adjusted_budget_usd

            # Generate recommendations
            recommendations = self._generate_recommendations(
                vol_mult, dd_mult, streak_mult, corr_mult, liq_mult
            )

            # Record to history
            self._record_budget_history(adjusted_budget_pct, adjusted_budget_usd)

            # Generate alerts if needed
            self._check_and_generate_alerts(adjusted_budget_pct, adjusted_budget_usd)

            return RiskBudgetResponse(
                base_budget_pct=round(base_budget_pct, 4),
                base_budget_usd=round(base_budget_usd, 2),
                adjusted_budget_pct=round(adjusted_budget_pct, 4),
                adjusted_budget_usd=round(adjusted_budget_usd, 2),
                volatility_multiplier=round(vol_mult, 4),
                drawdown_multiplier=round(dd_mult, 4),
                streak_multiplier=round(streak_mult, 4),
                correlation_multiplier=round(corr_mult, 4),
                liquidity_multiplier=round(liq_mult, 4),
                combined_multiplier=round(combined_mult, 4),
                market_regime=self._current_regime.value,
                risk_level=risk_level,
                max_position_size=round(max_position_size, 2),
                recommendations=recommendations,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def _calculate_volatility_multiplier(self) -> float:
        """
        Calculate volatility-based risk multiplier

        VIX-style adjustment:
        - Low volatility (< 20th percentile): 1.3x (increase risk)
        - Normal volatility (20-60th): 1.0x (unchanged)
        - Elevated volatility (60-80th): 0.8x (reduce risk)
        - High volatility (80-90th): 0.6x (significantly reduce)
        - Extreme volatility (> 90th): 0.4x (minimal risk)
        """
        if not self.config.volatility_adjustment_enabled:
            return 1.0

        percentile = self._volatility_percentile

        if percentile < 10:
            return 1.5  # Very low vol - can be aggressive
        elif percentile < 20:
            return 1.3
        elif percentile < 40:
            return 1.1
        elif percentile < 60:
            return 1.0
        elif percentile < 80:
            return 0.8
        elif percentile < 90:
            return 0.6
        else:  # >= 90
            return 0.4

    def _calculate_drawdown_multiplier(self) -> float:
        """
        Calculate drawdown-based risk multiplier

        Logic: Reduce risk proportionally to drawdown
        - No drawdown: 1.0x
        - At max_drawdown_pct/2: 0.5x
        - At max_drawdown_pct: 0.25x (emergency threshold)
        """
        if not self.config.drawdown_adjustment_enabled:
            return 1.0

        dd = self._current_drawdown
        max_dd = self.config.max_drawdown_pct

        if dd <= 0:
            return 1.0

        # Linear reduction from 1.0 to 0.25 based on drawdown
        ratio = dd / max_dd
        multiplier = 1.0 - (ratio * 0.75)  # At max_dd, multiplier = 0.25

        return max(0.25, min(1.0, multiplier))

    def _calculate_streak_multiplier(self) -> float:
        """
        Calculate win/loss streak risk multiplier

        Win streak: Cautiously increase (capped)
        - Each win: +5% up to +50% max
        Loss streak: Reduce more aggressively
        - Each loss: -10% down to -50% max
        """
        if not self.config.streak_adjustment_enabled:
            return 1.0

        if self._win_streak > 0:
            # Positive adjustment for win streak
            adjustment = min(
                self.config.max_streak_adjustment,
                self._win_streak * self.config.streak_bonus_per_win
            )
            return 1.0 + adjustment
        elif self._loss_streak > 0:
            # Negative adjustment for loss streak
            adjustment = min(
                self.config.max_streak_adjustment,
                self._loss_streak * self.config.streak_penalty_per_loss
            )
            return 1.0 - adjustment
        else:
            return 1.0

    def _calculate_correlation_multiplier(self) -> float:
        """
        Calculate correlation-based risk multiplier

        High correlation = concentrated risk = reduce budget
        - Correlation < 0.3: 1.2x (well diversified)
        - Correlation 0.3-0.5: 1.0x (normal)
        - Correlation 0.5-0.7: 0.8x (moderately correlated)
        - Correlation > 0.7: 0.6x (highly correlated)
        """
        if not self.config.correlation_adjustment_enabled:
            return 1.0

        corr = self._avg_correlation

        if corr < 0.3:
            return 1.2
        elif corr < 0.5:
            return 1.0
        elif corr < 0.7:
            return 0.8
        else:
            return 0.6

    def _calculate_liquidity_multiplier(self) -> float:
        """
        Calculate time-of-day liquidity multiplier

        Reduce risk during low liquidity hours (wider spreads, slippage risk)
        """
        if not self.config.liquidity_adjustment_enabled:
            return 1.0

        current_hour = datetime.now(timezone.utc).hour

        for start_hour, end_hour in LOW_LIQUIDITY_HOURS:
            if start_hour <= current_hour < end_hour:
                return 0.7  # 30% reduction during low liquidity

        return 1.0

    def _detect_market_regime(self) -> MarketRegime:
        """Detect market regime from volatility percentile"""
        percentile = self._volatility_percentile

        if percentile < 20:
            return MarketRegime.LOW_VOLATILITY
        elif percentile < 60:
            return MarketRegime.NORMAL
        elif percentile < 80:
            return MarketRegime.ELEVATED_VOLATILITY
        elif percentile < 90:
            return MarketRegime.HIGH_VOLATILITY
        else:
            return MarketRegime.EXTREME_VOLATILITY

    def _get_risk_level_name(self, risk_pct: float) -> str:
        """Get human-readable risk level name"""
        for level_name, level_pct in RISK_LADDER.items():
            if abs(risk_pct - level_pct) < 0.25:
                return level_name
        if risk_pct < 1.0:
            return "ultra_defensive"
        elif risk_pct > 2.25:
            return "aggressive"
        else:
            return "normal"

    def _generate_recommendations(
        self,
        vol_mult: float,
        dd_mult: float,
        streak_mult: float,
        corr_mult: float,
        liq_mult: float,
    ) -> List[str]:
        """Generate actionable recommendations based on multipliers"""
        recommendations = []

        if vol_mult < 0.7:
            recommendations.append(
                f"High volatility detected ({self._volatility_percentile:.0f}th percentile). "
                "Consider reducing position sizes and using tighter stops."
            )

        if dd_mult < 0.7:
            recommendations.append(
                f"Portfolio in drawdown ({self._current_drawdown:.1f}%). "
                "Focus on capital preservation over returns."
            )

        if streak_mult < 0.8:
            recommendations.append(
                f"Loss streak detected ({self._loss_streak} losses). "
                "Consider reviewing strategy performance and reducing size."
            )
        elif streak_mult > 1.2:
            recommendations.append(
                f"Win streak active ({self._win_streak} wins). "
                "Maintain discipline - avoid overconfidence."
            )

        if corr_mult < 0.8:
            recommendations.append(
                f"High portfolio correlation ({self._avg_correlation:.2f}). "
                "Consider diversifying into uncorrelated assets."
            )

        if liq_mult < 1.0:
            recommendations.append(
                "Currently in low-liquidity hours. "
                "Expect wider spreads and potential slippage."
            )

        if not recommendations:
            recommendations.append("Market conditions normal. Standard risk budget applies.")

        return recommendations

    def _get_emergency_budget(self) -> RiskBudgetResponse:
        """Return emergency-reduced budget"""
        base_budget_pct = self.config.base_risk_pct
        emergency_pct = base_budget_pct * self.config.emergency_reduction_factor
        emergency_pct = max(self.config.min_risk_pct, emergency_pct)
        emergency_usd = self._current_equity * (emergency_pct / 100)

        return RiskBudgetResponse(
            base_budget_pct=base_budget_pct,
            base_budget_usd=self._current_equity * (base_budget_pct / 100),
            adjusted_budget_pct=emergency_pct,
            adjusted_budget_usd=emergency_usd,
            volatility_multiplier=self.config.emergency_reduction_factor,
            drawdown_multiplier=self.config.emergency_reduction_factor,
            streak_multiplier=self.config.emergency_reduction_factor,
            correlation_multiplier=self.config.emergency_reduction_factor,
            liquidity_multiplier=self.config.emergency_reduction_factor,
            combined_multiplier=self.config.emergency_reduction_factor,
            market_regime="EMERGENCY",
            risk_level="ultra_defensive",
            max_position_size=emergency_usd,
            recommendations=[
                f"EMERGENCY MODE ACTIVE: {self._emergency_trigger.value if self._emergency_trigger else 'Unknown trigger'}. "
                "Risk significantly reduced. Review portfolio and market conditions before resuming normal operations."
            ],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # MARKET REGIME ADJUSTMENT
    # =========================================================================

    def adjust_for_market_regime(
        self,
        budget: RiskBudgetResponse,
        regime: MarketRegime,
    ) -> RiskBudgetResponse:
        """
        Apply additional adjustment based on market regime

        Args:
            budget: Base budget calculation
            regime: Market regime to adjust for

        Returns:
            Adjusted RiskBudgetResponse
        """
        regime_multipliers = {
            MarketRegime.LOW_VOLATILITY: 1.2,
            MarketRegime.NORMAL: 1.0,
            MarketRegime.ELEVATED_VOLATILITY: 0.8,
            MarketRegime.HIGH_VOLATILITY: 0.6,
            MarketRegime.EXTREME_VOLATILITY: 0.3,
        }

        multiplier = regime_multipliers.get(regime, 1.0)

        adjusted_pct = budget.adjusted_budget_pct * multiplier
        adjusted_pct = max(
            self.config.min_risk_pct,
            min(self.config.max_risk_pct, adjusted_pct)
        )

        adjusted_usd = self._current_equity * (adjusted_pct / 100)

        return RiskBudgetResponse(
            base_budget_pct=budget.base_budget_pct,
            base_budget_usd=budget.base_budget_usd,
            adjusted_budget_pct=adjusted_pct,
            adjusted_budget_usd=adjusted_usd,
            volatility_multiplier=budget.volatility_multiplier * multiplier,
            drawdown_multiplier=budget.drawdown_multiplier,
            streak_multiplier=budget.streak_multiplier,
            correlation_multiplier=budget.correlation_multiplier,
            liquidity_multiplier=budget.liquidity_multiplier,
            combined_multiplier=budget.combined_multiplier * multiplier,
            market_regime=regime.value,
            risk_level=self._get_risk_level_name(adjusted_pct),
            max_position_size=adjusted_usd,
            recommendations=budget.recommendations + [
                f"Regime adjustment applied: {regime.value} -> {multiplier:.0%}"
            ],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    # =========================================================================
    # STRATEGY ALLOCATION
    # =========================================================================

    def allocate_to_strategies(
        self,
        strategies: Dict[str, float],
        performance: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Dict[str, RiskAllocation]:
        """
        Allocate risk budget across strategies

        Args:
            strategies: Dict of strategy_name -> allocation_percentage (0-100)
            performance: Optional dict of strategy_name -> performance metrics

        Returns:
            Dict of strategy_name -> RiskAllocation
        """
        with self._lock:
            # Validate allocations sum to <= 100%
            total_allocation = sum(strategies.values())
            if total_allocation > 100:
                raise ValueError(
                    f"Total allocation ({total_allocation}%) exceeds 100%"
                )

            # Store allocations
            self._strategy_allocations = dict(strategies)
            if performance:
                self._strategy_performance = dict(performance)

            # Calculate current budget
            budget = self.calculate_risk_budget()
            total_budget = budget.adjusted_budget_usd

            allocations = {}

            for strategy_name, allocation_pct in strategies.items():
                # Base allocated budget
                allocated_usd = total_budget * (allocation_pct / 100)

                # Get current usage
                current_usage = self._strategy_usage.get(strategy_name, 0.0)

                # Performance multiplier
                perf_mult = 1.0
                if performance and strategy_name in performance:
                    perf_mult = self._calculate_performance_multiplier(
                        performance[strategy_name]
                    )

                # Effective budget with performance adjustment
                effective_usd = allocated_usd * perf_mult

                allocations[strategy_name] = RiskAllocation(
                    strategy_name=strategy_name,
                    allocation_pct=allocation_pct,
                    allocated_budget_usd=round(allocated_usd, 2),
                    current_usage_usd=round(current_usage, 2),
                    available_budget_usd=round(max(0, allocated_usd - current_usage), 2),
                    utilization_pct=round(
                        (current_usage / allocated_usd * 100) if allocated_usd > 0 else 0, 2
                    ),
                    performance_multiplier=round(perf_mult, 4),
                    effective_budget_usd=round(effective_usd, 2),
                )

            logger.info(
                f"Allocated risk budget across {len(strategies)} strategies: "
                f"total=${total_budget:,.0f}"
            )

            return allocations

    def _calculate_performance_multiplier(
        self,
        metrics: Dict[str, float],
    ) -> float:
        """Calculate performance-based multiplier for a strategy"""
        sharpe = metrics.get("sharpe_ratio", 0)
        trades = metrics.get("trades_count", 0)

        # Require minimum trades
        if trades < 10:
            return 1.0

        # Sharpe-based adjustment
        if sharpe > 2.0:
            return 1.3
        elif sharpe > 1.5:
            return 1.2
        elif sharpe > 1.0:
            return 1.1
        elif sharpe < 0:
            return 0.5
        elif sharpe < 0.5:
            return 0.7
        else:
            return 1.0

    def get_strategy_allocation(self, strategy_name: str) -> Optional[RiskAllocation]:
        """Get allocation for a specific strategy"""
        with self._lock:
            if strategy_name not in self._strategy_allocations:
                return None

            budget = self.calculate_risk_budget()
            allocation_pct = self._strategy_allocations[strategy_name]
            allocated_usd = budget.adjusted_budget_usd * (allocation_pct / 100)
            current_usage = self._strategy_usage.get(strategy_name, 0.0)

            perf_mult = 1.0
            if strategy_name in self._strategy_performance:
                perf_mult = self._calculate_performance_multiplier(
                    self._strategy_performance[strategy_name]
                )

            return RiskAllocation(
                strategy_name=strategy_name,
                allocation_pct=allocation_pct,
                allocated_budget_usd=round(allocated_usd, 2),
                current_usage_usd=round(current_usage, 2),
                available_budget_usd=round(max(0, allocated_usd - current_usage), 2),
                utilization_pct=round(
                    (current_usage / allocated_usd * 100) if allocated_usd > 0 else 0, 2
                ),
                performance_multiplier=round(perf_mult, 4),
                effective_budget_usd=round(allocated_usd * perf_mult, 2),
            )

    # =========================================================================
    # RISK UTILIZATION
    # =========================================================================

    def get_risk_utilization(self) -> RiskUtilization:
        """Get current risk utilization across all strategies and assets"""
        with self._lock:
            budget = self.calculate_risk_budget()
            total_budget = budget.adjusted_budget_usd

            # Sum all usage
            total_used = sum(self._strategy_usage.values())

            # By strategy
            by_strategy = {}
            for strategy_name, usage in self._strategy_usage.items():
                allocation_pct = self._strategy_allocations.get(strategy_name, 0)
                allocated_budget = total_budget * (allocation_pct / 100)
                by_strategy[strategy_name] = {
                    "allocated": round(allocated_budget, 2),
                    "used": round(usage, 2),
                    "available": round(max(0, allocated_budget - usage), 2),
                    "utilization_pct": round(
                        (usage / allocated_budget * 100) if allocated_budget > 0 else 0, 2
                    ),
                }

            # By asset
            by_asset = {}
            for symbol, usage in self._asset_usage.items():
                by_asset[symbol] = {
                    "used": round(usage, 2),
                    "pct_of_total": round(
                        (usage / total_budget * 100) if total_budget > 0 else 0, 2
                    ),
                }

            return RiskUtilization(
                total_budget_usd=round(total_budget, 2),
                used_budget_usd=round(total_used, 2),
                available_budget_usd=round(max(0, total_budget - total_used), 2),
                utilization_pct=round(
                    (total_used / total_budget * 100) if total_budget > 0 else 0, 2
                ),
                by_strategy=by_strategy,
                by_asset=by_asset,
                emergency_mode=self._emergency_mode,
                current_risk_level=self._get_risk_level_name(self._current_risk_pct),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

    def update_usage(
        self,
        strategy_name: str,
        symbol: str,
        risk_amount: float,
    ) -> None:
        """Update risk usage for a strategy/symbol"""
        with self._lock:
            self._strategy_usage[strategy_name] = (
                self._strategy_usage.get(strategy_name, 0.0) + risk_amount
            )
            self._asset_usage[symbol] = (
                self._asset_usage.get(symbol, 0.0) + risk_amount
            )

            logger.debug(
                f"Updated usage: {strategy_name}/{symbol} +${risk_amount:.2f}"
            )

    def release_usage(
        self,
        strategy_name: str,
        symbol: str,
        risk_amount: float,
    ) -> None:
        """Release risk usage when position closed"""
        with self._lock:
            self._strategy_usage[strategy_name] = max(
                0,
                self._strategy_usage.get(strategy_name, 0.0) - risk_amount
            )
            self._asset_usage[symbol] = max(
                0,
                self._asset_usage.get(symbol, 0.0) - risk_amount
            )

            logger.debug(
                f"Released usage: {strategy_name}/{symbol} -${risk_amount:.2f}"
            )

    def can_place_trade(
        self,
        strategy_name: str,
        symbol: str,
        risk_amount: float,
    ) -> Tuple[bool, str]:
        """
        Check if a trade can be placed within budget limits

        Args:
            strategy_name: Strategy placing the trade
            symbol: Asset symbol
            risk_amount: Risk amount in USD

        Returns:
            Tuple of (can_trade, reason)
        """
        with self._lock:
            # Emergency mode check
            if self._emergency_mode:
                return False, f"Emergency mode active: {self._emergency_trigger.value if self._emergency_trigger else 'unknown'}"

            # Get current budget
            budget = self.calculate_risk_budget()
            total_budget = budget.adjusted_budget_usd

            # Check total budget
            total_used = sum(self._strategy_usage.values())
            if total_used + risk_amount > total_budget:
                return False, f"Would exceed total budget (used: ${total_used:.0f}, limit: ${total_budget:.0f})"

            # Check strategy allocation
            if strategy_name in self._strategy_allocations:
                allocation_pct = self._strategy_allocations[strategy_name]
                strategy_budget = total_budget * (allocation_pct / 100)
                strategy_used = self._strategy_usage.get(strategy_name, 0.0)

                if strategy_used + risk_amount > strategy_budget:
                    return False, f"Would exceed {strategy_name} budget (used: ${strategy_used:.0f}, limit: ${strategy_budget:.0f})"

            return True, "Trade approved within risk limits"

    # =========================================================================
    # EMERGENCY TRIGGERS
    # =========================================================================

    def emergency_risk_reduction(
        self,
        trigger_reason: EmergencyTrigger,
        details: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Trigger emergency risk reduction

        Args:
            trigger_reason: Reason for emergency trigger
            details: Optional additional details

        Returns:
            Dict with emergency state details
        """
        with self._lock:
            self._emergency_mode = True
            self._emergency_trigger = trigger_reason

            # Generate critical alert
            alert = RiskBudgetAlert(
                severity=RiskBudgetAlertSeverity.EMERGENCY,
                message=f"Emergency risk reduction triggered: {trigger_reason.value}",
                timestamp=datetime.now(timezone.utc),
                trigger=trigger_reason.value,
                recommendations=[
                    "Stop all new position entries",
                    "Review all open positions",
                    "Identify and close high-risk positions",
                    "Wait for market conditions to normalize",
                ],
                metadata={"details": details} if details else {},
            )
            self._alerts.append(alert)

            logger.critical(
                f"EMERGENCY RISK REDUCTION: {trigger_reason.value} - {details}"
            )

            return {
                "success": True,
                "emergency_mode": True,
                "trigger": trigger_reason.value,
                "details": details,
                "reduction_factor": self.config.emergency_reduction_factor,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def clear_emergency_mode(self, reason: str = "Manual clear") -> Dict[str, Any]:
        """Clear emergency mode and resume normal operations"""
        with self._lock:
            prev_trigger = self._emergency_trigger

            self._emergency_mode = False
            self._emergency_trigger = None

            logger.info(f"Emergency mode cleared: {reason}")

            return {
                "success": True,
                "emergency_mode": False,
                "previous_trigger": prev_trigger.value if prev_trigger else None,
                "clear_reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def check_emergency_triggers(self) -> Optional[EmergencyTrigger]:
        """Check if any emergency conditions are met"""
        with self._lock:
            # Check daily loss limit
            if abs(self._daily_pnl) >= self._current_equity * (self.config.max_daily_loss_pct / 100):
                return EmergencyTrigger.DAILY_LOSS_LIMIT

            # Check max drawdown
            if self._current_drawdown >= self.config.max_drawdown_pct:
                return EmergencyTrigger.MAX_DRAWDOWN

            # Check extreme volatility
            if self._volatility_percentile >= 95:
                return EmergencyTrigger.EXTREME_VOLATILITY

            # Check correlation spike
            if self._avg_correlation >= 0.9:
                return EmergencyTrigger.CORRELATION_SPIKE

            return None

    # =========================================================================
    # MANUAL ADJUSTMENT
    # =========================================================================

    def manual_adjust(
        self,
        adjustment_type: str,
        value: Optional[float] = None,
        reason: str = "Manual adjustment",
        adjusted_by: str = "user",
    ) -> RiskAdjustment:
        """
        Manually adjust risk budget

        Args:
            adjustment_type: 'increase', 'decrease', 'set_level', 'emergency_stop'
            value: Adjustment value (percentage for increase/decrease, level for set_level)
            reason: Reason for adjustment
            adjusted_by: Who made the adjustment

        Returns:
            RiskAdjustment record
        """
        with self._lock:
            previous_risk = self._current_risk_pct

            if adjustment_type == "increase":
                new_risk = min(
                    self.config.max_risk_pct,
                    previous_risk + (value or 0.5)
                )
            elif adjustment_type == "decrease":
                new_risk = max(
                    self.config.min_risk_pct,
                    previous_risk - (value or 0.5)
                )
            elif adjustment_type == "set_level":
                if value is None:
                    raise ValueError("set_level requires a value")
                new_risk = max(
                    self.config.min_risk_pct,
                    min(self.config.max_risk_pct, value)
                )
            elif adjustment_type == "emergency_stop":
                new_risk = self.config.min_risk_pct
                self.emergency_risk_reduction(EmergencyTrigger.MANUAL_TRIGGER, reason)
            else:
                raise ValueError(f"Unknown adjustment type: {adjustment_type}")

            self._current_risk_pct = new_risk
            self.config.base_risk_pct = new_risk

            adjustment = RiskAdjustment(
                adjustment_type=adjustment_type,
                previous_risk_pct=round(previous_risk, 4),
                new_risk_pct=round(new_risk, 4),
                reason=reason,
                adjusted_by=adjusted_by,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            self._adjustment_history.append(adjustment)

            logger.info(
                f"Manual risk adjustment: {adjustment_type} "
                f"{previous_risk:.2f}% -> {new_risk:.2f}% ({reason})"
            )

            return adjustment

    # =========================================================================
    # HISTORY AND TRACKING
    # =========================================================================

    def _record_budget_history(self, risk_pct: float, risk_usd: float) -> None:
        """Record budget calculation to history"""
        entry = RiskBudgetHistoryEntry(
            timestamp=datetime.now(timezone.utc),
            equity=self._current_equity,
            risk_budget_pct=risk_pct,
            risk_budget_usd=risk_usd,
            market_regime=self._current_regime.value,
            volatility_percentile=self._volatility_percentile,
            drawdown_pct=self._current_drawdown,
            multipliers={
                "volatility": self._calculate_volatility_multiplier(),
                "drawdown": self._calculate_drawdown_multiplier(),
                "streak": self._calculate_streak_multiplier(),
                "correlation": self._calculate_correlation_multiplier(),
                "liquidity": self._calculate_liquidity_multiplier(),
            },
            emergency_mode=self._emergency_mode,
        )
        self._budget_history.append(entry)

    def get_budget_history(
        self,
        hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """Get budget history for specified number of hours"""
        with self._lock:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
            history = [
                entry.to_dict()
                for entry in self._budget_history
                if entry.timestamp >= cutoff
            ]
            return history

    def get_adjustment_history(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get recent manual adjustments"""
        with self._lock:
            return [
                adj.to_dict()
                for adj in self._adjustment_history[-limit:]
            ]

    # =========================================================================
    # ALERTS
    # =========================================================================

    def _check_and_generate_alerts(self, risk_pct: float, budget_usd: float) -> None:
        """Check conditions and generate alerts (without recursion)"""
        # Calculate utilization directly to avoid recursion
        total_used = sum(self._strategy_usage.values())
        utilization_pct = (total_used / budget_usd * 100) if budget_usd > 0 else 0
        
        # High utilization alert
        if utilization_pct >= 90:
            self._alerts.append(RiskBudgetAlert(
                severity=RiskBudgetAlertSeverity.CRITICAL,
                message=f"Risk budget {utilization_pct:.0f}% utilized - near limit",
                timestamp=datetime.now(timezone.utc),
                current_value=utilization_pct,
                threshold=90,
                recommendations=["Reduce position sizes", "Close losing positions"],
            ))
        elif utilization_pct >= 80:
            self._alerts.append(RiskBudgetAlert(
                severity=RiskBudgetAlertSeverity.WARNING,
                message=f"Risk budget {utilization_pct:.0f}% utilized",
                timestamp=datetime.now(timezone.utc),
                current_value=utilization_pct,
                threshold=80,
                recommendations=["Monitor positions closely"],
            ))

        # Low risk level alert
        if risk_pct <= self.config.min_risk_pct * 1.2:
            self._alerts.append(RiskBudgetAlert(
                severity=RiskBudgetAlertSeverity.HIGH,
                message=f"Risk budget at minimum levels ({risk_pct:.2f}%)",
                timestamp=datetime.now(timezone.utc),
                current_value=risk_pct,
                threshold=self.config.min_risk_pct,
                recommendations=["Review market conditions", "Evaluate portfolio health"],
            ))

    def get_alerts(
        self,
        min_severity: RiskBudgetAlertSeverity = RiskBudgetAlertSeverity.INFO,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Get recent alerts filtered by severity"""
        with self._lock:
            severity_order = [
                RiskBudgetAlertSeverity.INFO,
                RiskBudgetAlertSeverity.WARNING,
                RiskBudgetAlertSeverity.HIGH,
                RiskBudgetAlertSeverity.CRITICAL,
                RiskBudgetAlertSeverity.EMERGENCY,
            ]
            min_idx = severity_order.index(min_severity)

            filtered = [
                alert.to_dict()
                for alert in self._alerts[-limit:]
                if severity_order.index(alert.severity) >= min_idx
            ]
            return filtered

    # =========================================================================
    # KELLY CRITERION INTEGRATION
    # =========================================================================

    def update_kelly_data(self, kelly_data: Dict[str, Dict[str, float]]) -> None:
        """
        Update Kelly criterion data for budget integration

        Args:
            kelly_data: Dict of strategy_name -> kelly metrics
        """
        with self._lock:
            self._kelly_data = dict(kelly_data)
            logger.debug(f"Updated Kelly data for {len(kelly_data)} strategies")

    def get_kelly_adjusted_budget(self, strategy_name: str) -> float:
        """
        Get risk budget adjusted by Kelly recommendation

        The Kelly-suggested position size serves as a cap on the risk budget.
        """
        with self._lock:
            budget = self.calculate_risk_budget()
            base_budget = budget.adjusted_budget_usd

            if strategy_name not in self._kelly_data:
                return base_budget

            kelly = self._kelly_data[strategy_name]
            kelly_pct = kelly.get("fractional_kelly_pct", 0)

            if kelly_pct <= 0:
                # No edge - return minimum
                return base_budget * 0.25

            # Kelly-suggested budget
            kelly_budget = self._current_equity * (kelly_pct / 100)

            # Use minimum of risk budget and Kelly suggestion
            return min(base_budget, kelly_budget)

    # =========================================================================
    # CORRELATION MANAGER INTEGRATION
    # =========================================================================

    def update_correlation_data(
        self,
        correlation_matrix: Dict[str, float],
        avg_correlation: float,
    ) -> None:
        """
        Update correlation data for budget adjustment

        Args:
            correlation_matrix: Dict of symbol pairs -> correlation
            avg_correlation: Portfolio average correlation
        """
        with self._lock:
            self._correlation_data = dict(correlation_matrix)
            self._avg_correlation = avg_correlation
            logger.debug(f"Updated correlation data: avg={avg_correlation:.4f}")

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def get_current_budget(self) -> Dict[str, Any]:
        """Get current risk budget state"""
        with self._lock:
            budget = self.calculate_risk_budget()
            utilization = self.get_risk_utilization()

            return {
                "budget": budget.to_dict(),
                "utilization": utilization.to_dict(),
                "emergency_mode": self._emergency_mode,
                "config": self.config.to_dict(),
            }

    def get_state(self) -> Dict[str, Any]:
        """Get complete state for persistence"""
        with self._lock:
            return {
                "config": self.config.to_dict(),
                "current_equity": self._current_equity,
                "current_risk_pct": self._current_risk_pct,
                "peak_equity": self._peak_equity,
                "volatility_percentile": self._volatility_percentile,
                "current_drawdown": self._current_drawdown,
                "win_streak": self._win_streak,
                "loss_streak": self._loss_streak,
                "avg_correlation": self._avg_correlation,
                "emergency_mode": self._emergency_mode,
                "strategy_allocations": dict(self._strategy_allocations),
                "strategy_usage": dict(self._strategy_usage),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence"""
        with self._lock:
            if "config" in state:
                self.config = RiskBudgetConfig(**state["config"])
            if "current_equity" in state:
                self._current_equity = state["current_equity"]
            if "peak_equity" in state:
                self._peak_equity = state["peak_equity"]
            if "volatility_percentile" in state:
                self._volatility_percentile = state["volatility_percentile"]
            if "current_drawdown" in state:
                self._current_drawdown = state["current_drawdown"]
            if "win_streak" in state:
                self._win_streak = state["win_streak"]
            if "loss_streak" in state:
                self._loss_streak = state["loss_streak"]
            if "avg_correlation" in state:
                self._avg_correlation = state["avg_correlation"]
            if "strategy_allocations" in state:
                self._strategy_allocations = state["strategy_allocations"]
            if "strategy_usage" in state:
                self._strategy_usage = state["strategy_usage"]

            logger.info("Loaded risk budget state from persistence")

    def reset(self) -> None:
        """Reset to initial state"""
        with self._lock:
            self._current_equity = self.config.base_equity
            self._current_risk_pct = self.config.base_risk_pct
            self._current_regime = MarketRegime.NORMAL
            self._emergency_mode = False
            self._emergency_trigger = None
            self._volatility_percentile = 50.0
            self._current_drawdown = 0.0
            self._peak_equity = self.config.base_equity
            self._daily_pnl = 0.0
            self._win_streak = 0
            self._loss_streak = 0
            self._avg_correlation = 0.5
            self._strategy_allocations.clear()
            self._strategy_usage.clear()
            self._strategy_performance.clear()
            self._asset_usage.clear()
            self._budget_history.clear()
            self._adjustment_history.clear()
            self._alerts.clear()
            self._kelly_data.clear()
            self._correlation_data.clear()

            logger.info("DynamicRiskBudget reset to initial state")

    # =========================================================================
    # TRADE TRACKING (for streak calculation)
    # =========================================================================

    def record_trade_result(self, is_win: bool, pnl: float) -> None:
        """
        Record trade result for streak tracking

        Args:
            is_win: Whether trade was profitable
            pnl: Profit/loss amount in USD
        """
        with self._lock:
            # Update daily P&L
            self._daily_pnl += pnl

            # Update streaks
            if is_win:
                if self._win_streak >= 0:
                    self._win_streak += 1
                else:
                    self._win_streak = 1
                self._loss_streak = 0
            else:
                if self._loss_streak >= 0:
                    self._loss_streak += 1
                else:
                    self._loss_streak = 1
                self._win_streak = 0

            # Check emergency triggers
            trigger = self.check_emergency_triggers()
            if trigger and not self._emergency_mode:
                self.emergency_risk_reduction(trigger, f"Auto-triggered after trade: P&L=${pnl:.2f}")

            logger.debug(
                f"Trade recorded: {'WIN' if is_win else 'LOSS'} ${pnl:.2f}, "
                f"streak: W{self._win_streak}/L{self._loss_streak}"
            )

    def reset_daily_pnl(self) -> None:
        """Reset daily P&L (call at start of trading day)"""
        with self._lock:
            self._daily_pnl = 0.0
            logger.info("Daily P&L reset")


# =============================================================================
# GLOBAL SINGLETON
# =============================================================================

_risk_budget_manager: Optional[DynamicRiskBudget] = None
_manager_lock = RLock()


def get_risk_budget_manager(
    config: Optional[RiskBudgetConfig] = None,
) -> DynamicRiskBudget:
    """
    Get or create global risk budget manager instance (singleton)

    Args:
        config: Optional config for first initialization

    Returns:
        DynamicRiskBudget instance
    """
    global _risk_budget_manager

    with _manager_lock:
        if _risk_budget_manager is None:
            _risk_budget_manager = DynamicRiskBudget(config=config)
            logger.info("Created global risk budget manager instance")
        return _risk_budget_manager


def reset_risk_budget_manager() -> None:
    """Reset global risk budget manager instance"""
    global _risk_budget_manager

    with _manager_lock:
        if _risk_budget_manager is not None:
            _risk_budget_manager.reset()
        _risk_budget_manager = None
        logger.info("Reset global risk budget manager instance")
