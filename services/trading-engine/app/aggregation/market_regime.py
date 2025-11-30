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
        adx_period: int = 14,
        cache_ttl_seconds: int = 60,
        request_timeout: float = 5.0
    ):
        """
        Initialize market regime detector

        Args:
            enabled: Enable/disable regime detection (default: True)
            adx_period: ADX calculation period (default: 14)
            cache_ttl_seconds: How long to cache regime data (default: 60s)
            request_timeout: HTTP request timeout in seconds (default: 5.0)
        """
        self.enabled = enabled
        self.adx_period = adx_period
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
                f"adx_period={adx_period}, cache_ttl={cache_ttl_seconds}s"
            )
        else:
            logger.info("MarketRegimeDetector initialized (DISABLED)")

    async def detect_regime(
        self,
        symbol: str,
        interval: str = "60"
    ) -> RegimeAnalysis:
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

    async def _fetch_adx_data(
        self,
        symbol: str,
        interval: str
    ) -> Optional[Dict]:
        """
        Fetch ADX data from technical-analysis service

        Args:
            symbol: Trading symbol
            interval: Candlestick interval

        Returns:
            ADX data dictionary or None if request fails
        """
        url = (
            f"{self.settings.technical_analysis_url}"
            f"/api/v1/indicators/adx/{symbol}"
        )
        params = {
            "interval": interval,
            "period": self.adx_period,
            "limit": 100
        }

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
            strategy_recommendation=strategy_recommendation
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
            MarketRegime.UNKNOWN: 1.0
        }
        return modifiers.get(regime, 1.0)

    def _get_strategy_recommendation(
        self,
        regime: MarketRegime,
        direction: TrendDirection
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
        self,
        regime: MarketRegime,
        direction: TrendDirection,
        adx: float
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
            MarketRegime.UNKNOWN: "Unable to classify market regime"
        }

        direction_descriptions = {
            TrendDirection.BULLISH: "bullish bias",
            TrendDirection.BEARISH: "bearish bias",
            TrendDirection.NEUTRAL: "no clear directional bias"
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
        """
        return RegimeAnalysis(
            regime=MarketRegime.UNKNOWN,
            direction=TrendDirection.NEUTRAL,
            adx=0.0,
            plus_di=0.0,
            minus_di=0.0,
            confidence=0.0,
            confidence_modifier=1.0,  # No adjustment when unknown
            description="Market regime detection unavailable",
            strategy_recommendation="Use standard trading approach"
        )

    def apply_regime_adjustment(
        self,
        action: SignalAction,
        confidence: float,
        analysis: RegimeAnalysis
    ) -> Tuple[float, str]:
        """
        Apply regime-based confidence adjustment

        Args:
            action: Trading action (BUY/SELL/HOLD)
            confidence: Current signal confidence
            analysis: Regime analysis result

        Returns:
            Tuple of (adjusted_confidence, adjustment_reason)

        Logic:
        - Trend-following signals (BUY in bullish, SELL in bearish) get boost in trends
        - Counter-trend signals get penalized in trends
        - Mean-reversion signals get boost in ranging markets
        - HOLD signals are not adjusted
        """
        if action == SignalAction.HOLD:
            return confidence, "HOLD signal - no regime adjustment"

        # Check if signal aligns with trend direction
        is_aligned = (
            (action == SignalAction.BUY and analysis.direction == TrendDirection.BULLISH) or
            (action == SignalAction.SELL and analysis.direction == TrendDirection.BEARISH)
        )

        is_counter_trend = (
            (action == SignalAction.BUY and analysis.direction == TrendDirection.BEARISH) or
            (action == SignalAction.SELL and analysis.direction == TrendDirection.BULLISH)
        )

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
                # Counter-trend signal in trending market - heavy penalty
                penalty = 0.6  # 40% penalty for counter-trend in strong trend
                adjusted = confidence * penalty
                reason = f"Counter-trend penalty in {analysis.regime.value} (x{penalty:.2f})"
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

        else:
            # WEAK_TREND or UNKNOWN - no adjustment
            adjusted = confidence
            reason = f"No adjustment for {analysis.regime.value}"

        # Ensure confidence stays in valid range
        adjusted = max(0.0, min(1.0, adjusted))

        return adjusted, reason

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
            }
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
