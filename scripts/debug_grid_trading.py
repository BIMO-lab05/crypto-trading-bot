#!/usr/bin/env python3
"""
Debug script to test Grid Trading signal generation
Tests if the strategy can generate signals on simulated data
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "trading-engine"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

from app.backtesting.strategy_base import OHLCV
from app.strategies.grid_trading_strategy import GridTradingStrategy


# Create simple oscillating price data
def create_oscillating_data(start_price=100, periods=200):
    """Create price data that oscillates between 90 and 110"""
    bars = []
    base_time = datetime(2025, 1, 1)

    for i in range(periods):
        # Oscillate between 90 and 110
        price = start_price + 10 * ((i % 40) - 20) / 20

        bar = OHLCV(
            timestamp=base_time + timedelta(hours=i),
            open=price - 0.5,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1000
        )
        bars.append(bar)

    return bars


def test_grid_strategy():
    """Test grid strategy on simple data"""

    # Create strategy
    strategy = GridTradingStrategy(
        symbol="TESTUSDT",
        grid_levels=10,
        grid_range_pct=0.10,
        use_atr_spacing=False,  # Use fixed spacing for predictability
        max_positions=5,
        position_size_pct=0.02,
    )

    # Create oscillating data
    bars = create_oscillating_data(start_price=100, periods=200)

    print(f"Testing Grid Trading Strategy")
    print(f"=================================")
    print(f"Data: {len(bars)} bars, oscillating 90-110")
    print(f"Grid: 10 levels, ±10%, fixed spacing\n")

    signals_generated = 0
    equity = ACCOUNT_EQUITY_USD

    # Simulate trading
    for i, bar in enumerate(bars):
        # Add bar to strategy
        strategy.add_bar(bar)

        # DEBUG: Capture prev_price BEFORE on_bar() updates it
        prev_price_before = strategy._prev_price if strategy._prev_price else None

        # Get signal
        signal = strategy.on_bar(bar, equity)

        # Debug: Show grid state after initialization
        if i == 20 and strategy._grid_initialized and strategy.grid_state:
            print(f"\nGrid State at bar {i}:")
            buy_levels = strategy.grid_state.get_buy_levels()
            sell_levels = strategy.grid_state.get_sell_levels()
            print(f"  Buy levels: {[f'${lvl.price:.2f}' for lvl in buy_levels]}")
            print(f"  Sell levels: {[f'${lvl.price:.2f}' for lvl in sell_levels]}")
            print(f"  Active positions: {strategy.grid_state.active_positions}")
            print(f"  Last rebalance price: ${strategy.grid_state.last_rebalance_price:.2f}\n")

        # Debug: Track rebalancing events
        if strategy._grid_initialized and signal is None and prev_price_before is not None:
            # Check if grid was rebalanced this bar
            if strategy.grid_state and strategy.grid_state.last_rebalance_price == bar.close:
                print(f"⚠️  Bar {i}: Grid REBALANCED at ${bar.close:.2f}")

        # Debug: Show detailed price movement analysis for critical bars
        if strategy._grid_initialized and 58 <= i <= 65:
            if prev_price_before is not None:
                price_direction = "DOWN" if bar.close < prev_price_before else ("UP" if bar.close > prev_price_before else "FLAT")

                print(f"\nBar {i}: ${prev_price_before:.2f} -> ${bar.close:.2f} ({price_direction})")
                print(f"  Active positions: {strategy.grid_state.active_positions}")

                # Check which buy levels were crossed
                if bar.close <= prev_price_before:
                    buy_levels = strategy.grid_state.get_buy_levels()
                    crossed = [
                        lvl for lvl in buy_levels
                        if not lvl.is_filled and prev_price_before >= lvl.price >= bar.close
                    ]
                    if crossed:
                        print(f"  Crossed BUY levels: {[f'${lvl.price:.2f}' for lvl in crossed]}")
                        print(f"  Can add position? {strategy.grid_state.active_positions < strategy.max_positions}")
                    else:
                        print(f"  No buy levels crossed")

                # Check which sell levels were crossed
                elif bar.close >= prev_price_before:
                    sell_levels = strategy.grid_state.get_sell_levels()
                    crossed = [
                        lvl for lvl in sell_levels
                        if not lvl.is_filled and prev_price_before <= lvl.price <= bar.close
                    ]
                    if crossed:
                        print(f"  Crossed SELL levels: {[f'${lvl.price:.2f}' for lvl in crossed]}")
                        print(f"  Have positions? {strategy.grid_state.active_positions > 0}")
                    else:
                        print(f"  No sell levels crossed")

        if signal:
            signals_generated += 1
            print(f"\n✓✓✓ Bar {i}: SIGNAL {signal.signal_type.value} at ${bar.close:.2f} ✓✓✓\n")

    print(f"\n=================================")
    print(f"Total signals generated: {signals_generated}")
    print(f"Grid initialized: {strategy._grid_initialized}")
    if strategy.grid_state:
        print(f"Active positions: {strategy.grid_state.active_positions}")


if __name__ == "__main__":
    test_grid_strategy()
