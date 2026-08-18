#!/usr/bin/env python3
"""
System Verification Script
Purpose: Test all components and verify actual system state
"""

import asyncio
import requests
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)

logger = logging.getLogger(__name__)

# Service endpoints
SERVICES = {
    "API Gateway": "http://localhost:8000",
    "Bybit Connector": "http://localhost:8001",
    "Market Data": "http://localhost:8002",
    "Portfolio Manager": "http://localhost:8003",
    "Technical Analysis": "http://localhost:8004",
    "Trading Engine": "http://localhost:8005",
    "Notification": "http://localhost:8006",
    "ML Prediction": "http://localhost:8007",
    "Sentiment Analysis": "http://localhost:8008",
    "Risk Metrics": "http://localhost:8009",
}

def test_service_health(name, url):
    """Test service health endpoint"""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            status = data.get('status', 'unknown')
            if status == 'healthy':
                return True, "✅ Healthy"
            else:
                return False, f"⚠️  Status: {status}"
        else:
            return False, f"❌ HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "❌ Connection refused"
    except requests.exceptions.Timeout:
        return False, "❌ Timeout"
    except Exception as e:
        return False, f"❌ Error: {str(e)[:50]}"

def check_file_exists(filepath):
    """Check if file exists"""
    return Path(filepath).exists()

def main():
    """Main verification"""
    logger.info("="*80)
    logger.info("SYSTEM VERIFICATION - Testing Actual State")
    logger.info("="*80)

    # Test 1: Service Health
    logger.info("\n📡 SERVICE HEALTH CHECKS")
    logger.info("-"*80)
    healthy_services = 0
    total_services = len(SERVICES)

    for name, url in SERVICES.items():
        is_healthy, message = test_service_health(name, url)
        logger.info(f"{name:25} {url:30} {message}")
        if is_healthy:
            healthy_services += 1

    logger.info(f"\n✅ Services Healthy: {healthy_services}/{total_services}")

    # Test 2: Core Module Files
    logger.info("\n📁 CORE MODULE FILES")
    logger.info("-"*80)

    core_files = {
        "Signal Aggregator": "app/signal_aggregator.py",
        "Auto Trader": "app/auto_trader.py",
        "Position Sizing": "app/position_sizing.py",
        "Performance Tracker": "app/performance_tracker.py",
        "Multi-Timeframe": "app/aggregation/multi_timeframe.py",
        "Validator": "app/aggregation/validator.py",
        "Gatekeeper": "app/aggregation/gatekeeper.py",
    }

    existing_files = 0
    for name, filepath in core_files.items():
        exists = check_file_exists(filepath)
        status = "✅" if exists else "❌"
        logger.info(f"{status} {name:25} {filepath}")
        if exists:
            existing_files += 1

    logger.info(f"\n✅ Files Exist: {existing_files}/{len(core_files)}")

    # Test 3: Test Scripts
    logger.info("\n🧪 TEST SCRIPTS")
    logger.info("-"*80)

    test_scripts = {
        "Multi-Timeframe Test": "test_multi_timeframe.py",
        "Performance Tracker Test": "test_performance_tracker.py",
        "Position Sizing Test": "test_position_sizing.py",
    }

    existing_tests = 0
    for name, filepath in test_scripts.items():
        exists = check_file_exists(filepath)
        status = "✅" if exists else "❌"
        logger.info(f"{status} {name:30} {filepath}")
        if exists:
            existing_tests += 1

    logger.info(f"\n✅ Test Scripts: {existing_tests}/{len(test_scripts)}")

    # Test 4: Documentation Files
    logger.info("\n📚 DOCUMENTATION FILES")
    logger.info("-"*80)

    docs = {
        "Adaptive Volume": "ADAPTIVE_VOLUME_IMPLEMENTATION.md",
        "Multi-Timeframe": "MULTI_TIMEFRAME_IMPLEMENTATION.md",
        "Performance Tracker": "PERFORMANCE_TRACKER_IMPLEMENTATION.md",
        "Phase 2 Summary": "PHASE_2_COMPLETION_SUMMARY.md",
        "Position Sizing": "POSITION_SIZING_GUIDE.md",
        "Volume Profile": "VP_INTEGRATION_GUIDE.md",
    }

    existing_docs = 0
    for name, filepath in docs.items():
        exists = check_file_exists(filepath)
        status = "✅" if exists else "❌"
        logger.info(f"{status} {name:25} {filepath}")
        if exists:
            existing_docs += 1

    logger.info(f"\n✅ Documentation: {existing_docs}/{len(docs)}")

    # Summary
    logger.info("\n"+"="*80)
    logger.info("VERIFICATION SUMMARY")
    logger.info("="*80)
    logger.info(f"✅ Services Healthy:     {healthy_services:2}/{total_services}")
    logger.info(f"✅ Core Modules:         {existing_files:2}/{len(core_files)}")
    logger.info(f"✅ Test Scripts:         {existing_tests:2}/{len(test_scripts)}")
    logger.info(f"✅ Documentation:        {existing_docs:2}/{len(docs)}")

    total_checks = total_services + len(core_files) + len(test_scripts) + len(docs)
    total_passed = healthy_services + existing_files + existing_tests + existing_docs
    pass_rate = (total_passed / total_checks) * 100

    logger.info(f"\n📊 Overall Status: {total_passed}/{total_checks} ({pass_rate:.1f}%)")

    if pass_rate >= 90:
        logger.info("🎉 System Status: EXCELLENT")
    elif pass_rate >= 75:
        logger.info("✅ System Status: GOOD")
    elif pass_rate >= 50:
        logger.info("⚠️  System Status: NEEDS ATTENTION")
    else:
        logger.info("❌ System Status: CRITICAL")

    logger.info("="*80)

    return 0 if pass_rate >= 75 else 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
