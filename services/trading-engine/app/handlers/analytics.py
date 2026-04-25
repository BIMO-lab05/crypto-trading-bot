"""
Advanced Performance Metrics API Handlers - Phase 5.2
Purpose: FastAPI endpoint handlers for professional-grade performance analytics

This module provides HTTP endpoints for:
- GET /api/v1/analytics/metrics/risk-adjusted - Sharpe, Sortino, Calmar, Omega ratios
- GET /api/v1/analytics/metrics/drawdown - Drawdown analysis
- GET /api/v1/analytics/metrics/win-loss - Win rate, profit factor, Kelly %
- GET /api/v1/analytics/metrics/risk - VaR, CVaR, MAE, MFE
- GET /api/v1/analytics/metrics/efficiency - Trade efficiency stats
- GET /api/v1/analytics/metrics/all - Complete metrics summary
- GET /api/v1/analytics/metrics/compare - Period comparison
- GET /api/v1/analytics/metrics/benchmark - vs BTC performance
- GET /api/v1/analytics/report/daily - Daily report
- GET /api/v1/analytics/report/monthly - Monthly report

Author: Backend Developer Agent
Date: 2025-12-12
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from app.analytics.advanced_metrics import (
    get_advanced_metrics_calculator,
    RiskAdjustedMetrics,
    DrawdownMetrics,
    WinLossMetrics,
    RiskMetrics,
    EfficiencyMetrics,
    BenchmarkComparison,
    AllMetrics,
    MetricsPeriod,
)
from app.analytics.performance_report import (
    get_report_generator,
    DailyReportData,
    MonthlyReportData,
    MonteCarloResult,
)

logger = logging.getLogger(__name__)

# =============================================================================
# PYDANTIC RESPONSE MODELS
# =============================================================================


class RiskAdjustedMetricsResponse(BaseModel):
    """Response model for risk-adjusted metrics"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Risk-adjusted return metrics"
    )
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "sharpe_ratio": 1.85,
                    "sortino_ratio": 2.34,
                    "calmar_ratio": 1.92,
                    "omega_ratio": 1.67,
                    "treynor_ratio": 0.15,
                    "information_ratio": 0.82,
                    "gain_to_pain_ratio": 2.1
                },
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class DrawdownMetricsResponse(BaseModel):
    """Response model for drawdown analysis"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Drawdown analysis metrics"
    )
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "max_drawdown": -12.5,
                    "avg_drawdown": -3.2,
                    "drawdown_duration": 7,
                    "recovery_factor": 2.1,
                    "ulcer_index": 3.45,
                    "pain_index": 0.012,
                    "time_underwater_pct": 35.0,
                    "current_drawdown": -2.3
                },
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class WinLossMetricsResponse(BaseModel):
    """Response model for win/loss analysis"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Win/loss analysis metrics"
    )
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "win_rate": 58.0,
                    "profit_factor": 1.85,
                    "payoff_ratio": 1.45,
                    "expectancy": 0.042,
                    "kelly_percentage": 12.5,
                    "consecutive_wins": 7,
                    "consecutive_losses": 4,
                    "current_streak": 3,
                    "avg_win": 150.50,
                    "avg_loss": 85.25,
                    "largest_win": 450.00,
                    "largest_loss": 200.00
                },
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class RiskMetricsResponse(BaseModel):
    """Response model for risk quantification"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Risk quantification metrics"
    )
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "var_95": 2.3,
                    "var_99": 3.8,
                    "cvar_95": 3.1,
                    "cvar_99": 4.5,
                    "beta": 0.85,
                    "max_adverse_excursion": 1.5,
                    "max_favorable_excursion": 2.8,
                    "risk_of_ruin": 0.1,
                    "volatility": 25.5,
                    "downside_volatility": 18.2,
                    "tail_ratio": 1.35,
                    "risk_level": "moderate"
                },
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class EfficiencyMetricsResponse(BaseModel):
    """Response model for trade efficiency"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Trade efficiency metrics"
    )
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "avg_trade_duration_hours": 4.5,
                    "trades_per_day": 3.2,
                    "trades_per_week": 22.4,
                    "trades_per_month": 96.0,
                    "avg_position_size_pct": 5.0,
                    "capital_utilization_pct": 10.0,
                    "turnover_ratio": 12.5,
                    "holding_period_return": 0.15
                },
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class AllMetricsResponse(BaseModel):
    """Response model for complete metrics summary"""
    success: bool = True
    risk_adjusted: Dict[str, Any]
    drawdown: Dict[str, Any]
    win_loss: Dict[str, Any]
    risk: Dict[str, Any]
    efficiency: Dict[str, Any]
    total_trades: int
    total_pnl: float
    generated_at: str


