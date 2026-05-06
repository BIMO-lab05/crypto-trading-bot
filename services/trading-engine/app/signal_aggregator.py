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
from app.services.indicator_registry import get_indicator_registry

logger = logging.getLogger(__name__)


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
        Fetch MACD indicator with research-optimized parameters

        RESEARCH-BACKED PARAMETERS (2025 Crypto Trading Research):
        - Standard 12-26-9: Good for stocks, slow for crypto
        - Optimal 8-17-9: Best risk-adjusted returns for crypto day trading
        - Academic research: ~70% profitable trades with 1.51 profit factor
        """
        try:
            url = f"{self.base_url}/api/v1/indicators/macd/{symbol}"
            # RESEARCH-OPTIMIZED (2025): 8-17-9 proven optimal for crypto day trading
            # Balanced between responsiveness and accuracy
            params = {
                "interval": interval,
                "fast": 8,  # Research: Optimal for crypto volatility
                "slow": 17,  # Research: Best risk-adjusted returns
                "signal": 9,  # Research: Standard signal period works well
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
                        "parameters", {"fast": 8, "slow": 17, "signal": 9}
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
        self,
        symbol: str,
        interval: str = "60",
        period: int = 21,  # Matches research-optimized EMA period
    ) -> Optional[IndicatorSignal]:
        """Fetch SMA indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/sma/{symbol}"
            params = {"interval": interval, "period": period}

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
                    "period": period,
                    "weight": 0.8,  # Moderate weight for trend confirmation
                },
            )

        except Exception as e:
            logger.error(f"Error fetching SMA for {symbol}: {e}")
            return None

    async def fetch_ema(
        self,
        symbol: str,
        interval: str = "60",
        period: int = 21,  # Research-optimized EMA period (2025-12-23)
    ) -> Optional[IndicatorSignal]:
        """Fetch EMA indicator"""
        try:
            url = f"{self.base_url}/api/v1/indicators/ema/{symbol}"
            params = {"interval": interval, "period": period}

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
                    "period": period,
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
        self,
        symbol: str,
        interval: str = "60",
        tenkan_period: int = 20,
        kijun_period: int = 60,
        senkou_b_period: int = 120,
    ) -> Optional[IndicatorSignal]:
        """
        Fetch Ichimoku Cloud indicator

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
            params = {
                "interval": interval,
                "tenkan_period": tenkan_period,
                "kijun_period": kijun_period,
                "senkou_b_period": senkou_b_period,
            }

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
                    "tenkan_period": tenkan_period,
                    "kijun_period": kijun_period,
                    "senkou_b_period": senkou_b_period,
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
        - Advanced: Ichimoku (RSI_DIVERGENCE and SQZMOM_ENHANCED disabled for low confidence)
        - Risk Management: ATR (not a voting indicator)

        Total voting indicators: 9 (excludes ATR, TREND_FILTER, VOLUME_CONFIRMATION, disabled indicators)
        """
        logger.info(f"Fetching all indicators for {symbol} ({interval}m)")
        logger.info(
            "  Including advanced indicators: ICHIMOKU (RSI_DIVERGENCE and SQZMOM_ENHANCED disabled for better confidence)"
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
            # "SQZMOM_ENHANCED": self.fetch_enhanced_sqzmom(symbol, interval),  # DISABLED: stuck at 0.50 HOLD
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
                # observes disabled indicators (RSI_DIVERGENCE,
                # SQZMOM_ENHANCED) without counting their vote.
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
        return self.core_aggregator.aggregate_signals(indicators, timestamp, atr_data)

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
        """
        import time

        timestamp = int(time.time() * 1000)

        # Fetch all indicators (returns both indicators and ATR data)
        indicators, atr_data = await self.fetch_all_indicators(symbol, interval)

        # Aggregate signals with ATR data
        signal = self.aggregate_signals(indicators, timestamp, atr_data)
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
        adjusted_confidence = original_confidence * mtf_analysis.confidence_modifier

        logger.info("   Multi-timeframe adjustment:")
        logger.info(f"      Alignment: {mtf_analysis.alignment_strength.value}")
        logger.info(f"      Modifier: {mtf_analysis.confidence_modifier:.2f}x")
        logger.info(
            f"      Confidence: {original_confidence:.2f} -> {adjusted_confidence:.2f}"
        )
        logger.info(f"      Reasoning: {mtf_analysis.reasoning}")

        # Update signal with multi-timeframe analysis
        primary_signal.confidence = adjusted_confidence
        primary_signal.metadata["multi_timeframe"] = {
            "enabled": True,
            "timeframes": timeframes,
            "consensus_action": mtf_analysis.consensus_action.value,
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

        # Add market regime data if available (2025-11-28)
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
            signal = self.aggregate_signals(indicators, timestamp, atr_data)

        signal.symbol = symbol
        return signal

    async def get_trading_signal_with_vp(
        self,
        symbol: str,
        primary_interval: str = "60",
        timeframes: Optional[List[str]] = None,
        enable_vp: bool = True,
        vp_lookback: int = 100,
    ) -> TradingSignal:
        """
        Get trading signal with Volume Profile integration (Phase 3 - VP Strategy)

        Combines multi-timeframe confirmation with volume profile analysis
        for enhanced entry/exit levels and strategy selection.

        Args:
            symbol: Trading pair
            primary_interval: Primary timeframe
            timeframes: Timeframes for MTF analysis
            enable_vp: Enable volume profile analysis
            vp_lookback: Number of candles for VP calculation

        Returns:
            TradingSignal with VP enhancements
        """
        from app.volume_profile import get_vp_calculator
        from app.vp_strategy import get_vp_strategy_analyzer

        # Get multi-timeframe signal first (Phase 2)
        signal = await self.get_trading_signal_multi_timeframe(
            symbol=symbol, primary_interval=primary_interval, timeframes=timeframes
        )

        # If VP not enabled, return MTF signal as-is
        if not enable_vp:
            return signal

        try:
            # Fetch historical candles for VP calculation
            candles = await self._fetch_candles_for_vp(
                symbol=symbol, interval=primary_interval, limit=vp_lookback
            )

            if not candles or len(candles) < 10:
                logger.warning(
                    f"Insufficient candles for VP calculation ({len(candles) if candles else 0})"
                )
                return signal

            # Calculate volume profile
            vp_calculator = get_vp_calculator()
            vp_profile = vp_calculator.calculate_profile(
                symbol=symbol, interval=primary_interval, candles=candles
            )

            if not vp_profile:
                logger.warning(f"VP calculation failed for {symbol}")
                return signal

            # Get current price from signal metadata
            current_price = None
            for indicator_name, indicator_signal in signal.indicators.items():
                if hasattr(indicator_signal, "metadata") and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = Decimal(
                            str(indicator_signal.metadata["current_price"])
                        )
                        break

            if not current_price:
                logger.warning("No current price found in signal")
                return signal

            # Analyze VP strategy
            vp_analyzer = get_vp_strategy_analyzer()

            # Convert signal to dict for VP analyzer
            mtf_signal_dict = {
                "action": signal.action,
                "confidence": signal.confidence,
                "metadata": signal.metadata,
            }

            vp_signal = vp_analyzer.analyze_vp_signal(
                symbol=symbol,
                current_price=current_price,
                vp_profile=vp_profile,
                mtf_signal=mtf_signal_dict,
            )

            # Combine VP signal with MTF signal
            combined = vp_analyzer.combine_with_mtf_signal(vp_signal, mtf_signal_dict)

            # Update original signal with VP enhancements
            signal.confidence = combined["confidence"]
            signal.metadata.update(combined.get("metadata", {}))
            signal.metadata["vp_strategy"] = combined.get("vp_strategy")
            signal.metadata["vp_position"] = combined.get("vp_position")
            signal.metadata["vp_confidence_modifier"] = combined.get(
                "vp_confidence_modifier"
            )

            logger.info(
                f"VP Analysis: {vp_signal.strategy_type.value} "
                f"| Position: {vp_signal.price_position} "
                f"| Modifier: {combined.get('vp_confidence_modifier', 1.0):.2f}x"
            )
            logger.info(
                f"   VP Levels: POC=${vp_profile.poc:.2f}, VAH=${vp_profile.vah:.2f}, VAL=${vp_profile.val:.2f}"
            )
            logger.info(f"   {vp_signal.reasoning}")

        except Exception as e:
            logger.error(f"VP analysis error for {symbol}: {e}", exc_info=True)
            # Return original signal if VP fails
            return signal

        return signal

    async def _fetch_candles_for_vp(
        self, symbol: str, interval: str, limit: int = 100
    ) -> List[Dict]:
        """
        Fetch historical candles for volume profile calculation

        Args:
            symbol: Trading symbol
            interval: Timeframe interval
            limit: Number of candles to fetch

        Returns:
            List of candle dicts with OHLCV data
        """
        try:
            # Fetch klines from TA service
            url = f"{self.base_url}/api/v1/klines/{symbol}"
            params = {"interval": interval, "limit": limit}

            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            klines = data.get("klines", [])

            # Convert to candle format expected by VP calculator
            candles = []
            for k in klines:
                candles.append(
                    {
                        "timestamp": datetime.fromtimestamp(k[0] / 1000),
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    }
                )

            logger.info(f"Fetched {len(candles)} candles for VP calculation")
            return candles

        except Exception as e:
            logger.error(f"Error fetching candles for VP: {e}")
            return []


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
