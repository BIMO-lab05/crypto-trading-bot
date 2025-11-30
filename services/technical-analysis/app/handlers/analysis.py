"""
Analysis Endpoint Handlers
Extracted from main.py - Responsibility: Complex analysis endpoints
"""

import logging
import asyncio
from fastapi import HTTPException, Query

from app.config import get_settings
from app.fetcher import get_fetcher
from app.indicators import RSICalculator, MACDCalculator
from app.indicators.trend_filter import TrendFilter

logger = logging.getLogger(__name__)
settings = get_settings()


async def get_aggregated_signal(
    symbol: str,
    interval: str = Query(default="60")
):
    """
    Get aggregated trading signal for a symbol/interval

    Combines multiple indicators into a single signal with confidence
    """
    try:
        fetcher = get_fetcher()
        df = await fetcher.get_klines_as_dataframe(symbol, interval, limit=200)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available")

        # Calculate multiple indicators
        # RESEARCH-OPTIMIZED 2025-11-29: Use settings for optimal parameters
        rsi_calc = RSICalculator(period=settings.default_rsi_period)
        macd_calc = MACDCalculator(
            fast_period=settings.default_macd_fast,
            slow_period=settings.default_macd_slow,
            signal_period=settings.default_macd_signal
        )
        trend_filter = TrendFilter()

        rsi_value = rsi_calc.calculate(df)
        macd = macd_calc.calculate(df)
        trend_result = trend_filter.calculate(df['close'].tolist())
        trend = trend_result.get('trend') if trend_result else None

        # Simple signal aggregation
        signals = []

        # RSI signal
        if rsi_value:
            if rsi_value < 30:
                signals.append(('BUY', 0.7))
            elif rsi_value > 70:
                signals.append(('SELL', 0.7))
            else:
                signals.append(('HOLD', 0.5))

        # MACD signal
        if macd and macd.get('signal'):
            macd_signal = macd['signal']
            if macd_signal == 'BUY':
                signals.append(('BUY', 0.6))
            elif macd_signal == 'SELL':
                signals.append(('SELL', 0.6))
            else:
                signals.append(('HOLD', 0.4))

        # Trend signal
        if trend:
            if trend == 'BULLISH':
                signals.append(('BUY', 0.8))
            elif trend == 'BEARISH':
                signals.append(('SELL', 0.8))
            else:
                signals.append(('HOLD', 0.5))

        # Calculate weighted signal
        signal_weights = {'BUY': 0.0, 'SELL': 0.0, 'HOLD': 0.0}
        total_weight = 0.0

        for sig, weight in signals:
            signal_weights[sig] += weight
            total_weight += weight

        # Determine final signal
        final_signal = max(signal_weights, key=signal_weights.get)
        confidence = signal_weights[final_signal] / total_weight if total_weight > 0 else 0.5

        return {
            "symbol": symbol,
            "interval": interval,
            "signal": final_signal,
            "confidence": round(confidence, 3),
            "rsi": round(rsi_value, 2) if rsi_value else None,
            "macd_signal": macd.get('signal') if macd else None,
            "trend": trend,
            "timestamp": int(df.index[-1].timestamp() * 1000)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting aggregated signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_multi_timeframe_analysis(
    symbol: str,
    timeframes: str = Query(
        default="1,5,15,60,240,1440",
        description="Comma-separated timeframes in minutes"
    )
):
    """
    Analyze a symbol across multiple timeframes for trend confirmation

    Returns:
    - Individual analysis for each timeframe
    - Alignment score (how many timeframes agree)
    - Overall recommendation based on consensus
    """
    try:
        # Parse timeframes
        tf_list = [int(tf.strip()) for tf in timeframes.split(",")]

        # Timeframe names for display
        timeframe_names = {
            1: "1m", 5: "5m", 15: "15m", 30: "30m",
            60: "1h", 120: "2h", 240: "4h", 360: "6h",
            720: "12h", 1440: "1d"
        }

        fetcher = get_fetcher()

        # Analyze each timeframe
        async def analyze_timeframe(interval: int):
            try:
                df = await fetcher.get_klines_as_dataframe(symbol, str(interval), limit=200)

                if df.empty:
                    return None

                # Calculate indicators (RESEARCH-OPTIMIZED 2025-11-29)
                rsi_calc = RSICalculator(period=settings.default_rsi_period)
                macd_calc = MACDCalculator(
                    fast_period=settings.default_macd_fast,
                    slow_period=settings.default_macd_slow,
                    signal_period=settings.default_macd_signal
                )
                trend_filter = TrendFilter()

                rsi_value = rsi_calc.calculate(df)
                macd = macd_calc.calculate(df)
                trend_result = trend_filter.calculate(df['close'].tolist())
                trend = trend_result.get('trend') if trend_result else None

                # Determine signal for this timeframe
                signals = []

                if rsi_value:
                    if rsi_value < 30:
                        signals.append('BUY')
                    elif rsi_value > 70:
                        signals.append('SELL')
                    else:
                        signals.append('HOLD')

                if macd and macd.get('signal'):
                    signals.append(macd['signal'])

                if trend:
                    if trend == 'BULLISH':
                        signals.append('BUY')
                    elif trend == 'BEARISH':
                        signals.append('SELL')
                    else:
                        signals.append('HOLD')

                # Count signals
                buy_count = signals.count('BUY')
                sell_count = signals.count('SELL')

                # Determine timeframe signal
                if buy_count > sell_count:
                    tf_signal = 'BUY'
                elif sell_count > buy_count:
                    tf_signal = 'SELL'
                else:
                    tf_signal = 'HOLD'

                return {
                    "timeframe": timeframe_names.get(interval, f"{interval}m"),
                    "interval_minutes": interval,
                    "signal": tf_signal,
                    "rsi": round(rsi_value, 2) if rsi_value else None,
                    "macd_signal": macd.get('signal') if macd else None,
                    "trend": trend,
                    "timestamp": int(df.index[-1].timestamp() * 1000)
                }

            except Exception as e:
                logger.error(f"Error analyzing timeframe {interval}: {e}")
                return {
                    "timeframe": timeframe_names.get(interval, f"{interval}m"),
                    "interval_minutes": interval,
                    "signal": "ERROR",
                    "error": str(e)
                }

        # Execute all timeframe analyses in parallel
        results = await asyncio.gather(*[
            analyze_timeframe(tf) for tf in tf_list
        ])

        # Filter out None results
        valid_results = [r for r in results if r and r.get('signal') != 'ERROR']

        if not valid_results:
            raise HTTPException(status_code=404, detail="Unable to analyze any timeframes")

        # Calculate alignment
        buy_timeframes = [r for r in valid_results if r['signal'] == 'BUY']
        sell_timeframes = [r for r in valid_results if r['signal'] == 'SELL']
        hold_timeframes = [r for r in valid_results if r['signal'] == 'HOLD']

        total_timeframes = len(valid_results)

        # Determine overall recommendation
        if len(buy_timeframes) >= total_timeframes * 0.6:
            overall_signal = 'BUY'
            confidence = len(buy_timeframes) / total_timeframes
        elif len(sell_timeframes) >= total_timeframes * 0.6:
            overall_signal = 'SELL'
            confidence = len(sell_timeframes) / total_timeframes
        else:
            overall_signal = 'HOLD'
            confidence = max(len(buy_timeframes), len(sell_timeframes), len(hold_timeframes)) / total_timeframes

        # Calculate alignment score
        alignment_score = max(len(buy_timeframes), len(sell_timeframes), len(hold_timeframes)) / total_timeframes

        return {
            "symbol": symbol,
            "timeframes_analyzed": total_timeframes,
            "overall_signal": overall_signal,
            "confidence": round(confidence, 3),
            "alignment_score": round(alignment_score, 3),
            "summary": {
                "buy_timeframes": len(buy_timeframes),
                "sell_timeframes": len(sell_timeframes),
                "hold_timeframes": len(hold_timeframes)
            },
            "timeframe_details": valid_results,
            "recommendation": (
                f"Strong {overall_signal}" if alignment_score > 0.75
                else f"Moderate {overall_signal}" if alignment_score > 0.5
                else f"Weak {overall_signal} - Mixed signals across timeframes"
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-timeframe analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
