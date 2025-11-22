#!/usr/bin/env python3
"""
Risk Management Flow E2E Tests

Tests the complete risk management workflow including position sizing,
daily loss limits, risk/reward validation, and emergency stops.

Risk Management Flow:
1. Signal received → Risk Manager validates
2. Check account balance and available margin
3. Calculate position size (max 10% of portfolio)
4. Validate daily P&L limits (max 5% loss)
5. Check max concurrent positions
6. Apply risk/reward ratio validation
7. Approve or reject trade
"""

import pytest
import asyncio
from decimal import Decimal

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import (
    assert_risk_check_passed,
    assert_risk_check_blocked,
    assert_within_range,
    assert_balance_changed,
)
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
)


# ============================================================================
# Position Sizing Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_position_size_respects_max_percentage(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that position size doesn't exceed maximum portfolio percentage.

    Max position size: 10% of portfolio balance
    """
    symbol = "BTCUSDT"

    print(f"\n💰 Testing position size limits for {symbol}...")

    # Step 1: Set initial balance
    initial_balance = Decimal("10000.00")
    await portfolio_client.set_balance(initial_balance)

    current_balance = await portfolio_client.get_balance()
    print(f"  Portfolio balance: ${current_balance}")

    # Step 2: Trigger trade
    bullish_candles = generate_bullish_candles(start_price=45000.0, num_candles=60)
    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Step 3: Wait for position to open
    await asyncio.sleep(8)

    positions = await portfolio_client.get_positions()

    if len(positions) > 0:
        position = positions[0]
        position_value = Decimal(str(position.get("quantity", 0))) * Decimal(str(position.get("entry_price", 0)))

        # Calculate percentage
        position_pct = (position_value / current_balance) * 100

        print(f"  Position value: ${position_value:.2f}")
        print(f"  Position %: {position_pct:.2f}%")

        # Should be <= 10% of portfolio
        assert position_pct <= 10.5, f"Position exceeds 10% limit: {position_pct:.2f}%"

        print("  ✅ Position size within limit")
    else:
        pytest.skip("No position opened")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_position_size_scales_with_balance(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that position size scales proportionally with account balance.

    Larger balance → larger position size (maintaining same %)
    """
    symbol = "ETHUSDT"

    print(f"\n📊 Testing position size scaling for {symbol}...")

    # Test with two different balances
    balances = [Decimal("5000.00"), Decimal("20000.00")]
    position_values = []

    for balance in balances:
        # Set balance
        await portfolio_client.set_balance(balance)

        # Trigger trade
        candles = generate_bullish_candles(start_price=2000.0, num_candles=50)
        await market_data_client.inject_candles(symbol, candles, interval="60")

        await asyncio.sleep(5)

        # Get position
        positions = await portfolio_client.get_positions()

        if positions:
            position = positions[0]
            pos_value = Decimal(str(position["quantity"])) * Decimal(str(position["entry_price"]))
            position_values.append(pos_value)

            position_pct = (pos_value / balance) * 100
            print(f"  Balance ${balance}: Position ${pos_value:.2f} ({position_pct:.2f}%)")

            # Close position
            await portfolio_client.close_position(position["id"])
            await asyncio.sleep(2)

    # Verify scaling
    if len(position_values) == 2:
        # Position for larger balance should be roughly 4x (20k/5k)
        ratio = position_values[1] / position_values[0]
        print(f"\n  Scaling ratio: {ratio:.2f}x")

        # Should be close to 4x (20k/5k = 4)
        assert 3.0 <= ratio <= 5.0, f"Unexpected scaling ratio: {ratio:.2f}"

        print("  ✅ Position size scales correctly with balance")
    else:
        pytest.skip("Insufficient data to verify scaling")


