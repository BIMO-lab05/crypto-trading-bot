#!/usr/bin/env python3
"""
Train GRU Models for Remaining Symbols
Train the 8 symbols that currently only have LSTM models with GRU

Symbols to train:
- ARBUSDT, AVAXUSDT, DOTUSDT, LINKUSDT, LTCUSDT, OPUSDT, POLUSDT, SUIUSDT

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
        logging.FileHandler('gru_remaining_training.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Symbols that need GRU models (currently only have LSTM)
REMAINING_SYMBOLS = [
    'ARBUSDT',
    'AVAXUSDT',
    'DOTUSDT',
    'LINKUSDT',
    'LTCUSDT',
    'OPUSDT',
    'POLUSDT',
    'SUIUSDT'
]

# Data directory with 24-month CSV files
DATA_DIR = Path('/mnt/d/Bimo_max/crypto-trading-bot/data/ml_training')

def load_csv_data(symbol: str) -> pd.DataFrame:
    """
    Load historical data from CSV file

    Args:
        symbol: Trading symbol (e.g., ARBUSDT)

    Returns:
        DataFrame with OHLCV data
    """
    logger.info(f"Loading data for {symbol}...")

    # Try different filename patterns
    patterns = [
        f'{symbol}_1H_24months_20251208.csv',  # 24-month ML training data
        f'{symbol}_60m_180d_bybit.csv',        # 6 months fallback
        f'{symbol}_60m.csv',                   # Simple pattern
    ]

    # Try both ml_training and backtesting directories
    search_dirs = [
        DATA_DIR,
        Path('/mnt/d/Bimo_max/crypto-trading-bot/backtesting/data')
    ]

    for directory in search_dirs:
        for pattern in patterns:
            csv_file = directory / pattern
            if csv_file.exists():
                df = pd.read_csv(csv_file)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                logger.info(f"Loaded {len(df)} candles from {csv_file}")
                logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
                return df

    # If no file found
    raise FileNotFoundError(
        f"Could not find data file for {symbol}. Tried:\n" +
        "\n".join([f"  - {d}/{p}" for d in search_dirs for p in patterns])
    )


async def train_gru_model(symbol: str, epochs: int = 100):
    """
    Train GRU model for a single symbol

    Args:
        symbol: Trading symbol
        epochs: Number of training epochs

    Returns:
        Dictionary with training results
    """
    start_time = datetime.utcnow()

    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"Training GRU model for {symbol}")
        logger.info(f"{'='*80}")

        # Load data
        df = load_csv_data(symbol)

        # Initialize GRU predictor
        gru = GRUPricePredictor(symbol=symbol, interval='60')
        logger.info(f"Initialized GRU predictor")

        # Override epochs setting
        original_epochs = settings.epochs
        settings.epochs = epochs

        logger.info(f"Training configuration:")
        logger.info(f"  - Epochs: {epochs}")
        logger.info(f"  - Sequence length: {settings.sequence_length}")
        logger.info(f"  - Batch size: {settings.batch_size}")
        logger.info(f"  - Learning rate: {settings.learning_rate}")
        logger.info(f"  - Training samples: {len(df)}")

        # Train the model
        logger.info(f"Starting training... (this may take 10-20 minutes)")
        model_info = await gru.train(df)

        # Restore original settings
        settings.epochs = original_epochs

        # Calculate duration
        end_time = datetime.utcnow()
        training_duration = (end_time - start_time).total_seconds()

        # Extract results
        result = {
            'status': 'SUCCESS',
            'symbol': symbol,
            'interval': '60',
            'epochs': epochs,
            'training_duration_seconds': training_duration,
            'training_samples': model_info.training_samples,
            'r2_score': model_info.validation_r2_score,
            'mae': model_info.validation_mae,
            'rmse': model_info.validation_rmse,
            'model_version': model_info.model_version,
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.info(f"\n{'='*80}")
        logger.info(f"✅ {symbol} Training Complete!")
        logger.info(f"{'='*80}")
        logger.info(f"R² Score: {model_info.validation_r2_score:.4f}")
        logger.info(f"MAE: {model_info.validation_mae:.6f}")
        logger.info(f"RMSE: {model_info.validation_rmse:.6f}")
        logger.info(f"Training time: {training_duration/60:.1f} minutes")
        logger.info(f"Model saved: {gru._get_model_path()}")

        return result

    except FileNotFoundError as e:
        logger.warning(f"⚠️  {symbol} - Data file not found: {e}")
        return {
            'status': 'SKIPPED',
            'symbol': symbol,
            'reason': 'No data file available',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"❌ {symbol} training failed: {e}", exc_info=True)
        return {
            'status': 'FAILED',
            'symbol': symbol,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }


async def main():
    """Train GRU models for all remaining symbols"""

    print("\n" + "="*100)
    print("BATCH GRU TRAINING - REMAINING SYMBOLS")
    print("="*100)
    print(f"Symbols to train: {len(REMAINING_SYMBOLS)}")
    print(f"Training epochs: 100")
    print(f"Start time: {datetime.utcnow()}")
    print(f"Models directory: {settings.models_dir}")
    print("="*100 + "\n")

    overall_start = datetime.utcnow()
    results = {}

    # Train each symbol sequentially
    for i, symbol in enumerate(REMAINING_SYMBOLS, 1):
        logger.info(f"\n[{i}/{len(REMAINING_SYMBOLS)}] Processing {symbol}...")

        result = await train_gru_model(symbol, epochs=100)
        results[symbol] = result

        # Brief pause between symbols
        if i < len(REMAINING_SYMBOLS):
            await asyncio.sleep(2)

    overall_end = datetime.utcnow()
    total_duration = (overall_end - overall_start).total_seconds()

    # Print summary
    print("\n" + "="*100)
    print("TRAINING SUMMARY")
    print("="*100)
    print(f"Total time: {total_duration/60:.1f} minutes ({total_duration/3600:.2f} hours)")
    print()

    successful = sum(1 for r in results.values() if r['status'] == 'SUCCESS')
    failed = sum(1 for r in results.values() if r['status'] == 'FAILED')
    skipped = sum(1 for r in results.values() if r['status'] == 'SKIPPED')

    print(f"Results:")
    print(f"  ✅ Successful: {successful}/{len(REMAINING_SYMBOLS)}")
    print(f"  ❌ Failed: {failed}/{len(REMAINING_SYMBOLS)}")
    print(f"  ⚠️  Skipped: {skipped}/{len(REMAINING_SYMBOLS)}")
    print()

    # Detailed results
    print("Detailed Results:")
    print("-" * 100)

    for symbol, result in results.items():
        if result['status'] == 'SUCCESS':
            print(f"✅ {symbol:<12} R²={result['r2_score']:.4f}  "
                  f"MAE={result['mae']:.6f}  "
                  f"Time={result['training_duration_seconds']/60:.1f}min")
        elif result['status'] == 'SKIPPED':
            print(f"⚠️  {symbol:<12} SKIPPED - {result.get('reason', 'Unknown')}")
        else:
            print(f"❌ {symbol:<12} FAILED - {result.get('error', 'Unknown error')}")

    print()

    # Save results to JSON
    results_file = Path(__file__).parent / 'gru_remaining_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'generated_at': datetime.utcnow().isoformat(),
            'total_duration_seconds': total_duration,
            'symbols_trained': len(REMAINING_SYMBOLS),
            'successful': successful,
            'failed': failed,
            'skipped': skipped,
            'results': results
        }, f, indent=2)

    logger.info(f"Results saved to: {results_file}")

    # Next steps
    print("="*100)
    print("NEXT STEPS")
    print("="*100)
    if successful == len(REMAINING_SYMBOLS):
        print("🎉 All symbols trained successfully!")
        print("   - Run comparison report again to see updated results")
        print("   - Consider retraining all symbols with 24-month data for R² > 0.99")
    elif successful > 0:
        print(f"⚠️  {successful} symbols trained, but {failed + skipped} had issues")
        print("   - Check log file for details: gru_remaining_training.log")
        print("   - For skipped symbols, ensure 24-month CSV data is available")
    else:
        print("❌ No symbols trained successfully")
        print("   - Check data availability in data/ml_training/")
        print("   - Verify CSV file naming matches expected patterns")

    print()

    return results


if __name__ == '__main__':
    try:
        results = asyncio.run(main())

        # Exit with appropriate code
        failed_count = sum(1 for r in results.values() if r['status'] == 'FAILED')
        if failed_count > 0:
            logger.warning(f"Training completed with {failed_count} failures")
            sys.exit(1)
        else:
            logger.info("Training completed successfully!")
            sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("\nTraining interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Training pipeline failed: {e}", exc_info=True)
        sys.exit(1)
