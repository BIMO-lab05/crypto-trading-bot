"""
Performance Dashboard API Handlers
Purpose: API endpoints for real-time performance dashboard (Phase 5.3)

Provides endpoints for:
- GET /api/v1/trading/performance - Comprehensive performance summary
- GET /api/v1/trading/equity-curve - Historical equity curve data
- GET /api/v1/trading/drawdown - Drawdown history series
- GET /api/v1/trading/returns-distribution - Returns distribution for histogram
- GET /api/v1/trading/correlations - Asset correlation matrix
- GET /api/v1/trading/statistics - Detailed trade statistics
- GET /api/v1/trading/trades/history - Trade history with P&L details
- WebSocket /ws/performance - Real-time metrics updates

Author: Backend Developer Agent
Date: 2025-12-11
Phase: 5.3 - Real-Time Performance Dashboard
"""

import logging
import time
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import math

from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.paper_trading import get_paper_engine
from app.repositories import get_position_repository

# Configure logging
logger = logging.getLogger(__name__)

# Create router for performance dashboard endpoints
router = APIRouter(prefix="/api/v1/trading", tags=["Performance Dashboard"])


# =============================================================================
# RESPONSE MODELS
# =============================================================================


class PerformanceSummaryResponse(BaseModel):
    """Response model for comprehensive performance summary"""

    success: bool = True
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class EquityCurvePoint(BaseModel):
    """Single equity curve data point"""

    timestamp: str
    equity: float
    pnl: float = 0.0
    cumulative_pnl: float = 0.0
    trade_count: int = 0


class EquityCurveResponse(BaseModel):
    """Response model for equity curve data"""

    success: bool = True
    curve: List[EquityCurvePoint] = Field(default_factory=list)
    period: str = "30d"
    interval: str = "1h"
    # REQUIRED — no default. The old 10000.0 default was inert (the single
    # constructor at get_equity_curve always passes the real balance) but would
    # have silently reported a $10,000 baseline on a $100 account if any new
    # caller omitted it (AUDIT 2.5). Omission is now a ValidationError.
    initial_equity: float


class DrawdownPoint(BaseModel):
    """Single drawdown data point"""

    timestamp: str
    drawdown_percent: float
    drawdown_value: float
    equity: float
    peak: float


class DrawdownResponse(BaseModel):
    """Response model for drawdown series"""

    success: bool = True
    drawdown: List[DrawdownPoint] = Field(default_factory=list)
    current_drawdown: float = 0.0
    max_drawdown: float = 0.0
    period: str = "30d"


class ReturnsDistributionBin(BaseModel):
    """Single histogram bin for returns distribution"""

    bin_start: float
    bin_end: float
    bin_mid: float
    count: int
    frequency: float


class ReturnsDistributionStats(BaseModel):
    """Statistical summary for returns distribution"""

    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    std_dev: float = 0.0
    variance: float = 0.0
    min_value: float = 0.0
    max_value: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    range_value: float = 0.0


class ReturnsDistributionResponse(BaseModel):
    """Response model for returns distribution"""

    success: bool = True
    bins: List[ReturnsDistributionBin] = Field(default_factory=list)
    stats: Optional[ReturnsDistributionStats] = None
    period: str = "30d"


class CorrelationMatrixResponse(BaseModel):
    """Response model for asset correlation matrix"""

    success: bool = True
    matrix: List[List[float]] = Field(default_factory=list)
    symbols: List[str] = Field(default_factory=list)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class TradeStatisticsResponse(BaseModel):
    """Response model for detailed trade statistics"""

    success: bool = True
    statistics: Dict[str, Any] = Field(default_factory=dict)
    period: str = "30d"


class TradeHistoryItem(BaseModel):
    """Single trade history item"""

    id: str
    symbol: str
    side: str
    strategy: Optional[str] = None
    signal_type: Optional[str] = None
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    realized_pnl: Optional[float] = None
    opened_at: str
    closed_at: Optional[str] = None
    status: str