class PeriodComparisonResponse(BaseModel):
    """Response model for period comparison"""
    success: bool = True
    period_days: int
    current_period: Dict[str, Any]
    previous_period: Dict[str, Any]
    changes: Dict[str, Any]
    generated_at: str


class BenchmarkComparisonResponse(BaseModel):
    """Response model for benchmark comparison"""
    success: bool = True
    metrics: Dict[str, Any] = Field(
        ...,
        description="Benchmark comparison metrics"
    )
    benchmark: str = "BTC"
    generated_at: str = Field(
        ...,
        description="Timestamp when metrics were calculated"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "metrics": {
                    "strategy_return_pct": 15.5,
                    "benchmark_return_pct": 8.2,
                    "excess_return_pct": 7.3,
                    "alpha": 0.05,
                    "beta": 0.75,
                    "correlation": 0.65,
                    "tracking_error_pct": 8.5,
                    "information_ratio": 0.86,
                    "up_capture_pct": 110.0,
                    "down_capture_pct": 65.0
                },
                "benchmark": "BTC",
                "generated_at": "2025-12-12T10:30:00Z"
            }
        }


class DailyReportResponse(BaseModel):
    """Response model for daily report"""
    success: bool = True
    report: Dict[str, Any]


class MonthlyReportResponse(BaseModel):
    """Response model for monthly report"""
    success: bool = True
    report: Dict[str, Any]


class ErrorResponse(BaseModel):
    """Standard error response"""
    success: bool = False
    error: str
    detail: Optional[str] = None


# =============================================================================
# ROUTER SETUP
# =============================================================================

router = APIRouter(
    prefix="/api/v1/analytics/metrics",
    tags=["Advanced Performance Metrics"],
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)

report_router = APIRouter(
    prefix="/api/v1/analytics/report",
    tags=["Performance Reports"],
    responses={
        500: {"model": ErrorResponse, "description": "Internal Server Error"}
    }
)


# =============================================================================
# METRICS API ENDPOINTS
# =============================================================================

