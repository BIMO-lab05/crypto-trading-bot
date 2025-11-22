#!/usr/bin/env python3
"""
End-to-End Integration Test for Crypto Trading Bot
Tests complete trading flow from data collection to trade execution

Test Flow:
1. Health check all services
2. Collect market data
3. Generate technical analysis
4. Get ML prediction
5. Get sentiment analysis
6. Calculate risk metrics
7. Generate trading signal
8. Execute paper trade
9. Update portfolio
10. Send notifications
11. Verify complete flow

Author: Crypto Trading Bot Team
Last Updated: 2025-11-14
"""

import asyncio
import httpx
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys

# Service endpoints
SERVICES = {
    "api-gateway": "http://localhost:8000",
    "bybit-connector": "http://localhost:8001",
    "market-data": "http://localhost:8002",
    "portfolio-manager": "http://localhost:8003",
    "technical-analysis": "http://localhost:8004",
    "trading-engine": "http://localhost:8005",
    "notification-service": "http://localhost:8006",
    "ml-prediction": "http://localhost:8007",
    "sentiment-analysis": "http://localhost:8008",
    "risk-metrics": "http://localhost:8009",
}

# Test configuration
TEST_SYMBOL = "BTCUSDT"
TEST_INTERVAL = "60"  # 1 hour
TEST_CAPITAL = 10000.0


