"""
Regime-Based Strategy Selector for Hurst Exponent Market Analysis

Research Foundation:
- Mandelbrot's Fractal Market Hypothesis (1997)
- Peters' Fractal Market Analysis (1994)
- Adaptive Market Hypothesis (Lo, 2004)

Purpose:
- Select optimal strategy parameters based on detected market regime
- Adjust trading signals for regime-appropriate execution
- Manage position sizing based on market predictability
- Configure stop-loss and take-profit multipliers per regime

Integration:
- Works with HurstExponentCalculator from hurst_exponent.py
- Uses MarketRegimeType for regime classification
- Provides StrategyType-specific parameters

Regime-Strategy Mapping:
- TRENDING: Trend-following with wider stops, longer holds, momentum signals
- MEAN_REVERTING: Mean-reversion with tighter stops, shorter holds, RSI extremes
- RANDOM_WALK: Reduced exposure, skip low confidence, wait for clarity
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

# Import from the existing Hurst Exponent module
from .hurst_exponent import MarketRegimeType, StrategyType, HurstResult

# Configure module-level logger for tracking strategy selection decisions
logger = logging.getLogger(__name__)


class SignalType(Enum):
    """
    Trading signal types that can be adjusted based on market regime

    Categorization helps determine which signals are appropriate for each regime:
    - MOMENTUM signals work best in TRENDING regimes
    - REVERSAL signals work best in MEAN_REVERTING regimes
    - BREAKOUT signals work in both but with different parameters
    """
    # Momentum-based signals (trend-following)
    MOMENTUM_BULLISH = "momentum_bullish"       # Price moving up with strength
    MOMENTUM_BEARISH = "momentum_bearish"       # Price moving down with strength
    MACD_CROSSOVER = "macd_crossover"           # MACD line crosses signal line
    EMA_CROSSOVER = "ema_crossover"             # Fast EMA crosses slow EMA

    # Mean-reversion signals (counter-trend)
    RSI_OVERSOLD = "rsi_oversold"               # RSI below 30
    RSI_OVERBOUGHT = "rsi_overbought"           # RSI above 70
    BOLLINGER_BOUNCE = "bollinger_bounce"       # Price touches Bollinger band
    MEAN_REVERT = "mean_revert"                 # Price far from moving average

    # Breakout signals (regime-dependent)
    BREAKOUT_BULLISH = "breakout_bullish"       # Price breaks resistance
    BREAKOUT_BEARISH = "breakout_bearish"       # Price breaks support
    VOLUME_SPIKE = "volume_spike"               # Unusual volume activity

    # Neutral signals
    NEUTRAL = "neutral"                         # No clear direction


@dataclass
class RegimeStrategyConfig:
    """
    Configuration parameters for strategy execution in a specific market regime

    Each regime type has optimal parameters that maximize trading performance:
    - Position sizing affects risk exposure
    - Stop-loss multipliers control downside protection
    - Take-profit multipliers set profit targets
    - Signal preferences filter for regime-appropriate signals

    Attributes:
        regime: Market regime this configuration applies to
        position_size_multiplier: Scale position size (0.0-1.0), lower for uncertain regimes
        stop_loss_multiplier: Adjust stop distance (wider for trends, tighter for reversions)
        take_profit_multiplier: Adjust profit target distance
        min_signal_confidence: Minimum confidence required to act on signal
        preferred_signals: Signal types that work well in this regime
        avoid_signals: Signal types to ignore in this regime
        max_hold_periods: Maximum candles to hold position (shorter for mean-reversion)
        allow_scaling: Whether to allow position scaling in this regime
        description: Human-readable description of the strategy approach
    """
    # Core regime identifier
    regime: MarketRegimeType

    # Position sizing control (0.0 = don't trade, 1.0 = full size)
    position_size_multiplier: float = 1.0

    # Stop-loss and take-profit adjustments
    stop_loss_multiplier: float = 1.0       # 1.0 = standard, >1.0 = wider, <1.0 = tighter
    take_profit_multiplier: float = 1.0     # 1.0 = standard, >1.0 = larger targets

    # Signal filtering
    min_signal_confidence: float = 0.5      # Minimum confidence to act (0.0-1.0)

    # Preferred and avoided signal types
    preferred_signals: List[SignalType] = field(default_factory=list)
    avoid_signals: List[SignalType] = field(default_factory=list)

    # Trade management parameters
    max_hold_periods: int = 100             # Maximum candles to hold
    allow_scaling: bool = True              # Allow adding to position
    trailing_stop_enabled: bool = False     # Use trailing stops

    # Documentation
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert configuration to dictionary for serialization

        Returns:
            Dictionary representation of all configuration parameters
        """
        return {
            "regime": self.regime.value,
            "position_size_multiplier": round(self.position_size_multiplier, 4),
            "stop_loss_multiplier": round(self.stop_loss_multiplier, 4),
            "take_profit_multiplier": round(self.take_profit_multiplier, 4),
            "min_signal_confidence": round(self.min_signal_confidence, 4),
            "preferred_signals": [s.value for s in self.preferred_signals],
            "avoid_signals": [s.value for s in self.avoid_signals],
            "max_hold_periods": self.max_hold_periods,
            "allow_scaling": self.allow_scaling,
            "trailing_stop_enabled": self.trailing_stop_enabled,
            "description": self.description
        }


