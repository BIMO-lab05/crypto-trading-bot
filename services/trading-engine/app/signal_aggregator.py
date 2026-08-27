"""
Signal Aggregator
Purpose: Fetch and aggregate technical indicators from Technical Analysis Service

REFACTORED: Using Strangler Fig pattern
- Modular components in app/aggregation/
- CoreAggregator orchestrates gatekeeper, validator, voter
- Improved testability and maintainability

UPDATE 2025-11-26: Added new advanced indicators
- RSI Divergence: Detects bullish/bearish divergences for reversal signals
- Ichimoku Cloud: Japanese trading system with 5 components for trend/momentum
- Enhanced SQZMOM: Squeeze momentum with firing detection for breakout entries
"""

import httpx
import logging
from datetime import datetime
from typing import Dict, Optional, List
from app.config import get_settings
from app.models import TradingSignal, IndicatorSignal, SignalAction
from app.aggregation import CoreAggregator
from app.aggregation.ml_gate_reasons import log_ml_disabled  # noqa: F401 — used in get_trading_signal fallback branch; autoflake-survival
from app.services.indicator_registry import get_indicator_registry

logger = logging.getLogger(__name__)


def consolidate_mtf_confidence(mtf_analysis, primary_confidence: float):
    """Pick the action and the confidence that actually describe each other.

    2026-08-23. This used to be two unrelated quantities glued onto one object:
    ``action`` came from ``mtf_analysis.consensus_action`` -- a weighted blend of
    all three timeframes' raw PRE-GATE scores (multi_timeframe.py:189-211, which
    never reads the gated action) -- while ``confidence`` was the PRIMARY (60m)
    timeframe's number, untouched by the other two.

    That mattered because aggregator_core forces ``action = HOLD`` when the
    requirements gate fails but leaves ``confidence`` at the directional value
    that just failed. A rejected signal could therefore re-enter the pipeline as
    a trade candidate carrying its own rejected confidence, with the direction
    supplied by a consensus that had never consulted it.

    Measured over 8h of live logs, of 231 directional MTF consensuses:
      152 (65.8%) had ZERO timeframe whose gated action matched the consensus
       43         had exactly one
       36         had two -- and those 36 are exactly the ones that emitted

    So requiring at least one agreeing timeframe drops 152 laundered artifacts
    at zero cost to signals that actually trade.

    Returns ``(action, confidence)``:
    - directional consensus with no agreeing gated action -> HOLD
    - directional consensus with agreeing timeframes      -> weight-averaged
      confidence over those timeframes only (HOLD legs abstain)
    - HOLD consensus                                      -> primary confidence

    The result is passed through ``validate_confidence``: TradingSignal declares
    ``confidence`` with ``le=1.0``, but assignment bypasses pydantic validation
    because the model does not set ``validate_assignment``, so a modifier above
    1.0 could otherwise push it out of range.

    See .planning/evidence/hold-funnel-2026-08-22.md
    """
    from app.aggregation.confidence_guard import validate_confidence

    action = mtf_analysis.consensus_action
    signals = (mtf_analysis.timeframe_signals or {}).values()
    agreeing = [tf for tf in signals if tf.action == action]

    if action != SignalAction.HOLD and not agreeing:
        logger.info(
            "   MTF consensus %s unsupported by any timeframe's gated action "
            "-> HOLD (consensus is computed from pre-gate scores)",
            action.value,
        )
        action = SignalAction.HOLD
        agreeing = []

    base = primary_confidence
    if action != SignalAction.HOLD and agreeing:
        total_weight = sum(tf.weight for tf in agreeing)
        if total_weight > 0:
            base = sum(tf.confidence * tf.weight for tf in agreeing) / total_weight

    confidence = validate_confidence(
        base * mtf_analysis.confidence_modifier,
        source="signal_aggregator.multi_timeframe",
    )
    return action, confidence