@router.get(
    "/risk-adjusted",
    response_model=RiskAdjustedMetricsResponse,
    summary="Get Risk-Adjusted Metrics",
    description="""
    Get risk-adjusted return metrics for performance evaluation.

    Returns:
    - **Sharpe Ratio**: (Return - Risk Free) / Volatility
    - **Sortino Ratio**: (Return - Risk Free) / Downside Deviation
    - **Calmar Ratio**: Annualized Return / Max Drawdown
    - **Omega Ratio**: Probability-weighted gains / losses
    - **Treynor Ratio**: (Return - Risk Free) / Beta
    - **Information Ratio**: Excess Return / Tracking Error
    - **Gain-to-Pain Ratio**: Sum of returns / Abs sum of negative returns

    Higher values indicate better risk-adjusted performance.
    Industry benchmark: Sharpe > 1.0 is considered good.
    """
)
async def get_risk_adjusted_metrics() -> RiskAdjustedMetricsResponse:
    """Get all risk-adjusted return metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_risk_adjusted_metrics()

        return RiskAdjustedMetricsResponse(
            success=True,
            metrics=metrics.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting risk-adjusted metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/drawdown",
    response_model=DrawdownMetricsResponse,
    summary="Get Drawdown Analysis",
    description="""
    Get comprehensive drawdown analysis metrics.

    Returns:
    - **Max Drawdown**: Maximum peak-to-trough decline (%)
    - **Average Drawdown**: Average drawdown depth
    - **Drawdown Duration**: Longest drawdown period (days)
    - **Recovery Factor**: Net profit / Max drawdown
    - **Ulcer Index**: Root mean square of drawdowns (severity measure)
    - **Pain Index**: Product of drawdown depth and duration
    - **Time Underwater**: Percentage of time spent in drawdown
    - **Current Drawdown**: Current drawdown from peak

    Lower drawdown values indicate better capital preservation.
    """
)
async def get_drawdown_metrics() -> DrawdownMetricsResponse:
    """Get drawdown analysis metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_drawdown_metrics()

        return DrawdownMetricsResponse(
            success=True,
            metrics=metrics.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting drawdown metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/win-loss",
    response_model=WinLossMetricsResponse,
    summary="Get Win/Loss Metrics",
    description="""
    Get win/loss analysis metrics for trade performance.

    Returns:
    - **Win Rate**: Percentage of winning trades
    - **Profit Factor**: Gross profit / Gross loss
    - **Payoff Ratio**: Average win / Average loss
    - **Expectancy**: Expected value per trade
    - **Kelly Percentage**: Optimal position size (Kelly Criterion)
    - **Consecutive Wins/Losses**: Maximum streak counts
    - **Average Win/Loss**: Mean profit/loss per trade

    Profit Factor > 1.5 is generally considered good.
    Kelly % should be used conservatively (half-Kelly recommended).
    """
)
async def get_win_loss_metrics() -> WinLossMetricsResponse:
    """Get win/loss analysis metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_win_loss_metrics()

        return WinLossMetricsResponse(
            success=True,
            metrics=metrics.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting win/loss metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/risk",
    response_model=RiskMetricsResponse,
    summary="Get Risk Metrics",
    description="""
    Get risk quantification metrics for portfolio analysis.

    Returns:
    - **VaR 95%/99%**: Value at Risk at confidence levels
    - **CVaR 95%/99%**: Conditional VaR (Expected Shortfall)
    - **Beta**: Correlation with market benchmark
    - **MAE**: Maximum Adverse Excursion (avg max loss during trades)
    - **MFE**: Maximum Favorable Excursion (avg max profit during trades)
    - **Risk of Ruin**: Probability of total account loss
    - **Volatility**: Annualized standard deviation
    - **Downside Volatility**: Volatility of negative returns only
    - **Tail Ratio**: Asymmetry of return distribution
    - **Risk Level**: Classified risk level (very_low to very_high)

    VaR indicates potential loss at given confidence level.
    Risk of Ruin < 1% is recommended for conservative trading.
    """
)
async def get_risk_metrics() -> RiskMetricsResponse:
    """Get risk quantification metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_risk_metrics()

        return RiskMetricsResponse(
            success=True,
            metrics=metrics.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting risk metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/efficiency",
    response_model=EfficiencyMetricsResponse,
    summary="Get Trade Efficiency Metrics",
    description="""
    Get trade efficiency metrics for execution analysis.

    Returns:
    - **Average Trade Duration**: Mean holding time (hours)
    - **Trades Per Day/Week/Month**: Trading frequency
    - **Average Position Size**: Mean position as % of capital
    - **Capital Utilization**: Deployed capital percentage
    - **Turnover Ratio**: Annualized portfolio turnover
    - **Holding Period Return**: Return per unit of holding time

    Higher turnover may indicate active trading style.
    Capital utilization shows how much capital is deployed on average.
    """
)
async def get_efficiency_metrics() -> EfficiencyMetricsResponse:
    """Get trade efficiency metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_efficiency_metrics()

        return EfficiencyMetricsResponse(
            success=True,
            metrics=metrics.to_dict(),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting efficiency metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/all",
    response_model=AllMetricsResponse,
    summary="Get All Performance Metrics",
    description="""
    Get complete performance metrics in a single request.

    Returns all metric categories:
    - Risk-adjusted metrics (Sharpe, Sortino, etc.)
    - Drawdown analysis
    - Win/loss metrics
    - Risk metrics (VaR, CVaR, etc.)
    - Trade efficiency metrics
    - Total trades and P&L

    Use this endpoint for comprehensive dashboard updates.
    """
)
async def get_all_metrics() -> AllMetricsResponse:
    """Get all performance metrics combined"""
    try:
        calculator = get_advanced_metrics_calculator()
        metrics = calculator.get_all_metrics()

        return AllMetricsResponse(
            success=True,
            risk_adjusted=metrics.risk_adjusted.to_dict(),
            drawdown=metrics.drawdown.to_dict(),
            win_loss=metrics.win_loss.to_dict(),
            risk=metrics.risk.to_dict(),
            efficiency=metrics.efficiency.to_dict(),
            total_trades=metrics.total_trades,
            total_pnl=round(metrics.total_pnl, 2),
            generated_at=metrics.generated_at.isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting all metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/compare",
    response_model=PeriodComparisonResponse,
    summary="Compare Performance Periods",
    description="""
    Compare metrics between current and previous period.

    Shows:
    - Current period metrics
    - Previous period metrics
    - Changes in key metrics (trades, P&L, win rate, Sharpe)

    Useful for tracking performance trends over time.
    """
)
async def compare_periods(
    period: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Number of days per period"
    ),
) -> PeriodComparisonResponse:
    """Compare current vs previous period metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        comparison = calculator.compare_periods(period_days=period)

        if "error" in comparison:
            raise HTTPException(status_code=400, detail=comparison["error"])

        return PeriodComparisonResponse(
            success=True,
            period_days=comparison["period_days"],
            current_period=comparison["current_period"],
            previous_period=comparison["previous_period"],
            changes=comparison["changes"],
            generated_at=comparison["generated_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing periods: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/benchmark",
    response_model=BenchmarkComparisonResponse,
    summary="Get Benchmark Comparison",
    description="""
    Compare strategy performance vs BTC benchmark.

    Returns:
    - **Strategy Return**: Total strategy return
    - **Benchmark Return**: Total BTC return
    - **Excess Return**: Strategy - Benchmark
    - **Alpha**: Risk-adjusted excess return
    - **Beta**: Sensitivity to benchmark movements
    - **Correlation**: Strategy-benchmark correlation
    - **Tracking Error**: Standard deviation of excess returns
    - **Information Ratio**: Excess return / Tracking error
    - **Up/Down Capture**: Performance in up/down markets

    Alpha > 0 indicates outperformance vs benchmark.
    Low beta indicates less market correlation.
    """
)
async def get_benchmark_comparison() -> BenchmarkComparisonResponse:
    """Get benchmark comparison metrics"""
    try:
        calculator = get_advanced_metrics_calculator()
        comparison = calculator.get_benchmark_comparison()

        return BenchmarkComparisonResponse(
            success=True,
            metrics=comparison.to_dict(),
            benchmark="BTC",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.error(f"Error getting benchmark comparison: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# REPORT API ENDPOINTS
# =============================================================================

@report_router.get(
    "/daily",
    response_model=DailyReportResponse,
    summary="Get Daily Performance Report",
    description="""
    Generate comprehensive daily performance report.

    Includes:
    - Trade count and total P&L for the day
    - Win rate and Sharpe ratio
    - Best and worst trades
    - Strategy and symbol breakdowns
    - Equity change and current drawdown

    Useful for daily performance reviews.
    """
)
async def get_daily_report(
    date: Optional[str] = Query(
        default=None,
        description="Date for report (YYYY-MM-DD format, defaults to today)"
    ),
) -> DailyReportResponse:
    """Generate daily performance report"""
    try:
        generator = get_report_generator()

        # Parse date if provided
        report_date = None
        if date:
            try:
                report_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        report = generator.generate_daily_report(date=report_date)

        return DailyReportResponse(
            success=True,
            report=report.to_dict(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating daily report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@report_router.get(
    "/monthly",
    response_model=MonthlyReportResponse,
    summary="Get Monthly Performance Report",
    description="""
    Generate comprehensive monthly performance report.

    Includes:
    - Monthly P&L and trade statistics
    - Risk-adjusted metrics (Sharpe, Sortino, Calmar)
    - Weekly breakdown
    - Strategy and symbol performance
    - Equity and drawdown curves
    - Trade efficiency metrics
    - Benchmark comparison (vs BTC)

    Useful for monthly portfolio reviews.
    """
)
async def get_monthly_report(
    year: int = Query(
        default=None,
        description="Year for report (defaults to current year)"
    ),
    month: int = Query(
        default=None,
        ge=1,
        le=12,
        description="Month for report (1-12, defaults to current month)"
    ),
) -> MonthlyReportResponse:
    """Generate monthly performance report"""
    try:
        generator = get_report_generator()

        # Default to current year/month if not provided
        now = datetime.now(timezone.utc)
        report_year = year or now.year
        report_month = month or now.month

        report = generator.generate_monthly_report(year=report_year, month=report_month)

        return MonthlyReportResponse(
            success=True,
            report=report.to_dict(),
        )
    except Exception as e:
        logger.error(f"Error generating monthly report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@report_router.get(
    "/monte-carlo",
    summary="Run Monte Carlo Simulation",
    description="""
    Run Monte Carlo simulation for future performance projection.

    Parameters:
    - simulations: Number of simulation runs (default: 1000)
    - horizon: Investment horizon in days (default: 30)

    Returns:
    - Percentile outcomes (5th, 25th, 50th, 75th, 95th)
    - Expected return and standard deviation
    - Probability of profit/loss scenarios
    - VaR and CVaR estimates

    Useful for risk planning and position sizing.
    """
)
async def run_monte_carlo(
    simulations: int = Query(
        default=1000,
        ge=100,
        le=10000,
        description="Number of simulation runs"
    ),
    horizon: int = Query(
        default=30,
        ge=1,
        le=365,
        description="Investment horizon in days"
    ),
):
    """Run Monte Carlo simulation for future projections"""
    try:
        generator = get_report_generator()
        result = generator.run_monte_carlo_simulation(
            num_simulations=simulations,
            horizon_days=horizon,
        )

        return {
            "success": True,
            "simulation": result.to_dict(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Error running Monte Carlo simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# STANDALONE HANDLER FUNCTIONS
# =============================================================================

async def risk_adjusted_handler() -> RiskAdjustedMetricsResponse:
    """Standalone handler for risk-adjusted metrics"""
    return await get_risk_adjusted_metrics()


async def drawdown_handler() -> DrawdownMetricsResponse:
    """Standalone handler for drawdown metrics"""
    return await get_drawdown_metrics()


async def win_loss_handler() -> WinLossMetricsResponse:
    """Standalone handler for win/loss metrics"""
    return await get_win_loss_metrics()


async def risk_handler() -> RiskMetricsResponse:
    """Standalone handler for risk metrics"""
    return await get_risk_metrics()


async def efficiency_handler() -> EfficiencyMetricsResponse:
    """Standalone handler for efficiency metrics"""
    return await get_efficiency_metrics()


async def all_metrics_handler() -> AllMetricsResponse:
    """Standalone handler for all metrics"""
    return await get_all_metrics()


async def compare_handler(period: int = 30) -> PeriodComparisonResponse:
    """Standalone handler for period comparison"""
    return await compare_periods(period)


async def benchmark_handler() -> BenchmarkComparisonResponse:
    """Standalone handler for benchmark comparison"""
    return await get_benchmark_comparison()


async def daily_report_handler(date: Optional[str] = None) -> DailyReportResponse:
    """Standalone handler for daily report"""
    return await get_daily_report(date)


async def monthly_report_handler(
    year: Optional[int] = None,
    month: Optional[int] = None,
) -> MonthlyReportResponse:
    """Standalone handler for monthly report"""
    return await get_monthly_report(year, month)
