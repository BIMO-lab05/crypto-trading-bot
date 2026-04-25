#!/usr/bin/env python3
"""
Test Grid Trading v1 Strategy with CSV Historical Data
=======================================================
Uses real historical data from Bybit API instead of generated data.

Data Source: /mnt/d/Bimo_max/crypto-trading-bot/data/historical/
File Format: {SYMBOL}_180days_20251208.csv
CSV Columns: timestamp,open,high,low,close,volume,turnover

Available Symbols:
- BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, ADAUSDT
- APTUSDT, DOTUSDT, LTCUSDT, POLUSDT, AVAXUSDT

Comparison Goal:
- Baseline: 32.6% win rate (old Grid v1 with generated data)
- New Test: Grid v1 with real market data

Author: Grid Trading v1 CSV Data Testing
Date: 2025-12-08
"""

import sys
import os
from datetime import datetime
from typing import Dict, List
import pandas as pd

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'trading-engine'))

from app.strategies.grid_trading_strategy import GridTradingStrategy
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.backtesting.strategy_base import OHLCV


def load_csv_data(symbol: str, data_dir: str = "/mnt/d/Bimo_max/crypto-trading-bot/data/historical") -> List[OHLCV]:
    """
    Load CSV historical data and convert to OHLCV format

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')
        data_dir: Directory containing CSV files

    Returns:
        List[OHLCV]: List of OHLCV bars for backtesting

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV has invalid format
    """
    # Construct CSV filename
    csv_file = os.path.join(data_dir, f"{symbol}_180days_20251208.csv")

    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    print(f"📂 Loading data from: {csv_file}")

    # Read CSV with pandas
    df = pd.read_csv(csv_file)

    # Validate required columns
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"CSV missing required columns: {missing_columns}")

    # Convert timestamp strings to datetime objects
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Convert DataFrame rows to OHLCV objects
    bars = []
    for _, row in df.iterrows():
        bar = OHLCV(
            timestamp=row['timestamp'].to_pydatetime(),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume']),
        )
        bars.append(bar)

    print(f"✓ Loaded {len(bars)} bars from {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
    print(f"  Volume range: {df['volume'].min():.2f} - {df['volume'].max():.2f}")

    return bars


def run_grid_v1_backtest(symbol: str, use_filters: bool = True) -> Dict:
    """
    Run backtest for Grid Trading v1 with CSV data

    Args:
        symbol: Trading pair to test
        use_filters: Whether to use ADX/RSI/Volume filters

    Returns:
        Dict with backtest results
    """
    print(f"\n{'='*80}")
    print(f"🚀 Testing Grid Trading v1 ({'WITH' if use_filters else 'WITHOUT'} filters) on {symbol}")
    print(f"{'='*80}\n")

    # Load CSV data
    try:
        bars = load_csv_data(symbol)
    except Exception as e:
        print(f"❌ Error loading data for {symbol}: {e}")
        return {
            'symbol': symbol,
            'with_filters': use_filters,
            'win_rate': 0,
            'total_return': 0,
            'sharpe_ratio': 0,
            'total_trades': 0,
            'profit_factor': 0,
            'error': str(e)
        }

    # Temporarily modify filter constants if needed
    if not use_filters:
        # Monkey-patch to disable filters for baseline test
        import app.strategies.grid_trading_strategy as grid_module
        original_adx = grid_module.USE_ADX_FILTER
        original_rsi = grid_module.USE_RSI_FILTER
        original_volume = grid_module.USE_VOLUME_FILTER

        grid_module.USE_ADX_FILTER = False
        grid_module.USE_RSI_FILTER = False
        grid_module.USE_VOLUME_FILTER = False

    # Create Grid Trading v1 strategy with standard parameters
    strategy = GridTradingStrategy(
        symbol=symbol,
        grid_levels=10,           # 10 grid levels
        grid_range_pct=0.10,      # 10% range
        use_atr_spacing=True,     # ATR-based spacing
        max_positions=5,          # Max 5 concurrent positions
        position_size_pct=0.02,   # 2% per position
    )

    # Create backtest configuration
    config = BacktestConfig(
        initial_equity=10000.0,    # $10,000 starting capital
        commission_pct=0.1,        # 0.1% commission (Bybit spot)
        slippage_pct=0.05,         # 0.05% slippage
        position_size_pct=2.0,     # 2% per position (matches strategy)
        max_positions=5,           # Max 5 concurrent positions
        use_stop_loss=True,        # Use stop loss
        use_take_profit=True,      # Use take profit
    )

    # Create backtest engine
    engine = BacktestEngine(config)

    # Run backtest
    print(f"⏳ Running backtest on {len(bars)} bars...")
    result: BacktestResult = engine.run(strategy, bars)

    # Restore original filter settings
    if not use_filters:
        grid_module.USE_ADX_FILTER = original_adx
        grid_module.USE_RSI_FILTER = original_rsi
        grid_module.USE_VOLUME_FILTER = original_volume

    # Extract metrics from result
    metrics = result.metrics
    win_rate = metrics.win_rate

    # Display results
    print(f"\n{'='*80}")
    print(f"📊 GRID TRADING V1 RESULTS ({'WITH' if use_filters else 'WITHOUT'} filters) - {symbol}")
    print(f"{'='*80}")
    print(f"Total Return:    {metrics.total_return_pct:>8.2f}%")

    # Check if win rate meets target
    target_met = "✓" if win_rate >= 80 else "✗"
    baseline_met = "✓" if win_rate >= 32.6 else "✗"
    print(f"Win Rate:        {win_rate:>8.1f}% {target_met} (Target: 80% | Baseline: 32.6% {baseline_met})")

    print(f"Sharpe Ratio:    {metrics.sharpe_ratio:>8.2f}")
    print(f"Max Drawdown:    {metrics.max_drawdown_pct:>8.2f}%")
    print(f"Total Trades:    {metrics.total_trades:>8}")
    print(f"Winning Trades:  {metrics.winning_trades:>8}")
    print(f"Losing Trades:   {metrics.losing_trades:>8}")
    print(f"Profit Factor:   {metrics.profit_factor:>8.2f}")
    print(f"Avg Win:       $ {metrics.avg_win:>8.2f}")
    print(f"Avg Loss:      $ {metrics.avg_loss:>8.2f}")
    print(f"{'='*80}\n")

    return {
        'symbol': symbol,
        'with_filters': use_filters,
        'win_rate': win_rate,
        'total_return': metrics.total_return_pct,
        'sharpe_ratio': metrics.sharpe_ratio,
        'max_drawdown': metrics.max_drawdown_pct,
        'total_trades': metrics.total_trades,
        'winning_trades': metrics.winning_trades,
        'losing_trades': metrics.losing_trades,
        'profit_factor': metrics.profit_factor,
    }


def compare_with_baseline(results: List[Dict]):
    """
    Compare results with baseline (32.6% win rate from generated data)

    Args:
        results: List of backtest results for all symbols
    """
    print(f"\n{'='*80}")
    print("📈 COMPARISON: CSV DATA vs BASELINE (Generated Data)")
    print(f"{'='*80}\n")

    # Baseline from original Grid v1 with generated data
    baseline_win_rate = 32.6

    # Calculate average win rate from CSV data tests
    valid_results = [r for r in results if 'error' not in r]
    if not valid_results:
        print("❌ No valid results to compare")
        return

    avg_win_rate = sum(r['win_rate'] for r in valid_results) / len(valid_results)
    avg_return = sum(r['total_return'] for r in valid_results) / len(valid_results)
    avg_sharpe = sum(r['sharpe_ratio'] for r in valid_results) / len(valid_results)
    total_trades = sum(r['total_trades'] for r in valid_results)

    # Print per-symbol results
    print(f"{'Symbol':<12} {'Win Rate':>12} {'Return':>12} {'Sharpe':>12} {'Trades':>10} {'Status':>10}")
    print(f"{'-'*80}")
    for r in results:
        if 'error' in r:
            print(f"{r['symbol']:<12} {'ERROR':>12} {'-':>12} {'-':>12} {'-':>10} {'✗':>10}")
        else:
            # Status indicators
            vs_baseline = "✓" if r['win_rate'] > baseline_win_rate else "✗"
            vs_target = "🎯" if r['win_rate'] >= 80 else "⚠"
            status = f"{vs_baseline} {vs_target}"

            print(f"{r['symbol']:<12} {r['win_rate']:>11.1f}% {r['total_return']:>11.2f}% "
                  f"{r['sharpe_ratio']:>12.2f} {r['total_trades']:>10} {status:>10}")

    print(f"{'-'*80}")
    print(f"{'AVERAGE':<12} {avg_win_rate:>11.1f}% {avg_return:>11.2f}% "
          f"{avg_sharpe:>12.2f} {total_trades:>10}")
    print(f"{'='*80}\n")

    # Improvement analysis
    improvement = avg_win_rate - baseline_win_rate

    print(f"🏆 ANALYSIS:")
    print(f"   Baseline (Generated Data):  {baseline_win_rate:.1f}% win rate")
    print(f"   CSV Data Average:           {avg_win_rate:.1f}% win rate")
    print(f"   Difference:                 {improvement:+.1f}%")
    print(f"   Gap to 80% target:          {80 - avg_win_rate:.1f}%")
    print()

    # Verdict
    if avg_win_rate >= 80:
        print(f"   ✅ SUCCESS! Achieved >80% win rate target with real data!")
    elif avg_win_rate > baseline_win_rate:
        print(f"   ⚠️  Real data shows {'BETTER' if improvement > 0 else 'WORSE'} performance than generated data")
        print(f"      Improvement: {improvement:+.1f}%")
        print(f"      This {'validates' if improvement > 0 else 'questions'} the strategy's effectiveness")
    else:
        print(f"   ❌ Real data performance below baseline")
        print(f"      Strategy may need adjustment for real market conditions")

    print(f"\n💡 DATA SOURCE:")
    print(f"   Real Market Data: 180 days of hourly OHLCV from Bybit")
    print(f"   Period: June 2025 - December 2025")
    print(f"   Symbols Tested: {len(valid_results)}")
    print(f"   Total Bars Analyzed: ~{len(valid_results) * 4320:,} (approximate)")
    print(f"{'='*80}\n")


def main():
    """Main test execution with CSV data"""
    print(f"{'='*80}")
    print("🧪 GRID TRADING V1 - CSV HISTORICAL DATA TEST")
    print(f"{'='*80}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Goal: Test Grid v1 with real Bybit historical data")
    print(f"Baseline: 32.6% win rate (from generated data)")
    print(f"Target: >80% win rate")
    print(f"Data Source: CSV files from Bybit API")
    print(f"{'='*80}\n")

    # All available symbols
    symbols = [
        'BTCUSDT',   # Bitcoin
        'ETHUSDT',   # Ethereum
        'SOLUSDT',   # Solana
        'BNBUSDT',   # Binance Coin
        'ADAUSDT',   # Cardano
        'APTUSDT',   # Aptos
        'DOTUSDT',   # Polkadot
        'LTCUSDT',   # Litecoin
        'POLUSDT',   # Polygon
        'AVAXUSDT',  # Avalanche
    ]

    print(f"📊 Testing {len(symbols)} symbols with real market data\n")

    # Collect results for all symbols (with filters enabled)
    all_results = []

    for i, symbol in enumerate(symbols, 1):
        print(f"\n{'#'*80}")
        print(f"# [{i}/{len(symbols)}] TESTING {symbol} - GRID V1 WITH FILTERS")
        print(f"{'#'*80}")

        result = run_grid_v1_backtest(symbol, use_filters=True)
        all_results.append(result)

    # Compare with baseline
    compare_with_baseline(all_results)

    # Final summary
    print(f"\n{'='*80}")
    print("✅ CSV DATA TESTING COMPLETE")
    print(f"{'='*80}")
    print(f"Symbols Tested: {len(symbols)}")
    print(f"Data Period: 180 days (hourly bars)")
    print(f"Data Source: Bybit API historical data")
    print(f"Strategy: Grid Trading v1 with ADX/RSI/Volume filters")
    print(f"Baseline Comparison: 32.6% win rate (generated data)")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
