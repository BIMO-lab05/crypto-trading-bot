"""
ATR-Based Trailing Stop Module
Purpose: Dynamic trailing stops that adapt to market volatility using ATR
Research Date: 2025-12-02

Key Concepts:
- ATR (Average True Range) measures market volatility
- Volatile markets require wider stops to avoid whipsaws
- Calm markets allow tighter stops to lock in profits
- Typical crypto ATR multipliers: 2.0-3.0

Features:
- Chandelier Exit: Trail from highest high (longs) / lowest low (shorts)
- Dynamic ATR multiplier based on volatility regime
- Activation threshold: Only trail after minimum profit achieved
- Step-based updates: Reduce noise by requiring minimum price movement
"""

import logging
from typing import Dict, Optional, Tuple
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

# Configure module logger
logger = logging.getLogger(__name__)


class VolatilityRegime(Enum):
    """
    Volatility regime classification for dynamic ATR multiplier adjustment.

    LOW: Calm market conditions - use tighter stops
    NORMAL: Standard market conditions - use base multiplier
    HIGH: Elevated volatility - use wider stops
    EXTREME: Crisis/flash crash conditions - use maximum protection
    """
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    EXTREME = "extreme"


class PositionSide(Enum):
    """Position direction for trailing stop calculations"""
    LONG = "long"
    SHORT = "short"


@dataclass
class ATRTrailingStopConfig:
    """
    Configuration for ATR-based trailing stop behavior.

    Research-backed defaults for cryptocurrency trading:
    - base_atr_multiplier: 2.5x ATR provides good balance
    - min_atr_multiplier: 1.5x prevents stops that are too tight
    - max_atr_multiplier: 4.0x maximum for extreme volatility
    - activation_profit_pct: 1.0% profit before trailing begins
    - step_pct: 0.5% minimum price movement to update stop

    Attributes:
        base_atr_multiplier: Standard distance from price in ATR units
        min_atr_multiplier: Minimum distance (for low volatility)
        max_atr_multiplier: Maximum distance (for extreme volatility)
        activation_profit_pct: Profit percentage required to activate trailing
        step_pct: Minimum price movement percentage to trigger stop update
        use_chandelier_exit: If True, trail from highest/lowest price
    """
    # ATR multiplier settings for stop distance calculation
    base_atr_multiplier: float = 2.5  # Standard distance from price in ATR units
    min_atr_multiplier: float = 1.5   # Minimum distance (tighter in calm markets)
    max_atr_multiplier: float = 4.0   # Maximum distance (wider in volatile markets)

    # Trailing stop activation and update thresholds
    activation_profit_pct: float = 1.0  # Only start trailing after 1% profit
    step_pct: float = 0.5               # Move stop only when price moves 0.5%

    # Chandelier exit mode (recommended for trend following)
    use_chandelier_exit: bool = True  # Trail from highest high for longs

    # Volatility regime multiplier adjustments
    volatility_multipliers: Dict[str, float] = field(default_factory=lambda: {
        VolatilityRegime.LOW.value: 0.8,      # 80% of base = tighter stops
        VolatilityRegime.NORMAL.value: 1.0,   # 100% of base = standard
        VolatilityRegime.HIGH.value: 1.3,     # 130% of base = wider stops
        VolatilityRegime.EXTREME.value: 1.6   # 160% of base = maximum protection
    })

    def to_dict(self) -> Dict:
        """Convert configuration to dictionary for serialization"""
        return {
            "base_atr_multiplier": self.base_atr_multiplier,
            "min_atr_multiplier": self.min_atr_multiplier,
            "max_atr_multiplier": self.max_atr_multiplier,
            "activation_profit_pct": self.activation_profit_pct,
            "step_pct": self.step_pct,
            "use_chandelier_exit": self.use_chandelier_exit,
            "volatility_multipliers": self.volatility_multipliers
        }


