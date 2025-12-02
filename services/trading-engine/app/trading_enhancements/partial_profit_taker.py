"""
Partial Profit Taker - Scale-Out Strategy for Winning Positions
Research Source: Professional Trading Best Practices (2025-12-02)

Purpose:
- Scale out of winning positions at multiple profit levels
- Lock in profits while letting winners run
- Typical levels: 25%, 50%, 75% of position at 1%, 2%, 3% profit
- Move stop to breakeven after first partial take

Key Features:
- Configurable profit level triggers (1%, 2%, 3%, etc.)
- Configurable exit percentages per level
- Automatic breakeven stop activation after first partial
- Minimum position value protection
- Comprehensive position state tracking
- Integration with existing position manager
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# Configure module logger
logger = logging.getLogger(__name__)


class PartialExitStatus(Enum):
    """Status of partial exit execution"""
    PENDING = "pending"          # Waiting for price trigger
    TRIGGERED = "triggered"      # Price target hit, ready to execute
    EXECUTED = "executed"        # Exit order executed
    SKIPPED = "skipped"          # Skipped due to position too small
    FAILED = "failed"            # Execution failed


@dataclass
class PartialProfitConfig:
    """
    Configuration for partial profit taking strategy

    Based on professional trading research:
    - profit_levels: Price targets as % above entry (1%, 2%, 3%)
    - exit_percentages: How much of remaining position to exit at each level
    - move_stop_to_breakeven_after: Move stop after Nth partial take
    - min_position_value: Don't split positions below this USD value

    Example:
        - At 1% profit: Exit 25% of remaining position
        - At 2% profit: Exit 25% of remaining (now ~19% of original)
        - At 3% profit: Exit 25% of remaining (now ~14% of original)
        - After first partial: Move stop loss to breakeven
    """
    # Profit level triggers (% profit from entry)
    profit_levels: List[float] = field(
        default_factory=lambda: [1.0, 2.0, 3.0]
    )

    # Percentage of REMAINING position to exit at each level
    exit_percentages: List[float] = field(
        default_factory=lambda: [25.0, 25.0, 25.0]
    )

    # Move stop to breakeven after Nth partial (1 = after first partial)
    move_stop_to_breakeven_after: int = 1

    # Minimum position value in USD - don't split below this
    min_position_value: float = 10.0

    # Enable/disable partial profit taking
    enabled: bool = True

    def __post_init__(self):
        """Validate configuration on initialization"""
        # Ensure profit_levels and exit_percentages have same length
        if len(self.profit_levels) != len(self.exit_percentages):
            raise ValueError(
                f"profit_levels ({len(self.profit_levels)}) and "
                f"exit_percentages ({len(self.exit_percentages)}) must have same length"
            )

        # Validate profit levels are positive and ascending
        for i, level in enumerate(self.profit_levels):
            if level <= 0:
                raise ValueError(f"profit_level[{i}] must be positive, got {level}")
            if i > 0 and level <= self.profit_levels[i - 1]:
                raise ValueError("profit_levels must be in ascending order")

        # Validate exit percentages are between 0 and 100
        for i, pct in enumerate(self.exit_percentages):
            if not 0 < pct <= 100:
                raise ValueError(
                    f"exit_percentage[{i}] must be between 0 and 100, got {pct}"
                )

        # Validate move_stop_to_breakeven_after
        if self.move_stop_to_breakeven_after < 0:
            raise ValueError("move_stop_to_breakeven_after must be >= 0")


@dataclass
class PartialExitLevel:
    """
    Represents a single partial exit level

    Tracks the state and execution details of one profit-taking level.
    """
    # Level identification
    level_number: int                    # 1-indexed level number

    # Target configuration
    profit_target_pct: float             # % profit that triggers this level
    exit_pct: float                      # % of remaining position to exit

    # Execution state
    triggered: bool = False              # Has price hit this level?
    triggered_at: Optional[datetime] = None  # When price first hit target
    exit_price: Optional[float] = None   # Actual exit price achieved
    quantity_exited: Optional[float] = None  # Quantity exited at this level
    pnl_realized: Optional[float] = None     # PnL realized from this exit

    # Status tracking
    status: PartialExitStatus = PartialExitStatus.PENDING

    def mark_triggered(self, current_price: float) -> None:
        """Mark this level as triggered by price"""
        if not self.triggered:
            self.triggered = True
            self.triggered_at = datetime.now()
            self.status = PartialExitStatus.TRIGGERED
            logger.info(
                f"Partial exit level {self.level_number} triggered at "
                f"${current_price:.4f} (target: {self.profit_target_pct}%)"
            )

    def mark_executed(
        self,
        exit_price: float,
        quantity: float,
        pnl: float
    ) -> None:
        """Mark this level as executed with fill details"""
        self.exit_price = exit_price
        self.quantity_exited = quantity
        self.pnl_realized = pnl
        self.status = PartialExitStatus.EXECUTED
        logger.info(
            f"Partial exit level {self.level_number} executed: "
            f"qty={quantity:.6f} @ ${exit_price:.4f}, PnL=${pnl:.2f}"
        )

    def mark_skipped(self, reason: str) -> None:
        """Mark this level as skipped"""
        self.status = PartialExitStatus.SKIPPED
        logger.info(
            f"Partial exit level {self.level_number} skipped: {reason}"
        )


@dataclass
class PartialExitToExecute:
    """
    Represents a partial exit that should be executed

    This is returned when a price check determines an exit should occur.
    The caller is responsible for executing the actual trade.
    """
    symbol: str                          # Trading symbol
    level_number: int                    # Which level triggered
    quantity_to_exit: float              # How much to sell/buy
    exit_price: float                    # Current/target price
    profit_pct: float                    # Current profit percentage
    side: str                            # LONG or SHORT (original position side)
    order_side: str                      # BUY or SELL for the exit order

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "symbol": self.symbol,
            "level_number": self.level_number,
            "quantity_to_exit": self.quantity_to_exit,
            "exit_price": self.exit_price,
            "profit_pct": self.profit_pct,
            "side": self.side,
            "order_side": self.order_side
        }


@dataclass
class PositionPartialState:
    """
    Tracks the state of a position with partial profit taking

    Maintains complete history of partial exits and current position state.
    """
    # Position identification
    symbol: str                          # Trading symbol
    side: str                            # LONG or SHORT

    # Entry information
    entry_price: float                   # Original entry price
    original_quantity: float             # Original position size

    # Current state
    remaining_quantity: float            # Current position size
    exit_levels: List[PartialExitLevel] = field(default_factory=list)

    # PnL tracking
    total_realized_pnl: float = 0.0      # Sum of all partial exit PnLs
    total_quantity_exited: float = 0.0   # Total quantity exited so far

    # Stop management
    breakeven_stop_active: bool = False  # Has stop been moved to breakeven?
    original_stop_loss: Optional[float] = None   # Original SL price
    current_stop_loss: Optional[float] = None    # Current SL (may be breakeven)

    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)

    def get_completed_levels(self) -> int:
        """Return count of executed partial exit levels"""
        return sum(
            1 for level in self.exit_levels
            if level.status == PartialExitStatus.EXECUTED
        )

    def get_remaining_value(self, current_price: float) -> float:
        """Calculate remaining position value at current price"""
        return self.remaining_quantity * current_price

    def get_current_profit_pct(self, current_price: float) -> float:
        """
        Calculate current profit percentage from entry

        For LONG positions: profit when price > entry
        For SHORT positions: profit when price < entry
        """
        if self.side == "LONG":
            return ((current_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            return ((self.entry_price - current_price) / self.entry_price) * 100

    def update_after_exit(
        self,
        quantity_exited: float,
        pnl_realized: float
    ) -> None:
        """Update position state after a partial exit"""
        self.remaining_quantity -= quantity_exited
        self.total_quantity_exited += quantity_exited
        self.total_realized_pnl += pnl_realized
        self.last_updated = datetime.now()

        logger.debug(
            f"Position {self.symbol} updated after exit: "
            f"remaining={self.remaining_quantity:.6f}, "
            f"total_pnl=${self.total_realized_pnl:.2f}"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "entry_price": self.entry_price,
            "original_quantity": self.original_quantity,
            "remaining_quantity": self.remaining_quantity,
            "total_realized_pnl": self.total_realized_pnl,
            "total_quantity_exited": self.total_quantity_exited,
            "breakeven_stop_active": self.breakeven_stop_active,
            "current_stop_loss": self.current_stop_loss,
            "completed_levels": self.get_completed_levels(),
            "total_levels": len(self.exit_levels),
            "created_at": self.created_at.isoformat(),
            "last_updated": self.last_updated.isoformat()
        }


class PartialProfitTaker:
    """
    Partial Profit Taker - Implements scale-out strategy for winning positions

    Research-backed implementation for:
    - Taking profits at multiple levels
    - Reducing position size as profit increases
    - Moving stop to breakeven after initial profit
    - Letting remaining position run with reduced risk

    Usage:
        taker = PartialProfitTaker(config)

        # Create position state on entry
        state = taker.create_position_state("BTCUSDT", 50000.0, 0.1)

        # Check for partial exits on price update
        exits = taker.check_partial_exits(state, 50500.0)
        for exit in exits:
            # Execute the exit order
            result = exchange.place_order(...)
            taker.execute_partial_exit(state, exit.level_number, result.fill_price)

        # Check if stop should move to breakeven
        if taker.should_move_to_breakeven(state):
            breakeven_price = taker.get_breakeven_stop(state)
            # Update stop loss order
    """

    def __init__(self, config: Optional[PartialProfitConfig] = None):
        """
        Initialize Partial Profit Taker

        Args:
            config: Configuration for profit levels and exits.
                    Uses defaults if not provided.
        """
        self.config = config or PartialProfitConfig()
        self.positions: Dict[str, PositionPartialState] = {}

        logger.info(
            f"PartialProfitTaker initialized: enabled={self.config.enabled}, "
            f"levels={self.config.profit_levels}, "
            f"exit_pcts={self.config.exit_percentages}, "
            f"breakeven_after={self.config.move_stop_to_breakeven_after}"
        )

    def create_position_state(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        side: str = "LONG",
        stop_loss: Optional[float] = None
    ) -> PositionPartialState:
        """
        Create a new position state for partial profit tracking

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            entry_price: Position entry price
            quantity: Position size in base currency
            side: Position side, "LONG" or "SHORT"
            stop_loss: Optional initial stop loss price

        Returns:
            PositionPartialState object for tracking
        """
        # Create exit levels from config
        exit_levels = [
            PartialExitLevel(
                level_number=i + 1,
                profit_target_pct=self.config.profit_levels[i],
                exit_pct=self.config.exit_percentages[i]
            )
            for i in range(len(self.config.profit_levels))
        ]

        # Create position state
        state = PositionPartialState(
            symbol=symbol,
            side=side.upper(),
            entry_price=entry_price,
            original_quantity=quantity,
            remaining_quantity=quantity,
            exit_levels=exit_levels,
            original_stop_loss=stop_loss,
            current_stop_loss=stop_loss
        )

        # Store in positions dictionary
        self.positions[symbol] = state

        logger.info(
            f"Partial profit state created for {symbol}: "
            f"side={side}, entry=${entry_price:.4f}, qty={quantity:.6f}, "
            f"levels={len(exit_levels)}"
        )

        return state

    def check_partial_exits(
        self,
        position_state: PositionPartialState,
        current_price: float
    ) -> List[PartialExitToExecute]:
        """
        Check if any partial exit levels should be triggered

        Args:
            position_state: Current position state
            current_price: Current market price

        Returns:
            List of PartialExitToExecute for exits that should happen
        """
        if not self.config.enabled:
            return []

        exits_to_execute: List[PartialExitToExecute] = []

        # Calculate current profit percentage
        current_profit_pct = position_state.get_current_profit_pct(current_price)

        # Check if we're in profit (positive for both LONG and SHORT)
        if current_profit_pct <= 0:
            return []

        # Check each exit level
        for level in position_state.exit_levels:
            # Skip already executed or skipped levels
            if level.status in [PartialExitStatus.EXECUTED, PartialExitStatus.SKIPPED]:
                continue

            # Check if this level should trigger
            if current_profit_pct >= level.profit_target_pct:
                # Mark as triggered if not already
                if not level.triggered:
                    level.mark_triggered(current_price)

                # Calculate quantity to exit
                quantity_to_exit = position_state.remaining_quantity * (level.exit_pct / 100)

                # Check minimum position value
                remaining_value = position_state.get_remaining_value(current_price)
                exit_value = quantity_to_exit * current_price

                if remaining_value - exit_value < self.config.min_position_value:
                    # Position would be too small after exit
                    if remaining_value >= self.config.min_position_value:
                        # Close entire remaining position instead
                        quantity_to_exit = position_state.remaining_quantity
                        logger.info(
                            f"Adjusting level {level.level_number} to close full position "
                            f"(remaining value ${remaining_value:.2f} < min ${self.config.min_position_value})"
                        )
                    else:
                        level.mark_skipped("Position value below minimum")
                        continue

                # Determine order side for exit
                if position_state.side == "LONG":
                    order_side = "SELL"  # Sell to close LONG
                else:
                    order_side = "BUY"   # Buy to close SHORT

                # Create exit instruction
                exit_instruction = PartialExitToExecute(
                    symbol=position_state.symbol,
                    level_number=level.level_number,
                    quantity_to_exit=quantity_to_exit,
                    exit_price=current_price,
                    profit_pct=current_profit_pct,
                    side=position_state.side,
                    order_side=order_side
                )

                exits_to_execute.append(exit_instruction)
                logger.info(
                    f"Partial exit triggered for {position_state.symbol} level {level.level_number}: "
                    f"qty={quantity_to_exit:.6f} @ ${current_price:.4f} "
                    f"({current_profit_pct:.2f}% profit)"
                )

        return exits_to_execute

    def execute_partial_exit(
        self,
        position_state: PositionPartialState,
        level_number: int,
        exit_price: float
    ) -> PositionPartialState:
        """
        Record a partial exit execution and update position state

        Args:
            position_state: Current position state
            level_number: Which level was executed (1-indexed)
            exit_price: Actual fill price achieved

        Returns:
            Updated PositionPartialState
        """
        # Find the level
        level = None
        for l in position_state.exit_levels:
            if l.level_number == level_number:
                level = l
                break

        if not level:
            logger.error(f"Level {level_number} not found for {position_state.symbol}")
            return position_state

        # Calculate actual quantity and PnL
        quantity_exited = position_state.remaining_quantity * (level.exit_pct / 100)

        # Calculate PnL based on position side
        if position_state.side == "LONG":
            pnl = (exit_price - position_state.entry_price) * quantity_exited
        else:  # SHORT
            pnl = (position_state.entry_price - exit_price) * quantity_exited

        # Update level
        level.mark_executed(exit_price, quantity_exited, pnl)

        # Update position state
        position_state.update_after_exit(quantity_exited, pnl)

        # Check if should activate breakeven stop
        completed_levels = position_state.get_completed_levels()
        if (
            not position_state.breakeven_stop_active and
            completed_levels >= self.config.move_stop_to_breakeven_after
        ):
            position_state.breakeven_stop_active = True
            position_state.current_stop_loss = position_state.entry_price
            logger.info(
                f"Breakeven stop activated for {position_state.symbol} "
                f"after {completed_levels} partial exits"
            )

        return position_state

    def get_remaining_quantity(self, symbol: str) -> float:
        """
        Get remaining position quantity for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Remaining quantity, or 0.0 if not tracked
        """
        position = self.positions.get(symbol)
        if position:
            return position.remaining_quantity
        return 0.0

    def should_move_to_breakeven(
        self,
        position_state: PositionPartialState
    ) -> bool:
        """
        Check if stop should be moved to breakeven

        Args:
            position_state: Current position state

        Returns:
            True if breakeven stop should be activated
        """
        # Already activated
        if position_state.breakeven_stop_active:
            return False

        # Check if enough levels completed
        completed_levels = position_state.get_completed_levels()
        return completed_levels >= self.config.move_stop_to_breakeven_after

    def get_breakeven_stop(
        self,
        position_state: PositionPartialState
    ) -> float:
        """
        Get the breakeven stop price for a position

        The breakeven price is the original entry price.
        For positions with fees, caller should add a small buffer.

        Args:
            position_state: Current position state

        Returns:
            Breakeven stop price (entry price)
        """
        return position_state.entry_price

    def get_position_summary(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive summary of position partial profit state

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with position summary, or None if not found
        """
        position = self.positions.get(symbol)
        if not position:
            return None

        # Count levels by status
        level_stats = {
            "pending": 0,
            "triggered": 0,
            "executed": 0,
            "skipped": 0
        }
        for level in position.exit_levels:
            level_stats[level.status.value] = level_stats.get(level.status.value, 0) + 1

        # Build summary
        summary = {
            "symbol": position.symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "original_quantity": position.original_quantity,
            "remaining_quantity": position.remaining_quantity,
            "remaining_pct": (position.remaining_quantity / position.original_quantity) * 100,
            "total_quantity_exited": position.total_quantity_exited,
            "total_realized_pnl": position.total_realized_pnl,
            "breakeven_stop_active": position.breakeven_stop_active,
            "original_stop_loss": position.original_stop_loss,
            "current_stop_loss": position.current_stop_loss,
            "levels": {
                "total": len(position.exit_levels),
                "completed": level_stats["executed"],
                "pending": level_stats["pending"],
                "triggered": level_stats["triggered"],
                "skipped": level_stats["skipped"]
            },
            "exit_details": [
                {
                    "level": level.level_number,
                    "target_pct": level.profit_target_pct,
                    "exit_pct": level.exit_pct,
                    "status": level.status.value,
                    "triggered_at": level.triggered_at.isoformat() if level.triggered_at else None,
                    "exit_price": level.exit_price,
                    "quantity_exited": level.quantity_exited,
                    "pnl_realized": level.pnl_realized
                }
                for level in position.exit_levels
            ],
            "created_at": position.created_at.isoformat(),
            "last_updated": position.last_updated.isoformat()
        }

        return summary

    def remove_position(self, symbol: str) -> bool:
        """
        Remove a position from tracking

        Args:
            symbol: Trading symbol to remove

        Returns:
            True if position was removed, False if not found
        """
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"Partial profit position removed for {symbol}")
            return True
        return False

    def get_all_positions(self) -> List[str]:
        """
        Get list of all tracked symbols

        Returns:
            List of symbol strings
        """
        return list(self.positions.keys())

    def reset(self) -> None:
        """Clear all tracked positions"""
        count = len(self.positions)
        self.positions.clear()
        logger.info(f"PartialProfitTaker reset: {count} positions cleared")


# Global instance management
_partial_profit_taker: Optional[PartialProfitTaker] = None


def get_partial_profit_taker(
    config: Optional[PartialProfitConfig] = None
) -> PartialProfitTaker:
    """
    Get or create the global PartialProfitTaker instance

    Args:
        config: Optional configuration. Only used on first call
                or after reset_partial_profit_taker().

    Returns:
        PartialProfitTaker singleton instance
    """
    global _partial_profit_taker
    if _partial_profit_taker is None:
        _partial_profit_taker = PartialProfitTaker(config)
    return _partial_profit_taker


def reset_partial_profit_taker() -> None:
    """
    Reset the global PartialProfitTaker instance

    Use for testing or reconfiguration.
    """
    global _partial_profit_taker
    _partial_profit_taker = None
    logger.info("Global PartialProfitTaker instance reset")
