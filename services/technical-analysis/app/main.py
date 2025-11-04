"""
Technical Analysis Service - FastAPI Application
Purpose: REST API for technical indicators and trading signals
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.fetcher import get_fetcher, close_fetcher
from app.models import (
    HealthResponse,
    ReadyResponse,
    RSIResponse,
    MACDResponse,
    BollingerBandsResponse,
    MovingAverageResponse,
    SignalType
)
from app.indicators import (
    RSICalculator,
    MACDCalculator,
    BollingerBandsCalculator,
    SMACalculator,
    EMACalculator
)
from app.indicators.trend_filter import TrendFilter
from app.indicators.volume_confirmation import VolumeConfirmation
from app.indicators.atr import ATR
from app.indicators.stochastic import Stochastic

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(f"Market Data URL: {settings.market_data_url}")

    # Check Market Data Service connection
    fetcher = get_fetcher()
    is_healthy = await fetcher.health_check()
    if is_healthy:
        logger.info("✅ Market Data Service connection verified")
    else:
        logger.warning("⚠️ Market Data Service not available")

    yield

    # Cleanup
    logger.info("Shutting down Technical Analysis Service")
    await close_fetcher()


# FastAPI app
app = FastAPI(
    title="Technical Analysis Service",
    description="Calculate technical indicators and generate trading signals",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health endpoints
@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    fetcher = get_fetcher()
    market_data_healthy = await fetcher.health_check()

    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        market_data_connection=market_data_healthy,
        timestamp=int(time.time() * 1000)
    )


@app.get("/ready", response_model=ReadyResponse, tags=["Health"])
async def readiness_check():
    """Readiness check endpoint"""
    fetcher = get_fetcher()
    market_data_healthy = await fetcher.health_check()

    return ReadyResponse(
        status="ready" if market_data_healthy else "not_ready",
        service=settings.service_name,
        dependencies={
            "market_data_service": market_data_healthy
        },
        timestamp=int(time.time() * 1000)
    )


# RSI endpoint
@app.get("/api/v1/indicators/rsi/{symbol}", response_model=RSIResponse, tags=["Indicators"])
async def get_rsi(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval"),
    period: int = Query(default=14, ge=2, le=200, description="RSI period"),
    limit: int = Query(default=200, ge=50, le=1000, description="Number of candles to fetch")
):
    """
    Calculate RSI (Relative Strength Index)

    RSI measures momentum and identifies overbought/oversold conditions.
    - RSI > 70: Overbought (potential sell)
    - RSI < 30: Oversold (potential buy)
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available for symbol")

        calculator = RSICalculator(period=period)
        rsi_value, signal, confidence = calculator.calculate_with_signal(df)

        if rsi_value is None:
            raise HTTPException(status_code=400, detail="Insufficient data to calculate RSI")

        return RSIResponse(
            symbol=symbol,
            interval=interval,
            timestamp=int(df.index[-1].timestamp() * 1000),
            rsi=round(rsi_value, 2),
            signal=signal,
            confidence=confidence,
            parameters={"period": period}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating RSI for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# MACD endpoint
@app.get("/api/v1/indicators/macd/{symbol}", response_model=MACDResponse, tags=["Indicators"])
async def get_macd(
    symbol: str,
    interval: str = Query(default="60"),
    fast: int = Query(default=12, ge=2, le=50),
    slow: int = Query(default=26, ge=10, le=200),
    signal: int = Query(default=9, ge=2, le=50),
    limit: int = Query(default=200, ge=100, le=1000)
):
    """
    Calculate MACD (Moving Average Convergence Divergence)

    MACD is a trend-following momentum indicator.
    - MACD crosses above Signal: Bullish (buy)
    - MACD crosses below Signal: Bearish (sell)
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = MACDCalculator(fast, slow, signal)
        macd_data, macd_signal, confidence = calculator.calculate_with_signal(df)

        if macd_data is None:
            raise HTTPException(status_code=400, detail="Insufficient data to calculate MACD")

        return MACDResponse(
            symbol=symbol,
            interval=interval,
            timestamp=int(df.index[-1].timestamp() * 1000),
            macd_line=round(macd_data["macd_line"], 2),
            signal_line=round(macd_data["signal_line"], 2),
            histogram=round(macd_data["histogram"], 2),
            signal=macd_signal,
            confidence=confidence,
            parameters={"fast": fast, "slow": slow, "signal": signal}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating MACD for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Bollinger Bands endpoint
@app.get("/api/v1/indicators/bollinger/{symbol}", response_model=BollingerBandsResponse, tags=["Indicators"])
async def get_bollinger_bands(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=5, le=100),
    std_dev: float = Query(default=2.0, ge=1.0, le=3.0),
    limit: int = Query(default=200, ge=50, le=1000)
):
    """
    Calculate Bollinger Bands

    Bollinger Bands measure volatility.
    - Price at lower band: Oversold (potential buy)
    - Price at upper band: Overbought (potential sell)
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = BollingerBandsCalculator(period, std_dev)
        bb_data, bb_signal, confidence = calculator.calculate_with_signal(df)

        if bb_data is None:
            raise HTTPException(status_code=400, detail="Insufficient data to calculate Bollinger Bands")

        return BollingerBandsResponse(
            symbol=symbol,
            interval=interval,
            timestamp=int(df.index[-1].timestamp() * 1000),
            upper_band=round(bb_data["upper_band"], 2),
            middle_band=round(bb_data["middle_band"], 2),
            lower_band=round(bb_data["lower_band"], 2),
            current_price=round(bb_data["current_price"], 2),
            signal=bb_signal,
            confidence=confidence,
            parameters={"period": period, "std_dev": std_dev}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating Bollinger Bands for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# SMA endpoint
@app.get("/api/v1/indicators/sma/{symbol}", response_model=MovingAverageResponse, tags=["Indicators"])
async def get_sma(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=2, le=200),
    limit: int = Query(default=200, ge=50, le=1000)
):
    """
    Calculate SMA (Simple Moving Average)

    SMA is the average price over a period.
    - Price > SMA: Bullish trend
    - Price < SMA: Bearish trend
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = SMACalculator(period)
        sma_value = calculator.calculate(df)

        if sma_value is None:
            raise HTTPException(status_code=400, detail="Insufficient data to calculate SMA")

        current_price = float(df['close'].iloc[-1])
        signal, confidence = calculator.generate_signal(sma_value, current_price)

        return MovingAverageResponse(
            symbol=symbol,
            interval=interval,
            timestamp=int(df.index[-1].timestamp() * 1000),
            ma_type="SMA",
            value=round(sma_value, 2),
            current_price=round(current_price, 2),
            signal=signal,
            confidence=confidence,
            parameters={"period": period}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating SMA for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# EMA endpoint
@app.get("/api/v1/indicators/ema/{symbol}", response_model=MovingAverageResponse, tags=["Indicators"])
async def get_ema(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=2, le=200),
    limit: int = Query(default=200, ge=50, le=1000)
):
    """
    Calculate EMA (Exponential Moving Average)

    EMA gives more weight to recent prices.
    - Price > EMA: Bullish trend
    - Price < EMA: Bearish trend
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = EMACalculator(period)
        ema_value = calculator.calculate(df)

        if ema_value is None:
            raise HTTPException(status_code=400, detail="Insufficient data to calculate EMA")

        current_price = float(df['close'].iloc[-1])
        signal, confidence = calculator.generate_signal(ema_value, current_price)

        return MovingAverageResponse(
            symbol=symbol,
            interval=interval,
            timestamp=int(df.index[-1].timestamp() * 1000),
            ma_type="EMA",
            value=round(ema_value, 2),
            current_price=round(current_price, 2),
            signal=signal,
            confidence=confidence,
            parameters={"period": period}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating EMA for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Trend Filter endpoint (Phase 1 Enhancement)
@app.get("/api/v1/indicators/trend/{symbol}", tags=["Indicators"])
async def get_trend_filter(
    symbol: str,
    interval: str = Query(default="60"),
    fast_period: int = Query(default=50, ge=10, le=100, description="Fast EMA period"),
    slow_period: int = Query(default=200, ge=100, le=300, description="Slow EMA period"),
    limit: int = Query(default=300, ge=200, le=1000)
):
    """
    Calculate Trend Filter using dual EMA system

    **Phase 1 Enhancement**: Prevents counter-trend trading

    Uses 50 EMA and 200 EMA to identify market trend:
    - BULLISH: 50 EMA > 200 EMA with spread > 0.5%
    - BEARISH: 50 EMA < 200 EMA with spread > 0.5%
    - NEUTRAL: EMAs within 0.5% (choppy/sideways market)

    **Purpose**: Only allow trades in direction of major trend
    - BUY signals allowed only in BULLISH trend
    - SELL signals allowed only in BEARISH trend
    - HOLD recommended in NEUTRAL trend
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < slow_period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {slow_period} candles, got {len(df)}"
            )

        # Extract close prices
        close_prices = df['close'].tolist()

        # Calculate trend filter
        trend_filter = TrendFilter(fast_period=fast_period, slow_period=slow_period)
        result = trend_filter.calculate(close_prices)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "data": result,
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


# Volume Confirmation endpoint (Phase 1 Enhancement)
@app.get("/api/v1/indicators/volume/{symbol}", tags=["Indicators"])
async def get_volume_confirmation(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=20, ge=5, le=50, description="Volume averaging period"),
    signal_type: str = Query(default="breakout", description="breakout or continuation"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate Volume Confirmation

    **Phase 1 Enhancement**: Filters low-volume false breakouts

    Compares current volume to period average:
    - STRONG: Volume > 1.5x average (high confidence)
    - MODERATE: Volume 1.2-1.5x average (medium confidence)
    - WEAK: Volume 1.0-1.2x average (continuation only)
    - INSUFFICIENT: Volume < 1.0x average (reject signal)

    **Signal Types**:
    - breakout: Requires 1.2x volume (new support/resistance break)
    - continuation: Accepts 1.0x volume (existing trend continuation)
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period} candles, got {len(df)}"
            )

        # Extract volumes
        volumes = df['volume'].tolist()

        # Calculate volume confirmation
        volume_conf = VolumeConfirmation(period=period)
        result = volume_conf.calculate(volumes, signal_type)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "signal_type": signal_type,
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "data": result,
            "parameters": {"period": period}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating volume confirmation for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ATR endpoint (Phase 1 Enhancement)
@app.get("/api/v1/indicators/atr/{symbol}", tags=["Indicators"])
async def get_atr(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=14, ge=7, le=30, description="ATR period"),
    current_price: Optional[float] = Query(default=None, description="Entry price for position"),
    limit: int = Query(default=50, ge=30, le=200)
):
    """
    Calculate ATR (Average True Range)

    **Phase 1 Enhancement**: Dynamic stop-loss/take-profit based on volatility

    Returns volatility-based risk management levels:
    - ATR: Average True Range value
    - Stop-loss: Entry ± (2 × ATR)
    - Take-profit: Entry ± (4 × ATR) [1:2 risk/reward]
    - Volatility: LOW/MEDIUM/HIGH/EXTREME classification

    **Adapts to market conditions**:
    - Calm market (ATR < 1%): Tight stops
    - Normal market (ATR 1-2%): Standard stops
    - Volatile market (ATR 2-4%): Wide stops
    - Extreme volatility (ATR > 4%): Very wide stops
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period + 1:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + 1} candles, got {len(df)}"
            )

        # Extract OHLC data
        highs = df['high'].tolist()
        lows = df['low'].tolist()
        closes = df['close'].tolist()

        # Use last close as current price if not provided
        if current_price is None:
            current_price = closes[-1]

        # Calculate ATR
        atr_indicator = ATR(period=period)
        result = atr_indicator.calculate(highs, lows, closes, current_price)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "current_price": current_price,
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "data": result,
            "parameters": {"period": period}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating ATR for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Stochastic Oscillator endpoint (Phase 1 Enhancement)