@dataclass
class PositionTrailState:
    """
    State tracking for an individual position's trailing stop.

    Maintains the historical high/low prices and current stop level
    for proper Chandelier Exit calculation.

    Attributes:
        symbol: Trading symbol (e.g., "BTCUSDT")
        entry_price: Original entry price for the position
        current_stop: Current trailing stop price level
        highest_price: Highest price since entry (for long positions)
        lowest_price: Lowest price since entry (for short positions)
        trail_activated: Whether trailing has been activated (profit threshold met)
        last_update: Timestamp of last stop update
        side: Position direction (LONG or SHORT)
        atr_at_entry: ATR value when position was opened
        total_updates: Number of times the stop has been updated
    """
    # Position identification
    symbol: str
    entry_price: float
    side: PositionSide

    # Current stop state
    current_stop: float

    # Price extremes for Chandelier Exit calculation
    highest_price: float = 0.0  # Track highest for long positions
    lowest_price: float = float('inf')  # Track lowest for short positions

    # Trailing activation status
    trail_activated: bool = False

    # Timestamps and metadata
    last_update: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Additional tracking
    atr_at_entry: float = 0.0
    total_updates: int = 0

    def __post_init__(self):
        """Initialize price extremes based on entry price"""
        # Set initial extremes to entry price if not provided
        if self.highest_price == 0.0:
            self.highest_price = self.entry_price
        if self.lowest_price == float('inf'):
            self.lowest_price = self.entry_price

    def update_price_extremes(self, current_price: float) -> bool:
        """
        Update highest/lowest price tracking.

        Args:
            current_price: Current market price

        Returns:
            True if extremes were updated, False otherwise
        """
        updated = False

        # Update highest price for long positions
        if current_price > self.highest_price:
            self.highest_price = current_price
            updated = True
            logger.debug(
                f"{self.symbol}: New high price {current_price:.4f} "
                f"(previous: {self.highest_price:.4f})"
            )

        # Update lowest price for short positions
        if current_price < self.lowest_price:
            self.lowest_price = current_price
            updated = True
            logger.debug(
                f"{self.symbol}: New low price {current_price:.4f} "
                f"(previous: {self.lowest_price:.4f})"
            )

        return updated

    def to_dict(self) -> Dict:
        """Convert state to dictionary for serialization/logging"""
        return {
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "side": self.side.value,
            "current_stop": self.current_stop,
            "highest_price": self.highest_price,
            "lowest_price": self.lowest_price,
            "trail_activated": self.trail_activated,
            "last_update": self.last_update.isoformat(),
            "created_at": self.created_at.isoformat(),
            "atr_at_entry": self.atr_at_entry,
            "total_updates": self.total_updates
        }


