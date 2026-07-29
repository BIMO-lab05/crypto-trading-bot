"""
Position Models
Purpose: Trading position data structures

UPDATED 2025-11-29: Research-backed position management enhancements
- Added trailing stop support for locking in profits
- Added multiple take profit levels (TP1, TP2, TP3) for partial exits
- Research shows partial exits at 1:1, 2:1, 3:1 R:R improves consistency
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID, uuid4
from app.models.enums import PositionSide, PositionStatus


class PositionBase(BaseModel):
    """Base position model"""
    symbol: str = Field(description="Trading symbol")
    side: PositionSide = Field(description="Position side (LONG/SHORT)")
    entry_price: Decimal = Field(description="Entry price")
    quantity: Decimal = Field(description="Position quantity")
    stop_loss: Optional[Decimal] = Field(default=None, description="Stop loss price")
    take_profit: Optional[Decimal] = Field(default=None, description="Take profit price (legacy/primary)")
    strategy: Optional[str] = Field(default=None, description="Strategy name")
    # CRITICAL FIX 2025-12-05: Save entry signal confidence for performance analysis
    entry_signal_confidence: Optional[float] = Field(default=None, description="Entry signal confidence (0.0-1.0)")
    # RESEARCH-BACKED: Multi-level take profits for partial exits (2025-11-29)
    take_profit_1: Optional[Decimal] = Field(default=None, description="TP1 - 1:1 R:R (close 33%)")
    take_profit_2: Optional[Decimal] = Field(default=None, description="TP2 - 2:1 R:R (close 33%)")
    take_profit_3: Optional[Decimal] = Field(default=None, description="TP3 - 3:1 R:R (close final 34%)")
    trailing_stop: Optional[Decimal] = Field(default=None, description="Trailing stop price")
    trailing_stop_enabled: bool = Field(default=False, description="Enable trailing stop after TP1")


class PositionCreate(PositionBase):
    """Create position request"""
    pass


class PositionUpdate(BaseModel):
    """Update position request"""
    current_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    status: Optional[PositionStatus] = None


class Position(PositionBase):
    """
    Position model with calculated fields

    RESEARCH-BACKED ENHANCEMENTS (2025-11-29):
    - Trailing stop support: Locks in profits as price moves favorably
    - Partial exits: Scales out at TP1 (33%), TP2 (33%), TP3 (34%)
    - Exit tracking: Records which TPs have been hit
    """
    id: UUID = Field(default_factory=uuid4, description="Position ID")
    current_price: Optional[Decimal] = Field(default=None, description="Current price")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    status: PositionStatus = Field(default=PositionStatus.OPEN, description="Position status")
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Open timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="Close timestamp")
    exit_price: Optional[Decimal] = Field(default=None, description="Exit price (for closed positions)")
    exit_reason: Optional[str] = Field(default=None, description="Exit reason (stop_loss, take_profit, manual, etc)")

    # RESEARCH-BACKED: Partial exit tracking (2025-11-29)
    remaining_quantity: Optional[Decimal] = Field(default=None, description="Remaining position size after partial exits")
    tp1_hit: bool = Field(default=False, description="TP1 level reached and partial exit taken")
    tp2_hit: bool = Field(default=False, description="TP2 level reached and partial exit taken")
    tp3_hit: bool = Field(default=False, description="TP3 level reached and full exit taken")
    highest_price: Optional[Decimal] = Field(default=None, description="Highest price reached (for trailing)")
    lowest_price: Optional[Decimal] = Field(default=None, description="Lowest price reached (for trailing)")

    model_config = ConfigDict(from_attributes=True)

    def __init__(self, **data):
        """Initialize position with remaining quantity set to full quantity"""
        super().__init__(**data)
        if self.remaining_quantity is None:
            self.remaining_quantity = self.quantity

    @property
    def pnl_percentage(self) -> float:
        """Calculate P&L as percentage of the position's entry notional.

        FIX 2026-07-28: closed positions report realized P&L (unrealized is
        zeroed at close, which previously made every close log/notify +0.00%).
        """
        if self.entry_price == 0 or self.quantity == 0:
            return 0.0
        notional = self.entry_price * self.quantity
        if self.status == PositionStatus.CLOSED:
            return float((self.realized_pnl / notional) * 100)
        return float((self.unrealized_pnl / notional) * 100)

    @property
    def total_value(self) -> Decimal:
        """Calculate total position value at current price"""
        if self.current_price:
            return self.current_price * self.quantity
        return self.entry_price * self.quantity

    def update_pnl(self, current_price: Decimal):
        """Update unrealized P&L based on current price.

        FIX 2026-07-28: unrealized P&L is computed on the REMAINING quantity
        (after partial exits), not the original full quantity. Previously a
        position that had scaled out 66% still marked unrealized P&L on 100%
        of the original size, overstating equity and exit checks.
        """
        self.current_price = current_price
        qty = (
            self.remaining_quantity
            if self.remaining_quantity is not None
            else self.quantity
        )
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * qty
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - current_price) * qty

    def check_stop_loss(self, current_price: Decimal) -> bool:
        """Check if stop loss is hit"""
        if not self.stop_loss:
            return False

        if self.side == PositionSide.LONG:
            return current_price <= self.stop_loss
        else:  # SHORT
            return current_price >= self.stop_loss

    def check_take_profit(self, current_price: Decimal) -> bool:
        """Check if take profit is hit"""
        if not self.take_profit:
            return False

        if self.side == PositionSide.LONG:
            return current_price >= self.take_profit
        else:  # SHORT
            return current_price <= self.take_profit

    # ============================================================================
    # RESEARCH-BACKED: Trailing Stop and Partial Exit Methods (2025-11-29)
    # ============================================================================

    def update_price_extremes(self, current_price: Decimal):
        """
        Track price extremes for trailing stop calculation

        Args:
            current_price: Current market price
        """
        if self.highest_price is None or current_price > self.highest_price:
            self.highest_price = current_price
        if self.lowest_price is None or current_price < self.lowest_price:
            self.lowest_price = current_price

    def update_trailing_stop(self, current_price: Decimal, trail_distance: Decimal) -> bool:
        """
        Update trailing stop based on favorable price movement

        Trailing stop only moves in the profitable direction:
        - LONG: Stop rises as price rises (locks in profit)
        - SHORT: Stop falls as price falls (locks in profit)

        Args:
            current_price: Current market price
            trail_distance: Distance to trail behind price (e.g., 2 * ATR)

        Returns:
            True if trailing stop was updated
        """
        if not self.trailing_stop_enabled:
            return False

        self.update_price_extremes(current_price)

        if self.side == PositionSide.LONG:
            # For LONG: Trail up (increase stop as price rises)
            new_stop = current_price - trail_distance
            if self.trailing_stop is None or new_stop > self.trailing_stop:
                self.trailing_stop = new_stop
                return True
        else:  # SHORT
            # For SHORT: Trail down (decrease stop as price falls)
            new_stop = current_price + trail_distance
            if self.trailing_stop is None or new_stop < self.trailing_stop:
                self.trailing_stop = new_stop
                return True

        return False

    def check_trailing_stop(self, current_price: Decimal) -> bool:
        """
        Check if trailing stop has been hit

        Args:
            current_price: Current market price

        Returns:
            True if trailing stop is hit
        """
        if not self.trailing_stop or not self.trailing_stop_enabled:
            return False

        if self.side == PositionSide.LONG:
            return current_price <= self.trailing_stop
        else:  # SHORT
            return current_price >= self.trailing_stop

    def check_partial_exit(self, current_price: Decimal) -> Optional[Dict]:
        """
        Check if any take profit level has been hit for partial exit

        RESEARCH-BACKED PARTIAL EXIT STRATEGY:
        - TP1 (1:1 R:R): Exit 33% of position, enable trailing stop
        - TP2 (2:1 R:R): Exit another 33%, tighten trailing stop
        - TP3 (3:1 R:R): Exit final 34%

        Args:
            current_price: Current market price

        Returns:
            Dict with exit info if partial exit triggered, None otherwise
            {
                "level": "TP1" | "TP2" | "TP3",
                "exit_quantity": Decimal,
                "exit_percentage": float,
                "remaining_quantity": Decimal,
                "enable_trailing": bool
            }
        """
        if self.remaining_quantity is None or self.remaining_quantity <= 0:
            return None

        # Check TP levels in order
        if self.side == PositionSide.LONG:
            # LONG: Price goes UP to hit TPs
            if not self.tp1_hit and self.take_profit_1 and current_price >= self.take_profit_1:
                return self._create_partial_exit("TP1", Decimal("0.33"))
            elif not self.tp2_hit and self.take_profit_2 and current_price >= self.take_profit_2:
                return self._create_partial_exit("TP2", Decimal("0.33"))
            elif not self.tp3_hit and self.take_profit_3 and current_price >= self.take_profit_3:
                return self._create_partial_exit("TP3", Decimal("1.0"))  # Exit remaining
        else:
            # SHORT: Price goes DOWN to hit TPs
            if not self.tp1_hit and self.take_profit_1 and current_price <= self.take_profit_1:
                return self._create_partial_exit("TP1", Decimal("0.33"))
            elif not self.tp2_hit and self.take_profit_2 and current_price <= self.take_profit_2:
                return self._create_partial_exit("TP2", Decimal("0.33"))
            elif not self.tp3_hit and self.take_profit_3 and current_price <= self.take_profit_3:
                return self._create_partial_exit("TP3", Decimal("1.0"))

        return None

    def _create_partial_exit(self, level: str, percentage: Decimal) -> Dict:
        """
        Create partial exit details

        Args:
            level: TP level (TP1, TP2, TP3)
            percentage: Percentage of remaining position to exit

        Returns:
            Partial exit details dict
        """
        exit_quantity = self.remaining_quantity * percentage
        new_remaining = self.remaining_quantity - exit_quantity

        return {
            "level": level,
            "exit_quantity": exit_quantity,
            "exit_percentage": float(percentage * 100),
            "remaining_quantity": new_remaining,
            "enable_trailing": level == "TP1"  # Enable trailing after TP1
        }

    def apply_partial_exit(self, exit_info: Dict, realized_pnl: Decimal):
        """
        Apply partial exit to position

        Args:
            exit_info: Dict from check_partial_exit()
            realized_pnl: Realized P&L from the partial exit
        """
        level = exit_info["level"]
        self.remaining_quantity = exit_info["remaining_quantity"]
        self.realized_pnl += realized_pnl

        # Mark TP level as hit
        if level == "TP1":
            self.tp1_hit = True
            self.trailing_stop_enabled = True  # Enable trailing after TP1
        elif level == "TP2":
            self.tp2_hit = True
        elif level == "TP3":
            self.tp3_hit = True
            self.status = PositionStatus.CLOSED  # Full exit
            self.closed_at = datetime.now(timezone.utc)

    def get_effective_stop_loss(self) -> Optional[Decimal]:
        """
        Get the effective stop loss (original or trailing, whichever is better)

        Returns:
            The more favorable stop loss level
        """
        if not self.trailing_stop_enabled or not self.trailing_stop:
            return self.stop_loss

        if self.stop_loss is None:
            return self.trailing_stop

        if self.side == PositionSide.LONG:
            # For LONG: Higher stop is better
            return max(self.stop_loss, self.trailing_stop)
        else:
            # For SHORT: Lower stop is better
            return min(self.stop_loss, self.trailing_stop)