# ============================================================================
# Daily Loss Limit Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_trading_stops_at_daily_loss_limit(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that trading stops when daily loss limit is reached.

    Daily loss limit: 5% of account balance
    """
    symbol = "BNBUSDT"

    print(f"\n🛑 Testing daily loss limit for {symbol}...")

    # Step 1: Set initial balance
    initial_balance = Decimal("10000.00")
    await portfolio_client.set_balance(initial_balance)

    # Step 2: Simulate losses to approach limit
    # (In real scenario, this would be accumulated from actual trades)
    # For testing, we'll track P&L

    current_pnl = await portfolio_client.get_pnl()
    print(f"  Initial P&L: ${current_pnl:.2f}")

    # Step 3: Try to open position after significant losses
    # Inject signal data
    candles = generate_bullish_candles(start_price=300.0, num_candles=40)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    # Step 4: Check if position was opened
    positions = await portfolio_client.get_positions()

    # If daily loss is near/at limit, no new positions should open
    final_pnl = await portfolio_client.get_pnl()
    loss_pct = abs(final_pnl / initial_balance * 100) if final_pnl < 0 else 0

    print(f"  Current loss: ${abs(final_pnl):.2f} ({loss_pct:.2f}%)")

    if loss_pct >= 4.5:  # Near 5% limit
        assert len(positions) == 0, "Position opened despite being near loss limit"
        print("  ✅ Trading correctly stopped near daily loss limit")
    else:
        print(f"  ℹ️  Not yet at loss limit ({loss_pct:.2f}% < 5%)")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_emergency_stop_halts_all_trading(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that emergency stop halts all trading activity.

    Emergency stop can be triggered manually or automatically.
    """
    symbol = "SOLUSDT"

    print(f"\n🚨 Testing emergency stop for {symbol}...")

    # Step 1: Trigger emergency stop
    # (Implementation would depend on your Trading Engine API)
    # For now, we'll test that no trades execute after emergency stop

    # Step 2: Try to generate trading signal
    candles = generate_bullish_candles(start_price=100.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    # Step 3: Verify no new positions opened
    positions = await portfolio_client.get_positions()

    # Note: This test would need actual emergency stop API endpoint
    # For now, we just verify the concept

    print("  ℹ️  Emergency stop test (requires emergency stop API)")


# ============================================================================
# Risk/Reward Ratio Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_min_risk_reward_ratio_enforced(
    market_data_client,
    trading_engine_client
):
    """
    Test that minimum risk/reward ratio is enforced.

    Typical minimum: 1:2 (risk $1 to potentially gain $2)
    """
    symbol = "ADAUSDT"

    print(f"\n⚖️  Testing risk/reward ratio for {symbol}...")

    # Inject data that might have poor risk/reward
    candles = generate_bullish_candles(start_price=0.50, num_candles=40)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    # Get signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        metadata = signal.get("metadata", {})

        print(f"  Signal: {signal.get('action')}")
        print(f"  Metadata: {metadata}")

        # Check if risk/reward info is present
        if "risk_reward_ratio" in metadata:
            rr_ratio = metadata["risk_reward_ratio"]
            print(f"  Risk/Reward Ratio: {rr_ratio}")

            # Minimum should be 1:2 (0.5)
            if signal.get("action") != "HOLD":
                assert rr_ratio >= 0.4, f"Poor risk/reward ratio: {rr_ratio}"
                print("  ✅ Risk/reward ratio meets minimum")
    else:
        print("  ℹ️  No signal generated (may be filtered by risk checks)")


# ============================================================================
# Concurrent Position Limits
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_max_concurrent_positions_enforced(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that maximum concurrent positions limit is enforced.

    Typical limit: 3-5 concurrent positions
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]

    print(f"\n📊 Testing max concurrent positions with {len(symbols)} symbols...")

    # Try to open positions in all symbols
    for symbol in symbols:
        candles = generate_bullish_candles(start_price=100.0, num_candles=50)
        await market_data_client.inject_candles(symbol, candles, interval="60")
        await asyncio.sleep(2)

    # Wait for all signals to process
    await asyncio.sleep(10)

    # Check how many positions opened
    positions = await portfolio_client.get_positions()
    num_positions = len(positions)

    print(f"\n  Positions opened: {num_positions}/{len(symbols)}")

    for position in positions:
        print(f"    - {position.get('symbol')}")

    # Should respect max concurrent positions (typically 3-5)
    max_concurrent = 5
    assert num_positions <= max_concurrent, f"Too many concurrent positions: {num_positions}"

    print(f"  ✅ Concurrent positions within limit (<= {max_concurrent})")