class ATRTrailingStop:
    """
    ATR-Based Trailing Stop Calculator

    Implements dynamic trailing stops that adapt to market volatility:
    - Uses ATR (Average True Range) to set stop distances
    - Wider stops in volatile markets to avoid whipsaws
    - Tighter stops in calm markets to lock in profits
    - Chandelier Exit mode: trails from highest high (longs) / lowest low (shorts)

    Research indicates ATR multipliers of 2.0-3.0 work well for crypto:
    - 2.0x ATR: Tighter stops, more frequent triggers, less drawdown tolerance
    - 2.5x ATR: Balanced approach (default)
    - 3.0x ATR: Wider stops, fewer triggers, more drawdown tolerance

    Usage:
        config = ATRTrailingStopConfig(base_atr_multiplier=2.5)
        trailing_stop = ATRTrailingStop(config)

        # Calculate initial stop
        stop_price = trailing_stop.calculate_initial_stop(
            entry_price=50000.0,
            atr_value=500.0,
            side=PositionSide.LONG
        )

        # Update trailing stop as price moves
        new_stop = trailing_stop.calculate_trailing_stop(
            current_price=52000.0,
            highest_price=52000.0,
            atr_value=480.0,
            side=PositionSide.LONG,
            current_stop=49000.0
        )
    """

    def __init__(self, config: Optional[ATRTrailingStopConfig] = None):
        """
        Initialize ATR Trailing Stop calculator.

        Args:
            config: Configuration object with multiplier and threshold settings.
                   If None, uses default configuration.
        """
        # Use provided config or create default
        self.config = config or ATRTrailingStopConfig()

        # Store active position states for tracking
        self._position_states: Dict[str, PositionTrailState] = {}

        # Statistics tracking
        self._stats = {
            "stops_calculated": 0,
            "stops_updated": 0,
            "stops_triggered": 0,
            "total_profit_protected": 0.0
        }

        logger.info(
            f"ATRTrailingStop initialized: "
            f"base_mult={self.config.base_atr_multiplier}x, "
            f"min_mult={self.config.min_atr_multiplier}x, "
            f"max_mult={self.config.max_atr_multiplier}x, "
            f"activation={self.config.activation_profit_pct}%, "
            f"chandelier={self.config.use_chandelier_exit}"
        )

    def calculate_initial_stop(
        self,
        entry_price: float,
        atr_value: float,
        side: PositionSide,
        volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    ) -> float:
        """
        Calculate the initial stop loss level for a new position.

        Uses ATR multiplied by the configured multiplier to set stop distance.
        Adjusts multiplier based on current volatility regime.

        Args:
            entry_price: Entry price for the position
            atr_value: Current ATR (Average True Range) value
            side: Position direction (LONG or SHORT)
            volatility_regime: Current market volatility classification

        Returns:
            Initial stop loss price level

        Example:
            LONG entry at $50,000 with ATR of $500 and 2.5x multiplier:
            Stop = $50,000 - ($500 * 2.5) = $48,750
        """
        # Get dynamic multiplier based on volatility regime
        multiplier = self.get_dynamic_atr_multiplier(volatility_regime)

        # Calculate stop distance in price terms
        stop_distance = atr_value * multiplier

        # Calculate stop price based on position side
        if side == PositionSide.LONG:
            # For LONG: stop is below entry price
            stop_price = entry_price - stop_distance
        else:
            # For SHORT: stop is above entry price
            stop_price = entry_price + stop_distance

        # Update statistics
        self._stats["stops_calculated"] += 1

        logger.info(
            f"Initial stop calculated: "
            f"entry={entry_price:.4f}, "
            f"atr={atr_value:.4f}, "
            f"multiplier={multiplier:.2f}x ({volatility_regime.value}), "
            f"stop={stop_price:.4f}, "
            f"side={side.value}"
        )

        return stop_price

    def calculate_trailing_stop(
        self,
        current_price: float,
        highest_price: float,
        atr_value: float,
        side: PositionSide,
        current_stop: float,
        volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    ) -> float:
        """
        Calculate updated trailing stop level based on price movement.

        Implements Chandelier Exit logic when configured:
        - For LONG positions: trails from highest high
        - For SHORT positions: trails from lowest low

        Args:
            current_price: Current market price
            highest_price: Highest price since entry (for longs) or
                          lowest price since entry (for shorts)
            atr_value: Current ATR value
            side: Position direction (LONG or SHORT)
            current_stop: Current trailing stop level
            volatility_regime: Current market volatility classification

        Returns:
            New trailing stop price level (may be same as current if no update)

        Note:
            Trailing stops only move in the favorable direction:
            - LONG stops only move UP (never down)
            - SHORT stops only move DOWN (never up)
        """
        # Get dynamic multiplier for current volatility
        multiplier = self.get_dynamic_atr_multiplier(volatility_regime)

        # Calculate stop distance from reference price
        stop_distance = atr_value * multiplier

        if side == PositionSide.LONG:
            if self.config.use_chandelier_exit:
                # Chandelier Exit: trail from highest high
                reference_price = highest_price
            else:
                # Simple trailing: trail from current price
                reference_price = current_price

            # Calculate new stop level
            new_stop = reference_price - stop_distance

            # Only update if new stop is higher (more protective)
            if new_stop > current_stop:
                logger.debug(
                    f"LONG trailing stop updated: "
                    f"{current_stop:.4f} -> {new_stop:.4f} "
                    f"(ref_price={reference_price:.4f}, atr={atr_value:.4f})"
                )
                return new_stop

        else:  # SHORT position
            if self.config.use_chandelier_exit:
                # Chandelier Exit: trail from lowest low
                # Note: highest_price param actually holds lowest_price for shorts
                reference_price = highest_price
            else:
                # Simple trailing: trail from current price
                reference_price = current_price

            # Calculate new stop level
            new_stop = reference_price + stop_distance

            # Only update if new stop is lower (more protective)
            if new_stop < current_stop:
                logger.debug(
                    f"SHORT trailing stop updated: "
                    f"{current_stop:.4f} -> {new_stop:.4f} "
                    f"(ref_price={reference_price:.4f}, atr={atr_value:.4f})"
                )
                return new_stop

        # No update needed - return current stop
        return current_stop

    def should_update_stop(
        self,
        current_price: float,
        entry_price: float,
        current_stop: float,
        side: PositionSide,
        last_update_price: Optional[float] = None
    ) -> bool:
        """
        Determine if the trailing stop should be updated.

        Checks two conditions:
        1. Profit threshold: Position must be in profit by at least activation_profit_pct
        2. Step threshold: Price must have moved by at least step_pct since last update

        Args:
            current_price: Current market price
            entry_price: Original entry price
            current_stop: Current trailing stop level
            side: Position direction (LONG or SHORT)
            last_update_price: Price at last stop update (for step calculation)

        Returns:
            True if stop should be updated, False otherwise
        """
        # Calculate current profit percentage
        if side == PositionSide.LONG:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100

        # Check 1: Is position in sufficient profit to activate trailing?
        if profit_pct < self.config.activation_profit_pct:
            logger.debug(
                f"Trail not activated: profit {profit_pct:.2f}% < "
                f"threshold {self.config.activation_profit_pct:.2f}%"
            )
            return False

        # Check 2: Has price moved enough since last update?
        if last_update_price is not None:
            price_change_pct = abs(
                (current_price - last_update_price) / last_update_price
            ) * 100

            if price_change_pct < self.config.step_pct:
                logger.debug(
                    f"Step threshold not met: "
                    f"change {price_change_pct:.2f}% < step {self.config.step_pct:.2f}%"
                )
                return False

        # All conditions met - should update stop
        logger.debug(
            f"Stop update conditions met: "
            f"profit={profit_pct:.2f}%, side={side.value}"
        )
        return True

    def get_dynamic_atr_multiplier(
        self,
        volatility_regime: VolatilityRegime
    ) -> float:
        """
        Get the ATR multiplier adjusted for current volatility regime.

        In volatile markets, wider stops prevent whipsaws.
        In calm markets, tighter stops lock in more profit.

        Args:
            volatility_regime: Current market volatility classification

        Returns:
            Adjusted ATR multiplier clamped to min/max bounds

        Example:
            Base multiplier: 2.5x
            HIGH volatility adjustment: 1.3x
            Result: 2.5 * 1.3 = 3.25x (clamped to max if > max_atr_multiplier)
        """
        # Get volatility adjustment factor
        regime_key = volatility_regime.value
        adjustment = self.config.volatility_multipliers.get(regime_key, 1.0)

        # Calculate adjusted multiplier
        adjusted_multiplier = self.config.base_atr_multiplier * adjustment

        # Clamp to configured bounds
        clamped_multiplier = max(
            self.config.min_atr_multiplier,
            min(adjusted_multiplier, self.config.max_atr_multiplier)
        )

        # Log if clamping occurred
        if clamped_multiplier != adjusted_multiplier:
            logger.debug(
                f"ATR multiplier clamped: "
                f"{adjusted_multiplier:.2f} -> {clamped_multiplier:.2f} "
                f"(regime={volatility_regime.value})"
            )

        return clamped_multiplier

    def update_position_stop(
        self,
        position: Dict,
        current_price: float,
        atr_value: float,
        volatility_regime: VolatilityRegime = VolatilityRegime.NORMAL
    ) -> Optional[float]:
        """
        Update trailing stop for a position, handling all state management.

        This is the main entry point for position stop management.
        Creates or updates PositionTrailState and returns new stop if updated.

        Args:
            position: Position dictionary with keys:
                     - symbol: Trading symbol
                     - entry_price: Entry price
                     - side: "LONG" or "SHORT" or PositionSide enum
                     - current_stop: Current stop loss level (optional)
            current_price: Current market price
            atr_value: Current ATR value
            volatility_regime: Current market volatility classification

        Returns:
            New stop price if updated, None if no update needed

        Usage:
            position = {
                "symbol": "BTCUSDT",
                "entry_price": 50000.0,
                "side": "LONG",
                "current_stop": 48750.0
            }
            new_stop = trailing_stop.update_position_stop(
                position, current_price=52000.0, atr_value=480.0
            )
            if new_stop:
                # Update stop in exchange
                pass
        """
        # Extract position details
        symbol = position.get("symbol", "UNKNOWN")
        entry_price = float(position.get("entry_price", 0))

        # Handle side conversion
        side_value = position.get("side", "LONG")
        if isinstance(side_value, PositionSide):
            side = side_value
        else:
            side = PositionSide.LONG if side_value.upper() == "LONG" else PositionSide.SHORT

        # Get or create position state
        state = self._get_or_create_state(symbol, entry_price, side, atr_value)

        # Update current stop from position if provided
        if "current_stop" in position and position["current_stop"]:
            state.current_stop = float(position["current_stop"])

        # Update price extremes
        state.update_price_extremes(current_price)

        # Check if we should update the stop
        should_update = self.should_update_stop(
            current_price=current_price,
            entry_price=entry_price,
            current_stop=state.current_stop,
            side=side,
            last_update_price=state.highest_price if side == PositionSide.LONG else state.lowest_price
        )

        if not should_update:
            return None

        # Mark trailing as activated
        if not state.trail_activated:
            state.trail_activated = True
            logger.info(f"{symbol}: Trailing stop activated at price {current_price:.4f}")

        # Calculate new trailing stop
        reference_price = (
            state.highest_price if side == PositionSide.LONG else state.lowest_price
        )

        new_stop = self.calculate_trailing_stop(
            current_price=current_price,
            highest_price=reference_price,
            atr_value=atr_value,
            side=side,
            current_stop=state.current_stop,
            volatility_regime=volatility_regime
        )

        # Check if stop actually changed
        if abs(new_stop - state.current_stop) < 0.01:  # Allow for float precision
            return None

        # Update state
        old_stop = state.current_stop
        state.current_stop = new_stop
        state.last_update = datetime.utcnow()
        state.total_updates += 1

        # Update statistics
        self._stats["stops_updated"] += 1

        # Calculate profit protected
        if side == PositionSide.LONG:
            profit_protected = (new_stop - entry_price) / entry_price * 100
        else:
            profit_protected = (entry_price - new_stop) / entry_price * 100

        if profit_protected > 0:
            self._stats["total_profit_protected"] = max(
                self._stats["total_profit_protected"],
                profit_protected
            )

        logger.info(
            f"{symbol}: Trailing stop updated "
            f"{old_stop:.4f} -> {new_stop:.4f} "
            f"(protecting {profit_protected:.2f}% profit)"
        )

        return new_stop

    def _get_or_create_state(
        self,
        symbol: str,
        entry_price: float,
        side: PositionSide,
        atr_value: float
    ) -> PositionTrailState:
        """
        Get existing position state or create new one.

        Args:
            symbol: Trading symbol
            entry_price: Entry price for new state
            side: Position direction
            atr_value: Current ATR value

        Returns:
            PositionTrailState for the symbol
        """
        if symbol not in self._position_states:
            # Calculate initial stop for new position
            initial_stop = self.calculate_initial_stop(
                entry_price=entry_price,
                atr_value=atr_value,
                side=side
            )

            # Create new state
            self._position_states[symbol] = PositionTrailState(
                symbol=symbol,
                entry_price=entry_price,
                side=side,
                current_stop=initial_stop,
                highest_price=entry_price,
                lowest_price=entry_price,
                atr_at_entry=atr_value
            )

            logger.info(
                f"{symbol}: New position state created "
                f"(entry={entry_price:.4f}, initial_stop={initial_stop:.4f})"
            )

        return self._position_states[symbol]

    def remove_position_state(self, symbol: str) -> Optional[PositionTrailState]:
        """
        Remove position state when position is closed.

        Args:
            symbol: Trading symbol to remove

        Returns:
            Removed state if it existed, None otherwise
        """
        state = self._position_states.pop(symbol, None)
        if state:
            logger.info(
                f"{symbol}: Position state removed "
                f"(updates={state.total_updates})"
            )
        return state

    def get_position_state(self, symbol: str) -> Optional[PositionTrailState]:
        """
        Get current state for a position.

        Args:
            symbol: Trading symbol

        Returns:
            PositionTrailState if exists, None otherwise
        """
        return self._position_states.get(symbol)

    def get_all_states(self) -> Dict[str, PositionTrailState]:
        """Get all active position states."""
        return self._position_states.copy()

    def get_statistics(self) -> Dict:
        """
        Get trailing stop statistics.

        Returns:
            Dictionary with statistics:
            - stops_calculated: Total initial stops calculated
            - stops_updated: Total trailing stop updates
            - active_positions: Number of positions being tracked
            - total_profit_protected: Maximum profit protected across all positions
        """
        return {
            **self._stats,
            "active_positions": len(self._position_states)
        }

    def reset(self) -> None:
        """Reset all position states and statistics."""
        self._position_states.clear()
        self._stats = {
            "stops_calculated": 0,
            "stops_updated": 0,
            "stops_triggered": 0,
            "total_profit_protected": 0.0
        }
        logger.info("ATRTrailingStop reset - all states cleared")


