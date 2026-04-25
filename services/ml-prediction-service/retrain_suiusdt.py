#!/usr/bin/env python3
"""
Retrain SUIUSDT GRU model with 12-month extended data
Target: Achieve R²>0.85 (previous: 0.6638 with 6-month data)
"""
import os
import sys
import asyncio
import pandas as pd
import time
from datetime import datetime

# Set epochs BEFORE importing GRU model
os.environ['EPOCHS'] = '150'  # More epochs for better convergence
os.environ['BATCH_SIZE'] = '32'
os.environ['VALIDATION_SPLIT'] = '0.2'

# Add service directory to path
sys.path.insert(0, os.path.dirname(__file__))

from app.ml_models.gru_model import GRUPricePredictor

async def retrain_suiusdt():
    """Retrain SUIUSDT with 12-month data"""

    symbol = 'SUIUSDT'
    data_file = '/mnt/d/Bimo_max/crypto-trading-bot/data/ml_training/SUIUSDT_1H_12months_20251210.csv'

    print("\n" + "="*100)
    print(f"RETRAINING SUIUSDT GRU MODEL WITH EXTENDED DATA")
    print("="*100)
    print(f"Previous Performance (6 months):")
    print(f"  R² Score: 0.6638 (BELOW TARGET)")
    print(f"  MAE: 0.0436")
    print(f"  Directional Accuracy: 50.71%")
    print()
    print(f"Target Performance (12 months):")
    print(f"  R² Score: >0.85")
    print(f"  MAE: <0.03")
    print(f"  Directional Accuracy: >70%")
    print("="*100 + "\n")

    # Load data
    print(f"📊 Loading data from: {data_file}")
    df = pd.read_csv(data_file)

    # Ensure correct column names
    if df.columns[0] != 'timestamp':
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

    # Convert types
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # Remove NaN
    df = df.dropna()

    # Sort by timestamp
    df = df.sort_values('timestamp').reset_index(drop=True)

    print(f"   Loaded: {len(df):,} rows")
    print(f"   Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"   Duration: {(df['timestamp'].max() - df['timestamp'].min()).days} days")
    print()

    if len(df) < 1000:
        print(f"❌ ERROR: Insufficient data ({len(df)} rows), need at least 1000")
        return False

    # Initialize predictor
    print(f"🤖 Initializing GRU predictor...")
    predictor = GRUPricePredictor(symbol=symbol, interval='60')

    # Train
    print(f"\n🚀 Starting training (150 epochs with early stopping)...")
    print(f"   Expected time: ~3-5 minutes")
    print(f"   Architecture: 2 GRU layers (128/64 units), 98,245 parameters")
    print()

    start_time = time.time()

    try:
        model_info = await predictor.train(df)
        elapsed = time.time() - start_time

        print(f"\n{'='*100}")
        print(f"✅ TRAINING COMPLETE: SUIUSDT")
        print(f"{'='*100}")
        print(f"⏱️  Training Time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print()
        print(f"📈 Performance Metrics:")
        print(f"   R² Score: {model_info.validation_r2_score:.4f}")
        print(f"   MAE: {model_info.validation_mae:.6f}")
        print(f"   RMSE: {model_info.validation_rmse:.6f}")
        print(f"   Training Samples: {model_info.training_samples:,}")
        print()
        print(f"💾 Model Saved:")
        print(f"   Version: {model_info.model_version}")
        print(f"   Location: /models/SUIUSDT_60m_gru.keras")
        print()

        # Check if target met
        if model_info.validation_r2_score >= 0.85:
            print(f"🎯 TARGET MET: R²={model_info.validation_r2_score:.4f} ≥ 0.85")
            print(f"✅ Model is PRODUCTION READY!")
        elif model_info.validation_r2_score >= 0.75:
            print(f"⚠️  CLOSE TO TARGET: R²={model_info.validation_r2_score:.4f} (target: ≥0.85)")
            print(f"💡 Consider: Deploy with caution or retrain with 24-month data")
        else:
            print(f"❌ BELOW TARGET: R²={model_info.validation_r2_score:.4f} (target: ≥0.85)")
            print(f"💡 Recommendation: Retrain with 24-month data or adjust hyperparameters")

        print()
        print(f"📊 Improvement vs Previous:")
        prev_r2 = 0.6638
        improvement = ((model_info.validation_r2_score - prev_r2) / abs(prev_r2)) * 100
        print(f"   Previous R² (6 months): {prev_r2:.4f}")
        print(f"   New R² (12 months): {model_info.validation_r2_score:.4f}")
        print(f"   Improvement: {improvement:+.2f}%")
        print("="*100 + "\n")

        return {
            'success': True,
            'r2_score': model_info.validation_r2_score,
            'mae': model_info.validation_mae,
            'rmse': model_info.validation_rmse,
            'training_time': elapsed,
            'model_version': model_info.model_version,
            'meets_target': model_info.validation_r2_score >= 0.85
        }

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n{'='*100}")
        print(f"❌ TRAINING FAILED: SUIUSDT")
        print(f"{'='*100}")
        print(f"⏱️  Time Elapsed: {elapsed:.1f}s")
        print(f"❌ Error: {str(e)}")
        print("="*100 + "\n")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

if __name__ == '__main__':
    result = asyncio.run(retrain_suiusdt())

    if result.get('success'):
        print(f"\n✅ SUCCESS: SUIUSDT model retrained")
        print(f"   R² Score: {result['r2_score']:.4f}")
        print(f"   Target Met: {'YES' if result['meets_target'] else 'NO'}")
        sys.exit(0)
    else:
        print(f"\n❌ FAILURE: Training failed")
        sys.exit(1)
