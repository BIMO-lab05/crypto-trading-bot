#!/usr/bin/env python3
"""
Custom Assertions for E2E Testing

Provides domain-specific assertions for trading bot E2E tests.
"""

from typing import Dict, List, Optional, Any
from decimal import Decimal


class E2EAssertionError(AssertionError):
    """Custom assertion error for E2E tests."""
    pass


def assert_trade_executed(
    trade_history: List[Dict],
    symbol: str,
    side: str,
    min_quantity: Optional[Decimal] = None
) -> Dict:
    """
    Assert that a trade was executed successfully.

    Args:
        trade_history: List of trade records
        symbol: Trading symbol (e.g., "BTCUSDT")
        side: Trade side ("BUY" or "SELL")
        min_quantity: Minimum expected quantity

    Returns:
        The matching trade record

    Raises:
        E2EAssertionError: If trade not found or doesn't match criteria
    """
    matching_trades = [
        trade for trade in trade_history
        if trade.get("symbol") == symbol and trade.get("side") == side
    ]

    if not matching_trades:
        raise E2EAssertionError(
            f"No {side} trade found for {symbol}. "
            f"Trade history: {trade_history}"
        )

    latest_trade = matching_trades[-1]  # Get most recent

    if min_quantity is not None:
        trade_quantity = Decimal(str(latest_trade.get("quantity", 0)))
        if trade_quantity < min_quantity:
            raise E2EAssertionError(
                f"Trade quantity {trade_quantity} is less than "
                f"minimum {min_quantity}"
            )

    print(f"✅ Found {side} trade for {symbol}: {latest_trade}")
    return latest_trade


def assert_position_opened(
    positions: List[Dict],
    symbol: str,
    side: str,
    min_quantity: Optional[Decimal] = None
) -> Dict:
    """
    Assert that a position was opened.

    Args:
        positions: List of current positions
        symbol: Trading symbol
        side: Position side ("BUY" or "SELL")
        min_quantity: Minimum expected quantity

    Returns:
        The matching position

    Raises:
        E2EAssertionError: If position not found
    """
    matching_positions = [
        pos for pos in positions
        if pos.get("symbol") == symbol and pos.get("side") == side
    ]

    if not matching_positions:
        raise E2EAssertionError(
            f"No {side} position found for {symbol}. "
            f"Current positions: {positions}"
        )

    position = matching_positions[0]

    if min_quantity is not None:
        pos_quantity = Decimal(str(position.get("quantity", 0)))
        if pos_quantity < min_quantity:
            raise E2EAssertionError(
                f"Position quantity {pos_quantity} is less than "
                f"minimum {min_quantity}"
            )

    print(f"✅ Found {side} position for {symbol}: {position}")
    return position


def assert_position_closed(
    positions: List[Dict],
    symbol: str
):
    """
    Assert that a position was closed (no longer exists).

    Args:
        positions: List of current positions
        symbol: Trading symbol

    Raises:
        E2EAssertionError: If position still exists
    """
    open_positions = [
        pos for pos in positions
        if pos.get("symbol") == symbol
    ]

    if open_positions:
        raise E2EAssertionError(
            f"Position for {symbol} is still open: {open_positions[0]}"
        )

    print(f"✅ Position for {symbol} is closed")


def assert_pnl_positive(
    pnl: Decimal,
    min_profit: Optional[Decimal] = None
):
    """
    Assert that profit/loss is positive.

    Args:
        pnl: Profit/loss value
        min_profit: Minimum expected profit

    Raises:
        E2EAssertionError: If P&L is not positive or below minimum
    """
    if pnl <= 0:
        raise E2EAssertionError(
            f"Expected positive P&L, got {pnl}"
        )

    if min_profit is not None and pnl < min_profit:
        raise E2EAssertionError(
            f"P&L {pnl} is less than minimum expected {min_profit}"
        )

    print(f"✅ P&L is positive: {pnl}")


