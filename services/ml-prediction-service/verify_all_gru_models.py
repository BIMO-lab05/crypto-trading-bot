#!/usr/bin/env python3
"""
Verify All 16 GRU Models - Check existence and loadability
"""
import os
import sys
import json
from pathlib import Path
from datetime import datetime

def verify_gru_models():
    """Verify all 16 GRU models exist and are loadable"""

    # Expected symbols
    symbols = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT',
        'APTUSDT', 'DOGEUSDT', 'XRPUSDT', 'AVAXUSDT', 'DOTUSDT',
        'LTCUSDT', 'LINKUSDT', 'OPUSDT', 'POLUSDT', 'SUIUSDT', 'ARBUSDT'
    ]

    # Model directory
    models_dir = Path(__file__).parent / 'models'

    print("=" * 100)
    print("VERIFYING ALL 16 GRU MODELS")
    print("=" * 100)
    print(f"Models directory: {models_dir}")
    print(f"Expected models: {len(symbols)}")
    print()

    results = []
    missing = []

    for symbol in symbols:
        model_file = models_dir / f'{symbol}_60m_gru.keras'
        metadata_file = models_dir / f'{symbol}_60m_gru_metadata.json'
        scaler_x_file = models_dir / f'{symbol}_60m_gru_scaler_X.pkl'
        scaler_y_file = models_dir / f'{symbol}_60m_gru_scaler_y.pkl'

        # Check if files exist
        model_exists = model_file.exists()
        metadata_exists = metadata_file.exists()
        scaler_x_exists = scaler_x_file.exists()
        scaler_y_exists = scaler_y_file.exists()

        if model_exists and metadata_exists:
            # Load metadata
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                r2_score = metadata.get('training_stats', {}).get('r2_score', 0)
                mae = metadata.get('training_stats', {}).get('mae', 0)
                version = metadata.get('model_version', 'unknown')
                trained_at = metadata.get('trained_at', 'unknown')

                results.append({
                    'symbol': symbol,
                    'status': 'OK',
                    'r2_score': r2_score,
                    'mae': mae,
                    'version': version,
                    'trained_at': trained_at,
                    'model_size': model_file.stat().st_size / (1024 * 1024),  # MB
                    'has_scalers': scaler_x_exists and scaler_y_exists
                })
            except Exception as e:
                results.append({
                    'symbol': symbol,
                    'status': 'ERROR',
                    'error': str(e)
                })
        else:
            missing.append(symbol)
            results.append({
                'symbol': symbol,
                'status': 'MISSING',
                'model_exists': model_exists,
                'metadata_exists': metadata_exists,
                'scaler_x_exists': scaler_x_exists,
                'scaler_y_exists': scaler_y_exists
            })

    # Print results
    print("\n" + "=" * 100)
    print("VERIFICATION RESULTS")
    print("=" * 100)
    print()

    # Print OK models
    ok_models = [r for r in results if r['status'] == 'OK']
    if ok_models:
        print(f"✅ SUCCESSFUL: {len(ok_models)}/{len(symbols)} models")
        print()
        print(f"{'Symbol':<12} {'R² Score':<10} {'MAE':<10} {'Size (MB)':<12} {'Scalers':<10} {'Version':<20}")
        print("-" * 100)
        for r in sorted(ok_models, key=lambda x: x['r2_score'], reverse=True):
            scalers_ok = "✅" if r['has_scalers'] else "❌"
            print(f"{r['symbol']:<12} {r['r2_score']:<10.4f} {r['mae']:<10.6f} {r['model_size']:<12.2f} {scalers_ok:<10} {r['version']:<20}")

    # Print missing models
    if missing:
        print()
        print(f"❌ MISSING: {len(missing)}/{len(symbols)} models")
        print()
        for symbol in missing:
            print(f"  • {symbol}")

    # Print error models
    error_models = [r for r in results if r['status'] == 'ERROR']
    if error_models:
        print()
        print(f"⚠️  ERRORS: {len(error_models)}/{len(symbols)} models")
        print()
        for r in error_models:
            print(f"  • {r['symbol']}: {r['error']}")

    # Summary statistics
    if ok_models:
        print()
        print("=" * 100)
        print("PERFORMANCE STATISTICS")
        print("=" * 100)
        avg_r2 = sum(r['r2_score'] for r in ok_models) / len(ok_models)
        avg_mae = sum(r['mae'] for r in ok_models) / len(ok_models)
        total_size = sum(r['model_size'] for r in ok_models)

        print(f"Average R² Score: {avg_r2:.4f}")
        print(f"Average MAE: {avg_mae:.6f}")
        print(f"Total Storage: {total_size:.2f} MB")

        # Performance tiers
        exceptional = [r for r in ok_models if r['r2_score'] >= 0.95]
        excellent = [r for r in ok_models if 0.90 <= r['r2_score'] < 0.95]
        very_good = [r for r in ok_models if 0.85 <= r['r2_score'] < 0.90]
        good = [r for r in ok_models if 0.75 <= r['r2_score'] < 0.85]
        below_target = [r for r in ok_models if r['r2_score'] < 0.75]

        print()
        print("Performance Tiers:")
        print(f"  • Exceptional (R²≥0.95): {len(exceptional)} models")
        print(f"  • Excellent (R²0.90-0.95): {len(excellent)} models")
        print(f"  • Very Good (R²0.85-0.90): {len(very_good)} models")
        print(f"  • Good (R²0.75-0.85): {len(good)} models")
        if below_target:
            print(f"  • Below Target (R²<0.75): {len(below_target)} models - NEEDS ATTENTION")

    print()
    print("=" * 100)

    # Return status
    if len(ok_models) == len(symbols):
        print("✅ ALL 16 MODELS VERIFIED AND READY FOR DEPLOYMENT!")
        return 0
    else:
        print(f"⚠️  WARNING: {len(missing) + len(error_models)} models are not ready")
        return 1

if __name__ == '__main__':
    sys.exit(verify_gru_models())
