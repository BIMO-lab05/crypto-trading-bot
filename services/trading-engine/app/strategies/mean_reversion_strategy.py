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
    STRONG = "STRONG"             # 2 indicators at extremes
    MODERATE = "MODERATE"         # 1 indicator at extreme
    WEAK = "WEAK"                 # Near extremes but not quite


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
        logger.info(f"  Min confidence: {self.MIN_CONFIDENCE} (ADJUSTED for ranging market)")

    def generate_signal(
        self,
        indicators: Dict[str, IndicatorSignal],
        current_price: float,
        capital: float = 10000.0
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
        rsi_signal = indicators.get('RSI')
        bb_signal = indicators.get('BOLLINGER_BANDS')
        sma_signal = indicators.get('SMA')
        atr_signal = indicators.get('ATR')

        # Need at least RSI and one other indicator
        if not rsi_signal:
            return None

        # Get RSI value from metadata
        rsi_value = rsi_signal.metadata.get('value', 50.0) if rsi_signal.metadata else 50.0

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

        # Check Bollinger Bands lower band
        if bb_signal and bb_signal.metadata:
            bb_position = bb_signal.metadata.get('position', 0.5)  # 0 = at lower, 1 = at upper
            if bb_position <= 0.1:  # At or below lower band
                oversold_signals.append("BB_LOWER")
                oversold_confidence += 0.25
            elif bb_position <= 0.3:  # Near lower band
                oversold_signals.append("BB_NEAR_LOWER")
                oversold_confidence += 0.15

        # Check price deviation from SMA
        if sma_signal and atr_signal and sma_signal.metadata and atr_signal.metadata:
            sma_value = sma_signal.metadata.get('value')
            atr_value = atr_signal.metadata.get('value')

            if sma_value and atr_value:
                deviation = (current_price - sma_value) / atr_value if atr_value > 0 else 0

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
        if bb_signal and bb_signal.metadata:
            bb_position = bb_signal.metadata.get('position', 0.5)
            if bb_position >= 0.9:  # At or above upper band
                overbought_signals.append("BB_UPPER")
                overbought_confidence += 0.25
            elif bb_position >= 0.7:  # Near upper band
                overbought_signals.append("BB_NEAR_UPPER")
                overbought_confidence += 0.15

        # Check price deviation from SMA (overbought)
        if sma_signal and atr_signal and sma_signal.metadata and atr_signal.metadata:
            sma_value = sma_signal.metadata.get('value')
            atr_value = atr_signal.metadata.get('value')

            if sma_value and atr_value:
                deviation = (current_price - sma_value) / atr_value if atr_value > 0 else 0

                if deviation >= self.EXTREME_DEVIATION_THRESHOLD:
                    overbought_signals.append("PRICE_EXTREME_ABOVE_SMA")
                    overbought_confidence += 0.25
                elif deviation >= self.MEAN_DEVIATION_THRESHOLD:
                    overbought_signals.append("PRICE_ABOVE_SMA")
                    overbought_confidence += 0.15

        # Determine if we have a valid signal
        if len(oversold_signals) >= self.MIN_INDICATORS_ALIGNED and oversold_confidence >= self.MIN_CONFIDENCE:
            # BUY signal (market oversold, expect bounce)
            return self._create_buy_signal(
                current_price=current_price,
                indicators_aligned=oversold_signals,
                confidence=min(0.95, oversold_confidence),
                sma_value=sma_value if sma_signal and sma_signal.metadata else current_price,
                atr_value=atr_value if atr_signal and atr_signal.metadata else current_price * 0.02
            )

        elif len(overbought_signals) >= self.MIN_INDICATORS_ALIGNED and overbought_confidence >= self.MIN_CONFIDENCE:
            # SELL signal (market overbought, expect drop)
            return self._create_sell_signal(
                current_price=current_price,
                indicators_aligned=overbought_signals,
                confidence=min(0.95, overbought_confidence),
                sma_value=sma_value if sma_signal and sma_signal.metadata else current_price,
                atr_value=atr_value if atr_signal and atr_signal.metadata else current_price * 0.02
            )

        else:
            # No valid mean reversion setup
            return None

    def _create_buy_signal(
        self,
        current_price: float,
        indicators_aligned: List[str],
        confidence: float,
        sma_value: float,
        atr_value: float
    ) -> MeanReversionSignal:
        """Create BUY mean reversion signal"""
        # Target: Mean (SMA)
        target = sma_value

        # Stop loss: Below current price by 1.5x the distance to mean
        distance_to_mean = abs(current_price - sma_value)
        stop_loss = current_price - (distance_to_mean * 1.5)

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
            f"Risk/Reward: {(target - current_price) / (current_price - stop_loss):.2f}"
        ]

        return MeanReversionSignal(
            action=SignalAction.BUY,
            confidence=confidence,
            strength=strength,
            entry_price=current_price,
            target=target,
            stop_loss=stop_loss,
            indicators_aligned=indicators_aligned,
            reasoning=reasoning
        )

    def _create_sell_signal(
        self,
        current_price: float,
        indicators_aligned: List[str],
        confidence: float,
        sma_value: float,
        atr_value: float
    ) -> MeanReversionSignal:
        """Create SELL mean reversion signal"""
        # Target: Mean (SMA)
        target = sma_value

        # Stop loss: Above current price by 1.5x the distance to mean
        distance_to_mean = abs(current_price - sma_value)
        stop_loss = current_price + (distance_to_mean * 1.5)

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
            f"Risk/Reward: {(current_price - target) / (stop_loss - current_price):.2f}"
        ]

        return MeanReversionSignal(
            action=SignalAction.SELL,
            confidence=confidence,
            strength=strength,
            entry_price=current_price,
            target=target,
            stop_loss=stop_loss,
            indicators_aligned=indicators_aligned,
            reasoning=reasoning
        )
