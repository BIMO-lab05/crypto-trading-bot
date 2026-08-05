"""
Mean Reversion Strategy Implementation
=======================================
Purpose: Trade price reversions to statistical mean using Bollinger Bands and RSI

This strategy identifies overbought/oversold conditions and trades
expecting price to revert to its mean value.

Entry Conditions (Long):
1. Price touches or crosses below lower Bollinger Band
2. RSI below 30 (oversold)
3. Volume spike indicating capitulation
4. Optional: MACD histogram showing bullish divergence

Entry Conditions (Short):
1. Price touches or crosses above upper Bollinger Band
2. RSI above 70 (overbought)
3. Volume spike indicating exhaustion
4. Optional: MACD histogram showing bearish divergence

Exit Conditions:
1. Price reaches middle Bollinger Band (mean)
2. RSI returns to neutral zone (40-60)
3. Stop loss hit
4. Take profit hit

Phase 9: Multi-Strategy Orchestration Engine
Author: Backend Developer Agent
Date: 2025-12-11
"""

import logging
from dataclasses import dataclass
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
    create_signal,
)

# Configure logging
logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class MeanReversionConfig:
    """
    Configuration for Mean Reversion Strategy

    Contains all tunable parameters for the strategy.
    """

    # Bollinger Bands parameters
    bb_period: int = 20  # Lookback period for SMA
    bb_std_dev: float = 2.0  # Standard deviation multiplier
    bb_touch_threshold: float = 0.02  # Price within 2% of band = "touching"

    # RSI parameters
    rsi_period: int = 14
    rsi_oversold: float = 30.0  # Below this = oversold
    rsi_overbought: float = 70.0  # Above this = overbought
    rsi_neutral_low: float = 40.0  # Neutral zone lower bound
    rsi_neutral_high: float = 60.0  # Neutral zone upper bound

    # Volume filter
    volume_spike_multiplier: float = 1.5  # Volume > 1.5x average = spike
    volume_lookback: int = 20  # Bars for average volume calculation

    # Entry filters
    min_bb_width_pct: float = 1.0  # Min BB width to trade (avoid squeeze)
    max_bb_width_pct: float = 10.0  # Max BB width (avoid extreme volatility)
    min_confidence: float = 0.5  # Min signal confidence

    # Risk management
    default_stop_loss_pct: float = 2.0  # Default SL as % from entry
    default_take_profit_pct: float = 3.0  # Default TP as % from entry
    atr_stop_multiplier: float = 1.5  # SL = entry +/- ATR * multiplier
    use_atr_stops: bool = True  # Use ATR for dynamic stops

    # Position sizing
    max_position_pct: float = 5.0  # Max position as % of capital
    risk_per_trade_pct: float = 1.5  # Risk per trade as % of capital

    # Timing
    min_bars_between_signals: int = 5  # Cooldown between signals
    signal_expiry_seconds: int = 300  # Signal validity period

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "bb_period": self.bb_period,
            "bb_std_dev": self.bb_std_dev,
            "rsi_period": self.rsi_period,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "default_stop_loss_pct": self.default_stop_loss_pct,
            "default_take_profit_pct": self.default_take_profit_pct,
            "max_position_pct": self.max_position_pct,
            "risk_per_trade_pct": self.risk_per_trade_pct,
        }


# =============================================================================
# MEAN REVERSION STRATEGY
# =============================================================================


