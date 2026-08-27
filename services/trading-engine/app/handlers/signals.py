"""
Signal Endpoint Handlers
Extracted from main.py - Responsibility: Signal fetching and trading execution

Handles trading signal retrieval and analysis with optional execution.

UPDATED: Signal recording now handled by CoreAggregator with real filter data
ENHANCED: ML Prediction integration for 5-10% win rate improvement
"""

import logging
import time
import httpx
from fastapi import HTTPException

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.risk_manager import get_risk_manager
from app.models import SignalResponse
from app.services import TradingService

logger = logging.getLogger(__name__)
settings = get_settings()

# HTTP client for ML service calls
ml_client = httpx.AsyncClient(timeout=30.0)

# P21-7 (2026-08-27): technical-analysis owns the ADX regime vocabulary
# (`services/technical-analysis/app/indicators/adx.py::MarketRegime`) and
# publishes the computed label on the very endpoint this module already calls.
# `_fetch_market_regime` used to re-derive it from its own copies of TA's 25 /
# 20 boundaries, so the dashboard and the engine could disagree about the same
# market on any env override.
#
# TA's vocabulary is WIDER than that re-derivation was: it also emits
# STRONG_TREND (ADX >= 30), which no consumer here handles.
# `_calculate_enhanced_signal`'s regime_multiplier branches on TRENDING /
# RANGING only, so an unrecognised label keeps the neutral 1.0 instead of the
# 1.1 those bars used to get. STRONG_TREND is therefore mapped onto TRENDING,
# which is exactly what the deleted re-derivation produced for them.
#
# Scope note, so nobody over-reads this: `_get_risk_adjusted_signal` also
# branches on TRENDING / RANGING, but all three of its branches return "HOLD",
# so the regime label cannot move its output. The multiplier is the only
# consumer this mapping actually protects.
#
# NO THRESHOLD VALUE CHANGED: the boundaries are TA's, and they are the same
# 25 / 20 this handler used to apply. Anything absent from this table resolves
# to UNKNOWN and logs -- a label TA adds later must fail loud, not quietly
# take the neutral path.
TA_REGIME_TO_ENGINE_REGIME = {
    "STRONG_TREND": "TRENDING",
    "TRENDING": "TRENDING",
    "WEAK_TREND": "WEAK_TREND",
    "RANGING": "RANGING",
}


async def get_trading_signal(symbol: str, interval: str = "60") -> SignalResponse:
    """
    Get trading signal for a symbol

    Fetches all technical indicators and aggregates them into a trading signal.
    Signal is automatically recorded by CoreAggregator with real filter data.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (default: 60)

    Returns:
        SignalResponse with aggregated signal and confidence

    Raises:
        HTTPException: If signal fetching fails
    """
    try:
        aggregator = await get_aggregator()
        # CoreAggregator now records signal to Phase1MetricsProvider with real filter data
        signal = await aggregator.get_trading_signal(symbol, interval)

        return SignalResponse(
            success=True, signal=signal, timestamp=int(time.time() * 1000)
        )

    except Exception as e:
        logger.error(f"Error getting trading signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_enhanced_trading_signal(
    symbol: str, interval: str = "60"
) -> SignalResponse:
    """
    Get ENHANCED trading signal with ML predictions for 5-10% win rate improvement

    Combines:
    - Technical Analysis: 30% weight
    - ML Predictions: 35% weight (enhanced with ensemble)
    - Sentiment Analysis: 15% weight
    - Market Regime: 10% weight
    - Risk Adjustment: 10% weight

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (default: 60)

    Returns:
        SignalResponse with enhanced aggregated signal and confidence

    Raises:
        HTTPException: If signal fetching fails
    """
    try:
        # Get base technical signal
        aggregator = await get_aggregator()
        base_signal = await aggregator.get_trading_signal(symbol, interval)

        # Fetch ML prediction from ML service
        ml_prediction = await _fetch_ml_prediction(symbol, interval)

        # Fetch market regime data
        market_regime = await _fetch_market_regime(symbol, interval)

        # Calculate enhanced signal with weighted combination
        enhanced_signal = await _calculate_enhanced_signal(
            base_signal, ml_prediction, market_regime
        )

        return SignalResponse(
            success=True,
            signal=enhanced_signal,
            timestamp=int(time.time() * 1000),
            metadata={
                "enhanced": True,
                "win_rate_target": "5-10%",
                "ml_prediction": ml_prediction,
                "market_regime": market_regime,
            },
        )

    except Exception as e:
        logger.error(f"Error getting enhanced trading signal for {symbol}: {e}")
        # Fallback to basic signal
        return await get_trading_signal(symbol, interval)