def assert_pnl_negative(
    pnl: Decimal,
    max_loss: Optional[Decimal] = None
):
    """
    Assert that profit/loss is negative (loss).

    Args:
        pnl: Profit/loss value
        max_loss: Maximum acceptable loss (as positive number)

    Raises:
        E2EAssertionError: If P&L is not negative or exceeds max loss
    """
    if pnl >= 0:
        raise E2EAssertionError(
            f"Expected negative P&L (loss), got {pnl}"
        )

    if max_loss is not None and abs(pnl) > max_loss:
        raise E2EAssertionError(
            f"Loss {abs(pnl)} exceeds maximum acceptable loss {max_loss}"
        )

    print(f"✅ P&L is negative (loss): {pnl}")


def assert_signal_generated(
    signal: Dict,
    expected_action: str,
    min_confidence: Optional[float] = None
):
    """
    Assert that a valid trading signal was generated.

    Args:
        signal: Signal dictionary
        expected_action: Expected action ("BUY", "SELL", or "HOLD")
        min_confidence: Minimum confidence threshold (0-1)

    Raises:
        E2EAssertionError: If signal is invalid or doesn't match criteria
    """
    action = signal.get("action")
    confidence = signal.get("confidence", 0)

    if action != expected_action:
        raise E2EAssertionError(
            f"Expected signal action {expected_action}, got {action}"
        )

    if min_confidence is not None and confidence < min_confidence:
        raise E2EAssertionError(
            f"Signal confidence {confidence} is below minimum {min_confidence}"
        )

    print(f"✅ Signal generated: {action} (confidence: {confidence:.2f})")


def assert_balance_changed(
    initial_balance: Decimal,
    final_balance: Decimal,
    expected_change: str,  # "increase", "decrease", or "unchanged"
    min_change: Optional[Decimal] = None
):
    """
    Assert that account balance changed as expected.

    Args:
        initial_balance: Starting balance
        final_balance: Ending balance
        expected_change: Expected direction of change
        min_change: Minimum expected change amount

    Raises:
        E2EAssertionError: If balance didn't change as expected
    """
    change = final_balance - initial_balance

    if expected_change == "increase" and change <= 0:
        raise E2EAssertionError(
            f"Expected balance increase, got change of {change}"
        )

    if expected_change == "decrease" and change >= 0:
        raise E2EAssertionError(
            f"Expected balance decrease, got change of {change}"
        )

    if expected_change == "unchanged" and change != 0:
        raise E2EAssertionError(
            f"Expected no balance change, got change of {change}"
        )

    if min_change is not None and abs(change) < min_change:
        raise E2EAssertionError(
            f"Balance change {abs(change)} is less than minimum {min_change}"
        )

    print(f"✅ Balance changed from {initial_balance} to {final_balance} ({change:+})")


def assert_risk_check_passed(response: Dict):
    """
    Assert that risk check passed.

    Args:
        response: Risk check response

    Raises:
        E2EAssertionError: If risk check failed
    """
    approved = response.get("approved", False)
    reason = response.get("reason", "Unknown")

    if not approved:
        raise E2EAssertionError(
            f"Risk check failed: {reason}"
        )

    print(f"✅ Risk check passed")


def assert_risk_check_blocked(response: Dict, expected_reason: Optional[str] = None):
    """
    Assert that risk check blocked the trade.

    Args:
        response: Risk check response
        expected_reason: Expected blocking reason (substring match)

    Raises:
        E2EAssertionError: If risk check didn't block as expected
    """
    approved = response.get("approved", True)
    reason = response.get("reason", "")

    if approved:
        raise E2EAssertionError(
            f"Expected risk check to block trade, but it was approved"
        )

    if expected_reason and expected_reason.lower() not in reason.lower():
        raise E2EAssertionError(
            f"Expected block reason to contain '{expected_reason}', "
            f"got '{reason}'"
        )

    print(f"✅ Risk check correctly blocked trade: {reason}")


def assert_service_healthy(health_response: Dict, service_name: str = "Service"):
    """
    Assert that a service is healthy.

    Args:
        health_response: Health check response
        service_name: Name of the service (for error messages)

    Raises:
        E2EAssertionError: If service is not healthy
    """
    status = health_response.get("status", "unknown")

    if status != "healthy":
        raise E2EAssertionError(
            f"{service_name} is not healthy. Status: {status}, "
            f"Response: {health_response}"
        )

    print(f"✅ {service_name} is healthy")


