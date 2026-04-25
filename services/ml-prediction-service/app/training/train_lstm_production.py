#!/usr/bin/env python3
"""
Production LSTM Model Training Script

Train full LSTM model with production configuration:
- Full architecture (128, 64, 32 units)
- 50-100 epochs with early stopping
- Full sequence length (100 candles)
- Comprehensive evaluation metrics
- Model versioning and persistence

Author: ML Team
Date: 2025-12-07
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent / 'services' / 'market-data-service'))

import pandas as pd
import numpy as np
from app.training.feature_engineer import FeatureEngineer
from app.predictor import LSTMPricePredictor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_data(symbol: str = 'SOLUSDT', interval: str = '60', limit: int = 4000):
    """Load historical data from CSV - now using 24-month ML training dataset"""
    logger.info(f"Loading data for {symbol}...")

    # Use new ml_training data directory with 24 months of data
    data_dir = Path(__file__).parent.parent.parent.parent.parent / 'data' / 'ml_training'

    # Map interval (minutes) to timeframe string
    interval_map = {
        '60': '1H',
        '240': '4H',
        '1440': '1D',
        'D': '1D'
    }
    timeframe = interval_map.get(interval, '1H')

    # Try different filename patterns (prioritize new 24-month data)
    patterns = [
        f'{symbol}_{timeframe}_24months_20251208.csv',  # NEW: 24-month ML training data
        f'{symbol}_{interval}m_180d_bybit.csv',  # Fallback: 6 months
        f'{symbol}_{interval}m_90d_bybit.csv',   # Fallback: 3 months
        f'{symbol}_{interval}m.csv',             # Fallback: simple pattern
    ]

    # Also check backtesting directory as fallback
    fallback_dirs = [
        data_dir,
        Path(__file__).parent.parent.parent.parent.parent / 'backtesting' / 'data'
    ]

    for directory in fallback_dirs:
        for pattern in patterns:
            data_path = directory / pattern
            if data_path.exists():
                df = pd.read_csv(data_path)
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
                logger.info(f"Loaded {len(df)} candles from {data_path}")
                logger.info(f"Date range: {df.index.min()} to {df.index.max()}")
                return df

    # If no file found, raise error
    raise FileNotFoundError(
        f"Could not find data file for {symbol}. Tried:\n" +
        "\n".join([f"  - {d}/{p}" for d in fallback_dirs for p in patterns])
    )


def train_production_model(
    symbol: str = 'SOLUSDT',
    interval: str = '60',
    epochs: int = 100,
    sequence_length: int = 100,
    lstm_units: list = [128, 64, 32],
    batch_size: int = 32,
    learning_rate: float = 0.001,
    dropout_rate: float = 0.3
):
    """
    Train production-ready LSTM model

    Args:
        symbol: Trading symbol
        interval: Candle interval in minutes
        epochs: Maximum training epochs
        sequence_length: Number of candles in sequence
        lstm_units: LSTM layer units
        batch_size: Training batch size
        learning_rate: Learning rate for optimizer
        dropout_rate: Dropout rate for regularization

    Returns:
        Trained LSTMPricePredictor instance and training history
    """
    print("=" * 80)
    print("LSTM PRODUCTION MODEL TRAINING")
    print("=" * 80)
    print()

    # 1. Load data
    print("1. Loading historical data...")
    df = load_data(symbol=symbol, interval=interval, limit=4000)
    print(f"   ✅ Loaded {len(df)} candles")
    print()

    # 2. Feature engineering
    print("2. Engineering features...")
    fe = FeatureEngineer()  # No parameters needed
    features_df = fe.create_features(df)
    print(f"   ✅ Created {len(features_df.columns)} features, {len(features_df)} rows")
    print()

    # 3. Data split (70% train, 15% val, 15% test)
    train_size = int(len(features_df) * 0.70)
    val_size = int(len(features_df) * 0.15)

    train_df = features_df.iloc[:train_size]
    val_df = features_df.iloc[train_size:train_size+val_size]
    test_df = features_df.iloc[train_size+val_size:]

    print("3. Data split:")
    print(f"   Train: {len(train_df)} samples ({len(train_df)/len(features_df)*100:.1f}%)")
    print(f"   Val:   {len(val_df)} samples ({len(val_df)/len(features_df)*100:.1f}%)")
    print(f"   Test:  {len(test_df)} samples ({len(test_df)/len(features_df)*100:.1f}%)")
    print()

    # 4. Initialize LSTM model
    print("4. Building production LSTM model...")
    lstm = LSTMPricePredictor(
        sequence_length=sequence_length,
        features_count=54,  # Will be updated automatically
        prediction_horizon=4,
        lstm_units=lstm_units,
        dropout_rate=dropout_rate,
        learning_rate=learning_rate
    )
    print(f"   ✅ Model initialized")
    print(f"      Architecture: {lstm_units}")
    print(f"      Sequence length: {sequence_length}")
    print(f"      Dropout rate: {dropout_rate}")
    print(f"      Learning rate: {learning_rate}")
    print()

    # 5. Train model
    print(f"5. Training LSTM ({epochs} max epochs with early stopping)...")
    print("   This may take 10-20 minutes...")
    print()

    history = lstm.train(
        train_data=train_df,
        val_data=val_df,
        epochs=epochs,
        batch_size=batch_size,
        verbose=1
    )

    print()
    print("=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print()

    # 6. Evaluate on test set
    print("6. Evaluating on test set...")
    predictions, confidences = lstm.predict(test_df)

    # Calculate test metrics
    test_accuracy = np.mean(predictions == test_df['target'].values[-len(predictions):])
    up_count = np.sum(predictions == 1)
    down_count = np.sum(predictions == 0)
    avg_confidence = np.mean(confidences)

    print(f"   Test Accuracy:   {test_accuracy*100:.2f}%")
    print(f"   UP predictions:  {up_count}")
    print(f"   DOWN predictions: {down_count}")
    print(f"   Avg Confidence:  {avg_confidence*100:.2f}%")
    print()

    # 7. Save model
    model_dir = Path(__file__).parent.parent.parent / 'models'
    model_dir.mkdir(exist_ok=True, parents=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_path = model_dir / f'lstm_{symbol}_{timestamp}.keras'  # Added .keras extension

    print("7. Saving model...")
    lstm.save(str(model_path))
    print(f"   ✅ Model saved to: {model_path}")
    print()

    # 8. Generate summary report
    print("=" * 80)
    print("FINAL PERFORMANCE SUMMARY")
    print("=" * 80)
    print()
    print(f"Symbol: {symbol}")
    print(f"Interval: {interval}m")
    print(f"Training samples: {len(train_df)}")
    print(f"Validation samples: {len(val_df)}")
    print(f"Test samples: {len(test_df)}")
    print()
    print(f"Final Training Accuracy: {history.get('train_accuracy', 0)*100:.2f}%")
    print(f"Final Training AUC: {history.get('train_auc', 0):.4f}")
    print()
    print(f"Final Validation Accuracy: {history.get('val_accuracy', 0)*100:.2f}%")
    print(f"Final Validation AUC: {history.get('val_auc', 0):.4f}")
    print()
    print(f"Test Accuracy: {test_accuracy*100:.2f}%")
    print()

    # Success criteria check
    print("SUCCESS CRITERIA CHECK:")
    val_acc = history.get('val_accuracy', 0)
    val_auc = history.get('val_auc', 0)

    criteria_met = []
    if val_acc > 0.65:
        print(f"   ✅ Validation accuracy {val_acc*100:.2f}% > 65% (PASSED)")
        criteria_met.append(True)
    else:
        print(f"   ⚠️  Validation accuracy {val_acc*100:.2f}% < 65% (BELOW TARGET)")
        criteria_met.append(False)

    if val_auc > 0.60:
        print(f"   ✅ Validation AUC {val_auc:.4f} > 0.60 (PASSED)")
        criteria_met.append(True)
    else:
        print(f"   ⚠️  Validation AUC {val_auc:.4f} < 0.60 (BELOW TARGET)")
        criteria_met.append(False)

    if test_accuracy > 0.55:
        print(f"   ✅ Test accuracy {test_accuracy*100:.2f}% > 55% (PASSED)")
        criteria_met.append(True)
    else:
        print(f"   ⚠️  Test accuracy {test_accuracy*100:.2f}% < 55% (BELOW TARGET)")
        criteria_met.append(False)

    print()
    if all(criteria_met):
        print("🎉 ALL SUCCESS CRITERIA MET! Model ready for production.")
    else:
        print("⚠️  Some criteria not met. Consider:")
        print("   - Collecting more data (6 months instead of 3)")
        print("   - Tuning hyperparameters")
        print("   - Adding more features")
        print("   - Trying ensemble approach")
    print()

    return lstm, history


def main():
    """Main training script"""
    try:
        # Train production model
        lstm, history = train_production_model(
            symbol='SOLUSDT',
            interval='60',
            epochs=100,  # Max epochs (early stopping will prevent overfitting)
            sequence_length=100,  # Full sequence length
            lstm_units=[128, 64, 32],  # Full architecture
            batch_size=32,
            learning_rate=0.001,
            dropout_rate=0.3
        )

        print("✅ Production model training complete!")
        return 0

    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\n❌ Training failed: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
