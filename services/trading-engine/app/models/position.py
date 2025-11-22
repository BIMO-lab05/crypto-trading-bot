"""
Position Models
Purpose: Trading position data structures
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
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
    take_profit: Optional[Decimal] = Field(default=None, description="Take profit price")
    strategy: Optional[str] = Field(default=None, description="Strategy name")


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
    """Position model with calculated fields"""
    id: UUID = Field(default_factory=uuid4, description="Position ID")
    current_price: Optional[Decimal] = Field(default=None, description="Current price")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized P&L")
    status: PositionStatus = Field(default=PositionStatus.OPEN, description="Position status")
    opened_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Open timestamp")
    closed_at: Optional[datetime] = Field(default=None, description="Close timestamp")

    model_config = ConfigDict(from_attributes=True)

    @property
    def pnl_percentage(self) -> float:
        """Calculate P&L as percentage"""
        if self.entry_price == 0:
            return 0.0
        return float((self.unrealized_pnl / (self.entry_price * self.quantity)) * 100)

    @property
    def total_value(self) -> Decimal:
        """Calculate total position value at current price"""
        if self.current_price:
            return self.current_price * self.quantity
        return self.entry_price * self.quantity

    def update_pnl(self, current_price: Decimal):
        """Update unrealized P&L based on current price"""
        self.current_price = current_price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.unrealized_pnl = (self.entry_price - current_price) * self.quantity

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
