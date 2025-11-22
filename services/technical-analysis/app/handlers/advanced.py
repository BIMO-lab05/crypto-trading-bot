"""
Advanced Indicator Endpoint Handlers
Extracted from main.py - Responsibility: Advanced indicator endpoints
"""

import logging
from typing import Optional
from fastapi import HTTPException, Query

from app.services import IndicatorService

logger = logging.getLogger(__name__)


async def get_trend_filter(
    symbol: str,
    interval: str = Query(default="60"),
    fast_period: int = Query(default=50, ge=10, le=100, description="Fast EMA period"),
    slow_period: int = Query(default=200, ge=100, le=300, description="Slow EMA period"),
    limit: int = Query(default=300, ge=200, le=1000)
):
    """
    Calculate Trend Filter using dual EMA system

    Uses 50 EMA and 200 EMA to identify market trend:
    - BULLISH: 50 EMA > 200 EMA with spread > 0.5%
    - BEARISH: 50 EMA < 200 EMA with spread > 0.5%
    - NEUTRAL: EMAs within 0.5% (choppy/sideways market)
    """
    try:
        data = await IndicatorService.calculate_trend_filter(
            symbol, interval, fast_period, slow_period, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "fast_period": fast_period,
                "slow_period": slow_period
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating trend filter for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_volume_confirmation(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=5, le=50, description="Volume averaging period"),
    signal_type: str = Query(default="breakout", description="breakout or continuation"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate Volume Confirmation

    Compares current volume to period average:
    - STRONG: Volume > 1.5x average
    - MODERATE: Volume 1.2-1.5x average
    - WEAK: Volume 1.0-1.2x average
    - INSUFFICIENT: Volume < 1.0x average
    """
    try:
        data = await IndicatorService.calculate_volume_confirmation(
            symbol, interval, period, signal_type, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "signal_type": signal_type,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {"period": period}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating volume confirmation for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_atr(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=14, ge=7, le=30, description="ATR period"),
    current_price: Optional[float] = Query(default=None, description="Entry price for position"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate ATR (Average True Range)

    Returns volatility-based risk management levels:
    - ATR: Average True Range value
    - Stop-loss: Entry ± (2 × ATR)
    - Take-profit: Entry ± (4 × ATR)
    - Volatility classification
    """
    try:
        data = await IndicatorService.calculate_atr(
            symbol, interval, period, current_price, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "current_price": data["current_price"],
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {"period": period}
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating ATR for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_stochastic(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=14, ge=5, le=30, description="Stochastic period"),
    smooth_k: int = Query(default=3, ge=1, le=10, description="K smoothing"),
    smooth_d: int = Query(default=3, ge=1, le=10, description="D smoothing"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate Stochastic Oscillator

    Returns momentum analysis:
    - %K: Fast stochastic (0-100)
    - %D: Slow stochastic (SMA of %K)
    - Condition: OVERBOUGHT (>80) / OVERSOLD (<20) / NEUTRAL
    - Crossover signals
    """
    try:
        data = await IndicatorService.calculate_stochastic(
            symbol, interval, period, smooth_k, smooth_d, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "period": period,
                "smooth_k": smooth_k,
                "smooth_d": smooth_d
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating Stochastic for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
