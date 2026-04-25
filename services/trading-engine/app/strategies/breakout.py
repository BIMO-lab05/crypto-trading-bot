"""
Breakout Strategy Implementation
=================================
Purpose: Trade price breakouts from consolidation patterns and key levels

This strategy identifies when price breaks through significant support
or resistance levels, typically after periods of consolidation.

Entry Conditions (Long Breakout):
1. Price breaks above resistance level
2. Volume spike confirms breakout
3. ATR indicates sufficient volatility
4. Optional: Consolidation pattern (squeeze) detected
5. Close above breakout level for confirmation

Entry Conditions (Short Breakout):
1. Price breaks below support level
2. Volume spike confirms breakout
3. ATR indicates sufficient volatility
4. Optional: Consolidation pattern (squeeze) detected
5. Close below breakout level for confirmation

Exit Conditions:
1. Target reached (measured move)
2. Stop loss hit (failed breakout)
3. Volume fading (losing momentum)
4. Price returns inside range (false breakout)

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import statistics

from app.strategies.base import (
    StrategyBase,
    StrategySignal,
    AnalysisResult,
    StrategyCategory,
    StrategyRiskLevel,
    SignalType,
    MarketCondition,
    create_signal
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class BreakoutConfig:
    """Configuration for Breakout Strategy"""

    # Consolidation detection
    consolidation_lookback: int = 20  # Bars to detect consolidation
    consolidation_max_range_pct: float = 5.0  # Max range for consolidation
    squeeze_bb_width_pct: float = 3.0  # BB width below this = squeeze

    # Breakout detection
    breakout_threshold_pct: float = 0.5  # Min break above/below level
    confirm_bars: int = 2  # Bars to confirm breakout
    pullback_zone_pct: float = 1.0  # Zone for pullback entries

    # Volume confirmation
    volume_spike_multiplier: float = 2.0  # Volume > 2x average
    volume_lookback: int = 20

    # Key level detection
    level_lookback: int = 50  # Bars to detect levels
    level_touches_required: int = 2  # Min touches for valid level
    level_tolerance_pct: float = 0.5  # Price within 0.5% = touch

    # ATR parameters
    atr_period: int = 14
    min_atr_percentile: float = 30.0  # Min ATR percentile for entry

    # Risk management
    default_stop_loss_pct: float = 1.5  # Tight stop for breakouts
    default_take_profit_pct: float = 4.5  # 3:1 R:R
    atr_stop_multiplier: float = 1.0  # SL below/above breakout level
    measured_move_multiplier: float = 1.0  # TP = breakout + range

    # Position sizing
    max_position_pct: float = 5.0
    risk_per_trade_pct: float = 1.5

    # Timing
    min_bars_between_signals: int = 5
    signal_expiry_seconds: int = 180  # Breakouts are time-sensitive

    # False breakout protection
    require_volume_confirmation: bool = True
    require_close_confirmation: bool = True
    max_wick_pct: float = 2.0  # Max wick size for valid breakout

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "consolidation_lookback": self.consolidation_lookback,
            "breakout_threshold_pct": self.breakout_threshold_pct,
            "volume_spike_multiplier": self.volume_spike_multiplier,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "risk_per_trade_pct": self.risk_per_trade_pct,
        }


# =============================================================================
# BREAKOUT STRATEGY
# =============================================================================

class BreakoutStrategy(StrategyBase):
    """
    Breakout Trading Strategy

    Identifies and trades price breakouts from consolidation patterns
    and key support/resistance levels.

    Core Concept:
    Periods of consolidation (low volatility) often precede significant
    price moves. When price breaks through key levels with volume
    confirmation, it signals the start of a new trend.

    Breakout Types:
    1. Range Breakout - Break from horizontal consolidation
    2. Squeeze Breakout - Break from Bollinger Band squeeze
    3. Level Breakout - Break of significant S/R level
    4. Pattern Breakout - Break from chart patterns (triangles, etc.)

    Best Market Conditions:
    - Post-consolidation periods
    - High volume breakouts
    - Clear support/resistance levels

    Not Suitable For:
    - Choppy, ranging markets without clear levels
    - Low liquidity environments
    - High spread instruments
    """

    def __init__(
        self,
        strategy_config: Optional[BreakoutConfig] = None,
        supported_symbols: Optional[List[str]] = None,
        primary_timeframe: str = "60"
    ):
        """Initialize Breakout Strategy"""
        super().__init__(
            strategy_id="breakout_v1",
            name="Breakout Strategy",
            version="1.0.0",
            category=StrategyCategory.BREAKOUT,
            risk_level=StrategyRiskLevel.AGGRESSIVE,  # Breakouts are inherently riskier
            supported_symbols=supported_symbols,
            primary_timeframe=primary_timeframe,
            description="Trades price breakouts from consolidation and key levels"
        )

        self.strategy_config = strategy_config or BreakoutConfig()

        # Update metadata
        self.metadata.required_indicators = [
            "bollinger_bands", "volume", "atr", "support_resistance"
        ]
        self.metadata.required_data_history_bars = max(
            self.strategy_config.consolidation_lookback,
            self.strategy_config.level_lookback,
            self.strategy_config.volume_lookback
        ) + 50
        self.metadata.expected_win_rate = 0.40  # Lower win rate, higher R:R
        self.metadata.expected_profit_factor = 1.6
        self.metadata.expected_sharpe = 0.9
        self.metadata.typical_hold_period_hours = 8.0

        # Strategy state
        self._last_signal_bar: Dict[str, int] = {}
        self._current_bar: Dict[str, int] = {}
        self._detected_levels: Dict[str, Dict[str, List[float]]] = {}
        self._consolidation_ranges: Dict[str, Tuple[float, float]] = {}

        logger.info(
            f"BreakoutStrategy initialized: "
            f"consolidation_lookback={self.strategy_config.consolidation_lookback}, "
            f"volume_spike={self.strategy_config.volume_spike_multiplier}x"
        )

    # =========================================================================
    # LEVEL DETECTION
    # =========================================================================

    def _detect_support_resistance(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        lookback: int = None
    ) -> Dict[str, List[float]]:
        """
        Detect support and resistance levels from price history

        Uses swing high/low detection and clustering to find significant levels.
        """
        lookback = lookback or self.strategy_config.level_lookback

        if len(highs) < lookback:
            return {"support": [], "resistance": []}

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        recent_closes = closes[-lookback:]

        current_price = closes[-1]
        tolerance = current_price * (self.strategy_config.level_tolerance_pct / 100)

        # Find swing highs (local maxima)
        swing_highs = []
        for i in range(2, len(recent_highs) - 2):
            if (recent_highs[i] > recent_highs[i-1] and
                recent_highs[i] > recent_highs[i-2] and
                recent_highs[i] > recent_highs[i+1] and
                recent_highs[i] > recent_highs[i+2]):
                swing_highs.append(recent_highs[i])

        # Find swing lows (local minima)
        swing_lows = []
        for i in range(2, len(recent_lows) - 2):
            if (recent_lows[i] < recent_lows[i-1] and
                recent_lows[i] < recent_lows[i-2] and
                recent_lows[i] < recent_lows[i+1] and
                recent_lows[i] < recent_lows[i+2]):
                swing_lows.append(recent_lows[i])

        # Cluster similar levels
        def cluster_levels(levels: List[float], tolerance: float) -> List[float]:
            if not levels:
                return []

            levels = sorted(levels)
            clusters = []
            current_cluster = [levels[0]]

            for level in levels[1:]:
                if level - current_cluster[-1] <= tolerance:
                    current_cluster.append(level)
                else:
                    if len(current_cluster) >= self.strategy_config.level_touches_required:
                        clusters.append(statistics.mean(current_cluster))
                    current_cluster = [level]

            if len(current_cluster) >= self.strategy_config.level_touches_required:
                clusters.append(statistics.mean(current_cluster))

            return clusters

        # Separate into support (below price) and resistance (above price)
        all_levels = cluster_levels(swing_highs + swing_lows, tolerance)

        support = [l for l in all_levels if l < current_price]
        resistance = [l for l in all_levels if l > current_price]

        # Keep closest levels
        support = sorted(support, reverse=True)[:3]  # Closest 3 support levels
        resistance = sorted(resistance)[:3]  # Closest 3 resistance levels

        return {
            "support": support,
            "resistance": resistance
        }

    # =========================================================================
    # CONSOLIDATION DETECTION
    # =========================================================================

    def _detect_consolidation(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict[str, Any]:
        """
        Detect if market is in consolidation phase

        Returns consolidation info including range and squeeze status.
        """
        lookback = self.strategy_config.consolidation_lookback

        if len(highs) < lookback:
            return {
                "is_consolidating": False,
                "range_high": None,
                "range_low": None,
                "range_pct": None
            }

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]

        range_high = max(recent_highs)
        range_low = min(recent_lows)
        current_price = closes[-1]

        if range_low <= 0:
            return {
                "is_consolidating": False,
                "range_high": range_high,
                "range_low": range_low,
                "range_pct": None
            }

        range_pct = (range_high - range_low) / range_low * 100

        is_consolidating = range_pct <= self.strategy_config.consolidation_max_range_pct

        return {
            "is_consolidating": is_consolidating,
            "range_high": range_high,
            "range_low": range_low,
            "range_pct": range_pct,
            "consolidation_bars": lookback
        }

    def _detect_squeeze(
        self,
        closes: List[float],
        bb_width_pct: float
    ) -> bool:
        """Detect Bollinger Band squeeze"""
        return bb_width_pct < self.strategy_config.squeeze_bb_width_pct

    # =========================================================================
    # BREAKOUT DETECTION
    # =========================================================================

    def _detect_breakout(
        self,
        current_price: float,
        current_close: float,
        current_high: float,
        current_low: float,
        prev_high: float,
        prev_low: float,
        consolidation: Dict[str, Any],
        levels: Dict[str, List[float]],
        current_volume: float,
        avg_volume: float
    ) -> Dict[str, Any]:
        """
        Detect if a breakout is occurring

        Checks for:
        1. Price breaking above resistance or below support
        2. Volume confirmation
        3. Close confirmation (not just wick)
        """
        result = {
            "is_breakout": False,
            "direction": None,
            "breakout_level": None,
            "breakout_type": None,
            "volume_confirms": False,
            "close_confirms": False
        }

        threshold_pct = self.strategy_config.breakout_threshold_pct

        # Check volume spike
        volume_spike = (current_volume / avg_volume) >= self.strategy_config.volume_spike_multiplier if avg_volume > 0 else False

        # Check for range breakout (from consolidation)
        if consolidation.get("is_consolidating"):
            range_high = consolidation["range_high"]
            range_low = consolidation["range_low"]

            # Upward breakout
            if current_high > range_high * (1 + threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "long"
                result["breakout_level"] = range_high
                result["breakout_type"] = "range_breakout"
                result["close_confirms"] = current_close > range_high
                result["volume_confirms"] = volume_spike

            # Downward breakout
            elif current_low < range_low * (1 - threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "short"
                result["breakout_level"] = range_low
                result["breakout_type"] = "range_breakout"
                result["close_confirms"] = current_close < range_low
                result["volume_confirms"] = volume_spike

        # Check for level breakout (S/R levels)
        if not result["is_breakout"] and levels.get("resistance"):
            nearest_resistance = levels["resistance"][0]
            if current_high > nearest_resistance * (1 + threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "long"
                result["breakout_level"] = nearest_resistance
                result["breakout_type"] = "level_breakout"
                result["close_confirms"] = current_close > nearest_resistance
                result["volume_confirms"] = volume_spike

        if not result["is_breakout"] and levels.get("support"):
            nearest_support = levels["support"][0]
            if current_low < nearest_support * (1 - threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "short"
                result["breakout_level"] = nearest_support
                result["breakout_type"] = "level_breakout"
                result["close_confirms"] = current_close < nearest_support
                result["volume_confirms"] = volume_spike

        # Apply confirmation filters
        if result["is_breakout"]:
            if self.strategy_config.require_volume_confirmation and not result["volume_confirms"]:
                result["is_breakout"] = False
                result["rejection_reason"] = "No volume confirmation"

            if self.strategy_config.require_close_confirmation and not result["close_confirms"]:
                result["is_breakout"] = False
                result["rejection_reason"] = "No close confirmation"

            # Check for excessive wick (potential false breakout)
            if result["direction"] == "long":
                wick_pct = (current_high - current_close) / current_close * 100 if current_close > 0 else 0
                if wick_pct > self.strategy_config.max_wick_pct:
                    result["is_breakout"] = False
                    result["rejection_reason"] = "Excessive upper wick"

            elif result["direction"] == "short":
                wick_pct = (current_close - current_low) / current_close * 100 if current_close > 0 else 0
                if wick_pct > self.strategy_config.max_wick_pct:
                    result["is_breakout"] = False
                    result["rejection_reason"] = "Excessive lower wick"

        return result

    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================

    def _calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = None
    ) -> Optional[float]:
        """Calculate ATR"""
        period = period or self.strategy_config.atr_period

        if len(highs) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            true_ranges.append(tr)

        return statistics.mean(true_ranges[-period:])

    def _calculate_bollinger_width(
        self,
        closes: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Optional[float]:
        """Calculate Bollinger Band width percentage"""
        if len(closes) < period:
            return None

        recent = closes[-period:]
        middle = statistics.mean(recent)
        std = statistics.stdev(recent) if len(recent) > 1 else 0

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        if middle > 0:
            width_pct = (upper - lower) / middle * 100
        else:
            width_pct = 0

        return width_pct

    # =========================================================================
    # ANALYSIS IMPLEMENTATION
    # =========================================================================

    async def analyze(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> AnalysisResult:
        """Analyze market for breakout opportunities"""
        candles = data.get('candles', [])
        if not candles or len(candles) < self.metadata.required_data_history_bars:
            return AnalysisResult(
                symbol=symbol,
                condition=MarketCondition.UNKNOWN,
                confidence=0.0,
                recommendation="no_action"
            )

        # Extract OHLCV
        opens = [float(c.get('open', c.get('o', 0))) for c in candles]
        highs = [float(c.get('high', c.get('h', 0))) for c in candles]
        lows = [float(c.get('low', c.get('l', 0))) for c in candles]
        closes = [float(c.get('close', c.get('c', 0))) for c in candles]
        volumes = [float(c.get('volume', c.get('v', 0))) for c in candles]

        current_price = closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        current_volume = volumes[-1]

        # Calculate indicators
        atr = self._calculate_atr(highs, lows, closes)
        bb_width = self._calculate_bollinger_width(closes)
        avg_volume = statistics.mean(volumes[-self.strategy_config.volume_lookback:-1]) if len(volumes) > self.strategy_config.volume_lookback else volumes[-1]

        # Detect S/R levels
        levels = self._detect_support_resistance(highs, lows, closes)
        self._detected_levels[symbol] = levels

        # Detect consolidation
        consolidation = self._detect_consolidation(highs, lows, closes)
        if consolidation.get("is_consolidating"):
            self._consolidation_ranges[symbol] = (
                consolidation["range_low"],
                consolidation["range_high"]
            )

        # Check for squeeze
        is_squeeze = self._detect_squeeze(closes, bb_width) if bb_width else False

        # Detect breakout
        breakout = self._detect_breakout(
            current_price, closes[-1], current_high, current_low,
            highs[-2] if len(highs) > 1 else current_high,
            lows[-2] if len(lows) > 1 else current_low,
            consolidation, levels,
            current_volume, avg_volume
        )

        # Assess market condition
        if breakout.get("is_breakout"):
            if breakout["direction"] == "long":
                condition = MarketCondition.UPTREND
            else:
                condition = MarketCondition.DOWNTREND
        elif consolidation.get("is_consolidating"):
            condition = MarketCondition.RANGING
        elif is_squeeze:
            condition = MarketCondition.LOW_VOLATILITY
        else:
            condition = MarketCondition.RANGING

        # Calculate confidence
        confidence = self._calculate_breakout_confidence(breakout, consolidation, is_squeeze)

        # Get recommendation
        if breakout.get("is_breakout"):
            recommendation = breakout["direction"]
        elif is_squeeze and consolidation.get("is_consolidating"):
            recommendation = "wait_breakout"
        else:
            recommendation = "no_action"

        # Build indicators dict
        indicators = {
            "atr": atr,
            "bb_width_pct": bb_width,
            "is_consolidating": consolidation.get("is_consolidating", False),
            "consolidation_range_pct": consolidation.get("range_pct"),
            "range_high": consolidation.get("range_high"),
            "range_low": consolidation.get("range_low"),
            "is_squeeze": is_squeeze,
            "volume_ratio": current_volume / avg_volume if avg_volume > 0 else 1.0,
            "breakout_detected": breakout.get("is_breakout", False),
            "breakout_type": breakout.get("breakout_type"),
            "breakout_level": breakout.get("breakout_level"),
            "breakout_direction": breakout.get("direction"),
        }

        result = AnalysisResult(
            symbol=symbol,
            condition=condition,
            trend_direction=breakout.get("direction", "neutral") or "neutral",
            trend_strength=50.0 if consolidation.get("is_consolidating") else 0.0,
            volatility=bb_width or 0.0,
            atr_value=atr,
            support_levels=levels.get("support", []),
            resistance_levels=levels.get("resistance", []),
            indicators=indicators,
            confidence=confidence,
            recommendation=recommendation
        )

        self._last_analysis[symbol] = result

        logger.debug(
            f"Breakout analysis {symbol}: "
            f"consolidating={consolidation.get('is_consolidating')}, "
            f"squeeze={is_squeeze}, breakout={breakout.get('is_breakout')}, "
            f"confidence={confidence:.2f}"
        )

        return result

    def _calculate_breakout_confidence(
        self,
        breakout: Dict[str, Any],
        consolidation: Dict[str, Any],
        is_squeeze: bool
    ) -> float:
        """Calculate confidence in breakout signal"""
        if not breakout.get("is_breakout"):
            return 0.3 if consolidation.get("is_consolidating") else 0.1

        confidence = 0.5  # Base for breakout

        # Volume confirmation
        if breakout.get("volume_confirms"):
            confidence += 0.2

        # Close confirmation
        if breakout.get("close_confirms"):
            confidence += 0.15

        # Squeeze breakout (higher reliability)
        if is_squeeze:
            confidence += 0.1

        # Consolidation length bonus
        range_pct = consolidation.get("range_pct", 10)
        if range_pct and range_pct < 3.0:  # Tight consolidation
            confidence += 0.05

        return min(1.0, confidence)

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    async def generate_signals(
        self,
        symbol: str,
        analysis: AnalysisResult,
        current_price: Decimal
    ) -> List[StrategySignal]:
        """Generate breakout signals"""
        signals = []

        if analysis.recommendation not in ["long", "short"]:
            return signals

        indicators = analysis.indicators

        if not indicators.get("breakout_detected"):
            return signals

        # Check cooldown
        current_bar = self._current_bar.get(symbol, 0)
        last_signal_bar = self._last_signal_bar.get(symbol, -100)
        if current_bar - last_signal_bar < self.strategy_config.min_bars_between_signals:
            return signals

        # Get breakout level for stop calculation
        breakout_level = indicators.get("breakout_level")
        atr = indicators.get("atr")

        # Calculate stops
        if atr:
            sl_distance = atr * self.strategy_config.atr_stop_multiplier
            sl_pct = (sl_distance / float(current_price)) * 100
        else:
            sl_pct = self.strategy_config.default_stop_loss_pct

        # Calculate target (measured move)
        range_high = indicators.get("range_high", 0)
        range_low = indicators.get("range_low", 0)
        if range_high and range_low and range_high > range_low:
            range_size = range_high - range_low
            measured_move = range_size * self.strategy_config.measured_move_multiplier
            tp_pct = (measured_move / float(current_price)) * 100
        else:
            tp_pct = self.strategy_config.default_take_profit_pct

        # Ensure minimum R:R
        if tp_pct < sl_pct * 2:
            tp_pct = sl_pct * 3  # Force 3:1 R:R

        # Generate signal
        if analysis.recommendation == "long":
            signal = create_signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type=SignalType.ENTRY_LONG,
                entry_price=current_price,
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
                confidence=analysis.confidence,
                reasoning=self._build_breakout_reasoning(indicators, "long")
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["support_resistance", "volume", "atr"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "CRITICAL"  # Breakouts are time-sensitive

            signals.append(signal)
            self._last_signal_bar[symbol] = current_bar

        elif analysis.recommendation == "short":
            signal = create_signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type=SignalType.ENTRY_SHORT,
                entry_price=current_price,
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
                confidence=analysis.confidence,
                reasoning=self._build_breakout_reasoning(indicators, "short")
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["support_resistance", "volume", "atr"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "CRITICAL"

            signals.append(signal)
            self._last_signal_bar[symbol] = current_bar

        logger.info(f"Generated breakout signal for {symbol}: {analysis.recommendation}")

        return signals

    def _build_breakout_reasoning(
        self,
        indicators: Dict[str, Any],
        direction: str
    ) -> str:
        """Build reasoning for breakout signal"""
        parts = []

        breakout_type = indicators.get("breakout_type", "breakout")
        breakout_level = indicators.get("breakout_level", 0)

        if direction == "long":
            parts.append(f"Bullish {breakout_type.replace('_', ' ')}")
            parts.append(f"Resistance broken at {breakout_level:.2f}")
        else:
            parts.append(f"Bearish {breakout_type.replace('_', ' ')}")
            parts.append(f"Support broken at {breakout_level:.2f}")

        volume_ratio = indicators.get("volume_ratio", 1.0)
        if volume_ratio > 1.5:
            parts.append(f"Volume {volume_ratio:.1f}x average")

        if indicators.get("is_squeeze"):
            parts.append("Breaking out of squeeze")

        range_pct = indicators.get("consolidation_range_pct")
        if range_pct:
            parts.append(f"After {range_pct:.1f}% consolidation")

        return ". ".join(parts)

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        signal: StrategySignal,
        available_capital: float,
        risk_per_trade_pct: Optional[float] = None
    ) -> Tuple[Decimal, float]:
        """Calculate position size for breakout trade"""
        risk_pct = risk_per_trade_pct or self.strategy_config.risk_per_trade_pct
        risk_amount = available_capital * (risk_pct / 100)

        stop_loss_pct = signal.stop_loss_pct or self.strategy_config.default_stop_loss_pct

        if stop_loss_pct <= 0:
            stop_loss_pct = self.strategy_config.default_stop_loss_pct

        position_value = risk_amount / (stop_loss_pct / 100)

        max_position_value = available_capital * (self.strategy_config.max_position_pct / 100)
        position_value = min(position_value, max_position_value)

        if signal.entry_price and signal.entry_price > 0:
            quantity = Decimal(str(position_value)) / signal.entry_price
        else:
            quantity = Decimal('0')

        quantity = quantity.quantize(Decimal('0.00000001'))

        return quantity, risk_amount

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    async def on_initialize(self) -> None:
        """Initialize strategy"""
        await super().on_initialize()
        for symbol in self.metadata.supported_symbols:
            self._last_signal_bar[symbol] = -100
            self._current_bar[symbol] = 0
        logger.info("BreakoutStrategy ready")

    async def on_start(self) -> None:
        """Start trading"""
        await super().on_start()
        logger.info("BreakoutStrategy started")

    async def on_stop(self) -> None:
        """Stop trading"""
        await super().on_stop()
        self._last_signal_bar.clear()
        self._current_bar.clear()
        self._detected_levels.clear()
        self._consolidation_ranges.clear()
        logger.info("BreakoutStrategy stopped")

    def update_bar_count(self, symbol: str) -> None:
        """Update bar count"""
        self._current_bar[symbol] = self._current_bar.get(symbol, 0) + 1


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_breakout_strategy(
    symbols: Optional[List[str]] = None,
    timeframe: str = "60",
    config_overrides: Optional[Dict[str, Any]] = None
) -> BreakoutStrategy:
    """Factory function to create Breakout strategy"""
    config = BreakoutConfig()

    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return BreakoutStrategy(
        strategy_config=config,
        supported_symbols=symbols or [],
        primary_timeframe=timeframe
    )
