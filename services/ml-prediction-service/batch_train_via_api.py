#!/usr/bin/env python3
"""
Batch Production Training via API Endpoints
Train LSTM models for all active trading symbols using the API endpoints
"""
import requests
import json
import time
from datetime import datetime

# ML Prediction Service URL
BASE_URL = "http://localhost:8007"

# Active trading symbols (from config)
ACTIVE_SYMBOLS = [
    'BNBUSDT',   # Top performer: +$48.64
    'SOLUSDT',   # Top performer: +$48.16
    'ADAUSDT',   # Top performer: +$22.65
    'APTUSDT',   # New addition
    'DOTUSDT',   # New addition
    'LTCUSDT',   # New addition
]

def train_lstm_model(symbol: str, interval: str = "60", epochs: int = 100):
    """Train LSTM model via API endpoint"""
    url = f"{BASE_URL}/api/v1/models/train"

    payload = {
        "symbol": symbol,
        "interval": interval,
        "epochs": epochs,
        "force_retrain": True
    }

    print(f"   Sending training request for {symbol}...")
    print(f"   URL: {url}")
    print(f"   Payload: {json.dumps(payload, indent=2)}")

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=600  # 10 minute timeout per model
        )

        if response.status_code == 200:
            result = response.json()
            return {"status": "SUCCESS", "data": result}
        else:
            return {
                "status": "FAILED",
                "error": f"HTTP {response.status_code}: {response.text[:200]}"
            }

    except requests.exceptions.Timeout:
        return {"status": "TIMEOUT", "error": "Training request timed out after 10 minutes"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


def main():
    """Train LSTM models for all active symbols"""
    print("=" * 80)
    print("BATCH PRODUCTION TRAINING - LSTM MODELS VIA API")
    print("=" * 80)
    print(f"Training {len(ACTIVE_SYMBOLS)} symbols with 100 epochs each")
    print(f"Target: {BASE_URL}")
    print()

    results = {}

    for i, symbol in enumerate(ACTIVE_SYMBOLS, 1):
        print(f"[{i}/{len(ACTIVE_SYMBOLS)}] Training {symbol}...")
        print("-" * 80)

        start_time = time.time()
        result = train_lstm_model(symbol, interval="60", epochs=100)
        elapsed = time.time() - start_time

        results[symbol] = {
            **result,
            "elapsed_time": f"{elapsed:.1f}s"
        }

        if result["status"] == "SUCCESS":
            print(f"   ✅ {symbol} training complete ({elapsed:.1f}s)")
            if "data" in result:
                data = result["data"]
                if isinstance(data, dict):
                    acc = data.get("validation_accuracy", data.get("model_accuracy", "N/A"))
                    print(f"   📊 Accuracy: {acc}")
        else:
            print(f"   ❌ {symbol} training failed: {result.get('error', 'Unknown error')}")

        print()

        # Small delay between requests
        if i < len(ACTIVE_SYMBOLS):
            time.sleep(2)

    # Print summary
    print("=" * 80)
    print("TRAINING SUMMARY")
    print("=" * 80)
    print()

    success_count = sum(1 for r in results.values() if r['status'] == 'SUCCESS')
    failed_count = len(results) - success_count

    print(f"Total: {len(results)} symbols")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print()

    for symbol, result in results.items():
        status_icon = "✅" if result['status'] == 'SUCCESS' else "❌"
        print(f"{status_icon} {symbol}: {result['status']} ({result['elapsed_time']})")

    print()
    print("Batch training complete!")

    return results


if __name__ == '__main__':
    main()
