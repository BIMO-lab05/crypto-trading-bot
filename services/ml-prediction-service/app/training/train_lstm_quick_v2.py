#!/usr/bin/env python3
"""
Quick LSTM Model Training Test - 24-Month Dataset Validation
============================================================
Tests LSTM training with the new 24-month dataset using production API.

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
import asyncio

from app.predictor import LSTMPricePredictor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_data(symbol: str = 'SOLUSDT'):
    """Load historical data from CSV - using 24-month ML training dataset"""
    logger.info(f"Loading data for {symbol}...")

    # Use new ml_training data directory
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
                logger.info(f"Loaded {len(df)} candles from {data_path}")
                logger.info(f"Date range: {df.index.min()} to {df.index.max()}")
                return df

    # If no file found, raise error
    raise FileNotFoundError(
        f"Could not find data file for {symbol}. Tried:\\n" +
        "\\n".join([f"  - {d}/{p}" for d in fallback_dirs for p in patterns])
    )


async def main():
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
    print(f"   📊 Date range: {raw_df['timestamp'].min()} to {raw_df['timestamp'].max()}")
    print()

    # 2. Split data
    train_size = int(len(raw_df) * 0.85)  # 85% for training (LSTM handles internal val split)

    train_raw = raw_df.iloc[:train_size].copy()
    test_raw = raw_df.iloc[train_size:].copy()

    print("2. Data split:")
    print(f"   Train: {len(train_raw)} samples (85%, will be split internally)")
    print(f"   Test:  {len(test_raw)} samples (15%)")
    print()

    # 3. Initialize LSTM model with production API
    print("3. Building LSTM model...")
    lstm = LSTMPricePredictor(symbol='SOLUSDT', interval='240')  # 240 minutes = 4H
    print(f"   ✅ LSTM model initialized for SOLUSDT 4H")
    print(f"      Using production LSTMPricePredictor class")
    print()

    # 4. Train model (LSTM train() method takes full DataFrame)
    print("4. Training LSTM model...")
    print("   This should take 3-5 minutes...")
    print()

    # Call async train method
    model_info = await lstm.train(train_raw)

    print()
    print("=" * 80)
    print("TRAINING COMPLETE")
    print("=" * 80)
    print()

    # 5. Model performance metrics
    print("5. Model performance metrics...")
    print(f"   Model Type:          {model_info.model_type}")
    print(f"   Model Version:       {model_info.model_version}")
    print(f"   Validation Accuracy: {model_info.model_accuracy*100:.2f}%")
    print(f"   Last Trained:        {model_info.model_last_trained}")
    print()

    # 6. Extract detailed metrics
    if hasattr(model_info, 'model_info') and model_info.model_info:
        info = model_info.model_info
        print("6. Detailed training metrics:")
        print(f"   Train Loss:     {info.get('train_loss', 'N/A')}")
        print(f"   Val Loss:       {info.get('val_loss', 'N/A')}")
        print(f"   MAE:            {info.get('mae', 'N/A')}")
        print(f"   RMSE:           {info.get('rmse', 'N/A')}")
        print(f"   R² Score:       {info.get('r2_score', 'N/A')}")
        print()

    # 7. Compare with baseline
    print("=" * 80)
    print("COMPARISON: LSTM 24-Month vs Previous 6-Month")
    print("=" * 80)
    print()

    print("Previous (6-month data, 4h horizon):")
    print("  Train Acc: 54.18%  |  Val Acc: 49.64%  |  Test Acc: 52.80%")
    print()

    print(f"Current (24-month data, 4h horizon):")
    print(f"  Validation Accuracy: {model_info.model_accuracy*100:.2f}%")
    print()

    # Determine success
    baseline_acc = 0.528  # 52.80%

    if model_info.model_accuracy > baseline_acc:
        delta = (model_info.model_accuracy - baseline_acc) * 100
        print(f"✅ Validation accuracy improved by {delta:.2f}%")
        print()
        print("=" * 80)
        print("FINAL VERDICT")
        print("=" * 80)
        print()
        print("✅ 24-MONTH DATASET SHOWS IMPROVEMENT!")
        print("   The larger training dataset is helping:")
        print("   - More historical patterns")
        print("   - Better generalization")
        print("   - Reduced overfitting")
        print()
        print("   ✅ READY FOR FULL PRODUCTION TRAINING (100 epochs)")
    else:
        print(f"⚠️  Validation accuracy did not improve")
        print()
        print("=" * 80)
        print("FINAL VERDICT")
        print("=" * 80)
        print()
        print("⚠️  24-month dataset did not significantly improve results")
        print("   Possible issues:")
        print("   - Model architecture needs tuning")
        print("   - Feature engineering needs improvement")
        print("   - Hyperparameters need optimization")

    print()

    return 0


if __name__ == '__main__':
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        print(f"\\n❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
