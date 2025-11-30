"""
Technical Analysis Service - FastAPI Application
Purpose: REST API for technical indicators and trading signals

REFACTORED: Phase 3 Complete - Using modular handlers
Architecture: main.py -> handlers -> services -> domain
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path
from fastapi import FastAPI, Query

from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.fetcher import get_fetcher, close_fetcher
from app.models import (
    HealthResponse,
    ReadyResponse,
    RSIResponse,
    MACDResponse,
    BollingerBandsResponse,
    MovingAverageResponse
)

# Import all handler functions (Phase 3: Modular architecture)
from app.handlers import (
    health_check,
    readiness_check,
    get_rsi,
    get_macd,
    get_bollinger_bands,
    get_sma,
    get_ema,
    get_trend_filter,
    get_volume_confirmation,
    get_atr,
    get_stochastic,
    get_rsi_divergence,
    get_ichimoku,
    get_enhanced_sqzmom,
    get_adx,
    get_aggregated_signal,
    get_multi_timeframe_analysis,
    get_sqzmom,
    get_sqzmom_strategy_signal,
    get_sqzmom_backtest_data
)

# Fixed: Create logs directory to prevent startup crashes (Critical Issue #6)
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

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
    """
    Lifespan context manager for startup and shutdown

    Fixed: Wrapped in try/finally to ensure HTTP client cleanup happens
    even if startup fails (Critical Issue #7 - HTTP Client Resource Leak)
    """
    logger.info(f"Starting {settings.service_name} on port {settings.service_port}")
    logger.info(f"Market Data URL: {settings.market_data_url}")
    logger.info("Using modular architecture (Phase 3 refactoring complete)")

    try:
        # Check Market Data Service connection
        fetcher = get_fetcher()
        is_healthy = await fetcher.health_check()
        if is_healthy:
            logger.info("Market Data Service connection verified")
        else:
            logger.warning("Market Data Service not available")

        yield

    finally:
        # Cleanup - guaranteed to run even if startup or yield fails
        logger.info("Shutting down Technical Analysis Service")
        await close_fetcher()


# FastAPI app
app = FastAPI(
    title="Technical Analysis Service",
    description="Calculate technical indicators and generate trading signals",
    version="2.2.0",  # Updated: Added ADX indicator for market regime detection
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


# ============================================================================
# HEALTH ENDPOINTS
# ============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health():
    """Health check endpoint"""
    return await health_check()


@app.get("/ready", response_model=ReadyResponse, tags=["Health"])
async def ready():
    """Readiness check endpoint"""
    return await readiness_check()


# ============================================================================
# BASIC INDICATOR ENDPOINTS
# ============================================================================

@app.get("/api/v1/indicators/rsi/{symbol}", response_model=RSIResponse, tags=["Indicators"])
async def rsi_endpoint(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval"),
    # RESEARCH-OPTIMIZED 2025-11-28: Period 9 optimal for crypto volatility (prev: 14)
    period: int = Query(default=9, ge=2, le=200, description="RSI period (optimized for crypto)"),
    limit: int = Query(default=200, ge=50, le=1000, description="Number of candles to fetch")
):
    """
    Calculate RSI (Relative Strength Index)

    RSI measures momentum and identifies overbought/oversold conditions.
    RESEARCH-OPTIMIZED: Using 80/20 thresholds for crypto (more extreme than 70/30)
    - RSI > 80: Overbought (potential sell)
    - RSI < 20: Oversold (potential buy)
    """
    return await get_rsi(symbol, interval, period, limit)


@app.get("/api/v1/indicators/macd/{symbol}", response_model=MACDResponse, tags=["Indicators"])
async def macd_endpoint(
    symbol: str,
    interval: str = Query(default="60"),
    # RESEARCH-OPTIMIZED 2025-11-28: 8/17/9 reduces lag for crypto (prev: 12/26/9)
    fast: int = Query(default=8, ge=2, le=50, description="Fast EMA period (optimized)"),
    slow: int = Query(default=17, ge=10, le=200, description="Slow EMA period (optimized)"),
    signal: int = Query(default=9, ge=2, le=50, description="Signal line period"),
    limit: int = Query(default=200, ge=100, le=1000)
):
    """
    Calculate MACD (Moving Average Convergence Divergence)

    RESEARCH-OPTIMIZED: Using 8/17/9 for faster response in crypto markets
    MACD is a trend-following momentum indicator.
    - MACD crosses above Signal: Bullish (buy)
    - MACD crosses below Signal: Bearish (sell)
    """
    return await get_macd(symbol, interval, fast, slow, signal, limit)


@app.get("/api/v1/indicators/bollinger/{symbol}", response_model=BollingerBandsResponse, tags=["Indicators"])
async def bollinger_endpoint(
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
    return await get_bollinger_bands(symbol, interval, period, std_dev, limit)


@app.get("/api/v1/indicators/sma/{symbol}", response_model=MovingAverageResponse, tags=["Indicators"])
async def sma_endpoint(
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
    return await get_sma(symbol, interval, period, limit)


@app.get("/api/v1/indicators/ema/{symbol}", response_model=MovingAverageResponse, tags=["Indicators"])
async def ema_endpoint(
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
    return await get_ema(symbol, interval, period, limit)


# ============================================================================
# ADVANCED INDICATOR ENDPOINTS (Phase 1 Enhancements)
# ============================================================================

@app.get("/api/v1/indicators/trend/{symbol}", tags=["Indicators"])
async def trend_filter_endpoint(
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
    return await get_trend_filter(symbol, interval, fast_period, slow_period, limit)


@app.get("/api/v1/indicators/volume/{symbol}", tags=["Indicators"])
async def volume_confirmation_endpoint(
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
    return await get_volume_confirmation(symbol, interval, period, signal_type, limit)


@app.get("/api/v1/indicators/atr/{symbol}", tags=["Indicators"])
async def atr_endpoint(
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
    - Stop-loss: Entry +/- (2 x ATR)
    - Take-profit: Entry +/- (4 x ATR) [1:2 risk/reward]
    - Volatility: LOW/MEDIUM/HIGH/EXTREME classification

    **Adapts to market conditions**:
    - Calm market (ATR < 1%): Tight stops
    - Normal market (ATR 1-2%): Standard stops
    - Volatile market (ATR 2-4%): Wide stops
    - Extreme volatility (ATR > 4%): Very wide stops
    """
    return await get_atr(symbol, interval, period, current_price, limit)


@app.get("/api/v1/indicators/adx/{symbol}", tags=["Indicators"])
async def adx_endpoint(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=14, ge=7, le=30, description="ADX period"),
    trending_threshold: float = Query(default=25.0, ge=15.0, le=40.0, description="ADX threshold for TRENDING"),
    weak_trend_threshold: float = Query(default=20.0, ge=10.0, le=30.0, description="ADX threshold for WEAK_TREND"),
    strong_trend_threshold: float = Query(default=30.0, ge=25.0, le=50.0, description="ADX threshold for STRONG_TREND"),
    limit: int = Query(default=100, ge=50, le=500)
):
    """
    Calculate ADX (Average Directional Index)

    **Market Regime Detection**: Identifies trend strength for strategy selection

    Measures trend strength and provides market regime classification:
    - ADX: Average Directional Index value (0-100)
    - +DI: Positive Directional Indicator (upward movement strength)
    - -DI: Negative Directional Indicator (downward movement strength)

    **Market Regime Classification**:
    - STRONG_TREND: ADX >= 30 (use aggressive trend-following)
    - TRENDING: ADX 25-30 (use standard trend-following)
    - WEAK_TREND: ADX 20-25 (cautious trend-following)
    - RANGING: ADX < 20 (use mean-reversion strategies)

    **Trend Direction**:
    - BULLISH: +DI > -DI (upward momentum dominates)
    - BEARISH: -DI > +DI (downward momentum dominates)
    - NEUTRAL: +DI approximately equals -DI

    **Trading Applications**:
    - Trend-following works best when ADX > 25
    - Mean-reversion works best when ADX < 20
    - Adjust position sizing based on ADX (higher ADX = more confidence)
    """
    return await get_adx(
        symbol, interval, period, trending_threshold,
        weak_trend_threshold, strong_trend_threshold, limit
    )


