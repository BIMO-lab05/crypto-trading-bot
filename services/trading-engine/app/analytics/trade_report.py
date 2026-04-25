"""
Trade Report Generator Module
Purpose: Generate individual trade reports, daily summaries, weekly comparisons,
         and improvement recommendations based on post-trade analysis.

This module provides comprehensive reporting capabilities:
- Individual Trade Report Generation
- Daily Execution Summary Reports
- Weekly Performance Comparison
- Best/Worst Execution Analysis
- Trend Analysis and Improvement Tracking

Author: Backend Developer Agent
Date: 2025-12-12
Version: 1.1.0
"""

import logging
import threading
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import statistics
import json

from .post_trade_analysis import (
    PostTradeAnalyzer,
    PostTradeAnalysisResult,
    DailySummary,
    ImprovementRecommendation,
    TradeExecutionData,
    ExecutionQualityGrade,
    TradingSession,
    get_post_trade_analyzer,
)

# Configure logging for trade report module
logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS FOR REPORT TYPES
# =============================================================================

class ReportFormat(str, Enum):
    """Report output format"""
    JSON = "json"
    TEXT = "text"
    HTML = "html"


class ReportPeriod(str, Enum):
    """Report time periods"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class TrendDirection(str, Enum):
    """Trend direction indicators"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


# =============================================================================
# DATA MODELS FOR REPORTS
# =============================================================================

@dataclass
class IndividualTradeReport:
    """
    Detailed report for a single trade

    Contains full analysis, context, and recommendations.
    """
    trade_id: str
    report_generated_at: datetime

    # Trade Summary
    summary: Dict[str, Any]

    # Cost Analysis
    cost_analysis: Dict[str, Any]

    # Execution Quality
    quality_analysis: Dict[str, Any]

    # Context
    market_context: Dict[str, Any]

    # Comparison to historical
    historical_comparison: Dict[str, Any]

    # Recommendations
    recommendations: List[str]

    # Overall assessment
    overall_assessment: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "trade_id": self.trade_id,
            "report_generated_at": self.report_generated_at.isoformat(),
            "summary": self.summary,
            "cost_analysis": self.cost_analysis,
            "quality_analysis": self.quality_analysis,
            "market_context": self.market_context,
            "historical_comparison": self.historical_comparison,
            "recommendations": self.recommendations,
            "overall_assessment": self.overall_assessment,
        }

    def to_text(self) -> str:
        """Generate human-readable text report"""
        lines = [
            "=" * 60,
            f"TRADE EXECUTION REPORT: {self.trade_id}",
            f"Generated: {self.report_generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "=" * 60,
            "",
            "SUMMARY",
            "-" * 40,
            f"Symbol: {self.summary.get('symbol', 'N/A')}",
            f"Side: {self.summary.get('side', 'N/A')}",
            f"Size: {self.summary.get('size', 0):.6f}",
            f"Expected Price: ${self.summary.get('expected_price', 0):,.2f}",
            f"Execution Price: ${self.summary.get('execution_price', 0):,.2f}",
            f"Strategy: {self.summary.get('strategy', 'N/A')}",
            "",
            "COST ANALYSIS",
            "-" * 40,
            f"Slippage: {self.cost_analysis.get('slippage_bps', 0):.2f} bps (${self.cost_analysis.get('slippage_cost', 0):.2f})",
            f"  - Market Impact: ${self.cost_analysis.get('market_impact', 0):.2f}",
            f"  - Spread Cost: ${self.cost_analysis.get('spread_cost', 0):.2f}",
            f"  - Timing Cost: ${self.cost_analysis.get('timing_cost', 0):.2f}",
            f"Fees: ${self.cost_analysis.get('fees', 0):.2f}",
            f"Total Cost: {self.cost_analysis.get('total_cost_bps', 0):.2f} bps (${self.cost_analysis.get('total_cost', 0):.2f})",
            "",
            "EXECUTION QUALITY",
            "-" * 40,
            f"Quality Score: {self.quality_analysis.get('score', 0)}/100 ({self.quality_analysis.get('grade', 'N/A')})",
            f"Implementation Shortfall: {self.quality_analysis.get('impl_shortfall_bps', 0):.2f} bps",
            f"Price Improvement: {self.quality_analysis.get('price_improvement_bps', 0):.2f} bps",
            f"Fill Rate: {self.quality_analysis.get('fill_rate', 100):.1f}%",
            f"Time to Completion: {self.quality_analysis.get('time_seconds', 0):.1f}s",
            "",
            "MARKET CONTEXT",
            "-" * 40,
            f"Execution Style: {self.market_context.get('execution_style', 'N/A')}",
            f"Market Condition: {self.market_context.get('market_condition', 'N/A')}",
            f"Liquidity Level: {self.market_context.get('liquidity', 'N/A')}",
            f"Trading Session: {self.market_context.get('session', 'N/A')}",
            "",
            "HISTORICAL COMPARISON",
            "-" * 40,
            f"vs Strategy Avg: {self.historical_comparison.get('vs_strategy_avg', 'N/A')}",
            f"vs Symbol Avg: {self.historical_comparison.get('vs_symbol_avg', 'N/A')}",
            f"Percentile Rank: {self.historical_comparison.get('percentile', 'N/A')}",
            "",
            "RECOMMENDATIONS",
            "-" * 40,
        ]

        for i, rec in enumerate(self.recommendations, 1):
            lines.append(f"{i}. {rec}")

        lines.extend([
            "",
            "OVERALL ASSESSMENT",
            "-" * 40,
            self.overall_assessment,
            "",
            "=" * 60,
        ])

        return "\n".join(lines)