class TradeHistoryResponse(BaseModel):
    """Response model for trade history"""

    success: bool = True
    trades: List[TradeHistoryItem] = Field(default_factory=list)
    total_count: int = 0
    offset: int = 0
    limit: int = 100


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_period_timedelta(period: str) -> timedelta:
    """Convert period string to timedelta"""
    period_map = {
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
        "365d": timedelta(days=365),
        "all": timedelta(days=3650),  # ~10 years for "all"
    }
    return period_map.get(period, timedelta(days=30))


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Treat a naive datetime as UTC for comparison purposes.

    The positions table stores opened_at / closed_at as `timestamp
    without time zone`, but writes go through datetime.now(timezone.utc)
    — so values are conceptually UTC but come back from the ORM as
    tz-naive. Comparing them directly to a tz-aware cutoff
    (datetime.now(timezone.utc) - delta) raises
    "can't compare offset-naive and offset-aware datetimes", which
    500s every period-filtered endpoint in this module (statistics,
    performance, equity-curve, drawdown, returns-distribution).
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def calculate_equity_curve_from_trades(
    trades: List[Any], initial_balance: float
) -> List[Dict[str, Any]]:
    """
    Calculate equity curve from list of trades

    FIX 2026-08-03 (capital audit A1). `initial_balance` used to default to
    10000.0. `get_performance_summary()` omitted the argument while its two
    sibling endpoints passed the real balance, so the max-drawdown that endpoint
    reported was computed against a $10,000 baseline on a $100 account — the two
    disagreed by 100x within a single file. The default is now REMOVED rather
    than corrected, so omitting the argument is a TypeError instead of a
    silently wrong number. (Zero callers outside this module; verified by
    repo-wide grep.)

    Args:
        trades: List of trade/position objects
        initial_balance: Starting portfolio value. REQUIRED — source it from
            `paper_engine.get_initial_balance()`.

    Returns:
        List of equity curve data points
    """
    if not trades:
        return [
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "equity": initial_balance,
                "pnl": 0.0,
                "cumulative_pnl": 0.0,
                "trade_count": 0,
            }
        ]

    # Sort trades by close time
    sorted_trades = sorted(
        [t for t in trades if hasattr(t, "closed_at") and t.closed_at],
        key=lambda t: t.closed_at,
    )

    equity_curve = [
        {
            "timestamp": sorted_trades[0].closed_at.isoformat()
            if sorted_trades
            else datetime.now(timezone.utc).isoformat(),
            "equity": initial_balance,
            "pnl": 0.0,
            "cumulative_pnl": 0.0,
            "trade_count": 0,
        }
    ]

    cumulative_equity = initial_balance
    for idx, trade in enumerate(sorted_trades, 1):
        pnl = float(trade.realized_pnl or 0)
        cumulative_equity += pnl
        cumulative_pnl = cumulative_equity - initial_balance

        equity_curve.append(
            {
                "timestamp": trade.closed_at.isoformat()
                if trade.closed_at
                else datetime.now(timezone.utc).isoformat(),
                "equity": cumulative_equity,
                "pnl": pnl,
                "cumulative_pnl": cumulative_pnl,
                "trade_count": idx,
            }
        )

    return equity_curve


