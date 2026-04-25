"""
Grid Trading Strategy API Endpoints
Purpose: REST API for configuring and managing Grid Trading strategy

Provides endpoints for:
- Viewing current Grid Trading configuration
- Updating Grid Trading parameters
- Running Grid Trading backtests
- Viewing Grid Trading performance history
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from app.config import get_settings
from app.strategies.grid_trading_strategy import GridTradingStrategy
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig
from app.backtesting.strategy_base import OHLCV


# Router for Grid Trading endpoints
router = APIRouter(prefix="/grid-trading", tags=["grid-trading"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class GridTradingConfig(BaseModel):
    """Grid Trading strategy configuration"""
    grid_levels: int = Field(
        default=7,
        ge=3,
        le=30,
        description="Number of grid levels (3-30)"
    )
    grid_range_pct: float = Field(
        default=0.15,
        ge=0.01,
        le=0.50,
        description="Grid range as percentage (0.01-0.50 = 1%-50%)"
    )
    use_atr_spacing: bool = Field(
        default=False,
        description="Use ATR-based spacing (False = fixed spacing)"
    )
    max_positions: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum concurrent positions (1-10)"
    )
    position_size_pct: float = Field(
        default=0.015,
        ge=0.001,
        le=0.10,
        description="Position size as % of capital (0.001-0.10 = 0.1%-10%)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "grid_levels": 7,
                "grid_range_pct": 0.15,
                "use_atr_spacing": False,
                "max_positions": 3,
                "position_size_pct": 0.015
            }
        }


class BacktestRequest(BaseModel):
    """Request for running Grid Trading backtest"""
    symbol: str = Field(description="Trading pair symbol (e.g. BTCUSDT)")
    config: GridTradingConfig = Field(description="Grid Trading configuration")
    initial_equity: float = Field(default=10000.0, ge=100.0, description="Initial capital")
    commission_pct: float = Field(default=0.1, ge=0.0, le=1.0, description="Commission %")
    slippage_pct: float = Field(default=0.05, ge=0.0, le=1.0, description="Slippage %")

    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "BTCUSDT",
                "config": {
                    "grid_levels": 7,
                    "grid_range_pct": 0.15,
                    "use_atr_spacing": False,
                    "max_positions": 3,
                    "position_size_pct": 0.015
                },
                "initial_equity": 10000.0,
                "commission_pct": 0.1,
                "slippage_pct": 0.05
            }
        }


class BacktestResult(BaseModel):
    """Grid Trading backtest result"""
    symbol: str
    config: GridTradingConfig
    total_return_pct: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int
    max_drawdown_pct: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    test_date: datetime


class GridTradingStatus(BaseModel):
    """Current Grid Trading status"""
    enabled: bool
    active_symbols: List[str]
    current_config: GridTradingConfig
    total_grid_trades: int
    avg_return_pct: float


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/config", response_model=GridTradingConfig)
async def get_grid_trading_config():
    """
    Get current Grid Trading configuration

    Returns the currently active Grid Trading parameters
    that would be used for live trading.
    """
    settings = get_settings()

    # Return default optimized configuration
    # (In production, this would load from database/config)
    return GridTradingConfig(
        grid_levels=7,
        grid_range_pct=0.15,
        use_atr_spacing=False,
        max_positions=3,
        position_size_pct=0.015
    )


@router.put("/config", response_model=GridTradingConfig)
async def update_grid_trading_config(config: GridTradingConfig):
    """
    Update Grid Trading configuration

    Updates the Grid Trading parameters that will be used
    for future trades. Does not affect currently open positions.

    Args:
        config: New Grid Trading configuration

    Returns:
        Updated configuration
    """
    # Validate configuration
    if config.grid_levels < 3:
        raise HTTPException(status_code=400, detail="grid_levels must be >= 3")

    if config.grid_range_pct <= 0 or config.grid_range_pct > 0.50:
        raise HTTPException(status_code=400, detail="grid_range_pct must be 0.01-0.50")

    if config.position_size_pct <= 0 or config.position_size_pct > 0.10:
        raise HTTPException(status_code=400, detail="position_size_pct must be 0.001-0.10")

    # In production, save to database/config file
    # For now, return the validated config
    return config


@router.post("/backtest", response_model=BacktestResult)
async def run_grid_trading_backtest(request: BacktestRequest):
    """
    Run Grid Trading backtest

    Backtests the Grid Trading strategy with given configuration
    on historical data for the specified symbol.

    Args:
        request: Backtest configuration

    Returns:
        Backtest results with performance metrics

    Raises:
        HTTPException: If symbol data not available or backtest fails
    """
    try:
        # Load historical data
        # In production, fetch from market-data-service
        # For now, return error indicating data needed
        raise HTTPException(
            status_code=501,
            detail=(
                "Backtest endpoint requires historical data integration. "
                "Use the standalone backtest scripts in /scripts/ directory "
                "for now (test_grid_trading_backtest.py, optimize_grid_trading.py)"
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.get("/status", response_model=GridTradingStatus)
async def get_grid_trading_status():
    """
    Get Grid Trading status

    Returns current status of Grid Trading strategy including
    whether it's enabled, which symbols are trading, and
    performance summary.
    """
    settings = get_settings()

    # In production, fetch from database
    # For now, return placeholder
    return GridTradingStatus(
        enabled=False,  # Not yet integrated into auto-trader
        active_symbols=[],
        current_config=GridTradingConfig(),
        total_grid_trades=0,
        avg_return_pct=0.0
    )


@router.get("/performance")
async def get_grid_trading_performance(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(10, ge=1, le=100, description="Number of recent trades")
):
    """
    Get Grid Trading performance history

    Returns recent Grid Trading trades and their performance.

    Args:
        symbol: Optional symbol filter
        limit: Number of trades to return (1-100)

    Returns:
        List of recent Grid Trading trades with performance data
    """
    # In production, fetch from database
    # For now, return empty list
    return {
        "trades": [],
        "summary": {
            "total_trades": 0,
            "avg_return_pct": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0
        }
    }


@router.post("/enable")
async def enable_grid_trading(
    symbols: List[str] = Query(..., description="Symbols to enable Grid Trading for")
):
    """
    Enable Grid Trading for specified symbols

    Activates Grid Trading strategy for the given symbols.
    Grid will start placing orders on the next trading cycle.

    Args:
        symbols: List of symbols to enable (e.g. ["BTCUSDT", "ETHUSDT"])

    Returns:
        Confirmation message
    """
    if not symbols:
        raise HTTPException(status_code=400, detail="At least one symbol required")

    # In production, update database and notify auto-trader
    # For now, return error indicating not yet integrated
    raise HTTPException(
        status_code=501,
        detail=(
            "Grid Trading integration with auto-trader pending. "
            "See Step 4 in roadmap. Use backtest scripts for testing."
        )
    )


@router.post("/disable")
async def disable_grid_trading():
    """
    Disable Grid Trading

    Deactivates Grid Trading strategy for all symbols.
    Existing positions will be closed according to grid exit rules.

    Returns:
        Confirmation message
    """
    # In production, update database and notify auto-trader
    # For now, return error
    raise HTTPException(
        status_code=501,
        detail="Grid Trading integration with auto-trader pending"
    )


@router.get("/optimized-params")
async def get_optimized_parameters(
    symbol: Optional[str] = Query(None, description="Get optimized params for symbol")
):
    """
    Get optimized Grid Trading parameters

    Returns the optimized parameters from walk-forward validation
    and parameter optimization runs.

    Args:
        symbol: Optional symbol to get specific optimizations for

    Returns:
        Optimized parameters and their performance metrics
    """
    # Return the best parameters from optimization (from Step 1 results)
    optimized = {
        "best_overall": {
            "grid_levels": 7,
            "grid_range_pct": 0.15,
            "use_atr_spacing": False,
            "max_positions": 3,
            "position_size_pct": 0.015,
            "performance": {
                "composite_score": 26.4,
                "avg_return_pct": -0.00,
                "avg_sharpe": -0.05,
                "avg_win_rate": 37.7
            },
            "source": "Parameter optimization (108 combinations tested)",
            "date": "2025-12-08"
        },
        "by_symbol": {
            "SOLUSDT": {
                "return_pct": -0.00,
                "sharpe": -0.28,
                "win_rate": 34.1,
                "trades": 88
            },
            "LTCUSDT": {
                "return_pct": +0.00,
                "sharpe": +0.02,
                "win_rate": 42.1,
                "trades": 76
            },
            "BNBUSDT": {
                "return_pct": +0.00,
                "sharpe": +0.13,
                "win_rate": 37.0,
                "trades": 54
            }
        }
    }

    if symbol:
        if symbol in optimized["by_symbol"]:
            return {
                "symbol": symbol,
                **optimized["best_overall"],
                "symbol_performance": optimized["by_symbol"][symbol]
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No optimized parameters found for {symbol}"
            )

    return optimized
