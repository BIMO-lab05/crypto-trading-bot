"""
Post-Trade Analysis API Router (Phase 4.3)
Purpose: FastAPI router providing 7 endpoints for post-trade analysis

Endpoints:
1. GET /api/v1/analytics/post-trade/{trade_id} - Individual trade analysis
2. GET /api/v1/analytics/post-trade/daily-summary - Daily execution report
3. GET /api/v1/analytics/post-trade/worst-executions?limit=10 - Identify issues
4. GET /api/v1/analytics/post-trade/best-executions?limit=10 - Success patterns
5. GET /api/v1/analytics/post-trade/by-strategy/{strategy} - Strategy analysis
6. GET /api/v1/analytics/post-trade/by-symbol/{symbol} - Symbol analysis
7. GET /api/v1/analytics/post-trade/improvement-opportunities - Recommendations

Author: Backend Developer Agent
Date: 2025-12-12
Version: 1.0.0
"""

import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Path, Body

from app.analytics import (
    # Core classes
    get_post_trade_analyzer,
    get_trade_report_generator,
    TradeExecutionData,
    PostTradeAnalysisResult,
    # API Models
    PostTradeAnalysisRequest,
    TradeExecutionReport,
    SlippageBreakdownResponse,
    ExecutionQualityResponse,
    TradeClassificationResponse,
    DailySummaryResponse,
    ImprovementRecommendationResponse,
    BestWorstExecutionsResponse,
    StrategyAnalysisResponse,
    SymbolAnalysisResponse,
    WeeklyComparisonResponse,
    PostTradeAnalysisSummaryResponse,
    QualityGradeEnum,
)

# Configure logger for this router
logger = logging.getLogger(__name__)

# Create APIRouter instance with prefix and tags
router = APIRouter(
    prefix="/api/v1/analytics/post-trade",
    tags=["Post-Trade Analysis"],
    responses={
        404: {"description": "Trade not found"},
        500: {"description": "Internal server error"},
    },
)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _convert_analysis_to_response(analysis: PostTradeAnalysisResult) -> TradeExecutionReport:
    """
    Convert internal PostTradeAnalysisResult to API TradeExecutionReport

    Args:
        analysis: Internal analysis result

    Returns:
        API response model
    """
    return TradeExecutionReport(
        trade_id=analysis.trade_id,
        symbol=analysis.symbol,
        side=analysis.side,
        size=analysis.size,
        expected_price=analysis.expected_price,
        execution_price=analysis.execution_price,
        slippage=SlippageBreakdownResponse(
            market_impact=analysis.slippage.market_impact,
            spread_cost=analysis.slippage.spread_cost,
            timing_cost=analysis.slippage.timing_cost,
            total_slippage=analysis.slippage.total_slippage,
            slippage_bps=analysis.slippage.slippage_bps,
        ),
        fees=analysis.fees,
        total_cost=analysis.total_cost,
        cost_bps=analysis.cost_bps,
        execution_quality=ExecutionQualityResponse(
            implementation_shortfall=analysis.execution_quality.implementation_shortfall,
            implementation_shortfall_bps=analysis.execution_quality.implementation_shortfall_bps,
            price_improvement=analysis.execution_quality.price_improvement,
            price_improvement_bps=analysis.execution_quality.price_improvement_bps,
            fill_rate=analysis.execution_quality.fill_rate,
            time_to_completion=analysis.execution_quality.time_to_completion,
            spread_capture_rate=analysis.execution_quality.spread_capture_rate,
            benchmark_comparisons=analysis.execution_quality.benchmark_comparisons,
            quality_score=analysis.execution_quality.quality_score,
            quality_grade=QualityGradeEnum(analysis.execution_quality.quality_grade.value),
        ),
        classification=TradeClassificationResponse(
            execution_style=analysis.classification.execution_style.value,
            market_condition=analysis.classification.market_condition.value,
            liquidity_level=analysis.classification.liquidity_level.value,
            trading_session=analysis.classification.trading_session.value,
            order_urgency=analysis.classification.order_urgency,
        ),
        recommendations=analysis.recommendations,
        analyzed_at=analysis.analyzed_at,
        strategy=analysis.strategy,
    )


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get(
    "/summary",
    response_model=PostTradeAnalysisSummaryResponse,
    summary="Get Post-Trade Analysis Summary",
    description="Get overall summary of all post-trade analyses including averages and distributions.",
)
async def get_post_trade_summary():
    """
    Get overall summary of all post-trade analyses

    Returns summary statistics including:
    - Total number of analyses
    - Average slippage and cost in basis points
    - Average quality score
    - Quality grade distribution
    - Total fees and slippage costs
    """
    try:
        analyzer = get_post_trade_analyzer()
        summary = analyzer.get_summary()

        return PostTradeAnalysisSummaryResponse(**summary)

    except Exception as e:
        logger.error(f"Error getting post-trade summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get post-trade summary: {str(e)}"
        )


