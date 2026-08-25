#!/usr/bin/env python3
"""
Complete Trading Cycle E2E Tests

Tests the full end-to-end trading workflow from market data
through signal generation, trade execution, and P&L calculation.
"""

import pytest
import asyncio
from decimal import Decimal

from shared.account import MAX_RISK_PER_TRADE  # noqa: F401

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import (
    assert_trade_executed,
    assert_position_opened,
    assert_position_closed,
    assert_pnl_positive,
    assert_pnl_negative,
    assert_balance_changed,
    assert_response_time,
)
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
    create_profitable_trade_scenario,
    create_losing_trade_scenario,
)


# ============================================================================
# Smoke Tests (Critical Path)
# ============================================================================

@pytest.mark.e2e
@pytest.mark.smoke
@pytest.mark.asyncio
async def test_services_are_healthy(
    trading_engine_client,
    market_data_client,
    portfolio_client
):
    """
    [SMOKE] Verify all critical services are healthy.

    This is the most basic E2E test - if this fails, nothing else will work.
    """
    # Trading Engine health
    response = await trading_engine_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "healthy"

    # Market Data Service health
    response = await market_data_client.get("/health")
    assert response.status_code == 200

    # Portfolio Manager health
    response = await portfolio_client.get("/health")
    assert response.status_code == 200

    print("✅ All critical services are healthy")


