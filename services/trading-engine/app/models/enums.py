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


class ExitKind(str, Enum):
    """
    Why a position was closed (Stage 0, 2026-08-07).

    Replaces substring-matching over a free-text reason string. The two live
    predicates disagreed with each other (auto_trader.py:2883 tests
    "stop"/"loss"; :3073 also tests "max_hold"), and in PAPER mode neither
    string ever reached the database — positions.exit_reason was synthesized
    from order.side + order.strategy at paper_trading.py:343.

    Persisted to positions.exit_kind ALONGSIDE the prose exit_reason, which is
    left untouched: exit_reason is API-visible via TradeHistoryResponse, and
    the 17 existing rows are not backfilled.

    Full closes only. Partial exits (TP1/TP2/partial_profit_taker) survive in
    trades.strategy and are out of scope (owner decision 2026-08-07).
    """

    HARD_STOP = "HARD_STOP"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT = "TAKE_PROFIT"
    MAX_HOLD = "MAX_HOLD"
    MANUAL = "MANUAL"
    SIGNAL_REVERSAL = "SIGNAL_REVERSAL"
    LIQUIDATION = "LIQUIDATION"
