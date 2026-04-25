"""
Performance Tracker
====================
Purpose: Track per-strategy performance and trigger reallocation based on metrics

The Performance Tracker provides:
1. Enhanced performance tracking with reallocation triggers
2. Comparative metrics across strategies
3. Underperformer detection with actionable recommendations
4. Attribution analysis for portfolio returns
5. Automatic reallocation trigger detection

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
    StrategyPerformanceMetrics,
    StrategyState,
    StrategyStatus,
)
from app.orchestration.metrics import (
    StrategyMetrics,
    StrategyMetricsConfig,
    MetricsTrade,
    get_strategy_metrics_tracker,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# PERFORMANCE TRACKER CONFIGURATION
# =============================================================================

@dataclass
class PerformanceTrackerConfig:
    """
    Configuration for Performance Tracker

    Controls reallocation triggers, thresholds, and detection windows.
    """
    # Underperformance thresholds
    underperformance_sharpe_threshold: float = 0.0  # Below 0 = underperforming
    underperformance_profit_factor: float = 1.0  # Below 1 = losing money
    underperformance_win_rate: float = 0.35  # Below 35% = concerning
    underperformance_consecutive_losses: int = 5  # Max consecutive losses

    # Reallocation triggers
    realloc_sharpe_improvement: float = 0.5  # Sharpe increase triggers review
    realloc_sharpe_decline: float = -0.5  # Sharpe drop triggers reduction
    realloc_drawdown_trigger: float = 10.0  # Drawdown % to trigger reduction
    realloc_win_streak_bonus: int = 5  # Consecutive wins for bonus allocation
    realloc_min_trades_for_eval: int = 20  # Minimum trades before evaluation
    realloc_evaluation_window_days: int = 30  # Days to evaluate performance

    # Target allocation adjustments
    max_allocation_increase_pct: float = 5.0  # Max increase per reallocation
    max_allocation_decrease_pct: float = 10.0  # Max decrease per reallocation
    min_allocation_pct: float = 2.0  # Minimum allocation to maintain
    max_allocation_pct: float = 25.0  # Maximum allocation cap

    # Performance decay
    decay_rate_per_period: float = 0.95  # 5% decay per evaluation period
    recovery_rate_per_period: float = 1.02  # 2% recovery per positive period

    # Correlation thresholds for attribution
    high_correlation_threshold: float = 0.7
    diversification_target: float = 0.5  # Target average correlation

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "underperformance_sharpe_threshold": self.underperformance_sharpe_threshold,
            "underperformance_profit_factor": self.underperformance_profit_factor,
            "realloc_min_trades_for_eval": self.realloc_min_trades_for_eval,
            "realloc_evaluation_window_days": self.realloc_evaluation_window_days,
            "max_allocation_increase_pct": self.max_allocation_increase_pct,
        }


# =============================================================================
# REALLOCATION RECOMMENDATION
# =============================================================================

@dataclass
class ReallocationRecommendation:
    """
    Recommendation for strategy allocation change
    """
    strategy_id: str
    current_allocation_pct: float
    recommended_allocation_pct: float
    change_pct: float
    trigger: str
    reason: str
    confidence: float  # 0-1, how confident in recommendation
    priority: str  # LOW, MEDIUM, HIGH, CRITICAL
    metrics_summary: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "current_allocation_pct": self.current_allocation_pct,
            "recommended_allocation_pct": self.recommended_allocation_pct,
            "change_pct": self.change_pct,
            "trigger": self.trigger,
            "reason": self.reason,
            "confidence": self.confidence,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
        }


# =============================================================================
# UNDERPERFORMER RECORD
# =============================================================================

@dataclass
class UnderperformerRecord:
    """
    Record of an underperforming strategy
    """
    strategy_id: str
    detection_time: datetime
    reasons: List[str]
    metrics: StrategyPerformanceMetrics
    severity: str  # WARNING, HIGH, CRITICAL
    recommended_action: str  # MONITOR, REDUCE, PAUSE
    consecutive_underperformance_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "strategy_id": self.strategy_id,
            "detection_time": self.detection_time.isoformat(),
            "reasons": self.reasons,
            "severity": self.severity,
            "recommended_action": self.recommended_action,
            "consecutive_days": self.consecutive_underperformance_days,
            "sharpe": self.metrics.sharpe_ratio if self.metrics else 0,
        }


# =============================================================================
# PERFORMANCE TRACKER
# =============================================================================

class PerformanceTracker:
    """
    Strategy Performance Tracker with Reallocation Triggers

    Extends the base StrategyMetrics to add:

    1. Reallocation Triggers:
       - Strategy underperforming for N days -> reduce allocation
       - Strategy exceeding targets -> increase allocation
       - Strategy Sharpe < threshold -> pause strategy
       - Max drawdown exceeded -> reduce allocation

    2. Enhanced Metrics:
       - Rolling performance windows
       - Trend detection (improving/declining)
       - Peer comparison
       - Risk-adjusted rankings

    3. Attribution Analysis:
       - Contribution to portfolio returns
       - Risk contribution
       - Alpha/beta decomposition

    4. Automated Recommendations:
       - Allocation adjustment suggestions
       - Pause/resume recommendations
       - Diversification alerts

    Usage:
        tracker = PerformanceTracker()

        # Record trades
        tracker.record_strategy_trade(trade)

        # Check for underperformers
        underperformers = tracker.detect_underperformers()

        # Get reallocation recommendations
        recommendations = tracker.get_reallocation_recommendations(current_allocations)

        # Get portfolio attribution
        attribution = tracker.get_portfolio_attribution()
    """

    def __init__(
        self,
        config: Optional[PerformanceTrackerConfig] = None,
        metrics_tracker: Optional[StrategyMetrics] = None
    ):
        """
        Initialize Performance Tracker

        Args:
            config: Tracker configuration
            metrics_tracker: Optional underlying metrics tracker
        """
        self.config = config or PerformanceTrackerConfig()
        self._metrics = metrics_tracker or get_strategy_metrics_tracker()
        self._lock = RLock()

        # Performance history
        self._performance_history: Dict[str, List[Tuple[datetime, StrategyPerformanceMetrics]]] = defaultdict(list)

        # Underperformer tracking
        self._underperformer_records: Dict[str, UnderperformerRecord] = {}
        self._underperformer_history: List[UnderperformerRecord] = []

        # Current allocation tracking (for recommendations)
        self._current_allocations: Dict[str, float] = {}

        # Strategy baseline metrics (for comparison)
        self._baseline_metrics: Dict[str, StrategyPerformanceMetrics] = {}

        # Performance trends
        self._performance_trends: Dict[str, str] = {}  # "improving", "declining", "stable"

        # Reallocation history
        self._reallocation_history: List[ReallocationRecommendation] = []

        logger.info(
            f"PerformanceTracker initialized: "
            f"underperf_sharpe={self.config.underperformance_sharpe_threshold}, "
            f"eval_window={self.config.realloc_evaluation_window_days}d"
        )

    # =========================================================================
    # TRADE RECORDING
    # =========================================================================

    def record_trade(self, trade: MetricsTrade) -> Dict[str, Any]:
        """
        Record a completed trade and update performance metrics

        Args:
            trade: Completed trade record

        Returns:
            Recording result with trigger analysis
        """
        with self._lock:
            # Record in underlying metrics
            result = self._metrics.record_trade(trade)

            # Get updated metrics
            metrics = self._metrics.get_strategy_metrics(trade.strategy_id)

            if metrics:
                # Store in history
                self._performance_history[trade.strategy_id].append(
                    (datetime.now(timezone.utc), metrics)
                )

                # Update trend
                self._update_performance_trend(trade.strategy_id)

                # Check for triggers
                triggers = self._check_reallocation_triggers(trade.strategy_id, metrics)

                # Check for underperformance
                self._check_underperformance(trade.strategy_id, metrics)

                result["triggers"] = triggers
                result["trend"] = self._performance_trends.get(trade.strategy_id, "unknown")

            return result

    # =========================================================================
    # UNDERPERFORMER DETECTION
    # =========================================================================

    def detect_underperformers(self) -> List[UnderperformerRecord]:
        """
        Detect underperforming strategies

        Returns:
            List of underperformer records
        """
        with self._lock:
            underperformers = []

            for strategy_id in self._metrics._trade_history.keys():
                metrics = self._metrics.get_strategy_metrics(strategy_id)
                if not metrics:
                    continue

                # Skip if not enough trades
                if metrics.total_trades < self.config.realloc_min_trades_for_eval:
                    continue

                reasons = []
                severity = "WARNING"

                # Check Sharpe ratio
                if metrics.sharpe_ratio < self.config.underperformance_sharpe_threshold:
                    reasons.append(f"Low Sharpe ratio: {metrics.sharpe_ratio:.2f}")
                    if metrics.sharpe_ratio < -0.5:
                        severity = "CRITICAL"
                    elif metrics.sharpe_ratio < 0:
                        severity = "HIGH"

                # Check profit factor
                if metrics.profit_factor < self.config.underperformance_profit_factor:
                    reasons.append(f"Low profit factor: {metrics.profit_factor:.2f}")
                    if metrics.profit_factor < 0.8:
                        severity = "HIGH"

                # Check win rate
                if metrics.win_rate < self.config.underperformance_win_rate:
                    reasons.append(f"Low win rate: {metrics.win_rate:.1%}")

                # Check drawdown
                if metrics.max_drawdown_pct > self.config.realloc_drawdown_trigger:
                    reasons.append(f"High drawdown: {metrics.max_drawdown_pct:.1f}%")
                    severity = "HIGH"

                if reasons:
                    # Determine recommended action
                    if severity == "CRITICAL":
                        action = "PAUSE"
                    elif severity == "HIGH":
                        action = "REDUCE"
                    else:
                        action = "MONITOR"

                    # Check if existing record
                    existing = self._underperformer_records.get(strategy_id)
                    if existing:
                        days = (datetime.now(timezone.utc) - existing.detection_time).days
                    else:
                        days = 0

                    record = UnderperformerRecord(
                        strategy_id=strategy_id,
                        detection_time=datetime.now(timezone.utc),
                        reasons=reasons,
                        metrics=metrics,
                        severity=severity,
                        recommended_action=action,
                        consecutive_underperformance_days=days
                    )

                    self._underperformer_records[strategy_id] = record
                    underperformers.append(record)

                    logger.warning(
                        f"Underperformer detected: {strategy_id} - "
                        f"severity={severity}, action={action}"
                    )

            return underperformers

    def _check_underperformance(
        self,
        strategy_id: str,
        metrics: StrategyPerformanceMetrics
    ) -> bool:
        """Check if strategy is underperforming and update records"""
        if metrics.total_trades < self.config.realloc_min_trades_for_eval:
            return False

        is_underperforming = (
            metrics.sharpe_ratio < self.config.underperformance_sharpe_threshold or
            metrics.profit_factor < self.config.underperformance_profit_factor or
            metrics.win_rate < self.config.underperformance_win_rate
        )

        if is_underperforming:
            if strategy_id not in self._underperformer_records:
                # New underperformer
                reasons = []
                if metrics.sharpe_ratio < self.config.underperformance_sharpe_threshold:
                    reasons.append(f"Sharpe {metrics.sharpe_ratio:.2f}")
                if metrics.profit_factor < self.config.underperformance_profit_factor:
                    reasons.append(f"PF {metrics.profit_factor:.2f}")
                if metrics.win_rate < self.config.underperformance_win_rate:
                    reasons.append(f"WR {metrics.win_rate:.1%}")

                self._underperformer_records[strategy_id] = UnderperformerRecord(
                    strategy_id=strategy_id,
                    detection_time=datetime.now(timezone.utc),
                    reasons=reasons,
                    metrics=metrics,
                    severity="WARNING",
                    recommended_action="MONITOR"
                )
        else:
            # No longer underperforming - remove from records
            if strategy_id in self._underperformer_records:
                del self._underperformer_records[strategy_id]

        return is_underperforming

    # =========================================================================
    # REALLOCATION TRIGGERS
    # =========================================================================

    def _check_reallocation_triggers(
        self,
        strategy_id: str,
        metrics: StrategyPerformanceMetrics
    ) -> List[str]:
        """Check for conditions that trigger reallocation"""
        triggers = []

        # Get baseline if exists
        baseline = self._baseline_metrics.get(strategy_id)

        if baseline:
            # Sharpe improvement
            sharpe_change = metrics.sharpe_ratio - baseline.sharpe_ratio
            if sharpe_change >= self.config.realloc_sharpe_improvement:
                triggers.append(f"sharpe_improved:{sharpe_change:.2f}")

            # Sharpe decline
            if sharpe_change <= self.config.realloc_sharpe_decline:
                triggers.append(f"sharpe_declined:{sharpe_change:.2f}")

        # Drawdown trigger
        if metrics.max_drawdown_pct >= self.config.realloc_drawdown_trigger:
            triggers.append(f"high_drawdown:{metrics.max_drawdown_pct:.1f}%")

        # Win streak bonus
        if metrics.win_streak_max >= self.config.realloc_win_streak_bonus:
            triggers.append(f"win_streak:{metrics.win_streak_max}")

        # Update baseline periodically
        if not baseline or len(triggers) > 0:
            self._baseline_metrics[strategy_id] = metrics

        return triggers

    def _update_performance_trend(self, strategy_id: str) -> None:
        """Update performance trend for a strategy"""
        history = self._performance_history.get(strategy_id, [])

        if len(history) < 5:
            self._performance_trends[strategy_id] = "unknown"
            return

        # Get recent Sharpe ratios
        recent = history[-5:]
        sharpes = [m.sharpe_ratio for _, m in recent]

        # Calculate slope
        if len(sharpes) >= 2:
            avg_first_half = statistics.mean(sharpes[:len(sharpes)//2])
            avg_second_half = statistics.mean(sharpes[len(sharpes)//2:])

            diff = avg_second_half - avg_first_half
            if diff > 0.1:
                self._performance_trends[strategy_id] = "improving"
            elif diff < -0.1:
                self._performance_trends[strategy_id] = "declining"
            else:
                self._performance_trends[strategy_id] = "stable"

    # =========================================================================
    # REALLOCATION RECOMMENDATIONS
    # =========================================================================

    def get_reallocation_recommendations(
        self,
        current_allocations: Dict[str, float]
    ) -> List[ReallocationRecommendation]:
        """
        Get recommendations for allocation changes

        Args:
            current_allocations: Current allocation percentages by strategy

        Returns:
            List of reallocation recommendations
        """
        with self._lock:
            self._current_allocations = current_allocations
            recommendations = []

            for strategy_id, current_pct in current_allocations.items():
                metrics = self._metrics.get_strategy_metrics(strategy_id)
                if not metrics:
                    continue

                if metrics.total_trades < self.config.realloc_min_trades_for_eval:
                    continue

                recommendation = self._calculate_recommendation(
                    strategy_id, current_pct, metrics
                )

                if recommendation:
                    recommendations.append(recommendation)
                    self._reallocation_history.append(recommendation)

            # Sort by priority and absolute change
            priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            recommendations.sort(
                key=lambda r: (priority_order.get(r.priority, 4), -abs(r.change_pct))
            )

            return recommendations

    def _calculate_recommendation(
        self,
        strategy_id: str,
        current_pct: float,
        metrics: StrategyPerformanceMetrics
    ) -> Optional[ReallocationRecommendation]:
        """Calculate allocation recommendation for a strategy"""
        recommended_pct = current_pct
        trigger = ""
        reason = ""
        confidence = 0.5
        priority = "LOW"

        # Check for underperformance
        if strategy_id in self._underperformer_records:
            record = self._underperformer_records[strategy_id]

            if record.severity == "CRITICAL":
                # Reduce significantly
                recommended_pct = max(
                    self.config.min_allocation_pct,
                    current_pct - self.config.max_allocation_decrease_pct
                )
                trigger = "underperformance_critical"
                reason = f"Critical underperformance: {', '.join(record.reasons)}"
                confidence = 0.9
                priority = "CRITICAL"

            elif record.severity == "HIGH":
                # Reduce moderately
                recommended_pct = max(
                    self.config.min_allocation_pct,
                    current_pct - (self.config.max_allocation_decrease_pct * 0.5)
                )
                trigger = "underperformance_high"
                reason = f"High underperformance: {', '.join(record.reasons)}"
                confidence = 0.75
                priority = "HIGH"

        # Check for outperformance
        elif metrics.sharpe_ratio > 1.0 and metrics.profit_factor > 1.5:
            # Good performer - consider increase
            if self._performance_trends.get(strategy_id) == "improving":
                recommended_pct = min(
                    self.config.max_allocation_pct,
                    current_pct + self.config.max_allocation_increase_pct
                )
                trigger = "outperformance"
                reason = f"Strong performance: Sharpe {metrics.sharpe_ratio:.2f}, PF {metrics.profit_factor:.2f}"
                confidence = 0.65
                priority = "MEDIUM"

        # Check drawdown
        if metrics.max_drawdown_pct > self.config.realloc_drawdown_trigger:
            if recommended_pct >= current_pct:
                # Override increase if high drawdown
                recommended_pct = max(
                    self.config.min_allocation_pct,
                    current_pct * (1 - metrics.max_drawdown_pct / 100)
                )
                trigger = "high_drawdown"
                reason = f"High drawdown: {metrics.max_drawdown_pct:.1f}%"
                confidence = 0.8
                priority = "HIGH"

        # Only return if meaningful change
        change_pct = recommended_pct - current_pct
        if abs(change_pct) < 1.0:
            return None

        return ReallocationRecommendation(
            strategy_id=strategy_id,
            current_allocation_pct=current_pct,
            recommended_allocation_pct=round(recommended_pct, 2),
            change_pct=round(change_pct, 2),
            trigger=trigger,
            reason=reason,
            confidence=confidence,
            priority=priority,
            metrics_summary={
                "sharpe": metrics.sharpe_ratio,
                "win_rate": metrics.win_rate,
                "profit_factor": metrics.profit_factor,
                "max_drawdown": metrics.max_drawdown_pct,
                "total_trades": metrics.total_trades,
            }
        )

    # =========================================================================
    # COMPARATIVE ANALYSIS
    # =========================================================================

    def compare_strategies(self) -> Dict[str, Any]:
        """Get comparative analysis of all strategies"""
        return self._metrics.compare_strategies()

    def get_strategy_ranking(
        self,
        metric: str = "sharpe_ratio",
        ascending: bool = False
    ) -> List[Tuple[str, float]]:
        """
        Rank strategies by a specific metric

        Args:
            metric: Metric to rank by
            ascending: Sort order

        Returns:
            List of (strategy_id, metric_value) tuples
        """
        with self._lock:
            rankings = []

            for strategy_id in self._metrics._trade_history.keys():
                metrics = self._metrics.get_strategy_metrics(strategy_id)
                if metrics:
                    value = getattr(metrics, metric, 0.0)
                    rankings.append((strategy_id, value))

            rankings.sort(key=lambda x: x[1], reverse=not ascending)
            return rankings

    def get_best_performer(self) -> Optional[str]:
        """Get the best performing strategy by Sharpe ratio"""
        ranking = self.get_strategy_ranking("sharpe_ratio")
        if ranking:
            return ranking[0][0]
        return None

    def get_worst_performer(self) -> Optional[str]:
        """Get the worst performing strategy by Sharpe ratio"""
        ranking = self.get_strategy_ranking("sharpe_ratio", ascending=True)
        if ranking:
            return ranking[0][0]
        return None

    # =========================================================================
    # PORTFOLIO ATTRIBUTION
    # =========================================================================

    def get_portfolio_attribution(self) -> Dict[str, Any]:
        """
        Get portfolio return attribution by strategy

        Returns:
            Attribution breakdown
        """
        return self._metrics.get_portfolio_attribution()

    def get_contribution_by_strategy(self) -> Dict[str, float]:
        """Get PnL contribution percentage by strategy"""
        attribution = self.get_portfolio_attribution()
        by_strategy = attribution.get("by_strategy", {})

        contributions = {}
        for strategy_id, data in by_strategy.items():
            contributions[strategy_id] = data.get("contribution_pct", 0.0)

        return contributions

    # =========================================================================
    # CORRELATION ANALYSIS
    # =========================================================================

    def get_strategy_correlations(self) -> Dict[str, Dict[str, float]]:
        """Get correlation matrix between strategies"""
        return self._metrics.get_correlations()

    def get_diversification_score(self) -> Dict[str, Any]:
        """Get portfolio diversification score"""
        return self._metrics.get_diversification_score()

    def get_highly_correlated_pairs(
        self,
        threshold: Optional[float] = None
    ) -> List[Tuple[str, str, float]]:
        """
        Get pairs of highly correlated strategies

        Args:
            threshold: Correlation threshold (default from config)

        Returns:
            List of (strategy1, strategy2, correlation) tuples
        """
        threshold = threshold or self.config.high_correlation_threshold
        correlations = self.get_strategy_correlations()

        pairs = []
        seen = set()

        for s1, corrs in correlations.items():
            for s2, corr in corrs.items():
                if s1 != s2 and (s2, s1) not in seen:
                    if corr >= threshold:
                        pairs.append((s1, s2, corr))
                    seen.add((s1, s2))

        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs

    # =========================================================================
    # STATUS AND REPORTING
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get tracker status summary"""
        with self._lock:
            return {
                "strategies_tracked": len(self._metrics._trade_history),
                "underperformers_count": len(self._underperformer_records),
                "underperformers": list(self._underperformer_records.keys()),
                "performance_trends": dict(self._performance_trends),
                "pending_recommendations": len([
                    r for r in self._reallocation_history[-10:]
                    if r.change_pct != 0
                ]),
                "config": self.config.to_dict(),
            }

    def get_strategy_report(self, strategy_id: str) -> Dict[str, Any]:
        """Get comprehensive report for a strategy"""
        with self._lock:
            metrics = self._metrics.get_strategy_metrics(strategy_id)
            if not metrics:
                return {"error": "Strategy not found or no data"}

            return {
                "strategy_id": strategy_id,
                "metrics": metrics.to_dict(),
                "trend": self._performance_trends.get(strategy_id, "unknown"),
                "is_underperforming": strategy_id in self._underperformer_records,
                "underperformance_details": (
                    self._underperformer_records[strategy_id].to_dict()
                    if strategy_id in self._underperformer_records else None
                ),
                "current_allocation": self._current_allocations.get(strategy_id, 0.0),
                "correlations": self._metrics.get_correlations().get(strategy_id, {}),
            }

    def get_underperformers(self) -> List[Dict[str, Any]]:
        """Get list of current underperformers"""
        return self._metrics.get_underperformers()


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT
# =============================================================================

# Global performance tracker instance
_performance_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker(
    config: Optional[PerformanceTrackerConfig] = None
) -> PerformanceTracker:
    """Get or create global performance tracker instance"""
    global _performance_tracker
    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker(config)
    return _performance_tracker


def reset_performance_tracker() -> None:
    """Reset global performance tracker instance"""
    global _performance_tracker
    _performance_tracker = None
    logger.info("Performance tracker instance reset")
