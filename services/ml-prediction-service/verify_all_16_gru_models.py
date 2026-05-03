#!/usr/bin/env python3
"""
Verify All 16 GRU Models
Checks that all models exist and loads their metadata
"""

from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
import json

MODELS_DIR = (_REPO_ROOT / 'services/ml-prediction-service/models')

ALL_SYMBOLS = [
    'ADAUSDT', 'APTUSDT', 'ARBUSDT', 'AVAXUSDT',
    'BNBUSDT', 'BTCUSDT', 'DOGEUSDT', 'DOTUSDT',
    'ETHUSDT', 'LINKUSDT', 'LTCUSDT', 'OPUSDT',
    'POLUSDT', 'SOLUSDT', 'SUIUSDT', 'XRPUSDT'
]

print("="*100)
print("GRU MODEL VERIFICATION - ALL 16 SYMBOLS")
print("="*100)
print(f"Models directory: {MODELS_DIR}")
print()

complete = []
missing = []
model_data = []

for symbol in sorted(ALL_SYMBOLS):
    model_file = MODELS_DIR / f"{symbol}_60m_gru.keras"
    metadata_file = MODELS_DIR / f"{symbol}_60m_gru_metadata.json"

    if model_file.exists() and metadata_file.exists():
        # Load metadata
        with open(metadata_file) as f:
            metadata = json.load(f)

        size_mb = model_file.stat().st_size / 1024 / 1024
        r2 = metadata.get('validation_r2_score', 0)
        mae = metadata.get('validation_mae', 0)

        print(f"✅ {symbol:12} | R²={r2:.4f} | MAE={mae:.6f} | Size={size_mb:.2f}MB")

        complete.append(symbol)
        model_data.append({
            'symbol': symbol,
            'r2': r2,
            'mae': mae,
            'size_mb': size_mb
        })
    else:
        print(f"❌ {symbol:12} | MISSING")
        missing.append(symbol)

print()
print("="*100)
print(f"SUMMARY: {len(complete)}/16 models available ({len(complete)/16*100:.1f}%)")
print("="*100)

if complete:
    print(f"\n✅ Complete ({len(complete)}): {', '.join(complete)}")

if missing:
    print(f"\n❌ Missing ({len(missing)}): {', '.join(missing)}")

if model_data:
    avg_r2 = sum(m['r2'] for m in model_data) / len(model_data)
    avg_mae = sum(m['mae'] for m in model_data) / len(model_data)

    print(f"\n📊 Average Performance:")
    print(f"   R² Score: {avg_r2:.4f}")
    print(f"   MAE: {avg_mae:.6f}")

    best_r2 = max(model_data, key=lambda x: x['r2'])
    print(f"\n🏆 Best R²: {best_r2['symbol']} ({best_r2['r2']:.4f})")

print()
print("="*100)
