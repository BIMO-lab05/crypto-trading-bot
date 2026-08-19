"""
Input Validation Models
Pydantic models for request validation
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional

from app.config import settings


class SymbolValidator(BaseModel):
    """Validator for trading symbol"""
    symbol: str = Field(..., min_length=5, max_length=20, description="Trading symbol (e.g., BTCUSDT)")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        """Validate symbol format"""
        v = v.upper()
        if not v.endswith("USDT"):
            raise ValueError("Only USDT pairs are supported")
        if not v[:-4].isalpha():
            raise ValueError("Invalid symbol format - must be alphabetic + USDT")
        return v


class IntervalValidator(BaseModel):
    """Validator for kline interval"""
    interval: str = Field(default="60", description="Kline interval in minutes")

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        """Validate interval"""
        valid_intervals = ["1", "5", "15", "30", "60", "240", "D"]
        if v not in valid_intervals:
            raise ValueError(f"Invalid interval. Must be one of: {', '.join(valid_intervals)}")
        return v


class KlineRequest(BaseModel):
    """Request model for kline data"""
    symbol: str = Field(..., min_length=5, max_length=20)
    interval: str = Field(default="60")
    limit: int = Field(default=100, ge=1, le=1000, description="Number of candles to fetch")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.upper()
        if not v.endswith("USDT"):
            raise ValueError("Only USDT pairs supported")
        return v

    @field_validator("interval")
    @classmethod
    def validate_interval(cls, v: str) -> str:
        valid_intervals = ["1", "5", "15", "30", "60", "240", "D"]
        if v not in valid_intervals:
            raise ValueError(f"Invalid interval. Must be one of: {', '.join(valid_intervals)}")
        return v


class RSIRequest(BaseModel):
    """Request model for RSI indicator"""
    symbol: str = Field(..., min_length=5, max_length=20)
    interval: str = Field(default="60")
    period: int = Field(default=14, ge=2, le=100, description="RSI period")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return v.upper()


class TradeRequest(BaseModel):
    """Request model for trade execution"""
    # default_factory, not default=: evaluated per instantiation so the
    # canonical id is never frozen at import time (.claude/rules/money.md).
    portfolio_id: str = Field(
        default_factory=lambda: settings.default_portfolio_id, max_length=50
    )
    symbol: str = Field(..., min_length=5, max_length=20)
    quantity: str = Field(..., description="Trade quantity")
    price: str = Field(..., description="Trade price")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        return v.upper()

    @field_validator("quantity", "price")
    @classmethod
    def validate_numeric(cls, v: str) -> str:
        """Validate that quantity and price are valid numbers"""
        try:
            float_val = float(v)
            if float_val <= 0:
                raise ValueError("Value must be positive")
        except ValueError:
            raise ValueError("Must be a valid positive number")
        return v


class VaRRequest(BaseModel):
    """Request model for Value at Risk calculation"""
    confidence_level: float = Field(default=0.95, ge=0.9, le=0.99, description="Confidence level (0.9-0.99)")
    time_horizon_days: int = Field(default=1, ge=1, le=30, description="Time horizon in days")
