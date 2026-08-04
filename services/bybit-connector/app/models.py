"""
Bybit Connector Service - Request/Response Models
Purpose: Pydantic models for input validation and type safety
"""

import math
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ============================================================================
# ENUMS FOR VALIDATION
# ============================================================================


class OrderSide(str, Enum):
    """Valid order sides for Bybit"""

    BUY = "Buy"
    SELL = "Sell"


class OrderType(str, Enum):
    """Valid order types for Bybit"""

    MARKET = "Market"
    LIMIT = "Limit"


class TimeInForce(str, Enum):
    """Valid time in force values for Bybit"""

    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    POST_ONLY = "PostOnly"  # Post Only


class Category(str, Enum):
    """Valid product categories for Bybit"""

    LINEAR = "linear"
    INVERSE = "inverse"
    OPTION = "option"
    SPOT = "spot"


# ============================================================================
# REQUEST MODELS
# ============================================================================


class PlaceOrderRequest(BaseModel):
    """Request model for placing an order with comprehensive validation.

    Phase 18 BL-03: accepts BOTH camelCase (Bybit V5 wire format sent by
    the trading-engine bybit_adapter) and snake_case (internal Python
    callers / existing tests) via Pydantic v2 aliases + populate_by_name.
    """

    model_config = ConfigDict(populate_by_name=True)

    category: Category = Field(default=Category.LINEAR, description="Product category")
    symbol: str = Field(
        ..., min_length=6, max_length=20, description="Trading pair (e.g., BTCUSDT)"
    )
    side: OrderSide = Field(..., description="Buy or Sell")
    order_type: OrderType = Field(..., alias="orderType", description="Market or Limit")
    qty: str = Field(..., description="Order quantity (as string for precision)")
    price: Optional[str] = Field(
        None, description="Order price (required for Limit orders)"
    )
    time_in_force: TimeInForce = Field(
        default=TimeInForce.GTC, alias="timeInForce", description="Time in force"
    )
    reduce_only: bool = Field(
        default=False, alias="reduceOnly", description="Reduce only flag"
    )
    order_link_id: Optional[str] = Field(
        None, alias="orderLinkId", max_length=36, description="User-defined order ID"
    )
    # Conditional / bracket-order parameters (Bybit V5 native fields).
    take_profit: Optional[str] = Field(
        None, alias="takeProfit", description="Take-profit trigger price"
    )
    stop_loss: Optional[str] = Field(
        None, alias="stopLoss", description="Stop-loss trigger price"
    )
    tpsl_mode: Optional[str] = Field(
        None, alias="tpslMode", description="TP/SL mode: 'Full' or 'Partial'"
    )
    trigger_price: Optional[str] = Field(
        None, alias="triggerPrice", description="Conditional-order trigger price"
    )
    trigger_direction: Optional[int] = Field(
        None,
        alias="triggerDirection",
        description="Conditional trigger direction: 1=rise, 2=fall",
    )

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format"""
        v = v.upper()
        if not v.replace("USDT", "").replace("USDC", "").replace("USD", "").isalnum():
            raise ValueError("Symbol must be alphanumeric with USDT/USDC/USD suffix")
        return v

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, v: str) -> str:
        """Validate quantity is a positive, finite number"""
        try:
            qty_float = float(v)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Quantity must be a valid positive number: {e}")
        # float() accepts "nan"/"inf"/"Infinity"; nan/inf slip past a bare
        # `<= 0` check (nan comparisons are always False, inf > 0) and would be
        # forwarded verbatim to the exchange. Reject non-finite values.
        if not math.isfinite(qty_float):
            raise ValueError("Quantity must be a finite number")
        if qty_float <= 0:
            raise ValueError("Quantity must be positive")
        return v

    @field_validator("price", "take_profit", "stop_loss", "trigger_price")
    @classmethod
    def validate_price(cls, v: Optional[str], info) -> Optional[str]:
        """Validate price-shaped fields are positive, finite numbers when present"""
        if v is not None:
            try:
                price_float = float(v)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Price must be a valid positive number: {e}")
            # Reject nan/inf, which otherwise slip past the `<= 0` check.
            if not math.isfinite(price_float):
                raise ValueError("Price must be a finite number")
            if price_float <= 0:
                raise ValueError("Price must be positive")
        return v

    @field_validator("tpsl_mode")
    @classmethod
    def validate_tpsl_mode(cls, v: Optional[str]) -> Optional[str]:
        """tpsl_mode, when set, must be 'Full' or 'Partial' per Bybit V5"""
        if v is not None and v not in ("Full", "Partial"):
            raise ValueError("tpsl_mode must be 'Full' or 'Partial'")
        return v

    @field_validator("trigger_direction")
    @classmethod
    def validate_trigger_direction(cls, v: Optional[int]) -> Optional[int]:
        """trigger_direction, when set, must be 1 (rise) or 2 (fall)"""
        if v is not None and v not in (1, 2):
            raise ValueError("trigger_direction must be 1 (rise) or 2 (fall)")
        return v

    @model_validator(mode="after")
    def validate_order_requirements(self):
        """Validate order type requirements"""
        # Limit orders require price
        if self.order_type == OrderType.LIMIT and not self.price:
            raise ValueError("Limit orders require a price")
        # Conditional orders need both trigger_price and trigger_direction
        if (self.trigger_price is None) != (self.trigger_direction is None):
            raise ValueError(
                "trigger_price and trigger_direction must be specified together"
            )
        return self


class CancelOrderRequest(BaseModel):
    """Request model for cancelling an order"""

    category: Category = Field(default=Category.LINEAR, description="Product category")
    symbol: str = Field(..., min_length=6, max_length=20, description="Trading symbol")
    order_id: Optional[str] = Field(None, description="Order ID")
    order_link_id: Optional[str] = Field(None, description="User-defined order ID")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate and normalize symbol"""
        return v.upper()

    @model_validator(mode="after")
    def validate_id_provided(self):
        """Validate that at least one ID is provided"""
        if not self.order_id and not self.order_link_id:
            raise ValueError("Either order_id or order_link_id must be provided")
        return self


# ============================================================================
# RESPONSE MODELS (Optional - for documentation)
# ============================================================================


class OrderResponse(BaseModel):
    """Standard order response from Bybit"""

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Bybit

    order_id: str
    order_link_id: Optional[str] = None
    symbol: str
    side: str
    order_type: str
    qty: str
    price: Optional[str] = None
    status: str


class BalanceResponse(BaseModel):
    """Wallet balance response"""

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Bybit

    total_equity: Optional[str] = None
    available_balance: Optional[str] = None
    used_margin: Optional[str] = None
