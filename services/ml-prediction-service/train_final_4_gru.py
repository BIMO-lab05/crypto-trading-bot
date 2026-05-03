#!/usr/bin/env python3
"""
Train GRU Models for Final 4 Symbols
Symbols: LINKUSDT, OPUSDT, POLUSDT, SUIUSDT
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

# Set epochs via environment
os.environ['EPOCHS'] = '100'

sys.path.insert(0, str(Path(__file__).parent))

from app.ml_models.gru_model import GRUPricePredictor
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training_final_4.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

settings = get_settings()

DATA_DIR = (_REPO_ROOT / 'data/ml_training')
SYMBOLS = ['LINKUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT']
INTERVAL = '60'


def load_csv_data(symbol: str) -> pd.DataFrame:
    """Load CSV data"""
    # Find the file
    pattern = f"{symbol}_1H_24months_*.csv"
    files = list(DATA_DIR.glob(pattern))

    if not files:
        raise FileNotFoundError(f"No data file found for {symbol}")

    csv_file = files[0]
    logger.info(f"Loading {csv_file.name}")

    df = pd.read_csv(csv_file)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    df = df.sort_values('timestamp').reset_index(drop=True)

    logger.info(f"Loaded {len(df):,} candles")
    logger.info(f"Range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    return df


async def train_gru_model(symbol: str, data: pd.DataFrame) -> dict:
    """Train GRU model"""
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"Training GRU for {symbol} ({len(data):,} samples, 100 epochs)")
        logger.info(f"{'='*80}")

        start_time = time.time()

        predictor = GRUPricePredictor(symbol=symbol, interval=INTERVAL)
        model_info = await predictor.train(data)

        elapsed = time.time() - start_time

        logger.info(f"\n{'='*80}")
        logger.info(f"✅ {symbol} Complete!")
        logger.info(f"{'='*80}")
        logger.info(f"R² Score: {model_info.validation_r2_score:.4f}")
        logger.info(f"MAE: {model_info.validation_mae:.6f}")
        logger.info(f"RMSE: {model_info.validation_rmse:.6f}")
        logger.info(f"Training time: {elapsed:.1f}s ({elapsed/60:.1f} min)")

        return {
            'status': 'SUCCESS',
            'symbol': symbol,
            'r2_score': model_info.validation_r2_score,
            'mae': model_info.validation_mae,
            'rmse': model_info.validation_rmse,
            'training_time_seconds': elapsed
        }

    except Exception as e:
        logger.error(f"❌ {symbol} failed: {e}", exc_info=True)
        return {
            'status': 'FAILED',
            'symbol': symbol,
            'error': str(e)
        }


async def main():
    logger.info("\n" + "="*100)
    logger.info("FINAL 4 GRU MODELS TRAINING")
    logger.info("="*100)
    logger.info(f"Symbols: {', '.join(SYMBOLS)}")
    logger.info(f"Epochs: 100")
    logger.info("="*100 + "\n")

    overall_start = time.time()
    results = {}

    for i, symbol in enumerate(SYMBOLS, 1):
        logger.info(f"\n[{i}/{len(SYMBOLS)}] {symbol}")

        try:
            data = load_csv_data(symbol)
        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            results[symbol] = {'status': 'FAILED', 'error': str(e)}
            continue

        result = await train_gru_model(symbol, data)
        results[symbol] = result

        if i < len(SYMBOLS):
            await asyncio.sleep(2)

    total_duration = time.time() - overall_start
    successful = sum(1 for r in results.values() if r['status'] == 'SUCCESS')

    logger.info("\n" + "="*100)
    logger.info("TRAINING SUMMARY")
    logger.info("="*100)
    logger.info(f"Total time: {total_duration/60:.1f} minutes")
    logger.info(f"Success: {successful}/{len(SYMBOLS)}")
    logger.info("")

    for symbol, result in results.items():
        if result['status'] == 'SUCCESS':
            logger.info(f"✅ {symbol:<12} R²={result['r2_score']:.4f}  MAE={result['mae']:.6f}  Time={result['training_time_seconds']/60:.1f}min")
        else:
            logger.info(f"❌ {symbol:<12} FAILED - {result.get('error', 'Unknown')}")

    logger.info("="*100)
    logger.info("\n✅ All training complete!\n")


if __name__ == "__main__":
    asyncio.run(main())
