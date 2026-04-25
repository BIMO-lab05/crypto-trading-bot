"""
Simple Ensemble Integration Test
Tests ensemble predictor with live market data
"""

import asyncio
import sys
from pathlib import Path

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import ensemble predictor
from inference.ensemble import EnsemblePredictor


async def test_ensemble_basic():
    """Test ensemble predictor with live data"""

    print("\n" + "="*80)
    print("🧪 ENSEMBLE BASIC INTEGRATION TEST")
    print("="*80)

    # Initialize ensemble
    ensemble = EnsemblePredictor(
        ta_weight=0.40,
        ml_weight=0.30,
        sentiment_weight=0.15,
        multi_tf_weight=0.15
    )

    test_symbols = ["BTCUSDT", "ETHUSDT"]
    test_intervals = ["60"]
    test_models = ["LSTM"]

    results = []

    for symbol in test_symbols:
        for interval in test_intervals:
            for model in test_models:
                print(f"\n{'='*60}")
                print(f"Testing: {symbol} @ {interval}m with {model}")
                print(f"{'='*60}")

                try:
                    # Get prediction
                    signal = await ensemble.predict(
                        symbol=symbol,
                        interval=interval,
                        ml_model=model
                    )

                    # Display results
                    print(f"\n✅ Prediction successful!")
                    print(f"   Symbol: {signal.symbol}")
                    print(f"   Direction: {signal.direction}")
                    print(f"   Confidence: {signal.confidence:.2%}")
                    print(f"   Strength: {signal.strength:.3f}")
                    print(f"   Components Used: {signal.components_used}/{signal.components_available}")
                    print(f"   Weighted Score: {signal.weighted_score:.3f}")

                    # Component breakdown
                    print(f"\n   Component Breakdown:")
                    for component in signal.components:
                        print(f"      ✅ {component.source}: {component.raw_score:+.3f} (weight: {component.weight:.1%}, dir: {component.direction})")

                    results.append({
                        'symbol': symbol,
                        'interval': interval,
                        'model': model,
                        'success': True,
                        'direction': signal.direction,
                        'confidence': signal.confidence,
                        'components_used': signal.components_used
                    })

                except Exception as e:
                    print(f"\n❌ Error: {e}")
                    results.append({
                        'symbol': symbol,
                        'interval': interval,
                        'model': model,
                        'success': False,
                        'error': str(e)
                    })

                # Small delay between requests
                await asyncio.sleep(1)

    # Summary
    print(f"\n\n{'='*80}")
    print("📊 TEST SUMMARY")
    print("="*80)

    successful = sum(1 for r in results if r.get('success'))
    total = len(results)

    print(f"\nTotal Tests: {total}")
    print(f"Successful: {successful}/{total} ({successful/total*100:.1f}%)")

    # Display all results
    print(f"\n{'Symbol':<12} {'Interval':<10} {'Model':<8} {'Status':<10} {'Direction':<10} {'Confidence':<12} {'Components':<12}")
    print("-"*80)
    for r in results:
        status = "✅ PASS" if r.get('success') else "❌ FAIL"
        direction = r.get('direction', 'N/A')
        confidence = f"{r.get('confidence', 0):.2%}" if r.get('success') else 'N/A'
        components = f"{r.get('components_used', 0)}/4" if r.get('success') else 'N/A'

        print(f"{r['symbol']:<12} {r['interval']:<10} {r['model']:<8} {status:<10} {direction:<10} {confidence:<12} {components:<12}")

    # Final assessment
    print(f"\n{'='*80}")
    if successful == total:
        print("🎉 ALL TESTS PASSED - Ensemble is working correctly!")
        print("="*80)
        await ensemble.close()
        return True
    elif successful > 0:
        print(f"⚠️ PARTIAL SUCCESS - {successful}/{total} tests passed")
        print("="*80)
        await ensemble.close()
        return False
    else:
        print("❌ ALL TESTS FAILED - Ensemble needs debugging")
        print("="*80)
        await ensemble.close()
        return False


async def main():
    """Run ensemble integration test"""
    success = await test_ensemble_basic()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
