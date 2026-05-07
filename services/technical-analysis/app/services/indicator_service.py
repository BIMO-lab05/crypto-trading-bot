"""
Indicator Service - Business Logic Layer
Handles indicator calculations and data fetching orchestration
Extracted from main.py using Strangler Fig pattern
"""

import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException

from app.fetcher import get_fetcher
from app.indicators import (
    RSICalculator,
    MACDCalculator,
    BollingerBandsCalculator,
    SMACalculator,
    EMACalculator,
    RSIDivergenceCalculator,
    IchimokuCalculator,
    EnhancedSqueezeMomentum,
    ADXCalculator,
)
from app.indicators.trend_filter import TrendFilter
from app.indicators.volume_confirmation import VolumeConfirmation
from app.indicators.atr import ATR
from app.indicators.stochastic import Stochastic

logger = logging.getLogger(__name__)


class IndicatorService:
    """
    Service for calculating technical indicators
    Encapsulates business logic for indicator calculations
    """

    @staticmethod
    async def calculate_rsi(
        symbol: str, interval: str, period: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate RSI indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available for symbol")

        calculator = RSICalculator(period=period)
        rsi_value, signal, confidence = calculator.calculate_with_signal(df)

        if rsi_value is None:
            raise HTTPException(
                status_code=400, detail="Insufficient data to calculate RSI"
            )

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "rsi": round(rsi_value, 2),
            "signal": signal,
            "confidence": confidence,
        }

    @staticmethod
    async def calculate_macd(
        symbol: str, interval: str, fast: int, slow: int, signal: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate MACD indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = MACDCalculator(fast, slow, signal)
        macd_data, macd_signal, confidence = calculator.calculate_with_signal(df)

        if macd_data is None:
            raise HTTPException(
                status_code=400, detail="Insufficient data to calculate MACD"
            )

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "macd_line": round(macd_data["macd_line"], 2),
            "signal_line": round(macd_data["signal_line"], 2),
            "histogram": round(macd_data["histogram"], 2),
            "signal": macd_signal,
            "confidence": confidence,
        }

    @staticmethod
    async def calculate_bollinger_bands(
        symbol: str, interval: str, period: int, std_dev: float, limit: int
    ) -> Dict[str, Any]:
        """Calculate Bollinger Bands indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = BollingerBandsCalculator(period, std_dev)
        bb_data, bb_signal, confidence = calculator.calculate_with_signal(df)

        if bb_data is None:
            raise HTTPException(
                status_code=400, detail="Insufficient data to calculate Bollinger Bands"
            )

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "upper_band": float(bb_data["upper_band"]),
            "middle_band": float(bb_data["middle_band"]),
            "lower_band": float(bb_data["lower_band"]),
            "current_price": float(bb_data["current_price"]),
            "signal": bb_signal,
            "confidence": confidence,
        }

    @staticmethod
    async def calculate_sma(
        symbol: str, interval: str, period: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate SMA indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = SMACalculator(period)
        sma_value = calculator.calculate(df)

        if sma_value is None:
            raise HTTPException(
                status_code=400, detail="Insufficient data to calculate SMA"
            )

        current_price = float(df["close"].iloc[-1])
        signal, confidence = calculator.generate_signal(sma_value, current_price)

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "value": float(sma_value),
            "current_price": float(current_price),
            "signal": signal,
            "confidence": confidence,
        }

    @staticmethod
    async def calculate_ema(
        symbol: str, interval: str, period: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate EMA indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        calculator = EMACalculator(period)
        ema_value = calculator.calculate(df)

        if ema_value is None:
            raise HTTPException(
                status_code=400, detail="Insufficient data to calculate EMA"
            )

        current_price = float(df["close"].iloc[-1])
        signal, confidence = calculator.generate_signal(ema_value, current_price)

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "value": float(ema_value),
            "current_price": float(current_price),
            "signal": signal,
            "confidence": confidence,
        }

    @staticmethod
    async def calculate_trend_filter(
        symbol: str, interval: str, fast_period: int, slow_period: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate Trend Filter indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < slow_period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {slow_period} candles, got {len(df)}",
            )

        close_prices = df["close"].tolist()
        trend_filter = TrendFilter(fast_period=fast_period, slow_period=slow_period)
        result = trend_filter.calculate(close_prices)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_volume_confirmation(
        symbol: str, interval: str, period: int, signal_type: str, limit: int
    ) -> Dict[str, Any]:
        """Calculate Volume Confirmation indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period} candles, got {len(df)}",
            )

        volumes = df["volume"].tolist()
        volume_conf = VolumeConfirmation(period=period)
        result = volume_conf.calculate(volumes, signal_type)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_atr(
        symbol: str,
        interval: str,
        period: int,
        current_price: Optional[float],
        limit: int,
    ) -> Dict[str, Any]:
        """Calculate ATR indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period + 1:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + 1} candles, got {len(df)}",
            )

        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()

        if current_price is None:
            current_price = closes[-1]

        atr_indicator = ATR(period=period)
        result = atr_indicator.calculate(highs, lows, closes, current_price)

        return {
            "timestamp": int(df.index[-1].timestamp() * 1000),
            "current_price": current_price,
            "data": result,
        }

    @staticmethod
    async def calculate_stochastic(
        symbol: str,
        interval: str,
        period: int,
        smooth_k: int,
        smooth_d: int,
        limit: int,
    ) -> Dict[str, Any]:
        """Calculate Stochastic Oscillator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period + smooth_k:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + smooth_k} candles, got {len(df)}",
            )

        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()

        stoch = Stochastic(period=period, smooth_k=smooth_k, smooth_d=smooth_d)
        result = stoch.calculate(highs, lows, closes)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_rsi_divergence(
        symbol: str, interval: str, period: int, lookback: int, limit: int
    ) -> Dict[str, Any]:
        """Calculate RSI Divergence indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        if len(df) < period + lookback:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {period + lookback} candles, got {len(df)}",
            )

        calculator = RSIDivergenceCalculator(rsi_period=period, lookback=lookback)
        result = calculator.calculate_with_signal(df)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_ichimoku(
        symbol: str,
        interval: str,
        tenkan_period: int,
        kijun_period: int,
        senkou_b_period: int,
        limit: int,
    ) -> Dict[str, Any]:
        """Calculate Ichimoku Cloud indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        min_required = senkou_b_period + 26
        if len(df) < min_required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {min_required} candles, got {len(df)}",
            )

        calculator = IchimokuCalculator(
            tenkan_period=tenkan_period,
            kijun_period=kijun_period,
            senkou_b_period=senkou_b_period,
        )
        result = calculator.calculate_with_signal(df)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_enhanced_sqzmom(
        symbol: str,
        interval: str,
        bb_period: int,
        bb_mult: float,
        kc_period: int,
        kc_mult: float,
        mom_period: int,
        limit: int,
    ) -> Dict[str, Any]:
        """Calculate Enhanced Squeeze Momentum indicator"""
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        min_required = max(bb_period, kc_period) + mom_period
        if len(df) < min_required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {min_required} candles, got {len(df)}",
            )

        calculator = EnhancedSqueezeMomentum(
            bb_length=bb_period,
            bb_mult=bb_mult,
            kc_length=kc_period,
            kc_mult=kc_mult,
            momentum_length=mom_period,
        )
        result_df = calculator.calculate(df)

        if result_df is None or result_df.empty:
            return {
                "timestamp": int(df.index[-1].timestamp() * 1000),
                "data": {"error": "Calculation failed"},
            }

        # Get the latest values.
        # FIXED 2026-05-05 (audit P0): EnhancedSqueezeMomentum.calculate() writes
        # columns prefixed with `sqz_` (sqz_momentum, sqz_color, sqz_signal,
        # sqz_confidence, sqz_acceleration, sqz_direction). The earlier code
        # read non-prefixed keys (`momentum`, `momentum_color`, `signal`,
        # `confidence`) which silently fell back to defaults — every API
        # response and the trading-engine SQZMOM_ENHANCED voter received
        # zero momentum / 'gray' color / HOLD / 0.5 confidence regardless
        # of actual market state. Aligned to the indicator's output schema.
        latest = result_df.iloc[-1]
        result = {
            "squeeze_on": bool(latest.get("squeeze_on", False)),
            "squeeze_off": bool(latest.get("squeeze_off", False)),
            "squeeze_firing": bool(latest.get("squeeze_firing", False)),
            "momentum": float(latest.get("sqz_momentum", 0.0)),
            "momentum_color": str(latest.get("sqz_color", "gray")),
            "momentum_direction": str(latest.get("sqz_direction", "FLAT")),
            "signal": str(latest.get("sqz_signal", "HOLD")),
            "confidence": float(latest.get("sqz_confidence", 0.5)),
        }

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}

    @staticmethod
    async def calculate_adx(
        symbol: str,
        interval: str,
        period: int,
        trending_threshold: float,
        weak_trend_threshold: float,
        strong_trend_threshold: float,
        limit: int,
    ) -> Dict[str, Any]:
        """
        Calculate ADX (Average Directional Index) indicator

        ADX measures trend strength and provides market regime classification:
        - STRONG_TREND: ADX >= strong_trend_threshold (default 30)
        - TRENDING: ADX >= trending_threshold (default 25)
        - WEAK_TREND: ADX >= weak_trend_threshold (default 20)
        - RANGING: ADX < weak_trend_threshold

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            interval: Candlestick interval (e.g., "60" for 1 hour)
            period: ADX calculation period (default 14)
            trending_threshold: ADX value for TRENDING classification (default 25)
            weak_trend_threshold: ADX value for WEAK_TREND classification (default 20)
            strong_trend_threshold: ADX value for STRONG_TREND classification (default 30)
            limit: Number of candles to fetch

        Returns:
            Dictionary containing ADX data, market regime, and trend direction
        """
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # ADX needs period * 2 + 1 candles for proper smoothing
        min_required = period * 2 + 1
        if len(df) < min_required:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data: need {min_required} candles, got {len(df)}",
            )

        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()

        calculator = ADXCalculator(
            period=period,
            trending_threshold=trending_threshold,
            weak_trend_threshold=weak_trend_threshold,
            strong_trend_threshold=strong_trend_threshold,
        )
        result = calculator.calculate(highs, lows, closes)

        return {"timestamp": int(df.index[-1].timestamp() * 1000), "data": result}