class MeanReversionStrategy(StrategyBase):
    """
    Mean Reversion Trading Strategy

    Trades price reversions to statistical mean using technical indicators.

    Core Concept:
    Price tends to oscillate around its mean value. When price deviates
    significantly from the mean (measured by Bollinger Bands and RSI),
    there's a high probability it will revert back.

    Best Market Conditions:
    - Ranging/sideways markets
    - Low to moderate volatility
    - High liquidity instruments

    Not Suitable For:
    - Strong trending markets
    - Extremely volatile conditions
    - Low liquidity instruments

    Usage:
        config = MeanReversionConfig(bb_period=20, rsi_period=14)
        strategy = MeanReversionStrategy(config=config)

        # Run analysis
        analysis = await strategy.analyze("BTCUSDT", market_data)

        # Generate signals
        signals = await strategy.generate_signals("BTCUSDT", analysis, Decimal("42000"))

        # Calculate position size (capital = the live balance, never hardcoded)
        size, risk = strategy.calculate_position_size(
            signals[0], available_capital, 1.5
        )
    """

    def __init__(
        self,
        strategy_config: Optional[MeanReversionConfig] = None,
        supported_symbols: Optional[List[str]] = None,
        primary_timeframe: str = "60",
    ):
        """
        Initialize Mean Reversion Strategy

        Args:
            strategy_config: Strategy configuration
            supported_symbols: List of supported trading symbols
            primary_timeframe: Primary trading timeframe (minutes)
        """
        # Initialize base class
        super().__init__(
            strategy_id="mean_reversion_v1",
            name="Mean Reversion Strategy",
            version="1.0.0",
            category=StrategyCategory.MEAN_REVERSION,
            risk_level=StrategyRiskLevel.MODERATE,
            supported_symbols=supported_symbols,
            primary_timeframe=primary_timeframe,
            description="Trades price reversions to statistical mean using Bollinger Bands and RSI",
        )

        # Store strategy configuration
        self.strategy_config = strategy_config or MeanReversionConfig()

        # Update metadata with configuration
        self.metadata.required_indicators = ["bollinger_bands", "rsi", "volume", "atr"]
        self.metadata.required_data_history_bars = max(
            self.strategy_config.bb_period + 50,
            self.strategy_config.rsi_period + 50,
            self.strategy_config.volume_lookback + 50,
        )
        self.metadata.expected_win_rate = 0.55
        self.metadata.expected_profit_factor = 1.4
        self.metadata.expected_sharpe = 0.8
        self.metadata.typical_hold_period_hours = 4.0

        # Strategy-specific state
        self._last_signal_bar: Dict[str, int] = {}
        self._current_bar: Dict[str, int] = {}

        logger.info(
            f"MeanReversionStrategy initialized: "
            f"BB({self.strategy_config.bb_period}, {self.strategy_config.bb_std_dev}), "
            f"RSI({self.strategy_config.rsi_period})"
        )

    # =========================================================================
    # INDICATOR CALCULATIONS
    # =========================================================================

    def _calculate_bollinger_bands(
        self, closes: List[float], period: int = None, std_dev: float = None
    ) -> Dict[str, Optional[float]]:
        """
        Calculate Bollinger Bands

        Args:
            closes: List of closing prices
            period: Lookback period (default from config)
            std_dev: Standard deviation multiplier (default from config)

        Returns:
            Dict with upper, middle, lower bands and width
        """
        period = period or self.strategy_config.bb_period
        std_dev = std_dev or self.strategy_config.bb_std_dev

        if len(closes) < period:
            return {"upper": None, "middle": None, "lower": None, "width_pct": None}

        # Get recent closes
        recent_closes = closes[-period:]

        # Calculate SMA (middle band)
        middle = statistics.mean(recent_closes)

        # Calculate standard deviation
        std = statistics.stdev(recent_closes) if len(recent_closes) > 1 else 0

        # Calculate bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        # Calculate width as percentage
        width_pct = ((upper - lower) / middle * 100) if middle > 0 else 0

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "width_pct": width_pct,
        }

    def _calculate_rsi(
        self, closes: List[float], period: int = None
    ) -> Optional[float]:
        """
        Calculate Relative Strength Index

        Args:
            closes: List of closing prices
            period: Lookback period (default from config)

        Returns:
            RSI value (0-100) or None
        """
        period = period or self.strategy_config.rsi_period

        if len(closes) < period + 1:
            return None

        # Calculate price changes
        changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent_changes = changes[-(period):]

        # Separate gains and losses
        gains = [c for c in recent_changes if c > 0]
        losses = [abs(c) for c in recent_changes if c < 0]

        # Calculate average gains and losses
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0

        # Calculate RS and RSI
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_atr(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14,
    ) -> Optional[float]:
        """
        Calculate Average True Range

        Args:
            highs: List of high prices
            lows: List of low prices
            closes: List of closing prices
            period: Lookback period

        Returns:
            ATR value or None
        """
        if len(highs) < period + 1:
            return None

        true_ranges = []
        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1]

            # True range is max of:
            # 1. High - Low (current bar range)
            # 2. abs(High - Previous Close)
            # 3. abs(Low - Previous Close)
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        # Average of recent true ranges
        recent_tr = true_ranges[-period:]
        return statistics.mean(recent_tr) if recent_tr else None

    def _calculate_volume_spike(
        self, volumes: List[float], lookback: int = None
    ) -> Tuple[bool, float]:
        """
        Check for volume spike

        Args:
            volumes: List of volume values
            lookback: Bars for average calculation

        Returns:
            Tuple of (is_spike, volume_ratio)
        """
        lookback = lookback or self.strategy_config.volume_lookback

        if len(volumes) < lookback + 1:
            return False, 1.0

        current_vol = volumes[-1]
        avg_vol = statistics.mean(volumes[-(lookback + 1) : -1])

        if avg_vol <= 0:
            return False, 1.0

        ratio = current_vol / avg_vol
        is_spike = ratio >= self.strategy_config.volume_spike_multiplier

        return is_spike, ratio

    # =========================================================================
    # ANALYSIS IMPLEMENTATION
    # =========================================================================

    async def analyze(self, symbol: str, data: Dict[str, Any]) -> AnalysisResult:
        """
        Analyze market conditions for mean reversion opportunities

        Evaluates:
        1. Bollinger Band position and width
        2. RSI overbought/oversold condition
        3. Volume for confirmation
        4. Overall market condition assessment

        Args:
            symbol: Trading symbol
            data: Market data containing candles and indicators

        Returns:
            AnalysisResult with mean reversion assessment
        """
        # Extract data
        candles = data.get("candles", [])
        if not candles or len(candles) < self.metadata.required_data_history_bars:
            logger.warning(f"Insufficient data for {symbol}: {len(candles)} candles")
            return AnalysisResult(
                symbol=symbol,
                condition=MarketCondition.UNKNOWN,
                confidence=0.0,
                recommendation="no_action",
            )

        # Extract OHLCV arrays
        opens = [float(c.get("open", c.get("o", 0))) for c in candles]
        highs = [float(c.get("high", c.get("h", 0))) for c in candles]
        lows = [float(c.get("low", c.get("l", 0))) for c in candles]
        closes = [float(c.get("close", c.get("c", 0))) for c in candles]
        volumes = [float(c.get("volume", c.get("v", 0))) for c in candles]

        current_price = closes[-1]

        # Calculate indicators
        bb = self._calculate_bollinger_bands(closes)
        rsi = self._calculate_rsi(closes)
        atr = self._calculate_atr(highs, lows, closes)
        has_volume_spike, volume_ratio = self._calculate_volume_spike(volumes)

        # Pre-calculated indicators from data (if available)
        indicators = data.get("indicators", {})
        if not rsi and "rsi" in indicators:
            rsi = indicators["rsi"]

        # Default RSI if calculation failed
        if rsi is None:
            rsi = 50.0

        # Assess market condition
        condition = self._assess_market_condition(current_price, bb, rsi, volume_ratio)

        # Determine trend (for context)
        trend_direction = "neutral"
        if rsi < 40:
            trend_direction = "bearish"
        elif rsi > 60:
            trend_direction = "bullish"

        # Calculate trend strength (deviation from mean)
        if bb["middle"] and bb["middle"] > 0:
            deviation_pct = abs(current_price - bb["middle"]) / bb["middle"] * 100
            trend_strength = min(100, deviation_pct * 20)  # Scale to 0-100
        else:
            trend_strength = 0.0

        # Build indicator dictionary
        indicator_values = {
            "bb_upper": bb["upper"],
            "bb_middle": bb["middle"],
            "bb_lower": bb["lower"],
            "bb_width_pct": bb["width_pct"],
            "rsi": rsi,
            "atr": atr,
            "volume_ratio": volume_ratio,
            "has_volume_spike": has_volume_spike,
        }

        # Calculate confidence based on signal clarity
        confidence = self._calculate_analysis_confidence(
            current_price, bb, rsi, has_volume_spike
        )

        # Determine recommendation
        recommendation = self._get_recommendation(
            current_price, bb, rsi, has_volume_spike
        )

        # Identify support/resistance levels
        support_levels = []
        resistance_levels = []
        if bb["lower"]:
            support_levels.append(bb["lower"])
        if bb["middle"]:
            support_levels.append(bb["middle"] * 0.99)
            resistance_levels.append(bb["middle"] * 1.01)
        if bb["upper"]:
            resistance_levels.append(bb["upper"])

        # Create analysis result
        result = AnalysisResult(
            symbol=symbol,
            condition=condition,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            volatility=bb["width_pct"] or 0.0,
            volatility_percentile=50.0,  # Would need historical data
            atr_value=atr,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
            indicators=indicator_values,
            confidence=confidence,
            recommendation=recommendation,
        )

        # Cache result
        self._last_analysis[symbol] = result

        logger.debug(
            f"Analysis {symbol}: condition={condition.value}, "
            f"RSI={rsi:.1f}, BB_width={bb['width_pct']:.1f}%, "
            f"confidence={confidence:.2f}, rec={recommendation}"
        )

        return result

    def _assess_market_condition(
        self,
        price: float,
        bb: Dict[str, Optional[float]],
        rsi: float,
        volume_ratio: float,
    ) -> MarketCondition:
        """Assess current market condition for mean reversion"""
        if bb["upper"] is None or bb["lower"] is None:
            return MarketCondition.UNKNOWN

        bb_width = bb.get("width_pct", 0)

        # Check for extreme volatility
        if bb_width > self.strategy_config.max_bb_width_pct:
            return MarketCondition.HIGH_VOLATILITY

        # Check for squeeze (low volatility)
        if bb_width < self.strategy_config.min_bb_width_pct:
            return MarketCondition.LOW_VOLATILITY

        # Check for strong trend (RSI extreme)
        if rsi > 80:
            return MarketCondition.STRONG_UPTREND
        elif rsi < 20:
            return MarketCondition.STRONG_DOWNTREND

        # Check position relative to bands
        if price >= bb["upper"]:
            return MarketCondition.UPTREND
        elif price <= bb["lower"]:
            return MarketCondition.DOWNTREND

        # Default: ranging market
        return MarketCondition.RANGING

    def _calculate_analysis_confidence(
        self,
        price: float,
        bb: Dict[str, Optional[float]],
        rsi: float,
        has_volume_spike: bool,
    ) -> float:
        """Calculate confidence in analysis"""
        confidence = 0.5  # Base confidence

        if bb["upper"] is None or bb["lower"] is None:
            return 0.0

        # Add confidence for RSI extremes
        if rsi < 30 or rsi > 70:
            confidence += 0.15
        if rsi < 20 or rsi > 80:
            confidence += 0.10

        # Add confidence for BB touches
        touch_threshold = self.strategy_config.bb_touch_threshold
        if bb["upper"] and price >= bb["upper"] * (1 - touch_threshold):
            confidence += 0.15
        elif bb["lower"] and price <= bb["lower"] * (1 + touch_threshold):
            confidence += 0.15

        # Add confidence for volume spike
        if has_volume_spike:
            confidence += 0.10

        return min(1.0, confidence)

    def _get_recommendation(
        self,
        price: float,
        bb: Dict[str, Optional[float]],
        rsi: float,
        has_volume_spike: bool,
    ) -> str:
        """Get trading recommendation"""
        if bb["lower"] is None or bb["upper"] is None:
            return "no_action"

        # Check BB width for tradability
        bb_width = bb.get("width_pct", 0)
        if bb_width < self.strategy_config.min_bb_width_pct:
            return "no_action"  # Squeeze - wait
        if bb_width > self.strategy_config.max_bb_width_pct:
            return "no_action"  # Too volatile

        touch_threshold = self.strategy_config.bb_touch_threshold

        # Long signal conditions
        if (
            price <= bb["lower"] * (1 + touch_threshold)
            and rsi <= self.strategy_config.rsi_oversold
        ):
            return "long"

        # Short signal conditions
        if (
            price >= bb["upper"] * (1 - touch_threshold)
            and rsi >= self.strategy_config.rsi_overbought
        ):
            return "short"

        # Exit conditions
        if (
            rsi >= self.strategy_config.rsi_neutral_low
            and rsi <= self.strategy_config.rsi_neutral_high
        ):
            return "exit_to_neutral"

        return "no_action"

    # =========================================================================
    # SIGNAL GENERATION
    # =========================================================================

    async def generate_signals(
        self, symbol: str, analysis: AnalysisResult, current_price: Decimal
    ) -> List[StrategySignal]:
        """
        Generate trading signals based on mean reversion analysis

        Args:
            symbol: Trading symbol
            analysis: Analysis result from analyze()
            current_price: Current market price

        Returns:
            List of StrategySignal objects
        """
        signals = []

        # Check if recommendation suggests action
        if analysis.recommendation == "no_action":
            return signals

        # Check confidence threshold
        if analysis.confidence < self.strategy_config.min_confidence:
            logger.debug(
                f"Signal skipped for {symbol}: "
                f"confidence {analysis.confidence:.2f} below threshold"
            )
            return signals

        # Check signal cooldown
        current_bar = self._current_bar.get(symbol, 0)
        last_signal_bar = self._last_signal_bar.get(symbol, -100)
        if (
            current_bar - last_signal_bar
            < self.strategy_config.min_bars_between_signals
        ):
            logger.debug(f"Signal skipped for {symbol}: cooldown active")
            return signals

        # Get indicator values from analysis
        indicators = analysis.indicators
        bb_lower = indicators.get("bb_lower")
        bb_middle = indicators.get("bb_middle")
        bb_upper = indicators.get("bb_upper")
        atr = indicators.get("atr")
        rsi = indicators.get("rsi", 50)

        # Calculate stop loss and take profit
        if self.strategy_config.use_atr_stops and atr:
            # ATR-based stops
            sl_distance = atr * self.strategy_config.atr_stop_multiplier
            sl_pct = (sl_distance / float(current_price)) * 100
        else:
            # Fixed percentage stops
            sl_pct = self.strategy_config.default_stop_loss_pct

        # Take profit targets middle band (mean)
        if bb_middle:
            tp_distance = abs(float(current_price) - bb_middle)
            tp_pct = (tp_distance / float(current_price)) * 100
            tp_pct = max(tp_pct, self.strategy_config.default_take_profit_pct * 0.5)
        else:
            tp_pct = self.strategy_config.default_take_profit_pct

        # Generate signal based on recommendation
        if analysis.recommendation == "long":
            signal = create_signal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                signal_type=SignalType.ENTRY_LONG,
                entry_price=current_price,
                stop_loss_pct=sl_pct,
                take_profit_pct=tp_pct,
                confidence=analysis.confidence,
                reasoning=self._build_reasoning("long", indicators),
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["bollinger_bands", "rsi", "volume"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "HIGH" if rsi < 25 else "MEDIUM"

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
                reasoning=self._build_reasoning("short", indicators),
            )
            signal.market_condition = analysis.condition
            signal.timeframe = self.metadata.primary_timeframe
            signal.indicators_used = ["bollinger_bands", "rsi", "volume"]
            signal.expiry_seconds = self.strategy_config.signal_expiry_seconds
            signal.urgency = "HIGH" if rsi > 75 else "MEDIUM"

            signals.append(signal)
            self._last_signal_bar[symbol] = current_bar

        logger.info(
            f"Generated {len(signals)} signal(s) for {symbol}: "
            f"[{', '.join(s.signal_type.value for s in signals)}]"
        )

        return signals

    def _build_reasoning(self, direction: str, indicators: Dict[str, Any]) -> str:
        """Build explanation for the signal"""
        rsi = indicators.get("rsi", 50)
        bb_width = indicators.get("bb_width_pct", 0)
        volume_ratio = indicators.get("volume_ratio", 1.0)

        parts = []

        if direction == "long":
            parts.append("Mean reversion long entry")
            parts.append(f"RSI oversold at {rsi:.1f}")
            parts.append("Price touching lower Bollinger Band")
        else:
            parts.append("Mean reversion short entry")
            parts.append(f"RSI overbought at {rsi:.1f}")
            parts.append("Price touching upper Bollinger Band")

        parts.append(f"BB width: {bb_width:.1f}%")

        if volume_ratio > 1.5:
            parts.append(f"Volume spike: {volume_ratio:.1f}x average")

        return ". ".join(parts)

    # =========================================================================
    # POSITION SIZING
    # =========================================================================

    def calculate_position_size(
        self,
        signal: StrategySignal,
        available_capital: float,
        risk_per_trade_pct: Optional[float] = None,
    ) -> Tuple[Decimal, float]:
        """
        Calculate optimal position size for mean reversion trade

        Uses risk-based position sizing:
        Position Value = (Capital * Risk%) / Stop Loss Distance

        Args:
            signal: Trading signal
            available_capital: Available capital for trading
            risk_per_trade_pct: Risk per trade as % (overrides default)

        Returns:
            Tuple of (position_size in base currency, risk_amount in quote)
        """
        # Determine risk percentage
        risk_pct = risk_per_trade_pct or self.strategy_config.risk_per_trade_pct

        # Calculate risk amount
        risk_amount = available_capital * (risk_pct / 100)

        # Get stop loss percentage
        stop_loss_pct = (
            signal.stop_loss_pct or self.strategy_config.default_stop_loss_pct
        )

        if stop_loss_pct <= 0:
            stop_loss_pct = self.strategy_config.default_stop_loss_pct

        # Calculate position value based on stop loss
        # If we risk X and SL is Y%, position value = X / (Y/100)
        position_value = risk_amount / (stop_loss_pct / 100)

        # Apply maximum position limit
        max_position_value = available_capital * (
            self.strategy_config.max_position_pct / 100
        )
        position_value = min(position_value, max_position_value)

        # Calculate quantity
        if signal.entry_price and signal.entry_price > 0:
            quantity = Decimal(str(position_value)) / signal.entry_price
        else:
            quantity = Decimal("0")

        # Round to reasonable precision (8 decimal places)
        quantity = quantity.quantize(Decimal("0.00000001"))

        logger.debug(
            f"Position size calculated: {quantity} units, "
            f"value=${position_value:.2f}, risk=${risk_amount:.2f}"
        )

        return quantity, risk_amount

    # =========================================================================
    # LIFECYCLE METHODS
    # =========================================================================

    async def on_initialize(self) -> None:
        """Initialize strategy-specific resources"""
        await super().on_initialize()

        # Initialize bar tracking
        for symbol in self.metadata.supported_symbols:
            self._last_signal_bar[symbol] = -100
            self._current_bar[symbol] = 0

        logger.info(
            f"MeanReversionStrategy ready for {len(self.metadata.supported_symbols)} symbols"
        )

    async def on_start(self) -> None:
        """Start trading"""
        await super().on_start()
        logger.info("MeanReversionStrategy started trading")

    async def on_stop(self) -> None:
        """Stop trading"""
        await super().on_stop()
        self._last_signal_bar.clear()
        self._current_bar.clear()
        logger.info("MeanReversionStrategy stopped")

    def update_bar_count(self, symbol: str) -> None:
        """Update bar count for a symbol (call on new candle)"""
        self._current_bar[symbol] = self._current_bar.get(symbol, 0) + 1

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update strategy configuration at runtime

        Args:
            new_config: New configuration values
        """
        for key, value in new_config.items():
            if hasattr(self.strategy_config, key):
                setattr(self.strategy_config, key, value)
                logger.info(f"Updated config {key} = {value}")

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        return self.strategy_config.to_dict()


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_mean_reversion_strategy(
    symbols: Optional[List[str]] = None,
    timeframe: str = "60",
    config_overrides: Optional[Dict[str, Any]] = None,
) -> MeanReversionStrategy:
    """
    Factory function to create a Mean Reversion strategy instance

    Args:
        symbols: List of trading symbols
        timeframe: Trading timeframe in minutes
        config_overrides: Configuration overrides

    Returns:
        Configured MeanReversionStrategy instance
    """
    # Create config with defaults
    config = MeanReversionConfig()

    # Apply overrides
    if config_overrides:
        for key, value in config_overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

    # Create strategy
    strategy = MeanReversionStrategy(
        strategy_config=config,
        supported_symbols=symbols or [],
        primary_timeframe=timeframe,
    )

    return strategy
