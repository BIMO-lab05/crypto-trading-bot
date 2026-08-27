"""
Market Regime Detector Module
Purpose: Detects market regime using ADX indicator and adjusts confidence accordingly
Pattern: Strangler Fig - Modular component for signal aggregation pipeline

This module fetches ADX data from the technical-analysis service and classifies
the current market regime to help optimize trading strategy selection.

Market Regimes:
- STRONG_TREND: ADX >= 30, ideal for aggressive trend-following
- TRENDING: ADX 25-30, suitable for standard trend-following
- WEAK_TREND: ADX 20-25, caution advised, emerging/fading trends
- RANGING: ADX < 20, best for mean-reversion strategies
- VOLATILE: High ATR with unclear direction (special case)

Confidence Modifiers:
- STRONG_TREND: 1.2x boost for trend-following signals
- TRENDING: 1.1x boost for trend-following signals
- WEAK_TREND: 1.0x (no change)
- RANGING: 0.8x penalty for trend signals, 1.1x boost for mean-reversion
- VOLATILE: 0.7x penalty (higher risk environment)

Author: Backend Developer Agent
Date: 2025-11-28
"""

import logging
import httpx
from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from app.config import get_settings
from app.models import SignalAction

logger = logging.getLogger(__name__)


class MarketRegime(str, Enum):
    """
    Market regime classification based on ADX values

    Each regime suggests different trading approaches:
    - STRONG_TREND: Aggressive trend-following, larger position sizes
    - TRENDING: Standard trend-following strategies
    - WEAK_TREND: Cautious approach, smaller positions
    - RANGING: Mean-reversion strategies preferred
    - VOLATILE: Reduced exposure, tighter risk management
    - UNKNOWN: Unable to determine regime, use default behavior
    """

    STRONG_TREND = "STRONG_TREND"
    TRENDING = "TRENDING"
    WEAK_TREND = "WEAK_TREND"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class TrendDirection(str, Enum):
    """
    Trend direction based on +DI/-DI comparison

    BULLISH: +DI > -DI (upward momentum dominates)
    BEARISH: -DI > +DI (downward momentum dominates)
    NEUTRAL: +DI approximately equals -DI
    """

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass
class RegimeAnalysis:
    """
    Complete market regime analysis result

    Attributes:
        regime: Current market regime classification
        direction: Trend direction (bullish/bearish/neutral)
        adx: ADX value (0-100)
        plus_di: Positive Directional Indicator
        minus_di: Negative Directional Indicator
        confidence: Confidence in the regime classification (0.0-1.0)
        confidence_modifier: Multiplier to apply to signal confidence
        description: Human-readable description
        strategy_recommendation: Suggested trading strategy type
    """

    regime: MarketRegime
    direction: TrendDirection
    adx: float
    plus_di: float
    minus_di: float
    confidence: float
    confidence_modifier: float
    description: str
    strategy_recommendation: str


