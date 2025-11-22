#!/usr/bin/env python3
"""
Debug Feature Mismatch Between Training and Prediction
Purpose: Identify exactly which features differ between training and prediction time
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.predictor import LSTMPricePredictor
from app.ml_models.gru_model import GRUPricePredictor

def analyze_feature_engineering():
    """Analyze feature engineering to count features"""

    # Create sample data with required columns
    sample_data = pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=100, freq='1h'),
        'open': np.random.randn(100).cumsum() + 100,
        'high': np.random.randn(100).cumsum() + 102,
        'low': np.random.randn(100).cumsum() + 98,
        'close': np.random.randn(100).cumsum() + 100,
        'volume': np.random.rand(100) * 1000000,
    })

    print("="*80)
    print("FEATURE ENGINEERING ANALYSIS")
    print("="*80)

    # Analyze LSTM predictor features
    print("\n1. LSTM PREDICTOR FEATURES:")
    print("-"*80)

    lstm_predictor = LSTMPricePredictor(symbol='BTCUSDT', interval='60')
    lstm_features_df = lstm_predictor._create_features(sample_data)

    lstm_feature_cols = [col for col in lstm_features_df.columns if col not in ['timestamp', 'symbol']]

    print(f"Total LSTM features: {len(lstm_feature_cols)}")
    print("\nFeature list:")
    for i, col in enumerate(lstm_feature_cols, 1):
        print(f"  {i:2d}. {col}")

    # Analyze GRU predictor features
    print("\n2. GRU PREDICTOR FEATURES:")
    print("-"*80)

    gru_predictor = GRUPricePredictor(symbol='BTCUSDT', interval='60')
    gru_features_df = gru_predictor._create_features(sample_data)

    gru_feature_cols = [col for col in gru_features_df.columns if col not in ['timestamp', 'symbol']]

    print(f"Total GRU features: {len(gru_feature_cols)}")
    print("\nFeature list:")
    for i, col in enumerate(gru_feature_cols, 1):
        print(f"  {i:2d}. {col}")

    # Check if features match
    print("\n3. FEATURE COMPARISON:")
    print("-"*80)

    if set(lstm_feature_cols) == set(gru_feature_cols):
        print("✓ LSTM and GRU features MATCH")
    else:
        print("✗ LSTM and GRU features DIFFER")

        lstm_only = set(lstm_feature_cols) - set(gru_feature_cols)
        gru_only = set(gru_feature_cols) - set(lstm_feature_cols)

        if lstm_only:
            print(f"\nFeatures in LSTM only: {lstm_only}")
        if gru_only:
            print(f"\nFeatures in GRU only: {gru_only}")

    # Check loaded model metadata
    print("\n4. LOADED MODEL METADATA:")
    print("-"*80)

    models_dir = Path(__file__).parent / 'trained_models'

    # Check LSTM metadata
    lstm_metadata_files = list(models_dir.glob('*_metadata.json'))
    if lstm_metadata_files:
        import json
        for metadata_file in lstm_metadata_files[:2]:  # Show first 2
            print(f"\nFile: {metadata_file.name}")
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                saved_features = metadata.get('feature_columns', [])
                print(f"  Saved features count: {len(saved_features)}")
                print(f"  Features: {saved_features[:5]}... (showing first 5)")
    else:
        print("  No metadata files found in trained_models/")

    # Check GRU metadata
    gru_metadata_files = list(models_dir.glob('*_gru_metadata.json'))
    if gru_metadata_files:
        import json
        for metadata_file in gru_metadata_files[:2]:  # Show first 2
            print(f"\nFile: {metadata_file.name}")
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                saved_features = metadata.get('feature_columns', [])
                print(f"  Saved features count: {len(saved_features)}")
                print(f"  Features: {saved_features[:5]}... (showing first 5)")

    print("\n5. FEATURE BREAKDOWN:")
    print("-"*80)

    # Categorize features
    base_features = ['open', 'high', 'low', 'close', 'volume']
    return_features = [f for f in lstm_feature_cols if 'return' in f]
    momentum_features = [f for f in lstm_feature_cols if 'momentum' in f]
    ma_features = [f for f in lstm_feature_cols if 'sma' in f or 'ema' in f]
    volatility_features = [f for f in lstm_feature_cols if 'volatility' in f or 'range' in f]
    volume_features = [f for f in lstm_feature_cols if 'volume' in f and f != 'volume']
    indicator_features = [f for f in lstm_feature_cols if 'rsi' in f or 'macd' in f or 'bb' in f]

    print(f"Base OHLCV: {len(base_features)} - {base_features}")
    print(f"Returns: {len(return_features)} - {return_features}")
    print(f"Momentum: {len(momentum_features)} - {momentum_features}")
    print(f"Moving Averages: {len(ma_features)} - {ma_features}")
    print(f"Volatility: {len(volatility_features)} - {volatility_features}")
    print(f"Volume-derived: {len(volume_features)} - {volume_features}")
    print(f"Technical Indicators: {len(indicator_features)} - {indicator_features}")

    total_categorized = (len(base_features) + len(return_features) + len(momentum_features) +
                        len(ma_features) + len(volatility_features) + len(volume_features) +
                        len(indicator_features))

    other_features = [f for f in lstm_feature_cols if f not in
                     (base_features + return_features + momentum_features + ma_features +
                      volatility_features + volume_features + indicator_features)]

    if other_features:
        print(f"Other features: {len(other_features)} - {other_features}")
        total_categorized += len(other_features)

    print(f"\nTotal categorized: {total_categorized}")
    print(f"Expected total: {len(lstm_feature_cols)}")

    if total_categorized == len(lstm_feature_cols):
        print("✓ All features accounted for")
    else:
        print(f"✗ Mismatch: {total_categorized} vs {len(lstm_feature_cols)}")

    print("\n" + "="*80)


if __name__ == "__main__":
    analyze_feature_engineering()
