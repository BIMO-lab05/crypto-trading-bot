"""
Portfolio Models
Main portfolio tracking and management models
"""

from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
from uuid import uuid4

from app.models.asset import Asset, AssetHolding
from app.models.enums import AllocationStrategy


class Portfolio(BaseModel):
    """Complete portfolio state"""

    portfolio_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique portfolio ID")

    # Balance
    initial_capital: Decimal = Field(..., ge=0, description="Starting capital")
    cash_balance: Decimal = Field(..., ge=0, description="Current cash balance")
    total_value: Decimal = Field(default=Decimal("0"), ge=0, description="Total portfolio value")

    # Assets
    assets: Dict[str, Asset] = Field(default_factory=dict, description="Holdings by symbol")

    # Performance
    total_pnl: Decimal = Field(default=Decimal("0"), description="Total realized + unrealized P&L")
    realized_pnl: Decimal = Field(default=Decimal("0"), description="Realized profit/loss")
    unrealized_pnl: Decimal = Field(default=Decimal("0"), description="Unrealized profit/loss")
    total_return_pct: Decimal = Field(default=Decimal("0"), description="Total return %")

    # Strategy
    allocation_strategy: AllocationStrategy = Field(
        default=AllocationStrategy.EQUAL_WEIGHT,
        description="Portfolio allocation strategy"
    )

    # Metadata
    created_at: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))
    last_updated: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    class Config:
        json_encoders = {
            Decimal: str
        }

    def update_asset_prices(self, prices: Dict[str, Decimal]) -> None:
        """Update all asset prices and recalculate portfolio value"""
        total_asset_value = Decimal("0")
        total_unrealized_pnl = Decimal("0")

        for symbol, price in prices.items():
            if symbol in self.assets:
                self.assets[symbol].update_valuation(price)
                total_asset_value += self.assets[symbol].current_value
                total_unrealized_pnl += self.assets[symbol].unrealized_pnl

        # Update portfolio totals
        self.total_value = self.cash_balance + total_asset_value
        self.unrealized_pnl = total_unrealized_pnl
        self.total_pnl = self.realized_pnl + self.unrealized_pnl

        if self.initial_capital > 0:
            self.total_return_pct = ((self.total_value - self.initial_capital) / self.initial_capital) * Decimal("100")

        # Update asset allocations
        if self.total_value > 0:
            for asset in self.assets.values():
                asset.current_allocation_pct = (asset.current_value / self.total_value) * Decimal("100")

        self.last_updated = int(datetime.now().timestamp() * 1000)

    def add_asset(self, symbol: str, name: str, quantity: Decimal, price: Decimal) -> None:
        """Add or update asset position (buy)"""
        cost = quantity * price

        if cost > self.cash_balance:
            raise ValueError(f"Insufficient cash balance: need {cost}, have {self.cash_balance}")

        if symbol not in self.assets:
            # Create new asset
            self.assets[symbol] = Asset(
                symbol=symbol,
                name=name,
                quantity=quantity,
                average_entry_price=price,
                current_price=price,
                total_cost=cost,
                current_value=quantity * price
            )
        else:
            # Add to existing position
            self.assets[symbol].add_quantity(quantity, price)

        # Deduct cash
        self.cash_balance -= cost
        self.update_asset_prices({symbol: price})

    def remove_asset(self, symbol: str, quantity: Decimal, price: Decimal) -> Decimal:
        """Remove from asset position (sell) and return realized P&L"""
        if symbol not in self.assets:
            raise ValueError(f"Asset {symbol} not in portfolio")

        # Calculate realized P&L
        realized_pnl = self.assets[symbol].reduce_quantity(quantity, price)

        # Add proceeds to cash
        proceeds = quantity * price
        self.cash_balance += proceeds

        # Update realized P&L tracking
        self.realized_pnl += realized_pnl

        # Remove asset if quantity is zero
        if self.assets[symbol].quantity == 0:
            del self.assets[symbol]

        self.update_asset_prices({symbol: price})

        return realized_pnl

    def get_asset_allocation(self) -> Dict[str, Decimal]:
        """Get current asset allocation percentages"""
        return {
            symbol: asset.current_allocation_pct
            for symbol, asset in self.assets.items()
        }

    def needs_rebalancing(self, threshold_pct: Decimal) -> bool:
        """Check if portfolio needs rebalancing"""
        for asset in self.assets.values():
            if asset.target_allocation_pct is not None:
                drift = abs(asset.current_allocation_pct - asset.target_allocation_pct)
                if drift > threshold_pct:
                    return True
        return False


class PortfolioSnapshot(BaseModel):
    """Point-in-time portfolio snapshot for history"""

    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    portfolio_id: str
    timestamp: int = Field(default_factory=lambda: int(datetime.now().timestamp() * 1000))

    # Balances
    cash_balance: str  # String for Decimal
    total_value: str
    total_pnl: str
    total_return_pct: str

    # Holdings
    holdings: List[AssetHolding]

    # Performance
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None


class RebalanceRecommendation(BaseModel):
    """Rebalancing recommendation"""

    symbol: str
    current_allocation_pct: str
    target_allocation_pct: str
    drift_pct: str
    action: str  # "BUY" or "SELL"
    quantity: str  # Amount to trade
    estimated_cost: str  # Estimated transaction cost
