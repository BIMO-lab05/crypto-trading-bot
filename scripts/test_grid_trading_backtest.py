#!/usr/bin/env python3
"""
Grid Trading Strategy Backtesting Script
Tests Grid Trading strategy on 180 days of historical data across multiple symbols.

Features:
- Multiple symbol testing (10 symbols)
- Configuration parameter sweep (grid levels, spacing, range)
- Market condition analysis (trending vs ranging)
- Performance comparison across configurations
- Detailed metrics and reporting
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import pandas as pd
import numpy as np

# Add trading-engine to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "trading-engine"))
sys.path.insert(0, str(Path(__file__).parent.parent))
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

from app.backtesting.strategy_base import OHLCV
from app.backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestResult
from app.strategies.grid_trading_strategy import GridTradingStrategy


# Configuration constants
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
    "ADAUSDT", "APTUSDT", "DOTUSDT", "LTCUSDT",
    "POLUSDT", "AVAXUSDT"
]

# Grid configuration test matrix
GRID_CONFIGS = [
    # Default configuration
    {
        "name": "Default (10 levels, ±10%, ATR)",
        "grid_levels": 10,
        "grid_range_pct": 0.10,
        "use_atr_spacing": True,
        "max_positions": 5,
        "position_size_pct": 0.02,
    },
    # More aggressive - tighter grid
    {
        "name": "Aggressive (15 levels, ±5%, ATR)",
        "grid_levels": 15,
        "grid_range_pct": 0.05,
        "use_atr_spacing": True,
        "max_positions": 5,
        "position_size_pct": 0.02,
    },
    # Conservative - wider grid
    {
        "name": "Conservative (7 levels, ±15%, ATR)",
        "grid_levels": 7,
        "grid_range_pct": 0.15,
        "use_atr_spacing": True,
        "max_positions": 3,
        "position_size_pct": 0.015,
    },
    # Fixed spacing (no ATR)
    {
        "name": "Fixed Spacing (10 levels, ±10%)",
        "grid_levels": 10,
        "grid_range_pct": 0.10,
        "use_atr_spacing": False,
        "max_positions": 5,
        "position_size_pct": 0.02,
    },
]


def load_csv_data(symbol: str) -> List[OHLCV]:
    """
    Load historical data from CSV file

    Args:
        symbol: Trading pair symbol (e.g., 'BTCUSDT')

    Returns:
        List of OHLCV bars

    Raises:
        FileNotFoundError: If CSV file doesn't exist
    """
    # Find CSV file for this symbol
    csv_files = list(DATA_DIR.glob(f"{symbol}_180days_*.csv"))

    if not csv_files:
        raise FileNotFoundError(f"No CSV file found for {symbol} in {DATA_DIR}")

    csv_file = csv_files[0]
    print(f"  Loading data from: {csv_file.name}")

    # Read CSV
    df = pd.read_csv(csv_file)

    # Convert to OHLCV objects
    bars = []
    for _, row in df.iterrows():
        bar = OHLCV(
            timestamp=pd.to_datetime(row['timestamp']),
            open=float(row['open']),
            high=float(row['high']),
            low=float(row['low']),
            close=float(row['close']),
            volume=float(row['volume'])
        )
        bars.append(bar)

    print(f"  Loaded {len(bars)} bars from {bars[0].timestamp} to {bars[-1].timestamp}")

    return bars


def analyze_market_conditions(bars: List[OHLCV]) -> Dict[str, Any]:
    """
    Analyze market conditions from OHLCV data

    Args:
        bars: List of OHLCV bars

    Returns:
        Dictionary with market condition metrics
    """
    prices = [bar.close for bar in bars]

    # Calculate trend strength (linear regression slope)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    trend_pct = (slope * len(prices) / prices[0]) * 100

    # Calculate volatility (standard deviation of returns)
    returns = np.diff(prices) / prices[:-1]
    volatility = np.std(returns) * 100

    # Calculate ranging score (inverse of trend strength)
    # High ranging score = sideways market (good for grid trading)
    # Low ranging score = trending market (bad for grid trading)
    abs_trend = abs(trend_pct)
    if abs_trend < 5:
        market_type = "RANGING"
        ranging_score = 100
    elif abs_trend < 10:
        market_type = "WEAK_TREND"
        ranging_score = 70
    elif abs_trend < 20:
        market_type = "TREND"
        ranging_score = 40
    else:
        market_type = "STRONG_TREND"
        ranging_score = 10

    return {
        "trend_pct": trend_pct,
        "volatility_pct": volatility,
        "market_type": market_type,
        "ranging_score": ranging_score,
        "price_start": prices[0],
        "price_end": prices[-1],
        "price_min": min(prices),
        "price_max": max(prices),
    }


def run_backtest_single(
    symbol: str,
    bars: List[OHLCV],
    grid_config: Dict[str, Any],
    initial_equity: float = ACCOUNT_EQUITY_USD
) -> BacktestResult:
    """
    Run backtest for a single symbol with given grid configuration

    Args:
        symbol: Trading pair symbol
        bars: Historical OHLCV data
        grid_config: Grid strategy configuration
        initial_equity: Starting capital

    Returns:
        BacktestResult with all metrics
    """
    # Create strategy
    strategy = GridTradingStrategy(
        symbol=symbol,
        grid_levels=grid_config["grid_levels"],
        grid_range_pct=grid_config["grid_range_pct"],
        use_atr_spacing=grid_config["use_atr_spacing"],
        max_positions=grid_config["max_positions"],
        position_size_pct=grid_config["position_size_pct"],
    )

    # Create backtest config
    backtest_config = BacktestConfig(
        initial_equity=initial_equity,
        commission_pct=0.1,  # 0.1% commission (Bybit maker fee)
        slippage_pct=0.05,   # 0.05% slippage
        max_positions=grid_config["max_positions"],
    )

    # Create engine and run
    engine = BacktestEngine(backtest_config)
    result = engine.run(strategy, bars)

    return result


def print_result_summary(
    result: BacktestResult,
    market_conditions: Dict[str, Any],
    config_name: str
) -> None:
    """
    Print formatted backtest result summary

    Args:
        result: Backtest result
        market_conditions: Market condition analysis
        config_name: Configuration name
    """
    metrics = result.metrics

    print(f"\n{'='*80}")
    print(f"Configuration: {config_name}")
    print(f"Symbol: {result.symbol}")
    print(f"{'='*80}")

    # Market conditions
    print(f"\n📊 Market Conditions:")
    print(f"  Market Type: {market_conditions['market_type']}")
    print(f"  Trend: {market_conditions['trend_pct']:+.2f}%")
    print(f"  Volatility: {market_conditions['volatility_pct']:.2f}%")
    print(f"  Ranging Score: {market_conditions['ranging_score']}/100")
    print(f"  Price Range: ${market_conditions['price_min']:.2f} - ${market_conditions['price_max']:.2f}")

    # Performance metrics
    print(f"\n💰 Performance:")
    print(f"  Total Return: {metrics.total_return_pct:+.2f}%")
    print(f"  CAGR: {metrics.cagr:.2f}%")
    print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"  Max Drawdown: {metrics.max_drawdown_pct:.2f}%")

    # Trading activity
    print(f"\n📈 Trading Activity:")
    print(f"  Total Trades: {metrics.total_trades}")
    print(f"  Win Rate: {metrics.win_rate:.2f}%")
    print(f"  Profit Factor: {metrics.profit_factor:.2f}")
    print(f"  Average Win: ${metrics.avg_win:.2f}")
    print(f"  Average Loss: ${metrics.avg_loss:.2f}")

    # Risk metrics
    print(f"\n⚠️  Risk Metrics:")
    print(f"  Sortino Ratio: {metrics.sortino_ratio:.2f}")
    print(f"  Max Drawdown Duration: {metrics.max_drawdown_duration_days} days")

    # Signals
    print(f"\n🔔 Signal Execution:")
    print(f"  Signals Generated: {result.signals_generated}")
    print(f"  Signals Executed: {result.signals_executed}")
    print(f"  Execution Rate: {(result.signals_executed/result.signals_generated*100) if result.signals_generated > 0 else 0:.1f}%")


def run_comprehensive_backtest() -> None:
    """
    Run comprehensive backtest across all symbols and configurations
    """
    print("="*80)
    print("GRID TRADING STRATEGY - COMPREHENSIVE BACKTEST")
    print("="*80)
    print(f"\nData Directory: {DATA_DIR}")
    print(f"Symbols to Test: {', '.join(SYMBOLS)}")
    print(f"Configurations: {len(GRID_CONFIGS)}")
    print(f"\nStarting backtest...\n")

    # Store all results
    all_results = []

    # Test each symbol
    for symbol in SYMBOLS:
        print(f"\n{'#'*80}")
        print(f"Testing Symbol: {symbol}")
        print(f"{'#'*80}")

        try:
            # Load data
            bars = load_csv_data(symbol)

            # Analyze market conditions
            market_conditions = analyze_market_conditions(bars)

            # Test each configuration
            for config in GRID_CONFIGS:
                print(f"\nTesting configuration: {config['name']}")

                # Run backtest
                result = run_backtest_single(symbol, bars, config)

                # Store result with metadata
                all_results.append({
                    "symbol": symbol,
                    "config": config,
                    "result": result,
                    "market_conditions": market_conditions
                })

                # Print summary
                print_result_summary(result, market_conditions, config['name'])

        except Exception as e:
            print(f"  ❌ ERROR testing {symbol}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Print comparative summary
    print(f"\n\n{'='*80}")
    print("COMPARATIVE SUMMARY - ALL CONFIGURATIONS")
    print(f"{'='*80}\n")

    # Group results by configuration
    for config in GRID_CONFIGS:
        config_results = [r for r in all_results if r['config']['name'] == config['name']]

        if not config_results:
            continue

        print(f"\n{config['name']}:")
        print(f"  {'Symbol':<12} {'Return %':>10} {'Sharpe':>8} {'Win Rate':>10} {'Trades':>8} {'Market':>12}")
        print(f"  {'-'*70}")

        for res in config_results:
            metrics = res['result'].metrics
            market = res['market_conditions']['market_type']

            print(f"  {res['symbol']:<12} "
                  f"{metrics.total_return_pct:>+9.2f}% "
                  f"{metrics.sharpe_ratio:>8.2f} "
                  f"{metrics.win_rate:>9.2f}% "
                  f"{metrics.total_trades:>8d} "
                  f"{market:>12}")

        # Calculate averages
        avg_return = np.mean([r['result'].metrics.total_return_pct for r in config_results])
        avg_sharpe = np.mean([r['result'].metrics.sharpe_ratio for r in config_results])
        avg_win_rate = np.mean([r['result'].metrics.win_rate for r in config_results])

        print(f"  {'-'*70}")
        print(f"  {'AVERAGE':<12} "
              f"{avg_return:>+9.2f}% "
              f"{avg_sharpe:>8.2f} "
              f"{avg_win_rate:>9.2f}%")

    # Best performers
    print(f"\n\n{'='*80}")
    print("TOP PERFORMERS (by Total Return)")
    print(f"{'='*80}\n")

    sorted_results = sorted(all_results, key=lambda x: x['result'].metrics.total_return_pct, reverse=True)

    print(f"  {'Rank':<6} {'Symbol':<12} {'Config':<30} {'Return %':>10} {'Sharpe':>8}")
    print(f"  {'-'*76}")

    for i, res in enumerate(sorted_results[:10], 1):
        metrics = res['result'].metrics
        config_short = res['config']['name'][:30]

        print(f"  {i:<6} {res['symbol']:<12} {config_short:<30} "
              f"{metrics.total_return_pct:>+9.2f}% {metrics.sharpe_ratio:>8.2f}")

    # Market condition analysis
    print(f"\n\n{'='*80}")
    print("MARKET CONDITION ANALYSIS")
    print(f"{'='*80}\n")

    ranging_markets = [r for r in all_results if r['market_conditions']['ranging_score'] >= 70]
    trending_markets = [r for r in all_results if r['market_conditions']['ranging_score'] < 40]

    if ranging_markets:
        avg_return_ranging = np.mean([r['result'].metrics.total_return_pct for r in ranging_markets])
        print(f"RANGING Markets (Score >= 70): {len(ranging_markets)} tests")
        print(f"  Average Return: {avg_return_ranging:+.2f}%")

    if trending_markets:
        avg_return_trending = np.mean([r['result'].metrics.total_return_pct for r in trending_markets])
        print(f"\nTRENDING Markets (Score < 40): {len(trending_markets)} tests")
        print(f"  Average Return: {avg_return_trending:+.2f}%")

    print(f"\n✅ Comprehensive backtest complete!")
    print(f"   Total tests run: {len(all_results)}")
    print(f"   Symbols tested: {len(set(r['symbol'] for r in all_results))}")
    print(f"   Configurations tested: {len(GRID_CONFIGS)}")


if __name__ == "__main__":
    run_comprehensive_backtest()