@dataclass
class WeeklyComparisonReport:
    """
    Weekly performance comparison report

    Compares current week to previous week and historical averages.
    """
    week_start: str
    week_end: str
    report_generated_at: datetime

    # Current week metrics
    current_week: Dict[str, Any]

    # Previous week metrics
    previous_week: Optional[Dict[str, Any]]

    # Week-over-week changes
    wow_changes: Dict[str, Any]

    # Trends
    trends: Dict[str, TrendDirection]

    # Top performers
    best_executions: List[Dict[str, Any]]
    worst_executions: List[Dict[str, Any]]

    # Strategy comparison
    strategy_comparison: Dict[str, Dict[str, Any]]

    # Symbol comparison
    symbol_comparison: Dict[str, Dict[str, Any]]

    # Key insights
    insights: List[str]

    # Recommendations
    recommendations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "report_generated_at": self.report_generated_at.isoformat(),
            "current_week": self.current_week,
            "previous_week": self.previous_week,
            "wow_changes": self.wow_changes,
            "trends": {k: v.value for k, v in self.trends.items()},
            "best_executions": self.best_executions,
            "worst_executions": self.worst_executions,
            "strategy_comparison": self.strategy_comparison,
            "symbol_comparison": self.symbol_comparison,
            "insights": self.insights,
            "recommendations": self.recommendations,
        }


