"""
Volume Profile Trading Strategy
Purpose: Integrate VP signals with multi-timeframe analysis for automated trading
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from app.volume_profile import VolumeProfile, get_vp_calculator
from app.models import SignalAction

logger = logging.getLogger(__name__)


class VPStrategyType(str, Enum):
    """Volume Profile strategy types"""
    MEAN_REVERSION_LONG = "MEAN_REVERSION_LONG"
    MEAN_REVERSION_SHORT = "MEAN_REVERSION_SHORT"
    POC_BREAKOUT_LONG = "POC_BREAKOUT_LONG"
    POC_BREAKOUT_SHORT = "POC_BREAKOUT_SHORT"
    VAH_REJECTION_LONG = "VAH_REJECTION_LONG"
    VAL_REJECTION_SHORT = "VAL_REJECTION_SHORT"
    VALUE_AREA_TRADE = "VALUE_AREA_TRADE"
    NO_STRATEGY = "NO_STRATEGY"


@dataclass
class VPSignal:
    """Volume Profile trading signal"""
    symbol: str
    timestamp: datetime
    current_price: Decimal

    # VP data
    vp_profile: VolumeProfile
    price_position: str  # ABOVE_VAH, IN_VALUE_AREA, AT_POC, BELOW_VAL

    # Strategy
    strategy_type: VPStrategyType
    action: SignalAction  # BUY, SELL, HOLD
    confidence: float  # 0.0 to 1.0

    # VP-specific levels
    entry_price: Decimal
    stop_loss: Decimal
    take_profit_levels: Dict[str, Decimal]

    # Volume context
    volume_support: bool  # True if volume supports direction
    volume_bias: str  # "BULLISH", "BEARISH", "NEUTRAL"

    # Reasoning
    reasoning: str


class VPStrategyAnalyzer:
    """
    Analyze Volume Profile and determine trading strategies

    Integrates with multi-timeframe confirmation system
    """

    def __init__(
        self,
        min_vp_confidence: float = 0.6,
        poc_proximity_pct: float = 0.002,  # 0.2% from POC = "at POC"
        vp_lookback_candles: int = 100
    ):
        """
        Initialize VP strategy analyzer

        Args:
            min_vp_confidence: Minimum confidence for VP signals
            poc_proximity_pct: % distance from POC to consider "at POC"
            vp_lookback_candles: Number of candles for VP calculation
        """
        self.min_vp_confidence = min_vp_confidence
        self.poc_proximity_pct = poc_proximity_pct
        self.vp_lookback_candles = vp_lookback_candles
        self.vp_calculator = get_vp_calculator()

        logger.info(
            f"VPStrategyAnalyzer initialized "
            f"(min_conf={min_vp_confidence}, poc_prox={poc_proximity_pct})"
        )

    def analyze_vp_signal(
        self,
        symbol: str,
        current_price: Decimal,
        vp_profile: VolumeProfile,
        mtf_signal: Optional[Dict] = None
    ) -> VPSignal:
        """
        Analyze volume profile and generate trading signal

        Args:
            symbol: Trading symbol
            current_price: Current price
            vp_profile: Volume profile data
            mtf_signal: Multi-timeframe signal from Phase 2 (optional)

        Returns:
            VPSignal with strategy recommendation
        """
        # Get price position relative to value area
        price_position = vp_profile.get_price_position(current_price)

        # Get volume context at current price
        volume_level = vp_profile.get_volume_at_price(current_price)
        volume_support, volume_bias = self._analyze_volume_support(volume_level)

        # Determine strategy based on price position and MTF signal
        strategy_type, action, confidence, reasoning = self._determine_strategy(
            current_price=current_price,
            vp_profile=vp_profile,
            price_position=price_position,
            volume_support=volume_support,
            volume_bias=volume_bias,
            mtf_signal=mtf_signal
        )

        # Calculate entry/exit levels
        entry_price = current_price
        stop_loss = self._calculate_stop_loss(
            current_price, vp_profile, strategy_type
        )
        take_profit_levels = self._calculate_take_profit(
            current_price, vp_profile, strategy_type
        )

        return VPSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            current_price=current_price,
            vp_profile=vp_profile,
            price_position=price_position,
            strategy_type=strategy_type,
            action=action,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_levels=take_profit_levels,
            volume_support=volume_support,
            volume_bias=volume_bias,
            reasoning=reasoning
        )

    def _determine_strategy(
        self,
        current_price: Decimal,
        vp_profile: VolumeProfile,
        price_position: str,
        volume_support: bool,
        volume_bias: str,
        mtf_signal: Optional[Dict]
    ) -> Tuple[VPStrategyType, SignalAction, float, str]:
        """
        Determine trading strategy based on VP and MTF analysis

        Returns:
            (strategy_type, action, confidence, reasoning)
        """
        # Extract MTF data if available
        mtf_action = SignalAction.HOLD
        mtf_alignment = "NONE"
        mtf_confidence = 0.0

        if mtf_signal:
            mtf_action = mtf_signal.get('action', SignalAction.HOLD)
            mtf_data = mtf_signal.get('metadata', {}).get('multi_timeframe', {})
            mtf_alignment = mtf_data.get('alignment_strength', 'NONE')
            mtf_confidence = mtf_signal.get('confidence', 0.0)

        # Base confidence on MTF if available, otherwise start at 50%
        base_confidence = mtf_confidence if mtf_signal else 0.5

        # Strategy 1: Mean Reversion at VAL (LONG)
        if price_position == "BELOW_VAL":
            if mtf_action == SignalAction.BUY or mtf_action == SignalAction.HOLD:
                # Price below value area + bullish MTF = mean reversion long
                strategy = VPStrategyType.MEAN_REVERSION_LONG
                action = SignalAction.BUY

                # Boost confidence if volume supports
                confidence_mod = 1.15 if volume_support and volume_bias == "BULLISH" else 1.0

                # Additional boost for strong MTF alignment
                if mtf_alignment in ["STRONG", "VERY_STRONG"]:
                    confidence_mod *= 1.1

                confidence = min(base_confidence * confidence_mod, 1.0)
                reasoning = (
                    f"Mean reversion LONG: Price below VAL ({vp_profile.val:.2f}), "
                    f"MTF={mtf_action.value} ({mtf_alignment}), "
                    f"Volume {volume_bias}"
                )
                return strategy, action, confidence, reasoning

        # Strategy 2: Mean Reversion at VAH (SHORT)
        elif price_position == "ABOVE_VAH":
            if mtf_action == SignalAction.SELL or mtf_action == SignalAction.HOLD:
                strategy = VPStrategyType.MEAN_REVERSION_SHORT
                action = SignalAction.SELL

                confidence_mod = 1.15 if volume_support and volume_bias == "BEARISH" else 1.0
                if mtf_alignment in ["STRONG", "VERY_STRONG"]:
                    confidence_mod *= 1.1

                confidence = min(base_confidence * confidence_mod, 1.0)
                reasoning = (
                    f"Mean reversion SHORT: Price above VAH ({vp_profile.vah:.2f}), "
                    f"MTF={mtf_action.value} ({mtf_alignment}), "
                    f"Volume {volume_bias}"
                )
                return strategy, action, confidence, reasoning

        # Strategy 3: POC Breakout (LONG)
        elif price_position in ["IN_VALUE_AREA", "AT_POC"]:
            poc_distance_pct = abs(float(current_price - vp_profile.poc) / float(vp_profile.poc))

            # Check if price just broke above POC with strong MTF
            if current_price > vp_profile.poc and poc_distance_pct < 0.01:  # Within 1% above POC
                if mtf_action == SignalAction.BUY and mtf_alignment in ["STRONG", "VERY_STRONG"]:
                    strategy = VPStrategyType.POC_BREAKOUT_LONG
                    action = SignalAction.BUY

                    # Strong boost for aligned breakout
                    confidence_mod = 1.2 if volume_bias == "BULLISH" else 1.1
                    confidence = min(base_confidence * confidence_mod, 1.0)

                    reasoning = (
                        f"POC breakout LONG: Price above POC ({vp_profile.poc:.2f}), "
                        f"MTF ALIGNED ({mtf_alignment}), "
                        f"Volume {volume_bias}"
                    )
                    return strategy, action, confidence, reasoning

            # POC Breakout (SHORT)
            elif current_price < vp_profile.poc and poc_distance_pct < 0.01:
                if mtf_action == SignalAction.SELL and mtf_alignment in ["STRONG", "VERY_STRONG"]:
                    strategy = VPStrategyType.POC_BREAKOUT_SHORT
                    action = SignalAction.SELL

                    confidence_mod = 1.2 if volume_bias == "BEARISH" else 1.1
                    confidence = min(base_confidence * confidence_mod, 1.0)

                    reasoning = (
                        f"POC breakout SHORT: Price below POC ({vp_profile.poc:.2f}), "
                        f"MTF ALIGNED ({mtf_alignment}), "
                        f"Volume {volume_bias}"
                    )
                    return strategy, action, confidence, reasoning

        # Strategy 4: Value Area Trade (inside value area)
        if price_position == "IN_VALUE_AREA":
            if mtf_action in [SignalAction.BUY, SignalAction.SELL]:
                strategy = VPStrategyType.VALUE_AREA_TRADE
                action = mtf_action

                # Moderate confidence for value area trades
                confidence_mod = 1.05 if volume_support else 1.0
                confidence = min(base_confidence * confidence_mod, 1.0)

                reasoning = (
                    f"Value area trade: Price in VA, MTF={mtf_action.value}, "
                    f"Volume {volume_bias}"
                )
                return strategy, action, confidence, reasoning

        # No clear strategy
        return VPStrategyType.NO_STRATEGY, SignalAction.HOLD, 0.0, "No VP strategy identified"

    def _analyze_volume_support(
        self,
        volume_level: Optional[any]
    ) -> Tuple[bool, str]:
        """
        Analyze if volume supports the price level

        Returns:
            (volume_support: bool, volume_bias: str)
        """
        if not volume_level:
            return False, "NEUTRAL"

        buy_vol = float(volume_level.buy_volume)
        sell_vol = float(volume_level.sell_volume)
        total_vol = buy_vol + sell_vol

        if total_vol == 0:
            return False, "NEUTRAL"

        buy_pct = buy_vol / total_vol
        sell_pct = sell_vol / total_vol

        # Determine bias
        if buy_pct > 0.6:
            volume_bias = "BULLISH"
            volume_support = True
        elif sell_pct > 0.6:
            volume_bias = "BEARISH"
            volume_support = True
        else:
            volume_bias = "NEUTRAL"
            volume_support = False

        return volume_support, volume_bias

    def _calculate_stop_loss(
        self,
        entry_price: Decimal,
        vp_profile: VolumeProfile,
        strategy: VPStrategyType
    ) -> Decimal:
        """Calculate stop loss based on VP levels"""
        if strategy == VPStrategyType.MEAN_REVERSION_LONG:
            # SL below VAL
            return vp_profile.val * Decimal("0.995")

        elif strategy == VPStrategyType.MEAN_REVERSION_SHORT:
            # SL above VAH
            return vp_profile.vah * Decimal("1.005")

        elif strategy == VPStrategyType.POC_BREAKOUT_LONG:
            # SL just below POC
            return vp_profile.poc * Decimal("0.998")

        elif strategy == VPStrategyType.POC_BREAKOUT_SHORT:
            # SL just above POC
            return vp_profile.poc * Decimal("1.002")

        elif strategy == VPStrategyType.VALUE_AREA_TRADE:
            # Use 1.5% SL for value area trades
            return entry_price * Decimal("0.985")

        else:
            # Default 2% SL
            return entry_price * Decimal("0.98")

    def _calculate_take_profit(
        self,
        entry_price: Decimal,
        vp_profile: VolumeProfile,
        strategy: VPStrategyType
    ) -> Dict[str, Decimal]:
        """Calculate multiple TP levels based on VP"""
        if strategy == VPStrategyType.MEAN_REVERSION_LONG:
            return {
                "tp1": vp_profile.poc,  # POC
                "tp2": vp_profile.vah,  # VAH
                "tp3": vp_profile.vah * Decimal("1.01")  # 1% above VAH
            }

        elif strategy == VPStrategyType.MEAN_REVERSION_SHORT:
            return {
                "tp1": vp_profile.poc,
                "tp2": vp_profile.val,
                "tp3": vp_profile.val * Decimal("0.99")
            }

        elif strategy in [VPStrategyType.POC_BREAKOUT_LONG, VPStrategyType.POC_BREAKOUT_SHORT]:
            # Use value area width as ATR estimate
            va_width = vp_profile.vah - vp_profile.val

            if strategy == VPStrategyType.POC_BREAKOUT_LONG:
                return {
                    "tp1": vp_profile.vah,
                    "tp2": vp_profile.vah + va_width,
                    "tp3": vp_profile.vah + va_width * Decimal("2")
                }
            else:
                return {
                    "tp1": vp_profile.val,
                    "tp2": vp_profile.val - va_width,
                    "tp3": vp_profile.val - va_width * Decimal("2")
                }

        else:
            # Default: 2%, 4%, 6% TPs
            if strategy == VPStrategyType.MEAN_REVERSION_LONG or "LONG" in strategy.value:
                return {
                    "tp1": entry_price * Decimal("1.02"),
                    "tp2": entry_price * Decimal("1.04"),
                    "tp3": entry_price * Decimal("1.06")
                }
            else:
                return {
                    "tp1": entry_price * Decimal("0.98"),
                    "tp2": entry_price * Decimal("0.96"),
                    "tp3": entry_price * Decimal("0.94")
                }

    def combine_with_mtf_signal(
        self,
        vp_signal: VPSignal,
        mtf_signal: Dict
    ) -> Dict:
        """
        Combine VP signal with multi-timeframe signal

        Returns enhanced signal with VP context
        """
        # Start with MTF signal as base
        combined = mtf_signal.copy()

        # Apply VP confidence modifier
        original_confidence = combined.get('confidence', 0.0)
        vp_confidence_mod = vp_signal.confidence / original_confidence if original_confidence > 0 else 1.0

        # Limit modifier range (0.8x to 1.3x)
        vp_confidence_mod = max(0.8, min(1.3, vp_confidence_mod))

        # Calculate final confidence
        final_confidence = min(original_confidence * vp_confidence_mod, 1.0)

        # Update combined signal
        combined['confidence'] = final_confidence
        combined['vp_strategy'] = vp_signal.strategy_type.value
        combined['vp_position'] = vp_signal.price_position
        combined['vp_confidence_modifier'] = vp_confidence_mod

        # Add VP-specific levels to metadata
        if 'metadata' not in combined:
            combined['metadata'] = {}

        combined['metadata']['volume_profile'] = {
            "poc": float(vp_signal.vp_profile.poc),
            "vah": float(vp_signal.vp_profile.vah),
            "val": float(vp_signal.vp_profile.val),
            "position": vp_signal.price_position,
            "strategy": vp_signal.strategy_type.value,
            "volume_bias": vp_signal.volume_bias,
            "stop_loss": float(vp_signal.stop_loss),
            "take_profit": {k: float(v) for k, v in vp_signal.take_profit_levels.items()},
            "reasoning": vp_signal.reasoning
        }

        return combined


# Global instance
_vp_strategy_analyzer: Optional[VPStrategyAnalyzer] = None


def get_vp_strategy_analyzer() -> VPStrategyAnalyzer:
    """Get or create global VP strategy analyzer"""
    global _vp_strategy_analyzer
    if _vp_strategy_analyzer is None:
        _vp_strategy_analyzer = VPStrategyAnalyzer()
    return _vp_strategy_analyzer


def reset_vp_strategy_analyzer():
    """Reset global analyzer (for testing)"""
    global _vp_strategy_analyzer
    _vp_strategy_analyzer = None