async def _fetch_ml_prediction(symbol: str, interval: str) -> dict:
    """
    Fetch ML prediction from ML Prediction Service
    """
    try:
        ml_url = f"{settings.ml_prediction_url}/api/v1/predict/enhanced/{symbol}"
        params = {
            "interval": interval,
            "lookback_days": 90,
            "model_type": "ENSEMBLE",
            "confidence_threshold": 0.55,  # Lowered for more signals
        }

        response = await ml_client.get(ml_url, params=params)
        response.raise_for_status()

        return response.json()

    except Exception as e:
        logger.warning(f"ML prediction fetch failed for {symbol}: {e}")
        return {
            "symbol": symbol,
            "interval": interval,
            "signal": "HOLD",
            "confidence": 0.0,
            "reason": f"ML service error: {str(e)}",
        }


async def _fetch_market_regime(symbol: str, interval: str) -> dict:
    """
    Fetch market regime analysis
    """
    try:
        # Use technical analysis service for regime detection
        ta_url = f"{settings.technical_analysis_url}/api/v1/indicators/adx/{symbol}"
        params = {"interval": interval}

        response = await ml_client.get(ta_url, params=params)
        response.raise_for_status()

        payload = response.json().get("data", {}) or {}

        # A missing ADX used to default to 25, which satisfied the `>= 25`
        # branch below -- so an empty technical-analysis reply was reported as
        # TRENDING at confidence 0.7, indistinguishable downstream from a real
        # measurement. Absence stays absent (same sentinel doctrine as the
        # ensemble's ATR handling).
        adx_value = payload.get("adx")

        # Read the regime technical-analysis already computed rather than
        # re-deriving it here. See TA_REGIME_TO_ENGINE_REGIME above for why the
        # label is mapped instead of passed through raw.
        raw_regime = payload.get("regime")
        regime = TA_REGIME_TO_ENGINE_REGIME.get(raw_regime)
        if regime is None:
            if raw_regime is not None:
                logger.warning(
                    f"Unmapped technical-analysis regime {raw_regime!r} for "
                    f"{symbol}; reporting UNKNOWN. Add it to "
                    f"TA_REGIME_TO_ENGINE_REGIME -- an unmapped label silently "
                    f"takes the neutral multiplier downstream."
                )
            regime = "UNKNOWN"

        return {"regime": regime, "adx": adx_value, "confidence": 0.7}

    except Exception as e:
        logger.warning(f"Market regime fetch failed for {symbol}: {e}")
        return {
            # `adx` is None, not 25: a failed fetch has no measurement, and a
            # plausible stand-in reads as a real one in the API response.
            "regime": "UNKNOWN",
            "adx": None,
            "confidence": 0.5,
            "reason": f"Regime service error: {str(e)}",
        }


async def _calculate_enhanced_signal(
    base_signal, ml_prediction: dict, market_regime: dict
) -> any:  # Return type matches base signal type
    """
    Calculate enhanced signal combining all data sources
    """
    try:
        # Extract signal components
        ta_signal = (
            base_signal.signal.action.value
            if hasattr(base_signal.signal, "action")
            else "HOLD"
        )
        ta_confidence = (
            base_signal.signal.confidence
            if hasattr(base_signal.signal, "confidence")
            else 0.5
        )

        ml_signal = ml_prediction.get("signal", "HOLD")
        ml_confidence = ml_prediction.get("confidence", 0.5)

        regime = market_regime.get("regime", "UNKNOWN")

        # Apply market regime adjustment
        regime_multiplier = 1.0
        if regime == "RANGING":
            # In ranging markets, reduce confidence in trend-following signals
            if ta_signal in ["BUY", "SELL"]:
                regime_multiplier = 0.8
        elif regime == "TRENDING":
            # In trending markets, increase confidence
            regime_multiplier = 1.1

        # Calculate weighted signal
        signals = []
        weights = []

        # Renormalized 2026-05-02 after sentiment removal: was
        # TA 0.30 / ML 0.35 / Sentiment 0.15 / Risk 0.10 (sum 0.90 — never
        # actually summed to 1.0 even before). Rescaled the remaining three
        # legs to sum to 1.0 in the same proportions.
        # Technical Analysis (40% weight)
        signals.append(_normalize_signal(ta_signal))
        weights.append(ta_confidence * 0.40 * regime_multiplier)

        # ML Prediction (45% weight) - MAIN IMPROVEMENT DRIVER
        signals.append(_normalize_signal(ml_signal))
        weights.append(ml_confidence * 0.45)

        # Risk Adjustment (15% weight) - Based on market regime
        risk_signal = _get_risk_adjusted_signal(regime)
        risk_confidence = market_regime.get("confidence", 0.5)
        signals.append(_normalize_signal(risk_signal))
        weights.append(risk_confidence * 0.15)

        # Calculate final weighted signal
        if signals and weights:
            signal_values = [_signal_to_numeric(s) for s in signals]

            # Calculate weighted average
            weighted_sum = sum(s * w for s, w in zip(signal_values, weights))
            total_weight = sum(weights)

            if total_weight > 0:
                final_signal_numeric = weighted_sum / total_weight
                final_signal = _numeric_to_signal(final_signal_numeric)

                # Calculate overall confidence
                overall_confidence = sum(weights) / len(weights) if weights else 0.5

                # Apply win rate improvement factor
                win_rate_factor = await _calculate_win_rate_factor(ml_prediction)
                adjusted_confidence = overall_confidence * win_rate_factor

                # Update the signal with enhanced data
                if hasattr(base_signal.signal, "confidence"):
                    base_signal.signal.confidence = min(adjusted_confidence, 1.0)

                # Add enhanced metadata
                if not hasattr(base_signal.signal, "metadata"):
                    base_signal.signal.metadata = {}

                base_signal.signal.metadata.update(
                    {
                        "enhanced": True,
                        "win_rate_improvement_target": "5-10%",
                        "win_rate_factor_applied": win_rate_factor,
                        "individual_signals": {
                            "technical_analysis": {
                                "signal": ta_signal,
                                "confidence": ta_confidence,
                            },
                            "ml_prediction": {
                                "signal": ml_signal,
                                "confidence": ml_confidence,
                                "win_rate_potential": ml_prediction.get(
                                    "enhanced_metrics", {}
                                ).get("win_rate_potential", 0.5),
                            },
                            "risk_adjustment": {
                                "signal": risk_signal,
                                "confidence": risk_confidence,
                                "regime": regime,
                            },
                        },
                        "weights_applied": {
                            "technical_analysis": 0.40,
                            "ml_prediction": 0.45,
                            "risk_adjustment": 0.15,
                        },
                    }
                )

        return base_signal.signal

    except Exception as e:
        logger.error(f"Error calculating enhanced signal: {e}")
        # Return original signal if enhancement fails
        return base_signal.signal


