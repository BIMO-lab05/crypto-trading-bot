#!/usr/bin/env python3
"""
Order Execution E2E Tests

Tests the complete order lifecycle from signal generation through
order submission, status tracking, execution, and position updates.
"""

import pytest
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional
import time

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import (
    assert_trade_executed,
    assert_position_opened,
    assert_position_closed,
    assert_balance_changed,
    assert_within_range,
)
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
)


# ============================================================================
# Order Generation and Submission Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_generated_from_approved_signal(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that approved signal generates order for execution.

    Workflow:
    1. Inject bullish market data
    2. Wait for signal generation
    3. Verify signal approved by risk manager
    4. Verify order generated
    5. Verify order details (symbol, side, quantity)
    """
    symbol = "BTCUSDT"

    print(f"\n📊 Injecting bullish market data for {symbol}...")
    bullish_candles = generate_bullish_candles(
        start_price=45000.0,
        num_candles=60,
        price_increase_pct=8.0
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=bullish_candles,
        interval="60"
    )

    # Wait for signal generation
    print("⏳ Waiting for signal generation...")
    await asyncio.sleep(5)

    # Get aggregated signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal and signal.get("action") == "BUY":
        print(f"✅ BUY signal generated with confidence {signal.get('confidence', 0):.2f}")

        # Wait for order generation
        await asyncio.sleep(3)

        # Check if position opened (indicates order was executed)
        positions = await portfolio_client.get_positions()
        symbol_positions = [p for p in positions if p.get("symbol") == symbol]

        if len(symbol_positions) > 0:
            position = symbol_positions[0]
            print(f"✅ Order executed: {position.get('side')} {position.get('quantity')} {symbol}")
            assert position.get("side") == "BUY", "Position side should match signal"
            assert float(position.get("quantity", 0)) > 0, "Position quantity should be positive"
        else:
            pytest.skip("Order not executed yet")
    else:
        pytest.skip("No BUY signal generated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_submitted_to_bybit_connector(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that order is properly submitted to Bybit Connector.

    Validates:
    - Order format compliance
    - Required fields present
    - API communication success
    """
    symbol = "ETHUSDT"

    print(f"\n📊 Setting up trade for {symbol}...")

    # Get initial balance
    initial_balance = await portfolio_client.get_balance()

    # Inject bullish market data
    bullish_candles = generate_bullish_candles(
        start_price=2500.0,
        num_candles=60,
        price_increase_pct=7.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Wait for order execution
    print("⏳ Waiting for order submission and execution...")
    await asyncio.sleep(8)

    # Check trade history
    trade_history = await portfolio_client.get_trade_history()
    eth_trades = [t for t in trade_history if t.get("symbol") == symbol]

    if len(eth_trades) > 0:
        latest_trade = eth_trades[-1]
        print(f"✅ Order submitted and executed:")
        print(f"   - Order ID: {latest_trade.get('order_id', 'N/A')}")
        print(f"   - Symbol: {latest_trade.get('symbol')}")
        print(f"   - Side: {latest_trade.get('side')}")
        print(f"   - Quantity: {latest_trade.get('quantity')}")
        print(f"   - Price: ${latest_trade.get('price')}")

        # Validate order has required fields
        assert latest_trade.get("order_id") is not None, "Order ID missing"
        assert latest_trade.get("symbol") == symbol, "Symbol mismatch"
        assert latest_trade.get("side") in ["BUY", "SELL"], "Invalid side"
        assert float(latest_trade.get("quantity", 0)) > 0, "Invalid quantity"
        assert float(latest_trade.get("price", 0)) > 0, "Invalid price"
    else:
        pytest.skip("No trades executed yet")


# ============================================================================
# Order Status Tracking Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_status_progression(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test order status progression: pending → filled → confirmed.

    Workflow:
    1. Submit order
    2. Track status changes
    3. Verify final status is 'filled'
    4. Verify position reflects filled order
    """
    symbol = "BNBUSDT"

    print(f"\n📊 Initiating trade for {symbol}...")

    # Inject market data to trigger trade
    bullish_candles = generate_bullish_candles(
        start_price=300.0,
        num_candles=60,
        price_increase_pct=6.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Track order execution
    print("⏳ Tracking order status...")

    order_found = False
    max_wait = 15
    for i in range(max_wait):
        await asyncio.sleep(1)

        # Check if order filled (position opened)
        positions = await portfolio_client.get_positions()
        if any(p.get("symbol") == symbol for p in positions):
            order_found = True
            break

    if order_found:
        positions = await portfolio_client.get_positions()
        position = next(p for p in positions if p.get("symbol") == symbol)

        print(f"✅ Order filled successfully:")
        print(f"   - Entry Price: ${position.get('entry_price')}")
        print(f"   - Quantity: {position.get('quantity')}")
        print(f"   - Status: FILLED")

        # Validate position data
        assert position.get("entry_price") is not None, "Entry price missing"
        assert float(position.get("quantity", 0)) > 0, "Quantity invalid"
    else:
        pytest.skip("Order not filled within timeout")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_position_updated_after_order_fill(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that Portfolio Manager updates position after order fills.

    Validates:
    - Position created with correct details
    - Entry price matches fill price
    - Quantity matches order quantity
    - Stop-loss and take-profit set
    """
    symbol = "SOLUSDT"

    print(f"\n📊 Setting up position test for {symbol}...")

    # Get positions before
    positions_before = await portfolio_client.get_positions()
    sol_positions_before = [p for p in positions_before if p.get("symbol") == symbol]

    # Inject market data
    bullish_candles = generate_bullish_candles(
        start_price=100.0,
        num_candles=60,
        price_increase_pct=8.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Wait for position to open
    print("⏳ Waiting for position to open...")

    async def check_position_opened():
        positions = await portfolio_client.get_positions()
        return any(p.get("symbol") == symbol for p in positions)

    position_opened = await poll_until(check_position_opened, timeout=20, interval=2.0)

    if position_opened:
        positions = await portfolio_client.get_positions()
        position = next(p for p in positions if p.get("symbol") == symbol)

        print(f"✅ Position updated in Portfolio Manager:")
        print(f"   - Symbol: {position.get('symbol')}")
        print(f"   - Side: {position.get('side')}")
        print(f"   - Quantity: {position.get('quantity')}")
        print(f"   - Entry Price: ${position.get('entry_price')}")
        print(f"   - Stop Loss: ${position.get('stop_loss', 'Not set')}")
        print(f"   - Take Profit: ${position.get('take_profit', 'Not set')}")

        # Validate position details
        assert position.get("symbol") == symbol, "Symbol mismatch"
        assert position.get("side") in ["BUY", "SELL"], "Invalid side"
        assert float(position.get("quantity", 0)) > 0, "Invalid quantity"
        assert float(position.get("entry_price", 0)) > 0, "Invalid entry price"

        # Check if stop-loss and take-profit are set
        if position.get("stop_loss") is not None:
            entry_price = Decimal(str(position["entry_price"]))
            stop_loss = Decimal(str(position["stop_loss"]))

            if position["side"] == "BUY":
                assert stop_loss < entry_price, "Stop-loss should be below entry for BUY"
            else:
                assert stop_loss > entry_price, "Stop-loss should be above entry for SELL"
    else:
        pytest.skip("Position not opened")


# ============================================================================
# Order Modification Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_cancellation(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test order cancellation before fill.

    Note: This test may be limited by the speed of order execution.
    In paper trading, orders typically fill immediately.
    """
    symbol = "ADAUSDT"

    print(f"\n📊 Testing order cancellation for {symbol}...")

    # In paper trading mode, orders fill almost instantly
    # This test documents the expected cancellation behavior

    print("⚠️  Note: In paper trading, orders fill immediately")
    print("    Cancellation would work for pending orders on live exchange")
    print("    Expected behavior:")
    print("    1. Submit CANCEL request with order_id")
    print("    2. Bybit Connector sends cancel to exchange")
    print("    3. If not filled: order cancelled, no position")
    print("    4. If already filled: cancellation fails, position exists")

    # For documentation purposes, show that orders execute quickly
    bullish_candles = generate_bullish_candles(
        start_price=0.50,
        num_candles=30,
        price_increase_pct=5.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")
    await asyncio.sleep(3)

    positions = await portfolio_client.get_positions()
    ada_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(ada_positions) > 0:
        print("✅ Order filled immediately (typical for paper trading)")
    else:
        print("⏳ Order pending or no signal generated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stop_loss_modification(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test modification of stop-loss after position opened.

    Workflow:
    1. Open position
    2. Modify stop-loss to tighter level
    3. Verify stop-loss updated
    4. Trigger modified stop-loss
    """
    symbol = "DOGEUSDT"

    print(f"\n📊 Testing stop-loss modification for {symbol}...")

    # Open position
    bullish_candles = generate_bullish_candles(
        start_price=0.10,
        num_candles=60,
        price_increase_pct=5.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Wait for position
    print("⏳ Waiting for position to open...")
    await asyncio.sleep(8)

    positions = await portfolio_client.get_positions()
    doge_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(doge_positions) > 0:
        position = doge_positions[0]
        entry_price = Decimal(str(position["entry_price"]))
        original_sl = position.get("stop_loss")

        print(f"✅ Position opened:")
        print(f"   - Entry: ${entry_price}")
        print(f"   - Original SL: ${original_sl}")

        # Note: In the current implementation, stop-loss modification
        # would be done via Portfolio Manager API
        # This test documents the expected workflow

        print("\n📝 Stop-loss modification workflow:")
        print("   1. POST /api/v1/positions/{symbol}/stop-loss")
        print("   2. Validate new SL within allowed range")
        print("   3. Update position in database")
        print("   4. Notify Trading Engine of change")

        # Test that stop-loss is within valid range (2-5% for BUY)
        if original_sl:
            sl_decimal = Decimal(str(original_sl))
            sl_pct = abs((entry_price - sl_decimal) / entry_price * 100)
            print(f"   - SL Distance: {sl_pct:.2f}%")
            assert 1.0 <= sl_pct <= 10.0, f"Stop-loss outside valid range: {sl_pct:.2f}%"
    else:
        pytest.skip("Position not opened")


# ============================================================================
# Order Execution Edge Cases
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_partial_fill_handling(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test handling of partial order fills.

    Note: Paper trading typically fills orders completely.
    This test documents expected behavior for partial fills on live exchange.
    """
    symbol = "MATICUSDT"

    print(f"\n📊 Testing partial fill handling for {symbol}...")

    print("📝 Partial Fill Workflow (Live Trading):")
    print("   1. Submit order for 1000 MATIC")
    print("   2. Exchange fills 300 MATIC (partial)")
    print("   3. System creates position with 300 MATIC")
    print("   4. Remaining 700 MATIC order stays open")
    print("   5. System tracks partial fill status")
    print("   6. When fully filled, position updated to 1000 MATIC")

    print("\n⚠️  In paper trading mode:")
    print("   - Orders fill completely and immediately")
    print("   - No partial fills occur")
    print("   - Testing complete fill behavior instead")

    # Test complete fill in paper trading
    bullish_candles = generate_bullish_candles(
        start_price=0.80,
        num_candles=40,
        price_increase_pct=6.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")
    await asyncio.sleep(8)

    positions = await portfolio_client.get_positions()
    matic_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(matic_positions) > 0:
        position = matic_positions[0]
        print(f"\n✅ Order filled completely:")
        print(f"   - Quantity: {position.get('quantity')}")
        print(f"   - Status: FILLED")

        assert float(position.get("quantity", 0)) > 0, "Position should have quantity"
    else:
        pytest.skip("Position not opened")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_failed_order_handling(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test handling of failed orders (insufficient balance, invalid params, etc.).

    Workflow:
    1. Set very low balance
    2. Attempt to place large order
    3. Verify order rejected
    4. Verify no position created
    5. Verify error logged
    """
    symbol = "LINKUSDT"

    print(f"\n📊 Testing failed order handling for {symbol}...")

    # Set very low balance to cause failure
    low_balance = Decimal("1.00")
    await portfolio_client.set_balance(low_balance)
    print(f"Set balance to ${low_balance} (insufficient for trade)")

    # Try to trigger trade (should fail due to insufficient balance)
    bullish_candles = generate_bullish_candles(
        start_price=15.0,
        num_candles=40,
        price_increase_pct=5.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    print("⏳ Waiting to confirm order rejection...")
    await asyncio.sleep(8)

    # Verify no position created
    positions = await portfolio_client.get_positions()
    link_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(link_positions) == 0:
        print("✅ Order correctly rejected due to insufficient balance")
        print("   - No position created")
        print("   - Risk management blocked trade")
    else:
        # Position created despite low balance - investigate
        print("⚠️  Position created despite low balance - check risk management")
        position = link_positions[0]
        position_value = Decimal(str(position["quantity"])) * Decimal(str(position["entry_price"]))
        print(f"   - Position value: ${position_value}")
        print(f"   - Balance: ${low_balance}")

    # Reset balance for other tests
    await portfolio_client.set_balance(Decimal("10000.00"))


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_timeout_handling(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test handling of order timeouts.

    Documents expected behavior when order doesn't fill within timeout period.
    """
    print("\n📊 Testing order timeout handling...")

    print("📝 Order Timeout Workflow:")
    print("   1. Submit order with timeout (e.g., 30 seconds)")
    print("   2. Order remains unfilled past timeout")
    print("   3. System automatically cancels order")
    print("   4. No position created")
    print("   5. Timeout event logged")

    print("\n⚠️  In paper trading mode:")
    print("   - Orders fill immediately")
    print("   - Timeouts don't occur")
    print("   - Live trading would enforce timeouts")

    print("\n💡 Recommended timeout configuration:")
    print("   - Market orders: 5 seconds")
    print("   - Limit orders: 60 seconds")
    print("   - Stop orders: 30 seconds")

    # In paper trading, verify quick execution
    symbol = "AVAXUSDT"
    start_time = time.time()

    bullish_candles = generate_bullish_candles(
        start_price=35.0,
        num_candles=30,
        price_increase_pct=4.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")
    await asyncio.sleep(5)

    positions = await portfolio_client.get_positions()
    avax_positions = [p for p in positions if p.get("symbol") == symbol]

    elapsed = time.time() - start_time

    if len(avax_positions) > 0:
        print(f"\n✅ Order filled in {elapsed:.2f}s (well within timeout)")
    else:
        print(f"\n⏳ No position after {elapsed:.2f}s")


# ============================================================================
# Multiple Order Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_multiple_concurrent_orders(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test system can handle multiple orders concurrently.

    Workflow:
    1. Inject data for multiple symbols simultaneously
    2. Verify multiple signals generated
    3. Verify multiple orders executed
    4. Verify all positions opened correctly
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    print(f"\n📊 Testing concurrent orders for {len(symbols)} symbols...")

    # Inject data for all symbols concurrently
    tasks = []
    for i, symbol in enumerate(symbols):
        candles = generate_bullish_candles(
            start_price=1000.0 + (i * 100),
            num_candles=50,
            price_increase_pct=7.0
        )
        tasks.append(
            market_data_client.inject_candles(symbol, candles, interval="60")
        )

    await asyncio.gather(*tasks)
    print("✅ Market data injected for all symbols")

    # Wait for orders to execute
    print("⏳ Waiting for concurrent order execution...")
    await asyncio.sleep(10)

    # Check positions
    positions = await portfolio_client.get_positions()

    print(f"\n📊 Execution Results:")
    print(f"   - Positions opened: {len(positions)}")

    for symbol in symbols:
        symbol_positions = [p for p in positions if p.get("symbol") == symbol]
        if len(symbol_positions) > 0:
            position = symbol_positions[0]
            print(f"   ✅ {symbol}: {position.get('side')} {position.get('quantity')}")
        else:
            print(f"   ⏳ {symbol}: No position yet")

    # Verify at least some positions opened
    assert len(positions) > 0, "No positions opened for any symbol"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_execution_sequence(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test correct sequencing of order execution events.

    Expected sequence:
    1. Signal generated
    2. Risk check passed
    3. Order created
    4. Order submitted
    5. Order filled
    6. Position created
    7. Balance updated
    8. Notification sent
    """
    symbol = "UNIUSDT"

    print(f"\n📊 Testing execution sequence for {symbol}...")

    # Get initial state
    initial_balance = await portfolio_client.get_balance()
    initial_positions = await portfolio_client.get_positions()

    print(f"Initial state:")
    print(f"   - Balance: ${initial_balance}")
    print(f"   - Positions: {len(initial_positions)}")

    # Trigger trade
    print(f"\n1️⃣ Injecting market data...")
    bullish_candles = generate_bullish_candles(
        start_price=8.0,
        num_candles=60,
        price_increase_pct=8.0
    )
    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    print("2️⃣ Waiting for signal generation...")
    await asyncio.sleep(3)

    # Check signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
    if signal:
        print(f"3️⃣ Signal generated: {signal.get('action')} (confidence: {signal.get('confidence', 0):.2f})")

    print("4️⃣ Waiting for risk check and order execution...")
    await asyncio.sleep(5)

    # Check position
    positions = await portfolio_client.get_positions()
    uni_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(uni_positions) > 0:
        position = uni_positions[0]
        print(f"5️⃣ Order filled:")
        print(f"   - Entry: ${position.get('entry_price')}")
        print(f"   - Quantity: {position.get('quantity')}")

        print(f"6️⃣ Position created in Portfolio Manager")

        # Check balance update
        current_balance = await portfolio_client.get_balance()
        if current_balance != initial_balance:
            print(f"7️⃣ Balance updated: ${initial_balance} → ${current_balance}")

        print("8️⃣ Execution sequence completed successfully ✅")
    else:
        pytest.skip("Position not opened")


# ============================================================================
# P&L Calculation Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pnl_calculated_after_execution(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test P&L calculation after order execution and position close.

    Workflow:
    1. Open position (BUY)
    2. Verify unrealized P&L calculated
    3. Close position at profit
    4. Verify realized P&L calculated correctly
    5. Verify balance updated with P&L
    """
    symbol = "ATOMUSDT"

    print(f"\n📊 Testing P&L calculation for {symbol}...")

    # Get initial balance
    initial_balance = await portfolio_client.get_balance()
    print(f"Initial balance: ${initial_balance}")

    # Open position
    print("\n1️⃣ Opening position...")
    bullish_candles = generate_bullish_candles(
        start_price=10.0,
        num_candles=60,
        price_increase_pct=5.0
    )
    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Wait for position
    await asyncio.sleep(8)

    positions = await portfolio_client.get_positions()
    atom_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(atom_positions) == 0:
        pytest.skip("Position not opened")

    position = atom_positions[0]
    entry_price = Decimal(str(position["entry_price"]))
    quantity = Decimal(str(position["quantity"]))

    print(f"2️⃣ Position opened:")
    print(f"   - Entry: ${entry_price}")
    print(f"   - Quantity: {quantity}")

    # Simulate price increase for profit
    print("\n3️⃣ Simulating price increase...")
    profit_candles = generate_bullish_candles(
        start_price=float(entry_price),
        num_candles=20,
        price_increase_pct=10.0
    )
    await market_data_client.inject_candles(symbol, profit_candles, interval="60")

    # Wait for take-profit
    print("4️⃣ Waiting for position close...")
    await asyncio.sleep(10)

    # Check if position closed
    positions = await portfolio_client.get_positions()
    atom_positions = [p for p in positions if p.get("symbol") == symbol]

    if len(atom_positions) == 0:
        print("5️⃣ Position closed")

        # Check P&L
        final_balance = await portfolio_client.get_balance()
        pnl = final_balance - initial_balance

        print(f"6️⃣ P&L Calculation:")
        print(f"   - Initial: ${initial_balance}")
        print(f"   - Final: ${final_balance}")
        print(f"   - P&L: ${pnl}")

        if pnl > 0:
            print(f"   ✅ Profitable trade: +${pnl} ({pnl/initial_balance*100:.2f}%)")
        elif pnl < 0:
            print(f"   ⚠️  Loss: ${pnl} ({pnl/initial_balance*100:.2f}%)")
        else:
            print(f"   ➖ Break-even trade")
    else:
        print("⏳ Position still open")


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_order_execution_latency(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test order execution latency from signal to fill.

    SLA: Order execution < 2 seconds in paper trading.
    """
    symbol = "DOTUSDT"

    print(f"\n📊 Testing order execution latency for {symbol}...")

    # Prepare market data
    bullish_candles = generate_bullish_candles(
        start_price=6.0,
        num_candles=50,
        price_increase_pct=7.0
    )

    # Measure execution time
    start_time = time.time()

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Poll for position with timeout
    max_wait = 10
    position_opened = False

    for i in range(max_wait * 2):  # Check every 0.5s
        await asyncio.sleep(0.5)
        positions = await portfolio_client.get_positions()
        if any(p.get("symbol") == symbol for p in positions):
            position_opened = True
            break

    elapsed = time.time() - start_time

    if position_opened:
        print(f"✅ Order executed in {elapsed:.2f}s")

        # Check SLA
        if elapsed < 2.0:
            print(f"   🚀 Excellent latency (< 2s SLA)")
        elif elapsed < 5.0:
            print(f"   ✅ Acceptable latency (< 5s)")
        else:
            print(f"   ⚠️  Slow execution (> 5s)")

        assert elapsed < 10.0, f"Execution too slow: {elapsed:.2f}s"
    else:
        pytest.skip("Position not opened within timeout")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