# Global instance management
_atr_trailing_stop: Optional[ATRTrailingStop] = None


def get_atr_trailing_stop(
    config: Optional[ATRTrailingStopConfig] = None
) -> ATRTrailingStop:
    """
    Get or create the global ATRTrailingStop instance.

    This provides a singleton pattern for the trailing stop calculator,
    ensuring consistent state across the application.

    Args:
        config: Optional configuration. Only used when creating new instance.

    Returns:
        Global ATRTrailingStop instance

    Usage:
        # Get with default config
        trailing_stop = get_atr_trailing_stop()

        # Get with custom config (only applies if instance doesn't exist)
        config = ATRTrailingStopConfig(base_atr_multiplier=3.0)
        trailing_stop = get_atr_trailing_stop(config)
    """
    global _atr_trailing_stop

    if _atr_trailing_stop is None:
        _atr_trailing_stop = ATRTrailingStop(config)
        logger.info("Global ATRTrailingStop instance created")

    return _atr_trailing_stop


def reset_atr_trailing_stop() -> None:
    """
    Reset the global ATRTrailingStop instance.

    This clears all position states and allows reconfiguration.
    Use when reinitializing the trading system.
    """
    global _atr_trailing_stop

    if _atr_trailing_stop is not None:
        _atr_trailing_stop.reset()
        _atr_trailing_stop = None
        logger.info("Global ATRTrailingStop instance reset")