class SignalAggregator:
    """
    Fetches technical indicators and aggregates them into a trading signal

    Process:
    1. Fetch all indicators from Technical Analysis Service
    2. Normalize signals (BUY/SELL/HOLD -> numerical score)
    3. Weight by confidence
    4. Generate final trading decision

    Indicator Categories (2025-11-26):
    - Original 5: RSI, MACD, Bollinger Bands, SMA, EMA
    - Phase 1: Trend Filter (GATEKEEPER), Volume Confirmation (VALIDATOR), Stochastic
    - Advanced: RSI Divergence, Ichimoku Cloud, Enhanced SQZMOM
    - Risk Management: ATR (not a voting indicator)
    """

    def __init__(self):
        """Initialize signal aggregator with modular components"""
        self.settings = get_settings()
        self.base_url = self.settings.technical_analysis_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.core_aggregator = CoreAggregator(self.settings)  # Modular aggregation
        logger.info(f"SignalAggregator initialized with TA URL: {self.base_url}")

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def health_check(self) -> bool:
        """Check if Technical Analysis Service is available"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Technical Analysis Service health check failed: {e}")
            return False

    async def fetch_rsi(
        self,
        symbol: str,
        interval: str = "60",
        period: int = 9,  # RESEARCH: Period 9 optimal for crypto (more responsive to volatility)
    ) -> Optional[IndicatorSignal]:
        """
        Fetch RSI indicator with research-optimized period

        RESEARCH-BACKED: RSI(9) optimal for crypto markets
        - More responsive to price changes in volatile markets
        - Better captures momentum shifts in 24/7 crypto trading
        - Research thresholds: 75/25 (not 70/30) for reduced false signals
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/rsi/{symbol}"
            params = {"interval": interval, "period": period}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="RSI",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["rsi"],
                metadata={
                    "period": period,
                    "weight": 1.0,  # Standard weight for balanced signal aggregation
                },
            )

        except Exception as e:
            logger.error(f"Error fetching RSI for {symbol}: {e}")
            return None

    async def fetch_macd(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch MACD indicator using the TA service's research-optimized defaults

        Parameter drift fix (audit 2026-07): this client previously forced
        8-17-9 while the TA service default is the Kang-2021 5-35-5
        (see technical-analysis app/config.py and handlers/indicators.py).
        We now omit fast/slow/signal so the single source of truth for MACD
        parameters is the TA service's defaults (currently 5-35-5).
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/macd/{symbol}"
            # No fast/slow/signal here on purpose — use TA service defaults
            # (Kang 2021: 5-35-5) instead of drifting local overrides.
            params = {
                "interval": interval,
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="MACD",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["histogram"],
                metadata={
                    "macd_line": data["macd_line"],
                    "signal_line": data["signal_line"],
                    "parameters": data.get(
                        "parameters", {"fast": 5, "slow": 35, "signal": 5}
                    ),
                    "weight": 1.0,  # Balanced weight to avoid over-reliance on single indicator
                },
            )

        except Exception as e:
            logger.error(f"Error fetching MACD for {symbol}: {e}")
            return None

    async def fetch_bollinger_bands(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Bollinger Bands indicator with research-optimized parameters

        RESEARCH-OPTIMIZED 2025-11-29:
        - Wider bands (2.5 SD) work better for crypto volatility
        - Reduces false breakout signals in volatile markets
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/bollinger/{symbol}"
            # RESEARCH-OPTIMIZED 2025-11-29: Use 2.5 SD for crypto
            params = {
                "interval": interval,
                "std_dev": 2.5,  # Widened for crypto volatility (prev: 2.0)
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="BOLLINGER_BANDS",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["current_price"],
                metadata={
                    "upper_band": data["upper_band"],
                    "middle_band": data["middle_band"],
                    "lower_band": data["lower_band"],
                    "weight": 1.0,  # Standard weight for balanced volatility signals
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Bollinger Bands for {symbol}: {e}")
            return None

    async def fetch_sma(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch SMA indicator using the TA service's declared default period

        Parameter drift fix (phase 21 P21-4): this client previously forced
        period=21 while the TA service default was 20, so the traded path ran
        on 21 and a bare call to the same endpoint resolved to 20 - the two
        disagreed with nothing able to detect it. 21 won because it is the
        live traded value, and it now lives in the TA service's config.py as
        `default_sma_period`. We omit `period` so that declaration is the
        single source of truth (same fix as fetch_macd's 5-35-5).
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/sma/{symbol}"
            # No period here on purpose — use the TA service default
            # (currently 21) instead of a drifting local override.
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="SMA",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["value"],
                metadata={
                    "current_price": data["current_price"],
                    # Echo the parameters the TA service actually applied
                    # rather than a local literal the engine no longer owns
                    # (same shape as fetch_macd's "parameters" metadata).
                    "parameters": data.get("parameters", {}),
                    "weight": 0.8,  # Moderate weight for trend confirmation
                },
            )

        except Exception as e:
            logger.error(f"Error fetching SMA for {symbol}: {e}")
            return None

    async def fetch_ema(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch EMA indicator using the TA service's declared default period

        Parameter drift fix (phase 21 P21-4): this client previously forced
        period=21 while the TA service default was 20, so the traded path ran
        on 21 and a bare call to the same endpoint resolved to 20. 21 won
        because it is the live traded value, and it now lives in the TA
        service's config.py as `default_ema_period`. We omit `period` so that
        declaration is the single source of truth.
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/ema/{symbol}"
            # No period here on purpose — use the TA service default
            # (currently 21) instead of a drifting local override.
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            return IndicatorSignal(
                name="EMA",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["value"],
                metadata={
                    "current_price": data["current_price"],
                    # Echo the parameters the TA service actually applied
                    # rather than a local literal the engine no longer owns
                    # (same shape as fetch_macd's "parameters" metadata).
                    "parameters": data.get("parameters", {}),
                    "weight": 1.0,  # Standard weight for responsive trend analysis
                },
            )

        except Exception as e:
            logger.error(f"Error fetching EMA for {symbol}: {e}")
            return None

    # ==================== PHASE 1 INDICATORS ====================

    async def fetch_trend_filter(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Trend Filter (50/200 EMA)

        Role: GATEKEEPER - Blocks counter-trend trades
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/trend/{symbol}"
            params = {"interval": interval, "limit": 300}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return IndicatorSignal(
                name="TREND_FILTER",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["spread_pct"],
                metadata={
                    "trend": data["trend"],
                    "fast_ema": data["fast_ema"],
                    "slow_ema": data["slow_ema"],
                    "role": "GATEKEEPER",
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Trend Filter for {symbol}: {e}")
            return None

    async def fetch_volume_confirmation(
        self, symbol: str, interval: str = "60", signal_type: str = "breakout"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Volume Confirmation

        Role: VALIDATOR - Filters low-volume signals
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/volume/{symbol}"
            params = {"interval": interval, "signal_type": signal_type}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            # Convert volume confirmation to signal
            if data["confirmed"]:
                signal = (
                    SignalAction.BUY
                    if data["strength"] in ["STRONG", "MODERATE"]
                    else SignalAction.HOLD
                )
            else:
                signal = SignalAction.HOLD

            return IndicatorSignal(
                name="VOLUME_CONFIRMATION",
                signal=signal,
                confidence=data["confidence"],
                value=data["volume_ratio"],
                metadata={
                    "confirmed": data["confirmed"],
                    "strength": data["strength"],
                    "current_volume": data["current_volume"],
                    "avg_volume": data["avg_volume"],
                    "role": "VALIDATOR",
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Volume Confirmation for {symbol}: {e}")
            return None

    async def fetch_atr(self, symbol: str, interval: str = "60") -> Optional[Dict]:
        """
        Fetch ATR (Average True Range)

        Role: RISK MANAGER - Provides dynamic stop-loss levels
        Returns: Dict (not IndicatorSignal) as it's used for position sizing
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/atr/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return {
                "atr": data["atr"],
                "atr_pct": data["atr_pct"],
                "stop_loss_long": data["stop_loss_long"],
                "stop_loss_short": data["stop_loss_short"],
                "take_profit_long": data["take_profit_long"],
                "take_profit_short": data["take_profit_short"],
                "volatility": data["volatility"],
                "confidence": data["confidence"],
                "risk_reward_ratio": data["risk_reward_ratio"],
            }

        except Exception as e:
            logger.error(f"Error fetching ATR for {symbol}: {e}")
            return None

    async def fetch_adx(
        self,
        symbol: str,
        interval: str = "60",
    ) -> Optional["IndicatorSignal"]:
        """
        Fetch ADX (regime detector for HybridStrategyRouter — 2026-05-06).

        Role: TREND-STRENGTH GATE. ADX value flows into the indicators dict so
        downstream regime-aware logic (HybridStrategyRouter) can pick
        trend-following vs mean-reversion. Confidence is the TA service's
        derived value; signal direction follows +DI vs -DI bias.

        Returns IndicatorSignal so the aggregator's voter can fold it like any
        other leg, AND stamps `adx` into metadata for direct lookup.
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/adx/{symbol}"
            response = await self.client.get(url, params={"interval": interval})
            response.raise_for_status()
            data = response.json().get("data", {})
            adx_val = float(data.get("adx", 0.0))
            direction = data.get("direction", "NEUTRAL")
            regime = data.get("regime", "UNKNOWN")
            confidence = float(data.get("confidence", 0.0))
            # Map direction → SignalAction; ADX itself is a strength gauge,
            # only emit BUY/SELL when ADX>=20 (weak-trend threshold) so we
            # don't fold noise into the voter.
            if adx_val >= 20.0 and direction == "BULLISH":
                signal_action = SignalAction.BUY
            elif adx_val >= 20.0 and direction == "BEARISH":
                signal_action = SignalAction.SELL
            else:
                signal_action = SignalAction.HOLD
            return IndicatorSignal(
                name="ADX",
                signal=signal_action,
                confidence=confidence,
                value=adx_val,
                metadata={
                    "adx": adx_val,
                    "plus_di": data.get("plus_di"),
                    "minus_di": data.get("minus_di"),
                    "regime": regime,
                    "direction": direction,
                    "role": "TREND_GATE",
                    "weight": 1.0,
                },
            )
        except Exception as e:
            logger.error(f"Error fetching ADX for {symbol}: {e}")
            return None

    async def fetch_stochastic(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Stochastic Oscillator

        Role: MOMENTUM INDICATOR - Timing confirmation
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/stochastic/{symbol}"
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            return IndicatorSignal(
                name="STOCHASTIC",
                signal=SignalAction(data["signal"]),
                confidence=data["confidence"],
                value=data["k"],
                metadata={
                    "k": data["k"],
                    "d": data["d"],
                    "condition": data["condition"],
                    "crossover": data["crossover"],
                    "role": "MOMENTUM",
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Stochastic for {symbol}: {e}")
            return None

    # ==================== ADVANCED INDICATORS (2025-11-26) ====================

    async def fetch_rsi_divergence(
        self, symbol: str, interval: str = "60", period: int = 14, lookback: int = 20
    ) -> Optional[IndicatorSignal]:
        """
        Fetch RSI Divergence indicator

        Role: REVERSAL DETECTOR - Identifies potential trend reversals
        Detects bullish and bearish divergences between price and RSI

        Signals:
        - Bullish divergence: Price makes lower low, RSI makes higher low -> BUY
        - Bearish divergence: Price makes higher high, RSI makes lower high -> SELL
        - No divergence: HOLD

        Weight: 1.2x (high weight due to strong reversal signal quality)
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/rsi-divergence/{symbol}"
            params = {"interval": interval, "period": period, "lookback": lookback}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            # Handle list format: [indicator_data, signal, confidence, details]
            # or dict format: {"signal": ..., "confidence": ..., ...}
            if isinstance(data, list):
                # List format: [data_dict, signal_str, confidence_float, ...]
                indicator_data = data[0] if len(data) > 0 else {}
                signal_value = data[1] if len(data) > 1 else "HOLD"
                confidence = data[2] if len(data) > 2 else 0.5
                details = data[3] if len(data) > 3 else {}
                # Merge indicator_data and details
                rsi_value = indicator_data.get(
                    "current_rsi", details.get("current_rsi", 50.0)
                )
                bullish_div = indicator_data.get("bullish_divergence") or details.get(
                    "bullish_divergence"
                )
                bearish_div = indicator_data.get("bearish_divergence") or details.get(
                    "bearish_divergence"
                )
            else:
                # Dict format (original expected)
                signal_value = data.get("signal", "HOLD")
                confidence = data.get("confidence", 0.5)
                rsi_value = data.get("rsi", data.get("current_rsi", 50.0))
                bullish_div = data.get("bullish_divergence")
                bearish_div = data.get("bearish_divergence")

            # Determine divergence type
            divergence_type = "NONE"
            if (
                bullish_div
                and isinstance(bullish_div, dict)
                and bullish_div.get("detected")
            ):
                divergence_type = "BULLISH"
            elif (
                bearish_div
                and isinstance(bearish_div, dict)
                and bearish_div.get("detected")
            ):
                divergence_type = "BEARISH"

            return IndicatorSignal(
                name="RSI_DIVERGENCE",
                signal=SignalAction(signal_value),
                confidence=confidence,
                value=rsi_value,
                metadata={
                    "divergence_type": divergence_type,
                    "bullish_divergence": bullish_div,
                    "bearish_divergence": bearish_div,
                    "period": period,
                    "lookback": lookback,
                    "role": "REVERSAL_DETECTOR",
                    "weight": 1.2,  # High weight for divergence signals
                },
            )

        except Exception as e:
            logger.error(f"Error fetching RSI Divergence for {symbol}: {e}")
            return None

    async def fetch_ichimoku(
        self, symbol: str, interval: str = "60"
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Ichimoku Cloud indicator using the TA service's declared periods

        Parameter drift fix (phase 21 P21-5): this client previously forced
        20/60/120 while the TA service defaults were the traditional 9/26/52,
        so the traded path ran on 20/60/120 and a bare call to the same
        endpoint resolved to 9/26/52. 20/60/120 won because it is the live
        traded value (and what the route descriptions already advertised); it
        now lives in the TA service's config.py as `default_ichimoku_tenkan`,
        `_kijun` and `_senkou_b`. We omit all three so that declaration is the
        single source of truth.

        Role: MULTI-ASPECT TREND - Japanese trading system with 5 components
        Provides comprehensive trend, momentum, and support/resistance analysis

        Components (CRYPTO-OPTIMIZED 2025-12-23):
        - Tenkan-sen (Conversion Line): Short-term trend (20 periods, was 9)
        - Kijun-sen (Base Line): Medium-term trend (60 periods, was 26)
        - Senkou Span A: Leading span A (cloud boundary)
        - Senkou Span B: Leading span B (cloud boundary, 120 periods, was 52)
        - Chikou Span: Lagging span

        Research: Traditional 9-26-52 based on Japanese markets (5-day/1-month work weeks)
        Crypto 20-60-120 accounts for 24/7 trading (7-day weeks vs 5-day)

        Signals:
        - Price above cloud + TK cross up -> Strong BUY
        - Price below cloud + TK cross down -> Strong SELL
        - Price in cloud -> HOLD (consolidation)

        Weight: 1.3x (high weight due to multi-factor confirmation)
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/ichimoku/{symbol}"
            # No tenkan/kijun/senkou_b here on purpose — use the TA service
            # defaults (currently 20/60/120) instead of drifting local
            # overrides.
            params = {"interval": interval}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            # Handle list format: [indicator_data, signal, confidence]
            # or dict format: {"signal": ..., "confidence": ..., ...}
            if isinstance(data, list):
                # List format: [data_dict, signal_str, confidence_float]
                indicator_data = data[0] if len(data) > 0 else {}
                signal_value = data[1] if len(data) > 1 else "HOLD"
                confidence = data[2] if len(data) > 2 else 0.5
            else:
                # Dict format (original expected)
                indicator_data = data
                signal_value = data.get("signal", "HOLD")
                confidence = data.get("confidence", 0.5)

            return IndicatorSignal(
                name="ICHIMOKU",
                signal=SignalAction(signal_value),
                confidence=confidence,
                value=indicator_data.get("current_price", 0.0),
                metadata={
                    "tenkan_sen": indicator_data.get("tenkan_sen", 0.0),
                    "kijun_sen": indicator_data.get("kijun_sen", 0.0),
                    "senkou_span_a": indicator_data.get("senkou_span_a", 0.0),
                    "senkou_span_b": indicator_data.get("senkou_span_b", 0.0),
                    "chikou_span": indicator_data.get("chikou_span", 0.0),
                    "cloud_color": indicator_data.get("cloud_color", "NEUTRAL"),
                    "price_position": indicator_data.get("price_position", "IN_CLOUD"),
                    "tk_cross": indicator_data.get("tk_cross", "NONE"),
                    "cloud_thickness": indicator_data.get("cloud_thickness", 0.0),
                    # Periods are owned and applied by the TA service; the
                    # engine no longer holds a copy to report.
                    "role": "MULTI_ASPECT_TREND",
                    "weight": 1.3,  # Moderate weight for comprehensive trend analysis
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Ichimoku for {symbol}: {e}")
            return None

    async def fetch_enhanced_sqzmom(
        self,
        symbol: str,
        interval: str = "60",
        bb_period: int = 20,
        bb_mult: float = 2.0,
        kc_period: int = 20,
        kc_mult: float = 1.5,
        mom_period: int = 12,
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Enhanced Squeeze Momentum indicator

        Role: BREAKOUT DETECTOR - Identifies volatility compression and momentum direction
        Based on John Carter's TTM Squeeze with enhancements

        Components:
        - Squeeze ON: Bollinger Bands inside Keltner Channel (low volatility)
        - Squeeze OFF: Bollinger Bands outside Keltner Channel (volatility expansion)
        - Momentum: Linear regression based momentum histogram
        - Firing: First bar after squeeze releases (high probability breakout)

        Signals:
        - Squeeze firing + positive momentum -> BUY (breakout long)
        - Squeeze firing + negative momentum -> SELL (breakout short)
        - Squeeze ON -> HOLD (wait for breakout)
        - No squeeze + momentum -> Follow momentum direction

        Weight: 1.4x (highest weight for breakout signals due to high win rate)
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/sqzmom-enhanced/{symbol}"
            params = {
                "interval": interval,
                "bb_period": bb_period,
                "bb_mult": bb_mult,
                "kc_period": kc_period,
                "kc_mult": kc_mult,
                "mom_period": mom_period,
            }

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            result = response.json()
            data = result["data"]

            # Extract signal, confidence from response
            signal_value = data.get("signal", "HOLD")
            confidence = data.get("confidence", 0.5)

            return IndicatorSignal(
                name="SQZMOM_ENHANCED",
                signal=SignalAction(signal_value),
                confidence=confidence,
                value=data.get("momentum", 0.0),
                metadata={
                    "squeeze_on": data.get("squeeze_on", False),
                    "squeeze_off": data.get("squeeze_off", False),
                    "firing": data.get("firing", False),
                    "momentum": data.get("momentum", 0.0),
                    "momentum_direction": data.get("momentum_direction", "NEUTRAL"),
                    "momentum_increasing": data.get("momentum_increasing", False),
                    "squeeze_count": data.get("squeeze_count", 0),
                    "bb_upper": data.get("bb_upper", 0.0),
                    "bb_lower": data.get("bb_lower", 0.0),
                    "kc_upper": data.get("kc_upper", 0.0),
                    "kc_lower": data.get("kc_lower", 0.0),
                    "bb_period": bb_period,
                    "bb_mult": bb_mult,
                    "kc_period": kc_period,
                    "kc_mult": kc_mult,
                    "mom_period": mom_period,
                    "role": "BREAKOUT_DETECTOR",
                    "weight": 1.4,  # Highest weight for breakout signals
                },
            )

        except Exception as e:
            logger.error(f"Error fetching Enhanced SQZMOM for {symbol}: {e}")
            return None

    # ==================== FETCH ALL INDICATORS ====================

    async def fetch_all_indicators(
        self, symbol: str, interval: str = "60"
    ) -> tuple[Dict[str, IndicatorSignal], Optional[Dict]]:
        """
        Fetch all indicators in parallel

        Returns:
            tuple: (indicators_dict, atr_data)
            - indicators_dict: All voting indicators
            - atr_data: ATR data for dynamic stops (Dict or None)

        Indicator Categories (2025-12-17 Update - Optimization):
        - Original 5: RSI, MACD, Bollinger Bands, SMA, EMA
        - Phase 1: Trend Filter (GATEKEEPER), Volume Confirmation (VALIDATOR), Stochastic
        - Advanced: Ichimoku, SQZMOM_ENHANCED (re-enabled 2026-08-17), ADX (TREND_GATE, votes)
        - Disabled: RSI_DIVERGENCE (low confidence)
        - Risk Management: ATR (not a voting indicator)

        Total voting indicators: 9 (excludes ATR, TREND_FILTER, VOLUME_CONFIRMATION, disabled indicators)
        """
        logger.info(f"Fetching all indicators for {symbol} ({interval}m)")
        logger.info(
            "  Advanced: ICHIMOKU, SQZMOM_ENHANCED active; ADX votes (TREND_GATE); RSI_DIVERGENCE disabled"
        )

        # Fetch all indicators concurrently
        import asyncio

        tasks = {
            # Original 5 indicators
            "RSI": self.fetch_rsi(symbol, interval),
            "MACD": self.fetch_macd(symbol, interval),
            "BOLLINGER_BANDS": self.fetch_bollinger_bands(symbol, interval),
            "SMA": self.fetch_sma(symbol, interval),
            "EMA": self.fetch_ema(symbol, interval),
            # Phase 1 indicators
            "TREND_FILTER": self.fetch_trend_filter(symbol, interval),
            "VOLUME_CONFIRMATION": self.fetch_volume_confirmation(symbol, interval),
            "STOCHASTIC": self.fetch_stochastic(symbol, interval),
            # Advanced indicators (2025-11-26)
            # "RSI_DIVERGENCE": self.fetch_rsi_divergence(symbol, interval),  # DISABLED: stuck at 0.20 confidence
            "ICHIMOKU": self.fetch_ichimoku(symbol, interval),
            # Re-enabled 2026-08-17: the "stuck at 0.50 HOLD" cause was fixed
            # 2026-05-05 (indicator_service.py:403-422 — the endpoint read
            # non-prefixed keys; it now reads the sqz_-prefixed columns).
            "SQZMOM_ENHANCED": self.fetch_enhanced_sqzmom(symbol, interval),
            # ADX as TREND_GATE (added 2026-05-06). Required by
            # HybridStrategyRouter.detect_regime — without this leg the router
            # always falls through to RANGING regardless of actual market.
            "ADX": self.fetch_adx(symbol, interval),
            # Risk management (non-voting)
            "ATR": self.fetch_atr(symbol, interval),
        }

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Build indicator dictionary and extract ATR separately
        indicators = {}
        atr_data = None
        success_count = 0
        fail_count = 0

        for name, result in zip(tasks.keys(), results):
            if name == "ATR":
                # ATR is stored separately (not a voting indicator)
                if isinstance(result, dict):
                    atr_data = result
                    logger.info(
                        f"  [OK] ATR: {result['volatility']} volatility ({result['atr_pct']:.2f}%)"
                    )
                    success_count += 1
                else:
                    logger.warning("  [FAIL] ATR: Failed to fetch")
                    fail_count += 1
            elif isinstance(result, IndicatorSignal):
                indicators[name] = result
                # Log with indicator role if available
                role = result.metadata.get("role", "VOTER")
                weight = result.metadata.get("weight", 1.0)
                if weight != 1.0:
                    logger.info(
                        f"  [OK] {name}: {result.signal.value} (conf: {result.confidence:.2f}, role: {role}, weight: {weight}x)"
                    )
                else:
                    logger.info(
                        f"  [OK] {name}: {result.signal.value} (conf: {result.confidence:.2f}, role: {role})"
                    )
                success_count += 1
                # Record into rolling-confidence registry (2026-05-06).
                # was_voted=True for every active indicator; the False branch
                # is the shadow-mode hook reserved for a follow-up that
                # observes disabled indicators (RSI_DIVERGENCE) without
                # counting their vote.
                try:
                    await get_indicator_registry().record(
                        name=name,
                        confidence=float(result.confidence),
                        was_voted=True,
                    )
                except Exception as reg_err:  # noqa: BLE001 — telemetry must never break the trading loop
                    logger.warning(
                        "IndicatorRegistry.record(%s) failed: %s", name, reg_err
                    )
            else:
                logger.warning(
                    f"  [FAIL] {name}: Failed to fetch - {result if isinstance(result, Exception) else 'Unknown error'}"
                )
                fail_count += 1

        logger.info(
            f"Indicator fetch complete: {success_count} success, {fail_count} failed"
        )
        logger.info(
            f"Voting indicators available: {len([k for k in indicators.keys() if k not in ['TREND_FILTER', 'VOLUME_CONFIRMATION']])}"
        )

        return indicators, atr_data

    def signal_to_score(self, signal: SignalAction) -> float:
        """
        Convert signal action to numerical score
        REFACTORED: Delegates to SignalVoter

        BUY    -> +1.0
        SELL   -> -1.0
        HOLD   ->  0.0
        NEUTRAL->  0.0
        """
        # Delegate to modular voter component
        return self.core_aggregator.voter.signal_to_score(signal)

    def aggregate_signals(
        self,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None,
        symbol: Optional[str] = None,
    ) -> TradingSignal:
        """
        Aggregate individual indicator signals into a final trading signal

        REFACTORED: Delegates to CoreAggregator using Strangler Fig pattern

        PHASE 1 ENHANCEMENTS (Now Modular):
        1. Trend Filter as GATEKEEPER: Blocks counter-trend trades (gatekeeper.py)
        2. Volume Confirmation as VALIDATOR: Filters low-volume signals (validator.py)
        3. Voting logic with consensus requirements (voter.py)
        4. Orchestrated aggregation pipeline (aggregator_core.py)

        Pipeline:
        1. VOTER: Calculate preliminary signal from voting indicators
        2. GATEKEEPER: Block counter-trend trades
        3. VALIDATOR: Apply volume confidence penalty
        4. REQUIREMENTS: Check consensus and minimum confidence
        5. OUTPUT: Final TradingSignal
        """
        # Delegate to modular CoreAggregator
        return self.core_aggregator.aggregate_signals(
            indicators, timestamp, atr_data, symbol=symbol
        )

    async def aggregate_signals_enhanced(
        self,
        symbol: str,
        interval: str,
        indicators: Dict[str, IndicatorSignal],
        timestamp: int,
        atr_data: Optional[Dict] = None,
    ) -> TradingSignal:
        """
        PHASE 3 ENHANCED SIGNAL AGGREGATION

        Extends Phase 1 aggregation with:
        - ML price predictions (LSTM)
        - Sentiment analysis (news + social)
        - Multi-timeframe confirmation

        This method creates an EnhancedAggregator instance and uses it to
        combine technical indicators with ML and sentiment data.

        Args:
            symbol: Trading pair
            interval: Timeframe
            indicators: Technical indicators
            timestamp: Signal timestamp
            atr_data: ATR data for stops

        Returns:
            Enhanced TradingSignal with ML and sentiment metadata
        """
        from app.aggregation import EnhancedAggregator

        # Create enhanced aggregator
        enhanced = EnhancedAggregator(self.settings)

        try:
            # Use enhanced aggregation
            signal = await enhanced.aggregate_signals_enhanced(
                symbol=symbol,
                interval=interval,
                indicators=indicators,
                timestamp=timestamp,
                atr_data=atr_data,
            )
            return signal

        finally:
            # Cleanup
            await enhanced.close()

    async def get_trading_signal(
        self, symbol: str, interval: str = "60"
    ) -> TradingSignal:
        """
        Get complete trading signal for a symbol

        This is the main entry point for getting a trading signal.

        PHASE 1 UPDATE: Now fetches and includes ATR data for dynamic stops
        2025-11-26 UPDATE: Now includes advanced indicators (RSI Divergence, Ichimoku, SQZMOM)
        2026-05-15: Single-timeframe path now fetches market regime analysis and
        applies the ADX-based hard-block (counter-trend in TRENDING/STRONG_TREND).
        Previously regime adjustment only ran when callers explicitly fetched
        regime_analysis (auto-trader path); the read-only GET /signals/{symbol}
        endpoint bypassed it. With this change both paths get consistent gating.
        """
        import time

        timestamp = int(time.time() * 1000)

        # Fetch all indicators (returns both indicators and ATR data)
        indicators, atr_data = await self.fetch_all_indicators(symbol, interval)

        # Fetch regime analysis (best-effort; falls back to None on failure so
        # signal generation stays available even if ADX endpoint is degraded).
        regime_analysis = None
        try:
            regime_analysis = await self.core_aggregator.regime_detector.detect_regime(
                symbol, interval
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"Regime detection failed for {symbol} — proceeding without "
                f"regime hard-block: {e}"
            )

        # Aggregate signals with ATR data + regime analysis
        signal = self.core_aggregator.aggregate_signals(
            indicators, timestamp, atr_data, regime_analysis=regime_analysis,
            symbol=symbol,
        )
        signal.symbol = symbol

        return signal

    async def get_trading_signal_multi_timeframe(
        self,
        symbol: str,
        primary_interval: str = "60",
        timeframes: Optional[List[str]] = None,
        regime_analysis=None,  # Optional: Pre-fetched market regime analysis (2025-11-28)
    ) -> TradingSignal:
        """
        Get trading signal with multi-timeframe confirmation (Phase 2)

        This method fetches signals from multiple timeframes (15m, 60m, 240m)
        and applies consensus analysis to improve signal quality.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            primary_interval: Primary timeframe (default: 60m)
            timeframes: List of timeframes to analyze (default: ["15", "60", "240"])
            regime_analysis: Pre-fetched market regime analysis (optional, 2025-11-28)

        Returns:
            TradingSignal with multi-timeframe confidence adjustment
        """
        from app.aggregation import get_multi_timeframe_analyzer
        import time

        timestamp = int(time.time() * 1000)

        # Use default timeframes if not provided
        if timeframes is None:
            timeframes = ["15", "60", "240"]

        logger.info(f"Multi-timeframe analysis for {symbol}")
        logger.info(f"   Timeframes: {timeframes}m, Primary: {primary_interval}m")

        # Fetch signals from all timeframes concurrently
        signal_tasks = {
            interval: self.get_trading_signal(symbol, interval)
            for interval in timeframes
        }

        signals = {}
        for interval, task in signal_tasks.items():
            try:
                signals[interval] = await task
                logger.info(
                    f"   [OK] {interval}m: {signals[interval].action.value} (conf: {signals[interval].confidence:.2f})"
                )
            except Exception as e:
                logger.error(f"   [FAIL] {interval}m: Failed to fetch - {e}")

        # Ensure we have at least the primary signal
        if primary_interval not in signals:
            logger.error(f"Failed to fetch primary signal ({primary_interval}m)")
            # Fallback to single-timeframe
            return await self.get_trading_signal(symbol, primary_interval)

        # Get primary signal
        primary_signal = signals[primary_interval]

        # If we only have one timeframe, return it without analysis
        if len(signals) < 2:
            logger.warning(
                "Insufficient timeframes for multi-timeframe analysis, using primary only"
            )
            return primary_signal

        # Analyze multi-timeframe consensus
        mtf_analyzer = get_multi_timeframe_analyzer()
        mtf_analysis = await mtf_analyzer.analyze_timeframes(signals, primary_signal)

        # Apply confidence modifier from multi-timeframe analysis
        original_confidence = primary_signal.confidence
        consolidated_action, adjusted_confidence = consolidate_mtf_confidence(
            mtf_analysis, original_confidence
        )

        # 2026-08-27, P21-3. Record whether consolidation DEMOTED a directional
        # consensus to HOLD.
        #
        # Until this line existed the demotion was invisible downstream. The
        # metadata key written below as `consensus_action` carries
        # `mtf_analysis.consensus_action` -- the PRE-demotion blend -- so a
        # consensus that consolidate_mtf_confidence() demoted and a consensus
        # that was genuinely HOLD to begin with produced byte-identical
        # metadata. Nothing downstream could tell them apart.
        #
        # That is precisely why only ONE of the three ensemble legs honoured a
        # demotion. `multi_indicator` is guarded on
        # `aggregator_signal.action != HOLD` and therefore happens to see the
        # demoted action applied at `primary_signal.action` below; `simple_rsi`
        # and `mean_reversion` never read `.action` at all and traded straight
        # past a decision this function had already made. They cannot be gated
        # on something they cannot observe.
        #
        # Deliberately NARROW. `action == HOLD` reaches the ensemble from four
        # distinct upstream causes: this demotion, a raw consensus that was
        # genuinely HOLD, the regime hard-block further down this method, and a
        # per-timeframe requirements gate resolving HOLD inside aggregator_core.
        # This flag marks exactly one of them -- the demotion at
        # consolidate_mtf_confidence():71-78. The regime hard-block is arguably
        # the same class of defect and is deliberately NOT captured here:
        # 21-CONTEXT does not authorise gating on it, so it is named as a
        # follow-up rather than silently widened into.
        #
        # NO THRESHOLD VALUE CHANGED. MIN_AGREEING_LEGS (1),
        # AGGREGATION_THRESHOLD (0.10) and min_signal_confidence (0.30) are
        # untouched. This is observability wiring, not a gate.
        demoted_to_hold = (
            mtf_analysis.consensus_action != SignalAction.HOLD
            and consolidated_action == SignalAction.HOLD
        )

        logger.info("   Multi-timeframe adjustment:")
        logger.info(f"      Alignment: {mtf_analysis.alignment_strength.value}")
        logger.info(f"      Modifier: {mtf_analysis.confidence_modifier:.2f}x")
        logger.info(
            f"      Confidence: {original_confidence:.2f} -> {adjusted_confidence:.2f}"
        )
        logger.info(f"      Reasoning: {mtf_analysis.reasoning}")

        # Update signal with multi-timeframe analysis.
        #
        # 2026-08-22: apply consensus_action to the ACTION, not just the
        # confidence. Until this line existed, `consensus_action` was computed by
        # MultiTimeframeAnalyzer._calculate_weighted_consensus, written to the
        # metadata dict below, and never read by anything — while the returned
        # action stayed whatever the primary (60m) timeframe said. Measured over
        # 2,820 live evaluations the 60m timeframe was HOLD 100% of the time, so
        # the ensemble's `multi_indicator` leg (guarded on action != HOLD) could
        # never fire and the funnel emitted 0/146 signals.
        # See docs/FUNNEL_ROOT_CAUSE_2026-08-22.md.
        #
        # This is a dead-code repair, NOT a trade-unblocking change: recomputed
        # over 90 live cycles with the shipped weights (15m=0.20, 60m=0.50,
        # 240m=0.30) and the shipped +/-0.2 band, the consensus resolves to HOLD
        # in 90/90 cases (max score +0.106). The funnel stays empty because the
        # voting set cancels — trend voters pinned bullish, oscillators pinned
        # bearish, each individually correct. Do not "fix" that by lowering
        # thresholds; Phase-3 tested that and returned NO CHANGE.
        # 2026-08-23: confidence and action now come from the same place --
        # consolidate_mtf_confidence() weight-averages over the timeframes whose
        # GATED action matches the consensus, and demotes to HOLD when none does.
        # Previously confidence was the 60m primary's number regardless of which
        # action the consensus produced. See the helper's docstring.
        primary_signal.confidence = adjusted_confidence
        primary_signal.action = consolidated_action
        primary_signal.metadata["multi_timeframe"] = {
            "enabled": True,
            "timeframes": timeframes,
            "consensus_action": mtf_analysis.consensus_action.value,
            # P21-3 (2026-08-27): ADDITIVE keys. `consensus_action` above
            # is the pre-demotion blend and is left exactly as it was --
            # something downstream may already read it, and changing its
            # meaning to fix an observability gap would trade one silent
            # defect for another. See the block above the demotion
            # computation for why this pair exists and why it is narrow.
            "consolidated_action": consolidated_action.value,
            "demoted_to_hold": demoted_to_hold,
            "alignment_strength": mtf_analysis.alignment_strength.value,
            "confidence_modifier": mtf_analysis.confidence_modifier,
            "agreement_pct": mtf_analysis.agreement_pct,
            "reasoning": mtf_analysis.reasoning,
            "timeframe_signals": {
                interval: {
                    "action": tf.action.value,
                    "confidence": tf.confidence,
                    "score": tf.score,
                }
                for interval, tf in mtf_analysis.timeframe_signals.items()
            },
        }

        # Add market regime data if available (2025-11-28).
        # 2026-05-15: also apply regime hard-block here — the per-timeframe
        # signals are fetched via get_trading_signal() which does NOT receive
        # regime_analysis, so the core aggregator's regime step is bypassed in
        # this path. Apply it post-MTF on the primary signal to enforce the
        # ADX-based counter-trend block (see market_regime.apply_regime_adjustment).
        if regime_analysis:
            primary_signal.metadata["market_regime"] = {
                "regime": regime_analysis.regime.value,
                "direction": regime_analysis.direction.value,
                "adx": regime_analysis.adx,
                "plus_di": regime_analysis.plus_di,
                "minus_di": regime_analysis.minus_di,
                "confidence": regime_analysis.confidence,
                "confidence_modifier": regime_analysis.confidence_modifier,
                "description": regime_analysis.description,
                "strategy_recommendation": regime_analysis.strategy_recommendation,
            }

            adjusted_conf, regime_reason, regime_blocked = (
                self.core_aggregator.regime_detector.apply_regime_adjustment(
                    primary_signal.action,
                    primary_signal.confidence,
                    regime_analysis,
                )
            )
            primary_signal.confidence = adjusted_conf
            primary_signal.metadata["regime_blocked"] = regime_blocked
            primary_signal.metadata["regime_adjustment_reason"] = regime_reason

            if regime_blocked:
                logger.warning(
                    f"REGIME HARD-BLOCK (post-MTF): {primary_signal.action.value} "
                    f"on {symbol} rejected — {regime_reason}"
                )
                # P21-3, 2026-08-27: the redundant function-local
                # `from app.models import SignalAction` that used to sit here is
                # REMOVED. Python treats a name imported anywhere in a function
                # body as local to the WHOLE function, so this line shadowed the
                # module-level import at the top of the file and made
                # SignalAction unbound at every earlier reference in this method
                # (UnboundLocalError). The module-level import is the only one
                # needed -- do not reintroduce a local import here.
                primary_signal.action = SignalAction.HOLD
                primary_signal.metadata["meets_requirements"] = False

        return primary_signal

    async def get_trading_signal_enhanced(
        self, symbol: str, interval: str = "60", use_phase3: bool = True
    ) -> TradingSignal:
        """
        Get ENHANCED trading signal for a symbol (Phase 3)

        This is the Phase 3 entry point that includes:
        - Technical indicators (Phase 1)
        - ML price predictions
        - Sentiment analysis
        - Multi-timeframe confirmation

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes
            use_phase3: If False, fallback to Phase 1 signals only

        Returns:
            Enhanced TradingSignal with all Phase 3 features
        """
        import time

        timestamp = int(time.time() * 1000)

        # Fetch all indicators
        indicators, atr_data = await self.fetch_all_indicators(symbol, interval)

        # Use enhanced aggregation if enabled
        if use_phase3 and self.settings.enable_ml_predictions:
            signal = await self.aggregate_signals_enhanced(
                symbol=symbol,
                interval=interval,
                indicators=indicators,
                timestamp=timestamp,
                atr_data=atr_data,
            )
        else:
            # Fallback to Phase 1 aggregation
            # MLGATE-03 emission site E3 (Plan 09-03): the Phase-1 fallback is
            # the canonical ML-disabled branch on the routing path. No explicit
            # `reason` arg — defaults to get_current_reason() (D-09-03-06
            # cross-plan fallback). The actual log literal is emitted by
            # log_ml_disabled() in the helper module.
            log_ml_disabled(detail="fallback_to_phase1")
            signal = self.aggregate_signals(
                indicators, timestamp, atr_data, symbol=symbol
            )

        signal.symbol = symbol
        return signal


# Global signal aggregator instance
_aggregator: Optional[SignalAggregator] = None


async def get_aggregator() -> SignalAggregator:
    """Get or create signal aggregator instance"""
    global _aggregator
    if _aggregator is None:
        _aggregator = SignalAggregator()
    return _aggregator


async def close_aggregator():
    """Close signal aggregator"""
    global _aggregator
    if _aggregator is not None:
        await _aggregator.close()
        _aggregator = None
