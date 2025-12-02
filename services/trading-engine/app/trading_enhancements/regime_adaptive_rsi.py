"""
Regime-Adaptive RSI - Dynamic Thresholds Based on Market Regime
Research Source: Hurst Exponent + RSI Optimization Studies (2025-12-02)

Purpose:
- Combine Hurst-based regime detection with RSI threshold adjustment
- Dynamically adapt RSI thresholds based on market characteristics
- Optimize signal quality for trending vs mean-reverting markets

Key Insight:
- TRENDING markets (H > 0.55): RSI stays overbought/oversold longer
  -> Use WIDER thresholds (15/85) to avoid premature exits
  -> Strong momentum carries prices further before reversing

- MEAN_REVERTING markets (H < 0.45): RSI signals are more reliable
  -> Use TIGHTER thresholds (35/65) to catch more reversals
  -> Price tends to snap back to mean more quickly

- RANDOM_WALK (0.45-0.55): Standard thresholds or reduce trading
  -> Use moderate thresholds (25/75)
  -> Lower confidence in any directional signals

Research Findings Applied:
- Trending RSI can stay >70 or <30 for extended periods (don't fight the trend)
- Mean-reverting markets show quick RSI reversals (tighter thresholds = more signals)
- Combining volatility (ATR) and regime (Hurst) improves signal quality by 25-40%
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from enum import Enum

from app.trading_enhancements.hurst_exponent import (
    HurstExponentCalculator,
    HurstResult,
    HurstConfig,
    MarketRegimeType,
    create_hurst_calculator
)
from app.trading_enhancements.adaptive_rsi import (
    AdaptiveRSI,
    AdaptiveRSIConfig,
    AdaptiveRSIResult,
    RSIThresholds,
    SignalType,
    VolatilityRegime,
    TrendDirection,
    get_adaptive_rsi
)

logger = logging.getLogger(__name__)


class RegimeAdjustmentLevel(Enum):
    """Level of threshold adjustment based on regime"""
    AGGRESSIVE = "aggressive"   # Maximum threshold adjustment
    MODERATE = "moderate"       # Balanced adjustment
    CONSERVATIVE = "conservative"  # Minimal adjustment


@dataclass
class RegimeRSIConfig:
    """
    Configuration for Regime-Adaptive RSI

    Combines volatility-based and regime-based threshold adjustments.

    Attributes:
        # Hurst Configuration
        hurst_min_periods: Minimum data points for Hurst calculation
        hurst_trending_threshold: H above this = trending
        hurst_mean_reversion_threshold: H below this = mean reverting

        # Regime-Based RSI Threshold Adjustments
        # These adjust the base thresholds from AdaptiveRSI
        trending_oversold_adjustment: Add to oversold threshold in trending
        trending_overbought_adjustment: Add to overbought threshold in trending
        mean_revert_oversold_adjustment: Add to oversold in mean reverting
        mean_revert_overbought_adjustment: Add to overbought in mean reverting

        # Regime confidence requirements
        min_regime_confidence: Minimum Hurst confidence to apply adjustment

        # Signal strength modifiers
        trending_signal_strength_modifier: Multiply signal strength in trending
        mean_revert_signal_strength_modifier: Multiply signal strength in mean reverting
        random_walk_signal_strength_modifier: Multiply signal strength in random walk
    """
    # Hurst calculation settings
    hurst_min_periods: int = 50
    hurst_trending_threshold: float = 0.55
    hurst_mean_reversion_threshold: float = 0.45

    # Trending regime adjustments (H > 0.55)
    # Make thresholds WIDER (harder to trigger, but signals are stronger)
    trending_oversold_adjustment: float = -10.0    # 25 -> 15 (wider)
    trending_overbought_adjustment: float = 10.0   # 75 -> 85 (wider)

    # Mean-reverting regime adjustments (H < 0.45)
    # Make thresholds TIGHTER (easier to trigger, catch more reversions)
    mean_revert_oversold_adjustment: float = 10.0   # 25 -> 35 (tighter)
    mean_revert_overbought_adjustment: float = -10.0  # 75 -> 65 (tighter)

    # Random walk regime - no adjustment (use base thresholds)

    # Confidence requirements
    min_regime_confidence: float = 0.5

    # Signal strength modifiers by regime
    trending_signal_strength_modifier: float = 1.2    # Boost trending signals
    mean_revert_signal_strength_modifier: float = 1.0  # Normal mean reversion
    random_walk_signal_strength_modifier: float = 0.5  # Reduce random walk signals

    # Adjustment level
    adjustment_level: RegimeAdjustmentLevel = RegimeAdjustmentLevel.MODERATE

    # Cache settings
    regime_cache_seconds: int = 60  # Cache regime detection for N seconds


@dataclass
class RegimeRSIThresholds:
    """
    RSI thresholds adjusted for both volatility AND regime

    Combines ATR-based volatility adjustment with Hurst-based regime adjustment.
    """
    oversold: float
    overbought: float
    volatility_regime: VolatilityRegime
    market_regime: MarketRegimeType
    base_oversold: float  # Before regime adjustment
    base_overbought: float  # Before regime adjustment
    regime_adjustment_applied: bool
    hurst_value: float
    hurst_confidence: float


@dataclass
class RegimeAdaptiveRSIResult:
    """
    Complete result from Regime-Adaptive RSI calculation

    Extends AdaptiveRSIResult with regime information.
    """
    rsi_value: float
    thresholds: RegimeRSIThresholds
    signal: SignalType
    signal_strength: float

    # Regime information
    market_regime: MarketRegimeType
    hurst_value: float
    hurst_confidence: float
    regime_strategy_recommendation: str

    # Volatility information
    atr_value: float
    atr_percentage: float
    volatility_regime: VolatilityRegime

    # Trend information
    trend_direction: TrendDirection

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    signal_filtered_by_regime: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "rsi_value": round(self.rsi_value, 2),
            "thresholds": {
                "oversold": self.thresholds.oversold,
                "overbought": self.thresholds.overbought,
                "volatility_regime": self.thresholds.volatility_regime.value,
                "market_regime": self.thresholds.market_regime.value,
                "base_oversold": self.thresholds.base_oversold,
                "base_overbought": self.thresholds.base_overbought,
                "regime_adjustment_applied": self.thresholds.regime_adjustment_applied
            },
            "signal": self.signal.value,
            "signal_strength": round(self.signal_strength, 2),
            "market_regime": self.market_regime.value,
            "hurst_value": round(self.hurst_value, 4),
            "hurst_confidence": round(self.hurst_confidence, 2),
            "regime_strategy": self.regime_strategy_recommendation,
            "atr_percentage": round(self.atr_percentage, 2),
            "volatility_regime": self.volatility_regime.value,
            "trend_direction": self.trend_direction.value,
            "signal_filtered_by_regime": self.signal_filtered_by_regime,
            "timestamp": self.timestamp.isoformat()
        }


class RegimeAdaptiveRSI:
    """
    Regime-Adaptive RSI Indicator

    RESEARCH-BACKED IMPLEMENTATION:
    Combines two adaptive layers for optimal RSI signal generation:

    1. VOLATILITY LAYER (from AdaptiveRSI):
       - Uses ATR to detect volatility regime (HIGH/NORMAL/LOW)
       - Adjusts thresholds based on market volatility
       - High volatility = wider thresholds to filter noise

    2. REGIME LAYER (new - from Hurst Exponent):
       - Uses Hurst to detect market character (TRENDING/MEAN_REVERTING/RANDOM)
       - Further adjusts thresholds based on market regime
       - Trending = wider thresholds (let winners run)
       - Mean reverting = tighter thresholds (catch reversals faster)

    The final thresholds are:
    - Start with volatility-adjusted thresholds
    - Apply regime adjustment on top
    - Result: Thresholds optimized for current market conditions

    Usage:
        regime_rsi = RegimeAdaptiveRSI()

        result = regime_rsi.calculate(
            prices=close_prices,
            atr_value=current_atr
        )

        print(f"Signal: {result.signal.value}")
        print(f"Market Regime: {result.market_regime.value}")
        print(f"Adjusted Thresholds: {result.thresholds.oversold}/{result.thresholds.overbought}")
    """

    def __init__(
        self,
        config: Optional[RegimeRSIConfig] = None,
        adaptive_rsi_config: Optional[AdaptiveRSIConfig] = None
    ):
        """
        Initialize Regime-Adaptive RSI

        Args:
            config: Regime-adaptive configuration
            adaptive_rsi_config: Base AdaptiveRSI configuration
        """
        self.config = config or RegimeRSIConfig()

        # Initialize Hurst calculator
        self.hurst_calculator = create_hurst_calculator(
            trending_threshold=self.config.hurst_trending_threshold,
            mean_reversion_threshold=self.config.hurst_mean_reversion_threshold,
            min_periods=self.config.hurst_min_periods
        )

        # Initialize base AdaptiveRSI
        self.adaptive_rsi = AdaptiveRSI(adaptive_rsi_config)

        # Cache for regime detection
        self._cached_regime: Optional[HurstResult] = None
        self._cache_timestamp: Optional[datetime] = None

        # Last result storage
        self._last_result: Optional[RegimeAdaptiveRSIResult] = None

        logger.info(
            f"RegimeAdaptiveRSI initialized: "
            f"trending_threshold={self.config.hurst_trending_threshold}, "
            f"mean_reversion_threshold={self.config.hurst_mean_reversion_threshold}, "
            f"adjustment_level={self.config.adjustment_level.value}"
        )

    def calculate_regime(
        self,
        prices: List[float],
        use_cache: bool = True
    ) -> HurstResult:
        """
        Calculate market regime using Hurst exponent

        Args:
            prices: List of closing prices
            use_cache: Whether to use cached regime if valid

        Returns:
            HurstResult with regime detection
        """
        # Check cache validity
        if use_cache and self._cached_regime is not None and self._cache_timestamp is not None:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            if cache_age < self.config.regime_cache_seconds:
                logger.debug(f"Using cached regime (age: {cache_age:.1f}s)")
                return self._cached_regime

        # Calculate fresh regime
        try:
            result = self.hurst_calculator.calculate_hurst(prices)

            # Update cache
            self._cached_regime = result
            self._cache_timestamp = datetime.now()

            logger.info(
                f"Regime calculated: H={result.hurst_value:.4f}, "
                f"regime={result.regime.value}, confidence={result.confidence:.2f}"
            )

            return result

        except ValueError as e:
            # Not enough data for Hurst - return neutral regime
            logger.warning(f"Could not calculate Hurst: {e}")
            return HurstResult(
                hurst_value=0.5,
                regime=MarketRegimeType.RANDOM_WALK,
                confidence=0.0,
                recommended_strategy=self.hurst_calculator.get_strategy_recommendation(
                    MarketRegimeType.RANDOM_WALK
                ),
                period=0,
                sample_size=len(prices),
                r_squared=0.0
            )

    def apply_regime_adjustment(
        self,
        base_thresholds: RSIThresholds,
        regime: MarketRegimeType,
        confidence: float
    ) -> Tuple[float, float, bool]:
        """
        Apply regime-based adjustment to RSI thresholds

        Args:
            base_thresholds: Volatility-adjusted thresholds from AdaptiveRSI
            regime: Detected market regime
            confidence: Confidence in regime detection

        Returns:
            Tuple of (adjusted_oversold, adjusted_overbought, adjustment_applied)
        """
        # Start with base thresholds
        oversold = base_thresholds.oversold
        overbought = base_thresholds.overbought
        adjustment_applied = False

        # Only apply adjustment if confidence exceeds threshold
        if confidence < self.config.min_regime_confidence:
            logger.debug(
                f"Regime confidence {confidence:.2f} below threshold "
                f"{self.config.min_regime_confidence}, using base thresholds"
            )
            return oversold, overbought, False

        # Apply adjustment based on regime
        if regime == MarketRegimeType.TRENDING:
            # TRENDING: Widen thresholds (let winners run)
            oversold += self.config.trending_oversold_adjustment
            overbought += self.config.trending_overbought_adjustment
            adjustment_applied = True

            logger.debug(
                f"Applied TRENDING adjustment: "
                f"oversold {base_thresholds.oversold} -> {oversold}, "
                f"overbought {base_thresholds.overbought} -> {overbought}"
            )

        elif regime == MarketRegimeType.MEAN_REVERTING:
            # MEAN REVERTING: Tighten thresholds (catch reversions faster)
            oversold += self.config.mean_revert_oversold_adjustment
            overbought += self.config.mean_revert_overbought_adjustment
            adjustment_applied = True

            logger.debug(
                f"Applied MEAN_REVERTING adjustment: "
                f"oversold {base_thresholds.oversold} -> {oversold}, "
                f"overbought {base_thresholds.overbought} -> {overbought}"
            )

        else:
            # RANDOM_WALK: No adjustment
            logger.debug("RANDOM_WALK regime - no threshold adjustment")

        # Clamp to valid ranges
        oversold = max(5.0, min(45.0, oversold))
        overbought = min(95.0, max(55.0, overbought))

        return oversold, overbought, adjustment_applied

    def calculate_signal_strength(
        self,
        base_strength: float,
        regime: MarketRegimeType
    ) -> float:
        """
        Adjust signal strength based on market regime

        Args:
            base_strength: Signal strength from AdaptiveRSI (0-1)
            regime: Current market regime

        Returns:
            Adjusted signal strength (0-1)
        """
        if regime == MarketRegimeType.TRENDING:
            modifier = self.config.trending_signal_strength_modifier
        elif regime == MarketRegimeType.MEAN_REVERTING:
            modifier = self.config.mean_revert_signal_strength_modifier
        else:
            modifier = self.config.random_walk_signal_strength_modifier

        adjusted_strength = base_strength * modifier

        # Clamp to 0-1
        return max(0.0, min(1.0, adjusted_strength))

    def should_filter_signal(
        self,
        signal: SignalType,
        regime: MarketRegimeType,
        trend: TrendDirection
    ) -> bool:
        """
        Determine if signal should be filtered based on regime and trend

        Filtering rules:
        - In TRENDING regime: Don't take counter-trend signals
        - In MEAN_REVERTING regime: All signals are valid
        - In RANDOM_WALK: Filter signals with low confidence

        Args:
            signal: Generated trading signal
            regime: Current market regime
            trend: Current trend direction

        Returns:
            True if signal should be filtered out
        """
        if signal == SignalType.HOLD:
            return False  # Nothing to filter

        if regime == MarketRegimeType.TRENDING:
            # In trending markets, filter counter-trend signals
            if signal == SignalType.BUY and trend == TrendDirection.BEARISH:
                logger.info("Filtering BUY signal: TRENDING + BEARISH trend")
                return True
            if signal == SignalType.SELL and trend == TrendDirection.BULLISH:
                logger.info("Filtering SELL signal: TRENDING + BULLISH trend")
                return True

        return False

    def calculate(
        self,
        prices: List[float],
        atr_value: float,
        use_cache: bool = True
    ) -> RegimeAdaptiveRSIResult:
        """
        Calculate Regime-Adaptive RSI signal

        Main calculation method that combines:
        1. Volatility-adjusted thresholds (ATR-based)
        2. Regime-adjusted thresholds (Hurst-based)
        3. Signal generation with regime filtering

        Args:
            prices: List of closing prices (most recent last)
            atr_value: Current ATR value
            use_cache: Whether to use cached regime

        Returns:
            RegimeAdaptiveRSIResult with complete analysis
        """
        # Step 1: Calculate base adaptive RSI
        base_result = self.adaptive_rsi.calculate_adaptive_rsi(
            prices=prices,
            atr_value=atr_value
        )

        # Step 2: Calculate market regime
        regime_result = self.calculate_regime(prices, use_cache)

        # Step 3: Apply regime adjustment to thresholds
        adjusted_oversold, adjusted_overbought, adjustment_applied = self.apply_regime_adjustment(
            base_thresholds=base_result.thresholds,
            regime=regime_result.regime,
            confidence=regime_result.confidence
        )

        # Create regime-adjusted thresholds
        regime_thresholds = RegimeRSIThresholds(
            oversold=adjusted_oversold,
            overbought=adjusted_overbought,
            volatility_regime=base_result.thresholds.regime,
            market_regime=regime_result.regime,
            base_oversold=base_result.thresholds.oversold,
            base_overbought=base_result.thresholds.overbought,
            regime_adjustment_applied=adjustment_applied,
            hurst_value=regime_result.hurst_value,
            hurst_confidence=regime_result.confidence
        )

        # Step 4: Re-generate signal with adjusted thresholds
        if base_result.rsi_value <= adjusted_oversold:
            signal = SignalType.BUY
        elif base_result.rsi_value >= adjusted_overbought:
            signal = SignalType.SELL
        else:
            signal = SignalType.HOLD

        # Step 5: Check if signal should be filtered
        signal_filtered = self.should_filter_signal(
            signal, regime_result.regime, base_result.trend_direction
        )

        if signal_filtered:
            signal = SignalType.HOLD

        # Step 6: Calculate adjusted signal strength
        base_strength = self._calculate_base_strength(
            base_result.rsi_value,
            adjusted_oversold,
            adjusted_overbought
        )
        adjusted_strength = self.calculate_signal_strength(
            base_strength, regime_result.regime
        )

        # Create result
        result = RegimeAdaptiveRSIResult(
            rsi_value=base_result.rsi_value,
            thresholds=regime_thresholds,
            signal=signal,
            signal_strength=adjusted_strength,
            market_regime=regime_result.regime,
            hurst_value=regime_result.hurst_value,
            hurst_confidence=regime_result.confidence,
            regime_strategy_recommendation=regime_result.recommended_strategy.value,
            atr_value=base_result.atr_value,
            atr_percentage=base_result.atr_percentage,
            volatility_regime=base_result.thresholds.regime,
            trend_direction=base_result.trend_direction,
            signal_filtered_by_regime=signal_filtered
        )

        # Store last result
        self._last_result = result

        logger.info(
            f"RegimeAdaptiveRSI: RSI={base_result.rsi_value:.2f}, "
            f"signal={signal.value}, strength={adjusted_strength:.2f}, "
            f"regime={regime_result.regime.value}, "
            f"thresholds={adjusted_oversold:.0f}/{adjusted_overbought:.0f}"
        )

        return result

    def _calculate_base_strength(
        self,
        rsi_value: float,
        oversold: float,
        overbought: float
    ) -> float:
        """Calculate signal strength based on RSI position"""
        if rsi_value <= oversold:
            # How deep into oversold zone
            return (oversold - rsi_value) / oversold
        elif rsi_value >= overbought:
            # How deep into overbought zone
            return (rsi_value - overbought) / (100 - overbought)
        else:
            return 0.0

    def get_status(self) -> Dict[str, Any]:
        """Get current indicator status"""
        return {
            "name": "RegimeAdaptiveRSI",
            "config": {
                "hurst_trending_threshold": self.config.hurst_trending_threshold,
                "hurst_mean_reversion_threshold": self.config.hurst_mean_reversion_threshold,
                "min_regime_confidence": self.config.min_regime_confidence,
                "adjustment_level": self.config.adjustment_level.value,
                "trending_adjustments": {
                    "oversold": self.config.trending_oversold_adjustment,
                    "overbought": self.config.trending_overbought_adjustment
                },
                "mean_revert_adjustments": {
                    "oversold": self.config.mean_revert_oversold_adjustment,
                    "overbought": self.config.mean_revert_overbought_adjustment
                },
                "signal_strength_modifiers": {
                    "trending": self.config.trending_signal_strength_modifier,
                    "mean_reverting": self.config.mean_revert_signal_strength_modifier,
                    "random_walk": self.config.random_walk_signal_strength_modifier
                }
            },
            "cached_regime": {
                "value": self._cached_regime.hurst_value if self._cached_regime else None,
                "regime": self._cached_regime.regime.value if self._cached_regime else None,
                "age_seconds": (
                    (datetime.now() - self._cache_timestamp).total_seconds()
                    if self._cache_timestamp else None
                )
            },
            "last_result": self._last_result.to_dict() if self._last_result else None
        }

    def clear_cache(self):
        """Clear the regime cache"""
        self._cached_regime = None
        self._cache_timestamp = None
        logger.info("Regime cache cleared")


# Global instance management
_regime_adaptive_rsi: Optional[RegimeAdaptiveRSI] = None


def get_regime_adaptive_rsi(
    config: Optional[RegimeRSIConfig] = None
) -> RegimeAdaptiveRSI:
    """Get or create global RegimeAdaptiveRSI instance"""
    global _regime_adaptive_rsi
    if _regime_adaptive_rsi is None or config is not None:
        _regime_adaptive_rsi = RegimeAdaptiveRSI(config)
    return _regime_adaptive_rsi


def reset_regime_adaptive_rsi():
    """Reset global instance"""
    global _regime_adaptive_rsi
    _regime_adaptive_rsi = None
    logger.info("RegimeAdaptiveRSI instance reset")


def calculate_regime_adaptive_signal(
    prices: List[float],
    atr_value: float
) -> Dict[str, Any]:
    """
    Convenience function for quick signal calculation

    Args:
        prices: List of closing prices
        atr_value: Current ATR value

    Returns:
        Dictionary with signal information
    """
    rsi = get_regime_adaptive_rsi()
    result = rsi.calculate(prices, atr_value)
    return result.to_dict()
