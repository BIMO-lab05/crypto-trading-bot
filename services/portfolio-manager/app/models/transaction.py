"""
Transaction History Models
Track all buy/sell transactions for portfolio analysis
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import uuid4


class Transaction(BaseModel):
    """Individual transaction record"""

    transaction_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique transaction ID")
    portfolio_id: str = Field(..., description="Portfolio identifier")

    # Transaction details
    symbol: str = Field(..., description="Asset symbol")
    action: str = Field(..., description="BUY or SELL")
    quantity: str = Field(..., description="Quantity traded")
    price: str = Field(..., description="Price per unit")
    total_amount: str = Field(..., description="Total transaction value")

    # P&L (for SELL transactions)
    realized_pnl: Optional[str] = Field(None, description="Realized profit/loss (SELL only)")
    realized_pnl_pct: Optional[str] = Field(None, description="Realized P&L percentage (SELL only)")

    # Metadata
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    notes: Optional[str] = Field(None, description="Additional notes")

    class Config:
        json_encoders = {
            datetime: lambda v: int(v.timestamp() * 1000)
        }


class TransactionHistoryResponse(BaseModel):
    """Transaction history list response"""

    success: bool = True
    portfolio_id: str
    transactions: list[Transaction]
    total_count: int
    total_buy_volume: str
    total_sell_volume: str
    total_realized_pnl: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