def assert_indicator_value(
    indicators: Dict,
    indicator_name: str,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    expected_signal: Optional[str] = None
):
    """
    Assert that a technical indicator has expected value/signal.

    Args:
        indicators: Dictionary of indicators
        indicator_name: Name of the indicator (e.g., "RSI", "MACD")
        min_value: Minimum expected value
        max_value: Maximum expected value
        expected_signal: Expected signal ("BUY", "SELL", "NEUTRAL")

    Raises:
        E2EAssertionError: If indicator doesn't match criteria
    """
    if indicator_name not in indicators:
        raise E2EAssertionError(
            f"Indicator '{indicator_name}' not found in {list(indicators.keys())}"
        )

    indicator = indicators[indicator_name]
    value = indicator.get("value")
    signal = indicator.get("signal")

    if min_value is not None and value < min_value:
        raise E2EAssertionError(
            f"{indicator_name} value {value} is below minimum {min_value}"
        )

    if max_value is not None and value > max_value:
        raise E2EAssertionError(
            f"{indicator_name} value {value} exceeds maximum {max_value}"
        )

    if expected_signal is not None and signal != expected_signal:
        raise E2EAssertionError(
            f"{indicator_name} signal is {signal}, expected {expected_signal}"
        )

    print(f"✅ {indicator_name}: value={value}, signal={signal}")


def assert_response_time(
    actual_time: float,
    max_time: float,
    operation: str = "Operation"
):
    """
    Assert that an operation completed within acceptable time.

    Args:
        actual_time: Actual execution time in seconds
        max_time: Maximum acceptable time in seconds
        operation: Description of the operation

    Raises:
        E2EAssertionError: If operation took too long
    """
    if actual_time > max_time:
        raise E2EAssertionError(
            f"{operation} took {actual_time:.2f}s, "
            f"exceeds maximum {max_time:.2f}s"
        )

    print(f"✅ {operation} completed in {actual_time:.2f}s (< {max_time:.2f}s)")


def assert_data_freshness(
    timestamp: float,
    max_age_seconds: int = 60,
    data_type: str = "Data"
):
    """
    Assert that data is fresh (not stale).

    Args:
        timestamp: Unix timestamp of the data
        max_age_seconds: Maximum acceptable age in seconds
        data_type: Description of the data

    Raises:
        E2EAssertionError: If data is too old
    """
    import time

    current_time = time.time()
    age_seconds = current_time - timestamp

    if age_seconds > max_age_seconds:
        raise E2EAssertionError(
            f"{data_type} is {age_seconds:.0f}s old, "
            f"exceeds maximum age {max_age_seconds}s"
        )

    print(f"✅ {data_type} is fresh ({age_seconds:.1f}s old)")


def assert_within_range(
    value: Any,
    min_value: Any,
    max_value: Any,
    description: str = "Value"
):
    """
    Assert that a value is within expected range.

    Args:
        value: The value to check
        min_value: Minimum acceptable value
        max_value: Maximum acceptable value
        description: Description of the value

    Raises:
        E2EAssertionError: If value is out of range
    """
    if value < min_value or value > max_value:
        raise E2EAssertionError(
            f"{description} {value} is outside range [{min_value}, {max_value}]"
        )

    print(f"✅ {description} {value} is within range [{min_value}, {max_value}]")


def assert_list_not_empty(items: List, description: str = "List"):
    """
    Assert that a list is not empty.

    Args:
        items: List to check
        description: Description of the list

    Raises:
        E2EAssertionError: If list is empty
    """
    if not items:
        raise E2EAssertionError(f"{description} is empty")

    print(f"✅ {description} contains {len(items)} item(s)")


def assert_dict_contains_keys(
    data: Dict,
    required_keys: List[str],
    description: str = "Data"
):
    """
    Assert that a dictionary contains required keys.

    Args:
        data: Dictionary to check
        required_keys: List of required keys
        description: Description of the data

    Raises:
        E2EAssertionError: If any required key is missing
    """
    missing_keys = [key for key in required_keys if key not in data]

    if missing_keys:
        raise E2EAssertionError(
            f"{description} missing required keys: {missing_keys}. "
            f"Available keys: {list(data.keys())}"
        )

    print(f"✅ {description} contains all required keys: {required_keys}")