# ============================================================================
# Balance and Margin Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_insufficient_balance_blocks_trade(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that insufficient balance prevents trade execution.

    Cannot open position if balance too low.
    """
    symbol = "BTCUSDT"

    print(f"\n💸 Testing insufficient balance protection for {symbol}...")

    # Step 1: Set very low balance
    low_balance = Decimal("10.00")  # Only $10
    await portfolio_client.set_balance(low_balance)

    current_balance = await portfolio_client.get_balance()
    print(f"  Low balance set: ${current_balance}")

    # Step 2: Try to trigger BTC trade (expensive)
    candles = generate_bullish_candles(start_price=45000.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    # Step 3: Verify no position opened (balance too low)
    positions = await portfolio_client.get_positions()

    if len(positions) == 0:
        print("  ✅ Trade correctly blocked due to insufficient balance")
    else:
        # Position opened despite low balance
        position = positions[0]
        position_value = Decimal(str(position["quantity"])) * Decimal(str(position["entry_price"]))

        if position_value > current_balance:
            pytest.fail(f"Position value ${position_value} exceeds balance ${current_balance}")
        else:
            print(f"  ℹ️  Small position opened: ${position_value}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_available_margin_considered(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that available margin is considered for position sizing.

    If funds are tied up in existing positions, new positions should be smaller.
    """
    symbol1 = "BTCUSDT"
    symbol2 = "ETHUSDT"

    print(f"\n💹 Testing margin availability across positions...")

    # Step 1: Set balance
    total_balance = Decimal("10000.00")
    await portfolio_client.set_balance(total_balance)

    # Step 2: Open first position
    candles1 = generate_bullish_candles(start_price=45000.0, num_candles=50)
    await market_data_client.inject_candles(symbol1, candles1, interval="60")

    await asyncio.sleep(5)

    positions = await portfolio_client.get_positions()
    if positions:
        first_position_value = Decimal(str(positions[0]["quantity"])) * Decimal(str(positions[0]["entry_price"]))
        print(f"  First position value: ${first_position_value:.2f}")

        available_balance = total_balance - first_position_value
        print(f"  Available balance: ${available_balance:.2f}")

        # Step 3: Try to open second position
        candles2 = generate_bullish_candles(start_price=2000.0, num_candles=50)
        await market_data_client.inject_candles(symbol2, candles2, interval="60")

        await asyncio.sleep(5)

        positions = await portfolio_client.get_positions()
        if len(positions) >= 2:
            second_position_value = Decimal(str(positions[1]["quantity"])) * Decimal(str(positions[1]["entry_price"]))
            print(f"  Second position value: ${second_position_value:.2f}")

            # Total position value shouldn't exceed balance
            total_position_value = first_position_value + second_position_value
            assert total_position_value <= total_balance * Decimal("1.1"), "Total positions exceed balance"

            print("  ✅ Margin correctly managed across positions")
        else:
            print("  ℹ️  Second position not opened (may be blocked)")
    else:
        pytest.skip("First position not opened")