@app.get("/api/v1/indicators/stochastic/{symbol}", tags=["Indicators"])
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

    **Phase 1 Enhancement**: Momentum confirmation indicator

    Returns momentum analysis:
    - %K: Fast stochastic (0-100)
    - %D: Slow stochastic (SMA of %K)
    - Condition: OVERBOUGHT (>80) / OVERSOLD (<20) / NEUTRAL
    - Crossover: BULLISH / BEARISH / NONE

    **Trading signals**:
    - BUY: Oversold + bullish crossover (high confidence)
    - SELL: Overbought + bearish crossover (high confidence)
    - HOLD: No clear signal

    **Best used with**:
    - Trend filter (confirm trend direction)
    - Volume confirmation (validate breakouts)
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period + smooth_k:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + smooth_k} candles, got {len(df)}"
            )

        # Extract OHLC data
        highs = df['high'].tolist()
        lows = df['low'].tolist()
        closes = df['close'].tolist()

        # Calculate Stochastic
        stoch = Stochastic(
            period=period,
            smooth_k=smooth_k,
            smooth_d=smooth_d
        )
        result = stoch.calculate(highs, lows, closes)

        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "data": result,
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


# Root endpoint
@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "ready": "/ready",
            "docs": "/docs",
            "indicators": {
                "rsi": "/api/v1/indicators/rsi/{symbol}",
                "macd": "/api/v1/indicators/macd/{symbol}",
                "bollinger": "/api/v1/indicators/bollinger/{symbol}",
                "sma": "/api/v1/indicators/sma/{symbol}",
                "ema": "/api/v1/indicators/ema/{symbol}",
                "trend_filter": "/api/v1/indicators/trend/{symbol} [PHASE 1]",
                "volume_confirmation": "/api/v1/indicators/volume/{symbol} [PHASE 1]",
                "atr": "/api/v1/indicators/atr/{symbol} [PHASE 1]",
                "stochastic": "/api/v1/indicators/stochastic/{symbol} [PHASE 1]"
            },
            "phase_1_status": "All 4 Phase 1 indicators implemented ✅"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug
    )