def _normalize_signal(signal: str) -> str:
    """Normalize signal to standard format"""
    signal = signal.upper().strip()
    if signal in ["BUY", "LONG", "BULLISH", "UP", "1"]:
        return "BUY"
    elif signal in ["SELL", "SHORT", "BEARISH", "DOWN", "-1"]:
        return "SELL"
    else:
        return "HOLD"


def _signal_to_numeric(signal: str) -> float:
    """Convert signal to numeric value"""
    if signal == "BUY":
        return 1.0
    elif signal == "SELL":
        return -1.0
    else:
        return 0.0


def _numeric_to_signal(numeric: float) -> str:
    """Convert numeric value back to signal"""
    if numeric > 0.1:
        return "BUY"
    elif numeric < -0.1:
        return "SELL"
    else:
        return "HOLD"


def _get_risk_adjusted_signal(regime: str) -> str:
    """Get risk-adjusted signal based on market regime"""
    if regime == "RANGING":
        return "HOLD"  # Conservative in ranging markets
    elif regime == "TRENDING":
        return "HOLD"  # Let trends continue
    else:
        return "HOLD"  # Neutral for unknown regimes


async def _calculate_win_rate_factor(ml_prediction: dict) -> float:
    """Calculate win rate improvement factor based on ML prediction quality"""
    try:
        # Get ML win rate potential
        enhanced_metrics = ml_prediction.get("enhanced_metrics", {})
        ml_win_rate_potential = enhanced_metrics.get("win_rate_potential", 0.5)

        # Calculate improvement over baseline (50%)
        baseline = 0.5
        potential_improvement = max(0, ml_win_rate_potential - baseline)

        # Convert to factor (1.0 = no improvement, 1.1 = 10% improvement)
        improvement_factor = 1.0 + (
            potential_improvement * 0.2
        )  # 20% of potential improvement

        return min(max(improvement_factor, 0.9), 1.10)  # Clamp between 0.9-1.1

    except Exception:
        return 1.0  # No improvement factor


async def analyze_and_trade(
    symbol: str, interval: str = "60", execute: bool = False
) -> SignalResponse:
    """
    Analyze signal and optionally execute trade

    Process:
    1. Fetch trading signal from aggregator
    2. Validate signal with risk manager
    3. Execute trade if requested and validated

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        interval: Candlestick interval in minutes (default: 60)
        execute: If True, will execute trade based on signal

    Returns:
        SignalResponse with signal analysis and execution result

    Raises:
        HTTPException: If analysis or execution fails
    """
    try:
        # Fetch trading signal
        aggregator = await get_aggregator()
        signal = await aggregator.get_trading_signal(symbol, interval)

        # Validate signal with risk manager
        risk_manager = get_risk_manager()
        is_valid, reason = risk_manager.validate_signal(
            signal.action, signal.confidence
        )

        if not is_valid:
            return SignalResponse(
                success=False,
                signal=signal,
                message=f"Signal validation failed: {reason}",
                timestamp=int(time.time() * 1000),
            )

        # Execute trade if requested (paper trading only)
        if execute and settings.trading_mode == "PAPER":
            message = await TradingService.execute_signal_trade(signal)
            return SignalResponse(
                success=True,
                signal=signal,
                message=message,
                timestamp=int(time.time() * 1000),
            )

        return SignalResponse(
            success=True,
            signal=signal,
            message="Signal analyzed (not executed)",
            timestamp=int(time.time() * 1000),
        )

    except Exception as e:
        logger.error(f"Error analyzing signal for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
