"""
Allocation Manager
==================
Purpose: Dynamic capital allocation across trading strategies

The Allocation Manager provides sophisticated capital allocation:
1. Multiple allocation methods (equal, risk parity, Kelly, performance-based)
2. Dynamic rebalancing based on performance and market conditions
3. Risk budget management per strategy
4. Correlation-aware allocation adjustments
5. Integration with DynamicBudgetManager for risk limits

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from threading import RLock
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import math
import statistics

from app.orchestration.models import (
    StrategyConfig,
    StrategyState,
    StrategyAllocation,
    AllocationSnapshot,
    StrategyPerformanceMetrics,
    AllocationMethod,
    RebalanceTrigger,
    StrategyStatus,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ALLOCATION CONFIGURATION
# =============================================================================

@dataclass
class AllocationConfig:
    """
    Configuration for the Allocation Manager

    Controls allocation behavior, limits, and rebalancing triggers.
    """
    # Total capital
    total_capital: float = 100000.0

    # Allocation method
    allocation_method: AllocationMethod = AllocationMethod.PERFORMANCE_BASED

    # Exposure limits
    max_total_exposure_pct: float = 80.0  # Max 80% of capital deployed
    cash_reserve_pct: float = 10.0  # Always keep 10% cash
    max_single_strategy_pct: float = 25.0  # Max 25% in any one strategy
    min_strategy_allocation_pct: float = 2.0  # Min 2% to activate strategy

    # Rebalancing settings
    rebalance_trigger: RebalanceTrigger = RebalanceTrigger.THRESHOLD
    rebalance_threshold_pct: float = 5.0  # Rebalance when drift > 5%
    rebalance_interval_hours: int = 24  # For periodic rebalancing
    min_rebalance_interval_hours: int = 1  # Don't rebalance more often

    # Performance-based allocation settings
    performance_lookback_days: int = 30  # Days to consider for performance
    performance_weight_sharpe: float = 0.4  # Weight for Sharpe ratio
    performance_weight_win_rate: float = 0.3  # Weight for win rate
    performance_weight_profit_factor: float = 0.3  # Weight for profit factor
    min_trades_for_performance: int = 20  # Min trades for performance calc

    # Risk parity settings
    target_volatility_pct: float = 15.0  # Target portfolio volatility
    vol_lookback_days: int = 30  # Days for volatility calculation

    # Kelly criterion settings
    kelly_fraction: float = 0.25  # Use 25% of full Kelly
    kelly_max_allocation: float = 30.0  # Cap Kelly at 30%

    # Decay settings for underperformers
    underperformer_decay_rate: float = 0.9  # Reduce allocation by 10% per period
    underperformer_threshold_sharpe: float = 0.0  # Sharpe below 0 = underperformer

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_capital": self.total_capital,
            "allocation_method": self.allocation_method.value,
            "max_total_exposure_pct": self.max_total_exposure_pct,
            "cash_reserve_pct": self.cash_reserve_pct,
            "rebalance_trigger": self.rebalance_trigger.value,
            "rebalance_threshold_pct": self.rebalance_threshold_pct,
        }


# =============================================================================
# ALLOCATION MANAGER
# =============================================================================

class AllocationManager:
    """
    Dynamic Capital Allocation Manager

    Responsible for allocating capital across multiple trading strategies
    using various allocation methods:

    1. Equal Allocation:
       - Divides capital equally among active strategies
       - Simple but ignores risk and performance differences

    2. Risk Parity:
       - Allocates inversely proportional to volatility
       - Higher volatility strategies get smaller allocations
       - Goal: Equal risk contribution from each strategy

    3. Performance-Based:
       - Allocates more to better performing strategies
       - Uses Sharpe ratio, win rate, and profit factor
       - Dynamic adjustment based on rolling performance

    4. Kelly Criterion:
       - Mathematically optimal allocation based on edge
       - Uses fractional Kelly (25%) for safety
       - Requires win rate and payoff ratio data

    5. Dynamic:
       - Combines multiple methods
       - Adjusts based on market conditions
       - Most sophisticated but complex

    Features:
    - Automatic rebalancing on threshold drift
    - Correlation-aware allocation adjustments
    - Risk budget tracking per strategy
    - Integration with DynamicBudgetManager
    - Real-time allocation updates

    Usage:
        config = AllocationConfig(
            total_capital=100000,
            allocation_method=AllocationMethod.PERFORMANCE_BASED
        )
        manager = AllocationManager(config)

        # Add strategies
        manager.add_strategy("trend_following", target_pct=15.0)
        manager.add_strategy("mean_reversion", target_pct=15.0)

        # Update with performance data
        manager.update_performance("trend_following", sharpe=1.5, win_rate=0.55)

        # Calculate allocations
        allocations = manager.calculate_allocations()

        # Check if rebalancing needed
        if manager.needs_rebalancing():
            actions = manager.calculate_rebalance_actions()
    """

    def __init__(self, config: Optional[AllocationConfig] = None):
        """
        Initialize Allocation Manager

        Args:
            config: Allocation configuration
        """
        self.config = config or AllocationConfig()
        self._lock = RLock()

        # Strategy data storage
        self._strategy_configs: Dict[str, StrategyConfig] = {}
        self._strategy_states: Dict[str, StrategyState] = {}
        self._allocations: Dict[str, StrategyAllocation] = {}
        self._performance: Dict[str, StrategyPerformanceMetrics] = {}

        # Volatility data for risk parity
        self._strategy_volatility: Dict[str, float] = {}

        # Correlation matrix between strategies
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}

        # Historical allocations for tracking
        self._allocation_history: List[AllocationSnapshot] = []

        # Rebalancing tracking
        self._last_rebalance: Optional[datetime] = None
        self._rebalance_count: int = 0

        # Total deployed capital tracking
        self._total_deployed: float = 0.0

        logger.info(
            f"AllocationManager initialized: "
            f"capital=${self.config.total_capital:,.0f}, "
            f"method={self.config.allocation_method.value}"
        )

    # =========================================================================
    # STRATEGY MANAGEMENT
    # =========================================================================

    def add_strategy(
        self,
        strategy_id: str,
        config: Optional[StrategyConfig] = None,
        target_pct: Optional[float] = None,
        min_pct: Optional[float] = None,
        max_pct: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Add a strategy to allocation management

        Args:
            strategy_id: Unique strategy identifier
            config: Strategy configuration
            target_pct: Target allocation percentage
            min_pct: Minimum allocation percentage
            max_pct: Maximum allocation percentage

        Returns:
            Result dictionary
        """
        with self._lock:
            # Create or update allocation
            allocation = StrategyAllocation(
                strategy_id=strategy_id,
                target_pct=target_pct or (config.target_allocation_pct if config else 10.0),
                min_pct=min_pct or (config.min_allocation_pct if config else 0.0),
                max_pct=max_pct or (config.max_allocation_pct if config else self.config.max_single_strategy_pct),
                allocated_capital=0.0,
                available_capital=0.0
            )

            self._allocations[strategy_id] = allocation

            if config:
                self._strategy_configs[strategy_id] = config

            # Initialize state if not exists
            if strategy_id not in self._strategy_states:
                self._strategy_states[strategy_id] = StrategyState(
                    strategy_id=strategy_id,
                    status=StrategyStatus.WARMING_UP
                )

            # Initialize volatility estimate
            self._strategy_volatility[strategy_id] = 0.20  # 20% default

            logger.info(f"Added strategy to allocation: {strategy_id}, target={allocation.target_pct}%")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "target_pct": allocation.target_pct
            }

    def remove_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Remove a strategy from allocation management

        Args:
            strategy_id: Strategy to remove

        Returns:
            Result dictionary
        """
        with self._lock:
            if strategy_id not in self._allocations:
                return {"success": False, "error": "Strategy not found"}

            # Get current allocation for reallocation
            removed_allocation = self._allocations[strategy_id]

            # Remove from all tracking
            del self._allocations[strategy_id]
            self._strategy_configs.pop(strategy_id, None)
            self._strategy_states.pop(strategy_id, None)
            self._performance.pop(strategy_id, None)
            self._strategy_volatility.pop(strategy_id, None)

            # Remove from correlation matrix
            self._correlation_matrix.pop(strategy_id, None)
            for other_id in self._correlation_matrix:
                self._correlation_matrix[other_id].pop(strategy_id, None)

            logger.info(f"Removed strategy from allocation: {strategy_id}")

            return {
                "success": True,
                "strategy_id": strategy_id,
                "freed_allocation_pct": removed_allocation.current_pct
            }

    def update_strategy_state(self, strategy_id: str, state: StrategyState) -> None:
        """Update strategy state for allocation decisions"""
        with self._lock:
            self._strategy_states[strategy_id] = state

    def update_performance(
        self,
        strategy_id: str,
        metrics: Optional[StrategyPerformanceMetrics] = None,
        sharpe: Optional[float] = None,
        win_rate: Optional[float] = None,
        profit_factor: Optional[float] = None,
        volatility: Optional[float] = None
    ) -> None:
        """
        Update strategy performance metrics

        Args:
            strategy_id: Strategy identifier
            metrics: Full performance metrics object
            sharpe: Sharpe ratio (alternative to full metrics)
            win_rate: Win rate (alternative to full metrics)
            profit_factor: Profit factor (alternative to full metrics)
            volatility: Strategy volatility for risk parity
        """
        with self._lock:
            if metrics:
                self._performance[strategy_id] = metrics
            elif strategy_id in self._performance:
                # Update individual fields
                if sharpe is not None:
                    self._performance[strategy_id].sharpe_ratio = sharpe
                if win_rate is not None:
                    self._performance[strategy_id].win_rate = win_rate
                if profit_factor is not None:
                    self._performance[strategy_id].profit_factor = profit_factor
            else:
                # Create minimal metrics
                self._performance[strategy_id] = StrategyPerformanceMetrics(
                    strategy_id=strategy_id,
                    period_start=datetime.now(timezone.utc) - timedelta(days=30),
                    period_end=datetime.now(timezone.utc),
                    sharpe_ratio=sharpe or 0.0,
                    win_rate=win_rate or 0.5,
                    profit_factor=profit_factor or 1.0
                )

            # Update volatility if provided
            if volatility is not None:
                self._strategy_volatility[strategy_id] = volatility

    def update_correlation(
        self,
        strategy_1: str,
        strategy_2: str,
        correlation: float
    ) -> None:
        """
        Update correlation between two strategies

        Args:
            strategy_1: First strategy ID
            strategy_2: Second strategy ID
            correlation: Correlation coefficient (-1 to 1)
        """
        with self._lock:
            if strategy_1 not in self._correlation_matrix:
                self._correlation_matrix[strategy_1] = {}
            if strategy_2 not in self._correlation_matrix:
                self._correlation_matrix[strategy_2] = {}

            self._correlation_matrix[strategy_1][strategy_2] = correlation
            self._correlation_matrix[strategy_2][strategy_1] = correlation

    # =========================================================================
    # ALLOCATION CALCULATION
    # =========================================================================

    def calculate_allocations(self) -> Dict[str, StrategyAllocation]:
        """
        Calculate allocations for all strategies

        Uses the configured allocation method to determine
        optimal capital distribution.

        Returns:
            Dictionary of strategy allocations
        """
        with self._lock:
            method = self.config.allocation_method

            if method == AllocationMethod.EQUAL:
                return self._calculate_equal_allocations()
            elif method == AllocationMethod.RISK_PARITY:
                return self._calculate_risk_parity_allocations()
            elif method == AllocationMethod.PERFORMANCE_BASED:
                return self._calculate_performance_allocations()
            elif method == AllocationMethod.KELLY:
                return self._calculate_kelly_allocations()
            elif method == AllocationMethod.FIXED:
                return self._calculate_fixed_allocations()
            elif method == AllocationMethod.DYNAMIC:
                return self._calculate_dynamic_allocations()
            else:
                return self._calculate_equal_allocations()

    def _calculate_equal_allocations(self) -> Dict[str, StrategyAllocation]:
        """Calculate equal allocations across active strategies"""
        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return {}

        # Available capital after reserves
        available_pct = self.config.max_total_exposure_pct - self.config.cash_reserve_pct
        per_strategy_pct = available_pct / len(active_strategies)

        # Cap at max single strategy
        per_strategy_pct = min(per_strategy_pct, self.config.max_single_strategy_pct)

        for strategy_id in active_strategies:
            allocation = self._allocations[strategy_id]
            allocation.target_pct = per_strategy_pct
            allocation.allocated_capital = self.config.total_capital * (per_strategy_pct / 100)
            allocation.risk_budget_pct = per_strategy_pct * 0.2  # 20% of allocation as risk budget

        return dict(self._allocations)

    def _calculate_risk_parity_allocations(self) -> Dict[str, StrategyAllocation]:
        """
        Calculate risk parity allocations

        Allocates inversely proportional to volatility so each
        strategy contributes equal risk to the portfolio.
        """
        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return {}

        # Get volatilities
        volatilities = {
            sid: self._strategy_volatility.get(sid, 0.20)
            for sid in active_strategies
        }

        # Calculate inverse volatility weights
        inv_vols = {sid: 1.0 / max(vol, 0.01) for sid, vol in volatilities.items()}
        total_inv_vol = sum(inv_vols.values())

        # Available capital
        available_pct = self.config.max_total_exposure_pct - self.config.cash_reserve_pct

        for strategy_id in active_strategies:
            # Weight by inverse volatility
            weight = inv_vols[strategy_id] / total_inv_vol if total_inv_vol > 0 else 0
            target_pct = available_pct * weight

            # Apply limits
            target_pct = max(
                self.config.min_strategy_allocation_pct,
                min(target_pct, self.config.max_single_strategy_pct)
            )

            allocation = self._allocations[strategy_id]
            allocation.target_pct = target_pct
            allocation.allocated_capital = self.config.total_capital * (target_pct / 100)
            allocation.risk_budget_pct = target_pct * 0.2

        return dict(self._allocations)

    def _calculate_performance_allocations(self) -> Dict[str, StrategyAllocation]:
        """
        Calculate performance-based allocations

        Allocates more capital to strategies with better
        risk-adjusted returns and higher win rates.
        """
        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return {}

        # Calculate performance scores
        scores = {}
        for strategy_id in active_strategies:
            perf = self._performance.get(strategy_id)
            if perf and perf.total_trades >= self.config.min_trades_for_performance:
                score = self._calculate_performance_score(perf)
            else:
                score = 0.5  # Neutral score for strategies without enough data

            scores[strategy_id] = max(0.1, score)  # Floor at 0.1

        # Normalize scores
        total_score = sum(scores.values())

        # Available capital
        available_pct = self.config.max_total_exposure_pct - self.config.cash_reserve_pct

        for strategy_id in active_strategies:
            # Weight by performance score
            weight = scores[strategy_id] / total_score if total_score > 0 else 0
            target_pct = available_pct * weight

            # Apply limits
            target_pct = max(
                self.config.min_strategy_allocation_pct,
                min(target_pct, self.config.max_single_strategy_pct)
            )

            allocation = self._allocations[strategy_id]
            allocation.target_pct = target_pct
            allocation.allocated_capital = self.config.total_capital * (target_pct / 100)
            allocation.risk_budget_pct = target_pct * 0.2

        return dict(self._allocations)

    def _calculate_kelly_allocations(self) -> Dict[str, StrategyAllocation]:
        """
        Calculate Kelly criterion allocations

        Uses fractional Kelly to determine optimal bet size
        based on win rate and payoff ratio.
        """
        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return {}

        kelly_fractions = {}
        for strategy_id in active_strategies:
            perf = self._performance.get(strategy_id)
            if perf and perf.total_trades >= self.config.min_trades_for_performance:
                kelly = self._calculate_kelly_fraction(perf)
            else:
                kelly = 0.05  # Conservative default

            # Apply fractional Kelly and cap
            kelly = kelly * self.config.kelly_fraction
            kelly = min(kelly, self.config.kelly_max_allocation / 100)
            kelly = max(kelly, self.config.min_strategy_allocation_pct / 100)

            kelly_fractions[strategy_id] = kelly

        # Scale to fit within available capital
        total_kelly = sum(kelly_fractions.values())
        available_pct = self.config.max_total_exposure_pct - self.config.cash_reserve_pct
        scale = (available_pct / 100) / total_kelly if total_kelly > 0 else 1.0
        scale = min(scale, 1.0)  # Don't scale up

        for strategy_id in active_strategies:
            target_pct = kelly_fractions[strategy_id] * scale * 100

            # Apply limits
            target_pct = max(
                self.config.min_strategy_allocation_pct,
                min(target_pct, self.config.max_single_strategy_pct)
            )

            allocation = self._allocations[strategy_id]
            allocation.target_pct = target_pct
            allocation.allocated_capital = self.config.total_capital * (target_pct / 100)
            allocation.risk_budget_pct = target_pct * 0.2

        return dict(self._allocations)

    def _calculate_fixed_allocations(self) -> Dict[str, StrategyAllocation]:
        """Calculate fixed allocations based on target percentages"""
        for strategy_id, allocation in self._allocations.items():
            # Use pre-set target_pct
            allocation.allocated_capital = self.config.total_capital * (allocation.target_pct / 100)
            allocation.risk_budget_pct = allocation.target_pct * 0.2

        return dict(self._allocations)

    def _calculate_dynamic_allocations(self) -> Dict[str, StrategyAllocation]:
        """
        Calculate dynamic allocations combining multiple methods

        Combines:
        - 40% performance-based
        - 30% risk parity
        - 30% Kelly criterion
        """
        active_strategies = self._get_active_strategies()
        if not active_strategies:
            return {}

        # Calculate each method's allocation
        perf_allocations = self._calculate_performance_allocations()
        risk_parity_allocations = self._calculate_risk_parity_allocations()
        kelly_allocations = self._calculate_kelly_allocations()

        # Combine with weights
        for strategy_id in active_strategies:
            perf_target = perf_allocations.get(strategy_id, StrategyAllocation(strategy_id=strategy_id)).target_pct
            rp_target = risk_parity_allocations.get(strategy_id, StrategyAllocation(strategy_id=strategy_id)).target_pct
            kelly_target = kelly_allocations.get(strategy_id, StrategyAllocation(strategy_id=strategy_id)).target_pct

            # Weighted combination
            target_pct = (
                perf_target * 0.4 +
                rp_target * 0.3 +
                kelly_target * 0.3
            )

            # Apply limits
            target_pct = max(
                self.config.min_strategy_allocation_pct,
                min(target_pct, self.config.max_single_strategy_pct)
            )

            allocation = self._allocations[strategy_id]
            allocation.target_pct = target_pct
            allocation.allocated_capital = self.config.total_capital * (target_pct / 100)
            allocation.risk_budget_pct = target_pct * 0.2

        return dict(self._allocations)

    def _calculate_performance_score(self, metrics: StrategyPerformanceMetrics) -> float:
        """
        Calculate composite performance score

        Score is 0-1 based on:
        - Sharpe ratio (normalized)
        - Win rate
        - Profit factor (normalized)
        """
        # Normalize Sharpe (0-3 range -> 0-1)
        sharpe_score = min(1.0, max(0.0, (metrics.sharpe_ratio + 1) / 4))

        # Win rate is already 0-1
        win_rate_score = metrics.win_rate

        # Normalize profit factor (1-3 range -> 0-1)
        pf_score = min(1.0, max(0.0, (metrics.profit_factor - 0.5) / 2.5))

        # Weighted average
        score = (
            sharpe_score * self.config.performance_weight_sharpe +
            win_rate_score * self.config.performance_weight_win_rate +
            pf_score * self.config.performance_weight_profit_factor
        )

        return score

    def _calculate_kelly_fraction(self, metrics: StrategyPerformanceMetrics) -> float:
        """
        Calculate Kelly fraction for a strategy

        f* = (bp - q) / b
        where:
            b = odds (avg_win / avg_loss)
            p = probability of winning
            q = probability of losing (1 - p)
        """
        win_rate = metrics.win_rate
        if win_rate <= 0 or win_rate >= 1:
            return 0.0

        avg_win = abs(metrics.avg_win)
        avg_loss = abs(metrics.avg_loss)

        if avg_loss <= 0:
            return 0.0

        # Calculate odds
        b = avg_win / avg_loss
        p = win_rate
        q = 1 - p

        # Kelly formula
        kelly = (b * p - q) / b if b > 0 else 0.0

        # Kelly can be negative if no edge
        return max(0.0, kelly)

    def _get_active_strategies(self) -> List[str]:
        """Get list of active strategy IDs"""
        active = []
        for strategy_id, state in self._strategy_states.items():
            if state.status == StrategyStatus.ACTIVE:
                active.append(strategy_id)
        return active

    # =========================================================================
    # REBALANCING
    # =========================================================================

    def needs_rebalancing(self) -> bool:
        """
        Check if portfolio needs rebalancing

        Returns:
            True if rebalancing is needed
        """
        with self._lock:
            trigger = self.config.rebalance_trigger

            if trigger == RebalanceTrigger.MANUAL:
                return False

            if trigger == RebalanceTrigger.THRESHOLD:
                return self._check_threshold_rebalance()

            if trigger == RebalanceTrigger.PERIODIC:
                return self._check_periodic_rebalance()

            if trigger == RebalanceTrigger.PERFORMANCE:
                return self._check_performance_rebalance()

            if trigger == RebalanceTrigger.VOLATILITY:
                return self._check_volatility_rebalance()

            return False

    def _check_threshold_rebalance(self) -> bool:
        """Check if drift exceeds threshold"""
        for strategy_id, allocation in self._allocations.items():
            drift = abs(allocation.current_pct - allocation.target_pct)
            if drift > self.config.rebalance_threshold_pct:
                return True
        return False

    def _check_periodic_rebalance(self) -> bool:
        """Check if enough time has passed since last rebalance"""
        if self._last_rebalance is None:
            return True

        elapsed = datetime.now(timezone.utc) - self._last_rebalance
        return elapsed > timedelta(hours=self.config.rebalance_interval_hours)

    def _check_performance_rebalance(self) -> bool:
        """Check if significant performance changes warrant rebalancing"""
        # Recalculate allocations
        new_allocations = self.calculate_allocations()

        # Check for significant changes
        for strategy_id, new_alloc in new_allocations.items():
            if strategy_id in self._allocations:
                old_alloc = self._allocations[strategy_id]
                change = abs(new_alloc.target_pct - old_alloc.target_pct)
                if change > self.config.rebalance_threshold_pct:
                    return True

        return False

    def _check_volatility_rebalance(self) -> bool:
        """Check if volatility regime change requires rebalancing"""
        # Calculate current portfolio volatility
        portfolio_vol = self._calculate_portfolio_volatility()

        # Check if significantly different from target
        target_vol = self.config.target_volatility_pct
        if abs(portfolio_vol - target_vol) / target_vol > 0.2:  # 20% deviation
            return True

        return False

    def calculate_rebalance_actions(self) -> List[Dict[str, Any]]:
        """
        Calculate rebalancing actions needed

        Returns:
            List of actions to take for rebalancing
        """
        with self._lock:
            # First, recalculate optimal allocations
            self.calculate_allocations()

            actions = []

            for strategy_id, allocation in self._allocations.items():
                diff = allocation.target_pct - allocation.current_pct

                if abs(diff) > 0.5:  # Only include meaningful changes
                    action_type = "increase" if diff > 0 else "decrease"
                    amount = abs(diff / 100 * self.config.total_capital)

                    actions.append({
                        "strategy_id": strategy_id,
                        "action": action_type,
                        "current_pct": allocation.current_pct,
                        "target_pct": allocation.target_pct,
                        "diff_pct": diff,
                        "amount_usd": amount
                    })

            # Sort by absolute difference (largest changes first)
            actions.sort(key=lambda x: abs(x["diff_pct"]), reverse=True)

            return actions

    def execute_rebalance(self) -> Dict[str, Any]:
        """
        Execute rebalancing (update allocations)

        Returns:
            Rebalancing result
        """
        with self._lock:
            # Check minimum interval
            if self._last_rebalance is not None:
                elapsed = datetime.now(timezone.utc) - self._last_rebalance
                if elapsed < timedelta(hours=self.config.min_rebalance_interval_hours):
                    return {
                        "success": False,
                        "error": "Minimum rebalance interval not met",
                        "next_allowed": (
                            self._last_rebalance +
                            timedelta(hours=self.config.min_rebalance_interval_hours)
                        ).isoformat()
                    }

            # Get actions
            actions = self.calculate_rebalance_actions()

            # Update current allocations to match targets
            for strategy_id, allocation in self._allocations.items():
                allocation.current_pct = allocation.target_pct
                allocation.available_capital = (
                    allocation.allocated_capital - allocation.used_capital
                )
                allocation.needs_rebalancing = False
                allocation.rebalance_amount = 0.0
                allocation.last_rebalanced = datetime.now(timezone.utc)

            # Update tracking
            self._last_rebalance = datetime.now(timezone.utc)
            self._rebalance_count += 1

            # Create snapshot
            snapshot = self._create_snapshot()
            self._allocation_history.append(snapshot)

            logger.info(
                f"Executed rebalance #{self._rebalance_count}: "
                f"{len(actions)} adjustments"
            )

            return {
                "success": True,
                "rebalance_number": self._rebalance_count,
                "actions": actions,
                "timestamp": self._last_rebalance.isoformat()
            }

    # =========================================================================
    # CAPITAL TRACKING
    # =========================================================================

    def update_used_capital(
        self,
        strategy_id: str,
        used_capital: float
    ) -> None:
        """
        Update capital currently in use by a strategy

        Args:
            strategy_id: Strategy identifier
            used_capital: Capital currently deployed
        """
        with self._lock:
            if strategy_id in self._allocations:
                allocation = self._allocations[strategy_id]
                allocation.used_capital = used_capital
                allocation.available_capital = allocation.allocated_capital - used_capital

                # Update current percentage
                if self.config.total_capital > 0:
                    allocation.current_pct = (used_capital / self.config.total_capital) * 100

                # Check if drifted from target
                drift = abs(allocation.current_pct - allocation.target_pct)
                allocation.needs_rebalancing = drift > self.config.rebalance_threshold_pct
                allocation.rebalance_amount = (allocation.target_pct - allocation.current_pct) / 100 * self.config.total_capital

                allocation.last_updated = datetime.now(timezone.utc)

    def update_risk_budget_used(
        self,
        strategy_id: str,
        risk_used_pct: float
    ) -> None:
        """
        Update risk budget usage for a strategy

        Args:
            strategy_id: Strategy identifier
            risk_used_pct: Risk budget used as percentage
        """
        with self._lock:
            if strategy_id in self._allocations:
                self._allocations[strategy_id].risk_budget_used_pct = risk_used_pct

    def get_available_capital(self, strategy_id: str) -> float:
        """Get available capital for a strategy"""
        with self._lock:
            if strategy_id in self._allocations:
                return self._allocations[strategy_id].available_capital
            return 0.0

    def get_allocation(self, strategy_id: str) -> Optional[StrategyAllocation]:
        """Get allocation for a strategy"""
        with self._lock:
            return self._allocations.get(strategy_id)

    def get_all_allocations(self) -> Dict[str, StrategyAllocation]:
        """Get all allocations"""
        with self._lock:
            return dict(self._allocations)

    # =========================================================================
    # PORTFOLIO METRICS
    # =========================================================================

    def _calculate_portfolio_volatility(self) -> float:
        """
        Calculate portfolio volatility considering correlations

        Uses: sqrt(sum(wi * wj * sigma_i * sigma_j * corr_ij))
        """
        active_strategies = self._get_active_strategies()
        if len(active_strategies) < 2:
            if active_strategies:
                return self._strategy_volatility.get(active_strategies[0], 0.20)
            return 0.0

        # Get weights (current allocations)
        weights = {}
        total_allocated = sum(
            self._allocations[s].current_pct
            for s in active_strategies
        )

        for strategy_id in active_strategies:
            weights[strategy_id] = (
                self._allocations[strategy_id].current_pct / total_allocated
                if total_allocated > 0 else 0
            )

        # Calculate portfolio variance
        variance = 0.0
        for i, s1 in enumerate(active_strategies):
            for j, s2 in enumerate(active_strategies):
                w1 = weights[s1]
                w2 = weights[s2]
                vol1 = self._strategy_volatility.get(s1, 0.20)
                vol2 = self._strategy_volatility.get(s2, 0.20)

                if s1 == s2:
                    corr = 1.0
                else:
                    corr = self._correlation_matrix.get(s1, {}).get(s2, 0.5)

                variance += w1 * w2 * vol1 * vol2 * corr

        return math.sqrt(max(0, variance)) * 100  # Convert to percentage

    def _create_snapshot(self) -> AllocationSnapshot:
        """Create allocation snapshot for history"""
        total_allocated = sum(a.current_pct for a in self._allocations.values())
        total_used = sum(a.used_capital for a in self._allocations.values())

        return AllocationSnapshot(
            timestamp=datetime.now(timezone.utc),
            total_capital=self.config.total_capital,
            allocations=dict(self._allocations),
            total_allocated_pct=total_allocated,
            total_used_pct=(total_used / self.config.total_capital * 100) if self.config.total_capital > 0 else 0,
            cash_reserve_pct=100 - total_allocated
        )

    def get_snapshot(self) -> AllocationSnapshot:
        """Get current allocation snapshot"""
        with self._lock:
            return self._create_snapshot()

    def get_allocation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get allocation history"""
        with self._lock:
            history = self._allocation_history[-limit:]
            return [s.to_dict() for s in history]

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def get_state(self) -> Dict[str, Any]:
        """Get complete manager state for persistence"""
        with self._lock:
            return {
                "config": self.config.to_dict(),
                "allocations": {
                    sid: {
                        "target_pct": a.target_pct,
                        "current_pct": a.current_pct,
                        "min_pct": a.min_pct,
                        "max_pct": a.max_pct,
                        "allocated_capital": a.allocated_capital,
                        "used_capital": a.used_capital
                    }
                    for sid, a in self._allocations.items()
                },
                "volatility": dict(self._strategy_volatility),
                "last_rebalance": self._last_rebalance.isoformat() if self._last_rebalance else None,
                "rebalance_count": self._rebalance_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load manager state from persistence"""
        with self._lock:
            if "allocations" in state:
                for sid, alloc_data in state["allocations"].items():
                    if sid in self._allocations:
                        for key, value in alloc_data.items():
                            setattr(self._allocations[sid], key, value)

            if "volatility" in state:
                self._strategy_volatility.update(state["volatility"])

            if "last_rebalance" in state and state["last_rebalance"]:
                self._last_rebalance = datetime.fromisoformat(state["last_rebalance"])

            if "rebalance_count" in state:
                self._rebalance_count = state["rebalance_count"]

            logger.info("Loaded allocation manager state")

    def get_status(self) -> Dict[str, Any]:
        """Get manager status summary"""
        with self._lock:
            snapshot = self._create_snapshot()

            return {
                "total_capital": self.config.total_capital,
                "total_allocated_pct": snapshot.total_allocated_pct,
                "total_used_pct": snapshot.total_used_pct,
                "cash_reserve_pct": snapshot.cash_reserve_pct,
                "allocation_method": self.config.allocation_method.value,
                "active_strategies": len(self._get_active_strategies()),
                "total_strategies": len(self._allocations),
                "needs_rebalancing": self.needs_rebalancing(),
                "last_rebalance": self._last_rebalance.isoformat() if self._last_rebalance else None,
                "rebalance_count": self._rebalance_count,
                "portfolio_volatility": self._calculate_portfolio_volatility()
            }


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global allocation manager instance
_allocation_manager: Optional[AllocationManager] = None


def get_allocation_manager(
    config: Optional[AllocationConfig] = None
) -> AllocationManager:
    """Get or create global allocation manager instance"""
    global _allocation_manager
    if _allocation_manager is None:
        _allocation_manager = AllocationManager(config)
    return _allocation_manager


def reset_allocation_manager() -> None:
    """Reset global allocation manager instance"""
    global _allocation_manager
    _allocation_manager = None
    logger.info("Allocation manager instance reset")
