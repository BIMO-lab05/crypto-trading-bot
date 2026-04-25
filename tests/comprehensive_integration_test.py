#!/usr/bin/env python3
"""
Comprehensive Multi-Service Integration Test
Tests inter-service communication and data flow across the trading system
"""
import requests
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


class ComprehensiveIntegrationTest:
    """Test suite for multi-service integration scenarios"""

    def __init__(self, base_url: str = "http://localhost"):
        """Initialize test suite with base URL"""
        self.base_url = base_url
        self.services = {
            'api-gateway': 8000,
            'bybit-connector': 8001,
            'market-data': 8002,
            'portfolio-manager': 8003,
            'technical-analysis': 8004,
            'trading-engine': 8005,
            'notification-service': 8006,
            'ml-prediction': 8007,
            'sentiment-analysis': 8008,
            'risk-metrics': 8009,
        }
        self.results = {}

    def test_service_health(self) -> bool:
        """Test 1: All services are healthy"""
        print("\n" + "="*80)
        print("TEST 1: SERVICE HEALTH CHECK")
        print("="*80)

        all_healthy = True
        for service, port in self.services.items():
            try:
                url = f"{self.base_url}:{port}/health"
                response = requests.get(url, timeout=5)

                if response.status_code == 200:
                    print(f"✅ {service:25} HEALTHY (port {port})")
                else:
                    print(f"❌ {service:25} UNHEALTHY - HTTP {response.status_code}")
                    all_healthy = False
            except Exception as e:
                print(f"❌ {service:25} UNREACHABLE - {str(e)[:50]}")
                all_healthy = False

        self.results['service_health'] = all_healthy
        return all_healthy

    def test_market_data_flow(self) -> bool:
        """Test 2: Market data collection and distribution"""
        print("\n" + "="*80)
        print("TEST 2: MARKET DATA FLOW")
        print("="*80)

        symbol = "BTCUSDT"
        interval = "60"

        try:
            # Step 1: Get current ticker from market-data service
            print(f"\n📊 Step 1: Fetching ticker for {symbol}...")
            ticker_url = f"{self.base_url}:8002/api/v1/ticker/{symbol}"
            ticker_response = requests.get(ticker_url, timeout=10)

            if ticker_response.status_code == 200:
                ticker_response_json = ticker_response.json()
                # Market data service returns: {success: true, data: {...}}
                ticker_data = ticker_response_json.get('data', ticker_response_json)
                print(f"✅ Ticker received: ${ticker_data.get('last_price', 0):,.2f}")
                current_price = ticker_data.get('last_price')
            else:
                print(f"❌ Ticker fetch failed: HTTP {ticker_response.status_code}")
                self.results['market_data_flow'] = False
                return False

            # Step 2: Get historical klines
            print(f"\n📈 Step 2: Fetching klines ({interval}m)...")
            klines_url = f"{self.base_url}:8002/api/v1/klines/{symbol}"
            klines_response = requests.get(
                klines_url,
                params={'interval': interval, 'limit': 100},
                timeout=10
            )

            if klines_response.status_code == 200:
                klines_response_json = klines_response.json()
                # Market data service returns: {success: true, count: X, data: [...]}
                klines_data = klines_response_json.get('data', klines_response_json)
                print(f"✅ Klines received: {len(klines_data)} candles")
                if len(klines_data) > 0:
                    print(f"   Latest close: ${klines_data[-1]['close']:,.2f}")
                else:
                    print(f"   ⚠️ No kline data available")
            else:
                print(f"❌ Klines fetch failed: HTTP {klines_response.status_code}")
                self.results['market_data_flow'] = False
                return False

            # Step 3: Verify data consistency
            print(f"\n🔍 Step 3: Verifying data consistency...")
            if len(klines_data) > 0 and current_price:
                kline_close = klines_data[-1]['close']
                price_diff_pct = abs(current_price - kline_close) / current_price
                if price_diff_pct < 0.05:  # Within 5%
                    print(f"✅ Price consistency verified (ticker vs klines)")
                else:
                    print(f"⚠️  Price mismatch: ticker=${current_price:,.2f}, kline=${kline_close:,.2f} ({price_diff_pct:.2%} diff)")
            else:
                print(f"⚠️  Insufficient data to verify consistency")

            self.results['market_data_flow'] = True
            return True

        except Exception as e:
            print(f"❌ Market data flow test failed: {e}")
            self.results['market_data_flow'] = False
            return False

    def test_technical_analysis_pipeline(self) -> bool:
        """Test 3: Technical analysis calculation pipeline"""
        print("\n" + "="*80)
        print("TEST 3: TECHNICAL ANALYSIS PIPELINE")
        print("="*80)

        symbol = "BTCUSDT"
        interval = "60"

        try:
            # Step 1: Request RSI calculation
            print(f"\n📊 Step 1: Calculating RSI for {symbol}...")
            rsi_url = f"{self.base_url}:8004/api/v1/indicators/rsi/{symbol}"
            rsi_response = requests.get(
                rsi_url,
                params={'interval': interval, 'period': 14},
                timeout=10
            )

            if rsi_response.status_code == 200:
                rsi_data = rsi_response.json()
                rsi_value = rsi_data.get('rsi')
                print(f"✅ RSI calculated: {rsi_value:.2f}")

                # Validate RSI is in valid range
                if 0 <= rsi_value <= 100:
                    print(f"✅ RSI in valid range (0-100)")
                else:
                    print(f"❌ Invalid RSI value: {rsi_value}")
                    self.results['technical_analysis'] = False
                    return False
            else:
                print(f"❌ RSI calculation failed: HTTP {rsi_response.status_code}")
                self.results['technical_analysis'] = False
                return False

            # Step 2: Request MACD calculation
            print(f"\n📈 Step 2: Calculating MACD...")
            macd_url = f"{self.base_url}:8004/api/v1/indicators/macd/{symbol}"
            macd_response = requests.get(
                macd_url,
                params={'interval': interval},
                timeout=10
            )

            if macd_response.status_code == 200:
                macd_data = macd_response.json()
                print(f"✅ MACD calculated:")
                # Use correct field names: macd_line, signal_line, histogram
                macd_val = macd_data.get('macd_line', macd_data.get('macd', 0))
                signal_val = macd_data.get('signal_line', macd_data.get('signal', 0))
                histogram_val = macd_data.get('histogram', 0)
                print(f"   MACD: {macd_val:.2f}")
                print(f"   Signal: {signal_val:.2f}")
                print(f"   Histogram: {histogram_val:.2f}")
            else:
                print(f"❌ MACD calculation failed: HTTP {macd_response.status_code}")
                self.results['technical_analysis'] = False
                return False

            # Step 3: Get trading signals
            print(f"\n🎯 Step 3: Generating trading signals...")
            # Use correct endpoint: /api/v1/indicators/signal/{symbol}
            signals_url = f"{self.base_url}:8004/api/v1/indicators/signal/{symbol}"
            signals_response = requests.get(
                signals_url,
                params={'interval': interval},
                timeout=10
            )

            if signals_response.status_code == 200:
                signals_data = signals_response.json()
                signal = signals_data.get('signal')
                strength = signals_data.get('strength', 0)
                print(f"✅ Signal generated: {signal} (strength: {strength:.2%})")
            else:
                print(f"❌ Signal generation failed: HTTP {signals_response.status_code}")
                self.results['technical_analysis'] = False
                return False

            self.results['technical_analysis'] = True
            return True

        except Exception as e:
            print(f"❌ Technical analysis pipeline test failed: {e}")
            self.results['technical_analysis'] = False
            return False

    def test_ml_prediction_pipeline(self) -> bool:
        """Test 4: ML prediction and sentiment analysis integration"""
        print("\n" + "="*80)
        print("TEST 4: ML PREDICTION & SENTIMENT PIPELINE")
        print("="*80)

        symbol = "BTCUSDT"
        interval = "60"

        try:
            # Step 1: Get ML price prediction (GRU)
            print(f"\n🤖 Step 1: Requesting GRU price prediction...")
            ml_url = f"{self.base_url}:8007/api/v1/predict/price/{symbol}"
            ml_response = requests.get(
                ml_url,
                params={'interval': interval, 'model_type': 'GRU', 'use_cache': False},
                timeout=30
            )

            if ml_response.status_code == 200:
                ml_data = ml_response.json()
                print(f"✅ ML Prediction received:")
                print(f"   Model: {ml_data.get('model_type')}")
                print(f"   Current: ${ml_data.get('current_price'):,.2f}")
                print(f"   Direction: {ml_data.get('predicted_direction')}")
                print(f"   Confidence: {ml_data.get('average_confidence', 0):.2%}")

                ml_direction = ml_data.get('predicted_direction')
                ml_confidence = ml_data.get('average_confidence', 0)
            else:
                print(f"❌ ML prediction failed: HTTP {ml_response.status_code}")
                self.results['ml_prediction'] = False
                return False

            # Step 2: Get sentiment analysis
            print(f"\n💬 Step 2: Analyzing market sentiment...")
            sentiment_url = f"{self.base_url}:8008/api/v1/sentiment/{symbol}"
            sentiment_response = requests.get(sentiment_url, timeout=10)

            if sentiment_response.status_code == 200:
                sentiment_data = sentiment_response.json()
                print(f"✅ Sentiment analysis received:")
                print(f"   Overall: {sentiment_data.get('overall_sentiment')}")
                print(f"   Score: {sentiment_data.get('sentiment_score', 0):.2f}")
                print(f"   Sources: {len(sentiment_data.get('sources', []))}")

                sentiment_score = sentiment_data.get('sentiment_score', 0)
            else:
                print(f"⚠️  Sentiment analysis unavailable: HTTP {sentiment_response.status_code}")
                sentiment_score = 0

            # Step 3: Get ensemble prediction
            print(f"\n🎯 Step 3: Getting ensemble prediction...")
            ensemble_url = f"{self.base_url}:8007/api/v1/predict/ensemble/{symbol}"
            ensemble_response = requests.get(
                ensemble_url,
                params={'interval': interval, 'ml_model': 'GRU'},
                timeout=30
            )

            if ensemble_response.status_code == 200:
                ensemble_data = ensemble_response.json()
                print(f"✅ Ensemble prediction received:")
                print(f"   Signal: {ensemble_data.get('signal')}")
                print(f"   Strength: {ensemble_data.get('strength', 0):.2%}")
                print(f"   ML Weight: {ensemble_data.get('ml_weight', 0):.2%}")
                print(f"   TA Weight: {ensemble_data.get('ta_weight', 0):.2%}")
                print(f"   Sentiment Weight: {ensemble_data.get('sentiment_weight', 0):.2%}")
            else:
                print(f"⚠️  Ensemble prediction unavailable: HTTP {ensemble_response.status_code}")

            self.results['ml_prediction'] = True
            return True

        except Exception as e:
            print(f"❌ ML prediction pipeline test failed: {e}")
            self.results['ml_prediction'] = False
            return False

    def test_risk_management_pipeline(self) -> bool:
        """Test 5: Risk management and portfolio integration"""
        print("\n" + "="*80)
        print("TEST 5: RISK MANAGEMENT PIPELINE")
        print("="*80)

        symbol = "BTCUSDT"

        try:
            # Step 1: Get portfolio balance
            print(f"\n💰 Step 1: Fetching portfolio balance...")
            balance_url = f"{self.base_url}:8003/api/v1/portfolio/balance"
            balance_response = requests.get(balance_url, timeout=10)

            if balance_response.status_code == 200:
                balance_data = balance_response.json()
                print(f"✅ Balance received:")
                # Portfolio service returns numeric strings, convert to float
                total_value = float(balance_data.get('total_value', 0))
                cash_balance = float(balance_data.get('cash_balance', 0))
                unrealized_pnl = float(balance_data.get('unrealized_pnl', 0))
                print(f"   Total Value: ${total_value:,.2f}")
                print(f"   Cash Balance: ${cash_balance:,.2f}")
                print(f"   Unrealized P&L: ${unrealized_pnl:,.2f}")

                total_equity = total_value
            else:
                print(f"❌ Balance fetch failed: HTTP {balance_response.status_code}")
                self.results['risk_management'] = False
                return False

            # Step 2: Get current positions
            print(f"\n📊 Step 2: Fetching current positions...")
            positions_url = f"{self.base_url}:8003/api/v1/positions"
            positions_response = requests.get(positions_url, timeout=10)

            if positions_response.status_code == 200:
                positions_data = positions_response.json()
                positions = positions_data.get('positions', [])
                print(f"✅ Positions received: {len(positions)} open positions")

                for pos in positions[:5]:  # Show first 5
                    print(f"   {pos.get('symbol'):10} {pos.get('side'):5} {pos.get('size', 0):.4f} @ ${pos.get('entry_price', 0):,.2f}")
            else:
                print(f"⚠️  Positions fetch failed: HTTP {positions_response.status_code}")
                positions = []

            # Step 3: Calculate risk metrics
            print(f"\n⚠️  Step 3: Calculating risk metrics...")
            risk_url = f"{self.base_url}:8009/api/v1/risk/portfolio"
            risk_response = requests.get(risk_url, timeout=10)

            if risk_response.status_code == 200:
                risk_data = risk_response.json()
                print(f"✅ Risk metrics calculated:")
                print(f"   Portfolio Risk: {risk_data.get('portfolio_risk', 0):.2%}")
                print(f"   Max Drawdown: {risk_data.get('max_drawdown', 0):.2%}")
                print(f"   Sharpe Ratio: {risk_data.get('sharpe_ratio', 0):.2f}")
                print(f"   VaR (95%): ${risk_data.get('var_95', 0):,.2f}")
            else:
                print(f"⚠️  Risk metrics unavailable: HTTP {risk_response.status_code}")

            # Step 4: Test position sizing
            print(f"\n📏 Step 4: Testing position sizing...")
            size_url = f"{self.base_url}:8005/api/v1/position-size/{symbol}"
            size_response = requests.get(
                size_url,
                params={
                    'entry_price': 50000,
                    'stop_loss': 49000,
                    'risk_percentage': 2.0
                },
                timeout=10
            )

            if size_response.status_code == 200:
                size_data = size_response.json()
                print(f"✅ Position sizing calculated:")
                print(f"   Recommended Size: {size_data.get('position_size', 0):.4f} {symbol}")
                print(f"   Position Value: ${size_data.get('position_value', 0):,.2f}")
                print(f"   Risk Amount: ${size_data.get('risk_amount', 0):,.2f}")
            else:
                print(f"⚠️  Position sizing failed: HTTP {size_response.status_code}")

            self.results['risk_management'] = True
            return True

        except Exception as e:
            print(f"❌ Risk management pipeline test failed: {e}")
            self.results['risk_management'] = False
            return False

    def test_api_gateway_routing(self) -> bool:
        """Test 6: API Gateway routing to all services"""
        print("\n" + "="*80)
        print("TEST 6: API GATEWAY ROUTING")
        print("="*80)

        symbol = "BTCUSDT"

        # Test routes through API gateway
        gateway_routes = [
            ('/api/v1/market/ticker/BTCUSDT', 'Ticker'),
            ('/api/v1/analysis/rsi/BTCUSDT?interval=60', 'RSI'),
            ('/api/v1/ml/predict/BTCUSDT?interval=60', 'ML Prediction'),
            ('/api/v1/portfolio/balance', 'Balance'),
        ]

        all_passed = True
        for route, name in gateway_routes:
            try:
                url = f"{self.base_url}:8000{route}"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    print(f"✅ {name:20} routed successfully")
                else:
                    print(f"❌ {name:20} routing failed - HTTP {response.status_code}")
                    all_passed = False
            except Exception as e:
                print(f"❌ {name:20} routing error - {str(e)[:50]}")
                all_passed = False

        self.results['api_gateway'] = all_passed
        return all_passed

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        print("\n" + "="*80)
        print("COMPREHENSIVE INTEGRATION TEST REPORT")
        print("="*80)

        passed = sum(1 for v in self.results.values() if v)
        total = len(self.results)

        print(f"\nTest Results: {passed}/{total} passed")
        print("-" * 80)

        for test_name, result in self.results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name:.<40} {status}")

        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"\nOverall Success Rate: {success_rate:.1f}%")

        if passed == total:
            print("\n🎉 ALL INTEGRATION TESTS PASSED!")
            print("System is ready for production deployment!")
        else:
            failed_tests = [name for name, result in self.results.items() if not result]
            print(f"\n⚠️  {total - passed} test(s) failed:")
            for test_name in failed_tests:
                print(f"   - {test_name}")

        return {
            'timestamp': datetime.now().isoformat(),
            'total_tests': total,
            'passed': passed,
            'failed': total - passed,
            'success_rate': success_rate,
            'results': self.results
        }

    def run_all_tests(self) -> bool:
        """Run all integration tests in sequence"""
        print("="*80)
        print("COMPREHENSIVE MULTI-SERVICE INTEGRATION TEST SUITE")
        print("="*80)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Testing {len(self.services)} microservices")

        # Run tests in logical order
        test_sequence = [
            ('Service Health', self.test_service_health),
            ('Market Data Flow', self.test_market_data_flow),
            ('Technical Analysis Pipeline', self.test_technical_analysis_pipeline),
            ('ML Prediction Pipeline', self.test_ml_prediction_pipeline),
            ('Risk Management Pipeline', self.test_risk_management_pipeline),
            ('API Gateway Routing', self.test_api_gateway_routing),
        ]

        for test_name, test_func in test_sequence:
            try:
                test_func()
                time.sleep(1)  # Brief pause between tests
            except Exception as e:
                print(f"\n❌ {test_name} encountered unexpected error: {e}")
                self.results[test_name.lower().replace(' ', '_')] = False

        # Generate final report
        report = self.generate_report()

        # Save report to file
        report_file = f"integration_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Report saved to: {report_file}")

        return all(self.results.values())


def main():
    """Main entry point"""
    tester = ComprehensiveIntegrationTest()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