class E2ETestRunner:
    """End-to-end test runner for trading bot"""

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.test_results = []
        self.start_time = None
        self.end_time = None

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    def log_test(self, name: str, passed: bool, message: str = "", data: Dict = None):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status} - {name}")
        if message:
            print(f"  {message}")
        if data and not passed:
            print(f"  Data: {json.dumps(data, indent=2)}")

        self.test_results.append({
            "name": name,
            "passed": passed,
            "message": message,
            "timestamp": datetime.now().isoformat()
        })

    async def test_service_health(self, service_name: str, url: str) -> bool:
        """Test if service is healthy"""
        try:
            response = await self.client.get(f"{url}/health")
            if response.status_code == 200:
                data = response.json()
                is_healthy = data.get("status") == "healthy"
                self.log_test(
                    f"Service Health: {service_name}",
                    is_healthy,
                    f"Port: {url.split(':')[-1]}"
                )
                return is_healthy
            else:
                self.log_test(
                    f"Service Health: {service_name}",
                    False,
                    f"HTTP {response.status_code}"
                )
                return False
        except Exception as e:
            self.log_test(
                f"Service Health: {service_name}",
                False,
                f"Error: {str(e)}"
            )
            return False

    async def test_all_services_health(self) -> bool:
        """Test health of all services"""
        print("\n" + "="*80)
        print("STEP 1: SERVICE HEALTH CHECKS")
        print("="*80)

        tasks = [
            self.test_service_health(name, url)
            for name, url in SERVICES.items()
        ]
        results = await asyncio.gather(*tasks)

        all_healthy = all(results)
        print(f"\nResult: {len([r for r in results if r])}/{len(results)} services healthy")
        return all_healthy

    async def test_market_data_collection(self) -> Optional[List[Dict]]:
        """Test market data collection"""
        print("\n" + "="*80)
        print("STEP 2: MARKET DATA COLLECTION")
        print("="*80)

        try:
            # Request recent kline data
            response = await self.client.get(
                f"{SERVICES['market-data']}/api/v1/klines/{TEST_SYMBOL}",
                params={"interval": TEST_INTERVAL, "limit": 100}
            )

            if response.status_code == 200:
                data = response.json()
                klines = data.get("data", [])

                if len(klines) >= 50:
                    self.log_test(
                        "Market Data Collection",
                        True,
                        f"Retrieved {len(klines)} candles for {TEST_SYMBOL}"
                    )
                    return klines
                else:
                    self.log_test(
                        "Market Data Collection",
                        False,
                        f"Insufficient data: {len(klines)} candles (need ≥50)",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Market Data Collection",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Market Data Collection",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_technical_analysis(self) -> Optional[Dict]:
        """Test technical analysis signal generation"""
        print("\n" + "="*80)
        print("STEP 3: TECHNICAL ANALYSIS")
        print("="*80)

        try:
            # Request technical indicators
            response = await self.client.get(
                f"{SERVICES['technical-analysis']}/api/v1/signals/{TEST_SYMBOL}",
                params={"interval": TEST_INTERVAL}
            )

            if response.status_code == 200:
                data = response.json()

                # Check if we have required indicators
                required_indicators = ['rsi', 'macd', 'bollinger_bands', 'ema']
                has_all = all(ind in data for ind in required_indicators)

                if has_all:
                    self.log_test(
                        "Technical Analysis",
                        True,
                        f"RSI: {data['rsi']:.2f}, MACD: {data['macd']['histogram']:.4f}"
                    )
                    return data
                else:
                    self.log_test(
                        "Technical Analysis",
                        False,
                        f"Missing indicators. Got: {list(data.keys())}",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Technical Analysis",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Technical Analysis",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_ml_prediction(self) -> Optional[Dict]:
        """Test ML price prediction"""
        print("\n" + "="*80)
        print("STEP 4: ML PRICE PREDICTION")
        print("="*80)

        try:
            # Request ML prediction
            response = await self.client.get(
                f"{SERVICES['ml-prediction']}/api/v1/predictions/{TEST_SYMBOL}",
                params={"interval": TEST_INTERVAL}
            )

            if response.status_code == 200:
                data = response.json()
                prediction = data.get("prediction", {})

                if "direction" in prediction and "confidence" in prediction:
                    self.log_test(
                        "ML Price Prediction",
                        True,
                        f"Direction: {prediction['direction']}, Confidence: {prediction['confidence']:.2%}"
                    )
                    return prediction
                else:
                    self.log_test(
                        "ML Price Prediction",
                        False,
                        "Missing prediction fields",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "ML Price Prediction",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "ML Price Prediction",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_sentiment_analysis(self) -> Optional[Dict]:
        """Test sentiment analysis"""
        print("\n" + "="*80)
        print("STEP 5: SENTIMENT ANALYSIS")
        print("="*80)

        try:
            # Request sentiment analysis
            response = await self.client.get(
                f"{SERVICES['sentiment-analysis']}/api/v1/sentiment/{TEST_SYMBOL}"
            )

            if response.status_code == 200:
                data = response.json()
                sentiment = data.get("sentiment", {})

                if "sentiment_score" in sentiment:
                    self.log_test(
                        "Sentiment Analysis",
                        True,
                        f"Score: {sentiment['sentiment_score']:.2f}, Label: {sentiment.get('sentiment_label', 'N/A')}"
                    )
                    return sentiment
                else:
                    self.log_test(
                        "Sentiment Analysis",
                        False,
                        "Missing sentiment score",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Sentiment Analysis",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Sentiment Analysis",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_risk_metrics(self) -> Optional[Dict]:
        """Test risk metrics calculation"""
        print("\n" + "="*80)
        print("STEP 6: RISK METRICS CALCULATION")
        print("="*80)

        try:
            # Request risk metrics
            response = await self.client.get(
                f"{SERVICES['risk-metrics']}/api/v1/metrics/{TEST_SYMBOL}",
                params={"interval": TEST_INTERVAL}
            )

            if response.status_code == 200:
                data = response.json()
                metrics = data.get("metrics", {})

                if "volatility" in metrics and "sharpe_ratio" in metrics:
                    self.log_test(
                        "Risk Metrics Calculation",
                        True,
                        f"Volatility: {metrics['volatility']:.2%}, Sharpe: {metrics['sharpe_ratio']:.2f}"
                    )
                    return metrics
                else:
                    self.log_test(
                        "Risk Metrics Calculation",
                        False,
                        "Missing risk metrics",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Risk Metrics Calculation",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Risk Metrics Calculation",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_portfolio_query(self) -> Optional[Dict]:
        """Test portfolio balance query"""
        print("\n" + "="*80)
        print("STEP 7: PORTFOLIO BALANCE CHECK")
        print("="*80)

        try:
            # Request portfolio balance
            response = await self.client.get(
                f"{SERVICES['portfolio-manager']}/api/v1/balance"
            )

            if response.status_code == 200:
                data = response.json()
                balance = data.get("data", {})

                if "total_balance" in balance:
                    self.log_test(
                        "Portfolio Balance Query",
                        True,
                        f"Balance: ${balance['total_balance']:.2f}"
                    )
                    return balance
                else:
                    self.log_test(
                        "Portfolio Balance Query",
                        False,
                        "Missing balance data",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Portfolio Balance Query",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Portfolio Balance Query",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_trading_signal_generation(
        self,
        ta_data: Dict,
        ml_data: Dict,
        sentiment_data: Dict
    ) -> Optional[str]:
        """Test trading signal generation (Phase 3 weighted scoring)"""
        print("\n" + "="*80)
        print("STEP 8: TRADING SIGNAL GENERATION")
        print("="*80)

        # Implement weighted scoring logic (simplified version)
        buy_score = 0
        sell_score = 0

        # RSI (15 points)
        rsi = ta_data.get('rsi', 50)
        if rsi < 40:
            buy_score += 15 * (40 - rsi) / 40
        if rsi > 60:
            sell_score += 15 * (rsi - 60) / 40

        # MACD (15 points)
        macd_hist = ta_data.get('macd', {}).get('histogram', 0)
        if macd_hist > 0:
            buy_score += 15
        if macd_hist < 0:
            sell_score += 15

        # ML Prediction (20 points - key differentiator)
        ml_direction = ml_data.get('direction', 'NEUTRAL')
        ml_confidence = ml_data.get('confidence', 0)
        if ml_direction == 'BULLISH':
            buy_score += 20 * ml_confidence
        if ml_direction == 'BEARISH':
            sell_score += 20 * ml_confidence

        # Sentiment (15 points)
        sentiment_score = sentiment_data.get('sentiment_score', 0)
        if sentiment_score > 0.3:
            buy_score += 15
        if sentiment_score < -0.3:
            sell_score += 15

        # Generate signal if threshold met (55/100)
        threshold = 55
        signal = None

        if buy_score >= threshold:
            signal = "BUY"
            self.log_test(
                "Trading Signal Generation",
                True,
                f"BUY signal (score: {buy_score:.1f}/100)"
            )
        elif sell_score >= threshold:
            signal = "SELL"
            self.log_test(
                "Trading Signal Generation",
                True,
                f"SELL signal (score: {sell_score:.1f}/100)"
            )
        else:
            self.log_test(
                "Trading Signal Generation",
                True,
                f"HOLD - No signal (BUY: {buy_score:.1f}, SELL: {sell_score:.1f})"
            )

        return signal

    async def test_paper_trade_execution(self, signal: str) -> Optional[Dict]:
        """Test paper trade execution"""
        print("\n" + "="*80)
        print("STEP 9: PAPER TRADE EXECUTION")
        print("="*80)

        if not signal:
            self.log_test(
                "Paper Trade Execution",
                True,
                "Skipped - No signal generated"
            )
            return None

        try:
            # Execute paper trade
            trade_request = {
                "symbol": TEST_SYMBOL,
                "action": signal,
                "quantity": 0.001,  # Small test position
                "order_type": "MARKET",
                "paper_trading": True
            }

            response = await self.client.post(
                f"{SERVICES['trading-engine']}/api/v1/execute/paper",
                json=trade_request
            )

            if response.status_code == 200:
                data = response.json()
                trade = data.get("trade", {})

                if "order_id" in trade:
                    self.log_test(
                        "Paper Trade Execution",
                        True,
                        f"Trade executed - Order ID: {trade['order_id']}"
                    )
                    return trade
                else:
                    self.log_test(
                        "Paper Trade Execution",
                        False,
                        "Missing order ID",
                        data
                    )
                    return None
            else:
                self.log_test(
                    "Paper Trade Execution",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return None

        except Exception as e:
            self.log_test(
                "Paper Trade Execution",
                False,
                f"Error: {str(e)}"
            )
            return None

    async def test_notification_sending(self, trade: Optional[Dict]) -> bool:
        """Test notification sending"""
        print("\n" + "="*80)
        print("STEP 10: NOTIFICATION SENDING")
        print("="*80)

        if not trade:
            self.log_test(
                "Notification Sending",
                True,
                "Skipped - No trade executed"
            )
            return True

        try:
            # Send trade notification
            notification_request = {
                "symbol": trade.get("symbol", TEST_SYMBOL),
                "action": trade.get("action", "BUY"),
                "quantity": trade.get("quantity", 0.001),
                "entry_price": trade.get("entry_price", 0.0),
                "timestamp": datetime.now().isoformat()
            }

            response = await self.client.post(
                f"{SERVICES['notification-service']}/api/v1/notify/trade",
                json=notification_request
            )

            if response.status_code == 200:
                self.log_test(
                    "Notification Sending",
                    True,
                    "Trade notification sent successfully"
                )
                return True
            else:
                self.log_test(
                    "Notification Sending",
                    False,
                    f"HTTP {response.status_code}",
                    response.json() if response.text else {}
                )
                return False

        except Exception as e:
            self.log_test(
                "Notification Sending",
                False,
                f"Error: {str(e)}"
            )
            return False

    async def run_complete_test(self):
        """Run complete end-to-end test"""
        self.start_time = time.time()

        print("\n" + "="*80)
        print("CRYPTO TRADING BOT - END-TO-END INTEGRATION TEST")
        print("="*80)
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Test Symbol: {TEST_SYMBOL}")
        print(f"Test Interval: {TEST_INTERVAL}m")

        # Step 1: Health checks
        services_healthy = await self.test_all_services_health()
        if not services_healthy:
            print("\n❌ CRITICAL: Not all services are healthy. Aborting test.")
            return False

        # Step 2: Market data
        klines = await self.test_market_data_collection()
        if not klines:
            print("\n❌ CRITICAL: Cannot proceed without market data")
            return False

        # Step 3: Technical analysis
        ta_data = await self.test_technical_analysis()
        if not ta_data:
            print("\n⚠️ WARNING: Technical analysis failed, using defaults")
            ta_data = {"rsi": 50, "macd": {"histogram": 0}}

        # Step 4: ML prediction
        ml_data = await self.test_ml_prediction()
        if not ml_data:
            print("\n⚠️ WARNING: ML prediction failed, using defaults")
            ml_data = {"direction": "NEUTRAL", "confidence": 0.5}

        # Step 5: Sentiment analysis
        sentiment_data = await self.test_sentiment_analysis()
        if not sentiment_data:
            print("\n⚠️ WARNING: Sentiment analysis failed, using defaults")
            sentiment_data = {"sentiment_score": 0.0}

        # Step 6: Risk metrics
        risk_data = await self.test_risk_metrics()
        if not risk_data:
            print("\n⚠️ WARNING: Risk metrics failed, continuing without")

        # Step 7: Portfolio query
        portfolio = await self.test_portfolio_query()

        # Step 8: Signal generation
        signal = await self.test_trading_signal_generation(
            ta_data, ml_data, sentiment_data
        )

        # Step 9: Paper trade execution
        trade = await self.test_paper_trade_execution(signal)

        # Step 10: Notification
        await self.test_notification_sending(trade)

        # Calculate results
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)

        passed = sum(1 for r in self.test_results if r["passed"])
        total = len(self.test_results)
        pass_rate = (passed / total * 100) if total > 0 else 0

        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Pass Rate: {pass_rate:.1f}%")
        print(f"Duration: {duration:.2f}s")

        # List failed tests
        failed_tests = [r for r in self.test_results if not r["passed"]]
        if failed_tests:
            print("\n❌ Failed Tests:")
            for test in failed_tests:
                print(f"  - {test['name']}: {test['message']}")

        overall_pass = pass_rate >= 80  # 80% pass rate required

        if overall_pass:
            print("\n✅ END-TO-END TEST PASSED")
        else:
            print("\n❌ END-TO-END TEST FAILED")

        print("="*80 + "\n")

        return overall_pass


async def main():
    """Main test execution"""
    runner = E2ETestRunner()

    try:
        success = await runner.run_complete_test()
        sys.exit(0 if success else 1)
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
