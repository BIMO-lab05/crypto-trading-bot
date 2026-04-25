#!/usr/bin/env python3
"""
Train GRU Models for Priority Symbols
Train the symbols we have 24-month data for first

Priority Symbols (have 24-month 1H data):
- AVAXUSDT, DOTUSDT, LTCUSDT

Deferred (need to get/prepare data):
- LINKUSDT, OPUSDT, POLUSDT, SUIUSDT

Author: ML Team
Date: 2025-12-10
"""

import sys
import os
from pathlib import Path
import asyncio
import logging
from datetime import datetime
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from app.ml_models.gru_predictor import GRUPricePredictor
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('gru_priority_training.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Symbols with 24-month data available
PRIORITY_SYMBOLS = [
    'AVAXUSDT',
    'DOTUSDT',
    'LTCUSDT'
]

# Data directory with 24-month CSV files
DATA_DIR = Path('/mnt/d/Bimo_max/crypto-trading-bot/data/ml_training')

def load_csv_data(symbol: str) -> pd.DataFrame:
    """
    Load historical data from CSV file

    Args:
        symbol: Trading symbol (e.g., AVAXUSDT)

    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"Loading data for {symbol}...")

    # 24-month ML training data
    csv_file = DATA_DIR / f'{symbol}_1H_24months_20251208.csv'

    if not csv_file.exists():
        raise FileNotFoundError(f"Data file not found: {csv_file}")

    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    logger.info(f"Loaded {len(df)} candles from {csv_file}")
    logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    return df


async def train_gru_model(symbol: str, epochs: int = 100):
    """
    Train GRU model for a single symbol

    Args:
        symbol: Trading symbol
        epochs: Number of training epochs

    Returns:
        dict: Training results
    """
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Starting GRU training for {symbol}")
    logger.info(f"{'=' * 60}")

    try:
        # Load data
        df = load_csv_data(symbol)

        # Initialize GRU predictor
        predictor = GRUPricePredictor(
            symbol=symbol,
            interval='60'  # 60 minutes = 1 hour
        )

        # Train model
        logger.info(f"Training {symbol} with {epochs} epochs...")
        start_time = datetime.now()

        results = await predictor.train(
            historical_data=df,
            epochs=epochs,
            batch_size=settings.batch_size,
            validation_split=0.2
        )

        elapsed = (datetime.now() - start_time).total_seconds()

        logger.info(f"\n{'=' * 60}")
        logger.info(f"✅ {symbol} Training Complete!")
        logger.info(f"{'=' * 60}")
        logger.info(f"Time taken: {elapsed:.2f}s ({elapsed/60:.2f} minutes)")
        logger.info(f"R² Score: {results.get('test_r2', 0):.4f}")
        logger.info(f"MAE: {results.get('test_mae', 0):.6f}")
        logger.info(f"RMSE: {results.get('test_rmse', 0):.6f}")
        logger.info(f"Directional Accuracy: {results.get('directional_accuracy', 0):.2%}")

        return {
            'symbol': symbol,
            'status': 'success',
            'elapsed_seconds': elapsed,
            'results': results
        }

    except Exception as e:
        logger.error(f"❌ Error training {symbol}: {e}", exc_info=True)
        return {
            'symbol': symbol,
            'status': 'failed',
            'error': str(e)
        }


async def train_all_priority():
    """
    Train all priority symbols sequentially
    """
    logger.info("\n" + "=" * 60)
    logger.info("GRU TRAINING SESSION - PRIORITY SYMBOLS")
    logger.info("=" * 60)
    logger.info(f"Symbols to train: {', '.join(PRIORITY_SYMBOLS)}")
    logger.info(f"Total: {len(PRIORITY_SYMBOLS)} symbols")
    logger.info(f"Epochs per symbol: 100")
    logger.info("=" * 60 + "\n")

    results = []
    session_start = datetime.now()

    for idx, symbol in enumerate(PRIORITY_SYMBOLS, 1):
        logger.info(f"\n[{idx}/{len(PRIORITY_SYMBOLS)}] Processing {symbol}...")
        result = await train_gru_model(symbol, epochs=100)
        results.append(result)

    session_elapsed = (datetime.now() - session_start).total_seconds()

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("TRAINING SESSION SUMMARY")
    logger.info("=" * 60)

    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] == 'failed']

    logger.info(f"\nTotal time: {session_elapsed/60:.2f} minutes")
    logger.info(f"Successful: {len(successful)}/{len(PRIORITY_SYMBOLS)}")
    logger.info(f"Failed: {len(failed)}/{len(PRIORITY_SYMBOLS)}")

    if successful:
        logger.info("\n✅ Successfully trained:")
        for r in successful:
            results_data = r.get('results', {})
            logger.info(f"  - {r['symbol']:12} | R²={results_data.get('test_r2', 0):.4f} | "
                       f"Dir Acc={results_data.get('directional_accuracy', 0):.2%} | "
                       f"Time={r.get('elapsed_seconds', 0)/60:.1f}m")

    if failed:
        logger.info("\n❌ Failed:")
        for r in failed:
            logger.info(f"  - {r['symbol']:12} | Error: {r.get('error', 'Unknown')}")

    # Save results to file
    results_file = Path('gru_priority_training_results.json')
    with open(results_file, 'w') as f:
        json.dump({
            'session_start': session_start.isoformat(),
            'session_duration_minutes': session_elapsed / 60,
            'symbols_trained': len(PRIORITY_SYMBOLS),
            'successful': len(successful),
            'failed': len(failed),
            'results': results
        }, f, indent=2)

    logger.info(f"\nResults saved to: {results_file}")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    logger.info("Starting GRU training for priority symbols...")
    asyncio.run(train_all_priority())
    logger.info("\n✅ All training complete!")
