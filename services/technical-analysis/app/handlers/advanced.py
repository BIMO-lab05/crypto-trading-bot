"""
Advanced Indicator Endpoint Handlers
Extracted from main.py - Responsibility: Advanced indicator endpoints
"""

import logging
from typing import Optional
from fastapi import HTTPException, Query

from app.config import get_settings
from app.services import IndicatorService

logger = logging.getLogger(__name__)

# Query() defaults below are evaluated once at import time from the Settings
# singleton — Settings is the single source of truth for endpoint defaults
# (pinned by tests/test_endpoint_defaults_from_settings.py).
settings = get_settings()


async def get_trend_filter(
    symbol: str,
    interval: str = Query(default="60"),
    fast_period: int = Query(default=settings.default_trend_fast_period, ge=10, le=100, description="Fast EMA period"),
    slow_period: int = Query(default=settings.default_trend_slow_period, ge=100, le=300, description="Slow EMA period"),
    limit: int = Query(default=settings.default_trend_limit, ge=200, le=1000)
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
    period: int = Query(default=settings.default_volume_period, ge=5, le=50, description="Volume averaging period"),
    signal_type: str = Query(default=settings.default_volume_signal_type, description="breakout or continuation"),
    limit: int = Query(default=settings.default_volume_limit, ge=30, le=200)  # INCREASED 2026-02-25: 50→100 for better volume analysis
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
    period: int = Query(default=settings.default_atr_period, ge=7, le=30, description="ATR period"),
    current_price: Optional[float] = Query(default=None, description="Entry price for position"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate ATR (Average True Range)

    Returns volatility-based risk management levels:
    - ATR: Average True Range value
    - Stop-loss: Entry +/- (2 x ATR)
    - Take-profit: Entry +/- (4 x ATR)
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
    period: int = Query(default=settings.default_stochastic_period, ge=5, le=30, description="Stochastic period"),
    smooth_k: int = Query(default=settings.default_stochastic_smooth_k, ge=1, le=10, description="K smoothing"),
    smooth_d: int = Query(default=settings.default_stochastic_smooth_d, ge=1, le=10, description="D smoothing"),
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


async def get_rsi_divergence(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=settings.default_rsi_divergence_period, ge=7, le=30, description="RSI period"),
    lookback: int = Query(default=settings.default_rsi_divergence_lookback, ge=10, le=50, description="Lookback for divergence detection"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate RSI Divergence

    Detects bullish and bearish divergences:
    - Bullish: Price makes lower low, RSI makes higher low
    - Bearish: Price makes higher high, RSI makes lower high
    """
    try:
        data = await IndicatorService.calculate_rsi_divergence(
            symbol, interval, period, lookback, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "period": period,
                "lookback": lookback
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating RSI Divergence for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_ichimoku(
    symbol: str,
    interval: str = Query(default="60"),
    tenkan_period: int = Query(default=settings.default_ichimoku_tenkan, ge=5, le=20, description="Tenkan-sen (conversion) period"),
    kijun_period: int = Query(default=settings.default_ichimoku_kijun, ge=20, le=50, description="Kijun-sen (base) period"),
    senkou_b_period: int = Query(default=settings.default_ichimoku_senkou_b, ge=40, le=100, description="Senkou Span B period"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate Ichimoku Cloud

    Returns all 5 components:
    - Tenkan-sen (Conversion Line): Short-term trend
    - Kijun-sen (Base Line): Medium-term trend
    - Senkou Span A: Leading span A (cloud boundary)
    - Senkou Span B: Leading span B (cloud boundary)
    - Chikou Span: Lagging span (current close shifted back)
    """
    try:
        data = await IndicatorService.calculate_ichimoku(
            symbol, interval, tenkan_period, kijun_period, senkou_b_period, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "tenkan_period": tenkan_period,
                "kijun_period": kijun_period,
                "senkou_b_period": senkou_b_period
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating Ichimoku for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_enhanced_sqzmom(
    symbol: str,
    interval: str = Query(default="60"),
    bb_period: int = Query(default=settings.default_sqzmom_bb_period, ge=10, le=50, description="Bollinger Bands period"),
    bb_mult: float = Query(default=settings.default_sqzmom_bb_mult, ge=1.0, le=3.0, description="Bollinger Bands multiplier"),
    kc_period: int = Query(default=settings.default_sqzmom_kc_period, ge=10, le=50, description="Keltner Channel period"),
    kc_mult: float = Query(default=settings.default_sqzmom_kc_mult, ge=1.0, le=3.0, description="Keltner Channel multiplier"),
    mom_period: int = Query(default=settings.default_sqzmom_mom_period, ge=5, le=30, description="Momentum period"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate Enhanced Squeeze Momentum

    Identifies squeeze conditions and momentum direction:
    - Squeeze ON: BB inside KC (low volatility compression)
    - Squeeze OFF: BB outside KC (volatility expansion)
    - Momentum: Linear regression based momentum histogram
    - Firing: First bar after squeeze releases
    """
    try:
        data = await IndicatorService.calculate_enhanced_sqzmom(
            symbol, interval, bb_period, bb_mult, kc_period, kc_mult, mom_period, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "bb_period": bb_period,
                "bb_mult": bb_mult,
                "kc_period": kc_period,
                "kc_mult": kc_mult,
                "mom_period": mom_period
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating Enhanced SQZMOM for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_adx(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=settings.default_adx_period, ge=7, le=30, description="ADX period"),
    trending_threshold: float = Query(default=settings.default_adx_trending_threshold, ge=15.0, le=40.0, description="ADX threshold for TRENDING"),
    weak_trend_threshold: float = Query(default=settings.default_adx_weak_trend_threshold, ge=10.0, le=30.0, description="ADX threshold for WEAK_TREND"),
    strong_trend_threshold: float = Query(default=settings.default_adx_strong_trend_threshold, ge=25.0, le=50.0, description="ADX threshold for STRONG_TREND"),
    limit: int = Query(default=100, ge=50, le=500)
):
    """
    Calculate ADX (Average Directional Index)

    Measures trend strength and provides market regime classification:
    - ADX: Average Directional Index value (0-100)
    - +DI: Positive Directional Indicator (upward movement strength)
    - -DI: Negative Directional Indicator (downward movement strength)
    - Market Regime Classification:
      - STRONG_TREND: ADX >= strong_trend_threshold (default 30)
      - TRENDING: ADX >= trending_threshold (default 25)
      - WEAK_TREND: ADX >= weak_trend_threshold (default 20)
      - RANGING: ADX < weak_trend_threshold
    - Trend Direction: BULLISH (+DI > -DI), BEARISH (-DI > +DI), NEUTRAL

    Trading Applications:
    - Use trend-following strategies when ADX > 25
    - Use mean-reversion strategies when ADX < 20
    - +DI > -DI suggests bullish momentum
    - -DI > +DI suggests bearish momentum
    """
    try:
        data = await IndicatorService.calculate_adx(
            symbol, interval, period, trending_threshold,
            weak_trend_threshold, strong_trend_threshold, limit
        )
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": data["timestamp"],
            "data": data["data"],
            "parameters": {
                "period": period,
                "trending_threshold": trending_threshold,
                "weak_trend_threshold": weak_trend_threshold,
                "strong_trend_threshold": strong_trend_threshold
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating ADX for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
