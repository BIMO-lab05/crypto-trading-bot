#!/usr/bin/env python3
"""
ML Model Training Status Checker
Comprehensive verification of ML model training status and performance

Purpose:
- Check if model files exist
- Validate model metadata and performance metrics
- Test model predictions via API
- Identify models needing retraining
- Generate detailed status report

Author: Backend Developer Agent
Date: 2025-11-22
"""

import requests
import json
import sys
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent
from datetime import datetime
from typing import Dict, List, Optional
import time

# Configuration
ML_SERVICE_URL = "http://localhost:8007"
MODELS_DIR = (_REPO_ROOT / 'services/ml-prediction-service/trained_models')
TRAINING_RESULTS_FILE = MODELS_DIR / "training_results.json"

# Target symbols
SYMBOLS = [
    'BTCUSDT',
    'ETHUSDT',
    'BNBUSDT',
    'SOLUSDT',
    'XRPUSDT',
    'ADAUSDT',
    'DOGEUSDT'
]

MODEL_TYPES = ['LSTM', 'GRU']
TARGET_R2_SCORE = 0.99
ACCEPTABLE_R2_SCORE = 0.85  # Minimum acceptable for production


class MLStatusChecker:
    """Checks ML model training status and performance"""

    def __init__(self):
        """Initialize status checker"""
        self.status = {
            'timestamp': datetime.utcnow().isoformat(),
            'service_health': None,
            'models_found': [],
            'models_loaded': [],
            'training_results': None,
            'api_tests': [],
            'recommendations': []
        }

    def check_service_health(self) -> bool:
        """Check if ML service is running and healthy"""
        print("\n" + "="*80)
        print("CHECKING ML SERVICE HEALTH")
        print("="*80)

        try:
            # Health check
            response = requests.get(f"{ML_SERVICE_URL}/health", timeout=5)
            health_status = response.json()
            print(f"✓ Service health: {health_status.get('status', 'unknown')}")

            # Readiness check
            response = requests.get(f"{ML_SERVICE_URL}/ready", timeout=5)
            ready_status = response.json()

            print(f"✓ Service ready: {ready_status.get('ready', False)}")
            print(f"✓ Models loaded: {ready_status.get('models_loaded', False)}")
            print(f"✓ TensorFlow available: {ready_status.get('dependencies_available', {}).get('tensorflow', False)}")
            print(f"✓ Market data service: {ready_status.get('dependencies_available', {}).get('market_data_service', False)}")

            self.status['service_health'] = {
                'healthy': health_status.get('status') == 'healthy',
                'ready': ready_status.get('ready', False),
                'tensorflow': ready_status.get('dependencies_available', {}).get('tensorflow', False),
                'market_data': ready_status.get('dependencies_available', {}).get('market_data_service', False)
            }

            return True

        except Exception as e:
            print(f"✗ Service health check failed: {e}")
            self.status['service_health'] = {'healthy': False, 'error': str(e)}
            return False

    def check_model_files(self) -> Dict:
        """Check if model files exist on disk"""
        print("\n" + "="*80)
        print("CHECKING MODEL FILES ON DISK")
        print("="*80)

        results = {}

        for symbol in SYMBOLS:
            results[symbol] = {}

            for model_type in MODEL_TYPES:
                # Model file paths
                if model_type == 'LSTM':
                    model_file = MODELS_DIR / f"{symbol}_60m_lstm.keras"
                    metadata_file = MODELS_DIR / f"{symbol}_60m_metadata.json"
                    scalers_file = MODELS_DIR / f"{symbol}_60m_scalers.pkl"
                else:  # GRU
                    model_file = MODELS_DIR / f"{symbol}_60m_gru.keras"
                    metadata_file = MODELS_DIR / f"{symbol}_60m_gru_metadata.json"
                    scalers_file = MODELS_DIR / f"{symbol}_60m_gru_scalers.pkl"

                # Check files exist
                files_exist = {
                    'model': model_file.exists(),
                    'metadata': metadata_file.exists(),
                    'scalers': scalers_file.exists()
                }

                all_exist = all(files_exist.values())

                # Get file sizes
                if all_exist:
                    model_size_mb = model_file.stat().st_size / (1024 * 1024)

                    # Read metadata
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                    except:
                        metadata = {}

                    results[symbol][model_type] = {
                        'exists': True,
                        'size_mb': round(model_size_mb, 2),
                        'metadata': metadata
                    }

                    status_symbol = '✓'
                else:
                    results[symbol][model_type] = {
                        'exists': False,
                        'missing_files': [k for k, v in files_exist.items() if not v]
                    }
                    status_symbol = '✗'

                print(f"{status_symbol} {symbol} {model_type}: {'Found' if all_exist else 'Missing'}")

        self.status['models_found'] = results
        return results

    def check_loaded_models(self) -> List:
        """Check which models are loaded in the service"""
        print("\n" + "="*80)
        print("CHECKING LOADED MODELS IN SERVICE")
        print("="*80)

        try:
            response = requests.get(f"{ML_SERVICE_URL}/api/v1/models", timeout=5)
            loaded_models = response.json()

            print(f"Total models loaded: {loaded_models.get('total_models', 0)}")
            print(f"  LSTM models: {loaded_models.get('lstm_count', 0)}")
            print(f"  GRU models: {loaded_models.get('gru_count', 0)}")

            for model in loaded_models.get('models', []):
                print(f"  ✓ {model['symbol']} {model['model_type']} - Version: {model.get('version', 'unknown')}")

            self.status['models_loaded'] = loaded_models.get('models', [])
            return loaded_models.get('models', [])

        except Exception as e:
            print(f"✗ Failed to check loaded models: {e}")
            return []

    def load_training_results(self) -> Optional[Dict]:
        """Load and analyze training results"""
        print("\n" + "="*80)
        print("ANALYZING TRAINING RESULTS")
        print("="*80)

        try:
            if not TRAINING_RESULTS_FILE.exists():
                print("✗ Training results file not found")
                return None

            with open(TRAINING_RESULTS_FILE, 'r') as f:
                results = json.load(f)

            training_date = results.get('timestamp', 'unknown')
            print(f"Training date: {training_date}")
            print(f"Total symbols: {results.get('total_symbols', 0)}")
            print(f"Total models attempted: {results.get('total_models_attempted', 0)}")

            # Analyze results
            model_results = results.get('results', [])
            successful = [r for r in model_results if r.get('status') == 'SUCCESS']
            meets_target = [r for r in successful if r.get('r2_score', 0) >= TARGET_R2_SCORE]
            acceptable = [r for r in successful if r.get('r2_score', 0) >= ACCEPTABLE_R2_SCORE]

            print(f"\nPerformance Summary:")
            print(f"  Successful models: {len(successful)}/{len(model_results)}")
            print(f"  Meeting target (R² ≥ {TARGET_R2_SCORE}): {len(meets_target)}/{len(successful)}")
            print(f"  Acceptable (R² ≥ {ACCEPTABLE_R2_SCORE}): {len(acceptable)}/{len(successful)}")

            # Per-symbol breakdown
            print(f"\nPer-Symbol Performance:")
            print(f"{'Symbol':<12} {'Model':<6} {'R² Score':<12} {'Status':<10}")
            print("-" * 50)

            for symbol in SYMBOLS:
                symbol_results = [r for r in model_results if r.get('symbol') == symbol]
                for result in symbol_results:
                    model_type = result.get('model_type', 'Unknown')
                    r2_score = result.get('r2_score', 0)

                    if r2_score >= TARGET_R2_SCORE:
                        status = "EXCELLENT"
                    elif r2_score >= ACCEPTABLE_R2_SCORE:
                        status = "GOOD"
                    elif r2_score >= 0.7:
                        status = "FAIR"
                    elif r2_score >= 0:
                        status = "POOR"
                    else:
                        status = "FAILED"

                    print(f"{symbol:<12} {model_type:<6} {r2_score:>10.4f}  {status:<10}")

            self.status['training_results'] = results
            return results

        except Exception as e:
            print(f"✗ Failed to load training results: {e}")
            return None

    def test_predictions(self) -> List[Dict]:
        """Test predictions for all models"""
        print("\n" + "="*80)
        print("TESTING MODEL PREDICTIONS")
        print("="*80)

        test_results = []

        for symbol in SYMBOLS:
            for model_type in MODEL_TYPES:
                print(f"\nTesting {symbol} {model_type}...", end=" ")

                try:
                    start_time = time.time()
                    response = requests.get(
                        f"{ML_SERVICE_URL}/api/v1/predict/price/{symbol}",
                        params={'interval': '60', 'model_type': model_type},
                        timeout=10
                    )
                    latency = (time.time() - start_time) * 1000  # Convert to ms

                    if response.status_code == 200:
                        prediction = response.json()

                        result = {
                            'symbol': symbol,
                            'model_type': model_type,
                            'status': 'SUCCESS',
                            'latency_ms': round(latency, 2),
                            'current_price': prediction.get('current_price'),
                            'predictions_count': len(prediction.get('predictions', [])),
                            'avg_confidence': prediction.get('average_confidence')
                        }

                        print(f"✓ ({latency:.0f}ms, confidence: {result['avg_confidence']:.2f})")

                    else:
                        result = {
                            'symbol': symbol,
                            'model_type': model_type,
                            'status': 'FAILED',
                            'error': response.json().get('detail', 'Unknown error')
                        }
                        print(f"✗ {result['error']}")

                    test_results.append(result)

                except Exception as e:
                    result = {
                        'symbol': symbol,
                        'model_type': model_type,
                        'status': 'ERROR',
                        'error': str(e)
                    }
                    print(f"✗ {str(e)}")
                    test_results.append(result)

        self.status['api_tests'] = test_results
        return test_results

    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on status"""
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)

        recommendations = []

        # Check service health
        if not self.status.get('service_health', {}).get('healthy', False):
            recommendations.append("CRITICAL: ML service is not healthy - restart the service")

        # Check if models are loaded
        if len(self.status.get('models_loaded', [])) == 0:
            recommendations.append("WARNING: No models are loaded in the service - restart may be needed")

        # Check training results
        if self.status.get('training_results'):
            results = self.status['training_results'].get('results', [])

            # Find models with poor performance
            poor_models = [
                r for r in results
                if r.get('status') == 'SUCCESS' and r.get('r2_score', 0) < ACCEPTABLE_R2_SCORE
            ]

            if poor_models:
                recommendations.append(
                    f"RETRAIN: {len(poor_models)} models have R² < {ACCEPTABLE_R2_SCORE} - need retraining with more data"
                )

                # List specific models
                for model in poor_models:
                    recommendations.append(
                        f"  - {model.get('symbol')} {model.get('model_type')}: R²={model.get('r2_score', 0):.4f}"
                    )

        # Check API test results
        failed_tests = [t for t in self.status.get('api_tests', []) if t.get('status') != 'SUCCESS']
        if failed_tests:
            recommendations.append(f"ERROR: {len(failed_tests)} prediction tests failed")

        # Check prediction latency
        successful_tests = [t for t in self.status.get('api_tests', []) if t.get('status') == 'SUCCESS']
        if successful_tests:
            avg_latency = sum(t.get('latency_ms', 0) for t in successful_tests) / len(successful_tests)
            if avg_latency > 100:
                recommendations.append(f"PERFORMANCE: Average prediction latency is {avg_latency:.0f}ms (target: <100ms)")

        # Print recommendations
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                print(f"{i}. {rec}")
        else:
            print("✓ All systems operating normally!")

        self.status['recommendations'] = recommendations
        return recommendations

    def save_report(self, filename: str = "ml_status_report.json"):
        """Save status report to file"""
        report_file = (_REPO_ROOT / 'scripts') / filename

        with open(report_file, 'w') as f:
            json.dump(self.status, f, indent=2)

        print(f"\n✓ Report saved to: {report_file}")

    def run_full_check(self):
        """Run complete status check"""
        print("\n" + "#"*80)
        print("ML MODEL TRAINING STATUS CHECK")
        print(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print("#"*80)

        # Run all checks
        self.check_service_health()
        self.check_model_files()
        self.check_loaded_models()
        self.load_training_results()

        # Only test predictions if service is healthy
        if self.status.get('service_health', {}).get('healthy', False):
            self.test_predictions()
        else:
            print("\n⚠️  Skipping prediction tests - service is not healthy")

        self.generate_recommendations()

        # Save report
        self.save_report(f"ml_status_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json")

        # Print summary
        print("\n" + "#"*80)
        print("SUMMARY")
        print("#"*80)

        models_found = sum(
            1 for symbol_data in self.status.get('models_found', {}).values()
            for model_data in symbol_data.values()
            if model_data.get('exists', False)
        )

        print(f"Models found on disk: {models_found}/{len(SYMBOLS) * len(MODEL_TYPES)}")
        print(f"Models loaded in service: {len(self.status.get('models_loaded', []))}")
        print(f"Successful predictions: {sum(1 for t in self.status.get('api_tests', []) if t.get('status') == 'SUCCESS')}")
        print(f"Recommendations: {len(self.status.get('recommendations', []))}")

        print("\n" + "#"*80)


def main():
    """Main entry point"""
    try:
        checker = MLStatusChecker()
        checker.run_full_check()
        return 0

    except KeyboardInterrupt:
        print("\n\n⚠️  Check interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n✗ Check failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
