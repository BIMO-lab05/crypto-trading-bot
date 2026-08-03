"""
Mean Reversion Strategy for Ranging Markets
Created: 2026-01-03
Purpose: Trade mean reversion opportunities when market is sideways/ranging

Strategy Logic:
- Detects ranging markets using ADX (ADX < 25)
- Buys oversold conditions (expecting bounce back to mean)
- Sells overbought conditions (expecting drop back to mean)
- Uses Bollinger Bands, RSI, and price deviation from SMA

Research Foundation:
- Mean reversion works best in ranging markets (Bollinger, 1992)
- RSI extremes signal reversal points (Wilder, 1978)
- 2-3 standard deviations provide high probability setups
"""

import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

from app.models import SignalAction, IndicatorSignal

logger = logging.getLogger(__name__)


class MeanReversionSignalStrength(Enum):
    """Strength of mean reversion signal"""

    VERY_STRONG = "VERY_STRONG"  # Multiple indicators at extremes
    STRONG = "STRONG"  # 2 indicators at extremes
    MODERATE = "MODERATE"  # 1 indicator at extreme
    WEAK = "WEAK"  # Near extremes but not quite


@dataclass
class MeanReversionSignal:
    """Mean reversion trading signal"""

    action: SignalAction
    confidence: float
    strength: MeanReversionSignalStrength
    entry_price: float
    target: float  # Mean to revert to
    stop_loss: float
    indicators_aligned: List[str]  # Which indicators triggered
    reasoning: List[str]


