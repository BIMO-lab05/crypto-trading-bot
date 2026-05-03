#!/usr/bin/env python3
"""
Quick check of GRU training status
"""
import os
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

models_dir = (_REPO_ROOT / 'services/ml-prediction-service/models')

# All symbols we want to have GRU models for
ALL_SYMBOLS = [
    'ARBUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 
    'LTCUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT',
    # Already had these 8 from before
    'ADAUSDT', 'APTUSDT', 'BNBUSDT', 'BTCUSDT',
    'DOGEUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT'
]

print("=" * 60)
print("GRU MODEL TRAINING STATUS")
print("=" * 60)

has_gru = []
missing_gru = []

for symbol in sorted(ALL_SYMBOLS):
    gru_file = models_dir / f"{symbol}_60m_gru.keras"
    if gru_file.exists():
        size = gru_file.stat().st_size / 1024 / 1024  # MB
        print(f"✅ {symbol:12} - {size:.2f} MB")
        has_gru.append(symbol)
    else:
        print(f"❌ {symbol:12} - MISSING")
        missing_gru.append(symbol)

print("\n" + "=" * 60)
print(f"SUMMARY: {len(has_gru)}/16 GRU models trained")
print("=" * 60)
print(f"\n✅ Trained ({len(has_gru)}): {', '.join(has_gru)}")
print(f"\n❌ Missing ({len(missing_gru)}): {', '.join(missing_gru)}")