class MarketRegimeDetector:
    """
    MARKET REGIME DETECTOR: Classifies market conditions using ADX

    Responsibilities:
    - Fetch ADX data from technical-analysis service
    - Classify market regime (TRENDING, RANGING, etc.)
    - Calculate confidence modifiers based on regime
    - Provide strategy recommendations

    Integration Points:
    - Called AFTER gatekeeper and validator in aggregation pipeline
    - Provides regime-based confidence adjustment
    - Logs regime information for analysis

    Configuration:
    - Can be enabled/disabled via constructor
    - Configurable timeouts and thresholds
    - Caches regime data to reduce API calls
    """

    def __init__(
        self,
        enabled: bool = True,
        cache_ttl_seconds: int = 60,
        request_timeout: float = 5.0,
    ):
        """
        Initialize market regime detector

        Args:
            enabled: Enable/disable regime detection (default: True)
            cache_ttl_seconds: How long to cache regime data (default: 60s)
            request_timeout: HTTP request timeout in seconds (default: 5.0)

        Note:
            The ADX lookback is NOT a parameter here (P21-7, 2026-08-27). The
            technical-analysis service declares it and its /indicators/adx
            route resolves the query default from that declaration, so an
            engine-side copy was a second declaration that agreed only by
            coincidence. No caller ever passed it.
        """
        self.enabled = enabled
        self.cache_ttl = cache_ttl_seconds
        self.request_timeout = request_timeout
        self.settings = get_settings()

        # Statistics tracking
        self.detection_count = 0
        self.cache_hits = 0
        self.api_errors = 0

        # Regime counts for analysis
        self.regime_counts: Dict[MarketRegime, int] = {
            regime: 0 for regime in MarketRegime
        }

        # Simple cache: symbol -> (timestamp, regime_analysis)
        self._cache: Dict[str, Tuple[float, RegimeAnalysis]] = {}

        if self.enabled:
            logger.info(
                f"MarketRegimeDetector initialized: "
                f"cache_ttl={cache_ttl_seconds}s "
                f"(the ADX lookback is owned by technical-analysis)"
            )
        else:
            logger.info("MarketRegimeDetector initialized (DISABLED)")

    async def detect_regime(self, symbol: str, interval: str = "60") -> RegimeAnalysis:
        """
        Detect current market regime for a symbol

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            interval: Candlestick interval (default: "60" for 1 hour)

        Returns:
            RegimeAnalysis with complete regime information

        Note:
        - Returns UNKNOWN regime if detection fails or is disabled
        - Uses cached data if available and fresh
        """
        self.detection_count += 1

        # Return neutral analysis if disabled
        if not self.enabled:
            return self._get_default_analysis()

        # Check cache first
        import time

        cache_key = f"{symbol}_{interval}"
        if cache_key in self._cache:
            cached_time, cached_analysis = self._cache[cache_key]
            if time.time() - cached_time < self.cache_ttl:
                self.cache_hits += 1
                logger.debug(f"Cache hit for {symbol} regime")
                return cached_analysis

        # Fetch ADX data from technical-analysis service
        try:
            adx_data = await self._fetch_adx_data(symbol, interval)
            if not adx_data:
                logger.warning(f"No ADX data returned for {symbol}")
                return self._get_default_analysis()

            # Parse ADX response and classify regime
            analysis = self._analyze_regime(adx_data)

            # Update cache
            self._cache[cache_key] = (time.time(), analysis)

            # Update statistics
            self.regime_counts[analysis.regime] += 1

            logger.info(
                f"Market Regime for {symbol}: {analysis.regime.value} "
                f"(ADX: {analysis.adx:.1f}, Dir: {analysis.direction.value}, "
                f"Modifier: {analysis.confidence_modifier:.2f}x)"
            )

            return analysis

        except Exception as e:
            self.api_errors += 1
            logger.error(f"Error detecting regime for {symbol}: {e}", exc_info=True)
            return self._get_default_analysis()

    async def _fetch_adx_data(self, symbol: str, interval: str) -> Optional[Dict]:
        """
        Fetch ADX data from technical-analysis service

        Args:
            symbol: Trading symbol
            interval: Candlestick interval

        Returns:
            ADX data dictionary or None if request fails
        """
        url = f"{self.settings.technical_analysis_url}/api/v1/indicators/adx/{symbol}"
        # No lookback parameter here on purpose (P21-7, 2026-08-27) -- the
        # technical-analysis service declares it and resolves this route's
        # query default from that declaration. `signal_aggregator.fetch_adx`
        # already omits it; this was the last engine-side copy.
        # NO VALUE CHANGED: TA's declared default is the 14 this used to send.
        params = {"interval": interval, "limit": 100}

        try:
            async with httpx.AsyncClient(timeout=self.request_timeout) as client:
                response = await client.get(url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("data"):
                        return data["data"]
                    else:
                        logger.warning(f"ADX request successful but no data: {data}")
                        return None
                else:
                    logger.warning(
                        f"ADX request failed: status={response.status_code}, "
                        f"body={response.text[:200]}"
                    )
                    return None

        except httpx.TimeoutException:
            logger.warning(f"ADX request timed out for {symbol}")
            return None
        except Exception as e:
            logger.error(f"ADX request error for {symbol}: {e}")
            return None

    def _analyze_regime(self, adx_data: Dict) -> RegimeAnalysis:
        """
        Analyze ADX data and classify market regime

        Args:
            adx_data: ADX indicator data from technical-analysis service

        Returns:
            RegimeAnalysis with regime classification and modifiers
        """
        # Extract values from ADX data
        adx = float(adx_data.get("adx", 0))
        plus_di = float(adx_data.get("plus_di", 0))
        minus_di = float(adx_data.get("minus_di", 0))
        regime_str = adx_data.get("regime", "UNKNOWN")
        direction_str = adx_data.get("direction", "NEUTRAL")
        confidence = float(adx_data.get("confidence", 0.5))

        # Map regime string to enum
        try:
            if regime_str == "STRONG_TREND":
                regime = MarketRegime.STRONG_TREND
            elif regime_str == "TRENDING":
                regime = MarketRegime.TRENDING
            elif regime_str == "WEAK_TREND":
                regime = MarketRegime.WEAK_TREND
            elif regime_str == "RANGING":
                regime = MarketRegime.RANGING
            else:
                regime = MarketRegime.UNKNOWN
        except ValueError:
            regime = MarketRegime.UNKNOWN

        # Map direction string to enum
        try:
            direction = TrendDirection(direction_str)
        except ValueError:
            direction = TrendDirection.NEUTRAL

        # Calculate confidence modifier based on regime
        confidence_modifier = self._calculate_confidence_modifier(regime)

        # Generate strategy recommendation
        strategy_recommendation = self._get_strategy_recommendation(regime, direction)

        # Build description
        description = self._build_description(regime, direction, adx)

        return RegimeAnalysis(
            regime=regime,
            direction=direction,
            adx=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            confidence=confidence,
            confidence_modifier=confidence_modifier,
            description=description,
            strategy_recommendation=strategy_recommendation,
        )

    def _calculate_confidence_modifier(self, regime: MarketRegime) -> float:
        """
        Calculate confidence modifier based on market regime

        Args:
            regime: Current market regime

        Returns:
            Confidence multiplier (0.7-1.2)

        Modifiers:
        - STRONG_TREND: 1.2x boost (high probability trend continuation)
        - TRENDING: 1.1x boost (good trend-following conditions)
        - WEAK_TREND: 1.0x (neutral, no adjustment)
        - RANGING: 0.8x penalty (trend signals less reliable)
        - VOLATILE: 0.7x penalty (high risk environment)
        - UNKNOWN: 1.0x (no adjustment when uncertain)
        """
        modifiers = {
            MarketRegime.STRONG_TREND: 1.2,
            MarketRegime.TRENDING: 1.1,
            MarketRegime.WEAK_TREND: 1.0,
            MarketRegime.RANGING: 0.8,
            MarketRegime.VOLATILE: 0.7,
            MarketRegime.UNKNOWN: 1.0,
        }
        return modifiers.get(regime, 1.0)

    def _get_strategy_recommendation(
        self, regime: MarketRegime, direction: TrendDirection
    ) -> str:
        """
        Get strategy recommendation based on regime and direction

        Args:
            regime: Current market regime
            direction: Trend direction

        Returns:
            Strategy recommendation string
        """
        if regime == MarketRegime.STRONG_TREND:
            if direction == TrendDirection.BULLISH:
                return "Aggressive long trend-following, momentum strategies"
            elif direction == TrendDirection.BEARISH:
                return "Aggressive short trend-following, momentum strategies"
            else:
                return "Wait for clearer direction despite strong trend"

        elif regime == MarketRegime.TRENDING:
            if direction == TrendDirection.BULLISH:
                return "Standard long trend-following, buy dips"
            elif direction == TrendDirection.BEARISH:
                return "Standard short trend-following, sell rallies"
            else:
                return "Trend exists but direction unclear, reduce exposure"

        elif regime == MarketRegime.WEAK_TREND:
            return "Caution advised: emerging or fading trend, small positions"

        elif regime == MarketRegime.RANGING:
            return "Mean-reversion strategies, range trading, avoid breakout trades"

        elif regime == MarketRegime.VOLATILE:
            return "Reduce exposure, tighten stops, wait for clearer conditions"

        else:
            return "Unable to determine regime, use standard approach"

    def _build_description(
        self, regime: MarketRegime, direction: TrendDirection, adx: float
    ) -> str:
        """
        Build human-readable description of regime analysis

        Args:
            regime: Market regime
            direction: Trend direction
            adx: ADX value

        Returns:
            Description string
        """
        regime_descriptions = {
            MarketRegime.STRONG_TREND: "Strong trending market",
            MarketRegime.TRENDING: "Moderately trending market",
            MarketRegime.WEAK_TREND: "Weak trend developing or fading",
            MarketRegime.RANGING: "Ranging/sideways market",
            MarketRegime.VOLATILE: "Highly volatile conditions",
            MarketRegime.UNKNOWN: "Unable to classify market regime",
        }

        direction_descriptions = {
            TrendDirection.BULLISH: "bullish bias",
            TrendDirection.BEARISH: "bearish bias",
            TrendDirection.NEUTRAL: "no clear directional bias",
        }

        return (
            f"{regime_descriptions.get(regime, 'Unknown')} "
            f"(ADX: {adx:.1f}) with {direction_descriptions.get(direction, 'neutral bias')}"
        )

    def _get_default_analysis(self) -> RegimeAnalysis:
        """
        Get default regime analysis when detection fails or is disabled

        Returns:
            RegimeAnalysis with neutral/unknown values

        IMPORTANT for consumers: the returned analysis has
        ``confidence=0.0`` AND ``regime=MarketRegime.UNKNOWN``. The
        regime field is the canonical failure indicator — check it
        before trusting the other numeric fields, which are also 0.0.
        Audit-flagged 2026-04-28: confidence=0.0 by itself was a silent
        sentinel that downstream code couldn't tell apart from a
        real low-confidence regime. ``regime == MarketRegime.UNKNOWN``
        is the disambiguator.
        """
        return RegimeAnalysis(
            regime=MarketRegime.UNKNOWN,
            direction=TrendDirection.NEUTRAL,
            adx=0.0,
            plus_di=0.0,
            minus_di=0.0,
            confidence=0.0,
            confidence_modifier=1.0,  # No adjustment when unknown
            description="Market regime detection unavailable (failure sentinel)",
            strategy_recommendation="Use standard trading approach",
        )

    def apply_regime_adjustment(
        self, action: SignalAction, confidence: float, analysis: RegimeAnalysis
    ) -> Tuple[float, str, bool]:
        """
        Apply regime-based confidence adjustment.

        Args:
            action: Trading action (BUY/SELL/HOLD)
            confidence: Current signal confidence
            analysis: Regime analysis result

        Returns:
            Tuple of (adjusted_confidence, adjustment_reason, regime_blocked)

        Logic:
        - Trend-following signals (BUY in bullish, SELL in bearish) get boost in trends
        - Counter-trend signals in STRONG_TREND / TRENDING regimes are HARD-BLOCKED
          (added 2026-05-15 after May 6-7 whipsaw run: 25 closed positions / 0 winners.
          Oscillator-vs-trend disagreement was generating LONG entries against confirmed
          bearish trends, getting stopped out at -2% each. Soft 0.6x penalty was not
          enough — final cascade still let trades through. Hard-block forces HOLD.)
        - Counter-trend signals in WEAK_TREND keep the 0.6x soft penalty (ADX 20-25 is
          a transitioning regime where the trend is fading and reversal trades may be
          legitimate).
        - Mean-reversion signals get boost in ranging markets
        - HOLD signals are not adjusted
        """
        if action == SignalAction.HOLD:
            return confidence, "HOLD signal - no regime adjustment", False

        # Check if signal aligns with trend direction
        is_aligned = (
            action == SignalAction.BUY and analysis.direction == TrendDirection.BULLISH
        ) or (
            action == SignalAction.SELL and analysis.direction == TrendDirection.BEARISH
        )

        is_counter_trend = (
            action == SignalAction.BUY and analysis.direction == TrendDirection.BEARISH
        ) or (
            action == SignalAction.SELL and analysis.direction == TrendDirection.BULLISH
        )

        regime_blocked = False

        # Apply modifier based on regime and alignment
        if analysis.regime in [MarketRegime.STRONG_TREND, MarketRegime.TRENDING]:
            if is_aligned:
                # Trend-following signal in trending market - boost
                adjusted = confidence * analysis.confidence_modifier
                reason = (
                    f"Trend-aligned signal boosted: {analysis.regime.value} "
                    f"(x{analysis.confidence_modifier:.2f})"
                )
            elif is_counter_trend:
                # HARD-BLOCK counter-trend signals in confirmed trend regimes
                # (ADX >= 25 by definition of TRENDING / STRONG_TREND).
                # Confidence is zeroed so any downstream gate that bypasses the
                # regime_blocked flag still rejects the signal.
                adjusted = 0.0
                regime_blocked = True
                reason = (
                    f"Counter-trend HARD-BLOCKED in {analysis.regime.value} "
                    f"(ADX={analysis.adx:.1f}, +DI={analysis.plus_di:.1f}, "
                    f"-DI={analysis.minus_di:.1f})"
                )
            else:
                # Neutral direction - small adjustment
                adjusted = confidence * analysis.confidence_modifier
                reason = f"Regime adjustment: {analysis.regime.value}"

        elif analysis.regime == MarketRegime.RANGING:
            if is_counter_trend or analysis.direction == TrendDirection.NEUTRAL:
                # Mean-reversion potential in ranging market - small boost
                adjusted = confidence * 1.1
                reason = "Ranging market - mean-reversion signal boosted (x1.1)"
            else:
                # Trend-following in ranging market - penalty
                adjusted = confidence * analysis.confidence_modifier  # 0.8x
                reason = f"Trend signal penalized in ranging market (x{analysis.confidence_modifier:.2f})"

        elif analysis.regime == MarketRegime.VOLATILE:
            # All signals penalized in volatile conditions
            adjusted = confidence * analysis.confidence_modifier  # 0.7x
            reason = f"Volatile market penalty (x{analysis.confidence_modifier:.2f})"

        elif analysis.regime == MarketRegime.WEAK_TREND and is_counter_trend:
            # WEAK_TREND (ADX 20-25): transitioning regime. Counter-trend trades may
            # be legitimate reversals. Keep soft 0.6x penalty (was the old behavior
            # for all trend regimes; now only retained for WEAK_TREND).
            adjusted = confidence * 0.6
            reason = f"Counter-trend penalty in {analysis.regime.value} (x0.60, soft)"

        else:
            # WEAK_TREND aligned/neutral or UNKNOWN - no adjustment
            adjusted = confidence
            reason = f"No adjustment for {analysis.regime.value}"

        # Ensure confidence stays in valid range
        adjusted = max(0.0, min(1.0, adjusted))

        return adjusted, reason, regime_blocked

    def get_stats(self) -> Dict:
        """
        Get detector statistics

        Returns:
            Dictionary with detection statistics
        """
        total_detections = self.detection_count
        cache_hit_rate = (
            self.cache_hits / total_detections if total_detections > 0 else 0.0
        )

        return {
            "enabled": self.enabled,
            "total_detections": total_detections,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(cache_hit_rate, 2),
            "api_errors": self.api_errors,
            "regime_distribution": {
                regime.value: count
                for regime, count in self.regime_counts.items()
                if count > 0
            },
        }

    def reset_stats(self):
        """Reset all statistics"""
        self.detection_count = 0
        self.cache_hits = 0
        self.api_errors = 0
        self.regime_counts = {regime: 0 for regime in MarketRegime}
        self._cache.clear()
        logger.info("MarketRegimeDetector stats reset")


# Module-level singleton
_detector: Optional[MarketRegimeDetector] = None


def get_market_regime_detector(enabled: bool = True) -> MarketRegimeDetector:
    """
    Get or create the global market regime detector instance

    Args:
        enabled: Enable/disable regime detection

    Returns:
        MarketRegimeDetector singleton instance
    """
    global _detector
    if _detector is None:
        _detector = MarketRegimeDetector(enabled=enabled)
    return _detector


def reset_market_regime_detector():
    """Reset the global market regime detector instance (for testing)"""
    global _detector
    if _detector:
        _detector.reset_stats()
    _detector = None
