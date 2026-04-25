"""
Trend Following Strategy Implementation
========================================
Purpose: Identify and follow market trends using moving averages and momentum

This strategy captures medium to long-term trends by entering positions
in the direction of the prevailing trend and riding them until reversal.

Entry Conditions (Long):
1. Price above all key EMAs (20, 50, 200)
2. EMAs in bullish alignment (20 > 50 > 200)
3. ADX above threshold indicating trending market
4. MACD line above signal line
5. Optional: Pullback to EMA support

Entry Conditions (Short):
1. Price below all key EMAs (20, 50, 200)
2. EMAs in bearish alignment (20 < 50 < 200)
3. ADX above threshold indicating trending market
4. MACD line below signal line
5. Optional: Rally to EMA resistance

Exit Conditions:
1. Trend reversal (EMA cross)
2. Trailing stop hit
3. Take profit at resistance/support levels
4. ADX declining below threshold

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
class TrendFollowingConfig:
    """Configuration for Trend Following Strategy"""

    # EMA periods
    ema_fast_period: int = 21  # Research-optimized period
    ema_medium_period: int = 50
    ema_slow_period: int = 200

    # ADX parameters
    adx_period: int = 14
    adx_trend_threshold: float = 25.0  # Above this = trending
    adx_strong_trend: float = 40.0  # Strong trend

    # MACD parameters
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # Entry filters
    min_trend_strength: float = 0.3  # Minimum trend strength (0-1)
    require_pullback: bool = False  # Require pullback to EMA
    pullback_tolerance_pct: float = 0.5  # Price within 0.5% of EMA

    # Risk management
    default_stop_loss_pct: float = 3.0
    default_take_profit_pct: float = 6.0
    trailing_stop_pct: float = 2.0  # Trailing stop distance
    use_trailing_stop: bool = True
    atr_multiplier_sl: float = 2.0  # SL = ATR * multiplier
    atr_multiplier_tp: float = 4.0  # TP = ATR * multiplier

    # Position sizing
    max_position_pct: float = 8.0  # Trend following allows larger positions
    risk_per_trade_pct: float = 2.0

    # Timing
    min_bars_between_signals: int = 10
    signal_expiry_seconds: int = 600

    # Exit parameters
    exit_on_ema_cross: bool = True
    exit_on_adx_decline: bool = True
    adx_exit_threshold: float = 20.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "ema_fast": self.ema_fast_period,
            "ema_medium": self.ema_medium_period,
            "ema_slow": self.ema_slow_period,
            "adx_period": self.adx_period,
            "adx_threshold": self.adx_trend_threshold,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "use_trailing_stop": self.use_trailing_stop,
        }


# =============================================================================
# TREND FOLLOWING STRATEGY
# =============================================================================

class TrendFollowingStrategy(StrategyBase):
    """
    Trend Following Trading Strategy

    Captures medium to long-term market trends using multiple timeframe
    analysis and trend confirmation indicators.

    Core Concept:
    "The trend is your friend" - This strategy identifies established
    trends and enters positions in the trend direction, using trailing
    stops to maximize profit during extended moves.

    Best Market Conditions:
    - Trending markets (strong directional moves)
    - Moderate to high volatility
    - Clear price momentum

    Not Suitable For:
    - Ranging/choppy markets
    - Low volatility environments
    - Instruments with frequent reversals
    """

    def __init__(
        self,
        strategy_config: Optional[TrendFollowingConfig] = None,
        supported_symbols: Optional[List[str]] = None,
        primary_timeframe: str = "60"
    ):
        """Initialize Trend Following Strategy"""
        super().__init__(
            strategy_id="trend_following_v1",
            name="Trend Following Strategy",
            version="1.0.0",
            category=StrategyCategory.TREND_FOLLOWING,
            risk_level=StrategyRiskLevel.MODERATE,
            supported_symbols=supported_symbols,
            primary_timeframe=primary_timeframe,
            description="Captures market trends using EMA alignment, ADX, and MACD"
        )

        self.strategy_config = strategy_config or TrendFollowingConfig()

        # Update metadata
        self.metadata.required_indicators = [
            "ema_20", "ema_50", "ema_200", "adx", "macd", "atr"
        ]
        self.metadata.required_data_history_bars = self.strategy_config.ema_slow_period + 100
        self.metadata.expected_win_rate = 0.45  # Lower win rate, higher R:R
        self.metadata.expected_profit_factor = 1.8
        self.metadata.expected_sharpe = 1.2
        self.metadata.typical_hold_period_hours = 48.0  # Longer holds

        # Strategy state
        self._last_signal_bar: Dict[str, int] = {}
        self._current_bar: Dict[str, int] = {}
        self._active_positions: Dict[str, Dict[str, Any]] = {}

        logger.info(
            f"TrendFollowingStrategy initialized: "
            f"EMA({self.strategy_config.ema_fast_period},"
            f"{self.strategy_config.ema_medium_period},"
            f"{self.strategy_config.ema_slow_period}), "
            f"ADX threshold={self.strategy_config.adx_trend_threshold}"
        )

    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================

    def _calculate_ema(
        self,
        closes: List[float],
        period: int
    ) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(closes) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = statistics.mean(closes[:period])  # SMA for initial value

        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _calculate_ema_series(
        self,
        closes: List[float],
        period: int
    ) -> List[float]:
        """Calculate EMA series for all available data"""
        if len(closes) < period:
            return []

        multiplier = 2 / (period + 1)
        emas = [statistics.mean(closes[:period])]

        for i in range(period, len(closes)):
            ema = (closes[i] - emas[-1]) * multiplier + emas[-1]
            emas.append(ema)

        return emas

    def _calculate_adx(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = None
    ) -> Dict[str, Optional[float]]:
        """
        Calculate Average Directional Index

        Returns ADX, +DI, and -DI
        """
        period = period or self.strategy_config.adx_period

        if len(highs) < period * 2:
            return {"adx": None, "plus_di": None, "minus_di": None}

        # Calculate True Range and Directional Movement
        plus_dm = []
        minus_dm = []
        tr_list = []

        for i in range(1, len(highs)):
            high_diff = highs[i] - highs[i-1]
            low_diff = lows[i-1] - lows[i]

            # Plus and Minus Directional Movement
            if high_diff > low_diff and high_diff > 0:
                plus_dm.append(high_diff)
            else:
                plus_dm.append(0)

            if low_diff > high_diff and low_diff > 0:
                minus_dm.append(low_diff)
            else:
                minus_dm.append(0)

            # True Range
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)

        if len(tr_list) < period:
            return {"adx": None, "plus_di": None, "minus_di": None}

        # Smooth the values using Wilder's smoothing
        def wilder_smooth(data: List[float], period: int) -> List[float]:
            smoothed = [sum(data[:period])]
            for i in range(period, len(data)):
                smoothed.append(smoothed[-1] - smoothed[-1]/period + data[i])
            return smoothed

        smoothed_tr = wilder_smooth(tr_list, period)
        smoothed_plus_dm = wilder_smooth(plus_dm, period)
        smoothed_minus_dm = wilder_smooth(minus_dm, period)

        # Calculate DI values
        plus_di_list = []
        minus_di_list = []
        dx_list = []

        for i in range(len(smoothed_tr)):
            if smoothed_tr[i] > 0:
                plus_di = 100 * smoothed_plus_dm[i] / smoothed_tr[i]
                minus_di = 100 * smoothed_minus_dm[i] / smoothed_tr[i]
            else:
                plus_di = 0
                minus_di = 0

            plus_di_list.append(plus_di)
            minus_di_list.append(minus_di)

            # DX
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx = 100 * abs(plus_di - minus_di) / di_sum
            else:
                dx = 0
            dx_list.append(dx)

        # Calculate ADX (smoothed DX)
        if len(dx_list) >= period:
            adx_values = wilder_smooth(dx_list, period)
            adx = adx_values[-1] if adx_values else None
        else:
            adx = None

        return {
            "adx": adx,
            "plus_di": plus_di_list[-1] if plus_di_list else None,
            "minus_di": minus_di_list[-1] if minus_di_list else None
        }

    def _calculate_macd(
        self,
        closes: List[float]
    ) -> Dict[str, Optional[float]]:
        """Calculate MACD indicator"""
        fast_period = self.strategy_config.macd_fast
        slow_period = self.strategy_config.macd_slow
        signal_period = self.strategy_config.macd_signal

        if len(closes) < slow_period + signal_period:
            return {"macd": None, "signal": None, "histogram": None}

        # Calculate EMAs
        fast_ema = self._calculate_ema_series(closes, fast_period)
        slow_ema = self._calculate_ema_series(closes, slow_period)

        if not fast_ema or not slow_ema:
            return {"macd": None, "signal": None, "histogram": None}

        # Align the EMAs
        offset = len(fast_ema) - len(slow_ema)
        fast_ema = fast_ema[offset:]

        # Calculate MACD line
        macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]

        if len(macd_line) < signal_period:
            return {"macd": macd_line[-1] if macd_line else None, "signal": None, "histogram": None}

        # Calculate signal line (EMA of MACD)
        signal_line = self._calculate_ema_series(macd_line, signal_period)

        if not signal_line:
            return {"macd": macd_line[-1], "signal": None, "histogram": None}

        macd_value = macd_line[-1]
        signal_value = signal_line[-1]
        histogram = macd_value - signal_value

        return {
            "macd": macd_value,
            "signal": signal_value,
            "histogram": histogram
        }

    def _calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> Optional[float]:
        """Calculate Average True Range"""
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

    # =========================================================================
    # TREND ANALYSIS
    # =========================================================================

    def _check_ema_alignment(
        self,
        ema_fast: float,
        ema_medium: float,
        ema_slow: float
    ) -> Tuple[str, float]:
        """
        Check EMA alignment for trend direction

        Returns:
            Tuple of (direction, strength)
            direction: 'bullish', 'bearish', or 'neutral'
            strength: 0.0 to 1.0
        """
        if ema_fast > ema_medium > ema_slow:
            # Perfect bullish alignment
            # Calculate strength based on separation
            separation = (ema_fast - ema_slow) / ema_slow
            strength = min(1.0, separation * 20)  # Scale to 0-1
            return 'bullish', strength

        elif ema_fast < ema_medium < ema_slow:
            # Perfect bearish alignment
            separation = (ema_slow - ema_fast) / ema_slow
            strength = min(1.0, separation * 20)
            return 'bearish', strength

        else:
            # Mixed/neutral
            return 'neutral', 0.0

    def _assess_trend_condition(
        self,
        price: float,
        ema_fast: float,
        ema_medium: float,
        ema_slow: float,
        adx: float,
        plus_di: float,
        minus_di: float
    ) -> MarketCondition:
        """Assess market condition for trend trading"""
        if adx is None:
            return MarketCondition.UNKNOWN

        # Check if market is trending
        if adx < self.strategy_config.adx_trend_threshold:
            return MarketCondition.RANGING

        # Determine trend direction and strength
        alignment, strength = self._check_ema_alignment(ema_fast, ema_medium, ema_slow)

        if alignment == 'bullish':
            if adx >= self.strategy_config.adx_strong_trend:
                return MarketCondition.STRONG_UPTREND
            return MarketCondition.UPTREND

        elif alignment == 'bearish':
            if adx >= self.strategy_config.adx_strong_trend:
                return MarketCondition.STRONG_DOWNTREND
            return MarketCondition.DOWNTREND

        return MarketCondition.RANGING

    # =========================================================================
    # ANALYSIS IMPLEMENTATION
    # =========================================================================

    async def analyze(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> AnalysisResult:
        """Analyze market conditions for trend following opportunities"""
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

        # Calculate indicators
        ema_fast = self._calculate_ema(closes, self.strategy_config.ema_fast_period)
        ema_medium = self._calculate_ema(closes, self.strategy_config.ema_medium_period)
        ema_slow = self._calculate_ema(closes, self.strategy_config.ema_slow_period)
        adx_data = self._calculate_adx(highs, lows, closes)
        macd_data = self._calculate_macd(closes)
        atr = self._calculate_atr(highs, lows, closes)

        if not all([ema_fast, ema_medium, ema_slow]):
            return AnalysisResult(
                symbol=symbol,
                condition=MarketCondition.UNKNOWN,
                confidence=0.0,
                recommendation="no_action"
            )

        # Assess trend
        adx = adx_data.get('adx', 0) or 0
        plus_di = adx_data.get('plus_di', 0) or 0
        minus_di = adx_data.get('minus_di', 0) or 0

        condition = self._assess_trend_condition(
            current_price, ema_fast, ema_medium, ema_slow,
            adx, plus_di, minus_di
        )

        # Get EMA alignment
        alignment, strength = self._check_ema_alignment(ema_fast, ema_medium, ema_slow)

        # Check MACD confirmation
        macd_line = macd_data.get('macd', 0) or 0
        macd_signal = macd_data.get('signal', 0) or 0
        macd_histogram = macd_data.get('histogram', 0) or 0

        macd_bullish = macd_line > macd_signal
        macd_bearish = macd_line < macd_signal

        # Calculate confidence
        confidence = self._calculate_trend_confidence(
            alignment, strength, adx, macd_bullish if alignment == 'bullish' else macd_bearish
        )

        # Get recommendation
        recommendation = self._get_trend_recommendation(
            current_price, ema_fast, ema_medium, ema_slow,
            alignment, adx, macd_bullish, macd_bearish
        )

        # Determine trend direction
        if alignment == 'bullish':
            trend_direction = 'bullish'
        elif alignment == 'bearish':
            trend_direction = 'bearish'
        else:
            trend_direction = 'neutral'

        # Build indicators dictionary
        indicators = {
            "ema_fast": ema_fast,
            "ema_medium": ema_medium,
            "ema_slow": ema_slow,
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "macd": macd_line,
            "macd_signal": macd_signal,
            "macd_histogram": macd_histogram,
            "atr": atr,
            "ema_alignment": alignment,
            "ema_strength": strength
        }

        # Support/resistance from EMAs
        support_levels = sorted([ema_fast, ema_medium, ema_slow], reverse=True)
        resistance_levels = support_levels.copy()

        result = AnalysisResult(
            symbol=symbol,
            condition=condition,
            trend_direction=trend_direction,
            trend_strength=strength * 100,
            volatility=atr / current_price * 100 if atr and current_price > 0 else 0,
            atr_value=atr,
            support_levels=support_levels if trend_direction == 'bullish' else [],
            resistance_levels=resistance_levels if trend_direction == 'bearish' else [],
            indicators=indicators,
            confidence=confidence,
            recommendation=recommendation
        )

        self._last_analysis[symbol] = result

        logger.debug(
            f"Trend analysis {symbol}: {condition.value}, "
            f"alignment={alignment}, ADX={adx:.1f}, "
            f"MACD={'bullish' if macd_bullish else 'bearish'}, "
            f"confidence={confidence:.2f}"
        )

        return result

    def _calculate_trend_confidence(
        self,
        alignment: str,
        strength: float,
        adx: float,
        macd_confirms: bool
    ) -> float:
        """Calculate confidence in trend signal"""
        confidence = 0.3  # Base

        # Alignment confirmation
        if alignment in ['bullish', 'bearish']:
            confidence += 0.2
            confidence += strength * 0.2  # Up to 0.2 for strong alignment

        # ADX strength
        if adx >= self.strategy_config.adx_strong_trend:
            confidence += 0.2
        elif adx >= self.strategy_config.adx_trend_threshold:
            confidence += 0.1

        # MACD confirmation
        if macd_confirms:
            confidence += 0.15

        return min(1.0, confidence)

    def _get_trend_recommendation(
        self,
        price: float,
        ema_fast: float,
        ema_medium: float,
        ema_slow: float,
        alignment: str,
        adx: float,
        macd_bullish: bool,
        macd_bearish: bool
    ) -> str:
        """Get trend-based recommendation"""
        # Must be trending
        if adx < self.strategy_config.adx_trend_threshold:
            return "no_action"

        # Check for long entry
        if alignment == 'bullish' and price > ema_fast:
            if macd_bullish:
                # Check for pullback if required
                if self.strategy_config.require_pullback:
                    if abs(price - ema_fast) / price <= self.strategy_config.pullback_tolerance_pct / 100:
                        return "long"
                    return "wait_pullback"
                return "long"

        # Check for short entry
        if alignment == 'bearish' and price < ema_fast:
            if macd_bearish:
                if self.strategy_config.require_pullback:
                    if abs(price - ema_fast) / price <= self.strategy_config.pullback_tolerance_pct / 100:
                        return "short"
                    return "wait_pullback"
                return "short"

        return "no_action"

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    async def generate_signals(
        self,
        symbol: str,
        analysis: AnalysisResult,
        current_price: Decimal
    ) -> List[StrategySignal]:
        """Generate trend following signals"""
        signals = []

        if analysis.recommendation not in ["long", "short"]:
            return signals

        if analysis.confidence < self.strategy_config.min_trend_strength:
            return signals

        # Check cooldown
        current_bar = self._current_bar.get(symbol, 0)
        last_signal_bar = self._last_signal_bar.get(symbol, -100)
        if current_bar - last_signal_bar < self.strategy_config.min_bars_between_signals:
            return signals

        indicators = analysis.indicators
        atr = indicators.get('atr')

        # Calculate stop loss and take profit
        if atr:
            sl_pct = (atr * self.strategy_config.atr_multiplier_sl / float(current_price)) * 100
            tp_pct = (atr * self.strategy_config.atr_multiplier_tp / float(current_price)) * 100
        else:
            sl_pct = self.strategy_config.default_stop_loss_pct
            tp_pct = self.strategy_config.default_take_profit_pct

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
                reasoning=self._build_trend_reasoning("long", indicators)
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["ema", "adx", "macd"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "HIGH" if analysis.condition == MarketCondition.STRONG_UPTREND else "MEDIUM"

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
                reasoning=self._build_trend_reasoning("short", indicators)
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["ema", "adx", "macd"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "HIGH" if analysis.condition == MarketCondition.STRONG_DOWNTREND else "MEDIUM"

            signals.append(signal)
            self._last_signal_bar[symbol] = current_bar

        logger.info(
            f"Generated {len(signals)} trend signal(s) for {symbol}"
        )

        return signals

    def _build_trend_reasoning(
        self,
        direction: str,
        indicators: Dict[str, Any]
    ) -> str:
        """Build reasoning for trend signal"""
        parts = []

        if direction == "long":
            parts.append("Trend following long entry")
            parts.append("EMAs in bullish alignment")
        else:
            parts.append("Trend following short entry")
            parts.append("EMAs in bearish alignment")

        adx = indicators.get('adx', 0)
        parts.append(f"ADX at {adx:.1f} confirms trend")

        macd_histogram = indicators.get('macd_histogram', 0)
        if macd_histogram > 0:
            parts.append("MACD histogram positive")
        else:
            parts.append("MACD histogram negative")

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
        """Calculate position size for trend following trade"""
        risk_pct = risk_per_trade_pct or self.strategy_config.risk_per_trade_pct
        risk_amount = available_capital * (risk_pct / 100)

        stop_loss_pct = signal.stop_loss_pct or self.strategy_config.default_stop_loss_pct

        if stop_loss_pct <= 0:
            stop_loss_pct = self.strategy_config.default_stop_loss_pct

        position_value = risk_amount / (stop_loss_pct / 100)

        # Apply maximum position limit
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
        logger.info(f"TrendFollowingStrategy ready")

    async def on_start(self) -> None:
        """Start trading"""
        await super().on_start()
        logger.info("TrendFollowingStrategy started")

    async def on_stop(self) -> None:
        """Stop trading"""
        await super().on_stop()
        self._last_signal_bar.clear()
        self._current_bar.clear()
        logger.info("TrendFollowingStrategy stopped")

    def update_bar_count(self, symbol: str) -> None:
        """Update bar count"""
        self._current_bar[symbol] = self._current_bar.get(symbol, 0) + 1


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_trend_following_strategy(
    symbols: Optional[List[str]] = None,
    timeframe: str = "60",
    config_overrides: Optional[Dict[str, Any]] = None
) -> TrendFollowingStrategy:
    """Factory function to create Trend Following strategy"""
    config = TrendFollowingConfig()

    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    return TrendFollowingStrategy(
        strategy_config=config,
        supported_symbols=symbols or [],
        primary_timeframe=timeframe
    )
