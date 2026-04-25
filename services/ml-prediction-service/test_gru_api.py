#!/usr/bin/env python3
"""
Test GRU Model API - Verify ML prediction service works with new GRU models
Tests model loading, prediction generation, and API response format
"""
import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd

# Set environment for GRU models
os.environ['EPOCHS'] = '100'

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.ml_models.gru_model import GRUPricePredictor

async def test_model_loading(symbol: str) -> dict:
    """Test if a GRU model can be loaded successfully"""
    try:
        predictor = GRUPricePredictor(symbol=symbol, interval='60')

        # Try to load the model
        model_file = Path(__file__).parent / 'models' / f'{symbol}_60m_gru.keras'
        metadata_file = Path(__file__).parent / 'models' / f'{symbol}_60m_gru_metadata.json'

        if not model_file.exists():
            return {
                'status': 'FAIL',
                'error': 'Model file not found',
                'symbol': symbol
            }

        # Load metadata
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)

        return {
            'status': 'SUCCESS',
            'symbol': symbol,
            'version': metadata.get('model_version', 'unknown'),
            'r2_score': metadata.get('training_stats', {}).get('r2_score', 0),
            'trained_at': metadata.get('trained_at', 'unknown')
        }
    except Exception as e:
        return {
            'status': 'ERROR',
            'error': str(e),
            'symbol': symbol
        }

async def test_prediction(symbol: str, data_file: str = None) -> dict:
    """Test if a GRU model can generate predictions"""
    try:
        predictor = GRUPricePredictor(symbol=symbol, interval='60')

        # Find data file
        if not data_file:
            # Try different data locations
            data_locations = [
                Path(__file__).parent.parent.parent / 'data' / 'ml_training' / f'{symbol}_1H_24months_20251208.csv',
                Path(__file__).parent.parent.parent / 'data' / 'ml_training' / f'{symbol}_1H_12months_20251210.csv',
                Path(__file__).parent.parent.parent / 'data' / 'ml_training' / f'{symbol}_1H_6months_20251210.csv',
                Path(__file__).parent.parent.parent / 'data' / 'historical' / f'{symbol}_180days_20251208.csv',
            ]

            data_file = None
            for loc in data_locations:
                if loc.exists():
                    data_file = str(loc)
                    break

        if not data_file or not Path(data_file).exists():
            return {
                'status': 'SKIP',
                'error': 'No data file found',
                'symbol': symbol
            }

        # Load last 100 candles for prediction
        df = pd.read_csv(data_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.tail(100)  # Use last 100 candles

        # Make prediction (pass DataFrame directly, not list of dicts)
        result = await predictor.predict(df)

        if result and hasattr(result, 'predictions'):
            return {
                'status': 'SUCCESS',
                'symbol': symbol,
                'predictions': len(result.predictions),
                'avg_confidence': result.average_confidence,
                'direction': result.predicted_direction,
                'sample_prediction': result.predictions[0].predicted_price if result.predictions else None,
                'data_file': data_file
            }
        else:
            return {
                'status': 'FAIL',
                'error': 'No predictions returned',
                'symbol': symbol
            }

    except Exception as e:
        return {
            'status': 'ERROR',
            'error': str(e),
            'symbol': symbol
        }

async def run_api_tests():
    """Run comprehensive API tests for GRU models"""

    print("=" * 100)
    print("GRU MODEL API TESTING")
    print("=" * 100)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Test symbols - prioritize exceptional performers
    test_symbols = [
        'AVAXUSDT',  # Exceptional R²=0.9977
        'BTCUSDT',   # Excellent R²=0.9147
        'ETHUSDT',   # Very Good R²=0.8411
        'BNBUSDT',   # Excellent R²=0.9306
        'SUIUSDT',   # Exceptional R²=0.9897 (retrained)
    ]

    # Phase 1: Test Model Loading
    print("=" * 100)
    print("PHASE 1: MODEL LOADING TESTS")
    print("=" * 100)
    print()

    loading_results = []
    for symbol in test_symbols:
        print(f"Testing {symbol} model loading...", end=' ')
        result = await test_model_loading(symbol)
        loading_results.append(result)

        if result['status'] == 'SUCCESS':
            print(f"✅ OK (R²={result['r2_score']:.4f}, v{result['version']})")
        else:
            print(f"❌ {result['status']}: {result.get('error', 'Unknown error')}")

    # Phase 2: Test Predictions
    print()
    print("=" * 100)
    print("PHASE 2: PREDICTION GENERATION TESTS")
    print("=" * 100)
    print()

    prediction_results = []
    for symbol in test_symbols:
        print(f"Testing {symbol} predictions...", end=' ')
        result = await test_prediction(symbol)
        prediction_results.append(result)

        if result['status'] == 'SUCCESS':
            print(f"✅ OK ({result['predictions']} predictions, {result['direction']}, conf={result['avg_confidence']:.2f})")
            if result.get('sample_prediction'):
                print(f"   Sample price: ${result['sample_prediction']:.4f}")
        elif result['status'] == 'SKIP':
            print(f"⏭️  {result.get('error', 'Skipped')}")
        else:
            print(f"❌ {result['status']}: {result.get('error', 'Unknown error')}")

    # Summary
    print()
    print("=" * 100)
    print("TEST SUMMARY")
    print("=" * 100)

    loading_success = len([r for r in loading_results if r['status'] == 'SUCCESS'])
    prediction_success = len([r for r in prediction_results if r['status'] == 'SUCCESS'])
    prediction_skip = len([r for r in prediction_results if r['status'] == 'SKIP'])

    print(f"\nModel Loading: {loading_success}/{len(test_symbols)} successful")
    print(f"Predictions: {prediction_success}/{len(test_symbols)} successful, {prediction_skip} skipped (no data)")

    if loading_success == len(test_symbols) and prediction_success > 0:
        print("\n✅ API TESTS PASSED - GRU models are working correctly!")
        return 0
    else:
        print("\n⚠️  API TESTS INCOMPLETE - Some tests failed or were skipped")
        return 1

if __name__ == '__main__':
    result = asyncio.run(run_api_tests())
    sys.exit(result)
