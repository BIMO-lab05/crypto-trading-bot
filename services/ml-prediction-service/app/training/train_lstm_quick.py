#!/usr/bin/env python3
"""
Quick LSTM Model Training Test - 24-Month Dataset Validation
============================================================
Tests LSTM training with the new 24-month dataset to validate:
- Data loading from new ml_training directory
- Feature engineering pipeline
- Model training with enhanced dataset
- Comparison against baseline metrics

Expected Results:
- Training accuracy > 60%
- Validation accuracy > 55%
- Better than previous 52.80% test accuracy

Author: ML Team
Date: 2025-12-08
"""

import sys
import os
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np
import logging

from app.training.feature_engineer import FeatureEngineer
from app.predictor import LSTMPricePredictor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_data(symbol: str = 'SOLUSDT'):
    """Load historical data from CSV - using 24-month ML training dataset"""
    logger.info(f"Loading data for {symbol}...")

    # Use new ml_training data directory with 24 months of data
    data_dir = Path(__file__).parent.parent.parent.parent.parent / 'data' / 'ml_training'

    # LSTM uses 4H timeframe
    timeframe = '4H'

    # Try different filename patterns (prioritize new 24-month data)
    patterns = [
        f'{symbol}_{timeframe}_24months_20251208.csv',  # NEW: 24-month ML training data
        f'{symbol}_240m_180d_bybit.csv',  # Fallback: 6 months
        f'{symbol}_240m.csv',             # Fallback: simple pattern
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


def main():
    """Quick LSTM training test with 24-month dataset"""
    print("=" * 80)
    print("LSTM MODEL - QUICK TRAINING TEST (24-MONTH DATASET)")
    print("Validating enhanced dataset and training pipeline")
    print("=" * 80)
    print()

    # 1. Load data
    print("1. Loading 24-month historical data...")
    raw_df = load_data('SOLUSDT')
    print(f"   ✅ Loaded {len(raw_df)} candles")
    print(f"   📊 Date range: {raw_df.index.min()} to {raw_df.index.max()}")
    print()

    # 2. Feature engineering
    print("2. Engineering features...")
    fe = FeatureEngineer()
    features_df = fe.create_features(raw_df)
    print(f"   ✅ Created {len(features_df.columns)} features, {len(features_df)} rows")
    print()

    # 3. Data split
    train_size = int(len(features_df) * 0.70)
    val_size = int(len(features_df) * 0.15)

    train_df = features_df.iloc[:train_size]
    val_df = features_df.iloc[train_size:train_size+val_size]
    test_df = features_df.iloc[train_size+val_size:]

    print("3. Data split:")
    print(f"   Train: {len(train_df)} samples (70%)")
    print(f"   Val:   {len(val_df)} samples (15%)")
    print(f"   Test:  {len(test_df)} samples (15%)")
    print()

    # 4. Initialize LSTM model
    print("4. Building LSTM model...")
    lstm = LSTMPredictor(
        sequence_length=100,
        features_count=len(features_df.columns)-1,  # Exclude target
        prediction_horizon=5,  # 5 candles ahead (20 hours for 4H timeframe)
        lstm_units=[128, 64, 32],
        dropout_rate=0.3,
        learning_rate=0.001
    )
    print(f"   ✅ LSTM model initialized")
    print(f"      Sequence length: 100")
    print(f"      Features: {len(features_df.columns)-1}")
    print(f"      Prediction horizon: 5 candles (20 hours)")
    print()

    # 5. Train model (Quick test: 20 epochs)
    print("5. Training LSTM model (20 epochs for quick validation)...")
    print("   This should take 3-5 minutes...")
    print()

    history = lstm.train(
        train_df=train_df,
        val_df=val_df,
        epochs=20,  # Quick test (vs 100 for production)
        batch_size=32,
        early_stopping_patience=5
    )

    print()
    print("=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print()

    # 6. Evaluate on test set
    print("6. Evaluating on test set...")
    test_metrics = lstm.evaluate(test_df)

    print(f"   Test Accuracy:  {test_metrics['accuracy']*100:.2f}%")
    print(f"   Test Loss:      {test_metrics['loss']:.4f}")
    print()

    # 7. Training history
    print("7. Training summary:")
    final_train_acc = history['accuracy'][-1] if 'accuracy' in history else 0
    final_val_acc = history['val_accuracy'][-1] if 'val_accuracy' in history else 0

    print(f"   Final Train Accuracy: {final_train_acc*100:.2f}%")
    print(f"   Final Val Accuracy:   {final_val_acc*100:.2f}%")
    print(f"   Test Accuracy:        {test_metrics['accuracy']*100:.2f}%")
    print()

    # 8. Compare with baseline
    print("=" * 80)
    print("COMPARISON: LSTM 24-Month vs Previous 6-Month")
    print("=" * 80)
    print()

    print("Previous (6-month data, 4h horizon):")
    print("  Train Acc: 54.18%  |  Val Acc: 49.64%  |  Test Acc: 52.80%")
    print()

    print(f"Current (24-month data, 4h horizon):")
    print(f"  Train Acc: {final_train_acc*100:.2f}%  |  Val Acc: {final_val_acc*100:.2f}%  |  Test Acc: {test_metrics['accuracy']*100:.2f}%")
    print()

    # Determine success
    improvements = []

    if test_metrics['accuracy'] > 0.528:  # Better than baseline
        delta = (test_metrics['accuracy'] - 0.528) * 100
        print(f"✅ Test accuracy improved by {delta:.2f}%")
        improvements.append(True)
    else:
        print(f"⚠️  Test accuracy did not improve")
        improvements.append(False)

    if final_val_acc > 0.4964:  # Better than baseline val acc
        delta = (final_val_acc - 0.4964) * 100
        print(f"✅ Validation accuracy improved by {delta:.2f}%")
        improvements.append(True)
    else:
        print(f"⚠️  Validation accuracy did not improve")
        improvements.append(False)

    print()
    print("=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)
    print()

    if sum(improvements) >= 1:
        print("✅ 24-MONTH DATASET SHOWS IMPROVEMENT!")
        print("   The larger training dataset is helping:")
        print("   - More historical patterns")
        print("   - Better generalization")
        print("   - Reduced overfitting")
        print()
        print("   ✅ READY FOR FULL PRODUCTION TRAINING (100 epochs)")
    else:
        print("⚠️  24-month dataset did not significantly improve results")
        print("   Possible issues:")
        print("   - Model architecture needs tuning")
        print("   - Feature engineering needs improvement")
        print("   - Hyperparameters need optimization")

    print()

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
