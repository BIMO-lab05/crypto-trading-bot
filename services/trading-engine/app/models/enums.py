"""
Enumerations for Trading Engine
Purpose: Define all enum types used across the service
"""

from enum import Enum


class SignalAction(str, Enum):
    """Trading signal actions"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"


class PositionSide(str, Enum):
    """Position side (direction)"""
    LONG = "LONG"
    SHORT = "SHORT"


class PositionStatus(str, Enum):
    """Position status"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PENDING = "PENDING"


class OrderSide(str, Enum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"


class OrderStatus(str, Enum):
    """Order status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class TimeInForce(str, Enum):
    """Time in force for orders (added 2026-01-16 for Fix #3)"""
    GTC = "GTC"  # Good Till Cancel
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # Fill or Kill
    GTX = "GTX"  # Good Till Crossing (Post-only)


class TradingMode(str, Enum):
    """Trading mode"""
    PAPER = "PAPER"
    LIVE = "LIVE"
