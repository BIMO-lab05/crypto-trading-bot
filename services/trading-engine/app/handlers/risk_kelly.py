"""
Kelly Criterion Position Sizing API Handlers
Purpose: REST API endpoints for Kelly position sizing and risk management

Endpoints:
- GET /api/v1/risk/kelly-stats: Get Kelly statistics and current recommendations
- POST /api/v1/risk/kelly-calculate: Calculate position size for specific parameters
- POST /api/v1/risk/kelly-simulate: Simulate Kelly with hypothetical parameters
- POST /api/v1/risk/kelly-record-trade: Record a trade for Kelly tracking

Phase 3.2 - Statistical Arbitrage Position Sizing
Author: Trading Bot Development Team
Date: 2025-12-11
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, validator

from app.risk.kelly_position_sizing import (
    get_kelly_sizer,
    KellyMode,
    TradeRecord,
    KellyResult,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/risk", tags=["risk", "kelly"])


# ==========================================
# Pydantic Models for Request/Response
# ==========================================

class KellyStatsResponse(BaseModel):
    """Response model for Kelly statistics endpoint"""
    kelly: Dict[str, Any] = Field(description="Kelly calculation details")
    performance: Dict[str, Any] = Field(description="Performance metrics")
    trades: Dict[str, Any] = Field(description="Trade statistics")
    streak: Dict[str, Any] = Field(description="Current streak info")
    limits: Dict[str, Any] = Field(description="Position size limits")
    timestamp: str = Field(description="Response timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "kelly": {
                    "full_kelly_pct": 12.5,
                    "current_fraction": 0.30,
                    "default_fraction": 0.25,
                    "edge": 0.85
                },
                "performance": {
                    "win_rate": 0.58,
                    "avg_win_pct": 1.8,
                    "avg_loss_pct": 1.2,
                    "profit_factor": 1.5,
                    "expectancy": 0.55
                },
                "trades": {
                    "total_trades": 45,
                    "rolling_window": 50,
                    "trades_in_window": 45,
                    "min_for_kelly": 10,
                    "has_sufficient_data": True
                },
                "streak": {
                    "current_streak": 3,
                    "streak_type": "win"
                },
                "limits": {
                    "max_position_pct": 10.0,
                    "min_position_pct": 1.0,
                    "fallback_pct": 3.0
                },
                "timestamp": "2025-12-11T14:30:00Z"
            }
        }


class KellyCalculateRequest(BaseModel):
    """Request model for Kelly position size calculation"""
    capital: float = Field(..., gt=0, description="Available capital")
    current_price: float = Field(..., gt=0, description="Current asset price")
    mode: str = Field(
        default="FRACTIONAL",
        description="Kelly mode: FULL, FRACTIONAL, or DYNAMIC"
    )
    signal_confidence: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Signal confidence (0-1)"
    )
    stop_loss_pct: Optional[float] = Field(
        default=None,
        gt=0,
        description="Stop loss percentage for risk limiting"
    )

    @validator("mode")
    def validate_mode(cls, v):
        valid_modes = ["FULL", "FRACTIONAL", "DYNAMIC"]
        if v.upper() not in valid_modes:
            raise ValueError(f"Mode must be one of: {valid_modes}")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "capital": 10000,
                "current_price": 50000,
                "mode": "DYNAMIC",
                "signal_confidence": 0.75,
                "stop_loss_pct": 3.0
            }
        }


class KellyCalculateResponse(BaseModel):
    """Response model for Kelly position size calculation"""
    position_size_pct: float = Field(description="Recommended position size (%)")
    position_value: float = Field(description="Position value in currency")
    quantity: float = Field(description="Number of units to trade")
    full_kelly_pct: float = Field(description="Full Kelly percentage")
    kelly_fraction_used: float = Field(description="Kelly fraction applied")
    mode: str = Field(description="Kelly mode used")
    win_rate: float = Field(description="Win rate used in calculation")
    avg_win_pct: float = Field(description="Average win percentage")
    avg_loss_pct: float = Field(description="Average loss percentage")
    edge: float = Field(description="Expected edge per trade")
    confidence_level: float = Field(description="Confidence in estimate (0-1)")
    reasoning: str = Field(description="Human-readable explanation")
    metadata: Dict[str, Any] = Field(description="Additional details")

    class Config:
        json_schema_extra = {
            "example": {
                "position_size_pct": 3.75,
                "position_value": 375.0,
                "quantity": 0.0075,
                "full_kelly_pct": 15.0,
                "kelly_fraction_used": 0.25,
                "mode": "FRACTIONAL",
                "win_rate": 0.58,
                "avg_win_pct": 1.8,
                "avg_loss_pct": 1.2,
                "edge": 0.55,
                "confidence_level": 0.9,
                "reasoning": "Kelly calculation: W=58.0%, Avg Win=1.80%, Avg Loss=1.20%...",
                "metadata": {"streak": 2, "total_trades": 45}
            }
        }


class KellySimulateRequest(BaseModel):
    """Request model for Kelly simulation (what-if analysis)"""
    win_rate: float = Field(..., gt=0, lt=1, description="Hypothetical win rate (0-1)")
    avg_win_pct: float = Field(..., gt=0, description="Average win percentage")
    avg_loss_pct: float = Field(..., gt=0, description="Average loss percentage")
    capital: float = Field(default=10000, gt=0, description="Capital for calculation")
    current_price: float = Field(default=50000, gt=0, description="Price for calculation")
    mode: str = Field(default="FRACTIONAL", description="Kelly mode")

    @validator("mode")
    def validate_mode(cls, v):
        valid_modes = ["FULL", "FRACTIONAL", "DYNAMIC"]
        if v.upper() not in valid_modes:
            raise ValueError(f"Mode must be one of: {valid_modes}")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "win_rate": 0.60,
                "avg_win_pct": 2.0,
                "avg_loss_pct": 1.5,
                "capital": 10000,
                "current_price": 50000,
                "mode": "FRACTIONAL"
            }
        }


class RecordTradeRequest(BaseModel):
    """Request model for recording a trade"""
    trade_id: str = Field(..., description="Unique trade identifier")
    symbol: str = Field(..., description="Trading pair (e.g., 'BTCUSDT/ETHUSDT')")
    entry_time: datetime = Field(..., description="Trade entry timestamp")
    exit_time: datetime = Field(..., description="Trade exit timestamp")
    entry_price: float = Field(..., gt=0, description="Entry price")
    exit_price: float = Field(..., gt=0, description="Exit price")
    pnl: float = Field(..., description="Profit/Loss in base currency")
    pnl_pct: float = Field(..., description="Profit/Loss as percentage")
    strategy: str = Field(default="stat_arb", description="Strategy name")

    class Config:
        json_schema_extra = {
            "example": {
                "trade_id": "stat_arb_123",
                "symbol": "BTCUSDT/ETHUSDT",
                "entry_time": "2025-12-11T10:00:00Z",
                "exit_time": "2025-12-11T12:30:00Z",
                "entry_price": 50000,
                "exit_price": 51000,
                "pnl": 100,
                "pnl_pct": 2.0,
                "strategy": "pairs_trading"
            }
        }


class RecordTradeResponse(BaseModel):
    """Response model for recording a trade"""
    success: bool
    message: str
    updated_stats: Dict[str, Any]


# ==========================================
# API Endpoint Handlers
# ==========================================

@router.get("/kelly-stats", response_model=KellyStatsResponse)
async def get_kelly_stats():
    """
    Get Kelly Criterion statistics and current recommendations

    Returns comprehensive Kelly statistics including:
    - Current Kelly fraction and full Kelly percentage
    - Win rate and average win/loss percentages
    - Profit factor and expectancy
    - Current streak information
    - Position size limits

    This endpoint is useful for:
    - Monitoring Kelly-based position sizing health
    - Dashboard display of risk metrics
    - API integration for external tools
    """
    try:
        sizer = get_kelly_sizer()
        stats = sizer.get_kelly_stats()

        logger.info(
            f"Kelly stats requested: "
            f"trades={stats['trades']['total_trades']}, "
            f"win_rate={stats['performance']['win_rate']:.2%}, "
            f"kelly={stats['kelly']['full_kelly_pct']:.2f}%"
        )

        return KellyStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get Kelly stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve Kelly statistics: {str(e)}"
        )


@router.post("/kelly-calculate", response_model=KellyCalculateResponse)
async def calculate_kelly_position(request: KellyCalculateRequest):
    """
    Calculate optimal position size using Kelly Criterion

    Uses the current trade history to calculate:
    - Full Kelly percentage based on win rate and odds
    - Applies fractional Kelly for safety (default 25%)
    - Optionally adjusts by signal confidence
    - Applies risk limits based on stop loss

    Request body:
    - capital: Available trading capital
    - current_price: Current asset price
    - mode: FULL, FRACTIONAL, or DYNAMIC
    - signal_confidence: Optional confidence adjustment (0-1)
    - stop_loss_pct: Optional stop loss for risk limiting

    Returns:
    - Recommended position size (% and value)
    - Kelly calculation details
    - Human-readable reasoning
    """
    try:
        sizer = get_kelly_sizer()

        # Map mode string to enum
        mode = KellyMode(request.mode)

        # Calculate position size
        result = sizer.calculate_position_size(
            capital=request.capital,
            current_price=request.current_price,
            mode=mode,
            signal_confidence=request.signal_confidence,
            stop_loss_pct=request.stop_loss_pct
        )

        logger.info(
            f"Kelly position calculated: "
            f"mode={mode.value}, "
            f"size={result.position_size_pct:.2f}%, "
            f"value=${float(result.position_value):.2f}"
        )

        return KellyCalculateResponse(
            position_size_pct=result.position_size_pct,
            position_value=float(result.position_value),
            quantity=float(result.quantity),
            full_kelly_pct=result.full_kelly_pct,
            kelly_fraction_used=result.kelly_fraction_used,
            mode=result.mode.value,
            win_rate=result.win_rate,
            avg_win_pct=result.avg_win_pct,
            avg_loss_pct=result.avg_loss_pct,
            edge=result.edge,
            confidence_level=result.confidence_level,
            reasoning=result.reasoning,
            metadata=result.metadata
        )

    except Exception as e:
        logger.error(f"Failed to calculate Kelly position: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate position size: {str(e)}"
        )


@router.post("/kelly-simulate", response_model=KellyCalculateResponse)
async def simulate_kelly_position(request: KellySimulateRequest):
    """
    Simulate Kelly position sizing with hypothetical parameters

    Useful for:
    - What-if analysis
    - Strategy optimization
    - Understanding Kelly sensitivity

    Does NOT affect actual trading - this is for analysis only.

    Request body:
    - win_rate: Hypothetical win rate (0-1)
    - avg_win_pct: Hypothetical average win percentage
    - avg_loss_pct: Hypothetical average loss percentage
    - capital: Capital for calculation
    - current_price: Price for quantity calculation
    - mode: Kelly mode

    Returns:
    - Simulated position size recommendation
    - Kelly calculation details
    """
    try:
        sizer = get_kelly_sizer()

        # Map mode string to enum
        mode = KellyMode(request.mode)

        # Run simulation
        result = sizer.simulate_kelly(
            win_rate=request.win_rate,
            avg_win_pct=request.avg_win_pct,
            avg_loss_pct=request.avg_loss_pct,
            capital=request.capital,
            current_price=request.current_price,
            mode=mode
        )

        logger.info(
            f"Kelly simulation: "
            f"W={request.win_rate:.0%}, "
            f"Win={request.avg_win_pct:.1f}%, "
            f"Loss={request.avg_loss_pct:.1f}% -> "
            f"Kelly={result.full_kelly_pct:.2f}%"
        )

        return KellyCalculateResponse(
            position_size_pct=result.position_size_pct,
            position_value=float(result.position_value),
            quantity=float(result.quantity),
            full_kelly_pct=result.full_kelly_pct,
            kelly_fraction_used=result.kelly_fraction_used,
            mode=result.mode.value,
            win_rate=result.win_rate,
            avg_win_pct=result.avg_win_pct,
            avg_loss_pct=result.avg_loss_pct,
            edge=result.edge,
            confidence_level=result.confidence_level,
            reasoning=result.reasoning,
            metadata=result.metadata
        )

    except Exception as e:
        logger.error(f"Failed to simulate Kelly position: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to simulate position size: {str(e)}"
        )


@router.post("/kelly-record-trade", response_model=RecordTradeResponse)
async def record_trade_for_kelly(request: RecordTradeRequest):
    """
    Record a completed trade for Kelly tracking

    Updates:
    - Rolling win rate (last 50 trades)
    - Average win/loss percentages
    - Current streak
    - Dynamic Kelly fraction

    Request body:
    - trade_id: Unique trade identifier
    - symbol: Trading pair
    - entry_time/exit_time: Trade timestamps
    - entry_price/exit_price: Trade prices
    - pnl: Profit/Loss
    - pnl_pct: P&L percentage
    - strategy: Strategy name

    Returns:
    - Success status
    - Updated statistics
    """
    try:
        sizer = get_kelly_sizer()

        # Determine if win or loss
        is_win = request.pnl > 0

        # Create trade record
        trade = TradeRecord(
            trade_id=request.trade_id,
            symbol=request.symbol,
            entry_time=request.entry_time,
            exit_time=request.exit_time,
            entry_price=request.entry_price,
            exit_price=request.exit_price,
            pnl=request.pnl,
            pnl_pct=request.pnl_pct,
            is_win=is_win,
            strategy=request.strategy
        )

        # Record trade
        sizer.record_trade(trade)

        # Get updated stats
        updated_stats = sizer.get_performance_stats()

        logger.info(
            f"Trade recorded: {request.trade_id} "
            f"{'WIN' if is_win else 'LOSS'} {request.pnl_pct:+.2f}%, "
            f"new win_rate={updated_stats['win_rate']:.2%}, "
            f"streak={updated_stats['current_streak']}"
        )

        return RecordTradeResponse(
            success=True,
            message=f"Trade {request.trade_id} recorded successfully",
            updated_stats={
                "win_rate": updated_stats['win_rate'],
                "total_trades": updated_stats['total_trades'],
                "current_streak": updated_stats['current_streak'],
                "kelly_fraction": updated_stats['current_kelly_fraction'],
                "expectancy": updated_stats['expectancy']
            }
        )

    except Exception as e:
        logger.error(f"Failed to record trade: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to record trade: {str(e)}"
        )


@router.get("/kelly-comparison")
async def get_kelly_comparison(
    win_rate: float = Query(0.55, ge=0.01, le=0.99, description="Win rate"),
    avg_win_pct: float = Query(2.0, gt=0, description="Average win %"),
    avg_loss_pct: float = Query(1.5, gt=0, description="Average loss %"),
):
    """
    Compare different Kelly modes for given parameters

    Returns side-by-side comparison of:
    - Full Kelly (theoretical maximum)
    - Fractional Kelly (25% - conservative)
    - Half Kelly (50% - moderate)

    Useful for understanding risk/reward tradeoffs.
    """
    try:
        sizer = get_kelly_sizer()

        # Simulate all modes
        results = {}

        for mode_name, mode in [
            ("full_kelly", KellyMode.FULL),
            ("fractional_kelly_25", KellyMode.FRACTIONAL),
            ("dynamic_kelly", KellyMode.DYNAMIC),
        ]:
            result = sizer.simulate_kelly(
                win_rate=win_rate,
                avg_win_pct=avg_win_pct,
                avg_loss_pct=avg_loss_pct,
                mode=mode
            )

            results[mode_name] = {
                "mode": mode.value,
                "position_size_pct": result.position_size_pct,
                "full_kelly_pct": result.full_kelly_pct,
                "kelly_fraction": result.kelly_fraction_used,
                "edge": result.edge
            }

        # Calculate expected edge
        edge = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)

        return {
            "parameters": {
                "win_rate": win_rate,
                "avg_win_pct": avg_win_pct,
                "avg_loss_pct": avg_loss_pct,
                "edge": edge,
                "has_edge": edge > 0
            },
            "comparison": results,
            "recommendation": (
                "Full Kelly" if edge > 2.0 else
                "Fractional Kelly (25%)" if edge > 0.5 else
                "Conservative sizing" if edge > 0 else
                "No trade - negative edge"
            )
        }

    except Exception as e:
        logger.error(f"Failed to compare Kelly modes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare Kelly modes: {str(e)}"
        )


@router.delete("/kelly-reset")
async def reset_kelly_tracking():
    """
    Reset Kelly tracking data

    Clears:
    - All trade history
    - Streak information
    - Dynamic Kelly fraction

    Use with caution - this cannot be undone.
    """
    try:
        from app.risk.kelly_position_sizing import reset_kelly_sizer

        reset_kelly_sizer()

        logger.warning("Kelly tracking reset by API call")

        return {
            "success": True,
            "message": "Kelly tracking reset to initial state"
        }

    except Exception as e:
        logger.error(f"Failed to reset Kelly tracking: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset Kelly tracking: {str(e)}"
        )
