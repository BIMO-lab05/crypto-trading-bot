#!/usr/bin/env python3
"""
Statistical Arbitrage Paper Trading Verification Script
Purpose: Verify paper trading environment is correctly configured
Created: 2025-12-11
"""

import os
import sys
import asyncio
import httpx
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def log_step(message: str):
    print(f"{Colors.BLUE}[CHECK]{Colors.NC} {message}")


def log_success(message: str):
    print(f"{Colors.GREEN}[OK]{Colors.NC} {message}")


def log_warning(message: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")


def log_error(message: str):
    print(f"{Colors.RED}[FAIL]{Colors.NC} {message}")


def verify_env_config() -> dict:
    """Verify environment configuration"""
    print("\n" + "=" * 60)
    print("1. ENVIRONMENT CONFIGURATION VERIFICATION")
    print("=" * 60)

    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        log_error(f".env file not found at {env_path}")
        return {"status": "error", "issues": [".env file not found"]}

    load_dotenv(env_path)

    checks = {
        "trading_mode": {
            "var": "TRADING_MODE",
            "expected": "PAPER",
            "critical": True
        },
        "stat_arb_enabled": {
            "var": "STAT_ARB_ENABLED",
            "expected": "true",
            "critical": True
        },
        "paper_balance": {
            "var": "PAPER_INITIAL_BALANCE",
            "expected": "10000.0",
            "critical": False
        },
        "max_position": {
            "var": "MAX_POSITION_SIZE_PCT",
            "expected": "5.0",
            "critical": False
        },
        "grid_disabled": {
            "var": "GRID_TRADING_ENABLED",
            "expected": "false",
            "critical": False
        },
        "trend_disabled": {
            "var": "TREND_FOLLOWING_ENABLED",
            "expected": "false",
            "critical": False
        }
    }

    issues = []
    for check_name, config in checks.items():
        value = os.getenv(config["var"])

        if value is None:
            if config["critical"]:
                log_error(f"{config['var']}: NOT SET (Critical)")
                issues.append(f"{config['var']} not set")
            else:
                log_warning(f"{config['var']}: NOT SET (Using default)")
        elif value == config["expected"]:
            log_success(f"{config['var']}: {value}")
        else:
            if config["critical"]:
                log_error(f"{config['var']}: {value} (Expected: {config['expected']})")
                issues.append(f"{config['var']} = {value}, expected {config['expected']}")
            else:
                log_warning(f"{config['var']}: {value} (Expected: {config['expected']})")

    return {
        "status": "pass" if not issues else "fail",
        "issues": issues
    }


async def verify_services() -> dict:
    """Verify required services are accessible"""
    print("\n" + "=" * 60)
    print("2. SERVICE CONNECTIVITY VERIFICATION")
    print("=" * 60)

    services = {
        "Bybit Connector": os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8002"),
        "Technical Analysis": os.getenv("TECHNICAL_ANALYSIS_URL", "http://localhost:8004"),
        "Portfolio Manager": os.getenv("PORTFOLIO_MANAGER_URL", "http://localhost:8003"),
    }

    issues = []
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in services.items():
            try:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    log_success(f"{name}: OK ({url})")
                else:
                    log_warning(f"{name}: HTTP {response.status_code}")
                    issues.append(f"{name} returned {response.status_code}")
            except httpx.ConnectError:
                log_warning(f"{name}: NOT RESPONDING ({url})")
                issues.append(f"{name} not responding at {url}")
            except Exception as e:
                log_error(f"{name}: ERROR - {str(e)}")
                issues.append(f"{name} error: {str(e)}")

    return {
        "status": "pass" if not issues else "warning",
        "issues": issues
    }


def verify_paper_trading_engine() -> dict:
    """Verify paper trading engine configuration"""
    print("\n" + "=" * 60)
    print("3. PAPER TRADING ENGINE VERIFICATION")
    print("=" * 60)

    issues = []

    try:
        from app.config import get_settings
        settings = get_settings()

        # Check trading mode
        if settings.trading_mode == "PAPER":
            log_success(f"Trading Mode: {settings.trading_mode}")
        else:
            log_error(f"Trading Mode: {settings.trading_mode} (SHOULD BE PAPER!)")
            issues.append("Trading mode is not PAPER")

        # Check paper balance
        log_success(f"Paper Initial Balance: ${settings.paper_initial_balance:,.2f}")

        # Check risk settings
        log_success(f"Max Position Size: {settings.max_position_size_pct}%")
        log_success(f"Max Daily Loss: {settings.max_daily_loss_pct}%")
        log_success(f"Max Total Exposure: {settings.max_total_exposure_pct}%")

        # Check commission
        log_success(f"Paper Commission: {settings.paper_commission_pct}%")

    except ImportError as e:
        log_error(f"Could not import trading engine config: {e}")
        issues.append(f"Import error: {str(e)}")
    except Exception as e:
        log_error(f"Error checking configuration: {e}")
        issues.append(f"Config error: {str(e)}")

    return {
        "status": "pass" if not issues else "fail",
        "issues": issues
    }


def verify_stat_arb_manager() -> dict:
    """Verify Statistical Arbitrage Manager is available"""
    print("\n" + "=" * 60)
    print("4. STATISTICAL ARBITRAGE MANAGER VERIFICATION")
    print("=" * 60)

    issues = []

    try:
        from app.managers.statistical_arbitrage_manager import (
            StatisticalArbitrageManager,
            StrategyAllocation
        )

        # Test manager initialization
        test_allocation = StrategyAllocation(
            pairs_trading=0.4,
            funding_rate=0.4,
            triangular=0.2
        )

        if test_allocation.validate():
            log_success("Strategy allocation validation: PASS")
        else:
            log_error("Strategy allocation validation: FAIL")
            issues.append("Allocation validation failed")

        # Test manager creation
        manager = StatisticalArbitrageManager(
            total_capital=10000.0,
            allocation=test_allocation
        )
        log_success(f"Manager initialized: Capital=${manager.total_capital:,.2f}")
        log_success(f"Pairs Trading allocation: {test_allocation.pairs_trading * 100}%")
        log_success(f"Funding Rate allocation: {test_allocation.funding_rate * 100}%")
        log_success(f"Triangular allocation: {test_allocation.triangular * 100}%")

    except ImportError as e:
        log_error(f"Could not import Stat Arb Manager: {e}")
        issues.append(f"Import error: {str(e)}")
    except Exception as e:
        log_error(f"Error creating manager: {e}")
        issues.append(f"Manager error: {str(e)}")

    return {
        "status": "pass" if not issues else "fail",
        "issues": issues
    }


def verify_trading_symbols() -> dict:
    """Verify trading symbols configuration"""
    print("\n" + "=" * 60)
    print("5. TRADING SYMBOLS VERIFICATION")
    print("=" * 60)

    issues = []

    symbols_env = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")
    symbols = [s.strip() for s in symbols_env.split(",")]

    log_success(f"Configured symbols: {symbols}")

    # Check allocations
    total_alloc = 0.0
    for symbol in symbols:
        alloc_var = f"SYMBOL_ALLOCATION_{symbol}"
        alloc = os.getenv(alloc_var)
        if alloc:
            alloc_float = float(alloc)
            total_alloc += alloc_float
            log_success(f"  {symbol}: {alloc_float * 100}%")
        else:
            log_warning(f"  {symbol}: No specific allocation")

    if abs(total_alloc - 1.0) < 0.01 and total_alloc > 0:
        log_success(f"Total allocation: {total_alloc * 100}% (Valid)")
    elif total_alloc == 0:
        log_warning("No symbol allocations defined (will use default)")
    else:
        log_warning(f"Total allocation: {total_alloc * 100}% (Should be 100%)")
        issues.append(f"Allocation sums to {total_alloc * 100}%")

    return {
        "status": "pass" if not issues else "warning",
        "issues": issues
    }


def generate_report(results: dict) -> None:
    """Generate final verification report"""
    print("\n" + "=" * 60)
    print("VERIFICATION REPORT")
    print("=" * 60)

    all_pass = True
    warnings = 0

    for section, result in results.items():
        status = result["status"]
        if status == "pass":
            print(f"  {Colors.GREEN}[PASS]{Colors.NC} {section}")
        elif status == "warning":
            print(f"  {Colors.YELLOW}[WARN]{Colors.NC} {section}")
            warnings += 1
        else:
            print(f"  {Colors.RED}[FAIL]{Colors.NC} {section}")
            all_pass = False

        for issue in result.get("issues", []):
            print(f"         - {issue}")

    print("")

    if all_pass and warnings == 0:
        print(f"{Colors.GREEN}STATUS: ALL CHECKS PASSED{Colors.NC}")
        print("Paper trading environment is ready for Statistical Arbitrage deployment.")
    elif all_pass:
        print(f"{Colors.YELLOW}STATUS: PASSED WITH WARNINGS{Colors.NC}")
        print("Paper trading can proceed, but review warnings above.")
    else:
        print(f"{Colors.RED}STATUS: VERIFICATION FAILED{Colors.NC}")
        print("Please fix critical issues before proceeding.")

    print("=" * 60)


async def main():
    """Main verification routine"""
    print("=" * 60)
    print("STATISTICAL ARBITRAGE PAPER TRADING VERIFICATION")
    print("=" * 60)
    print(f"Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {}

    # Run verifications
    results["Environment Config"] = verify_env_config()
    results["Service Connectivity"] = await verify_services()
    results["Paper Trading Engine"] = verify_paper_trading_engine()
    results["Stat Arb Manager"] = verify_stat_arb_manager()
    results["Trading Symbols"] = verify_trading_symbols()

    # Generate report
    generate_report(results)


if __name__ == "__main__":
    asyncio.run(main())
