"""
Risk Coordinator
=================
Purpose: Global risk management and coordination across all trading strategies

The Risk Coordinator provides:
1. Total portfolio risk limit enforcement
2. Per-strategy risk limits
3. Correlation limits across strategies
4. Maximum concurrent positions management
5. Emergency stop coordination
6. Risk budget allocation

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
from datetime import datetime, timezone, timedelta
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
import statistics
import math

from app.orchestration.models import (
    StrategyState,
    StrategyStatus,
    StrategyAllocation,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# RISK COORDINATOR CONFIGURATION
# =============================================================================

@dataclass
class RiskCoordinatorConfig:
    """
    Configuration for Risk Coordinator

    Controls portfolio-wide and per-strategy risk limits.
    """
    # Portfolio-level limits
    max_total_exposure_pct: float = 80.0  # Max 80% of capital deployed
    max_total_drawdown_pct: float = 15.0  # Emergency stop at 15% drawdown
    max_daily_loss_pct: float = 5.0  # Max daily portfolio loss
    max_concurrent_positions: int = 20  # Max positions across all strategies

    # Per-strategy limits
    max_strategy_drawdown_pct: float = 10.0  # Max drawdown per strategy
    max_strategy_daily_loss_pct: float = 3.0  # Max daily loss per strategy
    max_strategy_positions: int = 5  # Max positions per strategy

    # Risk budget settings
    total_risk_budget_pct: float = 10.0  # Total risk budget (% of capital)
    per_strategy_risk_budget_pct: float = 2.0  # Risk budget per strategy
    max_single_trade_risk_pct: float = 1.0  # Max risk per trade

    # Correlation limits
    max_correlation: float = 0.7  # Max correlation between strategies
    max_correlated_strategies: int = 3  # Max highly correlated strategies
    correlation_exposure_penalty: float = 0.3  # Reduce exposure for correlated

    # Emergency stop settings
    emergency_stop_enabled: bool = True
    emergency_stop_drawdown_pct: float = 20.0  # Hard stop at 20%
    emergency_stop_daily_loss_pct: float = 7.0  # Hard stop at 7% daily

    # Recovery settings
    recovery_period_hours: int = 24  # Hours before allowing full trading after stop
    gradual_recovery_steps: int = 4  # Steps to full trading

    # Diversification requirements
    min_strategies_active: int = 2  # Minimum active strategies
    max_single_strategy_allocation: float = 25.0  # Max to any one strategy

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "max_total_drawdown_pct": self.max_total_drawdown_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_correlation": self.max_correlation,
            "emergency_stop_enabled": self.emergency_stop_enabled,
        }


# =============================================================================
# RISK UTILIZATION TRACKING
# =============================================================================

@dataclass
class RiskUtilization:
    """
    Current risk utilization metrics
    """
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Portfolio level
    total_exposure_pct: float = 0.0
    current_drawdown_pct: float = 0.0
    daily_loss_pct: float = 0.0
    total_positions: int = 0

    # Risk budget
    total_risk_used_pct: float = 0.0
    risk_budget_remaining_pct: float = 0.0

    # Strategy breakdown
    strategy_exposures: Dict[str, float] = field(default_factory=dict)
    strategy_risk_used: Dict[str, float] = field(default_factory=dict)

    # Limits status
    exposure_limit_pct: float = 0.0
    drawdown_limit_pct: float = 0.0
    position_limit_pct: float = 0.0

    # Warnings
    warnings: List[str] = field(default_factory=list)
    is_at_limit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "total_exposure_pct": self.total_exposure_pct,
            "current_drawdown_pct": self.current_drawdown_pct,
            "daily_loss_pct": self.daily_loss_pct,
            "total_positions": self.total_positions,
            "total_risk_used_pct": self.total_risk_used_pct,
            "risk_budget_remaining_pct": self.risk_budget_remaining_pct,
            "is_at_limit": self.is_at_limit,
            "warnings_count": len(self.warnings),
            "warnings": self.warnings[:5],  # First 5 warnings
        }


# =============================================================================
# RISK CHECK RESULT
# =============================================================================

@dataclass
class RiskCheckResult:
    """
    Result of a risk check for a proposed action
    """
    allowed: bool
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    adjusted_size_pct: Optional[float] = None  # Suggested reduced size
    current_utilization: Optional[RiskUtilization] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "warnings": self.warnings,
            "adjusted_size_pct": self.adjusted_size_pct,
        }


# =============================================================================
# RISK COORDINATOR
# =============================================================================

class RiskCoordinator:
    """
    Global Risk Management Coordinator

    Provides portfolio-wide risk management to ensure that:
    1. Total exposure stays within limits
    2. Drawdown limits are enforced
    3. Position limits are respected
    4. Risk is properly distributed across strategies
    5. Emergency stops are triggered when needed

    Key Responsibilities:

    1. Portfolio Risk Limits:
       - Maximum total exposure (% of capital deployed)
       - Maximum drawdown (emergency stop)
       - Maximum daily loss
       - Maximum concurrent positions

    2. Per-Strategy Limits:
       - Maximum strategy drawdown
       - Maximum strategy daily loss
       - Maximum positions per strategy
       - Risk budget per strategy

    3. Correlation Management:
       - Track correlations between strategies
       - Reduce exposure for highly correlated strategies
       - Ensure diversification requirements

    4. Risk Budget Allocation:
       - Allocate risk budget to strategies
       - Monitor risk utilization
       - Prevent over-leveraging

    5. Emergency Controls:
       - Emergency stop all trading
       - Gradual recovery after stop
       - Coordination with all strategies

    Usage:
        coordinator = RiskCoordinator()

        # Check if new trade is allowed
        result = coordinator.check_new_trade(strategy_id, symbol, size_pct)

        # Update after trade
        coordinator.update_position(strategy_id, symbol, size_pct)

        # Get current utilization
        utilization = coordinator.get_risk_utilization()

        # Emergency stop
        coordinator.emergency_stop("Market conditions dangerous")
    """

    def __init__(self, config: Optional[RiskCoordinatorConfig] = None):
        """
        Initialize Risk Coordinator

        Args:
            config: Risk coordinator configuration
        """
        self.config = config or RiskCoordinatorConfig()
        self._lock = RLock()

        # Portfolio state
        self._total_capital: float = 100000.0
        self._current_equity: float = 100000.0
        self._peak_equity: float = 100000.0
        self._today_starting_equity: float = 100000.0

        # Position tracking
        self._positions: Dict[str, Dict[str, float]] = defaultdict(dict)  # strategy -> symbol -> size_pct
        self._total_positions: int = 0
        self._total_exposure_pct: float = 0.0

        # Risk budget tracking
        self._strategy_risk_used: Dict[str, float] = defaultdict(float)
        self._total_risk_used: float = 0.0

        # Strategy states
        self._strategy_states: Dict[str, StrategyState] = {}
        self._strategy_drawdowns: Dict[str, float] = defaultdict(float)
        self._strategy_daily_loss: Dict[str, float] = defaultdict(float)

        # Correlation matrix
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}

        # Emergency stop state
        self._is_emergency_stopped: bool = False
        self._emergency_stop_time: Optional[datetime] = None
        self._emergency_stop_reason: str = ""

        # Recovery state
        self._in_recovery: bool = False
        self._recovery_start_time: Optional[datetime] = None
        self._recovery_step: int = 0

        # History
        self._risk_events: List[Dict[str, Any]] = []

        logger.info(
            f"RiskCoordinator initialized: "
            f"max_exposure={self.config.max_total_exposure_pct}%, "
            f"max_drawdown={self.config.max_total_drawdown_pct}%, "
            f"max_positions={self.config.max_concurrent_positions}"
        )

    # =========================================================================
    # CAPITAL AND EQUITY MANAGEMENT
    # =========================================================================

    def set_total_capital(self, capital: float) -> None:
        """Set total portfolio capital"""
        with self._lock:
            self._total_capital = capital
            self._current_equity = capital
            self._peak_equity = capital
            self._today_starting_equity = capital

    def update_equity(self, current_equity: float) -> Dict[str, Any]:
        """
        Update current equity and check for limits

        Args:
            current_equity: Current portfolio equity

        Returns:
            Status update with any triggered actions
        """
        with self._lock:
            self._current_equity = current_equity

            # Update peak equity
            if current_equity > self._peak_equity:
                self._peak_equity = current_equity

            # Calculate drawdown
            drawdown_pct = 0.0
            if self._peak_equity > 0:
                drawdown_pct = (self._peak_equity - current_equity) / self._peak_equity * 100

            # Calculate daily loss
            daily_loss_pct = 0.0
            if self._today_starting_equity > 0:
                daily_loss_pct = (self._today_starting_equity - current_equity) / self._today_starting_equity * 100

            result = {
                "current_equity": current_equity,
                "drawdown_pct": drawdown_pct,
                "daily_loss_pct": daily_loss_pct,
                "actions": []
            }

            # Check for emergency stop triggers
            if self.config.emergency_stop_enabled:
                if drawdown_pct >= self.config.emergency_stop_drawdown_pct:
                    self._trigger_emergency_stop(f"Drawdown {drawdown_pct:.1f}% exceeds emergency limit")
                    result["actions"].append("emergency_stop_triggered")

                if daily_loss_pct >= self.config.emergency_stop_daily_loss_pct:
                    self._trigger_emergency_stop(f"Daily loss {daily_loss_pct:.1f}% exceeds emergency limit")
                    result["actions"].append("emergency_stop_triggered")

            return result

    def reset_daily_tracking(self) -> None:
        """Reset daily tracking at start of new day"""
        with self._lock:
            self._today_starting_equity = self._current_equity
            for strategy_id in self._strategy_daily_loss:
                self._strategy_daily_loss[strategy_id] = 0.0

            logger.info("Reset daily risk tracking")

    # =========================================================================
    # TRADE RISK CHECKS
    # =========================================================================

    def check_new_trade(
        self,
        strategy_id: str,
        symbol: str,
        size_pct: float,
        risk_pct: float = 0.0
    ) -> RiskCheckResult:
        """
        Check if a new trade is allowed based on risk limits

        Args:
            strategy_id: Strategy requesting the trade
            symbol: Trading symbol
            size_pct: Position size as % of capital
            risk_pct: Risk amount as % of capital (for stop loss)

        Returns:
            RiskCheckResult indicating if trade is allowed
        """
        with self._lock:
            warnings = []

            # Check emergency stop
            if self._is_emergency_stopped:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Emergency stop active: {self._emergency_stop_reason}",
                    warnings=warnings
                )

            # Check total exposure
            new_total_exposure = self._total_exposure_pct + size_pct
            if new_total_exposure > self.config.max_total_exposure_pct:
                if new_total_exposure > self.config.max_total_exposure_pct * 1.1:
                    return RiskCheckResult(
                        allowed=False,
                        reason=f"Would exceed max exposure ({new_total_exposure:.1f}% > {self.config.max_total_exposure_pct}%)",
                        warnings=warnings,
                        adjusted_size_pct=max(0, self.config.max_total_exposure_pct - self._total_exposure_pct)
                    )
                else:
                    warnings.append(f"Approaching exposure limit ({new_total_exposure:.1f}%)")

            # Check position count
            new_position_count = self._total_positions + 1
            if new_position_count > self.config.max_concurrent_positions:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Would exceed max positions ({new_position_count} > {self.config.max_concurrent_positions})",
                    warnings=warnings
                )

            # Check strategy position limit
            strategy_positions = len(self._positions.get(strategy_id, {}))
            if strategy_positions >= self.config.max_strategy_positions:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Strategy {strategy_id} at position limit ({strategy_positions})",
                    warnings=warnings
                )

            # Check strategy drawdown
            strategy_dd = self._strategy_drawdowns.get(strategy_id, 0.0)
            if strategy_dd >= self.config.max_strategy_drawdown_pct:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Strategy {strategy_id} at drawdown limit ({strategy_dd:.1f}%)",
                    warnings=warnings
                )

            # Check strategy daily loss
            strategy_daily_loss = self._strategy_daily_loss.get(strategy_id, 0.0)
            if strategy_daily_loss >= self.config.max_strategy_daily_loss_pct:
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Strategy {strategy_id} at daily loss limit ({strategy_daily_loss:.1f}%)",
                    warnings=warnings
                )

            # Check risk budget
            if risk_pct > 0:
                new_risk_used = self._total_risk_used + risk_pct
                if new_risk_used > self.config.total_risk_budget_pct:
                    return RiskCheckResult(
                        allowed=False,
                        reason=f"Would exceed total risk budget ({new_risk_used:.1f}% > {self.config.total_risk_budget_pct}%)",
                        warnings=warnings
                    )

                strategy_risk_used = self._strategy_risk_used[strategy_id] + risk_pct
                if strategy_risk_used > self.config.per_strategy_risk_budget_pct:
                    return RiskCheckResult(
                        allowed=False,
                        reason=f"Strategy risk budget exceeded ({strategy_risk_used:.1f}%)",
                        warnings=warnings
                    )

                if risk_pct > self.config.max_single_trade_risk_pct:
                    warnings.append(f"Trade risk ({risk_pct:.1f}%) exceeds recommended max ({self.config.max_single_trade_risk_pct}%)")

            # Check correlation limits
            correlation_penalty = self._check_correlation_limits(strategy_id)
            adjusted_size = None
            if correlation_penalty > 0:
                warnings.append(f"High correlation with existing strategies (penalty: {correlation_penalty:.0%})")
                adjusted_size = size_pct * (1 - correlation_penalty)

            # Check if in recovery
            if self._in_recovery:
                recovery_factor = self._get_recovery_factor()
                warnings.append(f"In recovery mode (factor: {recovery_factor:.0%})")
                if adjusted_size:
                    adjusted_size *= recovery_factor
                else:
                    adjusted_size = size_pct * recovery_factor

            utilization = self._calculate_utilization()

            return RiskCheckResult(
                allowed=True,
                reason="Trade allowed",
                warnings=warnings,
                adjusted_size_pct=adjusted_size,
                current_utilization=utilization
            )

    def _check_correlation_limits(self, strategy_id: str) -> float:
        """
        Check correlation limits and return penalty factor

        Returns:
            Penalty factor (0 = no penalty, 1 = full penalty)
        """
        if strategy_id not in self._correlation_matrix:
            return 0.0

        # Count highly correlated strategies with open positions
        correlated_count = 0
        max_correlation = 0.0

        for other_id, correlation in self._correlation_matrix.get(strategy_id, {}).items():
            if other_id != strategy_id and other_id in self._positions:
                if correlation >= self.config.max_correlation:
                    correlated_count += 1
                    max_correlation = max(max_correlation, correlation)

        if correlated_count >= self.config.max_correlated_strategies:
            # Apply penalty based on correlation
            return min(1.0, self.config.correlation_exposure_penalty * correlated_count)

        return 0.0

    def _get_recovery_factor(self) -> float:
        """Get recovery factor for position sizing"""
        if not self._in_recovery or not self._recovery_start_time:
            return 1.0

        # Calculate time since recovery started
        elapsed = datetime.now(timezone.utc) - self._recovery_start_time
        recovery_hours = self.config.recovery_period_hours

        # Calculate current step
        step_duration = recovery_hours / self.config.gradual_recovery_steps
        current_step = int(elapsed.total_seconds() / 3600 / step_duration)
        current_step = min(current_step, self.config.gradual_recovery_steps - 1)

        # Return factor (0.25, 0.5, 0.75, 1.0 for 4 steps)
        return (current_step + 1) / self.config.gradual_recovery_steps

    # =========================================================================
    # POSITION TRACKING
    # =========================================================================

    def update_position(
        self,
        strategy_id: str,
        symbol: str,
        size_pct: float,
        risk_pct: float = 0.0
    ) -> None:
        """
        Update position tracking after trade

        Args:
            strategy_id: Strategy that opened/modified position
            symbol: Trading symbol
            size_pct: Position size as % of capital (0 to close)
            risk_pct: Risk amount as % of capital
        """
        with self._lock:
            if size_pct > 0:
                # Opening or increasing position
                old_size = self._positions[strategy_id].get(symbol, 0)
                self._positions[strategy_id][symbol] = size_pct

                # Update totals
                if old_size == 0:
                    self._total_positions += 1

                self._total_exposure_pct += (size_pct - old_size)

                # Update risk tracking
                if risk_pct > 0:
                    self._strategy_risk_used[strategy_id] += risk_pct
                    self._total_risk_used += risk_pct

            else:
                # Closing position
                if symbol in self._positions[strategy_id]:
                    old_size = self._positions[strategy_id][symbol]
                    del self._positions[strategy_id][symbol]

                    self._total_positions -= 1
                    self._total_exposure_pct -= old_size

                    # Clear risk used for this position
                    # (simplified - in reality would need to track per position)

    def close_all_positions(self, strategy_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Mark all positions as closed (for tracking)

        Args:
            strategy_id: Optional strategy to close (all if None)

        Returns:
            Closure summary
        """
        with self._lock:
            closed = []

            if strategy_id:
                # Close specific strategy positions
                if strategy_id in self._positions:
                    for symbol, size in list(self._positions[strategy_id].items()):
                        closed.append({"strategy": strategy_id, "symbol": symbol, "size": size})
                        self._total_exposure_pct -= size
                        self._total_positions -= 1
                    self._positions[strategy_id].clear()
            else:
                # Close all positions
                for strat_id, positions in list(self._positions.items()):
                    for symbol, size in positions.items():
                        closed.append({"strategy": strat_id, "symbol": symbol, "size": size})
                    self._total_positions -= len(positions)

                self._positions.clear()
                self._total_exposure_pct = 0.0

            return {
                "positions_closed": len(closed),
                "details": closed
            }

    # =========================================================================
    # EMERGENCY CONTROLS
    # =========================================================================

    def emergency_stop(self, reason: str = "Manual emergency stop") -> Dict[str, Any]:
        """
        Trigger emergency stop for all trading

        Args:
            reason: Reason for emergency stop

        Returns:
            Stop result
        """
        return self._trigger_emergency_stop(reason)

    def _trigger_emergency_stop(self, reason: str) -> Dict[str, Any]:
        """Internal method to trigger emergency stop"""
        with self._lock:
            if self._is_emergency_stopped:
                return {
                    "success": True,
                    "message": "Already in emergency stop",
                    "reason": self._emergency_stop_reason
                }

            self._is_emergency_stopped = True
            self._emergency_stop_time = datetime.now(timezone.utc)
            self._emergency_stop_reason = reason

            # Log event
            self._risk_events.append({
                "type": "emergency_stop",
                "reason": reason,
                "timestamp": self._emergency_stop_time.isoformat(),
                "drawdown_pct": self._get_current_drawdown(),
                "positions_open": self._total_positions
            })

            logger.critical(f"EMERGENCY STOP TRIGGERED: {reason}")

            return {
                "success": True,
                "message": "Emergency stop activated",
                "reason": reason,
                "timestamp": self._emergency_stop_time.isoformat()
            }

    def release_emergency_stop(self, start_recovery: bool = True) -> Dict[str, Any]:
        """
        Release emergency stop

        Args:
            start_recovery: Whether to start gradual recovery

        Returns:
            Release result
        """
        with self._lock:
            if not self._is_emergency_stopped:
                return {
                    "success": False,
                    "message": "No emergency stop active"
                }

            self._is_emergency_stopped = False
            stop_duration = None
            if self._emergency_stop_time:
                stop_duration = (datetime.now(timezone.utc) - self._emergency_stop_time).total_seconds() / 3600

            if start_recovery:
                self._in_recovery = True
                self._recovery_start_time = datetime.now(timezone.utc)
                self._recovery_step = 0

            # Log event
            self._risk_events.append({
                "type": "emergency_stop_released",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_hours": stop_duration,
                "recovery_started": start_recovery
            })

            logger.info(f"Emergency stop released after {stop_duration:.1f} hours")

            return {
                "success": True,
                "message": "Emergency stop released",
                "duration_hours": stop_duration,
                "recovery_mode": start_recovery
            }

    def is_emergency_stopped(self) -> bool:
        """Check if emergency stop is active"""
        return self._is_emergency_stopped

    # =========================================================================
    # RISK UTILIZATION
    # =========================================================================

    def get_risk_utilization(self) -> RiskUtilization:
        """Get current risk utilization snapshot"""
        with self._lock:
            return self._calculate_utilization()

    def _calculate_utilization(self) -> RiskUtilization:
        """Calculate current risk utilization"""
        drawdown = self._get_current_drawdown()
        daily_loss = self._get_daily_loss()

        warnings = []
        is_at_limit = False

        # Check exposure limit
        exposure_limit_pct = (self._total_exposure_pct / self.config.max_total_exposure_pct * 100) if self.config.max_total_exposure_pct > 0 else 0
        if exposure_limit_pct >= 90:
            warnings.append(f"Exposure at {exposure_limit_pct:.0f}% of limit")
            if exposure_limit_pct >= 100:
                is_at_limit = True

        # Check drawdown limit
        drawdown_limit_pct = (drawdown / self.config.max_total_drawdown_pct * 100) if self.config.max_total_drawdown_pct > 0 else 0
        if drawdown_limit_pct >= 75:
            warnings.append(f"Drawdown at {drawdown_limit_pct:.0f}% of limit")
            if drawdown_limit_pct >= 100:
                is_at_limit = True

        # Check position limit
        position_limit_pct = (self._total_positions / self.config.max_concurrent_positions * 100) if self.config.max_concurrent_positions > 0 else 0
        if position_limit_pct >= 80:
            warnings.append(f"Positions at {position_limit_pct:.0f}% of limit")
            if position_limit_pct >= 100:
                is_at_limit = True

        # Risk budget remaining
        risk_remaining = self.config.total_risk_budget_pct - self._total_risk_used

        return RiskUtilization(
            timestamp=datetime.now(timezone.utc),
            total_exposure_pct=self._total_exposure_pct,
            current_drawdown_pct=drawdown,
            daily_loss_pct=daily_loss,
            total_positions=self._total_positions,
            total_risk_used_pct=self._total_risk_used,
            risk_budget_remaining_pct=max(0, risk_remaining),
            strategy_exposures=dict(self._positions),
            strategy_risk_used=dict(self._strategy_risk_used),
            exposure_limit_pct=exposure_limit_pct,
            drawdown_limit_pct=drawdown_limit_pct,
            position_limit_pct=position_limit_pct,
            warnings=warnings,
            is_at_limit=is_at_limit
        )

    def _get_current_drawdown(self) -> float:
        """Get current portfolio drawdown percentage"""
        if self._peak_equity <= 0:
            return 0.0
        return max(0, (self._peak_equity - self._current_equity) / self._peak_equity * 100)

    def _get_daily_loss(self) -> float:
        """Get current daily loss percentage"""
        if self._today_starting_equity <= 0:
            return 0.0
        return max(0, (self._today_starting_equity - self._current_equity) / self._today_starting_equity * 100)

    # =========================================================================
    # CORRELATION MANAGEMENT
    # =========================================================================

    def update_correlations(self, correlations: Dict[str, Dict[str, float]]) -> None:
        """Update correlation matrix"""
        with self._lock:
            self._correlation_matrix = correlations

    def get_correlation_violations(self) -> List[Dict[str, Any]]:
        """Get strategies violating correlation limits"""
        with self._lock:
            violations = []

            # Check each pair of strategies with positions
            active_strategies = [s for s in self._positions if self._positions[s]]

            for i, s1 in enumerate(active_strategies):
                correlated_count = 0
                correlated_with = []

                for s2 in active_strategies[i+1:]:
                    if s1 in self._correlation_matrix and s2 in self._correlation_matrix.get(s1, {}):
                        corr = self._correlation_matrix[s1][s2]
                        if corr >= self.config.max_correlation:
                            correlated_count += 1
                            correlated_with.append((s2, corr))

                if correlated_count > 0:
                    violations.append({
                        "strategy": s1,
                        "correlated_count": correlated_count,
                        "correlated_with": correlated_with
                    })

            return violations

    # =========================================================================
    # STRATEGY STATE MANAGEMENT
    # =========================================================================

    def update_strategy_state(self, strategy_id: str, state: StrategyState) -> None:
        """Update strategy state for risk calculations"""
        with self._lock:
            self._strategy_states[strategy_id] = state
            self._strategy_drawdowns[strategy_id] = state.current_drawdown_pct
            self._strategy_daily_loss[strategy_id] = state.daily_loss_pct

    def get_strategy_risk_status(self, strategy_id: str) -> Dict[str, Any]:
        """Get risk status for a specific strategy"""
        with self._lock:
            positions = self._positions.get(strategy_id, {})
            exposure = sum(positions.values())

            return {
                "strategy_id": strategy_id,
                "positions": len(positions),
                "exposure_pct": exposure,
                "drawdown_pct": self._strategy_drawdowns.get(strategy_id, 0.0),
                "daily_loss_pct": self._strategy_daily_loss.get(strategy_id, 0.0),
                "risk_used_pct": self._strategy_risk_used.get(strategy_id, 0.0),
                "at_position_limit": len(positions) >= self.config.max_strategy_positions,
                "at_drawdown_limit": self._strategy_drawdowns.get(strategy_id, 0.0) >= self.config.max_strategy_drawdown_pct,
            }

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get overall coordinator status"""
        with self._lock:
            utilization = self._calculate_utilization()

            return {
                "total_capital": self._total_capital,
                "current_equity": self._current_equity,
                "peak_equity": self._peak_equity,
                "is_emergency_stopped": self._is_emergency_stopped,
                "emergency_stop_reason": self._emergency_stop_reason if self._is_emergency_stopped else None,
                "in_recovery": self._in_recovery,
                "recovery_factor": self._get_recovery_factor() if self._in_recovery else 1.0,
                "utilization": utilization.to_dict(),
                "config": self.config.to_dict(),
            }

    def get_risk_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent risk events"""
        with self._lock:
            return self._risk_events[-limit:]


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global risk coordinator instance
_risk_coordinator: Optional[RiskCoordinator] = None


def get_risk_coordinator(
    config: Optional[RiskCoordinatorConfig] = None
) -> RiskCoordinator:
    """Get or create global risk coordinator instance"""
    global _risk_coordinator
    if _risk_coordinator is None:
        _risk_coordinator = RiskCoordinator(config)
    return _risk_coordinator


def reset_risk_coordinator() -> None:
    """Reset global risk coordinator instance"""
    global _risk_coordinator
    _risk_coordinator = None
    logger.info("Risk coordinator instance reset")
