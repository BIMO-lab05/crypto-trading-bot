#!/usr/bin/env python3
"""
Train GRU Models for 3 Remaining Symbols with 24-month Data
Symbols: AVAXUSDT, DOTUSDT, LTCUSDT

Uses the working GRU implementation from gru_model.py
Based on the successful train_with_csv_data.py script
"""

import asyncio
import pandas as pd
from datetime import datetime
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
import logging
import sys
import os
import time

# Set epochs to 100 via environment variable BEFORE importing models
os.environ['EPOCHS'] = '100'

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.ml_models.gru_model import GRUPricePredictor
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training_remaining_3.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Data directory
DATA_DIR = (_REPO_ROOT / 'data/ml_training')

# Symbols to train (have 24-month data)
SYMBOLS = [
    'AVAXUSDT',
    'DOTUSDT',
    'LTCUSDT'
]

# Training configuration
INTERVAL = '60'  # 60 minute candles (1H)


def load_csv_data(symbol: str) -> pd.DataFrame:
    """Load historical candle data from CSV file"""
    csv_file = DATA_DIR / f"{symbol}_1H_24months_20251208.csv"

    logger.info(f"Loading data for {symbol} from {csv_file}")

    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    # Load CSV data
    df = pd.read_csv(csv_file)

    # Verify required columns
    required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_columns):
        raise ValueError(f"Missing required columns in {csv_file}")

    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Convert price/volume columns to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

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
    """Train GRU models for all 3 symbols"""

    logger.info("\n" + "="*100)
    logger.info("BATCH GRU TRAINING - REMAINING 3 SYMBOLS WITH 24-MONTH DATA")
    logger.info("="*100)
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Epochs: 100 (set via EPOCHS environment variable)")
    logger.info(f"Start time: {datetime.now()}")
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

    successful = sum(1 for r in results.values() if r['status'] == 'SUCCESS')
    failed = sum(1 for r in results.values() if r['status'] == 'FAILED')

    logger.info(f"Results:")
    logger.info(f"  ✅ Successful: {successful}/{len(SYMBOLS)}")
    logger.info(f"  ❌ Failed: {failed}/{len(SYMBOLS)}")
    logger.info("")

    # Detailed results
    logger.info("Detailed Results:")
    logger.info("-" * 100)

    for symbol, result in results.items():
        if result['status'] == 'SUCCESS':
            logger.info(f"✅ {symbol:<12} R²={result['r2_score']:.4f}  "
                       f"MAE={result['mae']:.6f}  "
                       f"Time={result['training_time_seconds']/60:.1f}min")
        else:
            logger.info(f"❌ {symbol:<12} FAILED - {result.get('error', 'Unknown error')}")

    logger.info("="*100)
    logger.info(f"\n✅ Training session complete!\n")


if __name__ == "__main__":
    logger.info("Starting GRU training...")
    asyncio.run(main())