def calculate_trailing_stop_update(
    symbol: str,
    entry_price: float,
    current_price: float,
    current_stop: float,
    atr_value: float,
    side: str,
    volatility_regime: str = "normal"
) -> Optional[float]:
    """
    Convenience function for calculating trailing stop updates.

    Provides a simple interface for one-off calculations without
    managing position state.

    Args:
        symbol: Trading symbol
        entry_price: Original entry price
        current_price: Current market price
        current_stop: Current stop loss level
        atr_value: Current ATR value
        side: Position side ("LONG" or "SHORT")
        volatility_regime: Volatility level ("low", "normal", "high", "extreme")

    Returns:
        New stop price if update needed, None otherwise

    Usage:
        new_stop = calculate_trailing_stop_update(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=52000.0,
            current_stop=48750.0,
            atr_value=480.0,
            side="LONG",
            volatility_regime="normal"
        )
    """
    # Get global instance
    trailing_stop = get_atr_trailing_stop()

    # Convert string regime to enum
    try:
        regime = VolatilityRegime(volatility_regime.lower())
    except ValueError:
        regime = VolatilityRegime.NORMAL
        logger.warning(
            f"Unknown volatility regime '{volatility_regime}', using NORMAL"
        )

    # Create position dict
    position = {
        "symbol": symbol,
        "entry_price": entry_price,
        "side": side,
        "current_stop": current_stop
    }

    # Calculate update
    return trailing_stop.update_position_stop(
        position=position,
        current_price=current_price,
        atr_value=atr_value,
        volatility_regime=regime
    )
