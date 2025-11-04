"""
Asset Models for Portfolio Management
Represents individual assets and their holdings
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional
from datetime import datetime

from app.models.enums import AssetType


class Asset(BaseModel):
    """Represents a single asset in the portfolio"""

    symbol: str = Field(..., description="Asset symbol (e.g., BTC, ETH)")
    name: str = Field(..., description="Asset full name")
    asset_type: AssetType = Field(default=AssetType.CRYPTO, description="Type of asset")

    # Holdings
    quantity: Decimal = Field(default=Decimal("0"), ge=0, description="Quantity held")
    average_entry_price: Decimal = Field(default=Decimal("0"), ge=0, description="Average purchase price")
    current_price: Decimal = Field(default=Decimal("0"), ge=0, description="Current market price")

    # Valuation
    total_cost: Decimal = Field(default=Decimal("0"), ge=0, description="Total cost basis")
    current_value: Decimal = Field(default=Decimal("0"), ge=0, description="Current market value")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized profit/loss")
    unrealized_pnl_pct: Decimal = Field(default=Decimal("0"), description="Unrealized P&L percentage")

    # Allocation
    target_allocation_pct: Optional[Decimal] = Field(default=None, description="Target allocation %")
    current_allocation_pct: Decimal = Field(default=Decimal("0"), description="Current allocation %")

    # Metadata
    last_updated: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    class Config:
        json_encoders = {
            Decimal: str
        }

    def update_valuation(self, current_price: Decimal) -> None:
        """Update asset valuation with new price"""
        self.current_price = current_price
        self.current_value = self.quantity * current_price

        if self.total_cost > 0:
            self.unrealized_pnl = self.current_value - self.total_cost
            self.unrealized_pnl_pct = (self.unrealized_pnl / self.total_cost) * Decimal("100")
        else:
            self.unrealized_pnl = Decimal("0")
            self.unrealized_pnl_pct = Decimal("0")

        self.last_updated = int(datetime.now().timestamp() * 1000)

    def add_quantity(self, quantity: Decimal, price: Decimal) -> None:
        """Add to asset position (buy)"""
        # Calculate new average entry price
        total_cost_before = self.quantity * self.average_entry_price
        new_cost = quantity * price
        new_total_quantity = self.quantity + quantity

        if new_total_quantity > 0:
            self.average_entry_price = (total_cost_before + new_cost) / new_total_quantity

        self.quantity = new_total_quantity
        self.total_cost = self.quantity * self.average_entry_price
        self.update_valuation(price)

    def reduce_quantity(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Reduce asset position (sell) and return realized P&L"""
        if quantity > self.quantity:
            raise ValueError(f"Cannot sell {quantity} units, only {self.quantity} available")

        # Calculate realized P&L for this sale
        cost_basis = quantity * self.average_entry_price
        sale_proceeds = quantity * price
        realized_pnl = sale_proceeds - cost_basis

        # Update position
        self.quantity -= quantity
        self.total_cost = self.quantity * self.average_entry_price
        self.update_valuation(price)

        return realized_pnl


class AssetHolding(BaseModel):
    """Simplified asset holding for responses"""

    symbol: str
    quantity: str  # String for Decimal serialization
    current_price: str
    current_value: str
    unrealized_pnl: str
    unrealized_pnl_pct: str
    allocation_pct: str
