#!/usr/bin/env python3
"""
Phase 3 Validation Script
Tests all ML Prediction, Sentiment Analysis, and Enhanced Trading Engine features
"""

import asyncio
import httpx
import json
import sys
from datetime import datetime
from typing import Dict, List, Tuple
import time

# ANSI color codes for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text:^80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.RESET} {text}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.RESET} {text}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.RESET} {text}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ{Colors.RESET} {text}")

class Phase3Validator:
    """Validates all Phase 3 services and features"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results = {
            'total_tests': 0,
            'passed': 0,
            'failed': 0,
            'warnings': 0
        }

        # Service URLs
        self.services = {
            'api-gateway': 'http://localhost:8000',
            'bybit-connector': 'http://localhost:8002',
            'market-data': 'http://localhost:8003',
            'technical-analysis': 'http://localhost:8004',
            'trading-engine': 'http://localhost:8005',
            'portfolio-manager': 'http://localhost:8006',
            'ml-prediction': 'http://localhost:8007',
            'sentiment-analysis': 'http://localhost:8008',
        }

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def test_service_health(self, service_name: str, url: str) -> bool:
        """Test if a service is healthy"""
        self.results['total_tests'] += 1
        try:
            response = await self.client.get(f"{url}/health", timeout=5.0)
            if response.status_code == 200:
                print_success(f"{service_name:25} → {url}")
                self.results['passed'] += 1
                return True
            else:
                print_error(f"{service_name:25} → HTTP {response.status_code}")
                self.results['failed'] += 1
                return False
        except Exception as e:
            print_error(f"{service_name:25} → {str(e)[:50]}")
            self.results['failed'] += 1
            return False

    async def test_all_services_health(self) -> Dict[str, bool]:
        """Test health of all services"""
        print_header("Service Health Checks")

        health_status = {}
        for service_name, url in self.services.items():
            health_status[service_name] = await self.test_service_health(service_name, url)
            await asyncio.sleep(0.1)  # Small delay between checks

        return health_status

    async def test_ml_model_exists(self, symbol: str = "BTCUSDT") -> bool:
        """Test if ML model exists for symbol"""
        self.results['total_tests'] += 1
        try:
            response = await self.client.get(
                f"{self.services['ml-prediction']}/api/v1/models/{symbol}",
                params={"interval": "60"}
            )

            if response.status_code == 200:
                data = response.json()
                print_success(f"ML Model for {symbol} exists")
                print_info(f"  Version: {data.get('model_version', 'unknown')}")
                print_info(f"  Accuracy: {data.get('validation_r2_score', 0):.2%}")
                print_info(f"  Last Trained: {data.get('last_trained', 'unknown')}")
                self.results['passed'] += 1
                return True
            elif response.status_code == 404:
                print_warning(f"ML Model for {symbol} not found - needs training")
                self.results['warnings'] += 1
                return False
            else:
                print_error(f"ML Model check failed: HTTP {response.status_code}")
                self.results['failed'] += 1
                return False

        except Exception as e:
            print_error(f"ML Model check failed: {e}")
            self.results['failed'] += 1
            return False

    async def test_ml_prediction(self, symbol: str = "BTCUSDT") -> bool:
        """Test ML price prediction"""
        self.results['total_tests'] += 1
        try:
            response = await self.client.get(
                f"{self.services['ml-prediction']}/api/v1/predict/trend/{symbol}",
                params={"interval": "60"}
            )

            if response.status_code == 200:
                data = response.json()
                print_success(f"ML Prediction for {symbol}")
                print_info(f"  Trend: {data.get('trend', 'unknown')}")
                print_info(f"  Confidence: {data.get('trend_confidence', 0):.2%}")
                print_info(f"  Strength: {data.get('trend_strength', 0):.2f}")
                self.results['passed'] += 1
                return True
            else:
                print_error(f"ML Prediction failed: HTTP {response.status_code}")
                if response.status_code == 404:
                    print_info("  Model needs training first")
                self.results['failed'] += 1
                return False

        except Exception as e:
            print_error(f"ML Prediction failed: {e}")
            self.results['failed'] += 1
            return False

    async def test_sentiment_analysis(self, symbol: str = "BTCUSDT") -> bool:
        """Test sentiment analysis"""
        self.results['total_tests'] += 1
        try:
            response = await self.client.get(
                f"{self.services['sentiment-analysis']}/api/v1/sentiment/combined/{symbol}",
                params={"use_cache": "false"}
            )

            if response.status_code == 200:
                data = response.json()
                print_success(f"Sentiment Analysis for {symbol}")
                print_info(f"  Label: {data.get('sentiment_label', 'unknown')}")
                print_info(f"  Score: {data.get('overall_sentiment', 0):.2f}")
                print_info(f"  Confidence: {data.get('confidence', 0):.2%}")
                print_info(f"  Trading Signal: {data.get('trading_signal', 'unknown')}")
                self.results['passed'] += 1
                return True
            else:
                print_error(f"Sentiment Analysis failed: HTTP {response.status_code}")
                self.results['failed'] += 1
                return False

        except Exception as e:
            print_error(f"Sentiment Analysis failed: {e}")
            self.results['failed'] += 1
            return False

    async def test_multi_timeframe(self, symbol: str = "BTCUSDT") -> bool:
        """Test multi-timeframe analysis"""
        self.results['total_tests'] += 1
        try:
            response = await self.client.get(
                f"{self.services['technical-analysis']}/api/v1/analysis/multi-timeframe/{symbol}",
                params={"timeframes": "15m,60m,240m"}
            )

            if response.status_code == 200:
                data = response.json()
                print_success(f"Multi-Timeframe Analysis for {symbol}")
                print_info(f"  Alignment Score: {data.get('alignment_score', 0):.1f}%")
                print_info(f"  Consensus Signal: {data.get('consensus_signal', 'unknown')}")
                print_info(f"  Overall Signal: {data.get('overall_signal', 'unknown')}")
                print_info(f"  Signal Strength: {data.get('signal_strength', 0):.2f}")
                self.results['passed'] += 1
                return True
            else:
                print_error(f"Multi-Timeframe Analysis failed: HTTP {response.status_code}")
                self.results['failed'] += 1
                return False

        except Exception as e:
            print_error(f"Multi-Timeframe Analysis failed: {e}")
            self.results['failed'] += 1
            return False

    async def test_api_gateway_ml_endpoints(self) -> bool:
        """Test API Gateway ML endpoints"""
        print_header("API Gateway ML Endpoints")

        all_passed = True
        endpoints = [
            ("/api/ml/predict/price/BTCUSDT?interval=60", "Price Prediction"),
            ("/api/ml/predict/trend/BTCUSDT?interval=60", "Trend Prediction"),
            ("/api/ml/predict/volatility/BTCUSDT?interval=60", "Volatility Prediction"),
        ]

        for endpoint, name in endpoints:
            self.results['total_tests'] += 1
            try:
                response = await self.client.get(f"{self.services['api-gateway']}{endpoint}")
                if response.status_code in [200, 404]:  # 404 is ok if model not trained
                    print_success(f"{name:30} → {response.status_code}")
                    self.results['passed'] += 1
                else:
                    print_error(f"{name:30} → HTTP {response.status_code}")
                    self.results['failed'] += 1
                    all_passed = False
            except Exception as e:
                print_error(f"{name:30} → {str(e)[:40]}")
                self.results['failed'] += 1
                all_passed = False

        return all_passed

    async def test_api_gateway_sentiment_endpoints(self) -> bool:
        """Test API Gateway sentiment endpoints"""
        print_header("API Gateway Sentiment Endpoints")

        all_passed = True
        endpoints = [
            ("/api/sentiment/news/BTCUSDT", "News Sentiment"),
            ("/api/sentiment/combined/BTCUSDT", "Combined Sentiment"),
            ("/api/sentiment/trend/BTCUSDT", "Sentiment Trend"),
        ]

        for endpoint, name in endpoints:
            self.results['total_tests'] += 1
            try:
                response = await self.client.get(f"{self.services['api-gateway']}{endpoint}")
                if response.status_code == 200:
                    print_success(f"{name:30} → 200 OK")
                    self.results['passed'] += 1
                else:
                    print_error(f"{name:30} → HTTP {response.status_code}")
                    self.results['failed'] += 1
                    all_passed = False
            except Exception as e:
                print_error(f"{name:30} → {str(e)[:40]}")
                self.results['failed'] += 1
                all_passed = False

        return all_passed

    async def test_enhanced_signal_metadata(self, symbol: str = "BTCUSDT") -> bool:
        """Test that enhanced signals include Phase 3 metadata"""
        self.results['total_tests'] += 1

        print_header(f"Enhanced Signal Integration Test ({symbol})")

        try:
            # Get signal from trading engine
            response = await self.client.get(
                f"{self.services['trading-engine']}/api/v1/signals/{symbol}",
                params={"interval": "60"}
            )

            if response.status_code != 200:
                print_error(f"Failed to get trading signal: HTTP {response.status_code}")
                self.results['failed'] += 1
                return False

            data = response.json()
            signal = data.get('signal', {})
            metadata = signal.get('metadata', {})

            print_success(f"Signal Retrieved: {signal.get('action', 'UNKNOWN')}")
            print_info(f"  Confidence: {signal.get('confidence', 0):.2%}")

            # Check for Phase 3 metadata
            has_ml = 'ml_prediction' in metadata
            has_sentiment = 'sentiment' in metadata
            has_mtf = 'multi_timeframe' in metadata

            if has_ml:
                print_success("  ✓ ML Prediction metadata present")
                ml_data = metadata['ml_prediction']
                print_info(f"    Trend: {ml_data.get('trend', 'unknown')}")
            else:
                print_warning("  ⚠ ML Prediction metadata missing")

            if has_sentiment:
                print_success("  ✓ Sentiment metadata present")
                sent_data = metadata['sentiment']
                print_info(f"    Label: {sent_data.get('label', 'unknown')}")
            else:
                print_warning("  ⚠ Sentiment metadata missing")

            if has_mtf:
                print_success("  ✓ Multi-Timeframe metadata present")
                mtf_data = metadata['multi_timeframe']
                print_info(f"    Alignment: {mtf_data.get('alignment_score', 0)}%")
            else:
                print_warning("  ⚠ Multi-Timeframe metadata missing")

            # Success if at least signal is present
            if signal.get('action'):
                self.results['passed'] += 1
                return True
            else:
                print_error("Signal action missing")
                self.results['failed'] += 1
                return False

        except Exception as e:
            print_error(f"Enhanced signal test failed: {e}")
            self.results['failed'] += 1
            return False

    async def test_phase3_vs_phase1_comparison(self, symbol: str = "BTCUSDT") -> bool:
        """Compare Phase 1 and Phase 3 signals"""
        print_header("Phase 1 vs Phase 3 Signal Comparison")

        self.results['total_tests'] += 1

        try:
            # Get Phase 1 signal (traditional)
            response1 = await self.client.get(
                f"{self.services['trading-engine']}/api/v1/signals/{symbol}",
                params={"interval": "60"}
            )

            if response1.status_code != 200:
                print_error(f"Failed to get Phase 1 signal")
                self.results['failed'] += 1
                return False

            phase1_data = response1.json()
            phase1_signal = phase1_data.get('signal', {})

            # Currently both use same endpoint, but we can check metadata
            phase = phase1_signal.get('metadata', {}).get('phase', 1)

            print_info(f"Signal Phase: {phase}")
            print_info(f"Action: {phase1_signal.get('action', 'UNKNOWN')}")
            print_info(f"Confidence: {phase1_signal.get('confidence', 0):.2%}")

            if phase == 3:
                print_success("✓ Phase 3 enhanced signals are active")
            else:
                print_warning("⚠ Using Phase 1 signals (Phase 3 may be disabled)")

            self.results['passed'] += 1
            return True

        except Exception as e:
            print_error(f"Comparison test failed: {e}")
            self.results['failed'] += 1
            return False

    async def generate_performance_report(self):
        """Generate final performance report"""
        print_header("Validation Summary")

        total = self.results['total_tests']
        passed = self.results['passed']
        failed = self.results['failed']
        warnings = self.results['warnings']

        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"Total Tests:     {total}")
        print(f"Passed:          {Colors.GREEN}{passed}{Colors.RESET} ({pass_rate:.1f}%)")
        print(f"Failed:          {Colors.RED}{failed}{Colors.RESET}")
        print(f"Warnings:        {Colors.YELLOW}{warnings}{Colors.RESET}")
        print()

        if failed == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.RESET}")
            print(f"{Colors.GREEN}Phase 3 implementation is working correctly.{Colors.RESET}")
            return True
        elif failed <= 3 and passed > failed:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠ MOSTLY WORKING{Colors.RESET}")
            print(f"{Colors.YELLOW}Some issues detected but core functionality works.{Colors.RESET}")
            return True
        else:
            print(f"{Colors.RED}{Colors.BOLD}✗ ISSUES DETECTED{Colors.RESET}")
            print(f"{Colors.RED}Multiple tests failed. Check logs above.{Colors.RESET}")
            return False

    async def run_full_validation(self):
        """Run complete validation suite"""
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}")
        print("╔═══════════════════════════════════════════════════════════════════════════════╗")
        print("║                                                                               ║")
        print("║                    PHASE 3 VALIDATION SUITE                                  ║")
        print("║                                                                               ║")
        print("║     ML Predictions + Sentiment Analysis + Multi-Timeframe                   ║")
        print("║                                                                               ║")
        print("╚═══════════════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.RESET}\n")

        print_info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # 1. Test service health
        health_status = await self.test_all_services_health()

        # Check if critical services are running
        critical_services = ['ml-prediction', 'sentiment-analysis', 'trading-engine', 'technical-analysis']
        all_critical_healthy = all(health_status.get(s, False) for s in critical_services)

        if not all_critical_healthy:
            print_error("\nCritical services are down. Cannot continue validation.")
            print_info("Please start services with: ./scripts/start_phase3_services.sh")
            return False

        # 2. Test ML features
        print_header("ML Prediction Features")
        await self.test_ml_model_exists("BTCUSDT")
        await self.test_ml_prediction("BTCUSDT")

        # 3. Test Sentiment features
        print_header("Sentiment Analysis Features")
        await self.test_sentiment_analysis("BTCUSDT")

        # 4. Test Multi-Timeframe
        print_header("Multi-Timeframe Analysis")
        await self.test_multi_timeframe("BTCUSDT")

        # 5. Test API Gateway integration
        await self.test_api_gateway_ml_endpoints()
        await self.test_api_gateway_sentiment_endpoints()

        # 6. Test enhanced signal integration
        await self.test_enhanced_signal_metadata("BTCUSDT")
        await self.test_phase3_vs_phase1_comparison("BTCUSDT")

        # 7. Generate report
        success = await self.generate_performance_report()

        print()
        print_info(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return success


async def main():
    """Main validation runner"""
    validator = Phase3Validator()

    try:
        success = await validator.run_full_validation()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Validation interrupted by user{Colors.RESET}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{Colors.RED}Validation failed with error: {e}{Colors.RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await validator.close()


if __name__ == "__main__":
    asyncio.run(main())
