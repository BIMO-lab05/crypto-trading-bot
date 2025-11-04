#!/usr/bin/env python3
"""
Crypto Trading Bot - Pipeline Test Script
Purpose: Test the complete data pipeline
"""

import requests
import json
import time
from typing import Dict, Any

# Colors for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    BOLD = '\033[1m'
    NC = '\033[0m'  # No Color


def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.BLUE}{Colors.BOLD}{text}{Colors.NC}")
    print("=" * 60)


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✓{Colors.NC} {text}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}✗{Colors.NC} {text}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠{Colors.NC} {text}")


def test_endpoint(method: str, url: str, description: str, data: Dict[str, Any] = None) -> bool:
    """Test an API endpoint"""
    print(f"Testing: {description}... ", end="", flush=True)
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=30)
        else:
            print_error(f"Unknown method: {method}")
            return False
        
        if 200 <= response.status_code < 300:
            print(f"{Colors.GREEN}✓{Colors.NC} (HTTP {response.status_code})")
            return True
        else:
            print(f"{Colors.RED}✗{Colors.NC} (HTTP {response.status_code})")
            print(f"  Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"{Colors.RED}✗{Colors.NC} (Connection refused)")
        return False
    except requests.exceptions.Timeout:
        print(f"{Colors.RED}✗{Colors.NC} (Timeout)")
        return False
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.NC} ({str(e)})")
        return False


def main():
    """Run pipeline tests"""
    print_header("🧪 Crypto Trading Bot - Pipeline Test")
    
    results = {"passed": 0, "failed": 0}
    
    # Test 1: Service Health
    print_header("Test 1: Service Health Checks")
    if test_endpoint("GET", "http://localhost:8002/health", "Bybit Connector health"):
        results["passed"] += 1
    else:
        results["failed"] += 1
        print_error("Bybit Connector is not running on port 8002")
        print_warning("Start it with: cd services/bybit-connector && uvicorn app.main:app --port 8002")
    
    if test_endpoint("GET", "http://localhost:8003/health", "Market Data Service health"):
        results["passed"] += 1
    else:
        results["failed"] += 1
        print_error("Market Data Service is not running on port 8003")
        print_warning("Start it with: cd services/market-data-service && uvicorn app.main:app --port 8003")
    
    # Test 2: Readiness
    print_header("Test 2: Service Readiness")
    if test_endpoint("GET", "http://localhost:8002/ready", "Bybit Connector ready"):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if test_endpoint("GET", "http://localhost:8003/ready", "Market Data Service ready"):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 3: Market Data from Bybit
    print_header("Test 3: Bybit Connector - Market Data")
    if test_endpoint("GET", "http://localhost:8002/api/v1/market/ticker?symbol=BTCUSDT&category=linear", "Get BTC ticker"):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    if test_endpoint("GET", "http://localhost:8002/api/v1/market/kline?symbol=BTCUSDT&interval=60&limit=10&category=linear", "Get BTC klines"):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 4: Data Collection
    print_header("Test 4: Market Data Service - Data Collection")
    print("⏳ Collecting 1 day of BTCUSDT klines...")
    if test_endpoint("POST", "http://localhost:8003/api/v1/collect/kline/BTCUSDT?interval=60&days=1", "Collect klines"):
        results["passed"] += 1
        time.sleep(2)  # Wait for data to be stored
    else:
        results["failed"] += 1
    
    print("⏳ Collecting ticker data...")
    if test_endpoint("POST", "http://localhost:8003/api/v1/collect/ticker/BTCUSDT", "Collect ticker"):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 5: Query Data
    print_header("Test 5: Market Data Service - Data Query")
    try:
        response = requests.get("http://localhost:8003/api/v1/klines/BTCUSDT?interval=60&limit=5", timeout=10)
        if response.status_code == 200:
            data = response.json()
            count = data.get("count", 0)
            print_success(f"Retrieved {count} klines from database")
            results["passed"] += 1
        else:
            print_error(f"Failed to query klines (HTTP {response.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_error(f"Failed to query klines: {e}")
        results["failed"] += 1
    
    try:
        response = requests.get("http://localhost:8003/api/v1/ticker/BTCUSDT", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                ticker_data = data.get("data", {})
                print_success(f"Retrieved ticker: ${ticker_data.get('last_price', 'N/A')}")
                results["passed"] += 1
            else:
                print_error("No ticker data available")
                results["failed"] += 1
        else:
            print_error(f"Failed to query ticker (HTTP {response.status_code})")
            results["failed"] += 1
    except Exception as e:
        print_error(f"Failed to query ticker: {e}")
        results["failed"] += 1
    
    # Summary
    print_header("📊 Test Summary")
    print(f"Passed: {Colors.GREEN}{results['passed']}{Colors.NC}")
    print(f"Failed: {Colors.RED}{results['failed']}{Colors.NC}")
    total = results['passed'] + results['failed']
    percentage = (results['passed'] / total * 100) if total > 0 else 0
    print(f"Success Rate: {percentage:.1f}%")
    
    print("\n" + "=" * 60)
    if results['failed'] == 0:
        print_success("✅ All tests passed! Pipeline is working correctly.")
    else:
        print_warning(f"⚠️  {results['failed']} test(s) failed. Check the output above.")
    
    print("\n" + "=" * 60)
    print("Next steps:")
    print("  • View API docs: http://localhost:8002/docs")
    print("  • View API docs: http://localhost:8003/docs")
    print("  • Check logs for detailed information")
    print("=" * 60)
    
    return results['failed'] == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