@router.post(
    "/analyze",
    response_model=TradeExecutionReport,
    summary="Analyze a Trade Execution",
    description="Submit a trade for post-trade analysis. Returns comprehensive cost and quality analysis.",
)
async def analyze_trade(
    request: PostTradeAnalysisRequest = Body(..., description="Trade execution data to analyze"),
):
    """
    Analyze a single trade execution

    Analyzes the provided trade and returns:
    - Slippage breakdown (market impact, spread, timing)
    - Execution quality metrics
    - Trade classification
    - Improvement recommendations
    """
    try:
        analyzer = get_post_trade_analyzer()

        # Convert request to internal data model
        trade_data = TradeExecutionData(
            trade_id=request.trade_id,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            expected_price=request.expected_price,
            execution_price=request.execution_price,
            fees=request.fees,
            order_type=request.order_type,
            decision_timestamp=request.decision_timestamp,
            execution_timestamp=request.execution_timestamp,
            strategy=request.strategy,
            benchmark_prices=request.benchmark_prices or {},
            market_data=request.market_data or {},
        )

        # Analyze the trade
        result = analyzer.analyze_trade(trade_data)

        # Convert to response
        return _convert_analysis_to_response(result)

    except Exception as e:
        logger.error(f"Error analyzing trade {request.trade_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze trade: {str(e)}"
        )


@router.get(
    "/{trade_id}",
    response_model=TradeExecutionReport,
    summary="Get Individual Trade Analysis",
    description="Retrieve the post-trade analysis for a specific trade by ID.",
)
async def get_trade_analysis(
    trade_id: str = Path(..., description="Unique trade identifier"),
):
    """
    Get post-trade analysis for a specific trade

    Returns comprehensive analysis including:
    - Cost breakdown
    - Execution quality metrics
    - Trade classification
    - Recommendations
    """
    try:
        analyzer = get_post_trade_analyzer()
        analysis = analyzer.get_analysis(trade_id)

        if analysis is None:
            raise HTTPException(
                status_code=404,
                detail=f"No analysis found for trade: {trade_id}"
            )

        return _convert_analysis_to_response(analysis)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trade analysis for {trade_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get trade analysis: {str(e)}"
        )


