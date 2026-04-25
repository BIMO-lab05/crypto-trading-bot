"""
Attribution Analysis API Handlers
Purpose: FastAPI endpoint handlers for P&L attribution analysis

This module provides HTTP endpoints for:
- GET /api/v1/analytics/attribution/by-strategy
- GET /api/v1/analytics/attribution/by-symbol
- GET /api/v1/analytics/attribution/summary
- GET /api/v1/analytics/attribution/trends
- GET /api/v1/analytics/attribution/daily-report

Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, HTTPException

from app.analytics import (
    get_attribution_analyzer,
    AttributionDimension,
    TradePeriod,
    AttributionMetrics,
    AttributionResult,
    AttributionSummary,
    TrendAnalysis,
    PerformanceDecomposition,
)
from app.analytics.models import (
    AttributionByStrategyResponse,
    AttributionBySymbolResponse,
    AttributionSummaryResponse,
    AttributionTrendsResponse,
    AttributionTrendsRequest,
    AttributionMetricsResponse,
    AttributionResultResponse,
    TrendDataResponse,
    DailyAttributionReportResponse,
    PerformanceDecompositionResponse,
    AttributionErrorResponse,
    TimePeriod,
    DimensionType,
)

# Configure logging
logger = logging.getLogger(__name__)

# Create router with prefix and tags
router = APIRouter(
    prefix="/api/v1/analytics/attribution",
    tags=["Attribution Analysis"],
    responses={
        500: {"model": AttributionErrorResponse, "description": "Internal Server Error"}
    }
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _metrics_to_response(metrics: AttributionMetrics) -> AttributionMetricsResponse:
    """Convert AttributionMetrics to response model"""
    return AttributionMetricsResponse(
        total_pnl=round(metrics.total_pnl, 2),
        win_rate=round(metrics.win_rate * 100, 2),
        sharpe_ratio=round(metrics.sharpe_ratio, 3),
        max_drawdown=round(metrics.max_drawdown * 100, 2),
        avg_win=round(metrics.avg_win, 2),
        avg_loss=round(metrics.avg_loss, 2),
        profit_factor=round(metrics.profit_factor, 3),
        trades_count=metrics.trades_count,
        sortino_ratio=round(metrics.sortino_ratio, 3),
        calmar_ratio=round(metrics.calmar_ratio, 3),
    )


def _attribution_to_response(result: AttributionResult) -> AttributionResultResponse:
    """Convert AttributionResult to response model"""
    return AttributionResultResponse(
        dimension=result.dimension.value,
        value=result.value,
        metrics=_metrics_to_response(result.metrics),
        contribution_pct=round(result.contribution_pct, 2),
        trades_count=len(result.trades),
    )


def _trend_to_response(trend: TrendAnalysis) -> TrendDataResponse:
    """Convert TrendAnalysis to response model"""
    return TrendDataResponse(
        dimension=trend.dimension.value,
        value=trend.value,
        periods=trend.periods,
        pnl_trend=[round(p, 2) for p in trend.pnl_trend],
        win_rate_trend=[round(w * 100, 2) for w in trend.win_rate_trend],
        trades_count_trend=trend.trades_count_trend,
        moving_avg_pnl=[round(m, 2) for m in trend.moving_avg_pnl],
        trend_direction=trend.trend_direction,
    )


def _parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse datetime string to datetime object"""
    if not dt_str:
        return None
    try:
        # Try ISO format first
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        # Try common formats
        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        raise ValueError(f"Invalid datetime format: {dt_str}")


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get(
    "/by-strategy",
    response_model=AttributionByStrategyResponse,
    summary="Get P&L Attribution by Strategy",
    description="""
    Get P&L attribution breakdown by trading strategy.

    Returns performance metrics for each strategy including:
    - Total P&L
    - Win rate
    - Sharpe ratio
    - Profit factor
    - Contribution percentage to total P&L

    Strategies include: Pairs Trading, Funding Rate Arb, Triangular Arb,
    Consensus, SQZMOM, and custom strategies.
    """
)
async def get_attribution_by_strategy(
    start_time: Optional[str] = Query(
        default=None,
        description="Start of analysis period (ISO format or YYYY-MM-DD)"
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="End of analysis period (ISO format or YYYY-MM-DD)"
    ),
) -> AttributionByStrategyResponse:
    """
    Get P&L attribution breakdown by trading strategy.

    This endpoint analyzes all closed trades and groups them by strategy
    to show which strategies are generating profits or losses.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Parse time parameters
        start_dt = _parse_datetime(start_time)
        end_dt = _parse_datetime(end_time)

        # Get attribution by strategy
        attributions = analyzer.get_attribution_by_strategy(
            start_time=start_dt,
            end_time=end_dt,
        )

        # Convert to response format
        attribution_responses = [
            _attribution_to_response(attr) for attr in attributions
        ]

        # Determine period boundaries from trades if not specified
        if attributions:
            all_trades = []
            for attr in attributions:
                all_trades.extend(attr.trades)
            if all_trades:
                actual_start = min(t.entry_time for t in all_trades)
                actual_end = max(t.exit_time for t in all_trades)
            else:
                actual_start = start_dt
                actual_end = end_dt
        else:
            actual_start = start_dt
            actual_end = end_dt

        return AttributionByStrategyResponse(
            success=True,
            attributions=attribution_responses,
            total_strategies=len(attributions),
            period_start=actual_start.isoformat() if actual_start else None,
            period_end=actual_end.isoformat() if actual_end else None,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting attribution by strategy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/by-symbol",
    response_model=AttributionBySymbolResponse,
    summary="Get P&L Attribution by Symbol",
    description="""
    Get P&L attribution breakdown by trading symbol/pair.

    Returns performance metrics for each symbol including:
    - Total P&L
    - Win rate
    - Sharpe ratio
    - Profit factor
    - Contribution percentage to total P&L

    Symbols include: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT, etc.
    """
)
async def get_attribution_by_symbol(
    start_time: Optional[str] = Query(
        default=None,
        description="Start of analysis period (ISO format or YYYY-MM-DD)"
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="End of analysis period (ISO format or YYYY-MM-DD)"
    ),
) -> AttributionBySymbolResponse:
    """
    Get P&L attribution breakdown by trading symbol.

    This endpoint analyzes all closed trades and groups them by symbol
    to show which trading pairs are performing best.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Parse time parameters
        start_dt = _parse_datetime(start_time)
        end_dt = _parse_datetime(end_time)

        # Get attribution by symbol
        attributions = analyzer.get_attribution_by_symbol(
            start_time=start_dt,
            end_time=end_dt,
        )

        # Convert to response format
        attribution_responses = [
            _attribution_to_response(attr) for attr in attributions
        ]

        # Determine period boundaries from trades
        if attributions:
            all_trades = []
            for attr in attributions:
                all_trades.extend(attr.trades)
            if all_trades:
                actual_start = min(t.entry_time for t in all_trades)
                actual_end = max(t.exit_time for t in all_trades)
            else:
                actual_start = start_dt
                actual_end = end_dt
        else:
            actual_start = start_dt
            actual_end = end_dt

        return AttributionBySymbolResponse(
            success=True,
            attributions=attribution_responses,
            total_symbols=len(attributions),
            period_start=actual_start.isoformat() if actual_start else None,
            period_end=actual_end.isoformat() if actual_end else None,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting attribution by symbol: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/summary",
    response_model=AttributionSummaryResponse,
    summary="Get Complete Attribution Summary",
    description="""
    Get comprehensive P&L attribution summary across all dimensions.

    Returns:
    - Overall portfolio performance metrics
    - Attribution breakdown by strategy
    - Attribution breakdown by symbol
    - Attribution breakdown by trade direction (long/short)
    - Attribution breakdown by market condition
    - Performance decomposition (alpha, beta, residual)

    This is the most comprehensive endpoint for understanding
    where your profits and losses are coming from.
    """
)
async def get_attribution_summary(
    start_time: Optional[str] = Query(
        default=None,
        description="Start of analysis period (ISO format or YYYY-MM-DD)"
    ),
    end_time: Optional[str] = Query(
        default=None,
        description="End of analysis period (ISO format or YYYY-MM-DD)"
    ),
    include_decomposition: bool = Query(
        default=True,
        description="Include performance decomposition (alpha, beta, residual)"
    ),
) -> AttributionSummaryResponse:
    """
    Get complete attribution summary across all dimensions.

    This endpoint provides a comprehensive view of performance attribution
    including breakdowns by strategy, symbol, direction, and market condition.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Parse time parameters
        start_dt = _parse_datetime(start_time)
        end_dt = _parse_datetime(end_time)

        # Get attribution summary
        summary = analyzer.get_attribution_summary(
            start_time=start_dt,
            end_time=end_dt,
        )

        # Get performance decomposition if requested
        decomposition = []
        if include_decomposition:
            decomposition_results = analyzer.get_performance_decomposition()
            decomposition = [d.to_dict() for d in decomposition_results]

        return AttributionSummaryResponse(
            success=True,
            overall_metrics=_metrics_to_response(summary.overall_metrics),
            by_strategy=[_attribution_to_response(r) for r in summary.by_strategy],
            by_symbol=[_attribution_to_response(r) for r in summary.by_symbol],
            by_direction=[_attribution_to_response(r) for r in summary.by_direction],
            by_market_condition=[_attribution_to_response(r) for r in summary.by_market_condition],
            performance_decomposition=decomposition,
            period_start=summary.period_start.isoformat() if summary.period_start else None,
            period_end=summary.period_end.isoformat() if summary.period_end else None,
            generated_at=summary.generated_at.isoformat(),
            current_equity=analyzer._current_equity,
            peak_equity=analyzer._peak_equity,
        )

    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting attribution summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/trends",
    response_model=AttributionTrendsResponse,
    summary="Get Attribution Trends Over Time",
    description="""
    Analyze attribution trends over time periods.

    Track how strategies, symbols, or other dimensions perform over time:
    - P&L trend over periods
    - Win rate trend
    - Trade count trend
    - Moving average P&L
    - Overall trend direction (up, down, flat)

    Use this to identify improving or declining strategies.
    """
)
async def get_attribution_trends(
    period: TimePeriod = Query(
        default=TimePeriod.DAILY,
        description="Time period granularity (hourly, daily, weekly, monthly)"
    ),
    lookback_days: int = Query(
        default=7,
        ge=1,
        le=365,
        description="Number of days to analyze"
    ),
    dimension: DimensionType = Query(
        default=DimensionType.STRATEGY,
        description="Attribution dimension to analyze"
    ),
) -> AttributionTrendsResponse:
    """
    Analyze attribution trends over time periods.

    This endpoint tracks how different strategies or symbols perform
    over time, helping identify trends and patterns.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Map API enums to internal enums
        period_map = {
            TimePeriod.HOURLY: TradePeriod.HOURLY,
            TimePeriod.DAILY: TradePeriod.DAILY,
            TimePeriod.WEEKLY: TradePeriod.WEEKLY,
            TimePeriod.MONTHLY: TradePeriod.MONTHLY,
        }
        dimension_map = {
            DimensionType.STRATEGY: AttributionDimension.STRATEGY,
            DimensionType.SYMBOL: AttributionDimension.SYMBOL,
            DimensionType.DIRECTION: AttributionDimension.DIRECTION,
            DimensionType.MARKET_CONDITION: AttributionDimension.MARKET_CONDITION,
        }

        internal_period = period_map[period]
        internal_dimension = dimension_map[dimension]

        # Get trends
        trends = analyzer.get_attribution_trends(
            period=internal_period,
            lookback_days=lookback_days,
            dimension=internal_dimension,
        )

        # Convert to response format
        trend_responses = [_trend_to_response(t) for t in trends]

        return AttributionTrendsResponse(
            success=True,
            trends=trend_responses,
            period=period.value,
            lookback_days=lookback_days,
            dimension=dimension.value,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    except ValueError as e:
        logger.error(f"Invalid parameter: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting attribution trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/daily-report",
    response_model=DailyAttributionReportResponse,
    summary="Get Daily Attribution Report",
    description="""
    Generate comprehensive daily attribution report.

    Includes:
    - Today's trade count and P&L
    - Win rate for the day
    - Top performing strategies
    - Top performing symbols
    - Current equity and drawdown

    Useful for daily performance reviews.
    """
)
async def get_daily_report() -> DailyAttributionReportResponse:
    """
    Generate daily attribution report.

    This endpoint provides a comprehensive daily summary of
    trading performance and attribution.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Generate daily report
        report = analyzer.generate_daily_report()

        # Convert to response format
        return DailyAttributionReportResponse(
            success=True,
            date=report["date"],
            generated_at=report["generated_at"],
            trades_today=report["trades_today"],
            overall_pnl=round(report["overall_pnl"], 2),
            win_rate=round(report["win_rate"] * 100, 2),
            top_strategies=[
                AttributionResultResponse(
                    dimension=s["dimension"],
                    value=s["value"],
                    metrics=AttributionMetricsResponse(**s["metrics"]),
                    contribution_pct=s["contribution_pct"],
                    trades_count=s["trades_count"],
                )
                for s in report.get("top_strategies", [])
            ],
            top_symbols=[
                AttributionResultResponse(
                    dimension=s["dimension"],
                    value=s["value"],
                    metrics=AttributionMetricsResponse(**s["metrics"]),
                    contribution_pct=s["contribution_pct"],
                    trades_count=s["trades_count"],
                )
                for s in report.get("top_symbols", [])
            ],
            current_equity=round(report["current_equity"], 2),
            peak_equity=round(report["peak_equity"], 2),
            current_drawdown=round(report["current_drawdown"] * 100, 2),
        )

    except Exception as e:
        logger.error(f"Error generating daily report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get(
    "/performance-decomposition",
    response_model=List[PerformanceDecompositionResponse],
    summary="Get Performance Decomposition",
    description="""
    Decompose performance into Alpha, Beta, and Residual components.

    - Alpha: Strategy-specific returns (skill component)
    - Beta: Market correlation (systematic risk)
    - Residual: Unexplained variance (luck/noise)

    High alpha indicates skilled strategy execution.
    Beta shows how correlated the strategy is with market movements.
    """
)
async def get_performance_decomposition() -> List[PerformanceDecompositionResponse]:
    """
    Get performance decomposition for all strategies.

    This endpoint decomposes strategy returns into alpha, beta,
    and residual components to separate skill from luck.
    """
    try:
        # Get analyzer instance
        analyzer = get_attribution_analyzer()

        # Get decomposition
        decompositions = analyzer.get_performance_decomposition()

        # Convert to response format
        return [
            PerformanceDecompositionResponse(
                strategy=d.strategy,
                alpha=round(d.alpha, 4),
                beta=round(d.beta, 4),
                residual=round(d.residual, 4),
                r_squared=round(d.r_squared, 4),
                total_return=round(d.total_return * 100, 2),
                benchmark_return=round(d.benchmark_return * 100, 2),
                information_ratio=round(d.information_ratio, 3),
            )
            for d in decompositions
        ]

    except Exception as e:
        logger.error(f"Error getting performance decomposition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# =============================================================================
# STANDALONE HANDLER FUNCTIONS (for main.py integration)
# =============================================================================

# These functions can be imported directly into main.py if not using router

async def attribution_by_strategy_handler(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> AttributionByStrategyResponse:
    """Standalone handler for attribution by strategy"""
    return await get_attribution_by_strategy(start_time, end_time)


async def attribution_by_symbol_handler(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> AttributionBySymbolResponse:
    """Standalone handler for attribution by symbol"""
    return await get_attribution_by_symbol(start_time, end_time)


async def attribution_summary_handler(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    include_decomposition: bool = True,
) -> AttributionSummaryResponse:
    """Standalone handler for attribution summary"""
    return await get_attribution_summary(start_time, end_time, include_decomposition)


async def attribution_trends_handler(
    period: str = "daily",
    lookback_days: int = 7,
    dimension: str = "strategy",
) -> AttributionTrendsResponse:
    """Standalone handler for attribution trends"""
    return await get_attribution_trends(
        TimePeriod(period),
        lookback_days,
        DimensionType(dimension),
    )
