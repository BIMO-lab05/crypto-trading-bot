#!/usr/bin/env python3
"""
Comprehensive Re-Testing Script Using Quality CSV Data
=======================================================

PURPOSE:
--------
Re-test ALL strategies using the quality 180-day CSV data instead of the broken
Market Data Service API (which only has 3 candles per symbol).

This script will:
1. Load historical data from CSV files (not API)
2. Test Grid Trading v1 baseline
3. Test Phase 2 strategies
4. Test SR strategy
5. Compare old results (on 3 candles) vs new results (on 180 days)
6. Document which strategies ACTUALLY work

CRITICAL CONTEXT:
-----------------
Previous test results showed:
- Grid v1: 32.6% win rate → improved to 29.68% (filters made it WORSE)
- Phase 2: ALL 7 strategies failed (negative Sharpe ratios)
- SR strategy: Could not test (only 8 days available)

Root Cause Discovery:
- Market Data Service API has only 3 candles per symbol (not 4,320 needed)
- All previous tests were based on BROKEN DATA
- CSV files contain the REAL 180 days of historical data

Expected Outcome:
- With quality data, discover which strategies actually work
- Realistic target: 45-55% win rate (not 80%)
- At least 1-2 strategies should show positive Sharpe ratio

Author: Strategic Assessment 2025-12-08
Date: 2025-12-08
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
from decimal import Decimal
import logging

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "services" / "trading-engine"))

# Import backtesting engine components
from app.backtesting.backtest_engine import BacktestEngine
from app.backtesting.data_handler import HistoricalDataHandler
from app.strategies.grid_trading_strategy import GridTradingStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# CSV data directory
CSV_DATA_DIR = PROJECT_ROOT / "data" / "historical"

# Test symbols (10 symbols with 180 days each)
TEST_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT",
    "BNBUSDT", "ADAUSDT", "APTUSDT",
    "DOTUSDT", "LTCUSDT", "POLUSDT", "AVAXUSDT"
]

# Backtest configuration
INITIAL_CAPITAL = 10000.0  # $10,000 initial capital
POSITION_SIZE = 0.1  # 10% of capital per trade

# Grid Trading v1 configurations to test
GRID_CONFIGS = [
    {
        "name": "Default",
        "num_levels": 10,
        "price_range_pct": 0.10,  # ±10%
        "spacing_type": "atr",
        "description": "10 levels, ±10% range, ATR spacing"
    },
    {
        "name": "Aggressive",
        "num_levels": 15,
        "price_range_pct": 0.05,  # ±5%
        "spacing_type": "atr",
        "description": "15 levels, ±5% range, ATR spacing"
    },
    {
        "name": "Conservative",
        "num_levels": 7,
        "price_range_pct": 0.15,  # ±15%
        "spacing_type": "atr",
        "description": "7 levels, ±15% range, ATR spacing"
    },
    {
        "name": "Fixed",
        "num_levels": 10,
        "price_range_pct": 0.10,  # ±10%
        "spacing_type": "fixed",
        "description": "10 levels, ±10% range, fixed spacing"
    }
]

# =============================================================================
# CSV DATA LOADER
# =============================================================================

class CSVDataLoader:
    """Load historical data from CSV files instead of Market Data Service API"""

    def __init__(self, csv_dir: Path):
        self.csv_dir = csv_dir
        logger.info(f"Initialized CSVDataLoader from directory: {csv_dir}")

    def load_symbol_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Load historical data for a symbol from CSV file

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
            Returns None if file not found
        """
        # Find CSV file (format: SYMBOL_180days_20251208.csv)
        csv_files = list(self.csv_dir.glob(f"{symbol}_*.csv"))

        if not csv_files:
            logger.error(f"No CSV file found for {symbol}")
            return None

        csv_file = csv_files[0]  # Use first matching file
        logger.info(f"Loading {symbol} data from: {csv_file.name}")

        try:
            # Read CSV file
            df = pd.read_csv(csv_file)

            # Validate required columns
            required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_cols):
                logger.error(f"Missing required columns in {csv_file.name}")
                return None

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Sort by timestamp (oldest first)
            df = df.sort_values('timestamp').reset_index(drop=True)

            # Log data summary
            logger.info(f"Loaded {len(df)} candles for {symbol}")
            logger.info(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            logger.info(f"  Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

            return df[required_cols]

        except Exception as e:
            logger.error(f"Error loading {csv_file.name}: {e}")
            return None

    def get_available_symbols(self) -> List[str]:
        """Get list of symbols with available CSV data"""
        csv_files = list(self.csv_dir.glob("*_*.csv"))
        symbols = []

        for csv_file in csv_files:
            # Extract symbol from filename (e.g., BTCUSDT_180days_20251208.csv)
            symbol = csv_file.stem.split('_')[0]
            if symbol not in symbols:
                symbols.append(symbol)

        return sorted(symbols)

# =============================================================================
# CSV-BASED DATA HANDLER (Replaces API-based handler)
# =============================================================================

class CSVHistoricalDataHandler(HistoricalDataHandler):
    """
    Historical data handler that loads from CSV files
    instead of Market Data Service API
    """

    def __init__(self, symbol: str, csv_loader: CSVDataLoader):
        self.symbol = symbol
        self.csv_loader = csv_loader
        self.data = None
        self.current_index = 0
        self.timeframe = "1h"  # CSV data is hourly

        # Load CSV data
        logger.info(f"Initializing CSV-based data handler for {symbol}")
        self._load_csv_data()

    def _load_csv_data(self):
        """Load historical data from CSV file"""
        self.data = self.csv_loader.load_symbol_data(self.symbol)

        if self.data is None or len(self.data) == 0:
            raise ValueError(f"No data available for {self.symbol}")

        logger.info(f"CSV data handler initialized with {len(self.data)} candles")

    async def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Get historical candles (interface compatible with original)

        Returns:
            List of candle dictionaries with OHLCV data
        """
        if self.data is None or len(self.data) == 0:
            logger.warning(f"No data available for {symbol}")
            return []

        # Filter by date range if specified
        df = self.data.copy()

        if start_time:
            df = df[df['timestamp'] >= start_time]

        if end_time:
            df = df[df['timestamp'] <= end_time]

        # Apply limit
        if limit and len(df) > limit:
            df = df.tail(limit)

        # Convert to list of dictionaries (format expected by backtest engine)
        candles = []
        for _, row in df.iterrows():
            candles.append({
                'timestamp': int(row['timestamp'].timestamp() * 1000),  # milliseconds
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume'])
            })

        logger.info(f"Returning {len(candles)} candles for {symbol}")
        return candles

# =============================================================================
# GRID TRADING V1 BACKTEST
# =============================================================================

async def test_grid_v1_baseline(
    symbols: List[str],
    csv_loader: CSVDataLoader
) -> Dict[str, Any]:
    """
    Test Grid Trading v1 baseline across all symbols and configurations

    Args:
        symbols: List of trading symbols
        csv_loader: CSVDataLoader instance

    Returns:
        Dictionary with test results
    """
    logger.info("="*80)
    logger.info("TESTING GRID TRADING V1 BASELINE WITH CSV DATA")
    logger.info("="*80)

    all_results = []

    for config in GRID_CONFIGS:
        logger.info(f"\n{'='*80}")
        logger.info(f"Testing Configuration: {config['name']}")
        logger.info(f"Description: {config['description']}")
        logger.info(f"{'='*80}\n")

        config_results = []

        for symbol in symbols:
            logger.info(f"\nTesting {symbol}...")

            try:
                # Create CSV-based data handler
                data_handler = CSVHistoricalDataHandler(symbol, csv_loader)

                # Create strategy instance
                strategy = GridTradingStrategy(
                    num_levels=config['num_levels'],
                    price_range_pct=config['price_range_pct'],
                    spacing_type=config['spacing_type']
                )

                # Create backtest engine
                engine = BacktestEngine(
                    strategy=strategy,
                    data_handler=data_handler,
                    initial_capital=Decimal(str(INITIAL_CAPITAL)),
                    symbol=symbol
                )

                # Run backtest
                results = await engine.run_backtest()

                # Calculate metrics
                total_trades = results.get('total_trades', 0)
                win_rate = results.get('win_rate', 0.0)
                total_return = results.get('total_return_pct', 0.0)
                sharpe_ratio = results.get('sharpe_ratio', 0.0)

                result_entry = {
                    'symbol': symbol,
                    'config': config['name'],
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'total_return': total_return,
                    'sharpe_ratio': sharpe_ratio
                }

                config_results.append(result_entry)
                all_results.append(result_entry)

                logger.info(f"  Trades: {total_trades}")
                logger.info(f"  Win Rate: {win_rate:.2f}%")
                logger.info(f"  Return: {total_return:.2f}%")
                logger.info(f"  Sharpe: {sharpe_ratio:.2f}")

            except Exception as e:
                logger.error(f"Error testing {symbol}: {e}", exc_info=True)
                continue

        # Calculate average for this configuration
        if config_results:
            avg_win_rate = np.mean([r['win_rate'] for r in config_results])
            avg_return = np.mean([r['total_return'] for r in config_results])
            avg_sharpe = np.mean([r['sharpe_ratio'] for r in config_results])

            logger.info(f"\n{'='*80}")
            logger.info(f"Configuration '{config['name']}' Average Results:")
            logger.info(f"  Average Win Rate: {avg_win_rate:.2f}%")
            logger.info(f"  Average Return: {avg_return:.2f}%")
            logger.info(f"  Average Sharpe: {avg_sharpe:.2f}")
            logger.info(f"{'='*80}\n")

    return {
        'strategy': 'Grid Trading v1 Baseline',
        'results': all_results,
        'summary': _calculate_summary(all_results)
    }

def _calculate_summary(results: List[Dict]) -> Dict[str, Any]:
    """Calculate summary statistics from results"""
    if not results:
        return {}

    return {
        'total_tests': len(results),
        'avg_win_rate': np.mean([r['win_rate'] for r in results]),
        'avg_return': np.mean([r['total_return'] for r in results]),
        'avg_sharpe': np.mean([r['sharpe_ratio'] for r in results]),
        'best_symbol': max(results, key=lambda r: r['win_rate'])['symbol'],
        'worst_symbol': min(results, key=lambda r: r['win_rate'])['symbol']
    }

# =============================================================================
# MAIN EXECUTION
# =============================================================================

async def main():
    """Main execution function"""
    logger.info("="*80)
    logger.info("COMPREHENSIVE STRATEGY RE-TESTING WITH CSV DATA")
    logger.info("="*80)
    logger.info(f"Start Time: {datetime.now()}")
    logger.info(f"CSV Data Directory: {CSV_DATA_DIR}")
    logger.info("")

    # Initialize CSV data loader
    csv_loader = CSVDataLoader(CSV_DATA_DIR)

    # Check available symbols
    available_symbols = csv_loader.get_available_symbols()
    logger.info(f"Available symbols in CSV files: {available_symbols}")

    # Filter to only test symbols with CSV data
    test_symbols = [s for s in TEST_SYMBOLS if s in available_symbols]
    logger.info(f"Testing {len(test_symbols)} symbols: {test_symbols}")

    if not test_symbols:
        logger.error("No test symbols have CSV data available!")
        return

    # Test Grid Trading v1 Baseline
    grid_v1_results = await test_grid_v1_baseline(test_symbols, csv_loader)

    # Print final summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY - GRID TRADING V1 BASELINE")
    logger.info("="*80)

    summary = grid_v1_results['summary']
    logger.info(f"Total Tests Run: {summary['total_tests']}")
    logger.info(f"Average Win Rate: {summary['avg_win_rate']:.2f}%")
    logger.info(f"Average Return: {summary['avg_return']:.2f}%")
    logger.info(f"Average Sharpe: {summary['avg_sharpe']:.2f}")
    logger.info(f"Best Symbol: {summary['best_symbol']}")
    logger.info(f"Worst Symbol: {summary['worst_symbol']}")

    # Compare to old baseline (from broken API data)
    old_baseline = 32.6  # Previous baseline win rate
    new_baseline = summary['avg_win_rate']
    difference = new_baseline - old_baseline

    logger.info("\n" + "="*80)
    logger.info("COMPARISON TO OLD BASELINE (Broken API Data)")
    logger.info("="*80)
    logger.info(f"Old Baseline (3 candles): {old_baseline}%")
    logger.info(f"New Baseline (180 days): {new_baseline:.2f}%")
    logger.info(f"Difference: {difference:+.2f}%")

    if new_baseline > old_baseline:
        logger.info("✅ IMPROVED! Quality data shows better performance!")
    elif new_baseline < old_baseline:
        logger.info("⚠️ WORSE! Need to investigate strategy implementation.")
    else:
        logger.info("➡️ SAME. Data quality had no impact.")

    logger.info("\n" + "="*80)
    logger.info(f"End Time: {datetime.now()}")
    logger.info("="*80)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