def calculate_drawdown_series(
    equity_curve: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Calculate drawdown series from equity curve

    Args:
        equity_curve: List of equity curve data points

    Returns:
        List of drawdown data points
    """
    if not equity_curve:
        return []

    drawdown_series = []
    peak = equity_curve[0]["equity"]

    for point in equity_curve:
        equity = point["equity"]
        if equity > peak:
            peak = equity

        drawdown_value = equity - peak
        drawdown_percent = (drawdown_value / peak * 100) if peak > 0 else 0.0

        drawdown_series.append(
            {
                "timestamp": point["timestamp"],
                "drawdown_percent": abs(drawdown_percent),
                "drawdown_value": drawdown_value,
                "equity": equity,
                "peak": peak,
            }
        )

    return drawdown_series


def calculate_returns_distribution(trades: List[Any], bins: int = 20) -> Dict[str, Any]:
    """
    Calculate returns distribution from trades

    Args:
        trades: List of trade objects with realized_pnl
        bins: Number of histogram bins

    Returns:
        Dictionary with bins list and stats
    """
    # Extract P&L values
    pnls = [float(t.realized_pnl) for t in trades if t.realized_pnl is not None]

    if not pnls:
        return {"bins": [], "stats": None}

    # Calculate statistics
    n = len(pnls)
    mean = sum(pnls) / n
    sorted_pnls = sorted(pnls)
    median = sorted_pnls[n // 2]
    min_val = min(pnls)
    max_val = max(pnls)
    range_val = max_val - min_val

    # Variance and std dev
    variance = sum((x - mean) ** 2 for x in pnls) / n
    std_dev = math.sqrt(variance)

    # Skewness and kurtosis
    if std_dev > 0:
        skewness = sum((x - mean) ** 3 for x in pnls) / (n * std_dev**3)
        kurtosis = (sum((x - mean) ** 4 for x in pnls) / (n * std_dev**4)) - 3
    else:
        skewness = 0.0
        kurtosis = 0.0

    # Create histogram bins
    bin_width = range_val / bins if bins > 0 and range_val > 0 else 1.0
    histogram = []

    for i in range(bins):
        bin_start = min_val + i * bin_width
        bin_end = bin_start + bin_width
        count = sum(
            1
            for x in pnls
            if bin_start <= x < bin_end or (i == bins - 1 and x == bin_end)
        )

        histogram.append(
            {
                "bin_start": round(bin_start, 2),
                "bin_end": round(bin_end, 2),
                "bin_mid": round((bin_start + bin_end) / 2, 2),
                "count": count,
                "frequency": round(count / n, 4) if n > 0 else 0.0,
            }
        )

    stats = {
        "count": n,
        "mean": round(mean, 2),
        "median": round(median, 2),
        "std_dev": round(std_dev, 2),
        "variance": round(variance, 2),
        "min_value": round(min_val, 2),
        "max_value": round(max_val, 2),
        "skewness": round(skewness, 4),
        "kurtosis": round(kurtosis, 4),
        "range_value": round(range_val, 2),
    }

    return {"bins": histogram, "stats": stats}


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.get("/performance", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    period: str = Query("30d", description="Time period (1d, 7d, 30d, 90d, all)"),
):
    """
    Get comprehensive performance summary with all key metrics

    Returns:
        PerformanceSummaryResponse with Sharpe, Sortino, VaR, etc.
    """
    try:
        paper_engine = get_paper_engine()
        position_repo = get_position_repository()

        # Get closed positions from database
        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        # Filter by period
        period_delta = get_period_timedelta(period)
        cutoff_date = datetime.now(timezone.utc) - period_delta

        filtered_positions = [
            pos
            for pos in db_closed_positions
            if pos.closed_at and _ensure_utc(pos.closed_at) >= cutoff_date
        ]

        # Calculate basic metrics
        total_trades = len(filtered_positions)
        winning_trades = sum(
            1
            for p in filtered_positions
            if p.realized_pnl and float(p.realized_pnl) > 0
        )
        losing_trades = sum(
            1
            for p in filtered_positions
            if p.realized_pnl and float(p.realized_pnl) < 0
        )
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

        total_pnl = sum(float(p.realized_pnl or 0) for p in filtered_positions)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0.0

        gross_profit = sum(
            float(p.realized_pnl)
            for p in filtered_positions
            if p.realized_pnl and float(p.realized_pnl) > 0
        )
        gross_loss = abs(
            sum(
                float(p.realized_pnl)
                for p in filtered_positions
                if p.realized_pnl and float(p.realized_pnl) < 0
            )
        )
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )

        avg_win = gross_profit / winning_trades if winning_trades > 0 else 0.0
        avg_loss = gross_loss / losing_trades if losing_trades > 0 else 0.0

        # Calculate risk metrics
        pnls = [float(p.realized_pnl) for p in filtered_positions if p.realized_pnl]

        if len(pnls) >= 2:
            variance = sum((x - avg_pnl) ** 2 for x in pnls) / len(pnls)
            std_dev = math.sqrt(variance)

            # Sharpe Ratio (simplified, assuming risk-free = 0)
            sharpe_ratio = avg_pnl / std_dev if std_dev > 0 else 0.0

            # Sortino Ratio
            downside_pnls = [x for x in pnls if x < 0]
            if downside_pnls:
                downside_var = sum(x**2 for x in downside_pnls) / len(downside_pnls)
                downside_dev = math.sqrt(downside_var)
                sortino_ratio = avg_pnl / downside_dev if downside_dev > 0 else 0.0
            else:
                sortino_ratio = float("inf") if avg_pnl > 0 else 0.0

            # VaR (95%)
            sorted_pnls = sorted(pnls)
            var_index = int(len(sorted_pnls) * 0.05)
            var_95 = (
                abs(sorted_pnls[var_index]) if var_index < len(sorted_pnls) else 0.0
            )

            # CVaR (95%)
            cvar_pnls = sorted_pnls[: var_index + 1]
            cvar_95 = abs(sum(cvar_pnls) / len(cvar_pnls)) if cvar_pnls else 0.0

            # Max Drawdown
            # FIX 2026-08-03 (capital audit A1): this call omitted
            # initial_balance and silently used the old 10000.0 default, so this
            # endpoint's max_drawdown was computed on a $10,000 baseline while
            # the sibling endpoints used the real balance. Mirror the siblings.
            initial_balance = float(paper_engine.get_initial_balance())
            equity_curve = calculate_equity_curve_from_trades(
                filtered_positions, initial_balance
            )
            drawdown_series = calculate_drawdown_series(equity_curve)
            max_drawdown = max(
                (d["drawdown_percent"] for d in drawdown_series), default=0.0
            )
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0
            var_95 = 0.0
            cvar_95 = 0.0
            max_drawdown = 0.0
            std_dev = 0.0

        metrics = {
            # Trade statistics
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2),
            # P&L metrics
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(profit_factor, 4)
            if profit_factor != float("inf")
            else 999.99,
            # Risk-adjusted metrics
            "sharpe_ratio": round(sharpe_ratio, 4),
            "sortino_ratio": round(sortino_ratio, 4)
            if sortino_ratio != float("inf")
            else 999.99,
            "var_95": round(var_95, 2),
            "cvar_95": round(cvar_95, 2),
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": round(max_drawdown, 2),
            "std_dev": round(std_dev, 4),
            # Metadata
            "period": period,
            "timestamp": int(time.time() * 1000),
        }

        return PerformanceSummaryResponse(success=True, metrics=metrics)

    except Exception as e:
        logger.error(f"Error getting performance summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity-curve", response_model=EquityCurveResponse)
async def get_equity_curve(
    period: str = Query("30d", description="Time period (1d, 7d, 30d, 90d, all)"),
    interval: str = Query("1h", description="Data interval (1m, 5m, 15m, 1h, 4h, 1d)"),
):
    """
    Get equity curve data for charting

    Returns:
        EquityCurveResponse with time-series equity data
    """
    try:
        paper_engine = get_paper_engine()
        position_repo = get_position_repository()

        # Get initial balance
        initial_balance = float(paper_engine.get_initial_balance())

        # Get closed positions
        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        # Filter by period
        period_delta = get_period_timedelta(period)
        cutoff_date = datetime.now(timezone.utc) - period_delta

        filtered_positions = [
            pos
            for pos in db_closed_positions
            if pos.closed_at and _ensure_utc(pos.closed_at) >= cutoff_date
        ]

        # Calculate equity curve
        equity_curve = calculate_equity_curve_from_trades(
            filtered_positions, initial_balance
        )

        # Convert to response model
        curve_points = [
            EquityCurvePoint(
                timestamp=point["timestamp"],
                equity=round(point["equity"], 2),
                pnl=round(point["pnl"], 2),
                cumulative_pnl=round(point["cumulative_pnl"], 2),
                trade_count=point["trade_count"],
            )
            for point in equity_curve
        ]

        return EquityCurveResponse(
            success=True,
            curve=curve_points,
            period=period,
            interval=interval,
            initial_equity=initial_balance,
        )

    except Exception as e:
        logger.error(f"Error getting equity curve: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drawdown", response_model=DrawdownResponse)
async def get_drawdown_history(
    period: str = Query("30d", description="Time period (7d, 30d, 90d, all)"),
):
    """
    Get drawdown history series

    Returns:
        DrawdownResponse with drawdown time-series data
    """
    try:
        paper_engine = get_paper_engine()
        position_repo = get_position_repository()

        initial_balance = float(paper_engine.get_initial_balance())

        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        period_delta = get_period_timedelta(period)
        cutoff_date = datetime.now(timezone.utc) - period_delta

        filtered_positions = [
            pos
            for pos in db_closed_positions
            if pos.closed_at and _ensure_utc(pos.closed_at) >= cutoff_date
        ]

        equity_curve = calculate_equity_curve_from_trades(
            filtered_positions, initial_balance
        )
        drawdown_series = calculate_drawdown_series(equity_curve)

        drawdown_points = [
            DrawdownPoint(
                timestamp=d["timestamp"],
                drawdown_percent=round(d["drawdown_percent"], 2),
                drawdown_value=round(d["drawdown_value"], 2),
                equity=round(d["equity"], 2),
                peak=round(d["peak"], 2),
            )
            for d in drawdown_series
        ]

        current_dd = drawdown_points[-1].drawdown_percent if drawdown_points else 0.0
        max_dd = max((d.drawdown_percent for d in drawdown_points), default=0.0)

        return DrawdownResponse(
            success=True,
            drawdown=drawdown_points,
            current_drawdown=round(current_dd, 2),
            max_drawdown=round(max_dd, 2),
            period=period,
        )

    except Exception as e:
        logger.error(f"Error getting drawdown history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/returns-distribution", response_model=ReturnsDistributionResponse)
async def get_returns_distribution(
    period: str = Query("30d", description="Time period"),
    bins: int = Query(20, ge=5, le=100, description="Number of histogram bins"),
):
    """
    Get returns distribution for histogram

    Returns:
        ReturnsDistributionResponse with histogram bins and statistics
    """
    try:
        position_repo = get_position_repository()

        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        period_delta = get_period_timedelta(period)
        cutoff_date = datetime.now(timezone.utc) - period_delta

        filtered_positions = [
            pos
            for pos in db_closed_positions
            if pos.closed_at and _ensure_utc(pos.closed_at) >= cutoff_date
        ]

        distribution = calculate_returns_distribution(filtered_positions, bins)

        dist_bins = [ReturnsDistributionBin(**b) for b in distribution.get("bins", [])]

        dist_stats = None
        if distribution.get("stats"):
            dist_stats = ReturnsDistributionStats(**distribution["stats"])

        return ReturnsDistributionResponse(
            success=True, bins=dist_bins, stats=dist_stats, period=period
        )

    except Exception as e:
        logger.error(f"Error getting returns distribution: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlations", response_model=CorrelationMatrixResponse)
async def get_correlations(
    period: str = Query("30d", description="Lookback period"),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
):
    """
    Get asset correlation matrix

    Returns:
        CorrelationMatrixResponse with correlation coefficients
    """
    try:
        # Parse symbols
        symbol_list = (
            symbols.split(",")
            if symbols
            else ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]
        )

        position_repo = get_position_repository()

        # Get positions by symbol
        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        # Group P&L by symbol
        pnl_by_symbol = defaultdict(list)
        for pos in db_closed_positions:
            if pos.symbol in symbol_list and pos.realized_pnl:
                pnl_by_symbol[pos.symbol].append(float(pos.realized_pnl))

        # Calculate correlation matrix
        valid_symbols = [s for s in symbol_list if len(pnl_by_symbol.get(s, [])) > 1]

        if len(valid_symbols) < 2:
            # Not enough data for correlation
            return CorrelationMatrixResponse(
                success=True, matrix=[], symbols=valid_symbols
            )

        # Simple correlation calculation
        n = len(valid_symbols)
        matrix = [[0.0] * n for _ in range(n)]

        for i, sym_i in enumerate(valid_symbols):
            for j, sym_j in enumerate(valid_symbols):
                if i == j:
                    matrix[i][j] = 1.0
                elif i < j:
                    pnl_i = pnl_by_symbol[sym_i]
                    pnl_j = pnl_by_symbol[sym_j]

                    # Align series by taking minimum length
                    min_len = min(len(pnl_i), len(pnl_j))
                    if min_len > 1:
                        pi = pnl_i[:min_len]
                        pj = pnl_j[:min_len]

                        mean_i = sum(pi) / min_len
                        mean_j = sum(pj) / min_len

                        cov = (
                            sum(
                                (pi[k] - mean_i) * (pj[k] - mean_j)
                                for k in range(min_len)
                            )
                            / min_len
                        )
                        std_i = math.sqrt(sum((x - mean_i) ** 2 for x in pi) / min_len)
                        std_j = math.sqrt(sum((x - mean_j) ** 2 for x in pj) / min_len)

                        corr = cov / (std_i * std_j) if std_i > 0 and std_j > 0 else 0.0
                        matrix[i][j] = round(corr, 4)
                        matrix[j][i] = round(corr, 4)

        return CorrelationMatrixResponse(
            success=True, matrix=matrix, symbols=valid_symbols
        )

    except Exception as e:
        logger.error(f"Error getting correlations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics", response_model=TradeStatisticsResponse)
async def get_trade_statistics(
    period: str = Query("30d", description="Time period"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
):
    """
    Get detailed trade statistics

    Returns:
        TradeStatisticsResponse with comprehensive trade stats
    """
    try:
        position_repo = get_position_repository()

        db_closed_positions = await position_repo.get_closed_positions(
            portfolio_id="paper_trading", limit=1000
        )

        period_delta = get_period_timedelta(period)
        cutoff_date = datetime.now(timezone.utc) - period_delta

        filtered_positions = [
            pos
            for pos in db_closed_positions
            if pos.closed_at
            and _ensure_utc(pos.closed_at) >= cutoff_date
            and (symbol is None or pos.symbol == symbol)
        ]

        # Calculate statistics
        total_trades = len(filtered_positions)
        if total_trades == 0:
            return TradeStatisticsResponse(
                success=True, statistics={"total_trades": 0}, period=period
            )

        pnls = [float(p.realized_pnl) for p in filtered_positions if p.realized_pnl]
        winning_trades = sum(1 for p in pnls if p > 0)
        losing_trades = sum(1 for p in pnls if p < 0)

        total_pnl = sum(pnls)
        avg_pnl = total_pnl / len(pnls) if pnls else 0.0

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))

        # By symbol breakdown
        by_symbol = defaultdict(
            lambda: {"trades": 0, "pnl": 0.0, "wins": 0, "losses": 0}
        )
        for pos in filtered_positions:
            sym = pos.symbol
            by_symbol[sym]["trades"] += 1
            pnl = float(pos.realized_pnl or 0)
            by_symbol[sym]["pnl"] += pnl
            if pnl > 0:
                by_symbol[sym]["wins"] += 1
            elif pnl < 0:
                by_symbol[sym]["losses"] += 1

        statistics = {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "breakeven_trades": total_trades - winning_trades - losing_trades,
            "win_rate": round(winning_trades / total_trades * 100, 2)
            if total_trades > 0
            else 0.0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(avg_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "profit_factor": round(gross_profit / gross_loss, 4)
            if gross_loss > 0
            else 999.99,
            "avg_win": round(gross_profit / winning_trades, 2)
            if winning_trades > 0
            else 0.0,
            "avg_loss": round(gross_loss / losing_trades, 2)
            if losing_trades > 0
            else 0.0,
            "by_symbol": {k: dict(v) for k, v in by_symbol.items()},
        }

        return TradeStatisticsResponse(
            success=True, statistics=statistics, period=period
        )

    except Exception as e:
        logger.error(f"Error getting trade statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades/history", response_model=TradeHistoryResponse)
async def get_trade_history_endpoint(
    limit: int = Query(100, ge=1, le=1000, description="Number of trades to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status: str = Query(
        "CLOSED", description="Trade status filter (OPEN, CLOSED, ALL)"
    ),
):
    """
    Get trade history with P&L details

    Returns:
        TradeHistoryResponse with paginated trade list
    """
    try:
        position_repo = get_position_repository()

        if status.upper() == "ALL":
            db_positions = await position_repo.get_positions_by_status(
                portfolio_id="paper_trading"
            )
        elif status.upper() == "OPEN":
            # Display path: a degraded read shows an empty history rather than
            # a 500. The strict get_open_positions is for startup hydration.
            db_positions = await position_repo.get_open_positions_or_empty(
                portfolio_id="paper_trading"
            )
        else:
            db_positions = await position_repo.get_closed_positions(
                portfolio_id="paper_trading", limit=limit + offset
            )

        # Apply pagination
        total_count = len(db_positions)
        paginated = db_positions[offset : offset + limit]

        trades = [
            TradeHistoryItem(
                id=str(pos.id),
                symbol=pos.symbol,
                side=pos.side,
                strategy=getattr(pos, "strategy", None),
                signal_type=getattr(pos, "signal_type", None),
                entry_price=float(pos.entry_price),
                exit_price=float(pos.exit_price) if pos.exit_price else None,
                quantity=float(pos.quantity),
                realized_pnl=float(pos.realized_pnl) if pos.realized_pnl else None,
                opened_at=pos.opened_at.isoformat() if pos.opened_at else None,
                closed_at=pos.closed_at.isoformat() if pos.closed_at else None,
                status=pos.status,
            )
            for pos in paginated
        ]

        return TradeHistoryResponse(
            success=True,
            trades=trades,
            total_count=total_count,
            offset=offset,
            limit=limit,
        )

    except Exception as e:
        logger.error(f"Error getting trade history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# WEBSOCKET FOR REAL-TIME UPDATES
# =============================================================================


class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(
            f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
        )

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        for connection in self.active_connections[
            :
        ]:  # Copy list to avoid mutation during iteration
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                self.disconnect(connection)


# Global connection manager
ws_manager = ConnectionManager()


@router.websocket("/ws/performance")
async def websocket_performance(websocket: WebSocket):
    """
    WebSocket endpoint for real-time performance updates

    Sends updates every second with latest metrics
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Wait for message or send update periodically
            try:
                # Wait for ping/subscribe messages
                data = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)

                if data.get("type") == "ping":
                    await websocket.send_json(
                        {"type": "pong", "timestamp": int(time.time() * 1000)}
                    )
                elif data.get("type") == "subscribe":
                    await websocket.send_json(
                        {"type": "subscribed", "channel": data.get("channel")}
                    )

            except asyncio.TimeoutError:
                # No message received, send metrics update
                try:
                    # Get current performance snapshot
                    paper_engine = get_paper_engine()
                    summary = paper_engine.get_performance_summary()

                    await websocket.send_json(
                        {
                            "type": "metrics",
                            "payload": {
                                "balance": float(summary.get("current_balance", 0)),
                                "unrealized_pnl": float(
                                    summary.get("unrealized_pnl", 0)
                                ),
                                "total_trades": summary.get("total_trades", 0),
                                "timestamp": int(time.time() * 1000),
                            },
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to send metrics update: {e}")

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# Add asyncio import for WebSocket timeout
import asyncio


# Export router for inclusion in main app
def get_performance_dashboard_router():
    """Get the performance dashboard router"""
    return router
