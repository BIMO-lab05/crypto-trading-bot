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


async def get_aggregated_signal(symbol: str, interval: str = Query(default="60")):
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
            signal_period=settings.default_macd_signal,
        )
        trend_filter = TrendFilter()

        rsi_value = rsi_calc.calculate(df)
        macd = macd_calc.calculate(df)
        trend_result = trend_filter.calculate(df["close"].tolist())
        trend = trend_result.get("trend") if trend_result else None

        # Pre-compute MACD signal label/confidence so we can both
        # (a) feed it into the weighted aggregation and
        # (b) surface it as the `macd_signal` field in the response.
        # MACDCalculator.calculate() returns only {macd_line, signal_line,
        # histogram} — there is no `signal` key. Earlier code used
        # `macd.get('signal')` to fill the response field, which always
        # returned None. Fixed 2026-05-05 (audit P0).
        macd_signal_label = None
        if macd:
            macd_signal_type, macd_conf = macd_calc.generate_signal(macd)
            macd_signal_label = macd_signal_type.value

        # Signal aggregation. Each calculator already exposes a
        # *generate_signal* / dict with derived confidence — earlier
        # versions of this handler discarded those and used hardcoded
        # weights (RSI 0.7, MACD 0.6, trend 0.8). The MACD branch was
        # also dead code: it gated on `macd.get('signal')` but the
        # MACDCalculator.calculate() return dict has no `signal` key.
        # Audit-flagged 2026-04-28; rewired 2026-04-29 to propagate the
        # real confidence values from each indicator.
        signals = []

        # RSI: confidence derived from distance to oversold/overbought
        # thresholds inside RSICalculator.generate_signal().
        if rsi_value is not None:
            rsi_signal, rsi_conf = rsi_calc.generate_signal(rsi_value)
            signals.append((rsi_signal.value, rsi_conf))

        # MACD: confidence derived from histogram magnitude inside
        # MACDCalculator.generate_signal().
        if macd:
            signals.append((macd_signal_label, macd_conf))

        # Trend: TrendFilter.calculate() already returns its own
        # `signal` and `confidence` derived from EMA-spread magnitude.
        if trend_result:
            signals.append(
                (
                    trend_result.get("signal", "HOLD"),
                    float(trend_result.get("confidence", 0.0)),
                )
            )

        # Drop confidence=0 entries before aggregation (INFRA-06 Bug 2).
        # A disabled or uninitialised indicator may emit a (label, 0.0) tuple;
        # letting it through pollutes the weighted sum and can swing the final
        # signal on zero information.
        original_count = len(signals)
        signals = [(sig, weight) for sig, weight in signals if weight > 0.0]
        dropped = original_count - len(signals)
        if dropped:
            logger.info(
                "AGGREGATOR_CONFIDENCE_FILTER: dropped %d zero-confidence signals",
                dropped,
            )

        # Calculate weighted signal
        signal_weights = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        total_weight = 0.0

        for sig, weight in signals:
            signal_weights[sig] += weight
            total_weight += weight

        # Determine final signal. With no usable votes every weight is 0.0 and
        # argmax returns "BUY" (first-inserted key wins ties), which then took
        # the directional branch below and its `else 0.0` arm — a phantom
        # directional label at zero confidence. No votes means HOLD, which
        # reaches the `else 0.5` neutral fallback.
        final_signal = (
            max(signal_weights, key=signal_weights.get) if total_weight > 0 else "HOLD"
        )

        # Agreement-based confidence (audit 2026-07): for directional
        # signals, measure agreement among DIRECTIONAL voters only
        # (BUY vs SELL). The old share-of-total formula divided by
        # buy+sell+hold weight, so HOLD voters structurally capped every
        # aggregated signal near ~0.47 even with unanimous direction.
        directional_weight = signal_weights["BUY"] + signal_weights["SELL"]
        if final_signal in ("BUY", "SELL"):
            confidence = (
                signal_weights[final_signal] / directional_weight
                if directional_weight > 0
                else 0.0
            )
        else:
            # HOLD keeps the original share-of-total formula.
            confidence = (
                signal_weights[final_signal] / total_weight if total_weight > 0 else 0.5
            )

        return {
            "symbol": symbol,
            "interval": interval,
            "signal": final_signal,
            "confidence": round(confidence, 3),
            "rsi": round(rsi_value, 2) if rsi_value else None,
            "macd_signal": macd_signal_label,
            "trend": trend,
            "timestamp": int(df.index[-1].timestamp() * 1000),
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
        description="Comma-separated timeframes in minutes",
    ),
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
            1: "1m",
            5: "5m",
            15: "15m",
            30: "30m",
            60: "1h",
            120: "2h",
            240: "4h",
            360: "6h",
            720: "12h",
            1440: "1d",
        }

        fetcher = get_fetcher()

        # Analyze each timeframe
        async def analyze_timeframe(interval: int):
            try:
                df = await fetcher.get_klines_as_dataframe(
                    symbol, str(interval), limit=200
                )

                if df.empty:
                    return None

                # Calculate indicators (RESEARCH-OPTIMIZED 2025-11-29)
                rsi_calc = RSICalculator(period=settings.default_rsi_period)
                macd_calc = MACDCalculator(
                    fast_period=settings.default_macd_fast,
                    slow_period=settings.default_macd_slow,
                    signal_period=settings.default_macd_signal,
                )
                trend_filter = TrendFilter()

                rsi_value = rsi_calc.calculate(df)
                macd = macd_calc.calculate(df)
                trend_result = trend_filter.calculate(df["close"].tolist())
                trend = trend_result.get("trend") if trend_result else None

                # Compute MACD signal label via generate_signal() — the
                # raw `macd` dict only carries {macd_line, signal_line,
                # histogram}, not a `signal` key. Earlier `macd.get('signal')`
                # always returned None, so the MACD vote was silently
                # dropped from the per-timeframe consensus. Multi-timeframe
                # analysis was effectively RSI + trend only. Fixed
                # 2026-05-05 (audit P0).
                macd_signal_label = None
                if macd:
                    macd_signal_type, _ = macd_calc.generate_signal(macd)
                    macd_signal_label = macd_signal_type.value

                # Determine signal for this timeframe
                signals = []

                if rsi_value:
                    if rsi_value < 30:
                        signals.append("BUY")
                    elif rsi_value > 70:
                        signals.append("SELL")
                    else:
                        signals.append("HOLD")

                if macd_signal_label:
                    signals.append(macd_signal_label)

                if trend:
                    if trend == "BULLISH":
                        signals.append("BUY")
                    elif trend == "BEARISH":
                        signals.append("SELL")
                    else:
                        signals.append("HOLD")

                # Count signals
                buy_count = signals.count("BUY")
                sell_count = signals.count("SELL")

                # Determine timeframe signal
                if buy_count > sell_count:
                    tf_signal = "BUY"
                elif sell_count > buy_count:
                    tf_signal = "SELL"
                else:
                    tf_signal = "HOLD"

                return {
                    "timeframe": timeframe_names.get(interval, f"{interval}m"),
                    "interval_minutes": interval,
                    "signal": tf_signal,
                    "rsi": round(rsi_value, 2) if rsi_value else None,
                    "macd_signal": macd_signal_label,
                    "trend": trend,
                    "timestamp": int(df.index[-1].timestamp() * 1000),
                }

            except Exception as e:
                logger.error(f"Error analyzing timeframe {interval}: {e}")
                return {
                    "timeframe": timeframe_names.get(interval, f"{interval}m"),
                    "interval_minutes": interval,
                    "signal": "ERROR",
                    "error": str(e),
                }

        # Execute all timeframe analyses in parallel
        results = await asyncio.gather(*[analyze_timeframe(tf) for tf in tf_list])

        # Filter out None results
        valid_results = [r for r in results if r and r.get("signal") != "ERROR"]

        if not valid_results:
            raise HTTPException(
                status_code=404, detail="Unable to analyze any timeframes"
            )

        # Calculate alignment
        buy_timeframes = [r for r in valid_results if r["signal"] == "BUY"]
        sell_timeframes = [r for r in valid_results if r["signal"] == "SELL"]
        hold_timeframes = [r for r in valid_results if r["signal"] == "HOLD"]

        total_timeframes = len(valid_results)

        # Determine overall recommendation
        # Agreement-based confidence (audit 2026-07): for directional
        # outcomes, confidence = winning direction's share of DIRECTIONAL
        # votes only (BUY vs SELL) — HOLD timeframes no longer structurally
        # cap directional confidence. HOLD keeps share-of-total.
        directional_count = len(buy_timeframes) + len(sell_timeframes)
        if len(buy_timeframes) >= total_timeframes * 0.6:
            overall_signal = "BUY"
            confidence = (
                len(buy_timeframes) / directional_count
                if directional_count > 0
                else 0.0
            )
        elif len(sell_timeframes) >= total_timeframes * 0.6:
            overall_signal = "SELL"
            confidence = (
                len(sell_timeframes) / directional_count
                if directional_count > 0
                else 0.0
            )
        else:
            overall_signal = "HOLD"
            confidence = (
                max(len(buy_timeframes), len(sell_timeframes), len(hold_timeframes))
                / total_timeframes
            )

        # Calculate alignment score
        alignment_score = (
            max(len(buy_timeframes), len(sell_timeframes), len(hold_timeframes))
            / total_timeframes
        )

        return {
            "symbol": symbol,
            "timeframes_analyzed": total_timeframes,
            "overall_signal": overall_signal,
            "confidence": round(confidence, 3),
            "alignment_score": round(alignment_score, 3),
            "summary": {
                "buy_timeframes": len(buy_timeframes),
                "sell_timeframes": len(sell_timeframes),
                "hold_timeframes": len(hold_timeframes),
            },
            "timeframe_details": valid_results,
            "recommendation": (
                f"Strong {overall_signal}"
                if alignment_score > 0.75
                else f"Moderate {overall_signal}"
                if alignment_score > 0.5
                else f"Weak {overall_signal} - Mixed signals across timeframes"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-timeframe analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