@app.get("/api/v1/indicators/stochastic/{symbol}", tags=["Indicators"])
async def stochastic_endpoint(
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
    return await get_stochastic(symbol, interval, period, smooth_k, smooth_d, limit)


@app.get("/api/v1/indicators/rsi-divergence/{symbol}", tags=["Indicators"])
async def rsi_divergence_endpoint(
    symbol: str,
    interval: str = Query(default="60"),
    period: int = Query(default=14, ge=7, le=30, description="RSI period"),
    lookback: int = Query(default=20, ge=10, le=50, description="Lookback for divergence detection"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate RSI Divergence

    **Detects bullish and bearish divergences for high-probability reversal signals**

    Divergence Types:
    - **Bullish Divergence**: Price makes lower low, RSI makes higher low (BUY signal)
    - **Bearish Divergence**: Price makes higher high, RSI makes lower high (SELL signal)
    - **Hidden Bullish**: Price makes higher low, RSI makes lower low (trend continuation BUY)
    - **Hidden Bearish**: Price makes lower high, RSI makes higher high (trend continuation SELL)

    **Signal Confidence** based on divergence strength and RSI zone
    """
    return await get_rsi_divergence(symbol, interval, period, lookback, limit)


@app.get("/api/v1/indicators/ichimoku/{symbol}", tags=["Indicators"])
async def ichimoku_endpoint(
    symbol: str,
    interval: str = Query(default="60"),
    tenkan_period: int = Query(default=9, ge=5, le=20, description="Tenkan-sen (conversion) period"),
    kijun_period: int = Query(default=26, ge=20, le=50, description="Kijun-sen (base) period"),
    senkou_b_period: int = Query(default=52, ge=40, le=100, description="Senkou Span B period"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate Ichimoku Cloud (Ichimoku Kinko Hyo)

    **Complete trend and support/resistance analysis in one indicator**

    Components:
    - **Tenkan-sen**: Short-term trend (9-period midpoint)
    - **Kijun-sen**: Medium-term trend (26-period midpoint)
    - **Senkou Span A**: Leading span A (Tenkan+Kijun midpoint, shifted 26 forward)
    - **Senkou Span B**: Leading span B (52-period midpoint, shifted 26 forward)
    - **Chikou Span**: Lagging span (current close, shifted 26 back)

    **Trading Signals**:
    - BUY: Price above cloud + TK cross bullish + Chikou above price
    - SELL: Price below cloud + TK cross bearish + Chikou below price
    - HOLD: Inside cloud or conflicting signals
    """
    return await get_ichimoku(symbol, interval, tenkan_period, kijun_period, senkou_b_period, limit)


@app.get("/api/v1/indicators/sqzmom-enhanced/{symbol}", tags=["Indicators"])
async def enhanced_sqzmom_endpoint(
    symbol: str,
    interval: str = Query(default="60"),
    bb_period: int = Query(default=20, ge=10, le=50, description="Bollinger Bands period"),
    bb_mult: float = Query(default=2.0, ge=1.0, le=3.0, description="Bollinger Bands multiplier"),
    kc_period: int = Query(default=20, ge=10, le=50, description="Keltner Channel period"),
    kc_mult: float = Query(default=1.5, ge=1.0, le=3.0, description="Keltner Channel multiplier"),
    mom_period: int = Query(default=12, ge=5, le=30, description="Momentum period"),
    limit: int = Query(default=200, ge=100, le=500)
):
    """
    Calculate Enhanced Squeeze Momentum

    **Advanced version with squeeze firing detection and momentum histogram**

    Features:
    - **Squeeze State**: ON (BB inside KC), OFF (BB outside KC)
    - **Squeeze Firing**: First bar after squeeze releases (high probability breakout)
    - **Momentum**: Linear regression based histogram
    - **Color Coding**: Lime/Green (bullish), Red/Maroon (bearish)

    **Trading Signals**:
    - BUY: Squeeze fires + positive momentum + increasing
    - SELL: Squeeze fires + negative momentum + decreasing
    - HOLD: Squeeze still on or momentum unclear
    """
    return await get_enhanced_sqzmom(symbol, interval, bb_period, bb_mult, kc_period, kc_mult, mom_period, limit)


# ============================================================================
# SQUEEZE MOMENTUM INDICATOR ENDPOINTS (LazyBear SQZMOM)
# ============================================================================

@app.get("/api/v1/indicators/sqzmom/{symbol}", tags=["Indicators"])
async def sqzmom_endpoint(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval in minutes"),
    bb_length: int = Query(default=20, ge=5, le=100, description="Bollinger Bands period"),
    bb_mult: float = Query(default=2.0, ge=1.0, le=3.0, description="Bollinger Bands std dev multiplier"),
    kc_length: int = Query(default=20, ge=5, le=100, description="Keltner Channel period"),
    kc_mult: float = Query(default=1.5, ge=1.0, le=3.0, description="Keltner Channel ATR multiplier"),
    use_true_range: bool = Query(default=True, description="Use True Range for Keltner Channels"),
    limit: int = Query(default=200, ge=50, le=1000, description="Number of candles to fetch")
):
    """
    Calculate Squeeze Momentum Indicator (SQZMOM) by LazyBear

    **Identifies low-volatility squeeze conditions and momentum direction for breakout trading**

    The Squeeze Momentum Indicator combines:
    1. **Bollinger Bands**: Volatility-based bands using standard deviation
    2. **Keltner Channels**: ATR-based channels using average true range
    3. **Squeeze Detection**: BB inside KC = squeeze ON (volatility compression)
    4. **Momentum**: Linear regression of price deviation from midpoint

    **Squeeze States**:
    - **Squeeze ON**: BB inside KC - Low volatility, potential breakout building
    - **Squeeze OFF**: BB outside KC - Breakout in progress
    - **Transitional**: Neither condition - Market in flux

    **Momentum Colors** (matching TradingView):
    - **Lime**: Positive momentum increasing (strongest bullish)
    - **Green**: Positive momentum decreasing (weakening bullish)
    - **Red**: Negative momentum decreasing (strongest bearish)
    - **Maroon**: Negative momentum increasing (weakening bearish)

    **Trading Signals**:
    - **BUY**: Squeeze released + positive momentum (lime/green bars)
    - **SELL**: Squeeze released + negative momentum (red/maroon bars)
    - **HOLD**: Squeeze active or unclear momentum

    **Parameters**:
    - Standard: BB(20, 2.0), KC(20, 1.5), True Range enabled
    - Sensitive: Lower periods (BB=15, KC=15) for faster signals
    - Conservative: Higher periods (BB=25, KC=25) for slower signals

    **Best For**: Breakout trading, range breakouts, volatility expansion trades
    """
    return await get_sqzmom(
        symbol=symbol,
        interval=interval,
        bb_length=bb_length,
        bb_mult=bb_mult,
        kc_length=kc_length,
        kc_mult=kc_mult,
        use_true_range=use_true_range,
        limit=limit
    )


@app.get("/api/v1/strategies/sqzmom/signal/{symbol}", tags=["Strategies"])
async def sqzmom_strategy_endpoint(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval in minutes"),
    min_momentum: float = Query(default=0.5, ge=0.1, le=5.0, description="Minimum momentum threshold for entry"),
    stop_loss_pct: float = Query(default=2.0, ge=0.5, le=10.0, description="Stop loss percentage"),
    take_profit_pct: float = Query(default=4.0, ge=1.0, le=20.0, description="Take profit percentage"),
    require_squeeze_release: bool = Query(default=True, description="Only trade on squeeze release"),
    require_volume: bool = Query(default=False, description="Require volume confirmation")
):
    """
    Get trading signal from Squeeze Momentum Strategy

    **Full trading strategy based on SQZMOM indicator with entry/exit rules**

    **Entry Conditions** (ALL must be met):
    1. **Momentum Threshold**: abs(momentum) > min_momentum
    2. **Momentum Direction**: Positive for LONG, Negative for SHORT
    3. **Squeeze Condition**:
       - Strict mode (require_squeeze_release=True): Only on squeeze release
       - Relaxed mode (require_squeeze_release=False): Also on accelerating momentum during squeeze
    4. **Volume Confirmation** (optional): Current volume > 1.2x average

    **Exit Conditions** (ANY triggers exit):
    1. **Momentum Reversal**: Color flip (bullish to bearish or vice versa)
    2. **Momentum Exhaustion**: Momentum declining for 3+ consecutive bars
    3. **Stop Loss**: Price moves stop_loss_pct% against position
    4. **Take Profit**: Price moves take_profit_pct% in favor

    **Risk Management**:
    - Default Risk/Reward: 1:2 (2% stop loss, 4% take profit)
    - Position size based on stop loss distance
    - Maximum 2% risk per trade recommended

    **Strategy Modes**:
    - **Conservative**: require_squeeze_release=True, min_momentum=1.0
    - **Standard**: require_squeeze_release=True, min_momentum=0.5 (default)
    - **Aggressive**: require_squeeze_release=False, min_momentum=0.3

    **Returns**:
    - Action: BUY/SELL/HOLD
    - Entry price, Stop loss, Take profit levels
    - Confidence score (0-1)
    - Detailed reasoning for signal
    """
    return await get_sqzmom_strategy_signal(
        symbol=symbol,
        interval=interval,
        min_momentum=min_momentum,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        require_squeeze_release=require_squeeze_release,
        require_volume=require_volume
    )


@app.get("/api/v1/indicators/sqzmom/{symbol}/backtest", tags=["Indicators"])
async def sqzmom_backtest_endpoint(
    symbol: str,
    interval: str = Query(default="60", description="Candlestick interval in minutes"),
    limit: int = Query(default=500, ge=100, le=2000, description="Number of historical candles")
):
    """
    Get historical Squeeze Momentum data for backtesting

    **Returns complete SQZMOM history for strategy backtesting and analysis**

    **Data Included**:
    - OHLCV candle data
    - Bollinger Bands (upper, basis, lower)
    - Keltner Channels (upper, basis, lower)
    - Squeeze states (on/off/transitional)
    - Momentum values and colors
    - Generated signals and confidence scores

    **Summary Statistics**:
    - Total bars analyzed
    - Squeeze ON percentage
    - BUY/SELL/HOLD signal counts
    - Momentum statistics (avg, max, min)

    **Use Cases**:
    - Backtest SQZMOM strategy performance
    - Optimize parameters (BB/KC periods, multipliers)
    - Analyze squeeze frequency and duration
    - Validate signal quality on historical data
    - Compare with actual trading results

    **Recommended Workflow**:
    1. Fetch historical data (500-1000 candles)
    2. Analyze squeeze patterns and momentum behavior
    3. Test different entry/exit rules
    4. Calculate win rate, risk/reward ratios
    5. Optimize parameters for specific market conditions
    """
    return await get_sqzmom_backtest_data(
        symbol=symbol,
        interval=interval,
        limit=limit
    )


# ============================================================================
# ANALYSIS ENDPOINTS (Complex Multi-Indicator Analysis)
# ============================================================================

@app.get("/api/v1/indicators/signal/{symbol}", tags=["Analysis"])
async def aggregated_signal_endpoint(
    symbol: str,
    interval: str = Query(default="60")
):
    """
    Get aggregated trading signal for a symbol/interval

    Combines multiple indicators into a single signal with confidence:
    - RSI (Relative Strength Index)
    - MACD (Moving Average Convergence Divergence)
    - Trend Filter (EMA-based trend detection)

    Returns weighted signal with confidence score (0-1)
    """
    return await get_aggregated_signal(symbol, interval)


@app.get("/api/v1/analysis/multi-timeframe/{symbol}", tags=["Analysis"])
async def multi_timeframe_endpoint(
    symbol: str,
    timeframes: str = Query(
        default="1,5,15,60,240,1440",
        description="Comma-separated timeframes in minutes"
    )
):
    """
    Analyze symbol across multiple timeframes for trend confirmation

    Returns:
    - Individual analysis for each timeframe
    - Alignment score (how many timeframes agree)
    - Overall recommendation based on consensus
    - Trading recommendation (Strong/Moderate/Weak signal)

    **Note**: Duplicate endpoint at line 651-694 removed (DRY principle)
    """
    return await get_multi_timeframe_analysis(symbol, timeframes)


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """Root endpoint with service information"""
    return {
        "service": settings.service_name,
        "version": "2.2.0",  # Updated: Added ADX indicator
        "status": "running",
        "architecture": "Modular (Phase 3 Complete)",
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
                "adx": "/api/v1/indicators/adx/{symbol} [MARKET REGIME]",
                "stochastic": "/api/v1/indicators/stochastic/{symbol} [PHASE 1]",
                "sqzmom": "/api/v1/indicators/sqzmom/{symbol} [LazyBear]"
            },
            "strategies": {
                "sqzmom_signal": "/api/v1/strategies/sqzmom/signal/{symbol}"
            },
            "analysis": {
                "multi_timeframe": "/api/v1/analysis/multi-timeframe/{symbol}",
                "aggregated_signal": "/api/v1/indicators/signal/{symbol}"
            },
            "backtesting": {
                "sqzmom_history": "/api/v1/indicators/sqzmom/{symbol}/backtest"
            }
        },
        "refactoring": {
            "status": "Phase 3 Complete",
            "original_lines": 987,
            "current_lines": "~500",
            "reduction": "49%",
            "modules": 9,
            "architecture": "main.py -> handlers -> services -> domain"
        },
        "new_features": {
            "sqzmom_indicator": "LazyBear's Squeeze Momentum Indicator",
            "sqzmom_strategy": "Complete trading strategy with entry/exit rules",
            "backtest_data": "Historical SQZMOM data for strategy validation",
            "adx_indicator": "ADX-based market regime detection (TRENDING/RANGING/WEAK_TREND)"
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
