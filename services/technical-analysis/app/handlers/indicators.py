"""
Basic Indicator Endpoint Handlers
Extracted from main.py - Responsibility: HTTP endpoints for basic indicators
"""

import logging
from fastapi import HTTPException, Query

from app.models import RSIResponse, MACDResponse, BollingerBandsResponse, MovingAverageResponse
from app.services import IndicatorService

logger = logging.getLogger(__name__)


async def get_rsi(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval"),
    period: int = Query(default=14, ge=2, le=200, description="RSI period"),
    limit: int = Query(default=200, ge=50, le=1000, description="Number of candles to fetch")
) -> RSIResponse:
    """Calculate RSI (Relative Strength Index)"""
    try:
        data = await IndicatorService.calculate_rsi(symbol, interval, period, limit)
        return RSIResponse(
            symbol=symbol,
            interval=interval,
            timestamp=data["timestamp"],
            rsi=data["rsi"],
            signal=data["signal"],
            confidence=data["confidence"],
            parameters={"period": period}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating RSI for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_macd(
    symbol: str,
    interval: str = Query(default="60"),
    fast: int = Query(default=12, ge=2, le=50),
    slow: int = Query(default=26, ge=10, le=200),
    signal: int = Query(default=9, ge=2, le=50),
    limit: int = Query(default=200, ge=100, le=1000)
) -> MACDResponse:
    """Calculate MACD (Moving Average Convergence Divergence)"""
    try:
        data = await IndicatorService.calculate_macd(symbol, interval, fast, slow, signal, limit)
        return MACDResponse(
            symbol=symbol,
            interval=interval,
            timestamp=data["timestamp"],
            macd_line=data["macd_line"],
            signal_line=data["signal_line"],
            histogram=data["histogram"],
            signal=data["signal"],
            confidence=data["confidence"],
            parameters={"fast": fast, "slow": slow, "signal": signal}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating MACD for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_bollinger_bands(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=5, le=100),
    std_dev: float = Query(default=2.0, ge=1.0, le=3.0),
    limit: int = Query(default=200, ge=50, le=1000)
) -> BollingerBandsResponse:
    """Calculate Bollinger Bands"""
    try:
        data = await IndicatorService.calculate_bollinger_bands(symbol, interval, period, std_dev, limit)
        return BollingerBandsResponse(
            symbol=symbol,
            interval=interval,
            timestamp=data["timestamp"],
            upper_band=data["upper_band"],
            middle_band=data["middle_band"],
            lower_band=data["lower_band"],
            current_price=data["current_price"],
            signal=data["signal"],
            confidence=data["confidence"],
            parameters={"period": period, "std_dev": std_dev}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating Bollinger Bands for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_sma(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=2, le=200),
    limit: int = Query(default=200, ge=50, le=1000)
) -> MovingAverageResponse:
    """Calculate SMA (Simple Moving Average)"""
    try:
        data = await IndicatorService.calculate_sma(symbol, interval, period, limit)
        return MovingAverageResponse(
            symbol=symbol,
            interval=interval,
            timestamp=data["timestamp"],
            ma_type="SMA",
            value=data["value"],
            current_price=data["current_price"],
            signal=data["signal"],
            confidence=data["confidence"],
            parameters={"period": period}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating SMA for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_ema(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=2, le=200),
    limit: int = Query(default=200, ge=50, le=1000)
) -> MovingAverageResponse:
    """Calculate EMA (Exponential Moving Average)"""
    try:
        data = await IndicatorService.calculate_ema(symbol, interval, period, limit)
        return MovingAverageResponse(
            symbol=symbol,
            interval=interval,
            timestamp=data["timestamp"],
            ma_type="EMA",
            value=data["value"],
            current_price=data["current_price"],
            signal=data["signal"],
            confidence=data["confidence"],
            parameters={"period": period}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating EMA for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