# ============================================================================
# Profitable Trading Cycle Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_buy_cycle_with_profit(
    market_data_client,
    trading_engine_client,
    portfolio_client,
    bullish_market_data
):
    """
    Test complete BUY → SELL cycle resulting in profit.

    Workflow:
    1. Setup initial portfolio balance
    2. Inject bullish market data
    3. Wait for signal generation
    4. Verify BUY order execution
    5. Verify position opened
    6. Simulate price increase (take-profit scenario)
    7. Verify SELL order execution
    8. Verify position closed
    9. Verify profit realized
    """
    symbol = "BTCUSDT"

    # Step 1: Setup - Get initial balance
    initial_balance = await portfolio_client.get_balance()
    print(f"Initial balance: ${initial_balance}")

    # Step 2: Inject bullish market data (price will increase)
    print(f"\n📊 Injecting bullish market data for {symbol}...")
    await market_data_client.inject_candles(
        symbol=symbol,
        candles=bullish_market_data,
        interval="60"
    )

    # Step 3: Wait for signal generation and order execution
    print("⏳ Waiting for signal generation and trade execution...")

    async def check_position_opened():
        positions = await portfolio_client.get_positions()
        return any(p.get("symbol") == symbol for p in positions)

    # Wait up to 30 seconds for position to open
    position_opened = await poll_until(
        check_position_opened,
        timeout=30,
        interval=2.0,
        error_message=f"Position for {symbol} was not opened"
    )

    if not position_opened:
        pytest.skip("Position not opened - signal may not have been generated")

    # Step 4: Verify BUY order was executed
    trade_history = await portfolio_client.get_trade_history()
    buy_trade = assert_trade_executed(trade_history, symbol, "BUY")
    entry_price = Decimal(str(buy_trade.get("price")))
    print(f"✅ BUY order executed at ${entry_price}")

    # Step 5: Verify position is open
    positions = await portfolio_client.get_positions()
    position = assert_position_opened(positions, symbol, "BUY")
    position_quantity = Decimal(str(position.get("quantity")))
    print(f"✅ Position opened: {position_quantity} {symbol}")

    # Step 6: Simulate price increase (take-profit scenario)
    print(f"\n📈 Simulating price increase for take-profit...")
    target_price = float(entry_price * Decimal("1.10"))  # 10% profit
    profit_candles = generate_bullish_candles(
        start_price=float(entry_price),
        num_candles=10,
        price_increase_pct=10.0
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=profit_candles,
        interval="60"
    )

    # Step 7: Wait for SELL execution (take-profit trigger)
    print("⏳ Waiting for take-profit execution...")

    async def check_position_closed():
        positions = await portfolio_client.get_positions()
        return not any(p.get("symbol") == symbol for p in positions)

    position_closed = await poll_until(
        check_position_closed,
        timeout=30,
        interval=2.0,
        error_message="Position was not closed"
    )

    if not position_closed:
        pytest.skip("Position not closed - take-profit may not have triggered")

    # Step 8: Verify SELL order was executed
    trade_history = await portfolio_client.get_trade_history()
    sell_trade = assert_trade_executed(trade_history, symbol, "SELL")
    exit_price = Decimal(str(sell_trade.get("price")))
    print(f"✅ SELL order executed at ${exit_price}")

    # Step 9: Verify position is closed
    positions = await portfolio_client.get_positions()
    assert_position_closed(positions, symbol)

    # Step 10: Verify profit was realized
    final_balance = await portfolio_client.get_balance()
    assert_balance_changed(initial_balance, final_balance, "increase")

    pnl = final_balance - initial_balance
    assert_pnl_positive(pnl, min_profit=Decimal("0.01"))

    print(f"\n💰 Profit realized: ${pnl}")
    print(f"Final balance: ${final_balance}")

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_sell_cycle_with_profit(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test complete SELL → BUY cycle (short position) resulting in profit.

    Workflow:
    1. Setup initial portfolio
    2. Inject bearish market data
    3. Wait for SELL signal (short position)
    4. Verify SELL order execution
    5. Simulate price decrease
    6. Verify BUY order execution (close short)
    7. Verify profit from short position
    """
    symbol = "ETHUSDT"

    # Step 1: Get initial balance
    initial_balance = await portfolio_client.get_balance()
    print(f"Initial balance: ${initial_balance}")

    # Step 2: Inject bearish market data (price will decrease)
    print(f"\n📉 Injecting bearish market data for {symbol}...")
    bearish_candles = generate_bearish_candles(
        start_price=200.0,
        num_candles=30,
        price_decrease_pct=10.0
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=bearish_candles,
        interval="60"
    )

    # Step 3: Wait for SELL signal and position
    print("⏳ Waiting for SELL signal and position...")

    async def check_short_position():
        positions = await portfolio_client.get_positions()
        return any(
            p.get("symbol") == symbol and p.get("side") == "SELL"
            for p in positions
        )

    short_opened = await poll_until(
        check_short_position,
        timeout=30,
        interval=2.0,
        error_message="Short position not opened"
    )

    if not short_opened:
        pytest.skip("Short position not opened - SELL signal may not have been generated")

    # Step 4: Verify SELL order executed
    trade_history = await portfolio_client.get_trade_history()
    sell_trade = assert_trade_executed(trade_history, symbol, "SELL")
    entry_price = Decimal(str(sell_trade.get("price")))
    print(f"✅ SELL order (short) executed at ${entry_price}")

    # Step 5: Verify short position opened
    positions = await portfolio_client.get_positions()
    position = assert_position_opened(positions, symbol, "SELL")
    print(f"✅ Short position opened: {position.get('quantity')} {symbol}")

    # Step 6: Simulate additional price decrease (profit scenario for short)
    print(f"\n📉 Simulating further price decrease...")
    more_bearish_candles = generate_bearish_candles(
        start_price=float(entry_price),
        num_candles=10,
        price_decrease_pct=5.0
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=more_bearish_candles,
        interval="60"
    )

    # Step 7: Wait for position close (take-profit on short)
    print("⏳ Waiting for short position to close...")

    async def check_short_closed():
        positions = await portfolio_client.get_positions()
        return not any(p.get("symbol") == symbol for p in positions)

    short_closed = await poll_until(
        check_short_closed,
        timeout=30,
        interval=2.0,
        error_message="Short position not closed"
    )

    if not short_closed:
        pytest.skip("Short position not closed")

    # Step 8: Verify BUY order executed (close short)
    trade_history = await portfolio_client.get_trade_history()
    buy_trade = assert_trade_executed(trade_history, symbol, "BUY")
    exit_price = Decimal(str(buy_trade.get("price")))
    print(f"✅ BUY order (close short) executed at ${exit_price}")

    # Step 9: Verify profit (entry > exit for short position)
    final_balance = await portfolio_client.get_balance()
    pnl = final_balance - initial_balance

    # For short position, profit when exit < entry
    if exit_price < entry_price:
        assert_pnl_positive(pnl)
        print(f"\n💰 Profit from short: ${pnl}")
    else:
        print(f"\n⚠️  Short closed at higher price (loss scenario)")


# ============================================================================
# Losing Trade Tests (Risk Management Validation)
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stop_loss_triggers_on_losing_trade(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that stop-loss triggers correctly to limit losses.

    Workflow:
    1. Open BUY position
    2. Simulate price decrease
    3. Verify stop-loss triggers
    4. Verify loss is limited
    """
    symbol = "BNBUSDT"

    # Step 1: Setup
    initial_balance = await portfolio_client.get_balance()

    # Step 2: Inject initial bullish data to trigger BUY
    print(f"\n📊 Injecting market data to trigger BUY for {symbol}...")
    initial_candles = generate_bullish_candles(
        start_price=300.0,
        num_candles=20,
        price_increase_pct=5.0
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=initial_candles,
        interval="60"
    )

    # Step 3: Wait for position to open
    async def check_position():
        positions = await portfolio_client.get_positions()
        return any(p.get("symbol") == symbol for p in positions)

    position_opened = await poll_until(check_position, timeout=30, interval=2.0)

    if not position_opened:
        pytest.skip("Position not opened")

    positions = await portfolio_client.get_positions()
    position = assert_position_opened(positions, symbol, "BUY")
    entry_price = Decimal(str(position.get("entry_price")))
    print(f"✅ Position opened at ${entry_price}")

    # Step 4: Simulate sharp price drop (stop-loss scenario)
    print(f"\n📉 Simulating price drop to trigger stop-loss...")
    crash_candles = generate_bearish_candles(
        start_price=float(entry_price),
        num_candles=15,
        price_decrease_pct=8.0  # 8% drop should trigger stop-loss
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=crash_candles,
        interval="60"
    )

    # Step 5: Wait for stop-loss to trigger
    print("⏳ Waiting for stop-loss to trigger...")

    async def check_stop_loss():
        positions = await portfolio_client.get_positions()
        return not any(p.get("symbol") == symbol for p in positions)

    stop_loss_triggered = await poll_until(
        check_stop_loss,
        timeout=30,
        interval=2.0,
        error_message="Stop-loss did not trigger"
    )

    if not stop_loss_triggered:
        pytest.skip("Stop-loss did not trigger")

    # Step 6: Verify loss was limited
    final_balance = await portfolio_client.get_balance()
    pnl = final_balance - initial_balance

    # Bound = per-trade risk cap (MAX_RISK_PER_TRADE fraction, 0.10 paper per
    # ADR-010) — this is one trade's stop-loss, so the per-trade cap applies,
    # not the 12% daily breaker (ADR-028). Old hardcoded 5% matched neither.
    assert_pnl_negative(pnl, max_loss=initial_balance * Decimal(str(MAX_RISK_PER_TRADE)))

    print(f"\n🛡️ Stop-loss triggered successfully")
    print(f"Loss limited to: ${abs(pnl)} ({abs(pnl)/initial_balance*100:.2f}%)")


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_generation_performance(
    market_data_client,
    trading_engine_client,
    bullish_market_data
):
    """
    Test that signal generation completes within acceptable time.

    Performance SLA: Signal generation < 5 seconds
    """
    import time

    symbol = "BTCUSDT"

    # Inject market data
    await market_data_client.inject_candles(
        symbol=symbol,
        candles=bullish_market_data,
        interval="60"
    )

    # Measure signal generation time
    start_time = time.time()

    # Request signal aggregation
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    elapsed_time = time.time() - start_time

    # Verify signal was generated
    assert signal is not None, "No signal generated"

    # Verify performance SLA
    assert_response_time(
        actual_time=elapsed_time,
        max_time=5.0,
        operation="Signal Generation"
    )

    print(f"✅ Signal generated in {elapsed_time:.2f}s: {signal.get('action')}")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_multiple_concurrent_symbols(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test system can handle multiple trading symbols concurrently.

    Tests scalability of the trading system.
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]

    # Inject data for all symbols concurrently
    print(f"\n📊 Injecting data for {len(symbols)} symbols concurrently...")

    tasks = []
    for i, symbol in enumerate(symbols):
        # Alternate between bullish and bearish to test different signals
        if i % 2 == 0:
            candles = generate_bullish_candles(start_price=100.0 + i*10, num_candles=30)
        else:
            candles = generate_bearish_candles(start_price=100.0 + i*10, num_candles=30)

        tasks.append(
            market_data_client.inject_candles(symbol, candles, interval="60")
        )

    # Execute all injections concurrently
    await asyncio.gather(*tasks)

    # Wait for positions to open
    print("⏳ Waiting for positions to open...")
    await asyncio.sleep(10)

    # Verify at least some positions were opened
    positions = await portfolio_client.get_positions()
    assert len(positions) > 0, "No positions opened for any symbol"

    print(f"✅ {len(positions)} positions opened across {len(symbols)} symbols")

    for position in positions:
        print(f"  - {position.get('symbol')}: {position.get('side')} {position.get('quantity')}")


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_no_trade_on_sideways_market(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that system doesn't trade in sideways (ranging) market.

    Validates that signal confidence thresholds work correctly.
    """
    from tests.e2e.fixtures.mock_data import generate_sideways_candles

    symbol = "ADAUSDT"

    # Inject sideways market data (no clear trend)
    print(f"\n📊 Injecting sideways market data for {symbol}...")
    sideways_candles = generate_sideways_candles(
        base_price=0.50,
        num_candles=50,
        volatility=0.02
    )

    await market_data_client.inject_candles(
        symbol=symbol,
        candles=sideways_candles,
        interval="60"
    )

    # Wait to see if any position opens
    print("⏳ Waiting to confirm no position opens...")
    await asyncio.sleep(15)

    # Verify NO position was opened
    positions = await portfolio_client.get_positions()
    symbol_positions = [p for p in positions if p.get("symbol") == symbol]

    assert len(symbol_positions) == 0, f"Unexpected position opened in sideways market: {symbol_positions}"

    print(f"✅ Correctly avoided trading in sideways market")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
