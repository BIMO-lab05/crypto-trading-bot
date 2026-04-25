"""
Enhanced Breakout Strategy Implementation
=========================================
Purpose: Trade price breakouts from consolidation patterns and key levels with improved confirmation

This strategy identifies when price breaks through significant support
or resistance levels, typically after periods of consolidation, with enhanced
confirmation mechanisms.

Enhanced Features:
1. Multiple confirmation layers (volume, momentum, volatility)
2. Better false breakout detection
3. Dynamic stop-loss based on ATR
4. Improved position sizing
5. Better risk management

Entry Conditions (Long Breakout):
1. Price breaks above resistance level
2. Volume spike confirms breakout
3. ATR indicates sufficient volatility
4. Momentum indicator (MACD) confirms trend
5. Close above breakout level for confirmation
6. Pullback to former resistance zone (confirmation)

Entry Conditions (Short Breakout):
1. Price breaks below support level
2. Volume spike confirms breakout
3. ATR indicates sufficient volatility
4. Momentum indicator (MACD) confirms trend
5. Close below breakout level for confirmation
6. Pullback to former support zone (confirmation)

Exit Conditions:
1. Target reached (measured move)
2. Stop loss hit (failed breakout)
3. Volume fading (losing momentum)
4. Price returns inside range (false breakout)
5. Contrarian signal from momentum indicators
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
import statistics
import numpy as np
import pandas as pd

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# ENHANCED CONFIGURATION
# =============================================================================

@dataclass
class EnhancedBreakoutConfig:
    """Configuration for Enhanced Breakout Strategy"""

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

    # Momentum confirmation (MACD)
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9

    # Risk management
    default_stop_loss_pct: float = 1.5  # Tight stop for breakouts
    default_take_profit_pct: float = 4.5  # 3:1 R:R
    atr_stop_multiplier: float = 1.5  # SL based on ATR
    measured_move_multiplier: float = 1.0  # TP = breakout + range

    # Position sizing
    max_position_pct: float = 5.0
    risk_per_trade_pct: float = 1.5

    # Timing
    min_bars_between_signals: int = 5
    signal_expiry_seconds: int = 180  # Breakouts are time-sensitive

    # Enhanced confirmation features
    require_momentum_confirmation: bool = True  # MACD confirmation
    require_pullback_confirmation: bool = True  # Pullback to former level
    enable_dynamic_stops: bool = True  # Use ATR-based stops
    max_wick_pct: float = 2.0  # Max wick size for valid breakout

    # False breakout protection
    require_volume_confirmation: bool = True
    require_close_confirmation: bool = True
    enable_false_breakout_detection: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "consolidation_lookback": self.consolidation_lookback,
            "breakout_threshold_pct": self.breakout_threshold_pct,
            "volume_spike_multiplier": self.volume_spike_multiplier,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "require_momentum_confirmation": self.require_momentum_confirmation,
            "enable_dynamic_stops": self.enable_dynamic_stops,
        }


# =============================================================================
# ENHANCED BREAKOUT STRATEGY
# =============================================================================

class EnhancedBreakoutStrategy:
    """
    Enhanced Breakout Trading Strategy

    Identifies and trades price breakouts from consolidation patterns
    and key support/resistance levels with improved confirmation mechanisms.

    Core Concept:
    Periods of consolidation (low volatility) often precede significant
    price moves. When price breaks through key levels with volume
    and momentum confirmation, it signals the start of a new trend.

    Enhanced Features:
    1. Volume confirmation
    2. Momentum confirmation (MACD)
    3. Pullback confirmation
    4. Dynamic stops based on ATR
    5. False breakout detection
    6. Improved position sizing
    """

    def __init__(
        self,
        strategy_config: Optional[EnhancedBreakoutConfig] = None,
        supported_symbols: Optional[List[str]] = None,
        primary_timeframe: str = "60"
    ):
        """Initialize Enhanced Breakout Strategy"""
        self.strategy_config = strategy_config or EnhancedBreakoutConfig()

        # Strategy state
        self._last_signal_bar: Dict[str, int] = {}
        self._current_bar: Dict[str, int] = {}
        self._detected_levels: Dict[str, Dict[str, List[float]]] = {}
        self._consolidation_ranges: Dict[str, Tuple[float, float]] = {}
        self._breakout_levels: Dict[str, float] = {}  # Track recent breakout levels

        logger.info(
            f"EnhancedBreakoutStrategy initialized: "
            f"consolidation_lookback={self.strategy_config.consolidation_lookback}, "
            f"volume_spike={self.strategy_config.volume_spike_multiplier}x, "
            f"momentum_confirmed={self.strategy_config.require_momentum_confirmation}"
        )

    # =========================================================================
    # ENHANCED LEVEL DETECTION
    # =========================================================================

    def _detect_support_resistance(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        lookback: int = None
    ) -> Dict[str, List[float]]:
        """
        Enhanced support and resistance level detection with multiple methods
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
    # ENHANCED CONSOLIDATION DETECTION
    # =========================================================================

    def _detect_consolidation(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float]
    ) -> Dict[str, Any]:
        """
        Enhanced consolidation detection with multiple indicators
        """
        lookback = self.strategy_config.consolidation_lookback

        if len(highs) < lookback:
            return {
                "is_consolidating": False,
                "range_high": None,
                "range_low": None,
                "range_pct": None,
                "volatility_ratio": None
            }

        recent_highs = highs[-lookback:]
        recent_lows = lows[-lookback:]
        recent_closes = closes[-lookback:]

        range_high = max(recent_highs)
        range_low = min(recent_lows)
        current_price = closes[-1]

        if range_low <= 0:
            return {
                "is_consolidating": False,
                "range_high": range_high,
                "range_low": range_low,
                "range_pct": None,
                "volatility_ratio": None
            }

        range_pct = (range_high - range_low) / range_low * 100

        # Calculate volatility ratio (current vs historical)
        current_volatility = np.std(np.diff(recent_closes))
        historical_volatility = np.mean([np.std(np.diff(closes[i:i+lookback])) 
                                       for i in range(len(closes)-lookback, len(closes)-10)])
        
        volatility_ratio = current_volatility / historical_volatility if historical_volatility > 0 else 1.0

        is_consolidating = (range_pct <= self.strategy_config.consolidation_max_range_pct and 
                           volatility_ratio < 0.7)  # Below 70% of historical volatility

        return {
            "is_consolidating": is_consolidating,
            "range_high": range_high,
            "range_low": range_low,
            "range_pct": range_pct,
            "volatility_ratio": volatility_ratio,
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
    # ENHANCED BREAKOUT DETECTION WITH MULTIPLE CONFIRMATIONS
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
        avg_volume: float,
        macd_histogram: float,
        atr_value: float
    ) -> Dict[str, Any]:
        """
        Enhanced breakout detection with multiple confirmation layers
        """
        result = {
            "is_breakout": False,
            "direction": None,
            "breakout_level": None,
            "breakout_type": None,
            "volume_confirms": False,
            "close_confirms": False,
            "momentum_confirms": False,
            "pullback_confirms": False,
            "confidence": 0.0
        }

        threshold_pct = self.strategy_config.breakout_threshold_pct

        # Check volume spike
        volume_spike = (current_volume / avg_volume) >= self.strategy_config.volume_spike_multiplier if avg_volume > 0 else False
        result["volume_confirms"] = volume_spike

        # Check momentum (MACD histogram should confirm direction)
        momentum_confirms = False
        if self.strategy_config.require_momentum_confirmation:
            if current_price > current_close:  # Bullish breakout
                momentum_confirms = macd_histogram > 0
            else:  # Bearish breakout
                momentum_confirms = macd_histogram < 0
        else:
            momentum_confirms = True  # Skip if not required
        
        result["momentum_confirms"] = momentum_confirms

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

            # Downward breakout
            elif current_low < range_low * (1 - threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "short"
                result["breakout_level"] = range_low
                result["breakout_type"] = "range_breakout"
                result["close_confirms"] = current_close < range_low

        # Check for level breakout (S/R levels)
        if not result["is_breakout"] and levels.get("resistance"):
            nearest_resistance = levels["resistance"][0]
            if current_high > nearest_resistance * (1 + threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "long"
                result["breakout_level"] = nearest_resistance
                result["breakout_type"] = "level_breakout"
                result["close_confirms"] = current_close > nearest_resistance

        if not result["is_breakout"] and levels.get("support"):
            nearest_support = levels["support"][0]
            if current_low < nearest_support * (1 - threshold_pct / 100):
                result["is_breakout"] = True
                result["direction"] = "short"
                result["breakout_level"] = nearest_support
                result["breakout_type"] = "level_breakout"
                result["close_confirms"] = current_close < nearest_support

        # Apply confirmation filters
        if result["is_breakout"]:
            # All confirmations must pass
            all_confirmations_pass = True
            
            if self.strategy_config.require_volume_confirmation and not result["volume_confirms"]:
                all_confirmations_pass = False
                result["rejection_reason"] = "No volume confirmation"

            if self.strategy_config.require_close_confirmation and not result["close_confirms"]:
                all_confirmations_pass = False
                result["rejection_reason"] = "No close confirmation"

            if self.strategy_config.require_momentum_confirmation and not result["momentum_confirms"]:
                all_confirmations_pass = False
                result["rejection_reason"] = "No momentum confirmation"

            # Check for excessive wick (potential false breakout)
            if result["direction"] == "long":
                wick_pct = (current_high - current_close) / current_close * 100 if current_close > 0 else 0
                if wick_pct > self.strategy_config.max_wick_pct:
                    all_confirmations_pass = False
                    result["rejection_reason"] = "Excessive upper wick"

            elif result["direction"] == "short":
                wick_pct = (current_close - current_low) / current_close * 100 if current_close > 0 else 0
                if wick_pct > self.strategy_config.max_wick_pct:
                    all_confirmations_pass = False
                    result["rejection_reason"] = "Excessive lower wick"

            result["is_breakout"] = all_confirmations_pass

        # Calculate confidence based on confirmations
        if result["is_breakout"]:
            confidence = 0.5  # Base confidence
            
            # Boost for each confirmation
            if result["volume_confirms"]:
                confidence += 0.2
            if result["momentum_confirms"]:
                confidence += 0.2
            if result["close_confirms"]:
                confidence += 0.1
            
            # Boost for consolidation breakout
            if consolidation.get("is_consolidating"):
                confidence += 0.1
                
            result["confidence"] = min(1.0, confidence)

        return result

    # =========================================================================
    # ENHANCED INDICATOR CALCULATIONS
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

    def _calculate_macd(
        self,
        closes: List[float]
    ) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate MACD line, signal line, and histogram"""
        if len(closes) < self.strategy_config.macd_slow_period + self.strategy_config.macd_signal_period:
            return None, None, None

        closes_series = pd.Series(closes)
        
        # Calculate EMAs
        ema_fast = closes_series.ewm(span=self.strategy_config.macd_fast_period).mean()
        ema_slow = closes_series.ewm(span=self.strategy_config.macd_slow_period).mean()
        
        # MACD line
        macd_line = ema_fast - ema_slow
        
        # Signal line
        signal_line = macd_line.ewm(span=self.strategy_config.macd_signal_period).mean()
        
        # Histogram
        histogram = macd_line - signal_line
        
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]

    # =========================================================================
    # ENHANCED ANALYSIS IMPLEMENTATION
    # =========================================================================

    def analyze(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Enhanced analysis with multiple confirmation layers"""
        candles = data.get('candles', [])
        if not candles or len(candles) < 200:  # Increased requirement for enhanced analysis
            return {
                "symbol": symbol,
                "is_breakout": False,
                "direction": None,
                "confidence": 0.0,
                "reason": "Insufficient data for enhanced analysis"
            }

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
        
        # Calculate MACD
        macd_line, signal_line, macd_histogram = self._calculate_macd(closes)

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

        # Detect breakout with enhanced confirmations
        breakout = self._detect_breakout(
            current_price, closes[-1], current_high, current_low,
            highs[-2] if len(highs) > 1 else current_high,
            lows[-2] if len(lows) > 1 else current_low,
            consolidation, levels,
            current_volume, avg_volume,
            macd_histogram if macd_histogram is not None else 0,
            atr if atr is not None else 0
        )

        # Build enhanced indicators dict
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
            "macd_histogram": macd_histogram,
            "macd_line": macd_line,
            "macd_signal": signal_line,
            "volatility_ratio": consolidation.get("volatility_ratio")
        }

        result = {
            "symbol": symbol,
            "is_breakout": breakout.get("is_breakout", False),
            "direction": breakout.get("direction"),
            "confidence": breakout.get("confidence", 0.0),
            "indicators": indicators,
            "consolidation_info": consolidation,
            "support_levels": levels.get("support", []),
            "resistance_levels": levels.get("resistance", []),
            "breakout_details": breakout
        }

        logger.debug(
            f"Enhanced breakout analysis {symbol}: "
            f"consolidating={consolidation.get('is_consolidating')}, "
            f"squeeze={is_squeeze}, breakout={breakout.get('is_breakout')}, "
            f"confidence={breakout.get('confidence', 0.0):.2f}"
        )

        return result

    # =========================================================================
    # ENHANCED SIGNAL GENERATION WITH DYNAMIC PARAMETERS
    # =========================================================================

    def generate_signal(
        self,
        symbol: str,
        analysis: Dict[str, Any],
        current_price: float
    ) -> Optional[Dict[str, Any]]:
        """Generate enhanced breakout signals with dynamic parameters"""
        if not analysis.get("is_breakout") or not analysis.get("direction"):
            return None

        indicators = analysis.get("indicators", {})
        breakout_details = analysis.get("breakout_details", {})

        # Check cooldown
        current_bar = self._current_bar.get(symbol, 0)
        last_signal_bar = self._last_signal_bar.get(symbol, -100)
        if current_bar - last_signal_bar < self.strategy_config.min_bars_between_signals:
            return None

        # Get breakout level for stop calculation
        breakout_level = indicators.get("breakout_level")
        atr = indicators.get("atr")

        # Calculate dynamic stops based on ATR
        if atr and self.strategy_config.enable_dynamic_stops:
            sl_distance = atr * self.strategy_config.atr_stop_multiplier
            sl_pct = (sl_distance / current_price) * 100
        else:
            sl_pct = self.strategy_config.default_stop_loss_pct

        # Calculate target (measured move)
        range_high = indicators.get("range_high", 0)
        range_low = indicators.get("range_low", 0)
        if range_high and range_low and range_high > range_low:
            range_size = range_high - range_low
            measured_move = range_size * self.strategy_config.measured_move_multiplier
            tp_pct = (measured_move / current_price) * 100
        else:
            tp_pct = self.strategy_config.default_take_profit_pct

        # Ensure minimum R:R ratio
        if tp_pct < sl_pct * 1.5:  # At least 1.5:1 ratio
            tp_pct = sl_pct * 2  # Force 2:1 R:R

        # Generate signal with enhanced reasoning
        direction = analysis["direction"]
        confidence = analysis["confidence"]

        if direction == "long":
            signal = {
                "symbol": symbol,
                "action": "BUY",
                "entry_price": current_price,
                "stop_loss_pct": sl_pct,
                "take_profit_pct": tp_pct,
                "confidence": confidence,
                "reason": self._build_enhanced_reasoning(indicators, "long", confidence),
                "breakout_type": indicators.get("breakout_type"),
                "breakout_level": breakout_level,
                "atr_based_stop": self.strategy_config.enable_dynamic_stops,
                "macd_confirmation": indicators.get("macd_histogram", 0) > 0
            }
            
            # Store breakout level for potential pullback confirmation
            self._breakout_levels[symbol] = breakout_level

        elif direction == "short":
            signal = {
                "symbol": symbol,
                "action": "SELL",
                "entry_price": current_price,
                "stop_loss_pct": sl_pct,
                "take_profit_pct": tp_pct,
                "confidence": confidence,
                "reason": self._build_enhanced_reasoning(indicators, "short", confidence),
                "breakout_type": indicators.get("breakout_type"),
                "breakout_level": breakout_level,
                "atr_based_stop": self.strategy_config.enable_dynamic_stops,
                "macd_confirmation": indicators.get("macd_histogram", 0) < 0
            }
            
            # Store breakout level for potential pullback confirmation
            self._breakout_levels[symbol] = breakout_level

        else:
            return None

        # Update signal tracking
        self._last_signal_bar[symbol] = current_bar

        logger.info(f"Generated enhanced breakout signal for {symbol}: {direction} (confidence: {confidence:.2f})")

        return signal

    def _build_enhanced_reasoning(
        self,
        indicators: Dict[str, Any],
        direction: str,
        confidence: float
    ) -> str:
        """Build enhanced reasoning for breakout signal"""
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

        macd_hist = indicators.get("macd_histogram", 0)
        if macd_hist and abs(macd_hist) > 0.0001:  # Non-zero MACD confirmation
            if (direction == "long" and macd_hist > 0) or (direction == "short" and macd_hist < 0):
                parts.append("Momentum confirmed")

        if indicators.get("is_squeeze"):
            parts.append("Breaking out of squeeze")

        range_pct = indicators.get("consolidation_range_pct")
        if range_pct:
            parts.append(f"After {range_pct:.1f}% consolidation")

        parts.append(f"Confidence: {confidence:.1f}")

        return ". ".join(parts)

    # =========================================================================
    # ENHANCED POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        signal: Dict[str, Any],
        available_capital: float,
        risk_per_trade_pct: Optional[float] = None
    ) -> float:
        """Calculate enhanced position size based on multiple factors"""
        risk_pct = risk_per_trade_pct or self.strategy_config.risk_per_trade_pct
        risk_amount = available_capital * (risk_pct / 100)

        stop_loss_pct = signal.get('stop_loss_pct') or self.strategy_config.default_stop_loss_pct

        if stop_loss_pct <= 0:
            stop_loss_pct = self.strategy_config.default_stop_loss_pct

        position_value = risk_amount / (stop_loss_pct / 100)

        max_position_value = available_capital * (self.strategy_config.max_position_pct / 100)
        position_value = min(position_value, max_position_value)

        # Adjust position size based on confidence
        confidence = signal.get('confidence', 0.5)
        confidence_adjustment = 0.5 + (confidence * 0.5)  # Scale from 0.5 to 1.0
        position_value = position_value * confidence_adjustment

        # Further adjust based on volatility
        volatility_ratio = signal.get('indicators', {}).get('volatility_ratio', 1.0)
        if volatility_ratio > 1.5:  # High volatility
            position_value = position_value * 0.8  # Reduce position size
        elif volatility_ratio < 0.7:  # Low volatility
            position_value = position_value * 1.1  # Slightly increase position size

        return min(position_value, available_capital * 0.1)  # Cap at 10% of capital

    # =========================================================================
    # ENHANCED FALSE BREAKOUT DETECTION
    # =========================================================================

    def detect_false_breakout(
        self,
        symbol: str,
        current_price: float,
        current_candle: Dict[str, Any]
    ) -> bool:
        """Detect if a recent breakout was a false breakout"""
        if symbol not in self._breakout_levels:
            return False

        breakout_level = self._breakout_levels[symbol]
        current_close = current_candle.get('close', current_candle.get('c', 0))
        current_high = current_candle.get('high', current_candle.get('h', 0))
        current_low = current_candle.get('low', current_candle.get('l', 0))

        # Check if price has moved back inside the previous range
        # within a certain number of bars since the breakout
        if hasattr(self, '_bars_since_breakout'):
            bars_since = self._bars_since_breakout.get(symbol, 0)
            if bars_since < 5:  # Within 5 bars of breakout
                # If price moved back inside the range, it might be a false breakout
                if (current_close < breakout_level and current_high > breakout_level) or \
                   (current_close > breakout_level and current_low < breakout_level):
                    return True

        return False


# =============================================================================
# ENHANCED FACTORY FUNCTION
# =============================================================================

def create_enhanced_breakout_strategy(
    symbols: Optional[List[str]] = None,
    timeframe: str = "60",
    config_overrides: Optional[Dict[str, Any]] = None
) -> EnhancedBreakoutStrategy:
    """Factory function to create Enhanced Breakout strategy"""
    config = EnhancedBreakoutConfig()

    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return EnhancedBreakoutStrategy(
        strategy_config=config,
        supported_symbols=symbols or [],
        primary_timeframe=timeframe
    )