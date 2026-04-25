#!/usr/bin/env python3
"""
Batch Production Training Script
Train LSTM models for all active trading symbols with 100 epochs
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.training.train_lstm_production import train_production_model
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Active trading symbols (from config)
ACTIVE_SYMBOLS = [
    'BNBUSDT',   # Top performer: +$48.64
    'SOLUSDT',   # Top performer: +$48.16
    'ADAUSDT',   # Top performer: +$22.65
    'APTUSDT',   # New addition
    'DOTUSDT',   # New addition
    'LTCUSDT',   # New addition
]

def main():
    """Train LSTM models for all active symbols"""
    logger.info("=" * 80)
    logger.info("BATCH PRODUCTION TRAINING - LSTM MODELS")
    logger.info("=" * 80)
    logger.info(f"Training {len(ACTIVE_SYMBOLS)} symbols with 100 epochs each")
    logger.info("")

    results = {}

    for i, symbol in enumerate(ACTIVE_SYMBOLS, 1):
        try:
            logger.info(f"[{i}/{len(ACTIVE_SYMBOLS)}] Training {symbol}...")
            logger.info("-" * 80)

            model, history = train_production_model(
                symbol=symbol,
                interval='60',
                epochs=100,
                sequence_length=100,
                lstm_units=[128, 64, 32],
                batch_size=32,
                learning_rate=0.001,
                dropout_rate=0.3
            )

            val_acc = history.get('val_accuracy', 0)
            test_acc = history.get('test_accuracy', 0)

            results[symbol] = {
                'status': 'SUCCESS',
                'val_accuracy': val_acc,
                'test_accuracy': test_acc
            }

            logger.info(f"✅ {symbol} training complete")
            logger.info("")

        except Exception as e:
            logger.error(f"❌ {symbol} training failed: {e}")
            results[symbol] = {
                'status': 'FAILED',
                'error': str(e)
            }
            logger.info("")
            continue

    # Print summary
    logger.info("=" * 80)
    logger.info("TRAINING SUMMARY")
    logger.info("=" * 80)

    for symbol, result in results.items():
        if result['status'] == 'SUCCESS':
            logger.info(f"✅ {symbol}: Val Acc={result['val_accuracy']*100:.2f}%, Test Acc={result['test_accuracy']*100:.2f}%")
        else:
            logger.info(f"❌ {symbol}: {result['error']}")

    logger.info("")
    logger.info("Batch training complete!")

    return results

if __name__ == '__main__':
    main()