class MeanReversionStrategy:
    """
    Mean Reversion Strategy

    Triggers:
    - BUY when price is oversold (expecting bounce up)
    - SELL when price is overbought (expecting drop down)

    Indicators Used:
    - Bollinger Bands: Price at lower/upper band
    - RSI: Below 30 (oversold) or above 70 (overbought)
    - Price vs SMA: Significant deviation from mean

    Entry Rules:
    - BUY: RSI < 30 OR price < BB lower OR price < SMA - 2*ATR
    - SELL: RSI > 70 OR price > BB upper OR price > SMA + 2*ATR
    - Require at least 2 indicators agreeing for confidence

    Exit Rules:
    - Target: Mean (SMA or BB middle)
    - Stop: Beyond extreme (1.5x distance from mean)
    """

    def __init__(self):
        """Initialize mean reversion strategy"""
        # RSI thresholds
        self.RSI_OVERSOLD = 30.0
        self.RSI_OVERBOUGHT = 70.0
        self.RSI_EXTREME_OVERSOLD = 20.0  # Very strong signal
        self.RSI_EXTREME_OVERBOUGHT = 80.0

        # Bollinger Band settings (already 2.5 std dev)
        # Lower band = mean - 2.5*std, Upper band = mean + 2.5*std

        # Price deviation from SMA (in terms of ATR)
        self.MEAN_DEVIATION_THRESHOLD = 2.0  # 2x ATR from SMA
        self.EXTREME_DEVIATION_THRESHOLD = 3.0  # 3x ATR (very strong)

        # Confidence levels - ADJUSTED 2026-02-24 for ranging market
        self.MIN_CONFIDENCE = 0.30  # LOWERED from 0.60 to 0.30 to enable trading
        self.MIN_INDICATORS_ALIGNED = 2  # Need at least 2 signals

        logger.info("MeanReversionStrategy initialized")
        logger.info(f"  RSI thresholds: {self.RSI_OVERSOLD}/{self.RSI_OVERBOUGHT}")
        logger.info(f"  Deviation threshold: {self.MEAN_DEVIATION_THRESHOLD} ATR")
        logger.info(
            f"  Min confidence: {self.MIN_CONFIDENCE} (ADJUSTED for ranging market)"
        )

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 10000.0,
    ) -> Optional[MeanReversionSignal]:
        """
        Generate mean reversion signal

        Args:
            indicators: Dict of indicator signals
            current_price: Current market price
            capital: Available capital

        Returns:
            MeanReversionSignal or None if no setup
        """
        # Extract indicator values
        rsi_signal = indicators.get("RSI")
        bb_signal = indicators.get("BOLLINGER_BANDS")
        sma_signal = indicators.get("SMA")
        atr_signal = indicators.get("ATR")

        # Need at least RSI and one other indicator
        if not rsi_signal:
            return None

        # RSI reading lives on .value. This used to read metadata['value'] and
        # fall back to 50.0 — a perfectly neutral RSI — so a payload the leg
        # could not actually read scored as a calm market instead of surfacing.
        # Audit 2026-07-30 F-1: fail closed rather than fabricate an input.
        rsi_value = rsi_signal.numeric_value()
        if rsi_value is None:
            return None

        bb_position = self._bollinger_position(bb_signal, current_price)
        sma_value = sma_signal.numeric_value() if sma_signal else None
        atr_value = atr_signal.numeric_value() if atr_signal else None

        # Count oversold signals (BUY opportunities)
        oversold_signals = []
        oversold_confidence = 0.0

        # Check RSI oversold
        if rsi_value <= self.RSI_EXTREME_OVERSOLD:
            oversold_signals.append("RSI_EXTREME")
            oversold_confidence += 0.30
        elif rsi_value <= self.RSI_OVERSOLD:
            oversold_signals.append("RSI_OVERSOLD")
            oversold_confidence += 0.20

        # Check Bollinger Bands lower band (0 = at lower, 1 = at upper).
        # None means no bands were published — skip the check rather than score
        # a fabricated mid-band 0.5.
        if bb_position is not None:
            if bb_position <= 0.1:  # At or below lower band
                oversold_signals.append("BB_LOWER")
                oversold_confidence += 0.25
            elif bb_position <= 0.3:  # Near lower band
                oversold_signals.append("BB_NEAR_LOWER")
                oversold_confidence += 0.15

        # Check price deviation from SMA
        if sma_value and atr_value and atr_value > 0:
            deviation = (current_price - sma_value) / atr_value

            if deviation <= -self.EXTREME_DEVIATION_THRESHOLD:
                oversold_signals.append("PRICE_EXTREME_BELOW_SMA")
                oversold_confidence += 0.25
            elif deviation <= -self.MEAN_DEVIATION_THRESHOLD:
                oversold_signals.append("PRICE_BELOW_SMA")
                oversold_confidence += 0.15

        # Count overbought signals (SELL opportunities)
        overbought_signals = []
        overbought_confidence = 0.0

        # Check RSI overbought
        if rsi_value >= self.RSI_EXTREME_OVERBOUGHT:
            overbought_signals.append("RSI_EXTREME")
            overbought_confidence += 0.30
        elif rsi_value >= self.RSI_OVERBOUGHT:
            overbought_signals.append("RSI_OVERBOUGHT")
            overbought_confidence += 0.20

        # Check Bollinger Bands upper band
        if bb_position is not None:
            if bb_position >= 0.9:  # At or above upper band
                overbought_signals.append("BB_UPPER")
                overbought_confidence += 0.25
            elif bb_position >= 0.7:  # Near upper band
                overbought_signals.append("BB_NEAR_UPPER")
                overbought_confidence += 0.15

        # Check price deviation from SMA (overbought)
        if sma_value and atr_value and atr_value > 0:
            deviation = (current_price - sma_value) / atr_value

            if deviation >= self.EXTREME_DEVIATION_THRESHOLD:
                overbought_signals.append("PRICE_EXTREME_ABOVE_SMA")
                overbought_confidence += 0.25
            elif deviation >= self.MEAN_DEVIATION_THRESHOLD:
                overbought_signals.append("PRICE_ABOVE_SMA")
                overbought_confidence += 0.15

        # Stop/target anchors. These previously read sma_value / atr_value, which
        # were only bound inside the deviation branch above — an UnboundLocalError
        # waiting for the first fire that skipped it. Resolve them once, here.
        #
        # The mean is the whole point of a mean-reversion trade: it is the target,
        # and the stop is placed relative to the distance to it. Anchoring it to
        # current_price (the old fallback) collapses that distance to zero, giving
        # a target equal to entry and a degenerate stop. Prefer the Bollinger
        # middle band when SMA is absent — it is an SMA — and refuse to signal
        # when neither is available.
        anchor_sma = sma_value or self._bollinger_middle(bb_signal)
        if not anchor_sma or anchor_sma == current_price:
            return None
        anchor_atr = atr_value if atr_value else current_price * 0.02

        # Determine if we have a valid signal
        if (
            len(oversold_signals) >= self.MIN_INDICATORS_ALIGNED
            and oversold_confidence >= self.MIN_CONFIDENCE
        ):
            # BUY signal (market oversold, expect bounce)
            return self._create_buy_signal(
                current_price=current_price,
                indicators_aligned=oversold_signals,
                confidence=min(0.95, oversold_confidence),
                sma_value=anchor_sma,
                atr_value=anchor_atr,
            )

        elif (
            len(overbought_signals) >= self.MIN_INDICATORS_ALIGNED
            and overbought_confidence >= self.MIN_CONFIDENCE
        ):
            # SELL signal (market overbought, expect drop)
            return self._create_sell_signal(
                current_price=current_price,
                indicators_aligned=overbought_signals,
                confidence=min(0.95, overbought_confidence),
                sma_value=anchor_sma,
                atr_value=anchor_atr,
            )

        else:
            # No valid mean reversion setup
            return None

    @staticmethod
    def _bollinger_middle(bb_signal: Optional[IndicatorSignal]) -> Optional[float]:
        """The Bollinger middle band — an SMA, usable as the reversion target when
        the SMA indicator itself is unavailable."""
        if not bb_signal:
            return None
        middle = (bb_signal.metadata or {}).get("middle_band")
        return None if middle is None else float(middle)

    @staticmethod
    def _bollinger_position(
        bb_signal: Optional[IndicatorSignal], current_price: float
    ) -> Optional[float]:
        """Where price sits across the Bollinger channel: 0 = lower band, 1 = upper.

        The aggregator publishes `upper_band` / `middle_band` / `lower_band` and
        no `position` key, so the previous `metadata.get('position', 0.5)` always
        returned a fabricated mid-band reading (audit 2026-07-30 F-1). Honour an
        explicit `position` if some producer supplies one, else derive it.

        Returns None when the channel cannot be determined — callers must skip
        the Bollinger checks rather than assume a neutral position. Values
        outside [0, 1] are returned as-is: price beyond a band is meaningful.
        """
        if not bb_signal:
            return None
        metadata = bb_signal.metadata or {}

        explicit = metadata.get("position")
        if explicit is not None:
            return float(explicit)

        upper = metadata.get("upper_band")
        lower = metadata.get("lower_band")
        if upper is None or lower is None:
            return None

        span = float(upper) - float(lower)
        if span <= 0:
            return None

        return (current_price - float(lower)) / span

    def _create_buy_signal(
        self,
        current_price: float,
        indicators_aligned: List[str],
        confidence: float,
        sma_value: float,
        atr_value: float,
    ) -> MeanReversionSignal:
        """Create BUY mean reversion signal"""
        # Target: Mean (SMA)
        target = sma_value

        # Stop loss: below current price by 0.75x the distance to mean.
        # FIX 2026-07-28: was 1.5x — risking 1.5R to make 1.0R (inverted
        # risk/reward, negative expectancy below ~60% win rate before fees).
        # At 0.75x the trade risks 0.75R for a 1.0R reward (R/R ~1.33).
        distance_to_mean = abs(current_price - sma_value)
        stop_loss = current_price - (distance_to_mean * 0.75)

        # Determine strength
        if len(indicators_aligned) >= 3 or "EXTREME" in str(indicators_aligned):
            strength = MeanReversionSignalStrength.VERY_STRONG
        elif len(indicators_aligned) >= 2:
            strength = MeanReversionSignalStrength.STRONG
        else:
            strength = MeanReversionSignalStrength.MODERATE

        reasoning = [
            f"Mean reversion BUY: {len(indicators_aligned)} oversold signals",
            f"Indicators: {', '.join(indicators_aligned)}",
            f"Expected reversion to mean: ${target:.2f}",
            f"Risk/Reward: {(target - current_price) / (current_price - stop_loss):.2f}",
        ]

        return MeanReversionSignal(
            action=SignalAction.BUY,
            confidence=confidence,
            strength=strength,
            entry_price=current_price,
            target=target,
            stop_loss=stop_loss,
            indicators_aligned=indicators_aligned,
            reasoning=reasoning,
        )

    def _create_sell_signal(
        self,
        current_price: float,
        indicators_aligned: List[str],
        confidence: float,
        sma_value: float,
        atr_value: float,
    ) -> MeanReversionSignal:
        """Create SELL mean reversion signal"""
        # Target: Mean (SMA)
        target = sma_value

        # Stop loss: above current price by 0.75x the distance to mean.
        # FIX 2026-07-28: was 1.5x — risking 1.5R to make 1.0R (inverted
        # risk/reward, negative expectancy below ~60% win rate before fees).
        # At 0.75x the trade risks 0.75R for a 1.0R reward (R/R ~1.33).
        distance_to_mean = abs(current_price - sma_value)
        stop_loss = current_price + (distance_to_mean * 0.75)

        # Determine strength
        if len(indicators_aligned) >= 3 or "EXTREME" in str(indicators_aligned):
            strength = MeanReversionSignalStrength.VERY_STRONG
        elif len(indicators_aligned) >= 2:
            strength = MeanReversionSignalStrength.STRONG
        else:
            strength = MeanReversionSignalStrength.MODERATE

        reasoning = [
            f"Mean reversion SELL: {len(indicators_aligned)} overbought signals",
            f"Indicators: {', '.join(indicators_aligned)}",
            f"Expected reversion to mean: ${target:.2f}",
            f"Risk/Reward: {(current_price - target) / (stop_loss - current_price):.2f}",
        ]

        return MeanReversionSignal(
            action=SignalAction.SELL,
            confidence=confidence,
            strength=strength,
            entry_price=current_price,
            target=target,
            stop_loss=stop_loss,
            indicators_aligned=indicators_aligned,
            reasoning=reasoning,
        )