@dataclass
class ExecutionTrend:
    """
    Trend analysis for execution metrics over time

    Tracks improvement or degradation in execution quality.
    """
    metric_name: str
    current_value: float
    previous_value: float
    change_pct: float
    direction: TrendDirection
    data_points: List[Tuple[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "metric_name": self.metric_name,
            "current_value": round(self.current_value, 4),
            "previous_value": round(self.previous_value, 4),
            "change_pct": round(self.change_pct, 2),
            "direction": self.direction.value,
            "data_points": [
                {"date": d, "value": round(v, 4)}
                for d, v in self.data_points
            ],
        }


# =============================================================================
# TRADE REPORT GENERATOR
# =============================================================================

class TradeReportGenerator:
    """
    Trade Report Generator

    Generates various reports from post-trade analysis data including
    individual trade reports, daily summaries, weekly comparisons,
    and trend analysis.

    Thread-safe implementation for concurrent report generation.

    Usage:
        generator = get_trade_report_generator()
        report = generator.generate_individual_report(trade_id)
        weekly = generator.generate_weekly_comparison()
    """

    def __init__(self, analyzer: Optional[PostTradeAnalyzer] = None):
        """
        Initialize the Trade Report Generator

        Args:
            analyzer: PostTradeAnalyzer instance (uses global singleton if not provided)
        """
        self._lock = threading.Lock()
        # Use provided analyzer or get the global singleton
        # This ensures we always use the same analyzer instance in tests
        self._analyzer = analyzer

        # Report cache
        self._report_cache: Dict[str, Any] = {}

        logger.info("TradeReportGenerator initialized")

    @property
    def _analyzer_instance(self) -> PostTradeAnalyzer:
        """
        Get the analyzer instance lazily

        This property ensures we always get the current global singleton
        if no explicit analyzer was provided. This is important for tests
        where the singleton may be reset between test fixtures.
        """
        if self._analyzer is not None:
            return self._analyzer
        return get_post_trade_analyzer()

    # =========================================================================
    # INDIVIDUAL TRADE REPORTS
    # =========================================================================

    def generate_individual_report(
        self,
        trade_id: str,
        format: ReportFormat = ReportFormat.JSON,
    ) -> Optional[IndividualTradeReport]:
        """
        Generate detailed report for a single trade

        Args:
            trade_id: Trade identifier
            format: Output format

        Returns:
            IndividualTradeReport or None if trade not found
        """
        with self._lock:
            # Get analysis result - use property to get correct analyzer
            analysis = self._analyzer_instance.get_analysis(trade_id)
            if not analysis:
                logger.warning(f"No analysis found for trade: {trade_id}")
                return None

            # Build summary section
            summary = {
                "symbol": analysis.symbol,
                "side": analysis.side,
                "size": analysis.size,
                "expected_price": analysis.expected_price,
                "execution_price": analysis.execution_price,
                "strategy": analysis.strategy,
                "executed_at": analysis.analyzed_at.isoformat(),
            }

            # Build cost analysis section
            cost_analysis = {
                "slippage_bps": analysis.slippage.slippage_bps,
                "slippage_cost": analysis.slippage.total_slippage,
                "market_impact": analysis.slippage.market_impact,
                "spread_cost": analysis.slippage.spread_cost,
                "timing_cost": analysis.slippage.timing_cost,
                "fees": analysis.fees,
                "total_cost_bps": analysis.cost_bps,
                "total_cost": analysis.total_cost,
            }

            # Build quality analysis section
            quality_analysis = {
                "score": analysis.execution_quality.quality_score,
                "grade": analysis.execution_quality.quality_grade.value,
                "impl_shortfall_bps": analysis.execution_quality.implementation_shortfall_bps,
                "price_improvement_bps": analysis.execution_quality.price_improvement_bps,
                "fill_rate": analysis.execution_quality.fill_rate,
                "time_seconds": analysis.execution_quality.time_to_completion,
                "spread_capture_rate": analysis.execution_quality.spread_capture_rate,
                "benchmark_comparisons": analysis.execution_quality.benchmark_comparisons,
            }

            # Build market context section
            market_context = {
                "execution_style": analysis.classification.execution_style.value,
                "market_condition": analysis.classification.market_condition.value,
                "liquidity": analysis.classification.liquidity_level.value,
                "session": analysis.classification.trading_session.value,
                "urgency": analysis.classification.order_urgency,
            }

            # Build historical comparison
            historical_comparison = self._build_historical_comparison(analysis)

            # Generate overall assessment
            overall_assessment = self._generate_overall_assessment(analysis)

            report = IndividualTradeReport(
                trade_id=trade_id,
                report_generated_at=datetime.now(timezone.utc),
                summary=summary,
                cost_analysis=cost_analysis,
                quality_analysis=quality_analysis,
                market_context=market_context,
                historical_comparison=historical_comparison,
                recommendations=analysis.recommendations,
                overall_assessment=overall_assessment,
            )

            logger.info(f"Generated individual report for trade: {trade_id}")
            return report

    def _build_historical_comparison(
        self,
        analysis: PostTradeAnalysisResult,
    ) -> Dict[str, Any]:
        """
        Build historical comparison section

        Args:
            analysis: Current trade analysis

        Returns:
            Dictionary with historical comparisons
        """
        analyzer = self._analyzer_instance

        # Get strategy stats
        strategy_stats = analyzer.get_strategy_stats(analysis.strategy)
        if "error" not in strategy_stats:
            strategy_avg_quality = strategy_stats.get("avg_quality_score", 50)
            vs_strategy = "better" if analysis.execution_quality.quality_score > strategy_avg_quality else "worse"
            diff = analysis.execution_quality.quality_score - strategy_avg_quality
            vs_strategy_str = f"{abs(diff):.0f} pts {vs_strategy} than avg"
        else:
            vs_strategy_str = "Insufficient data"

        # Get symbol stats
        symbol_stats = analyzer.get_symbol_stats(analysis.symbol)
        if "error" not in symbol_stats:
            symbol_avg_quality = symbol_stats.get("avg_quality_score", 50)
            vs_symbol = "better" if analysis.execution_quality.quality_score > symbol_avg_quality else "worse"
            diff = analysis.execution_quality.quality_score - symbol_avg_quality
            vs_symbol_str = f"{abs(diff):.0f} pts {vs_symbol} than avg"
        else:
            vs_symbol_str = "Insufficient data"

        # Calculate percentile rank
        all_scores = []
        for a in analyzer._analyses.values():
            all_scores.append(a.execution_quality.quality_score)

        if len(all_scores) > 1:
            below_count = sum(1 for s in all_scores if s < analysis.execution_quality.quality_score)
            percentile = (below_count / len(all_scores)) * 100
            percentile_str = f"{percentile:.0f}th percentile"
        else:
            percentile_str = "Insufficient data"

        return {
            "vs_strategy_avg": vs_strategy_str,
            "vs_symbol_avg": vs_symbol_str,
            "percentile": percentile_str,
            "strategy_trade_count": strategy_stats.get("trade_count", 0),
            "symbol_trade_count": symbol_stats.get("trade_count", 0),
        }

    def _generate_overall_assessment(
        self,
        analysis: PostTradeAnalysisResult,
    ) -> str:
        """
        Generate overall assessment text

        Args:
            analysis: Trade analysis

        Returns:
            Assessment string
        """
        score = analysis.execution_quality.quality_score
        grade = analysis.execution_quality.quality_grade
        slippage = analysis.slippage.slippage_bps
        cost = analysis.cost_bps

        if grade == ExecutionQualityGrade.EXCELLENT:
            base = "Excellent execution with minimal market impact."
        elif grade == ExecutionQualityGrade.GOOD:
            base = "Good execution with acceptable costs."
        elif grade == ExecutionQualityGrade.FAIR:
            base = "Fair execution with room for improvement."
        elif grade == ExecutionQualityGrade.POOR:
            base = "Poor execution requiring strategy review."
        else:
            base = "Very poor execution requiring immediate attention."

        # Add context
        context_parts = []

        if slippage < 0:
            context_parts.append(f"Achieved {abs(slippage):.1f}bps price improvement.")
        elif slippage > 15:
            context_parts.append(f"High slippage of {slippage:.1f}bps needs investigation.")

        if analysis.classification.liquidity_level.value == "thin":
            context_parts.append("Executed during thin liquidity conditions.")

        if analysis.execution_quality.fill_rate < 100:
            context_parts.append(f"Partial fill of {analysis.execution_quality.fill_rate:.0f}%.")

        return f"{base} {' '.join(context_parts)}".strip()

    # =========================================================================
    # DAILY SUMMARY REPORTS
    # =========================================================================

    def generate_daily_summary(
        self,
        date: Optional[str] = None,
        format: ReportFormat = ReportFormat.JSON,
    ) -> DailySummary:
        """
        Generate daily execution summary

        Args:
            date: Date string (YYYY-MM-DD) or None for today
            format: Output format

        Returns:
            DailySummary object
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        summary = self._analyzer_instance.get_daily_summary(date)
        logger.info(f"Generated daily summary for: {date}")

        return summary

    def generate_multi_day_summary(
        self,
        days: int = 7,
    ) -> Dict[str, DailySummary]:
        """
        Generate summaries for multiple days

        Args:
            days: Number of days to include

        Returns:
            Dictionary mapping dates to summaries
        """
        summaries = {}
        today = datetime.now(timezone.utc).date()
        analyzer = self._analyzer_instance

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            summaries[date] = analyzer.get_daily_summary(date)

        logger.info(f"Generated summaries for {days} days")
        return summaries

    # =========================================================================
    # WEEKLY COMPARISON REPORTS
    # =========================================================================

    def generate_weekly_comparison(
        self,
        week_offset: int = 0,
    ) -> WeeklyComparisonReport:
        """
        Generate weekly comparison report

        Args:
            week_offset: 0 for current week, -1 for last week, etc.

        Returns:
            WeeklyComparisonReport object
        """
        with self._lock:
            analyzer = self._analyzer_instance

            # Calculate week boundaries
            today = datetime.now(timezone.utc).date()
            # Find start of current week (Monday)
            days_since_monday = today.weekday()
            current_week_start = today - timedelta(days=days_since_monday)

            # Apply offset
            target_week_start = current_week_start + timedelta(weeks=week_offset)
            target_week_end = target_week_start + timedelta(days=6)

            # Previous week
            prev_week_start = target_week_start - timedelta(weeks=1)
            prev_week_end = prev_week_start + timedelta(days=6)

            # Collect data for current week
            current_week_analyses = self._get_analyses_for_period(
                target_week_start.strftime("%Y-%m-%d"),
                target_week_end.strftime("%Y-%m-%d"),
            )

            # Collect data for previous week
            prev_week_analyses = self._get_analyses_for_period(
                prev_week_start.strftime("%Y-%m-%d"),
                prev_week_end.strftime("%Y-%m-%d"),
            )

            # Calculate metrics for current week
            current_metrics = self._calculate_period_metrics(current_week_analyses)

            # Calculate metrics for previous week
            prev_metrics = self._calculate_period_metrics(prev_week_analyses) if prev_week_analyses else None

            # Calculate week-over-week changes
            wow_changes = self._calculate_wow_changes(current_metrics, prev_metrics)

            # Determine trends
            trends = self._determine_trends(wow_changes)

            # Get best and worst executions
            best = analyzer.get_best_executions(5)
            worst = analyzer.get_worst_executions(5)

            best_dicts = [
                {
                    "trade_id": a.trade_id,
                    "symbol": a.symbol,
                    "score": a.execution_quality.quality_score,
                    "cost_bps": a.cost_bps,
                }
                for a in best if a.analyzed_at.date() >= target_week_start
            ][:5]

            worst_dicts = [
                {
                    "trade_id": a.trade_id,
                    "symbol": a.symbol,
                    "score": a.execution_quality.quality_score,
                    "cost_bps": a.cost_bps,
                }
                for a in worst if a.analyzed_at.date() >= target_week_start
            ][:5]

            # Strategy comparison
            strategy_comparison = self._build_strategy_comparison(current_week_analyses)

            # Symbol comparison
            symbol_comparison = self._build_symbol_comparison(current_week_analyses)

            # Generate insights
            insights = self._generate_weekly_insights(
                current_metrics, prev_metrics, wow_changes, strategy_comparison
            )

            # Get recommendations
            recommendations = [
                r.recommendation
                for r in analyzer.get_improvement_recommendations()[:5]
            ]

            report = WeeklyComparisonReport(
                week_start=target_week_start.strftime("%Y-%m-%d"),
                week_end=target_week_end.strftime("%Y-%m-%d"),
                report_generated_at=datetime.now(timezone.utc),
                current_week=current_metrics,
                previous_week=prev_metrics,
                wow_changes=wow_changes,
                trends=trends,
                best_executions=best_dicts,
                worst_executions=worst_dicts,
                strategy_comparison=strategy_comparison,
                symbol_comparison=symbol_comparison,
                insights=insights,
                recommendations=recommendations,
            )

            logger.info(
                f"Generated weekly comparison: "
                f"{target_week_start} to {target_week_end}"
            )

            return report

    def _get_analyses_for_period(
        self,
        start_date: str,
        end_date: str,
    ) -> List[PostTradeAnalysisResult]:
        """
        Get all analyses within a date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            List of analyses in the period
        """
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        analyzer = self._analyzer_instance

        return [
            a for a in analyzer._analyses.values()
            if start <= a.analyzed_at.date() <= end
        ]

    def _calculate_period_metrics(
        self,
        analyses: List[PostTradeAnalysisResult],
    ) -> Dict[str, Any]:
        """
        Calculate aggregate metrics for a period

        Args:
            analyses: List of analyses

        Returns:
            Dictionary of metrics
        """
        if not analyses:
            return {
                "trade_count": 0,
                "total_volume": 0.0,
                "avg_slippage_bps": 0.0,
                "avg_cost_bps": 0.0,
                "avg_quality_score": 0.0,
                "total_fees": 0.0,
                "total_slippage_cost": 0.0,
            }

        return {
            "trade_count": len(analyses),
            "total_volume": sum(a.size * a.execution_price for a in analyses),
            "avg_slippage_bps": statistics.mean(a.slippage.slippage_bps for a in analyses),
            "avg_cost_bps": statistics.mean(a.cost_bps for a in analyses),
            "avg_quality_score": statistics.mean(a.execution_quality.quality_score for a in analyses),
            "total_fees": sum(a.fees for a in analyses),
            "total_slippage_cost": sum(a.slippage.total_slippage for a in analyses),
            "quality_distribution": {
                grade.value: sum(
                    1 for a in analyses
                    if a.execution_quality.quality_grade == grade
                )
                for grade in ExecutionQualityGrade
            },
        }

    def _calculate_wow_changes(
        self,
        current: Dict[str, Any],
        previous: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Calculate week-over-week changes

        Args:
            current: Current week metrics
            previous: Previous week metrics

        Returns:
            Dictionary of changes
        """
        if not previous or previous.get("trade_count", 0) == 0:
            return {
                "trade_count_change": current.get("trade_count", 0),
                "trade_count_change_pct": 0.0,
                "slippage_change_bps": 0.0,
                "cost_change_bps": 0.0,
                "quality_change": 0.0,
            }

        def pct_change(curr, prev):
            if prev == 0:
                return 100 if curr > 0 else 0
            return ((curr - prev) / prev) * 100

        return {
            "trade_count_change": current["trade_count"] - previous["trade_count"],
            "trade_count_change_pct": pct_change(
                current["trade_count"], previous["trade_count"]
            ),
            "slippage_change_bps": current["avg_slippage_bps"] - previous["avg_slippage_bps"],
            "cost_change_bps": current["avg_cost_bps"] - previous["avg_cost_bps"],
            "quality_change": current["avg_quality_score"] - previous["avg_quality_score"],
        }

    def _determine_trends(
        self,
        changes: Dict[str, Any],
    ) -> Dict[str, TrendDirection]:
        """
        Determine trend direction for key metrics

        Args:
            changes: Week-over-week changes

        Returns:
            Dictionary mapping metrics to trend direction
        """
        trends = {}

        # Slippage trend (lower is better)
        slip_change = changes.get("slippage_change_bps", 0)
        if slip_change < -1:
            trends["slippage"] = TrendDirection.IMPROVING
        elif slip_change > 1:
            trends["slippage"] = TrendDirection.DECLINING
        else:
            trends["slippage"] = TrendDirection.STABLE

        # Cost trend (lower is better)
        cost_change = changes.get("cost_change_bps", 0)
        if cost_change < -1:
            trends["cost"] = TrendDirection.IMPROVING
        elif cost_change > 1:
            trends["cost"] = TrendDirection.DECLINING
        else:
            trends["cost"] = TrendDirection.STABLE

        # Quality trend (higher is better)
        qual_change = changes.get("quality_change", 0)
        if qual_change > 2:
            trends["quality"] = TrendDirection.IMPROVING
        elif qual_change < -2:
            trends["quality"] = TrendDirection.DECLINING
        else:
            trends["quality"] = TrendDirection.STABLE

        return trends

    def _build_strategy_comparison(
        self,
        analyses: List[PostTradeAnalysisResult],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build strategy-by-strategy comparison

        Args:
            analyses: List of analyses

        Returns:
            Dictionary of strategy metrics
        """
        if not analyses:
            return {}

        by_strategy = defaultdict(list)
        for a in analyses:
            by_strategy[a.strategy].append(a)

        comparison = {}
        for strategy, trades in by_strategy.items():
            comparison[strategy] = {
                "trade_count": len(trades),
                "avg_slippage_bps": statistics.mean(t.slippage.slippage_bps for t in trades),
                "avg_cost_bps": statistics.mean(t.cost_bps for t in trades),
                "avg_quality_score": statistics.mean(
                    t.execution_quality.quality_score for t in trades
                ),
                "total_volume": sum(t.size * t.execution_price for t in trades),
            }

        return comparison

    def _build_symbol_comparison(
        self,
        analyses: List[PostTradeAnalysisResult],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Build symbol-by-symbol comparison

        Args:
            analyses: List of analyses

        Returns:
            Dictionary of symbol metrics
        """
        if not analyses:
            return {}

        by_symbol = defaultdict(list)
        for a in analyses:
            by_symbol[a.symbol].append(a)

        comparison = {}
        for symbol, trades in by_symbol.items():
            comparison[symbol] = {
                "trade_count": len(trades),
                "avg_slippage_bps": statistics.mean(t.slippage.slippage_bps for t in trades),
                "avg_cost_bps": statistics.mean(t.cost_bps for t in trades),
                "avg_quality_score": statistics.mean(
                    t.execution_quality.quality_score for t in trades
                ),
                "total_volume": sum(t.size * t.execution_price for t in trades),
            }

        return comparison

    def _generate_weekly_insights(
        self,
        current: Dict[str, Any],
        previous: Optional[Dict[str, Any]],
        changes: Dict[str, Any],
        by_strategy: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        """
        Generate insights from weekly data

        Args:
            current: Current week metrics
            previous: Previous week metrics
            changes: Week-over-week changes
            by_strategy: Strategy breakdown

        Returns:
            List of insight strings
        """
        insights = []

        # Trade volume insight
        trade_count = current.get("trade_count", 0)
        if trade_count > 0:
            insights.append(
                f"Executed {trade_count} trades this week with "
                f"${current.get('total_volume', 0):,.0f} total volume."
            )

        # Week-over-week comparison
        if previous and previous.get("trade_count", 0) > 0:
            slip_change = changes.get("slippage_change_bps", 0)
            qual_change = changes.get("quality_change", 0)

            if slip_change < -2:
                insights.append(
                    f"Slippage improved by {abs(slip_change):.1f}bps compared to last week."
                )
            elif slip_change > 2:
                insights.append(
                    f"Slippage increased by {slip_change:.1f}bps - investigate causes."
                )

            if qual_change > 3:
                insights.append(
                    f"Execution quality improved by {qual_change:.1f} points."
                )
            elif qual_change < -3:
                insights.append(
                    f"Execution quality declined by {abs(qual_change):.1f} points."
                )

        # Strategy insights
        if by_strategy:
            best_strategy = max(
                by_strategy.items(),
                key=lambda x: x[1]["avg_quality_score"]
            )
            worst_strategy = min(
                by_strategy.items(),
                key=lambda x: x[1]["avg_quality_score"]
            )

            if best_strategy[0] != worst_strategy[0]:
                diff = best_strategy[1]["avg_quality_score"] - worst_strategy[1]["avg_quality_score"]
                if diff > 10:
                    insights.append(
                        f"'{best_strategy[0]}' outperforms '{worst_strategy[0]}' "
                        f"by {diff:.0f} quality points."
                    )

        # Cost efficiency insight
        total_cost = current.get("total_fees", 0) + current.get("total_slippage_cost", 0)
        if current.get("total_volume", 0) > 0:
            cost_pct = (total_cost / current["total_volume"]) * 100
            if cost_pct > 0.1:
                insights.append(
                    f"Total execution costs represent {cost_pct:.3f}% of trading volume."
                )

        return insights

    # =========================================================================
    # BEST/WORST ANALYSIS
    # =========================================================================

    def get_best_executions_report(
        self,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Generate report of best executions

        Args:
            limit: Maximum number of results

        Returns:
            Report dictionary
        """
        best = self._analyzer_instance.get_best_executions(limit)

        return {
            "report_type": "best_executions",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(best),
            "executions": [
                {
                    "trade_id": a.trade_id,
                    "symbol": a.symbol,
                    "side": a.side,
                    "strategy": a.strategy,
                    "quality_score": a.execution_quality.quality_score,
                    "quality_grade": a.execution_quality.quality_grade.value,
                    "slippage_bps": a.slippage.slippage_bps,
                    "cost_bps": a.cost_bps,
                    "analyzed_at": a.analyzed_at.isoformat(),
                    "success_factors": self._identify_success_factors(a),
                }
                for a in best
            ],
            "common_patterns": self._identify_common_patterns(best, "success"),
        }

    def get_worst_executions_report(
        self,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Generate report of worst executions

        Args:
            limit: Maximum number of results

        Returns:
            Report dictionary
        """
        worst = self._analyzer_instance.get_worst_executions(limit)

        return {
            "report_type": "worst_executions",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(worst),
            "executions": [
                {
                    "trade_id": a.trade_id,
                    "symbol": a.symbol,
                    "side": a.side,
                    "strategy": a.strategy,
                    "quality_score": a.execution_quality.quality_score,
                    "quality_grade": a.execution_quality.quality_grade.value,
                    "slippage_bps": a.slippage.slippage_bps,
                    "cost_bps": a.cost_bps,
                    "analyzed_at": a.analyzed_at.isoformat(),
                    "problem_factors": self._identify_problem_factors(a),
                }
                for a in worst
            ],
            "common_patterns": self._identify_common_patterns(worst, "problem"),
        }

    def _identify_success_factors(
        self,
        analysis: PostTradeAnalysisResult,
    ) -> List[str]:
        """
        Identify what made this execution successful

        Args:
            analysis: Trade analysis

        Returns:
            List of success factors
        """
        factors = []

        if analysis.slippage.slippage_bps < 0:
            factors.append("Achieved price improvement")

        if analysis.classification.liquidity_level.value == "deep":
            factors.append("Executed during deep liquidity")

        if analysis.classification.execution_style.value == "passive":
            if analysis.execution_quality.spread_capture_rate > 50:
                factors.append("Effective spread capture with limit order")

        if analysis.execution_quality.time_to_completion < 5:
            factors.append("Fast execution")

        if analysis.execution_quality.fill_rate == 100:
            factors.append("Complete fill")

        return factors if factors else ["Good overall execution"]

    def _identify_problem_factors(
        self,
        analysis: PostTradeAnalysisResult,
    ) -> List[str]:
        """
        Identify what caused poor execution

        Args:
            analysis: Trade analysis

        Returns:
            List of problem factors
        """
        factors = []

        if analysis.slippage.slippage_bps > 15:
            factors.append(f"High slippage: {analysis.slippage.slippage_bps:.1f}bps")

        if analysis.slippage.market_impact > analysis.slippage.spread_cost:
            factors.append("High market impact - order too large")

        if analysis.classification.liquidity_level.value == "thin":
            factors.append("Thin liquidity conditions")

        if analysis.execution_quality.fill_rate < 100:
            factors.append(f"Partial fill: {analysis.execution_quality.fill_rate:.0f}%")

        if analysis.execution_quality.time_to_completion > 60:
            factors.append("Slow execution")

        return factors if factors else ["Multiple contributing factors"]

    def _identify_common_patterns(
        self,
        analyses: List[PostTradeAnalysisResult],
        pattern_type: str,
    ) -> List[str]:
        """
        Identify common patterns in a set of analyses

        Args:
            analyses: List of analyses
            pattern_type: "success" or "problem"

        Returns:
            List of common patterns
        """
        if not analyses:
            return []

        patterns = []

        # Check session concentration
        sessions = [a.classification.trading_session for a in analyses]
        most_common_session = max(set(sessions), key=sessions.count)
        session_pct = sessions.count(most_common_session) / len(sessions) * 100

        if session_pct > 60:
            if pattern_type == "success":
                patterns.append(
                    f"{session_pct:.0f}% of best executions during {most_common_session.value} session"
                )
            else:
                patterns.append(
                    f"{session_pct:.0f}% of poor executions during {most_common_session.value} session"
                )

        # Check execution style
        styles = [a.classification.execution_style for a in analyses]
        most_common_style = max(set(styles), key=styles.count)
        style_pct = styles.count(most_common_style) / len(styles) * 100

        if style_pct > 60:
            patterns.append(
                f"{style_pct:.0f}% used {most_common_style.value} execution"
            )

        # Check market condition
        conditions = [a.classification.market_condition for a in analyses]
        most_common_condition = max(set(conditions), key=conditions.count)
        condition_pct = conditions.count(most_common_condition) / len(conditions) * 100

        if condition_pct > 50:
            patterns.append(
                f"{condition_pct:.0f}% occurred in {most_common_condition.value} markets"
            )

        return patterns


# =============================================================================
# GLOBAL INSTANCE MANAGEMENT (THREAD-SAFE SINGLETON)
# =============================================================================

_trade_report_generator: Optional[TradeReportGenerator] = None
_report_instance_lock: threading.Lock = threading.Lock()


def get_trade_report_generator() -> TradeReportGenerator:
    """
    Get or create the global TradeReportGenerator instance

    Thread-safe singleton pattern ensures only one instance exists.
    The generator lazily accesses the global PostTradeAnalyzer singleton,
    ensuring it always uses the current analyzer instance.

    Returns:
        Global TradeReportGenerator instance

    Example:
        >>> generator = get_trade_report_generator()
        >>> report = generator.generate_individual_report("tr_001")
    """
    global _trade_report_generator

    with _report_instance_lock:
        if _trade_report_generator is None:
            # Create with analyzer=None to use lazy lookup via property
            _trade_report_generator = TradeReportGenerator(analyzer=None)
            logger.info("Created new TradeReportGenerator instance")

        return _trade_report_generator


def reset_trade_report_generator() -> None:
    """
    Reset the global TradeReportGenerator instance

    Useful for testing or starting fresh.
    """
    global _trade_report_generator

    with _report_instance_lock:
        _trade_report_generator = None
        logger.info("Global TradeReportGenerator reset")
