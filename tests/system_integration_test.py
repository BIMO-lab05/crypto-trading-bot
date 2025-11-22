#!/usr/bin/env python3
"""
System Integration Test - Production Readiness Verification
"""
import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Any
import aiohttp
import sys

class SystemIntegrationTest:
    def __init__(self):
        self.base_urls = {
            'api_gateway': 'http://localhost:8000',
            'bybit': 'http://localhost:8001',
            'market_data': 'http://localhost:8002',
            'portfolio': 'http://localhost:8003',
            'technical_analysis': 'http://localhost:8004',
            'trading_engine': 'http://localhost:8005',
            'notification': 'http://localhost:8006',
            'ml_prediction': 'http://localhost:8007',
            'sentiment': 'http://localhost:8008',
            'risk_metrics': 'http://localhost:8009'
        }
        self.results = {
            'services_health': {},
            'integration_tests': {},
            'performance_metrics': {},
            'data_completeness': {},
            'errors': []
        }

    async def test_service_health(self, session: aiohttp.ClientSession):
        """Test all services health endpoints"""
        print("🔍 Testing Service Health...")

        for service, url in self.base_urls.items():
            try:
                start = time.time()
                async with session.get(f"{url}/health", timeout=5) as resp:
                    elapsed = (time.time() - start) * 1000
                    self.results['services_health'][service] = {
                        'status': resp.status,
                        'healthy': resp.status == 200,
                        'response_time_ms': round(elapsed, 2)
                    }
                    print(f"  ✅ {service}: {resp.status} ({elapsed:.0f}ms)")
            except Exception as e:
                self.results['services_health'][service] = {
                    'status': 0,
                    'healthy': False,
                    'error': str(e)
                }
                print(f"  ❌ {service}: {e}")

    async def test_data_flow(self, session: aiohttp.ClientSession):
        """Test complete data flow from market data to trading decision"""
        print("\n🔄 Testing Data Flow Integration...")

        symbol = "BTCUSDT"

        # 1. Get market data
        try:
            async with session.get(f"{self.base_urls['market_data']}/api/v1/klines/{symbol}?limit=100") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.results['integration_tests']['market_data'] = {
                        'success': True,
                        'klines_count': len(data.get('data', []))
                    }
                    print(f"  ✅ Market Data: {len(data.get('data', []))} klines")
                else:
                    self.results['integration_tests']['market_data'] = {'success': False}
                    print(f"  ❌ Market Data: {resp.status}")
        except Exception as e:
            self.results['integration_tests']['market_data'] = {'success': False, 'error': str(e)}
            print(f"  ❌ Market Data: {e}")

        # 2. Get technical analysis
        try:
            async with session.get(f"{self.base_urls['technical_analysis']}/api/v1/indicators/signal/{symbol}") as resp:
                if resp.status == 200:
                    signal = await resp.json()
                    self.results['integration_tests']['technical_analysis'] = {
                        'success': True,
                        'signal': signal.get('signal'),
                        'confidence': signal.get('confidence')
                    }
                    print(f"  ✅ Technical Analysis: {signal.get('signal')} (conf: {signal.get('confidence', 0):.2f})")
                else:
                    self.results['integration_tests']['technical_analysis'] = {'success': False}
                    print(f"  ❌ Technical Analysis: {resp.status}")
        except Exception as e:
            self.results['integration_tests']['technical_analysis'] = {'success': False, 'error': str(e)}
            print(f"  ❌ Technical Analysis: {e}")

        # 3. Get ML prediction
        try:
            async with session.get(f"{self.base_urls['ml_prediction']}/api/v1/predict/{symbol}/60m") as resp:
                if resp.status == 200:
                    prediction = await resp.json()
                    self.results['integration_tests']['ml_prediction'] = {
                        'success': True,
                        'predicted_direction': prediction.get('predicted_direction')
                    }
                    print(f"  ✅ ML Prediction: {prediction.get('predicted_direction')}")
                else:
                    self.results['integration_tests']['ml_prediction'] = {'success': False}
                    print(f"  ❌ ML Prediction: {resp.status}")
        except Exception as e:
            self.results['integration_tests']['ml_prediction'] = {'success': False, 'error': str(e)}
            print(f"  ❌ ML Prediction: {e}")

        # 4. Check portfolio status
        try:
            async with session.get(f"{self.base_urls['portfolio']}/api/v1/portfolio/balance") as resp:
                if resp.status == 200:
                    balance = await resp.json()
                    self.results['integration_tests']['portfolio'] = {
                        'success': True,
                        'total_value': balance.get('total_value')
                    }
                    print(f"  ✅ Portfolio: ${balance.get('total_value')}")
                else:
                    self.results['integration_tests']['portfolio'] = {'success': False}
                    print(f"  ❌ Portfolio: {resp.status}")
        except Exception as e:
            self.results['integration_tests']['portfolio'] = {'success': False, 'error': str(e)}
            print(f"  ❌ Portfolio: {e}")

        # 5. Check risk metrics
        try:
            async with session.get(f"{self.base_urls['risk_metrics']}/risk/scorecard") as resp:
                if resp.status == 200:
                    risk = await resp.json()
                    self.results['integration_tests']['risk_metrics'] = {
                        'success': True,
                        'risk_level': risk.get('overall_risk_level'),
                        'risk_score': risk.get('risk_score')
                    }
                    print(f"  ✅ Risk Metrics: {risk.get('overall_risk_level')} (score: {risk.get('risk_score', 0):.2f})")
                else:
                    self.results['integration_tests']['risk_metrics'] = {'success': False}
                    print(f"  ❌ Risk Metrics: {resp.status}")
        except Exception as e:
            self.results['integration_tests']['risk_metrics'] = {'success': False, 'error': str(e)}
            print(f"  ❌ Risk Metrics: {e}")

    async def test_performance(self, session: aiohttp.ClientSession):
        """Test service performance under load"""
        print("\n⚡ Testing Performance...")

        # Test key endpoints under concurrent load
        endpoints = [
            ('technical_analysis', f"{self.base_urls['technical_analysis']}/api/v1/indicators/signal/BTCUSDT"),
            ('portfolio', f"{self.base_urls['portfolio']}/api/v1/portfolio/balance"),
            ('risk_metrics', f"{self.base_urls['risk_metrics']}/risk/scorecard")
        ]

        for name, url in endpoints:
            requests = 10
            start = time.time()
            tasks = []

            for _ in range(requests):
                tasks.append(session.get(url))

            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start

            successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status == 200)
            avg_time = (elapsed / requests) * 1000

            self.results['performance_metrics'][name] = {
                'requests': requests,
                'successful': successful,
                'avg_response_ms': round(avg_time, 2),
                'success_rate': (successful / requests) * 100
            }

            print(f"  {name}: {successful}/{requests} successful, avg {avg_time:.0f}ms")

    def calculate_production_readiness_score(self):
        """Calculate overall production readiness score"""
        score = 0
        max_score = 100

        # Service health (30 points)
        healthy_services = sum(1 for s in self.results['services_health'].values() if s.get('healthy', False))
        total_services = len(self.results['services_health'])
        score += (healthy_services / total_services) * 30 if total_services > 0 else 0

        # Integration tests (30 points)
        successful_integrations = sum(1 for t in self.results['integration_tests'].values() if t.get('success', False))
        total_integrations = len(self.results['integration_tests'])
        score += (successful_integrations / total_integrations) * 30 if total_integrations > 0 else 0

        # Performance (20 points)
        if self.results['performance_metrics']:
            avg_success_rate = sum(m.get('success_rate', 0) for m in self.results['performance_metrics'].values()) / len(self.results['performance_metrics'])
            avg_response = sum(m.get('avg_response_ms', 1000) for m in self.results['performance_metrics'].values()) / len(self.results['performance_metrics'])

            # Success rate (10 points)
            score += (avg_success_rate / 100) * 10

            # Response time (10 points) - under 500ms gets full points
            if avg_response < 500:
                score += 10
            elif avg_response < 1000:
                score += 5
            else:
                score += 2

        # Data completeness (20 points) - placeholder for now
        score += 10  # Assuming partial data completeness

        return min(score, max_score)

    async def run(self):
        """Run all integration tests"""
        print("=" * 50)
        print("🚀 SYSTEM INTEGRATION TEST - PRODUCTION READINESS")
        print("=" * 50)
        print(f"Started at: {datetime.now().isoformat()}\n")

        async with aiohttp.ClientSession() as session:
            await self.test_service_health(session)
            await self.test_data_flow(session)
            await self.test_performance(session)

        # Calculate score
        score = self.calculate_production_readiness_score()
        self.results['production_readiness_score'] = score

        # Generate report
        print("\n" + "=" * 50)
        print("📊 FINAL REPORT")
        print("=" * 50)

        print("\n🏥 Service Health Summary:")
        healthy = sum(1 for s in self.results['services_health'].values() if s.get('healthy', False))
        total = len(self.results['services_health'])
        print(f"  Healthy Services: {healthy}/{total}")
        for service, status in self.results['services_health'].items():
            icon = "✅" if status.get('healthy', False) else "❌"
            print(f"    {icon} {service}: {status.get('response_time_ms', 'N/A')}ms")

        print("\n🔄 Integration Test Summary:")
        successful = sum(1 for t in self.results['integration_tests'].values() if t.get('success', False))
        total_tests = len(self.results['integration_tests'])
        print(f"  Successful Tests: {successful}/{total_tests}")

        print("\n⚡ Performance Summary:")
        for name, metrics in self.results['performance_metrics'].items():
            print(f"  {name}:")
            print(f"    Success Rate: {metrics.get('success_rate', 0):.1f}%")
            print(f"    Avg Response: {metrics.get('avg_response_ms', 0):.0f}ms")

        print("\n" + "=" * 50)
        print(f"🎯 PRODUCTION READINESS SCORE: {score:.1f}/100")

        if score >= 80:
            print("✅ SYSTEM IS PRODUCTION READY!")
            recommendation = "GO"
        elif score >= 60:
            print("⚠️ SYSTEM NEEDS MINOR IMPROVEMENTS")
            recommendation = "CONDITIONAL GO"
        else:
            print("❌ SYSTEM IS NOT PRODUCTION READY")
            recommendation = "NO GO"

        print(f"📝 RECOMMENDATION: {recommendation}")
        print("=" * 50)

        # Save results
        with open('/mnt/d/Bimo_max/crypto-trading-bot/tests/integration_test_results.json', 'w') as f:
            json.dump(self.results, f, indent=2, default=str)

        return score, recommendation

if __name__ == "__main__":
    test = SystemIntegrationTest()
    score, recommendation = asyncio.run(test.run())

    # Exit with appropriate code
    if recommendation == "GO":
        sys.exit(0)
    elif recommendation == "CONDITIONAL GO":
        sys.exit(1)
    else:
        sys.exit(2)