@dataclass
class TradingSignal:
    """
    Representation of a trading signal to be adjusted based on regime

    This dataclass captures all relevant information about a trading signal
    that may need regime-based adjustments before execution.

    Attributes:
        signal_type: Type of signal (momentum, reversal, breakout, etc.)
        direction: Trade direction ('long' or 'short')
        confidence: Signal strength/confidence (0.0-1.0)
        entry_price: Suggested entry price
        stop_loss: Suggested stop-loss price
        take_profit: Suggested take-profit price
        position_size: Suggested position size (before regime adjustment)
        timestamp: When the signal was generated
        metadata: Additional signal-specific information
    """
    signal_type: SignalType
    direction: str                          # 'long' or 'short'
    confidence: float                       # 0.0 to 1.0
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: float = 1.0              # Base position size
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary for logging and serialization"""
        return {
            "signal_type": self.signal_type.value,
            "direction": self.direction,
            "confidence": round(self.confidence, 4),
            "entry_price": round(self.entry_price, 8),
            "stop_loss": round(self.stop_loss, 8) if self.stop_loss else None,
            "take_profit": round(self.take_profit, 8) if self.take_profit else None,
            "position_size": round(self.position_size, 8),
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class AdjustedSignal:
    """
    Signal after regime-based adjustments have been applied

    Contains the original signal plus all regime-specific modifications
    and the reasoning behind each adjustment.

    Attributes:
        original_signal: The input signal before adjustments
        regime: Market regime used for adjustments
        adjusted_stop_loss: Stop-loss after regime multiplier applied
        adjusted_take_profit: Take-profit after regime multiplier applied
        adjusted_position_size: Position size after regime multiplier applied
        should_execute: Whether the signal should be executed
        skip_reason: If not executing, why
        adjustments_made: List of adjustments applied
        regime_confidence: Confidence in the regime detection
    """
    original_signal: TradingSignal
    regime: MarketRegimeType
    adjusted_stop_loss: Optional[float]
    adjusted_take_profit: Optional[float]
    adjusted_position_size: float
    should_execute: bool
    skip_reason: Optional[str] = None
    adjustments_made: List[str] = field(default_factory=list)
    regime_confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert adjusted signal to dictionary"""
        return {
            "original_signal": self.original_signal.to_dict(),
            "regime": self.regime.value,
            "adjusted_stop_loss": round(self.adjusted_stop_loss, 8) if self.adjusted_stop_loss else None,
            "adjusted_take_profit": round(self.adjusted_take_profit, 8) if self.adjusted_take_profit else None,
            "adjusted_position_size": round(self.adjusted_position_size, 8),
            "should_execute": self.should_execute,
            "skip_reason": self.skip_reason,
            "adjustments_made": self.adjustments_made,
            "regime_confidence": round(self.regime_confidence, 4)
        }


