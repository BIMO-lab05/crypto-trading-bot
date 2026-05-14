"""
Hybrid Strategy Router
Created: 2026-01-03
Purpose: Route between trend-following and mean reversion based on market regime

Logic:
- Detects market regime using ADX indicator
- Routes to appropriate strategy:
  * ADX >= 25: TRENDING → Use trend-following strategy
  * ADX < 25: RANGING → Use mean reversion strategy
- Combines best of both worlds for all market conditions
"""

import logging
from typing import Dict, Optional
from enum import Enum

from app.models import IndicatorSignal
from app.strategies.research_optimized_strategy import (
    ResearchOptimizedStrategy,
    TradeSetup,
)
from app.strategies.mean_reversion_strategy import (
    MeanReversionStrategy,
    MeanReversionSignal,
)

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification"""

    TRENDING = "TRENDING"  # ADX >= 25
    RANGING = "RANGING"  # ADX < 25
    UNKNOWN = "UNKNOWN"  # Cannot determine


class HybridStrategyRouter:
    """
    Hybrid strategy that switches between trend-following and mean reversion

    Features:
    - Automatic regime detection using ADX
    - Trend-following for trending markets (ADX >= 25)
    - Mean reversion for ranging markets (ADX < 25)
    - Seamless switching based on conditions
    """

    def __init__(self):
        """Initialize hybrid strategy router"""
        self.trend_strategy = ResearchOptimizedStrategy()
        self.mean_reversion_strategy = MeanReversionStrategy()

        # ADX threshold for regime classification
        self.ADX_TRENDING_THRESHOLD = 25.0

        # Statistics
        self.total_signals = 0
        self.trend_signals = 0
        self.mean_reversion_signals = 0

        logger.info("HybridStrategyRouter initialized")
        logger.info(f"  ADX threshold: {self.ADX_TRENDING_THRESHOLD}")
        logger.info("  Trend strategy: ResearchOptimizedStrategy")
        logger.info("  Mean reversion strategy: MeanReversionStrategy")

    def detect_regime(self, indicators: Dict[str, IndicatorSignal]) -> MarketRegime:
        """
        Detect current market regime using ADX

        Args:
            indicators: Dict of indicator signals

        Returns:
            MarketRegime (TRENDING, RANGING, or UNKNOWN)
        """
        # Primary path (2026-05-06): read the ADX leg the aggregator now
        # supplies. ADX is its own indicator, NOT nested in ATR.metadata.
        # Old code looked at atr_signal.metadata['adx'] which never existed,
        # so the router silently defaulted to RANGING every cycle regardless
        # of regime — a load-bearing bug for trend-following profitability.
        adx_signal = indicators.get("ADX")
        adx_value = None
        if adx_signal is not None:
            # Prefer the value field (ADX numeric), fall back to metadata.
            adx_value = getattr(adx_signal, "value", None)
            if adx_value is None and getattr(adx_signal, "metadata", None):
                adx_value = adx_signal.metadata.get("adx")
        # Legacy fallback only if the primary lookup truly missed.
        if adx_value is None:
            atr_signal = indicators.get("ATR")
            if atr_signal and getattr(atr_signal, "metadata", None):
                adx_value = atr_signal.metadata.get("adx")

        if adx_value is not None:
            try:
                adx_value = float(adx_value)
            except (TypeError, ValueError):
                adx_value = None

        if adx_value is not None:
            if adx_value >= self.ADX_TRENDING_THRESHOLD:
                logger.info(
                    f"[HYBRID] ADX={adx_value:.2f} >= "
                    f"{self.ADX_TRENDING_THRESHOLD} → TRENDING"
                )
                return MarketRegime.TRENDING
            logger.info(
                f"[HYBRID] ADX={adx_value:.2f} < "
                f"{self.ADX_TRENDING_THRESHOLD} → RANGING"
            )
            return MarketRegime.RANGING

        # Fallback only when ADX is genuinely unavailable (e.g. TA service
        # transient down). Treat conf > 0.5 instead of 0.7 so the fallback
        # has a non-zero chance of firing — old 0.7 floor never triggered
        # with current aggregator confidence regime (~0.16-0.30).
        trend_indicators = ["EMA", "SMA", "ICHIMOKU", "TREND_FILTER"]
        strong_trend_count = sum(
            1
            for name in trend_indicators
            if (sig := indicators.get(name)) and sig.confidence > 0.5
        )
        if strong_trend_count >= 2:
            logger.warning(
                f"[HYBRID] ADX unavailable; fallback says TRENDING "
                f"({strong_trend_count}/{len(trend_indicators)} legs strong)"
            )
            return MarketRegime.TRENDING
        logger.warning(
            f"[HYBRID] ADX unavailable; fallback says RANGING "
            f"({strong_trend_count}/{len(trend_indicators)} legs strong)"
        )
        return MarketRegime.RANGING

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 10000.0,
    ) -> Optional[TradeSetup]:
        """
        Generate trading signal using appropriate strategy

        Args:
            indicators: Dict of indicator signals
            current_price: Current market price
            capital: Available capital

        Returns:
            TradeSetup or None
        """
        self.total_signals += 1

        # Detect market regime
        regime = self.detect_regime(indicators)

        logger.info(f"[HYBRID] Market regime: {regime.value}")

        # Route to appropriate strategy
        if regime == MarketRegime.TRENDING:
            # Use trend-following strategy
            logger.info("[HYBRID] Using TREND-FOLLOWING strategy")
            self.trend_signals += 1

            signal = self.trend_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

            if signal:
                # Add regime info to reasoning
                signal.reasoning.insert(
                    0, "Market regime: TRENDING (using trend-following)"
                )

            return signal

        elif regime == MarketRegime.RANGING:
            # Use mean reversion strategy
            logger.info("[HYBRID] Using MEAN REVERSION strategy")
            self.mean_reversion_signals += 1

            mr_signal = self.mean_reversion_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

            if mr_signal:
                # Convert MeanReversionSignal to TradeSetup format
                return self._convert_mean_reversion_to_trade_setup(
                    mr_signal=mr_signal, current_price=current_price, capital=capital
                )
            else:
                return None

        else:
            # Unknown regime - default to trend-following (safer)
            logger.warning("[HYBRID] Unknown regime, defaulting to trend-following")
            return self.trend_strategy.generate_signal(
                indicators=indicators, current_price=current_price, capital=capital
            )

    def _convert_mean_reversion_to_trade_setup(
        self, mr_signal: MeanReversionSignal, current_price: float, capital: float
    ) -> TradeSetup:
        """Convert MeanReversionSignal to TradeSetup format"""
        from app.strategies.research_optimized_strategy import (
            SignalStrength,
            MarketCondition,
        )

        # Map mean reversion strength to signal strength
        strength_mapping = {
            "VERY_STRONG": SignalStrength.VERY_STRONG,
            "STRONG": SignalStrength.STRONG,
            "MODERATE": SignalStrength.MODERATE,
            "WEAK": SignalStrength.WEAK,
        }

        signal_strength = strength_mapping.get(
            mr_signal.strength.value, SignalStrength.MODERATE
        )

        # Calculate position size (10-20% of capital based on confidence)
        position_size_pct = 0.10 + (mr_signal.confidence * 0.10)  # 10-20%
        position_value = capital * position_size_pct
        quantity = position_value / current_price

        # Create TradeSetup
        return TradeSetup(
            action=mr_signal.action,
            confidence=mr_signal.confidence,
            signal_strength=signal_strength,
            entry_price=mr_signal.entry_price,
            stop_loss=mr_signal.stop_loss,
            take_profit=mr_signal.target,  # Mean is the target
            position_size_pct=position_size_pct,
            quantity=quantity,
            indicators_aligned=len(mr_signal.indicators_aligned),
            market_condition=MarketCondition.RANGING,  # Explicitly ranging
            reasoning=mr_signal.reasoning,
            metadata={
                "strategy_type": "mean_reversion",
                "indicators_triggered": mr_signal.indicators_aligned,
                "target_mean": mr_signal.target,
            },
        )

    def get_stats(self) -> Dict[str, any]:
        """Get strategy usage statistics"""
        if self.total_signals == 0:
            return {
                "total_signals": 0,
                "trend_signals": 0,
                "mean_reversion_signals": 0,
                "trend_pct": 0.0,
                "mean_reversion_pct": 0.0,
            }

        return {
            "total_signals": self.total_signals,
            "trend_signals": self.trend_signals,
            "mean_reversion_signals": self.mean_reversion_signals,
            "trend_pct": (self.trend_signals / self.total_signals) * 100,
            "mean_reversion_pct": (self.mean_reversion_signals / self.total_signals)
            * 100,
        }