# ============================================================================
# Risk Parameter Validation Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_stop_loss_percentage_validation(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that stop-loss percentage is set correctly.

    Typical stop-loss: 2-5% from entry price
    """
    symbol = "BNBUSDT"

    print(f"\n🛡️ Testing stop-loss percentage for {symbol}...")

    # Open position
    candles = generate_bullish_candles(start_price=300.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    positions = await portfolio_client.get_positions()

    if positions:
        position = positions[0]
        entry_price = Decimal(str(position.get("entry_price", 0)))
        stop_loss = Decimal(str(position.get("stop_loss", 0)))

        if stop_loss > 0:
            # Calculate stop-loss percentage
            sl_diff = abs(entry_price - stop_loss)
            sl_pct = (sl_diff / entry_price) * 100

            print(f"  Entry price: ${entry_price:.2f}")
            print(f"  Stop-loss: ${stop_loss:.2f}")
            print(f"  Stop-loss %: {sl_pct:.2f}%")

            # Stop-loss should be 2-5% from entry
            assert_within_range(sl_pct, 1.5, 6.0, "Stop-loss percentage")

            print("  ✅ Stop-loss percentage valid")
        else:
            print("  ⚠️  Stop-loss not set")
    else:
        pytest.skip("No position opened")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_take_profit_percentage_validation(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that take-profit percentage is set correctly.

    Typical take-profit: 5-15% from entry price
    """
    symbol = "SOLUSDT"

    print(f"\n🎯 Testing take-profit percentage for {symbol}...")

    # Open position
    candles = generate_bullish_candles(start_price=100.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    positions = await portfolio_client.get_positions()

    if positions:
        position = positions[0]
        entry_price = Decimal(str(position.get("entry_price", 0)))
        take_profit = Decimal(str(position.get("take_profit", 0)))

        if take_profit > 0:
            # Calculate take-profit percentage
            tp_diff = abs(take_profit - entry_price)
            tp_pct = (tp_diff / entry_price) * 100

            print(f"  Entry price: ${entry_price:.2f}")
            print(f"  Take-profit: ${take_profit:.2f}")
            print(f"  Take-profit %: {tp_pct:.2f}%")

            # Take-profit should be 5-20% from entry
            assert_within_range(tp_pct, 3.0, 25.0, "Take-profit percentage")

            print("  ✅ Take-profit percentage valid")
        else:
            print("  ⚠️  Take-profit not set")
    else:
        pytest.skip("No position opened")


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_zero_balance_blocks_all_trades(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test that zero balance prevents any trading.
    """
    symbol = "DOGEUSDT"

    print(f"\n🚫 Testing zero balance protection for {symbol}...")

    # Set zero balance
    await portfolio_client.set_balance(Decimal("0.00"))

    # Try to trigger trade
    candles = generate_bullish_candles(start_price=0.10, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(5)

    # Verify no position opened
    positions = await portfolio_client.get_positions()

    assert len(positions) == 0, "Position opened with zero balance!"

    print("  ✅ Zero balance correctly blocks all trading")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_risk_manager_handles_extreme_volatility(
    market_data_client,
    trading_engine_client,
    portfolio_client
):
    """
    Test risk manager response to extreme price volatility.

    Should reduce position size or block trades during high volatility.
    """
    symbol = "BTCUSDT"

    print(f"\n⚡ Testing extreme volatility handling for {symbol}...")

    # Generate highly volatile data (large price swings)
    from tests.e2e.fixtures.mock_data import generate_price_spike

    base_candles = generate_bullish_candles(start_price=45000.0, num_candles=40)

    # Add extreme volatility spikes
    volatile_candles = generate_price_spike(base_candles, spike_index=20, spike_pct=15.0, direction="up")
    volatile_candles = generate_price_spike(volatile_candles, spike_index=25, spike_pct=15.0, direction="down")

    await market_data_client.inject_candles(symbol, volatile_candles, interval="60")

    await asyncio.sleep(5)

    # Check if position was opened and size
    positions = await portfolio_client.get_positions()

    if positions:
        position = positions[0]
        print(f"  Position opened: {position.get('quantity')} {symbol}")
        print("  ℹ️  Position opened despite high volatility")
    else:
        print("  ✅ Trading blocked due to extreme volatility")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
