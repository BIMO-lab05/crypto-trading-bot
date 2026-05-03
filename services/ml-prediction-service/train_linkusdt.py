#!/usr/bin/env python3
"""
Train GRU model for LINKUSDT with available data
"""
import os
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent.parent
import sys
import asyncio
import pandas as pd
from datetime import datetime

# Set epochs BEFORE importing GRU model
os.environ['EPOCHS'] = '100'

# Add service directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app.ml_models.gru_model import GRUPricePredictor

async def train_linkusdt():
    """Train GRU model for LINKUSDT"""
    symbol = 'LINKUSDT'

    print(f"\n{'='*80}")
    print(f"TRAINING GRU MODEL: {symbol}")
    print(f"{'='*80}\n")

    # Find data file
    data_dir = str(_REPO_ROOT / 'data/ml_training')
    csv_file = f'{data_dir}/{symbol}_1H_24months_20251210.csv'

    if not os.path.exists(csv_file):
        print(f"❌ ERROR: Data file not found: {csv_file}")
        return False

    # Load data
    print(f"📊 Loading data from {csv_file}")
    df = pd.read_csv(csv_file)
    print(f"   Loaded {len(df)} rows")

    # Check minimum data requirement
    if len(df) < 1000:
        print(f"❌ ERROR: Insufficient data ({len(df)} rows), need at least 1000")
        return False

    # Prepare columns
    if df.columns[0] != 'timestamp':
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Features: {list(df.columns)}")

    # Initialize predictor
    print(f"\n🤖 Initializing GRU predictor...")
    predictor = GRUPricePredictor(symbol=symbol, interval='60')

    # Train
    print(f"\n🚀 Starting training (100 epochs, early stopping)...")
    start_time = datetime.now()

    try:
        result = await predictor.train(df)
        elapsed = (datetime.now() - start_time).total_seconds() / 60

        print(f"\n{'='*80}")
        print(f"✅ TRAINING COMPLETE: {symbol}")
        print(f"{'='*80}")
        print(f"⏱️  Training time: {elapsed:.1f} minutes")
        print(f"📈 R² Score: {result.metrics.get('test_r2', 0):.4f}")
        print(f"📉 MAE: {result.metrics.get('test_mae', 0):.6f}")
        print(f"📉 RMSE: {result.metrics.get('test_rmse', 0):.6f}")
        print(f"💾 Model saved: {result.model_path}")
        print(f"🔖 Version: {result.version}")
        print(f"{'='*80}\n")

        return True

    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds() / 60
        print(f"\n{'='*80}")
        print(f"❌ TRAINING FAILED: {symbol}")
        print(f"{'='*80}")
        print(f"⏱️  Time elapsed: {elapsed:.1f} minutes")
        print(f"❌ Error: {str(e)}")
        print(f"{'='*80}\n")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = asyncio.run(train_linkusdt())
    sys.exit(0 if success else 1)