@router.get(
    "/daily-summary",
    response_model=DailySummaryResponse,
    summary="Get Daily Execution Summary",
    description="Get aggregated execution summary for a specific date.",
)
async def get_daily_summary(
    date: Optional[str] = Query(
        None,
        description="Date in YYYY-MM-DD format (default: today)",
        regex=r"^\d{4}-\d{2}-\d{2}$",
    ),
):
    """
    Get daily execution summary

    Returns aggregated metrics for the specified date:
    - Trade count and volume
    - Average slippage and costs
    - Best/worst executions
    - Breakdown by strategy, symbol, session
    - Daily recommendations
    """
    try:
        report_generator = get_trade_report_generator()

        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        summary = report_generator.generate_daily_summary(date)

        return DailySummaryResponse(
            date=summary.date,
            total_trades=summary.total_trades,
            total_volume=summary.total_volume,
            avg_slippage_bps=summary.avg_slippage_bps,
            avg_cost_bps=summary.avg_cost_bps,
            avg_quality_score=summary.avg_quality_score,
            total_fees=summary.total_fees,
            total_slippage_cost=summary.total_slippage_cost,
            best_trade={"trade_id": summary.best_trade_id, "score": summary.best_trade_score}
                if summary.best_trade_id else None,
            worst_trade={"trade_id": summary.worst_trade_id, "score": summary.worst_trade_score}
                if summary.worst_trade_id else None,
            by_strategy=summary.by_strategy,
            by_symbol=summary.by_symbol,
            by_session=summary.by_session,
            recommendations=summary.recommendations,
            generated_at=summary.generated_at,
        )

    except Exception as e:
        logger.error(f"Error getting daily summary for {date}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get daily summary: {str(e)}"
        )


@router.get(
    "/worst-executions",
    response_model=BestWorstExecutionsResponse,
    summary="Get Worst Executions",
    description="Get the worst trade executions to identify recurring issues.",
)
async def get_worst_executions(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
):
    """
    Get worst trade executions

    Returns the trades with lowest execution quality scores,
    including identified problem factors and common patterns.
    """
    try:
        report_generator = get_trade_report_generator()
        report = report_generator.get_worst_executions_report(limit)

        return BestWorstExecutionsResponse(
            report_type=report["report_type"],
            generated_at=datetime.fromisoformat(report["generated_at"]),
            count=report["count"],
            executions=report["executions"],
            common_patterns=report["common_patterns"],
        )

    except Exception as e:
        logger.error(f"Error getting worst executions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get worst executions: {str(e)}"
        )


@router.get(
    "/best-executions",
    response_model=BestWorstExecutionsResponse,
    summary="Get Best Executions",
    description="Get the best trade executions to identify success patterns.",
)
async def get_best_executions(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
):
    """
    Get best trade executions

    Returns the trades with highest execution quality scores,
    including identified success factors and common patterns.
    """
    try:
        report_generator = get_trade_report_generator()
        report = report_generator.get_best_executions_report(limit)

        return BestWorstExecutionsResponse(
            report_type=report["report_type"],
            generated_at=datetime.fromisoformat(report["generated_at"]),
            count=report["count"],
            executions=report["executions"],
            common_patterns=report["common_patterns"],
        )

    except Exception as e:
        logger.error(f"Error getting best executions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get best executions: {str(e)}"
        )