class RegimeStrategySelector:
    """
    Regime-Based Strategy Selector for Adaptive Trading

    RESEARCH-BACKED IMPLEMENTATION:
    Implements adaptive trading strategy selection based on Hurst Exponent
    market regime detection. Different market regimes require fundamentally
    different trading approaches:

    TRENDING MARKETS (H > 0.55):
    - Use trend-following strategies (momentum, breakouts)
    - Wider stop-losses to avoid being stopped out during retracements
    - Larger take-profit targets to capture extended moves
    - Full position sizing to maximize gains from persistence
    - Enable trailing stops to lock in profits

    MEAN-REVERTING MARKETS (H < 0.45):
    - Use mean-reversion strategies (RSI extremes, Bollinger bounces)
    - Tighter stop-losses as prices should revert quickly
    - Smaller take-profit targets (aim for mean, not beyond)
    - Slightly reduced position sizing due to faster reversals
    - Disable trailing stops, use fixed targets

    RANDOM WALK MARKETS (0.45 <= H <= 0.55):
    - Reduce trading activity (no exploitable pattern)
    - Significantly reduced position sizing
    - Only act on high-confidence signals
    - Consider sitting on sidelines

    Usage:
        # Create selector with default or custom configs
        selector = RegimeStrategySelector()

        # Get strategy parameters for a regime
        params = selector.get_strategy_for_regime(MarketRegimeType.TRENDING)

        # Adjust a signal based on regime
        signal = TradingSignal(signal_type=SignalType.MOMENTUM_BULLISH, ...)
        adjusted = selector.adjust_signal_for_regime(signal, hurst_result)

        # Check if we should trade
        should_trade = selector.should_trade_in_regime(
            MarketRegimeType.RANDOM_WALK,
            confidence=0.6
        )
    """

    # Default configuration for each regime type
    DEFAULT_TRENDING_CONFIG = RegimeStrategyConfig(
        regime=MarketRegimeType.TRENDING,
        position_size_multiplier=1.0,           # Full size - trends are exploitable
        stop_loss_multiplier=1.5,               # Wider stops - avoid whipsaws
        take_profit_multiplier=2.0,             # Larger targets - capture full move
        min_signal_confidence=0.5,              # Standard confidence threshold
        preferred_signals=[                      # Momentum signals work best
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.MACD_CROSSOVER,
            SignalType.EMA_CROSSOVER,
            SignalType.BREAKOUT_BULLISH,
            SignalType.BREAKOUT_BEARISH
        ],
        avoid_signals=[                          # Mean-reversion signals fail in trends
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.MEAN_REVERT
        ],
        max_hold_periods=200,                   # Hold longer for trend capture
        allow_scaling=True,                     # Can add to winning positions
        trailing_stop_enabled=True,             # Trailing stops work well
        description="Trend-following mode: Ride the trend with momentum signals, "
                   "wider stops to survive retracements, and trailing stops to capture gains."
    )

    DEFAULT_MEAN_REVERTING_CONFIG = RegimeStrategyConfig(
        regime=MarketRegimeType.MEAN_REVERTING,
        position_size_multiplier=0.9,           # Slightly reduced - faster reversals
        stop_loss_multiplier=0.8,               # Tighter stops - quick reversals expected
        take_profit_multiplier=1.2,             # Smaller targets - aim for mean
        min_signal_confidence=0.6,              # Higher confidence needed
        preferred_signals=[                      # Reversion signals work best
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.BOLLINGER_BOUNCE,
            SignalType.MEAN_REVERT
        ],
        avoid_signals=[                          # Trend signals fail in reversions
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.BREAKOUT_BULLISH,
            SignalType.BREAKOUT_BEARISH
        ],
        max_hold_periods=50,                    # Shorter holds for quick reversals
        allow_scaling=False,                    # Don't add to positions
        trailing_stop_enabled=False,            # Fixed targets work better
        description="Mean-reversion mode: Trade oversold/overbought extremes with "
                   "tight stops and quick profit-taking as price reverts to mean."
    )

    DEFAULT_RANDOM_WALK_CONFIG = RegimeStrategyConfig(
        regime=MarketRegimeType.RANDOM_WALK,
        position_size_multiplier=0.5,           # Half size - market is unpredictable
        stop_loss_multiplier=1.0,               # Standard stops
        take_profit_multiplier=1.0,             # Standard targets
        min_signal_confidence=0.8,              # Only high-confidence signals
        preferred_signals=[                      # Very few preferred signals
            SignalType.VOLUME_SPIKE,            # Only trade on unusual activity
        ],
        avoid_signals=[                          # Avoid most signals
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.MACD_CROSSOVER,
            SignalType.EMA_CROSSOVER,
            SignalType.MEAN_REVERT
        ],
        max_hold_periods=25,                    # Short holds only
        allow_scaling=False,                    # No position scaling
        trailing_stop_enabled=False,            # No trailing stops
        description="Random walk mode: Market is unpredictable. Reduce exposure, "
                   "only trade on very high confidence signals, consider waiting."
    )

    def __init__(
        self,
        trending_config: Optional[RegimeStrategyConfig] = None,
        mean_reverting_config: Optional[RegimeStrategyConfig] = None,
        random_walk_config: Optional[RegimeStrategyConfig] = None,
        min_confidence_to_trade: float = 0.5
    ):
        """
        Initialize the Regime Strategy Selector

        Args:
            trending_config: Custom configuration for trending regime.
                           Uses DEFAULT_TRENDING_CONFIG if not provided.
            mean_reverting_config: Custom configuration for mean-reverting regime.
                                  Uses DEFAULT_MEAN_REVERTING_CONFIG if not provided.
            random_walk_config: Custom configuration for random walk regime.
                              Uses DEFAULT_RANDOM_WALK_CONFIG if not provided.
            min_confidence_to_trade: Global minimum confidence threshold (0.0-1.0)
                                    to consider any trading activity.
        """
        # Store configurations for each regime
        # Use provided configs or defaults
        self._configs: Dict[MarketRegimeType, RegimeStrategyConfig] = {
            MarketRegimeType.TRENDING: trending_config or self.DEFAULT_TRENDING_CONFIG,
            MarketRegimeType.MEAN_REVERTING: mean_reverting_config or self.DEFAULT_MEAN_REVERTING_CONFIG,
            MarketRegimeType.RANDOM_WALK: random_walk_config or self.DEFAULT_RANDOM_WALK_CONFIG
        }

        # Global minimum confidence threshold
        self._min_confidence_to_trade = min_confidence_to_trade

        # Log initialization with key parameters
        logger.info(
            f"RegimeStrategySelector initialized with configs: "
            f"trending_pos={self._configs[MarketRegimeType.TRENDING].position_size_multiplier}, "
            f"mean_rev_pos={self._configs[MarketRegimeType.MEAN_REVERTING].position_size_multiplier}, "
            f"random_pos={self._configs[MarketRegimeType.RANDOM_WALK].position_size_multiplier}, "
            f"min_confidence={self._min_confidence_to_trade}"
        )

    def get_strategy_for_regime(
        self,
        regime: MarketRegimeType
    ) -> Dict[str, Any]:
        """
        Get complete strategy parameters for a given market regime

        Returns all configuration parameters needed to execute trades
        in the specified market regime. This includes position sizing,
        stop-loss/take-profit multipliers, preferred signals, etc.

        Args:
            regime: The detected market regime type

        Returns:
            Dictionary containing all strategy parameters for the regime

        Example:
            params = selector.get_strategy_for_regime(MarketRegimeType.TRENDING)
            # Returns:
            # {
            #     'regime': 'trending',
            #     'position_size_multiplier': 1.0,
            #     'stop_loss_multiplier': 1.5,
            #     'take_profit_multiplier': 2.0,
            #     'preferred_signals': ['momentum_bullish', ...],
            #     ...
            # }
        """
        # Get the configuration for this regime
        config = self._configs.get(regime)

        if config is None:
            # This should never happen with proper MarketRegimeType enum
            logger.warning(f"Unknown regime type: {regime}, using RANDOM_WALK defaults")
            config = self._configs[MarketRegimeType.RANDOM_WALK]

        # Convert to dictionary and add metadata
        strategy_dict = config.to_dict()
        strategy_dict["strategy_type"] = self._get_strategy_type(regime).value
        strategy_dict["retrieved_at"] = datetime.now().isoformat()

        logger.debug(f"Strategy for {regime.value}: {strategy_dict}")

        return strategy_dict

    def _get_strategy_type(self, regime: MarketRegimeType) -> StrategyType:
        """
        Map regime to recommended strategy type

        Internal helper to get the StrategyType enum for a given regime.

        Args:
            regime: Market regime type

        Returns:
            Corresponding StrategyType
        """
        strategy_map = {
            MarketRegimeType.TRENDING: StrategyType.TREND_FOLLOWING,
            MarketRegimeType.MEAN_REVERTING: StrategyType.MEAN_REVERSION,
            MarketRegimeType.RANDOM_WALK: StrategyType.NEUTRAL
        }
        return strategy_map.get(regime, StrategyType.NEUTRAL)

    def adjust_signal_for_regime(
        self,
        signal: TradingSignal,
        hurst_result: HurstResult
    ) -> AdjustedSignal:
        """
        Adjust a trading signal based on the current market regime

        Takes a raw trading signal and applies regime-appropriate adjustments:
        - Scales position size based on regime confidence
        - Adjusts stop-loss distance using regime multiplier
        - Adjusts take-profit distance using regime multiplier
        - Filters signals that don't match the regime
        - Adds documentation of all adjustments made

        Args:
            signal: Original trading signal to be adjusted
            hurst_result: Result from Hurst Exponent calculation containing
                         regime type and confidence

        Returns:
            AdjustedSignal with all regime-based modifications applied

        Example:
            signal = TradingSignal(
                signal_type=SignalType.MOMENTUM_BULLISH,
                direction='long',
                confidence=0.7,
                entry_price=50000.0,
                stop_loss=49000.0,
                take_profit=52000.0,
                position_size=0.1
            )
            adjusted = selector.adjust_signal_for_regime(signal, hurst_result)
            if adjusted.should_execute:
                execute_trade(adjusted)
        """
        # Get regime-specific configuration
        regime = hurst_result.regime
        config = self._configs[regime]

        # Track all adjustments made
        adjustments: List[str] = []

        # Determine if signal type is appropriate for this regime
        signal_appropriate = self._is_signal_appropriate_for_regime(
            signal.signal_type, regime
        )

        if not signal_appropriate:
            # Signal type doesn't match regime - skip execution
            logger.info(
                f"Signal {signal.signal_type.value} not appropriate for "
                f"{regime.value} regime - skipping"
            )
            return AdjustedSignal(
                original_signal=signal,
                regime=regime,
                adjusted_stop_loss=signal.stop_loss,
                adjusted_take_profit=signal.take_profit,
                adjusted_position_size=0.0,
                should_execute=False,
                skip_reason=f"Signal type {signal.signal_type.value} not suitable for {regime.value} regime",
                adjustments_made=["Signal filtered due to regime mismatch"],
                regime_confidence=hurst_result.confidence
            )

        # Check confidence thresholds
        if signal.confidence < config.min_signal_confidence:
            logger.info(
                f"Signal confidence {signal.confidence:.2f} below regime threshold "
                f"{config.min_signal_confidence:.2f} - skipping"
            )
            return AdjustedSignal(
                original_signal=signal,
                regime=regime,
                adjusted_stop_loss=signal.stop_loss,
                adjusted_take_profit=signal.take_profit,
                adjusted_position_size=0.0,
                should_execute=False,
                skip_reason=f"Signal confidence {signal.confidence:.2f} below threshold {config.min_signal_confidence:.2f}",
                adjustments_made=["Signal filtered due to low confidence"],
                regime_confidence=hurst_result.confidence
            )

        # Adjust position size
        adjusted_position_size = signal.position_size * config.position_size_multiplier
        if adjusted_position_size != signal.position_size:
            adjustments.append(
                f"Position size: {signal.position_size:.4f} -> {adjusted_position_size:.4f} "
                f"(multiplier: {config.position_size_multiplier})"
            )

        # Adjust stop-loss
        adjusted_stop_loss = self._adjust_stop_loss(
            signal.entry_price,
            signal.stop_loss,
            signal.direction,
            config.stop_loss_multiplier
        )
        if adjusted_stop_loss != signal.stop_loss and signal.stop_loss is not None:
            adjustments.append(
                f"Stop-loss: {signal.stop_loss:.8f} -> {adjusted_stop_loss:.8f} "
                f"(multiplier: {config.stop_loss_multiplier})"
            )

        # Adjust take-profit
        adjusted_take_profit = self._adjust_take_profit(
            signal.entry_price,
            signal.take_profit,
            signal.direction,
            config.take_profit_multiplier
        )
        if adjusted_take_profit != signal.take_profit and signal.take_profit is not None:
            adjustments.append(
                f"Take-profit: {signal.take_profit:.8f} -> {adjusted_take_profit:.8f} "
                f"(multiplier: {config.take_profit_multiplier})"
            )

        # Add regime-specific notes
        adjustments.append(f"Regime: {regime.value} (confidence: {hurst_result.confidence:.2f})")
        adjustments.append(f"Strategy: {config.description}")

        # Log the adjustments
        logger.info(
            f"Adjusted signal for {regime.value} regime: "
            f"pos_size={adjusted_position_size:.4f}, "
            f"sl={adjusted_stop_loss}, tp={adjusted_take_profit}"
        )

        return AdjustedSignal(
            original_signal=signal,
            regime=regime,
            adjusted_stop_loss=adjusted_stop_loss,
            adjusted_take_profit=adjusted_take_profit,
            adjusted_position_size=adjusted_position_size,
            should_execute=True,
            skip_reason=None,
            adjustments_made=adjustments,
            regime_confidence=hurst_result.confidence
        )

    def _adjust_stop_loss(
        self,
        entry_price: float,
        stop_loss: Optional[float],
        direction: str,
        multiplier: float
    ) -> Optional[float]:
        """
        Adjust stop-loss price based on regime multiplier

        For multiplier > 1.0: Stop moves further from entry (wider stop)
        For multiplier < 1.0: Stop moves closer to entry (tighter stop)

        Args:
            entry_price: Entry price for the trade
            stop_loss: Original stop-loss price
            direction: Trade direction ('long' or 'short')
            multiplier: Regime-specific stop-loss multiplier

        Returns:
            Adjusted stop-loss price, or None if input was None
        """
        if stop_loss is None:
            return None

        # Calculate original stop distance
        stop_distance = abs(entry_price - stop_loss)

        # Apply multiplier to distance
        adjusted_distance = stop_distance * multiplier

        # Calculate new stop-loss based on direction
        if direction.lower() == 'long':
            # For long: stop is below entry
            adjusted_stop = entry_price - adjusted_distance
        else:
            # For short: stop is above entry
            adjusted_stop = entry_price + adjusted_distance

        return adjusted_stop

    def _adjust_take_profit(
        self,
        entry_price: float,
        take_profit: Optional[float],
        direction: str,
        multiplier: float
    ) -> Optional[float]:
        """
        Adjust take-profit price based on regime multiplier

        For multiplier > 1.0: Target moves further from entry (larger target)
        For multiplier < 1.0: Target moves closer to entry (smaller target)

        Args:
            entry_price: Entry price for the trade
            take_profit: Original take-profit price
            direction: Trade direction ('long' or 'short')
            multiplier: Regime-specific take-profit multiplier

        Returns:
            Adjusted take-profit price, or None if input was None
        """
        if take_profit is None:
            return None

        # Calculate original profit distance
        profit_distance = abs(entry_price - take_profit)

        # Apply multiplier to distance
        adjusted_distance = profit_distance * multiplier

        # Calculate new take-profit based on direction
        if direction.lower() == 'long':
            # For long: target is above entry
            adjusted_tp = entry_price + adjusted_distance
        else:
            # For short: target is below entry
            adjusted_tp = entry_price - adjusted_distance

        return adjusted_tp

    def _is_signal_appropriate_for_regime(
        self,
        signal_type: SignalType,
        regime: MarketRegimeType
    ) -> bool:
        """
        Check if a signal type is appropriate for the given regime

        Signals can be:
        - Preferred: Signal is ideal for this regime
        - Neutral: Signal not in preferred or avoid lists
        - Avoided: Signal typically fails in this regime

        Args:
            signal_type: The type of signal being evaluated
            regime: The current market regime

        Returns:
            True if signal should be considered, False if it should be skipped
        """
        config = self._configs[regime]

        # Check if signal is in avoid list
        if signal_type in config.avoid_signals:
            return False

        # Signal is either preferred or neutral - both are acceptable
        return True

    def should_trade_in_regime(
        self,
        regime: MarketRegimeType,
        confidence: float
    ) -> bool:
        """
        Determine if trading is advisable given regime and confidence

        Considers:
        - Regime type (random walk is discouraged)
        - Regime detection confidence
        - Global minimum confidence threshold
        - Regime-specific confidence threshold

        Args:
            regime: Detected market regime type
            confidence: Confidence in the regime detection (0.0-1.0)

        Returns:
            True if trading is recommended, False otherwise

        Example:
            # Random walk with any confidence - discouraged
            selector.should_trade_in_regime(MarketRegimeType.RANDOM_WALK, 0.9)
            # Returns: False (random walk, even high confidence)

            # Trending with high confidence - recommended
            selector.should_trade_in_regime(MarketRegimeType.TRENDING, 0.8)
            # Returns: True
        """
        # Check global minimum confidence
        if confidence < self._min_confidence_to_trade:
            logger.info(
                f"Confidence {confidence:.2f} below global minimum "
                f"{self._min_confidence_to_trade:.2f} - trading not recommended"
            )
            return False

        # Get regime-specific config
        config = self._configs[regime]

        # Check regime-specific confidence threshold
        # Note: For random walk, we use a higher threshold
        effective_threshold = config.min_signal_confidence
        if regime == MarketRegimeType.RANDOM_WALK:
            # Random walk requires very high confidence to trade at all
            effective_threshold = max(effective_threshold, 0.85)

            # Only trade random walk if position multiplier > 0
            if config.position_size_multiplier <= 0:
                logger.info("Random walk regime with zero position size - trading not recommended")
                return False

        if confidence < effective_threshold:
            logger.info(
                f"Confidence {confidence:.2f} below regime threshold "
                f"{effective_threshold:.2f} for {regime.value} - trading not recommended"
            )
            return False

        logger.info(
            f"Trading recommended in {regime.value} regime with confidence {confidence:.2f}"
        )
        return True

    def get_position_size_multiplier(self, regime: MarketRegimeType) -> float:
        """
        Get the position size multiplier for a specific regime

        Position size multipliers adjust risk exposure based on
        regime predictability:
        - TRENDING: 1.0 (full size) - trends are exploitable
        - MEAN_REVERTING: 0.9 (slightly reduced) - faster reversals
        - RANDOM_WALK: 0.5 (half size) - market is unpredictable

        Args:
            regime: Market regime type

        Returns:
            Position size multiplier (0.0-1.0)

        Example:
            multiplier = selector.get_position_size_multiplier(MarketRegimeType.RANDOM_WALK)
            actual_size = base_position_size * multiplier  # Reduces risk
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])
        multiplier = config.position_size_multiplier

        logger.debug(f"Position size multiplier for {regime.value}: {multiplier}")

        return multiplier

    def get_stop_loss_multiplier(self, regime: MarketRegimeType) -> float:
        """
        Get the stop-loss distance multiplier for a specific regime

        Stop-loss multipliers adjust stop distance based on regime characteristics:
        - TRENDING: 1.5 (wider) - accommodate retracements without being stopped
        - MEAN_REVERTING: 0.8 (tighter) - quick stops if reversion doesn't happen
        - RANDOM_WALK: 1.0 (standard) - no regime-based adjustment

        Args:
            regime: Market regime type

        Returns:
            Stop-loss multiplier (applied to stop distance from entry)

        Example:
            multiplier = selector.get_stop_loss_multiplier(MarketRegimeType.TRENDING)
            # If original stop distance is $100, adjusted is $150 (1.5x wider)
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])
        multiplier = config.stop_loss_multiplier

        logger.debug(f"Stop-loss multiplier for {regime.value}: {multiplier}")

        return multiplier

    def get_take_profit_multiplier(self, regime: MarketRegimeType) -> float:
        """
        Get the take-profit distance multiplier for a specific regime

        Take-profit multipliers adjust target distance based on regime:
        - TRENDING: 2.0 (larger) - capture extended trend moves
        - MEAN_REVERTING: 1.2 (smaller) - aim for mean, not beyond
        - RANDOM_WALK: 1.0 (standard) - no regime-based adjustment

        Args:
            regime: Market regime type

        Returns:
            Take-profit multiplier (applied to profit target distance)

        Example:
            multiplier = selector.get_take_profit_multiplier(MarketRegimeType.TRENDING)
            # If original target is $200 profit, adjusted is $400 (2.0x larger)
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])
        multiplier = config.take_profit_multiplier

        logger.debug(f"Take-profit multiplier for {regime.value}: {multiplier}")

        return multiplier

    def get_preferred_signals(self, regime: MarketRegimeType) -> List[SignalType]:
        """
        Get list of signal types that work well in a specific regime

        Preferred signals are those with historically higher win rates
        and better risk-adjusted returns in the given regime.

        Args:
            regime: Market regime type

        Returns:
            List of preferred SignalType values for this regime

        Example:
            preferred = selector.get_preferred_signals(MarketRegimeType.TRENDING)
            # Returns: [MOMENTUM_BULLISH, MOMENTUM_BEARISH, MACD_CROSSOVER, ...]
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])
        return config.preferred_signals.copy()

    def get_avoided_signals(self, regime: MarketRegimeType) -> List[SignalType]:
        """
        Get list of signal types to avoid in a specific regime

        Avoided signals are those that historically underperform or
        generate false signals in the given regime.

        Args:
            regime: Market regime type

        Returns:
            List of SignalType values to avoid in this regime

        Example:
            avoid = selector.get_avoided_signals(MarketRegimeType.TRENDING)
            # Returns: [RSI_OVERSOLD, RSI_OVERBOUGHT, MEAN_REVERT]
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])
        return config.avoid_signals.copy()

    def get_regime_summary(self, regime: MarketRegimeType) -> Dict[str, Any]:
        """
        Get a comprehensive summary of regime-specific strategy settings

        Returns all relevant parameters for a regime in a single call,
        useful for logging, debugging, and UI display.

        Args:
            regime: Market regime type

        Returns:
            Dictionary with all regime strategy information
        """
        config = self._configs.get(regime, self._configs[MarketRegimeType.RANDOM_WALK])

        return {
            "regime": regime.value,
            "strategy_type": self._get_strategy_type(regime).value,
            "description": config.description,
            "parameters": {
                "position_size_multiplier": config.position_size_multiplier,
                "stop_loss_multiplier": config.stop_loss_multiplier,
                "take_profit_multiplier": config.take_profit_multiplier,
                "min_signal_confidence": config.min_signal_confidence,
                "max_hold_periods": config.max_hold_periods,
                "allow_scaling": config.allow_scaling,
                "trailing_stop_enabled": config.trailing_stop_enabled
            },
            "signal_preferences": {
                "preferred": [s.value for s in config.preferred_signals],
                "avoided": [s.value for s in config.avoid_signals]
            }
        }

    def get_all_regime_summaries(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summaries for all regime configurations

        Returns:
            Dictionary with regime names as keys and summaries as values
        """
        return {
            regime.value: self.get_regime_summary(regime)
            for regime in MarketRegimeType
        }

    def update_config(
        self,
        regime: MarketRegimeType,
        **kwargs
    ) -> None:
        """
        Update configuration parameters for a specific regime

        Allows runtime adjustment of strategy parameters without
        creating a new selector instance.

        Args:
            regime: Regime to update
            **kwargs: Parameters to update (position_size_multiplier,
                     stop_loss_multiplier, take_profit_multiplier, etc.)

        Example:
            # Make trending even more aggressive
            selector.update_config(
                MarketRegimeType.TRENDING,
                position_size_multiplier=1.2,
                take_profit_multiplier=2.5
            )
        """
        config = self._configs.get(regime)

        if config is None:
            logger.warning(f"Unknown regime {regime}, update ignored")
            return

        # Update allowed parameters
        allowed_params = {
            'position_size_multiplier', 'stop_loss_multiplier',
            'take_profit_multiplier', 'min_signal_confidence',
            'max_hold_periods', 'allow_scaling', 'trailing_stop_enabled'
        }

        for key, value in kwargs.items():
            if key in allowed_params:
                setattr(config, key, value)
                logger.info(f"Updated {regime.value}.{key} = {value}")
            else:
                logger.warning(f"Parameter {key} not allowed for update")

    def get_status(self) -> Dict[str, Any]:
        """
        Get current selector status and all configurations

        Returns comprehensive status information for monitoring
        and debugging purposes.

        Returns:
            Dictionary with selector status and configuration details
        """
        return {
            "name": "RegimeStrategySelector",
            "min_confidence_to_trade": self._min_confidence_to_trade,
            "configurations": self.get_all_regime_summaries(),
            "signal_types_supported": [s.value for s in SignalType],
            "regime_types_supported": [r.value for r in MarketRegimeType]
        }


