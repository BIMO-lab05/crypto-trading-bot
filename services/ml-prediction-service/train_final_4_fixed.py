#!/usr/bin/env python3
"""
Train GRU models for final 4 symbols: LINKUSDT, OPUSDT, POLUSDT, SUIUSDT
Uses correct ModelInfo access pattern
"""
import os
import sys
import asyncio
import pandas as pd
import time
import logging
from pathlib import Path

# Set environment variables BEFORE imports
os.environ['EPOCHS'] = '100'
os.environ['BATCH_SIZE'] = '32'
os.environ['VALIDATION_SPLIT'] = '0.2'

# Add service to path
sys.path.insert(0, os.path.dirname(__file__))

from app.ml_models.gru_model import GRUPricePredictor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('training_final_4.log')
    ]
)
logger = logging.getLogger(__name__)

# Configuration
SYMBOLS = ['LINKUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT']
INTERVAL = '60'  # 1 hour
DATA_DIR = '/mnt/d/Bimo_max/crypto-trading-bot/data'


def find_data_file(symbol: str) -> str:
    """Find data file for symbol in ml_training or historical"""
    # Check ml_training first
    ml_training = f'{DATA_DIR}/ml_training'
    patterns = [
        f'{symbol}_1H_24months_20251210.csv',
        f'{symbol}_1H_6months_20251210.csv',
        f'{symbol}_1H_24months_*.csv',
    ]

    for pattern in patterns:
        files = list(Path(ml_training).glob(pattern))
        if files:
            return str(files[0])

    # Check historical
    historical = f'{DATA_DIR}/historical'
    pattern = f'{symbol}_180days_*.csv'
    files = list(Path(historical).glob(pattern))
    if files:
        return str(files[0])

    raise FileNotFoundError(f"No data file found for {symbol}")


def load_csv_data(symbol: str) -> pd.DataFrame:
    """Load and prepare CSV data"""
    csv_file = find_data_file(symbol)
    logger.info(f"Loading data from: {csv_file}")

    df = pd.read_csv(csv_file)

    # Ensure correct column names
    if df.columns[0] != 'timestamp':
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']

    # Keep only required columns
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].copy()

    # Convert types
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Remove any NaN rows
    df = df.dropna()

    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)

    logger.info(f"Loaded {len(df)} candles for {symbol}")
    logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    return df


async def train_gru_model(symbol: str, data: pd.DataFrame) -> dict:
    """Train GRU model for a symbol"""
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"Training GRU model for {symbol} ({len(data)} samples, 100 epochs)")
        logger.info(f"{'='*80}")

        start_time = time.time()

        # Initialize GRU predictor
        predictor = GRUPricePredictor(symbol=symbol, interval=INTERVAL)

        # Train the model (epochs controlled by EPOCHS env var set above)
        model_info = await predictor.train(data)

        elapsed = time.time() - start_time

        logger.info(f"\n{'='*80}")
        logger.info(f"✅ {symbol} GRU Training Complete!")
        logger.info(f"{'='*80}")
        logger.info(f"R² Score: {model_info.validation_r2_score:.4f}")
        logger.info(f"MAE: {model_info.validation_mae:.6f}")
        logger.info(f"RMSE: {model_info.validation_rmse:.6f}")
        logger.info(f"Training samples: {model_info.training_samples}")
        logger.info(f"Training time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        logger.info(f"Model version: {model_info.model_version}")

        return {
            'status': 'SUCCESS',
            'symbol': symbol,
            'r2_score': model_info.validation_r2_score,
            'mae': model_info.validation_mae,
            'rmse': model_info.validation_rmse,
            'training_time_seconds': elapsed,
            'training_samples': model_info.training_samples,
            'model_version': model_info.model_version
        }

    except Exception as e:
        logger.error(f"❌ {symbol} training failed: {e}", exc_info=True)
        return {
            'status': 'FAILED',
            'symbol': symbol,
            'error': str(e)
        }


async def main():
    """Train GRU models for all 4 symbols"""

    logger.info("\n" + "="*100)
    logger.info(f"TRAINING GRU MODELS FOR FINAL 4 SYMBOLS: {', '.join(SYMBOLS)}")
    logger.info("="*100 + "\n")

    overall_start = time.time()
    results = {}

    # Train each symbol sequentially
    for i, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"\n[{i}/{len(SYMBOLS)}] Processing {symbol}...")

        # Load data
        try:
            data = load_csv_data(symbol)
        except Exception as e:
            logger.error(f"Failed to load data for {symbol}: {e}")
            results[symbol] = {'status': 'FAILED', 'error': str(e)}
            continue

        # Train model
        result = await train_gru_model(symbol, data)
        results[symbol] = result

        # Brief pause between symbols
        if i < len(SYMBOLS):
            await asyncio.sleep(2)

    total_duration = time.time() - overall_start

    # Print summary
    logger.info("\n" + "="*100)
    logger.info("TRAINING SUMMARY")
    logger.info("="*100)
    logger.info(f"Total time: {total_duration/60:.1f} minutes ({total_duration/3600:.2f} hours)")
    logger.info("")

    successes = [s for s, r in results.items() if r.get('status') == 'SUCCESS']
    failures = [s for s, r in results.items() if r.get('status') == 'FAILED']

    logger.info(f"✅ Successful: {len(successes)}/{len(SYMBOLS)}")
    logger.info(f"❌ Failed: {len(failures)}/{len(SYMBOLS)}")
    logger.info("")

    if successes:
        logger.info("Successfully trained models:")
        for symbol in successes:
            r = results[symbol]
            logger.info(f"  • {symbol}: R²={r['r2_score']:.4f}, MAE={r['mae']:.6f}, "
                       f"Time={r['training_time_seconds']/60:.1f}min")

    if failures:
        logger.info("\nFailed trainings:")
        for symbol in failures:
            logger.info(f"  • {symbol}: {results[symbol].get('error', 'Unknown error')}")

    logger.info("\n" + "="*100 + "\n")

    return len(successes), len(failures)


if __name__ == '__main__':
    success_count, failure_count = asyncio.run(main())
    sys.exit(0 if failure_count == 0 else 1)