@router.get(
    "/by-strategy/{strategy}",
    response_model=StrategyAnalysisResponse,
    summary="Get Strategy Analysis",
    description="Get post-trade analysis aggregated by strategy.",
)
async def get_strategy_analysis(
    strategy: str = Path(..., description="Strategy name"),
):
    """
    Get post-trade analysis for a specific strategy

    Returns aggregated metrics and all individual trade analyses
    for the specified strategy.
    """
    try:
        analyzer = get_post_trade_analyzer()

        # Get stats for the strategy
        stats = analyzer.get_strategy_stats(strategy)

        if "error" in stats:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for strategy: {strategy}"
            )

        # Get individual trades
        trades = analyzer.get_by_strategy(strategy)

        return StrategyAnalysisResponse(
            strategy=strategy,
            trade_count=stats["trade_count"],
            avg_slippage_bps=stats["avg_slippage_bps"],
            avg_cost_bps=stats["avg_cost_bps"],
            avg_quality_score=stats["avg_quality_score"],
            min_quality_score=stats["min_quality_score"],
            max_quality_score=stats["max_quality_score"],
            trades=[
                {
                    "trade_id": t.trade_id,
                    "symbol": t.symbol,
                    "side": t.side,
                    "quality_score": t.execution_quality.quality_score,
                    "cost_bps": t.cost_bps,
                    "analyzed_at": t.analyzed_at.isoformat(),
                }
                for t in trades
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy analysis for {strategy}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get strategy analysis: {str(e)}"
        )


@router.get(
    "/by-symbol/{symbol}",
    response_model=SymbolAnalysisResponse,
    summary="Get Symbol Analysis",
    description="Get post-trade analysis aggregated by trading symbol.",
)
async def get_symbol_analysis(
    symbol: str = Path(..., description="Trading symbol (e.g., BTCUSDT)"),
):
    """
    Get post-trade analysis for a specific symbol

    Returns aggregated metrics and all individual trade analyses
    for the specified symbol.
    """
    try:
        analyzer = get_post_trade_analyzer()

        # Get stats for the symbol
        stats = analyzer.get_symbol_stats(symbol)

        if "error" in stats:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for symbol: {symbol}"
            )

        # Get individual trades
        trades = analyzer.get_by_symbol(symbol)

        return SymbolAnalysisResponse(
            symbol=symbol,
            trade_count=stats["trade_count"],
            avg_slippage_bps=stats["avg_slippage_bps"],
            avg_cost_bps=stats["avg_cost_bps"],
            avg_quality_score=stats["avg_quality_score"],
            min_quality_score=stats["min_quality_score"],
            max_quality_score=stats["max_quality_score"],
            trades=[
                {
                    "trade_id": t.trade_id,
                    "strategy": t.strategy,
                    "side": t.side,
                    "quality_score": t.execution_quality.quality_score,
                    "cost_bps": t.cost_bps,
                    "analyzed_at": t.analyzed_at.isoformat(),
                }
                for t in trades
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting symbol analysis for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get symbol analysis: {str(e)}"
        )


@router.get(
    "/improvement-opportunities",
    response_model=List[ImprovementRecommendationResponse],
    summary="Get Improvement Opportunities",
    description="Get actionable recommendations to improve execution quality.",
)
async def get_improvement_opportunities():
    """
    Get improvement recommendations

    Analyzes all trade data to generate actionable recommendations:
    - Strategy-specific improvements
    - Symbol-specific improvements
    - Timing optimizations
    - Order type recommendations
    """
    try:
        analyzer = get_post_trade_analyzer()
        recommendations = analyzer.get_improvement_recommendations()

        return [
            ImprovementRecommendationResponse(
                category=rec.category,
                priority=rec.priority,
                recommendation=rec.recommendation,
                expected_savings_bps=rec.expected_savings_bps,
                applicable_to=rec.applicable_to,
                evidence=rec.evidence,
            )
            for rec in recommendations
        ]

    except Exception as e:
        logger.error(f"Error getting improvement opportunities: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get improvement opportunities: {str(e)}"
        )


@router.get(
    "/weekly-comparison",
    response_model=WeeklyComparisonResponse,
    summary="Get Weekly Comparison Report",
    description="Get week-over-week performance comparison.",
)
async def get_weekly_comparison(
    week_offset: int = Query(
        0,
        ge=-52,
        le=0,
        description="Week offset (0 = current week, -1 = last week)",
    ),
):
    """
    Get weekly comparison report

    Compares execution metrics week-over-week:
    - Trade volume and count changes
    - Slippage and cost trends
    - Quality score trends
    - Strategy and symbol breakdowns
    - Insights and recommendations
    """
    try:
        report_generator = get_trade_report_generator()
        report = report_generator.generate_weekly_comparison(week_offset)

        return WeeklyComparisonResponse(
            week_start=report.week_start,
            week_end=report.week_end,
            report_generated_at=report.report_generated_at,
            current_week=report.current_week,
            previous_week=report.previous_week,
            wow_changes=report.wow_changes,
            trends={k: v.value for k, v in report.trends.items()},
            best_executions=report.best_executions,
            worst_executions=report.worst_executions,
            strategy_comparison=report.strategy_comparison,
            symbol_comparison=report.symbol_comparison,
            insights=report.insights,
            recommendations=report.recommendations,
        )

    except Exception as e:
        logger.error(f"Error getting weekly comparison: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get weekly comparison: {str(e)}"
        )


# Export the router
post_trade_router = router
