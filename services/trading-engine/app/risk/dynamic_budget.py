"""
Dynamic Risk Budgeting Module
Purpose: Real-time risk budget allocation with multi-factor adjustments

Features:
- Per-strategy risk budget allocation
- Per-asset risk limits
- Volatility-based adjustments (VIX-style)
- Correlation-based adjustments
- Performance-based adjustments
- Kelly criterion integration
- Budget enforcement and validation
- Automatic rebalancing
- Alert generation

Multi-Factor Budget Calculation:
    effective_budget = base_budget × vol_multiplier × corr_multiplier × perf_multiplier × kelly_multiplier

Adjustment Factors:
- Volatility: Reduce budget when volatility is high (>80th percentile)
- Correlation: Reduce budget when portfolio correlation is high (>0.7)
- Performance: Increase/decrease based on strategy Sharpe ratio
- Kelly: Cap budget at Kelly-recommended optimal size

Phase 3.3 - Dynamic Risk Budgeting
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Tuple, Any
from enum import Enum
import json
import asyncio
from threading import RLock

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class BudgetConfig:
    """
    Configuration for Dynamic Risk Budgeting

    Attributes:
        total_capital: Total trading capital in USD
        max_total_risk_pct: Maximum total portfolio risk as % of capital
        max_strategy_risk_pct: Maximum risk per strategy as % of capital
        max_asset_risk_pct: Maximum risk per asset as % of capital
        volatility_adjustment_enabled: Enable volatility-based adjustments
        correlation_adjustment_enabled: Enable correlation-based adjustments
        performance_adjustment_enabled: Enable performance-based adjustments
        kelly_integration_enabled: Enable Kelly criterion integration
        rebalance_threshold_pct: Trigger rebalance when drift exceeds this %
        alert_threshold_pct: Generate warning when budget usage exceeds this %
        auto_rebalance: Automatically rebalance on position changes
        min_trades_for_performance: Minimum trades required for performance adjustment
    """
    total_capital: float = 100000.0
    max_total_risk_pct: float = 10.0  # Max 10% of capital at risk
    max_strategy_risk_pct: float = 5.0  # Max 5% per strategy
    max_asset_risk_pct: float = 3.0  # Max 3% per asset
    volatility_adjustment_enabled: bool = True
    correlation_adjustment_enabled: bool = True
    performance_adjustment_enabled: bool = True
    kelly_integration_enabled: bool = True
    rebalance_threshold_pct: float = 1.0  # Rebalance when 1% drift
    alert_threshold_pct: float = 80.0  # Alert at 80% budget usage
    auto_rebalance: bool = False
    min_trades_for_performance: int = 10

    def __post_init__(self):
        """Validate configuration values"""
        # Validate percentages
        if not (0 < self.max_total_risk_pct <= 100):
            raise ValueError(f"max_total_risk_pct must be between 0 and 100, got {self.max_total_risk_pct}")
        if not (0 < self.max_strategy_risk_pct <= 100):
            raise ValueError(f"max_strategy_risk_pct must be between 0 and 100, got {self.max_strategy_risk_pct}")
        if not (0 < self.max_asset_risk_pct <= 100):
            raise ValueError(f"max_asset_risk_pct must be between 0 and 100, got {self.max_asset_risk_pct}")

        # Validate capital
        if self.total_capital <= 0:
            raise ValueError(f"total_capital must be positive, got {self.total_capital}")

        logger.info(f"BudgetConfig initialized: {self.total_capital} capital, {self.max_total_risk_pct}% max risk")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return asdict(self)


@dataclass
class BudgetAlert:
    """Budget alert notification"""
    severity: AlertSeverity
    message: str
    timestamp: datetime
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DynamicBudgetManager:
    """
    Dynamic Risk Budget Management System

    Manages risk budget allocation across strategies and assets with
    multi-factor dynamic adjustments.

    Usage:
        config = BudgetConfig(total_capital=100000, max_total_risk_pct=10)
        manager = DynamicBudgetManager(config=config)

        # Allocate strategy budgets
        manager.allocate_strategy_budget("pairs_trading", 50.0)
        manager.allocate_strategy_budget("mean_reversion", 50.0)

        # Update market data
        manager.update_volatility(volatility_data)
        manager.update_correlations(correlation_data)
        manager.update_attribution(performance_data)
        manager.update_kelly_data(kelly_data)

        # Check if order can be placed
        can_place, reason = manager.can_place_order(
            strategy_name="pairs_trading",
            symbol="BTCUSDT",
            order_risk_amount=500.0
        )
    """

    def __init__(self, config: Optional[BudgetConfig] = None):
        """
        Initialize budget manager

        Args:
            config: Budget configuration (uses defaults if None)
        """
        self.config = config or BudgetConfig()
        self._lock = RLock()  # Thread safety for concurrent access

        # Budget allocations
        self._strategy_allocations: Dict[str, Dict[str, float]] = {}
        self._asset_limits: Dict[str, Dict[str, float]] = {}

        # Current positions and usage
        self._current_positions: List[Dict[str, Any]] = []
        self._strategy_usage: Dict[str, float] = {}
        self._asset_usage: Dict[str, float] = {}

        # Market data for adjustments
        self._volatility_data: Dict[str, Dict[str, float]] = {}
        self._correlation_data: Dict[str, Any] = {}
        self._attribution_data: Dict[str, Any] = {}
        self._kelly_data: Dict[str, Dict[str, float]] = {}

        # State tracking
        self._last_rebalance: Optional[datetime] = None
        self._alerts: List[BudgetAlert] = []

        logger.info(f"DynamicBudgetManager initialized with {self.config.total_capital} capital")

    def get_budget_state(self) -> Dict[str, Any]:
        """Get current overall budget state"""
        with self._lock:
            total_budget = self.config.total_capital * (self.config.max_total_risk_pct / 100.0)
            used_budget = sum(self._strategy_usage.values())

            return {
                "total_budget": total_budget,
                "used_budget": used_budget,
                "available_budget": max(0, total_budget - used_budget),
                "utilization_pct": (used_budget / total_budget * 100.0) if total_budget > 0 else 0.0,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def allocate_strategy_budget(
        self,
        strategy_name: str,
        allocation_pct: float
    ) -> Dict[str, Any]:
        """
        Allocate budget to a strategy

        Args:
            strategy_name: Name of the strategy
            allocation_pct: Percentage of total risk budget to allocate (0-100)

        Returns:
            Dict with allocation result
        """
        with self._lock:
            # Calculate total budget
            total_budget = self.config.total_capital * (self.config.max_total_risk_pct / 100.0)

            # Check if total allocation would exceed 100%
            current_total = sum(
                alloc["allocation_pct"]
                for name, alloc in self._strategy_allocations.items()
                if name != strategy_name
            )

            if current_total + allocation_pct > 100.0:
                return {
                    "success": False,
                    "error": f"Total allocation would exceed 100% (current: {current_total}%, trying to add: {allocation_pct}%)"
                }

            # Calculate allocated amount
            allocated_budget = total_budget * (allocation_pct / 100.0)

            # Apply strategy limit
            strategy_limit = self.config.total_capital * (self.config.max_strategy_risk_pct / 100.0)
            effective_budget = min(allocated_budget, strategy_limit)

            # Store allocation
            self._strategy_allocations[strategy_name] = {
                "allocation_pct": allocation_pct,
                "allocated_budget": effective_budget,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Allocated {allocation_pct}% (${effective_budget:.2f}) to {strategy_name}")

            return {
                "success": True,
                "strategy": strategy_name,
                "allocation_pct": allocation_pct,
                "allocated_budget": effective_budget,
                "effective_budget": effective_budget,
            }

    def get_strategy_allocations(self) -> Dict[str, Dict[str, Any]]:
        """Get all strategy allocations"""
        with self._lock:
            return dict(self._strategy_allocations)

    def set_asset_limit(
        self,
        symbol: str,
        max_risk_pct: float
    ) -> Dict[str, Any]:
        """
        Set asset-specific risk limit

        Args:
            symbol: Asset symbol
            max_risk_pct: Maximum risk as % of capital

        Returns:
            Dict with limit setting result
        """
        with self._lock:
            max_risk_usd = self.config.total_capital * (max_risk_pct / 100.0)

            self._asset_limits[symbol] = {
                "max_risk_pct": max_risk_pct,
                "max_risk_usd": max_risk_usd,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Set asset limit for {symbol}: {max_risk_pct}% (${max_risk_usd:.2f})")

            return {
                "success": True,
                "symbol": symbol,
                "max_risk_pct": max_risk_pct,
                "max_risk_usd": max_risk_usd,
            }

    def get_asset_risk_usage(self, symbol: str) -> Dict[str, Any]:
        """Get current asset risk usage"""
        with self._lock:
            # Get limit (default if not set)
            if symbol in self._asset_limits:
                max_risk_usd = self._asset_limits[symbol]["max_risk_usd"]
            else:
                max_risk_usd = self.config.total_capital * (self.config.max_asset_risk_pct / 100.0)

            # Calculate current usage
            current_risk_usd = self._asset_usage.get(symbol, 0.0)

            return {
                "symbol": symbol,
                "max_risk_usd": max_risk_usd,
                "current_risk_usd": current_risk_usd,
                "available_risk_usd": max(0, max_risk_usd - current_risk_usd),
                "utilization_pct": (current_risk_usd / max_risk_usd * 100.0) if max_risk_usd > 0 else 0.0,
            }

    def can_add_asset_risk(
        self,
        symbol: str,
        additional_risk: float
    ) -> Tuple[bool, str]:
        """
        Check if additional risk can be added to asset

        Args:
            symbol: Asset symbol
            additional_risk: Additional risk amount in USD

        Returns:
            Tuple of (can_add, reason)
        """
        usage = self.get_asset_risk_usage(symbol)

        if usage["current_risk_usd"] + additional_risk > usage["max_risk_usd"]:
            return False, f"Would exceed asset limit for {symbol} (current: ${usage['current_risk_usd']:.2f}, limit: ${usage['max_risk_usd']:.2f})"

        return True, "Within asset limits"

    def update_positions(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update current positions and recalculate usage

        Args:
            positions: List of position dicts with keys: symbol, strategy, risk_amount

        Returns:
            Dict with update result
        """
        with self._lock:
            self._current_positions = positions

            # Recalculate strategy usage
            self._strategy_usage = {}
            for pos in positions:
                strategy = pos.get("strategy", "unknown")
                risk = pos.get("risk_amount", 0.0)
                self._strategy_usage[strategy] = self._strategy_usage.get(strategy, 0.0) + risk

            # Recalculate asset usage
            self._asset_usage = {}
            for pos in positions:
                symbol = pos.get("symbol", "unknown")
                risk = pos.get("risk_amount", 0.0)
                self._asset_usage[symbol] = self._asset_usage.get(symbol, 0.0) + risk

            # Check if rebalance needed
            rebalance_checked = False
            if self.config.auto_rebalance and self.needs_rebalancing():
                self.force_rebalance()
                rebalance_checked = True

            # Generate alerts
            self._generate_alerts()

            logger.debug(f"Updated positions: {len(positions)} positions, {len(self._strategy_usage)} strategies")

            return {
                "success": True,
                "positions_count": len(positions),
                "strategies_count": len(self._strategy_usage),
                "rebalance_checked": rebalance_checked,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def update_volatility(self, volatility_data: Dict[str, Dict[str, float]]) -> None:
        """Update volatility data for adjustments"""
        with self._lock:
            self._volatility_data = volatility_data
            logger.debug(f"Updated volatility data for {len(volatility_data)} symbols")

    def update_correlations(self, correlation_data: Dict[str, Any]) -> None:
        """Update correlation data for adjustments"""
        with self._lock:
            self._correlation_data = correlation_data
            logger.debug("Updated correlation data")

    def update_attribution(self, attribution_data: Dict[str, Any]) -> None:
        """Update performance attribution data for adjustments"""
        with self._lock:
            self._attribution_data = attribution_data
            logger.debug("Updated attribution data")

    def update_kelly_data(self, kelly_data: Dict[str, Dict[str, float]]) -> None:
        """Update Kelly criterion data for adjustments"""
        with self._lock:
            self._kelly_data = kelly_data
            logger.debug(f"Updated Kelly data for {len(kelly_data)} strategies")

    def calculate_volatility_multiplier(
        self,
        volatility_data: Dict[str, float]
    ) -> float:
        """
        Calculate volatility-based budget multiplier

        Args:
            volatility_data: Dict with keys: current_volatility, historical_avg, percentile_rank

        Returns:
            Multiplier (0.5 to 1.5)
        """
        if not self.config.volatility_adjustment_enabled:
            return 1.0

        percentile = volatility_data.get("percentile_rank", 50)

        # VIX-style adjustment
        if percentile > 90:  # Extreme volatility
            multiplier = 0.5
        elif percentile > 80:  # High volatility
            multiplier = 0.7
        elif percentile > 60:  # Elevated volatility
            multiplier = 0.9
        elif percentile < 20:  # Low volatility
            multiplier = 1.3
        elif percentile < 10:  # Very low volatility
            multiplier = 1.5
        else:  # Normal volatility
            multiplier = 1.0

        return multiplier

    def calculate_correlation_multiplier(self) -> float:
        """
        Calculate correlation-based budget multiplier

        Returns:
            Multiplier (0.6 to 1.2)
        """
        if not self.config.correlation_adjustment_enabled:
            return 1.0

        avg_corr = self._correlation_data.get("avg_correlation", 0.5)

        # High correlation = reduce budget
        if avg_corr > 0.8:  # Very high correlation
            multiplier = 0.6
        elif avg_corr > 0.7:  # High correlation
            multiplier = 0.8
        elif avg_corr > 0.5:  # Moderate correlation
            multiplier = 0.9
        elif avg_corr < 0.3:  # Low correlation (well diversified)
            multiplier = 1.2
        else:  # Normal correlation
            multiplier = 1.0

        return multiplier

    def calculate_performance_multiplier(self, strategy_name: str) -> float:
        """
        Calculate performance-based budget multiplier

        Args:
            strategy_name: Strategy to calculate multiplier for

        Returns:
            Multiplier (0.25 to 1.5)
        """
        if not self.config.performance_adjustment_enabled:
            return 1.0

        # Get strategy performance
        by_strategy = self._attribution_data.get("by_strategy", {})
        strategy_perf = by_strategy.get(strategy_name, {})

        # Need minimum trades
        trades_count = strategy_perf.get("trades_count", 0)
        if trades_count < self.config.min_trades_for_performance:
            return 1.0  # Neutral until enough data

        # Use Sharpe ratio for adjustment
        sharpe = strategy_perf.get("sharpe_ratio", 0.0)

        if sharpe > 2.0:  # Excellent performance
            multiplier = 1.5
        elif sharpe > 1.5:  # Good performance
            multiplier = 1.3
        elif sharpe > 1.0:  # Above average
            multiplier = 1.1
        elif sharpe < 0:  # Losing strategy
            multiplier = 0.5
        elif sharpe < 0.5:  # Poor performance
            multiplier = 0.7
        else:  # Average performance
            multiplier = 1.0

        # Floor and ceiling
        return max(0.25, min(1.5, multiplier))

    def get_strategy_budget_usage(self, strategy_name: str) -> Dict[str, Any]:
        """Get current strategy budget usage"""
        with self._lock:
            allocation = self._strategy_allocations.get(strategy_name, {})
            allocated_budget = allocation.get("allocated_budget", 0.0)
            used_budget = self._strategy_usage.get(strategy_name, 0.0)

            return {
                "strategy": strategy_name,
                "allocated_budget": allocated_budget,
                "used_budget": used_budget,
                "available_budget": max(0, allocated_budget - used_budget),
                "utilization_pct": (used_budget / allocated_budget * 100.0) if allocated_budget > 0 else 0.0,
            }

    def get_adjusted_strategy_budget(
        self,
        strategy_name: str,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get strategy budget with all adjustments applied

        Args:
            strategy_name: Strategy name
            symbol: Optional symbol for symbol-specific volatility adjustment

        Returns:
            Dict with adjusted budget details
        """
        base = self.get_strategy_budget_usage(strategy_name)

        # Calculate multipliers
        vol_multiplier = 1.0
        if symbol and symbol in self._volatility_data:
            vol_multiplier = self.calculate_volatility_multiplier(self._volatility_data[symbol])

        corr_multiplier = self.calculate_correlation_multiplier()
        perf_multiplier = self.calculate_performance_multiplier(strategy_name)

        # Combined multiplier
        combined = vol_multiplier * corr_multiplier * perf_multiplier
        combined = max(0.1, min(2.0, combined))  # Bound to 0.1-2.0

        adjusted_budget = base["allocated_budget"] * combined

        return {
            **base,
            "volatility_multiplier": vol_multiplier,
            "correlation_multiplier": corr_multiplier,
            "performance_multiplier": perf_multiplier,
            "combined_multiplier": combined,
            "adjusted_budget": adjusted_budget,
            "correlation_adjusted_budget": base["allocated_budget"] * corr_multiplier,
        }

    def get_kelly_adjusted_budget(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get budget with Kelly criterion adjustment

        Args:
            strategy_name: Strategy name

        Returns:
            Dict with Kelly-adjusted budget
        """
        base = self.get_strategy_budget_usage(strategy_name)

        if not self.config.kelly_integration_enabled:
            return {
                **base,
                "kelly_recommendation": base["allocated_budget"],
                "kelly_multiplier": 1.0,
                "final_budget": base["allocated_budget"],
            }

        # Get Kelly data
        kelly = self._kelly_data.get(strategy_name, {})
        fractional_kelly_pct = kelly.get("fractional_kelly_pct", 0.0)

        # Kelly multiplier based on recommendation
        if fractional_kelly_pct <= 0:  # No edge or negative edge
            kelly_multiplier = 0.1  # Minimal allocation
        elif fractional_kelly_pct < 2.0:
            kelly_multiplier = 0.5  # Reduce significantly
        elif fractional_kelly_pct < 5.0:
            kelly_multiplier = 0.8  # Reduce moderately
        else:
            kelly_multiplier = 1.0  # Full allocation

        final_budget = base["allocated_budget"] * kelly_multiplier

        return {
            **base,
            "kelly_recommendation": fractional_kelly_pct,
            "kelly_multiplier": kelly_multiplier,
            "final_budget": final_budget,
        }

    def get_effective_budget(
        self,
        strategy_name: str,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get effective budget with ALL adjustments

        Args:
            strategy_name: Strategy name
            symbol: Optional symbol for symbol-specific adjustments

        Returns:
            Dict with complete budget calculation
        """
        base = self.get_strategy_budget_usage(strategy_name)

        # Calculate all multipliers
        vol_multiplier = 1.0
        if symbol and symbol in self._volatility_data:
            vol_multiplier = self.calculate_volatility_multiplier(self._volatility_data[symbol])

        corr_multiplier = self.calculate_correlation_multiplier()
        perf_multiplier = self.calculate_performance_multiplier(strategy_name)

        # Kelly multiplier
        kelly_multiplier = 1.0
        if self.config.kelly_integration_enabled:
            kelly = self._kelly_data.get(strategy_name, {})
            fractional_kelly_pct = kelly.get("fractional_kelly_pct", 5.0)
            if fractional_kelly_pct <= 0:
                kelly_multiplier = 0.1
            elif fractional_kelly_pct < 2.0:
                kelly_multiplier = 0.5
            elif fractional_kelly_pct < 5.0:
                kelly_multiplier = 0.8

        # Combined multiplier with bounds
        combined = vol_multiplier * corr_multiplier * perf_multiplier * kelly_multiplier
        combined = max(0.1, min(2.0, combined))

        effective_budget = base["allocated_budget"] * combined

        return {
            "strategy": strategy_name,
            "symbol": symbol,
            "base_budget": base["allocated_budget"],
            "volatility_multiplier": vol_multiplier,
            "correlation_multiplier": corr_multiplier,
            "performance_multiplier": perf_multiplier,
            "kelly_multiplier": kelly_multiplier,
            "combined_multiplier": combined,
            "effective_budget": max(0, effective_budget),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def can_place_order(
        self,
        strategy_name: str,
        symbol: str,
        order_risk_amount: float
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if order can be placed within budgets

        Args:
            strategy_name: Strategy name
            symbol: Asset symbol
            order_risk_amount: Risk amount of the order in USD

        Returns:
            Tuple of (can_place, reason)
        """
        # Validate risk amount
        if order_risk_amount < 0:
            return False, "Invalid risk amount: cannot be negative"

        with self._lock:
            # Check total budget
            state = self.get_budget_state()
            if state["used_budget"] + order_risk_amount > state["total_budget"]:
                return False, f"Would exceed total budget (used: ${state['used_budget']:.2f}, limit: ${state['total_budget']:.2f})"

            # Check strategy budget
            strategy_usage = self.get_strategy_budget_usage(strategy_name)
            if strategy_usage["used_budget"] + order_risk_amount > strategy_usage["allocated_budget"]:
                return False, f"Would exceed strategy budget for {strategy_name} (used: ${strategy_usage['used_budget']:.2f}, limit: ${strategy_usage['allocated_budget']:.2f})"

            # Check asset limit
            asset_usage = self.get_asset_risk_usage(symbol)
            if asset_usage["current_risk_usd"] + order_risk_amount > asset_usage["max_risk_usd"]:
                return False, f"Would exceed asset limit for {symbol} (used: ${asset_usage['current_risk_usd']:.2f}, limit: ${asset_usage['max_risk_usd']:.2f})"

            return True, "Order approved within all budget limits"

    def needs_rebalancing(self) -> bool:
        """Check if portfolio needs rebalancing"""
        with self._lock:
            for strategy_name, allocation in self._strategy_allocations.items():
                target_pct = allocation["allocation_pct"]

                # Calculate current percentage
                total_budget = self.config.total_capital * (self.config.max_total_risk_pct / 100.0)
                current_usage = self._strategy_usage.get(strategy_name, 0.0)
                current_pct = (current_usage / total_budget * 100.0) if total_budget > 0 else 0.0

                # Check drift
                drift = abs(current_pct - target_pct)
                if drift > self.config.rebalance_threshold_pct:
                    return True

            return False

    def calculate_rebalance_actions(self) -> List[Dict[str, Any]]:
        """Calculate rebalancing actions needed"""
        with self._lock:
            actions = []
            total_budget = self.config.total_capital * (self.config.max_total_risk_pct / 100.0)

            for strategy_name, allocation in self._strategy_allocations.items():
                target_pct = allocation["allocation_pct"]
                target_budget = total_budget * (target_pct / 100.0)

                current_usage = self._strategy_usage.get(strategy_name, 0.0)

                if current_usage < target_budget - (target_budget * self.config.rebalance_threshold_pct / 100.0):
                    actions.append({
                        "strategy": strategy_name,
                        "current_allocation": current_usage,
                        "target_allocation": target_budget,
                        "action_type": "increase",
                        "amount": target_budget - current_usage,
                    })
                elif current_usage > target_budget + (target_budget * self.config.rebalance_threshold_pct / 100.0):
                    actions.append({
                        "strategy": strategy_name,
                        "current_allocation": current_usage,
                        "target_allocation": target_budget,
                        "action_type": "decrease",
                        "amount": current_usage - target_budget,
                    })

            return actions

    def force_rebalance(self) -> Dict[str, Any]:
        """Force portfolio rebalancing"""
        with self._lock:
            actions = self.calculate_rebalance_actions()
            self._last_rebalance = datetime.now(timezone.utc)

            logger.info(f"Forced rebalance with {len(actions)} actions")

            return {
                "success": True,
                "rebalanced_at": self._last_rebalance.isoformat(),
                "actions_taken": actions,
            }

    def _generate_alerts(self) -> None:
        """Generate budget alerts based on current state"""
        self._alerts = []

        # Check total budget utilization
        state = self.get_budget_state()
        if state["utilization_pct"] >= 100:
            self._alerts.append(BudgetAlert(
                severity=AlertSeverity.CRITICAL,
                message=f"Total budget limit reached ({state['utilization_pct']:.1f}%)",
                timestamp=datetime.now(timezone.utc),
                recommendations=[
                    "Close losing positions immediately",
                    "Reduce position sizes",
                    "Suspend new order placement",
                ],
                metadata={"utilization_pct": state["utilization_pct"]},
            ))
        elif state["utilization_pct"] >= self.config.alert_threshold_pct:
            self._alerts.append(BudgetAlert(
                severity=AlertSeverity.WARNING,
                message=f"Total budget usage at {state['utilization_pct']:.1f}% (threshold: {self.config.alert_threshold_pct}%)",
                timestamp=datetime.now(timezone.utc),
                recommendations=[
                    "Monitor positions closely",
                    "Consider reducing new position sizes",
                ],
                metadata={"utilization_pct": state["utilization_pct"]},
            ))

        # Check volatility alerts
        for symbol, vol_data in self._volatility_data.items():
            percentile = vol_data.get("percentile_rank", 50)
            if percentile >= 90:
                self._alerts.append(BudgetAlert(
                    severity=AlertSeverity.WARNING,
                    message=f"Extreme volatility detected for {symbol} ({percentile}th percentile)",
                    timestamp=datetime.now(timezone.utc),
                    recommendations=[
                        f"Reduce position sizes for {symbol}",
                        "Tighten stop losses",
                        "Consider exiting volatile positions",
                    ],
                    metadata={"symbol": symbol, "percentile": percentile},
                ))

    def get_budget_alerts(self) -> List[Dict[str, Any]]:
        """Get current budget alerts"""
        with self._lock:
            return [
                {
                    "severity": alert.severity.value,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "recommendations": alert.recommendations,
                    "metadata": alert.metadata,
                }
                for alert in self._alerts
            ]

    def get_budgets_api_response(self) -> Dict[str, Any]:
        """Get formatted response for GET /api/v1/risk/budgets"""
        with self._lock:
            state = self.get_budget_state()

            # By strategy
            by_strategy = {}
            for strategy_name in self._strategy_allocations.keys():
                by_strategy[strategy_name] = self.get_effective_budget(strategy_name)

            # By asset
            by_asset = {}
            for symbol in set(pos.get("symbol") for pos in self._current_positions):
                by_asset[symbol] = self.get_asset_risk_usage(symbol)

            return {
                **state,
                "by_strategy": by_strategy,
                "by_asset": by_asset,
                "alerts": self.get_budget_alerts(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def rebalance_api_response(self) -> Dict[str, Any]:
        """Get formatted response for PUT /api/v1/risk/budgets/rebalance"""
        before = self.get_budget_state()
        result = self.force_rebalance()
        after = self.get_budget_state()

        return {
            "success": result["success"],
            "rebalanced_at": result["rebalanced_at"],
            "before": before,
            "after": after,
            "actions_taken": result["actions_taken"],
            "message": f"Rebalancing completed with {len(result['actions_taken'])} actions",
        }

    def get_state(self) -> Dict[str, Any]:
        """Get complete state for persistence"""
        with self._lock:
            return {
                "config": self.config.to_dict(),
                "strategy_allocations": dict(self._strategy_allocations),
                "asset_limits": dict(self._asset_limits),
                "current_volatility": dict(self._volatility_data),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Load state from persistence"""
        with self._lock:
            if "config" in state:
                self.config = BudgetConfig(**state["config"])
            if "strategy_allocations" in state:
                self._strategy_allocations = state["strategy_allocations"]
            if "asset_limits" in state:
                self._asset_limits = state["asset_limits"]

            logger.info("Loaded budget manager state from persistence")

    def reset(self) -> None:
        """Reset all budget state"""
        with self._lock:
            self._strategy_allocations.clear()
            self._asset_limits.clear()
            self._current_positions.clear()
            self._strategy_usage.clear()
            self._asset_usage.clear()
            self._volatility_data.clear()
            self._correlation_data.clear()
            self._attribution_data.clear()
            self._kelly_data.clear()
            self._alerts.clear()
            self._last_rebalance = None

            logger.info("Reset budget manager state")


# Global singleton instance
_budget_manager: Optional[DynamicBudgetManager] = None
_manager_lock = RLock()


def get_budget_manager(config: Optional[BudgetConfig] = None) -> DynamicBudgetManager:
    """
    Get or create global budget manager instance (singleton)

    Args:
        config: Optional config for first initialization

    Returns:
        DynamicBudgetManager instance
    """
    global _budget_manager

    with _manager_lock:
        if _budget_manager is None:
            _budget_manager = DynamicBudgetManager(config=config)
            logger.info("Created global budget manager instance")
        return _budget_manager


def reset_budget_manager() -> None:
    """Reset global budget manager instance"""
    global _budget_manager

    with _manager_lock:
        _budget_manager = None
        logger.info("Reset global budget manager instance")
