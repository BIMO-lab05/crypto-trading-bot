#!/usr/bin/env python3
"""
Squeeze Momentum Indicator (SQZMOM) - Usage Examples
This script demonstrates how to use the SQZMOM indicator and strategy.

Usage:
    python examples/sqzmom_example.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from app.indicators.squeeze_momentum import SqueezeMomentumIndicator
from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy


def create_sample_data(num_candles=100, trend='bullish'):
    """
    Create sample OHLCV data for testing

    Args:
        num_candles: Number of candles to generate
        trend: 'bullish', 'bearish', or 'sideways'

    Returns:
        DataFrame with OHLCV data
    """
    np.random.seed(42)

    # Base price
    base_price = 100

    # Generate prices based on trend
    if trend == 'bullish':
        # Uptrend with some noise
        close_prices = [base_price + i * 2 + np.random.randn() * 3 for i in range(num_candles)]
    elif trend == 'bearish':
        # Downtrend with some noise
        close_prices = [base_price - i * 2 + np.random.randn() * 3 for i in range(num_candles)]
    else:  # sideways
        # Sideways with noise
        close_prices = [base_price + np.random.randn() * 5 for i in range(num_candles)]

    # Generate OHLC from close
    data = {
        'timestamp': [1700000000 + i * 3600 for i in range(num_candles)],
        'open': [p + np.random.randn() * 0.5 for p in close_prices],
        'high': [p + abs(np.random.randn()) * 3 for p in close_prices],
        'low': [p - abs(np.random.randn()) * 3 for p in close_prices],
        'close': close_prices,
        'volume': [1000 + np.random.randint(-200, 200) for _ in range(num_candles)]
    }

    return pd.DataFrame(data)


def example_1_basic_indicator():
    """
    Example 1: Basic SQZMOM indicator usage
    """
    print("=" * 80)
    print("EXAMPLE 1: Basic SQZMOM Indicator Usage")
    print("=" * 80)

    # Create sample data
    df = create_sample_data(num_candles=100, trend='bullish')

    # Initialize indicator with default parameters
    indicator = SqueezeMomentumIndicator()

    # Calculate indicator
    print("\nCalculating SQZMOM indicator...")
    result_df = indicator.calculate(df)

    if result_df is not None:
        print(f"✓ Calculation successful! {len(result_df)} candles processed")

        # Show last 5 rows
        print("\nLast 5 candles:")
        print(result_df[['close', 'squeeze_on', 'squeeze_off', 'sqz_momentum', 'sqz_color', 'sqz_signal']].tail())

        # Get current signal
        signal = indicator.get_signal(df)
        print("\n" + "=" * 40)
        print("Current Signal:")
        print("=" * 40)
        print(f"Action: {signal['signal']}")
        print(f"Confidence: {signal['confidence']:.2f}")
        print(f"Squeeze ON: {signal['squeeze_on']}")
        print(f"Squeeze OFF: {signal['squeeze_off']}")
        print(f"Momentum: {signal['momentum']:.4f}")
        print(f"Color: {signal['color']}")
        print(f"Strength: {signal['strength']:.2f}")
    else:
        print("✗ Calculation failed (insufficient data?)")


def example_2_custom_parameters():
    """
    Example 2: Using custom parameters
    """
    print("\n\n" + "=" * 80)
    print("EXAMPLE 2: Custom Parameters (Aggressive Settings)")
    print("=" * 80)

    # Create sample data
    df = create_sample_data(num_candles=100, trend='bullish')

    # Initialize with aggressive parameters
    indicator = SqueezeMomentumIndicator(
        bb_length=15,       # Shorter period = more sensitive
        bb_mult=1.8,        # Tighter bands
        kc_length=15,
        kc_mult=1.3,
        use_true_range=True
    )

    print("\nParameters:")
    print(f"  BB: {indicator.bb_length} period, {indicator.bb_mult}x std dev")
    print(f"  KC: {indicator.kc_length} period, {indicator.kc_mult}x ATR")
    print(f"  True Range: {indicator.use_true_range}")

    # Calculate
    result_df = indicator.calculate(df)

    if result_df is not None:
        # Count squeeze occurrences
        squeeze_on_count = result_df['squeeze_on'].sum()
        squeeze_off_count = result_df['squeeze_off'].sum()

        print(f"\nResults:")
        print(f"  Squeeze ON: {squeeze_on_count}/{len(result_df)} candles ({squeeze_on_count/len(result_df)*100:.1f}%)")
        print(f"  Squeeze OFF: {squeeze_off_count}/{len(result_df)} candles ({squeeze_off_count/len(result_df)*100:.1f}%)")

        # Count signals
        buy_signals = (result_df['sqz_signal'] == 'BUY').sum()
        sell_signals = (result_df['sqz_signal'] == 'SELL').sum()
        hold_signals = (result_df['sqz_signal'] == 'HOLD').sum()

        print(f"\nSignals:")
        print(f"  BUY: {buy_signals}")
        print(f"  SELL: {sell_signals}")
        print(f"  HOLD: {hold_signals}")


def example_3_strategy_usage():
    """
    Example 3: Using the trading strategy
    """
    print("\n\n" + "=" * 80)
    print("EXAMPLE 3: SQZMOM Trading Strategy")
    print("=" * 80)

    # Create sample data
    df = create_sample_data(num_candles=100, trend='bullish')

    # Initialize indicator and strategy
    indicator = SqueezeMomentumIndicator()
    strategy = SqueezeMomentumStrategy(
        sqzmom_indicator=indicator,
        min_momentum_threshold=0.5,
        stop_loss_pct=2.0,
        take_profit_pct=4.0,
        require_squeeze_release=True,
        require_volume_confirmation=False
    )

    print("\nStrategy Configuration:")
    print(f"  Min Momentum: {strategy.min_momentum}")
    print(f"  Stop Loss: {strategy.stop_loss_pct}%")
    print(f"  Take Profit: {strategy.take_profit_pct}%")
    print(f"  Require Squeeze Release: {strategy.require_squeeze_release}")

    # Analyze market
    analysis = strategy.analyze(df)

    print("\n" + "=" * 40)
    print("Strategy Analysis:")
    print("=" * 40)
    print(f"Action: {analysis['action']}")
    print(f"Confidence: {analysis['confidence']:.2f}")
    print(f"Entry Price: ${analysis.get('entry_price', 0):.2f}")
    print(f"Stop Loss: ${analysis.get('stop_loss', 0):.2f}")
    print(f"Take Profit: ${analysis.get('take_profit', 0):.2f}")
    print(f"Reason: {analysis['reason']}")
    print(f"Momentum: {analysis.get('momentum', 0):.4f}")
    print(f"Squeeze State: {analysis.get('squeeze_state', 'N/A')}")


def example_4_different_market_conditions():
    """
    Example 4: Testing on different market conditions
    """
    print("\n\n" + "=" * 80)
    print("EXAMPLE 4: Different Market Conditions")
    print("=" * 80)

    trends = ['bullish', 'bearish', 'sideways']
    indicator = SqueezeMomentumIndicator()

    for trend in trends:
        print(f"\n{'-' * 40}")
        print(f"{trend.upper()} Market:")
        print(f"{'-' * 40}")

        # Create data
        df = create_sample_data(num_candles=100, trend=trend)

        # Get signal
        signal = indicator.get_signal(df)

        if signal:
            print(f"Signal: {signal['signal']}")
            print(f"Confidence: {signal['confidence']:.2f}")
            print(f"Momentum: {signal['momentum']:.4f} ({signal['color']})")
            print(f"Squeeze: {'ON' if signal['squeeze_on'] else 'OFF' if signal['squeeze_off'] else 'Transitional'}")


def example_5_backtesting_simulation():
    """
    Example 5: Simple backtesting simulation
    """
    print("\n\n" + "=" * 80)
    print("EXAMPLE 5: Simple Backtesting Simulation")
    print("=" * 80)

    # Create longer dataset
    df = create_sample_data(num_candles=500, trend='bullish')

    # Initialize strategy
    indicator = SqueezeMomentumIndicator()
    strategy = SqueezeMomentumStrategy(
        sqzmom_indicator=indicator,
        min_momentum_threshold=0.5,
        require_squeeze_release=True
    )

    # Calculate indicator for entire dataset
    result_df = indicator.calculate(df)

    if result_df is None:
        print("Failed to calculate indicator")
        return

    # Simulate trades
    trades = []
    position = None

    for i in range(len(result_df)):
        current_row = result_df.iloc[i]
        signal = current_row['sqz_signal']
        price = current_row['close']

        # Entry logic
        if position is None:
            if signal == 'BUY':
                position = {
                    'type': 'LONG',
                    'entry_price': price,
                    'entry_index': i,
                    'stop_loss': price * (1 - 0.02),
                    'take_profit': price * (1 + 0.04)
                }
            elif signal == 'SELL':
                position = {
                    'type': 'SHORT',
                    'entry_price': price,
                    'entry_index': i,
                    'stop_loss': price * (1 + 0.02),
                    'take_profit': price * (1 - 0.04)
                }

        # Exit logic
        elif position:
            should_exit = False
            exit_reason = ''

            if position['type'] == 'LONG':
                if price <= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop Loss'
                elif price >= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Take Profit'
                elif signal == 'SELL':
                    should_exit = True
                    exit_reason = 'Signal Reversal'
            else:  # SHORT
                if price >= position['stop_loss']:
                    should_exit = True
                    exit_reason = 'Stop Loss'
                elif price <= position['take_profit']:
                    should_exit = True
                    exit_reason = 'Take Profit'
                elif signal == 'BUY':
                    should_exit = True
                    exit_reason = 'Signal Reversal'

            if should_exit:
                # Calculate P&L
                if position['type'] == 'LONG':
                    pnl_pct = ((price - position['entry_price']) / position['entry_price']) * 100
                else:
                    pnl_pct = ((position['entry_price'] - price) / position['entry_price']) * 100

                trades.append({
                    'type': position['type'],
                    'entry_price': position['entry_price'],
                    'exit_price': price,
                    'pnl_pct': pnl_pct,
                    'exit_reason': exit_reason,
                    'bars_held': i - position['entry_index']
                })

                position = None

    # Display results
    if trades:
        print(f"\nBacktest Results ({len(trades)} trades):")
        print("=" * 60)

        winning_trades = [t for t in trades if t['pnl_pct'] > 0]
        losing_trades = [t for t in trades if t['pnl_pct'] <= 0]

        print(f"Total Trades: {len(trades)}")
        print(f"Winning Trades: {len(winning_trades)} ({len(winning_trades)/len(trades)*100:.1f}%)")
        print(f"Losing Trades: {len(losing_trades)} ({len(losing_trades)/len(trades)*100:.1f}%)")

        total_pnl = sum(t['pnl_pct'] for t in trades)
        avg_win = sum(t['pnl_pct'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t['pnl_pct'] for t in losing_trades) / len(losing_trades) if losing_trades else 0

        print(f"\nPerformance:")
        print(f"Total P&L: {total_pnl:.2f}%")
        print(f"Average Win: {avg_win:.2f}%")
        print(f"Average Loss: {avg_loss:.2f}%")
        if avg_loss != 0:
            print(f"Win/Loss Ratio: {abs(avg_win/avg_loss):.2f}")

        print(f"\nFirst 5 Trades:")
        for i, trade in enumerate(trades[:5], 1):
            print(f"  {i}. {trade['type']}: {trade['pnl_pct']:+.2f}% ({trade['exit_reason']})")
    else:
        print("No trades executed")


def main():
    """Run all examples"""
    print("\n")
    print("*" * 80)
    print("SQUEEZE MOMENTUM INDICATOR (SQZMOM) - USAGE EXAMPLES")
    print("*" * 80)

    try:
        # Run examples
        example_1_basic_indicator()
        example_2_custom_parameters()
        example_3_strategy_usage()
        example_4_different_market_conditions()
        example_5_backtesting_simulation()

        print("\n\n" + "=" * 80)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print("\nNext Steps:")
        print("1. Test with real market data from your exchange")
        print("2. Optimize parameters for your specific trading pairs")
        print("3. Backtest on historical data")
        print("4. Paper trade before going live")
        print("\nAPI Documentation: http://localhost:8003/docs")
        print("Full Documentation: /docs/SQZMOM_INDICATOR.md")
        print("=" * 80)

    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
