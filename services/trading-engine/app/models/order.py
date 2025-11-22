"""
Order Models
Purpose: Trading order data structures
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from decimal import Decimal
from datetime import datetime, timezone
from uuid import UUID, uuid4
from app.models.enums import OrderSide, OrderType, OrderStatus


class OrderBase(BaseModel):
    """Base order model"""
    symbol: str = Field(description="Trading symbol")
    side: OrderSide = Field(description="Order side (BUY/SELL)")
    type: OrderType = Field(description="Order type")
    quantity: Decimal = Field(description="Order quantity")
    price: Optional[Decimal] = Field(default=None, description="Limit price (for LIMIT orders)")
    strategy: Optional[str] = Field(default=None, description="Strategy name")


class OrderCreate(OrderBase):
    """Create order request"""
    position_id: Optional[UUID] = Field(default=None, description="Associated position ID")


class OrderUpdate(BaseModel):
    """Update order request"""
    status: Optional[OrderStatus] = None
    filled_price: Optional[Decimal] = None
    filled_quantity: Optional[Decimal] = None
    bybit_order_id: Optional[str] = None


class Order(OrderBase):
    """Order model"""
    id: UUID = Field(default_factory=uuid4, description="Order ID")
    position_id: Optional[UUID] = Field(default=None, description="Associated position ID")
    status: OrderStatus = Field(default=OrderStatus.PENDING, description="Order status")
    filled_price: Optional[Decimal] = Field(default=None, description="Filled price")
    filled_quantity: Decimal = Field(default=Decimal("0"), description="Filled quantity")
    bybit_order_id: Optional[str] = Field(default=None, description="Bybit order ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Update timestamp")

    model_config = ConfigDict(from_attributes=True)

    @property
    def is_filled(self) -> bool:
        """Check if order is fully filled"""
        return self.status == OrderStatus.FILLED

    @property
    def is_pending(self) -> bool:
        """Check if order is still pending"""
        return self.status == OrderStatus.PENDING
