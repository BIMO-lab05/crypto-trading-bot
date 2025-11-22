#!/usr/bin/env python3
"""
Quick Coverage Analysis Script
Purpose: Fast coverage analysis for all services
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# Define services
SERVICES = [
    "api-gateway",
    "bybit-connector",
    "market-data-service",
    "portfolio-manager",
    "technical-analysis",
    "trading-engine",
    "notification-service",
    "ml-prediction-service",
    "sentiment-analysis-service",
    "risk-metrics-service"
]

def count_test_files(service_path):
    """Count test files in a service"""
    tests_dir = service_path / "tests"
    if not tests_dir.exists():
        return 0
    return len(list(tests_dir.glob("**/*.py"))) - len(list(tests_dir.glob("**/__*.py")))

def run_coverage(service_path):
    """Run coverage for a service"""
    tests_dir = service_path / "tests"
    if not tests_dir.exists():
        return None, 0, 0

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--cov=app",
             "--cov-report=term", "-q", "--tb=no"],
            cwd=service_path,
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # Extract coverage
        coverage = "N/A"
        for line in output.split('\n'):
            if "TOTAL" in line:
                parts = line.split()
                if len(parts) > 0:
                    coverage = parts[-1]
                    break

        # Extract test results
        passed = failed = 0
        for line in output.split('\n'):
            if " passed" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            passed = int(parts[i-1])
                        except:
                            pass
            if " failed" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "failed" and i > 0:
                        try:
                            failed = int(parts[i-1])
                        except:
                            pass

        return coverage, passed, failed

    except subprocess.TimeoutExpired:
        return "TIMEOUT", 0, 0
    except Exception as e:
        return f"ERROR: {str(e)}", 0, 0

def main():
    print("=" * 80)
    print("QUICK COVERAGE ANALYSIS")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    results = []
    base_path = Path("/mnt/d/Bimo_max/crypto-trading-bot/services")

    for service in SERVICES:
        service_path = base_path / service

        print(f"Analyzing: {service:<30}", end=" ", flush=True)

        if not service_path.exists():
            print("❌ NOT FOUND")
            results.append((service, 0, "N/A", 0, 0, "NOT_FOUND"))
            continue

        test_count = count_test_files(service_path)

        if test_count == 0:
            print(f"⚠️  NO TESTS (0 files)")
            results.append((service, 0, "0%", 0, 0, "NO_TESTS"))
            continue

        print(f"🔍 {test_count} test files...", end=" ", flush=True)

        coverage, passed, failed = run_coverage(service_path)

        # Determine status
        if coverage == "N/A" or coverage == "ERROR" or coverage == "TIMEOUT":
            status = "ERROR"
            symbol = "❌"
        else:
            try:
                cov_num = float(coverage.replace('%', ''))
                if cov_num >= 80:
                    status = "✅ PASS"
                    symbol = "✅"
                elif cov_num >= 60:
                    status = "⚠️  MEDIUM"
                    symbol = "⚠️"
                else:
                    status = "❌ LOW"
                    symbol = "❌"
            except:
                status = "ERROR"
                symbol = "❌"

        print(f"{symbol} {coverage} ({passed}✓ {failed}✗)")

        results.append((service, test_count, coverage, passed, failed, status))

    # Print summary table
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"{'Service':<30} {'Tests':<8} {'Coverage':<12} {'Status':<15} {'P/F':<8}")
    print("-" * 80)

    for service, test_count, coverage, passed, failed, status in results:
        pf = f"{passed}/{failed}"
        print(f"{service:<30} {test_count:<8} {coverage:<12} {status:<15} {pf:<8}")

    print("-" * 80)

    # Statistics
    total_services = len(SERVICES)
    services_with_tests = sum(1 for r in results if r[1] > 0)
    services_above_80 = sum(1 for r in results if r[5] == "✅ PASS")
    services_need_tests = total_services - services_with_tests

    print()
    print(f"Total Services: {total_services}")
    print(f"Services with Tests: {services_with_tests}")
    print(f"Services with 80%+ Coverage: {services_above_80}")
    print(f"Services Needing Tests: {services_need_tests}")
    print()

    # Priority actions
    print("PRIORITY ACTIONS:")
    print()

    # Services without tests
    no_tests = [r[0] for r in results if r[5] == "NO_TESTS"]
    if no_tests:
        print("1. CREATE TESTS FOR:")
        for service in no_tests:
            print(f"   - {service}")
        print()

    # Services with low coverage
    low_coverage = [r for r in results if r[5] in ["❌ LOW", "⚠️  MEDIUM"]]
    if low_coverage:
        print("2. IMPROVE COVERAGE FOR:")
        for service, _, coverage, _, _, status in low_coverage:
            print(f"   - {service:<30} {coverage}")
        print()

    # Services with errors
    errors = [r for r in results if r[5] == "ERROR"]
    if errors:
        print("3. FIX ERRORS IN:")
        for service, _, _, _, _, _ in errors:
            print(f"   - {service}")
        print()

    print("=" * 80)

if __name__ == "__main__":
    main()
