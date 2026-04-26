#!/usr/bin/env python3
"""
GRU Integration Test - Verify end-to-end prediction flow
Tests that trading engine can successfully request and receive GRU predictions
"""
import requests
import json
from datetime import datetime

def test_ml_service_health():
    """Test ML prediction service is running"""
    try:
        response = requests.get("http://localhost:8007/health", timeout=5)
        if response.status_code == 200:
            print("✅ ML Prediction Service: HEALTHY")
            return True
        else:
            print(f"❌ ML Prediction Service: Unhealthy (status {response.status_code})")
            return False
    except Exception as e:
        print(f"❌ ML Prediction Service: NOT REACHABLE - {e}")
        return False

def test_gru_prediction(symbol="BTCUSDT"):
    """Test GRU prediction endpoint"""
    try:
        # Request prediction with GRU model (default now)
        url = f"http://localhost:8007/api/v1/predict/price/{symbol}"
        params = {
            "interval": "60",
            "model_type": "GRU",  # Explicitly request GRU
            "use_cache": False     # Force fresh prediction
        }

        print(f"\n📊 Testing GRU prediction for {symbol}...")
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()

            # Verify it's a GRU prediction
            if data.get('model_type') == 'GRU':
                print(f"✅ Model Type: GRU (correct)")
            else:
                print(f"⚠️  Model Type: {data.get('model_type')} (expected GRU)")

            # Display prediction details
            print(f"   Symbol: {data.get('symbol')}")
            print(f"   Current Price: ${data.get('current_price', 0):.2f}")
            print(f"   Predictions: {len(data.get('predictions', []))} future points")
            print(f"   Direction: {data.get('predicted_direction')}")
            print(f"   Confidence: {data.get('average_confidence', 0):.2%}")
            print(f"   Model Version: {data.get('model_version')}")

            # Check prediction quality
            if data.get('average_confidence', 0) > 0.7:
                print(f"✅ High confidence prediction (>{0.7:.0%})")
            elif data.get('average_confidence', 0) > 0.5:
                print(f"⚠️  Medium confidence prediction (>{0.5:.0%})")
            else:
                print(f"❌ Low confidence prediction (<{0.5:.0%})")

            return True
        else:
            print(f"❌ Prediction failed: HTTP {response.status_code}")
            print(f"   Error: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Prediction request failed: {e}")
        return False

def test_default_model_type():
    """Test that default model type is now GRU"""
    try:
        # Request without specifying model_type (should default to GRU)
        url = "http://localhost:8007/api/v1/predict/price/ETHUSDT"
        params = {
            "interval": "60",
            # No model_type parameter - should default to GRU
            "use_cache": False
        }

        print(f"\n🔍 Testing default model type (no model_type param)...")
        response = requests.get(url, params=params, timeout=30)

        if response.status_code == 200:
            data = response.json()
            model_type = data.get('model_type')

            if model_type == 'GRU':
                print(f"✅ Default model type: GRU (deployment successful!)")
                return True
            else:
                print(f"❌ Default model type: {model_type} (expected GRU)")
                return False
        else:
            print(f"❌ Request failed: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False

def test_multiple_symbols():
    """Test GRU predictions for multiple symbols"""
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]

    print(f"\n📈 Testing GRU predictions for {len(symbols)} symbols...")
    results = []

    for symbol in symbols:
        try:
            url = f"http://localhost:8007/api/v1/predict/price/{symbol}"
            params = {"interval": "60", "model_type": "GRU", "use_cache": False}

            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                results.append({
                    'symbol': symbol,
                    'status': 'SUCCESS',
                    'confidence': data.get('average_confidence', 0),
                    'direction': data.get('predicted_direction'),
                    'model_type': data.get('model_type')
                })
                print(f"   ✅ {symbol}: {data.get('predicted_direction')} (conf={data.get('average_confidence', 0):.2%})")
            else:
                results.append({'symbol': symbol, 'status': 'FAILED'})
                print(f"   ❌ {symbol}: HTTP {response.status_code}")

        except Exception as e:
            results.append({'symbol': symbol, 'status': 'ERROR', 'error': str(e)})
            print(f"   ❌ {symbol}: {e}")

    successful = len([r for r in results if r.get('status') == 'SUCCESS'])
    print(f"\n   Results: {successful}/{len(symbols)} successful")

    return successful == len(symbols)

def main():
    """Run complete integration test suite"""
    print("=" * 80)
    print("GRU MODEL INTEGRATION TEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    tests = []

    # Test 1: Service Health
    print("TEST 1: ML Prediction Service Health")
    print("-" * 80)
    tests.append(("Service Health", test_ml_service_health()))

    # Test 2: GRU Prediction
    print("\nTEST 2: GRU Prediction Functionality")
    print("-" * 80)
    tests.append(("GRU Prediction", test_gru_prediction("BTCUSDT")))

    # Test 3: Default Model Type
    print("\nTEST 3: Default Model Type (GRU)")
    print("-" * 80)
    tests.append(("Default GRU", test_default_model_type()))

    # Test 4: Multiple Symbols
    print("\nTEST 4: Multiple Symbol Predictions")
    print("-" * 80)
    tests.append(("Multi-Symbol", test_multiple_symbols()))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, result in tests:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:.<30} {status}")

    passed = sum(1 for _, result in tests if result)
    total = len(tests)

    print()
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL INTEGRATION TESTS PASSED!")
        print("GRU models are working correctly in production!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        print("Please check the ML prediction service configuration")
        return 1

if __name__ == '__main__':
    exit(main())