# Module-level singleton instance
_instance: Optional[RegimeStrategySelector] = None


def get_regime_strategy_selector(
    force_new: bool = False,
    **kwargs
) -> RegimeStrategySelector:
    """
    Get the global RegimeStrategySelector instance (singleton pattern)

    Provides a convenient way to access a shared selector instance
    across the application. Creates a new instance on first call
    or if force_new is True.

    Args:
        force_new: If True, creates a new instance even if one exists
        **kwargs: Arguments passed to RegimeStrategySelector constructor
                 when creating a new instance

    Returns:
        RegimeStrategySelector instance

    Example:
        # First call creates the instance
        selector = get_regime_strategy_selector()

        # Subsequent calls return the same instance
        same_selector = get_regime_strategy_selector()
        assert selector is same_selector

        # Force create a new instance with custom config
        new_selector = get_regime_strategy_selector(
            force_new=True,
            min_confidence_to_trade=0.6
        )
    """
    global _instance

    if _instance is None or force_new:
        logger.info("Creating new RegimeStrategySelector instance")
        _instance = RegimeStrategySelector(**kwargs)

    return _instance


def create_regime_strategy_selector(
    trending_position_mult: float = 1.0,
    trending_stop_mult: float = 1.5,
    trending_tp_mult: float = 2.0,
    mean_rev_position_mult: float = 0.9,
    mean_rev_stop_mult: float = 0.8,
    mean_rev_tp_mult: float = 1.2,
    random_position_mult: float = 0.5,
    min_confidence: float = 0.5
) -> RegimeStrategySelector:
    """
    Factory function to create a RegimeStrategySelector with custom parameters

    Provides a convenient way to create a customized selector with
    common parameter adjustments without manually constructing
    RegimeStrategyConfig instances.

    Args:
        trending_position_mult: Position size multiplier for trending (default: 1.0)
        trending_stop_mult: Stop-loss multiplier for trending (default: 1.5)
        trending_tp_mult: Take-profit multiplier for trending (default: 2.0)
        mean_rev_position_mult: Position size multiplier for mean-reverting (default: 0.9)
        mean_rev_stop_mult: Stop-loss multiplier for mean-reverting (default: 0.8)
        mean_rev_tp_mult: Take-profit multiplier for mean-reverting (default: 1.2)
        random_position_mult: Position size multiplier for random walk (default: 0.5)
        min_confidence: Minimum confidence to trade (default: 0.5)

    Returns:
        Configured RegimeStrategySelector instance

    Example:
        # Create selector with more conservative random walk handling
        selector = create_regime_strategy_selector(
            random_position_mult=0.25,  # Even smaller positions in random walk
            min_confidence=0.7          # Higher confidence requirement
        )
    """
    # Create custom trending config
    trending_config = RegimeStrategyConfig(
        regime=MarketRegimeType.TRENDING,
        position_size_multiplier=trending_position_mult,
        stop_loss_multiplier=trending_stop_mult,
        take_profit_multiplier=trending_tp_mult,
        min_signal_confidence=0.5,
        preferred_signals=[
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.MACD_CROSSOVER,
            SignalType.EMA_CROSSOVER,
            SignalType.BREAKOUT_BULLISH,
            SignalType.BREAKOUT_BEARISH
        ],
        avoid_signals=[
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.MEAN_REVERT
        ],
        max_hold_periods=200,
        allow_scaling=True,
        trailing_stop_enabled=True,
        description="Trend-following mode with custom parameters"
    )

    # Create custom mean-reverting config
    mean_rev_config = RegimeStrategyConfig(
        regime=MarketRegimeType.MEAN_REVERTING,
        position_size_multiplier=mean_rev_position_mult,
        stop_loss_multiplier=mean_rev_stop_mult,
        take_profit_multiplier=mean_rev_tp_mult,
        min_signal_confidence=0.6,
        preferred_signals=[
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.BOLLINGER_BOUNCE,
            SignalType.MEAN_REVERT
        ],
        avoid_signals=[
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.BREAKOUT_BULLISH,
            SignalType.BREAKOUT_BEARISH
        ],
        max_hold_periods=50,
        allow_scaling=False,
        trailing_stop_enabled=False,
        description="Mean-reversion mode with custom parameters"
    )

    # Create custom random walk config
    random_config = RegimeStrategyConfig(
        regime=MarketRegimeType.RANDOM_WALK,
        position_size_multiplier=random_position_mult,
        stop_loss_multiplier=1.0,
        take_profit_multiplier=1.0,
        min_signal_confidence=0.8,
        preferred_signals=[SignalType.VOLUME_SPIKE],
        avoid_signals=[
            SignalType.MOMENTUM_BULLISH,
            SignalType.MOMENTUM_BEARISH,
            SignalType.RSI_OVERSOLD,
            SignalType.RSI_OVERBOUGHT,
            SignalType.MACD_CROSSOVER,
            SignalType.EMA_CROSSOVER,
            SignalType.MEAN_REVERT
        ],
        max_hold_periods=25,
        allow_scaling=False,
        trailing_stop_enabled=False,
        description="Random walk mode with custom parameters"
    )

    return RegimeStrategySelector(
        trending_config=trending_config,
        mean_reverting_config=mean_rev_config,
        random_walk_config=random_config,
        min_confidence_to_trade=min_confidence
    )
