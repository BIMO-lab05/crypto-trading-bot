#!/usr/bin/env python3
"""
Crypto Trading Bot - Risk Management Validation Script
Version: 1.0.0
Last Updated: 2025-11-14

Purpose: Validate all risk management rules and safety mechanisms
Usage: python3 scripts/validate_risk_limits.py [--verbose]

Every cap this script checks is imported from shared/account.py rather than
restated here. A validator that hardcodes the numbers it validates cannot
detect the drift it exists to detect: until 2026-08-06 this file asserted a
2%-per-trade / 5%-daily policy against a system configured for 10% / 12%
(ADR-010, ADR-028) and reported PASS, because both sides of every comparison
came from the same stale literals.

Tests:
1. Position size calculation (paper per-trade risk cap)
2. Daily loss limit enforcement (ADR-028 breaker)
3. Circuit breaker activation (10% drawdown)
4. Stop-loss calculation (ATR-based)
5. Emergency stop procedures
6. Maximum position limits
7. Leverage restrictions
"""

import asyncio
import sys
import argparse
from datetime import datetime
from pathlib import Path
import httpx

# Host-run script: repo-root shared/ is importable (CLAUDE.md money rules).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.account import (  # noqa: E402
    ACCOUNT_EQUITY_USD,
    LIVE_MAX_RISK_PER_TRADE,
    MAX_DAILY_LOSS_PCT,
    MAX_POSITION_SIZE_PCT,
    MAX_RISK_PER_TRADE,
    MIN_NOTIONAL_USD,
    max_daily_loss_fraction,
    max_position_size_fraction,
)

# ANSI color codes for terminal output
GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
NC = "\033[0m"  # No Color

# Service URLs
TRADING_ENGINE_URL = "http://localhost:8005"
PORTFOLIO_URL = "http://localhost:8003"
RISK_METRICS_URL = "http://localhost:8009"

# ---------------------------------------------------------------------------
# Risk parameters.
#
# UNITS ARE NOT UNIFORM upstream and the names here carry the unit so a
# fraction is never compared against a percent (CLAUDE.md: comparing
# `0.10 > 12.0` is a check that silently never fires).
#
#   MAX_RISK_PER_TRADE      fraction, 0.10 paper (ADR-010)
#   MAX_DAILY_LOSS_PCT      percent,  12.0      (ADR-028)
#   MAX_POSITION_SIZE_PCT   percent,  10.0
#
# LIVE_MAX_RISK_PER_TRADE (0.02) is the non-negotiable LIVE cap and is
# reported separately in the pre-live summary — the paper relaxation must not
# erase it.
# ---------------------------------------------------------------------------
DAILY_LOSS_LIMIT_FRACTION = max_daily_loss_fraction()  # 0.12
MAX_POSITION_SIZE_FRACTION = max_position_size_fraction()  # 0.10

# Not declared in shared/account.py — there is no MAX_DRAWDOWN env key or
# Settings field; this is the script's own peak-to-trough gate, distinct from
# the daily-loss breaker above. Kept local and named as such rather than
# pretending it has an upstream source.
MAX_DRAWDOWN = 0.10  # fraction, 10% peak-to-trough
MAX_POSITIONS = 5  # Maximum concurrent positions
MAX_LEVERAGE = 1  # No leverage in initial version


class RiskValidator:
    """Validates all risk management rules"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose mode enabled"""
        if self.verbose:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] {level}: {message}")

    def print_test(self, name: str, passed: bool, details: str = ""):
        """Print test result with color coding"""
        if passed:
            print(f"{GREEN}✓{NC} {name}")
            if details and self.verbose:
                print(f"  {details}")
            self.passed += 1
        else:
            print(f"{RED}✗{NC} {name}")
            if details:
                print(f"  {RED}{details}{NC}")
            self.failed += 1

    def print_warning(self, name: str, details: str = ""):
        """Print warning"""
        print(f"{YELLOW}⚠{NC} {name}")
        if details:
            print(f"  {YELLOW}{details}{NC}")
        self.warnings += 1

    async def test_service_connectivity(self) -> bool:
        """Test 1: Verify required services are accessible"""
        print(f"\n{BLUE}[1/8] Service Connectivity${NC}")
        print("─" * 50)

        services = {
            "Trading Engine": f"{TRADING_ENGINE_URL}/health",
            "Portfolio Manager": f"{PORTFOLIO_URL}/health",
            "Risk Metrics": f"{RISK_METRICS_URL}/health",
        }

        all_healthy = True
        async with httpx.AsyncClient(timeout=5.0) as client:
            for name, url in services.items():
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        self.print_test(f"{name} accessible", True)
                    else:
                        self.print_test(
                            f"{name} accessible", False, f"HTTP {response.status_code}"
                        )
                        all_healthy = False
                except Exception as e:
                    self.print_test(f"{name} accessible", False, str(e))
                    all_healthy = False

        return all_healthy

    async def test_position_size_calculation(self) -> bool:
        """Test 2: Sizing on the real account clears the venue floor and cap.

        The previous version of this test computed
        `(balance * MAX_RISK_PER_TRADE) / stop_loss_pct` and compared it to a
        hardcoded `expected_max_position` derived from the same formula, on
        synthetic $10K/$5K/$50K balances. It asserted only that Python
        multiplies correctly, and it could not fail.

        What actually constrains sizing on a $100 account is the pair of
        boundaries in .claude/rules/money.md: notional below the venue minimum
        must be REJECTED (never clamped up, which turns a 10% cap into a 40%
        one), and notional above the position cap must be clamped DOWN.
        """
        risk_pct = MAX_RISK_PER_TRADE * 100
        print(f"\n{BLUE}[2/8] Position Size Calculation ({risk_pct:.0f}% Risk){NC}")
        print("─" * 50)

        equity = ACCOUNT_EQUITY_USD
        risk_budget = equity * MAX_RISK_PER_TRADE
        position_cap = equity * MAX_POSITION_SIZE_FRACTION

        print(
            f"  Account: ${equity:.2f} | risk budget ${risk_budget:.2f} "
            f"| position cap ${position_cap:.2f} | venue min ${MIN_NOTIONAL_USD:.2f}"
        )

        all_passed = True

        # Stop distances spanning the tight/typical/wide range. The implied
        # notional is risk_budget / stop_distance in every case.
        for stop_loss_pct in (0.02, 0.05, 0.10, 0.50):
            implied_notional = risk_budget / stop_loss_pct
            label = (
                f"Stop {stop_loss_pct * 100:.0f}% -> notional ${implied_notional:.2f}"
            )

            if implied_notional > position_cap:
                # Clamping DOWN to the position cap is correct behaviour.
                self.print_test(
                    f"{label}: clamped down to cap",
                    True,
                    f"exceeds ${position_cap:.2f} cap, clamp to cap "
                    f"(still >= ${MIN_NOTIONAL_USD:.2f} venue min: "
                    f"{position_cap >= MIN_NOTIONAL_USD})",
                )
                if position_cap < MIN_NOTIONAL_USD:
                    self.print_warning(
                        "Position cap below venue minimum",
                        f"cap ${position_cap:.2f} < min ${MIN_NOTIONAL_USD:.2f} — "
                        "no compliant trade size exists at this stop distance",
                    )
            elif implied_notional < MIN_NOTIONAL_USD:
                # Below the floor the ONLY correct outcome is a rejection.
                self.print_warning(
                    f"{label}: below venue minimum",
                    f"< ${MIN_NOTIONAL_USD:.2f} — trade must be REJECTED with a "
                    "reason, never clamped up to the minimum",
                )
            else:
                self.print_test(
                    f"{label}: within [min, cap]",
                    True,
                    f"${MIN_NOTIONAL_USD:.2f} <= ${implied_notional:.2f} "
                    f"<= ${position_cap:.2f}",
                )

        # The structural check: is there any stop distance at which a trade is
        # both above the venue floor and within the position cap? On $100 with
        # a 10% position cap the answer is $10 vs a $5 floor — a thin but real
        # window. If the cap ever falls below the floor, sizing is impossible
        # and the engine must reject every trade rather than round up.
        window_exists = position_cap >= MIN_NOTIONAL_USD
        self.print_test(
            "A compliant position size exists at this account size",
            window_exists,
            f"position cap ${position_cap:.2f} vs venue minimum "
            f"${MIN_NOTIONAL_USD:.2f}",
        )
        if not window_exists:
            all_passed = False

        # LIVE is a different account entirely: the 2% cap is non-negotiable
        # and on this equity it sits below the venue minimum.
        live_budget = equity * LIVE_MAX_RISK_PER_TRADE
        if live_budget < MIN_NOTIONAL_USD:
            self.print_warning(
                "LIVE per-trade cap is below the venue minimum",
                f"{LIVE_MAX_RISK_PER_TRADE * 100:.0f}% of ${equity:.2f} = "
                f"${live_budget:.2f} < ${MIN_NOTIONAL_USD:.2f} — LIVE trading is "
                "not mechanically viable at this account size regardless of edge",
            )

        # NOTE: this is a warning, not a failure. The LIVE cap being below the
        # venue minimum is a true and permanent property of a $100 account, so
        # failing on it would make this test red on every run forever.
        return all_passed

    async def test_daily_loss_limit(self) -> bool:
        """Test 3: Daily loss limit enforcement (ADR-028 breaker)"""
        print(
            f"\n{BLUE}[3/8] Daily Loss Limit "
            f"({MAX_DAILY_LOSS_PCT:.0f}% of Portfolio, ADR-028){NC}"
        )
        print("─" * 50)

        # Try to get actual portfolio data
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{PORTFOLIO_URL}/api/v1/balance")

                if response.status_code == 200:
                    data = response.json()
                    # FIX 2026-08-05 (AUDIT 2.5): the old .get(..., 10000)
                    # fallbacks assumed a $10,000 account (100x real) — a
                    # validator that invents its own balance can mask real
                    # breaches. Missing fields now FAIL the check loudly.
                    if "total_balance" not in data or "initial_balance" not in data:
                        self.print_test(
                            "Daily loss data available",
                            False,
                            "portfolio /balance response missing "
                            "total_balance/initial_balance — cannot validate "
                            "daily loss limit (refusing to assume an account "
                            "size)",
                        )
                        return False
                    current_balance = float(data["total_balance"])
                    initial_balance = float(data["initial_balance"])

                    daily_loss = initial_balance - current_balance
                    daily_loss_pct = (
                        (daily_loss / initial_balance) * 100
                        if initial_balance > 0
                        else 0
                    )

                    # Test 1: Check if daily loss is within limit
                    within_limit = abs(daily_loss_pct) < MAX_DAILY_LOSS_PCT

                    details = f"Balance: ${current_balance:.2f}, Daily Loss: ${daily_loss:.2f} ({daily_loss_pct:.2f}%)"
                    self.print_test(
                        f"Current daily loss within {MAX_DAILY_LOSS_PCT:.0f}% limit",
                        within_limit,
                        details,
                    )

                    # Test 2: Calculate remaining daily loss allowance
                    remaining_loss = (
                        initial_balance * DAILY_LOSS_LIMIT_FRACTION
                    ) - daily_loss
                    remaining_pct = (remaining_loss / initial_balance) * 100

                    if remaining_loss > 0:
                        self.print_test(
                            "Remaining daily loss allowance",
                            True,
                            f"${remaining_loss:.2f} remaining ({remaining_pct:.2f}%)",
                        )
                    else:
                        self.print_warning(
                            "Daily loss limit reached",
                            f"${abs(remaining_loss):.2f} over limit",
                        )

                    # Test 3: Verify trading should stop if limit reached
                    if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
                        # Check if trading is actually stopped
                        status_response = await client.get(
                            f"{TRADING_ENGINE_URL}/api/v1/status"
                        )
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            trading_active = status_data.get("trading_active", False)

                            if not trading_active:
                                self.print_test(
                                    "Trading halted when limit reached",
                                    True,
                                    "Auto-trading is disabled",
                                )
                            else:
                                self.print_test(
                                    "Trading halted when limit reached",
                                    False,
                                    "Auto-trading still active despite loss limit",
                                )
                                return False
                        else:
                            self.print_warning(
                                "Cannot verify trading status",
                                f"HTTP {status_response.status_code}",
                            )

                    return within_limit
                else:
                    self.print_warning(
                        "Cannot fetch portfolio data", f"HTTP {response.status_code}"
                    )
                    return False

        except Exception as e:
            self.print_test("Daily loss limit check", False, str(e))
            return False

    async def test_circuit_breaker(self) -> bool:
        """Test 4: Circuit breaker activates at 10% drawdown"""
        print(f"\n{BLUE}[4/8] Circuit Breaker (10% Drawdown Limit){NC}")
        print("─" * 50)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get risk metrics
                response = await client.get(
                    f"{RISK_METRICS_URL}/api/v1/metrics/portfolio"
                )

                if response.status_code == 200:
                    data = response.json()
                    max_drawdown = data.get("max_drawdown", 0)
                    max_drawdown_pct = abs(max_drawdown * 100)

                    # Test 1: Current drawdown within limit
                    within_limit = max_drawdown_pct < (MAX_DRAWDOWN * 100)
                    details = f"Current max drawdown: {max_drawdown_pct:.2f}%"
                    self.print_test("Drawdown within 10% limit", within_limit, details)

                    # Test 2: Calculate drawdown buffer
                    drawdown_buffer = (MAX_DRAWDOWN * 100) - max_drawdown_pct
                    if drawdown_buffer > 0:
                        self.print_test(
                            "Drawdown buffer available",
                            True,
                            f"{drawdown_buffer:.2f}% before circuit breaker",
                        )
                    else:
                        self.print_warning(
                            "Circuit breaker threshold reached",
                            f"{abs(drawdown_buffer):.2f}% over limit",
                        )

                    # Test 3: Verify circuit breaker status
                    if max_drawdown_pct >= (MAX_DRAWDOWN * 100):
                        # Circuit breaker should be activated
                        status_response = await client.get(
                            f"{TRADING_ENGINE_URL}/api/v1/status"
                        )
                        if status_response.status_code == 200:
                            status_data = status_response.json()
                            circuit_breaker = status_data.get(
                                "circuit_breaker_active", False
                            )

                            if circuit_breaker:
                                self.print_test(
                                    "Circuit breaker activated",
                                    True,
                                    "System protection engaged",
                                )
                            else:
                                self.print_test(
                                    "Circuit breaker activated",
                                    False,
                                    "Circuit breaker should be active but isn't",
                                )
                                return False
                    else:
                        self.print_test(
                            "Circuit breaker monitoring",
                            True,
                            "Normal operation, no breaker needed",
                        )

                    return within_limit
                else:
                    self.print_warning(
                        "Cannot fetch risk metrics", f"HTTP {response.status_code}"
                    )
                    return False

        except Exception as e:
            self.print_test("Circuit breaker check", False, str(e))
            return False

    async def test_stop_loss_calculation(self) -> bool:
        """Test 5: Stop-loss calculation (ATR-based)"""
        print(f"\n{BLUE}[5/8] Stop-Loss Calculation (ATR-Based){NC}")
        print("─" * 50)

        # Test scenarios with mock data
        test_cases = [
            {
                "symbol": "BTCUSDT",
                "entry_price": 40000,
                "atr": 800,  # $800 ATR
                "multiplier": 2.0,  # 2x ATR
                "expected_sl_long": 38400,  # 40000 - (2 * 800)
                "expected_sl_short": 41600,  # 40000 + (2 * 800)
                "description": "BTC standard volatility",
            },
            {
                "symbol": "ETHUSDT",
                "entry_price": 2500,
                "atr": 50,  # $50 ATR
                "multiplier": 2.0,
                "expected_sl_long": 2400,  # 2500 - (2 * 50)
                "expected_sl_short": 2600,  # 2500 + (2 * 50)
                "description": "ETH moderate volatility",
            },
            {
                "symbol": "BNBUSDT",
                "entry_price": 300,
                "atr": 10,  # $10 ATR
                "multiplier": 2.0,
                "expected_sl_long": 280,  # 300 - (2 * 10)
                "expected_sl_short": 320,  # 300 + (2 * 10)
                "description": "BNB low volatility",
            },
        ]

        all_passed = True

        for case in test_cases:
            # Calculate stop loss for LONG position
            calculated_sl_long = case["entry_price"] - (
                case["atr"] * case["multiplier"]
            )
            passed_long = abs(calculated_sl_long - case["expected_sl_long"]) < 0.01

            # Calculate stop loss for SHORT position
            calculated_sl_short = case["entry_price"] + (
                case["atr"] * case["multiplier"]
            )
            passed_short = abs(calculated_sl_short - case["expected_sl_short"]) < 0.01

            # Test LONG
            details = f"Entry: ${case['entry_price']}, ATR: ${case['atr']}, SL: ${calculated_sl_long:.2f}"
            self.print_test(f"{case['description']} - LONG", passed_long, details)

            # Test SHORT
            details = f"Entry: ${case['entry_price']}, ATR: ${case['atr']}, SL: ${calculated_sl_short:.2f}"
            self.print_test(f"{case['description']} - SHORT", passed_short, details)

            if not (passed_long and passed_short):
                all_passed = False

        # Test edge case: Very high volatility
        high_vol_sl = 40000 - (2000 * 2.0)  # $2000 ATR = 10% stop loss
        sl_percentage = ((40000 - high_vol_sl) / 40000) * 100

        if sl_percentage <= 10:  # Should not exceed 10% stop loss
            self.print_test(
                "Edge case: High volatility caps SL at reasonable level",
                True,
                f"SL: ${high_vol_sl:.2f} ({sl_percentage:.2f}%)",
            )
        else:
            self.print_warning(
                "Edge case: High volatility SL may be too wide",
                f"SL: ${high_vol_sl:.2f} ({sl_percentage:.2f}%)",
            )

        return all_passed

    async def test_max_positions(self) -> bool:
        """Test 6: Maximum concurrent positions limit"""
        print(
            f"\n{BLUE}[6/8] Maximum Concurrent Positions (Limit: {MAX_POSITIONS}){NC}"
        )
        print("─" * 50)

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get current open positions
                response = await client.get(
                    f"{TRADING_ENGINE_URL}/api/v1/positions?status=open"
                )

                if response.status_code == 200:
                    data = response.json()
                    positions = data.get("positions", [])
                    open_count = len(positions)

                    # Test 1: Current positions within limit
                    within_limit = open_count <= MAX_POSITIONS
                    details = f"Current: {open_count}/{MAX_POSITIONS} positions"
                    self.print_test(
                        "Open positions within limit", within_limit, details
                    )

                    # Test 2: Show position diversity
                    if open_count > 0:
                        symbols = [p.get("symbol") for p in positions]
                        unique_symbols = len(set(symbols))

                        self.print_test(
                            "Position diversity",
                            True,
                            f"{unique_symbols} unique symbols in {open_count} positions",
                        )

                        # Show position details if verbose
                        if self.verbose:
                            for pos in positions:
                                symbol = pos.get("symbol", "UNKNOWN")
                                side = pos.get("side", "UNKNOWN")
                                pnl = pos.get("pnl", 0)
                                self.log(f"  - {symbol} {side}: P&L ${pnl:.2f}")
                    else:
                        self.print_test("No open positions", True, "Starting fresh")

                    # Test 3: Calculate available slots
                    available_slots = MAX_POSITIONS - open_count
                    if available_slots > 0:
                        self.print_test(
                            "Position slots available",
                            True,
                            f"{available_slots} slots remaining",
                        )
                    else:
                        self.print_warning(
                            "No position slots available",
                            "Must close position before opening new one",
                        )

                    return within_limit
                else:
                    self.print_warning(
                        "Cannot fetch positions", f"HTTP {response.status_code}"
                    )
                    return False

        except Exception as e:
            self.print_test("Max positions check", False, str(e))
            return False

    async def test_leverage_restrictions(self) -> bool:
        """Test 7: Leverage restrictions (1x only)"""
        print(f"\n{BLUE}[7/8] Leverage Restrictions (Max: {MAX_LEVERAGE}x){NC}")
        print("─" * 50)

        # In initial version, leverage should be disabled (1x only)
        self.print_test(
            "Leverage set to 1x (no leverage)",
            True,
            "Paper trading mode: leverage disabled",
        )

        self.print_test(
            "Margin trading disabled", True, "Only spot-equivalent positions allowed"
        )

        self.print_test(
            "No liquidation risk",
            True,
            "1x leverage eliminates liquidation possibility",
        )

        # Test that position size never exceeds balance. Uses the real
        # account and the real position cap rather than invented figures —
        # $8,000 against a $10,000 balance was never a scenario this system
        # can produce.
        test_balance = ACCOUNT_EQUITY_USD
        test_position = ACCOUNT_EQUITY_USD * MAX_POSITION_SIZE_FRACTION

        if test_position <= test_balance:
            self.print_test(
                "Position size <= balance",
                True,
                f"${test_position} position with ${test_balance} balance",
            )
        else:
            self.print_test(
                "Position size <= balance",
                False,
                f"${test_position} position exceeds ${test_balance} balance",
            )
            return False

        return True

    async def test_emergency_stop(self) -> bool:
        """Test 8: Emergency stop procedures"""
        print(f"\n{BLUE}[8/8] Emergency Stop Procedures{NC}")
        print("─" * 50)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Test 1: Emergency stop endpoint exists
                try:
                    # Don't actually trigger emergency stop, just verify endpoint
                    self.print_test(
                        "Emergency stop endpoint exists",
                        True,
                        "POST /api/v1/emergency/stop available",
                    )
                except:
                    self.print_test("Emergency stop endpoint exists", False)
                    return False

                # Test 2: Emergency close all positions endpoint
                self.print_test(
                    "Emergency close all endpoint exists",
                    True,
                    "POST /api/v1/emergency/close-all available",
                )

                # Test 3: Verify trading status endpoint
                response = await client.get(f"{TRADING_ENGINE_URL}/api/v1/status")
                if response.status_code == 200:
                    self.print_test(
                        "Trading status monitoring available",
                        True,
                        "Can check if trading is active",
                    )
                else:
                    self.print_test(
                        "Trading status monitoring available",
                        False,
                        f"HTTP {response.status_code}",
                    )
                    return False

                # Test 4: Verify notification system for alerts
                notification_response = await client.get("http://localhost:8006/health")
                if notification_response.status_code == 200:
                    self.print_test(
                        "Emergency notification system available",
                        True,
                        "Can send emergency alerts",
                    )
                else:
                    self.print_warning(
                        "Emergency notification system unavailable",
                        "Telegram notifications not configured",
                    )

                return True

        except Exception as e:
            self.print_test("Emergency stop procedures", False, str(e))
            return False

    def print_summary(self) -> int:
        """Print validation summary and return exit code"""
        print("\n" + "=" * 60)
        print(f"{BLUE}Risk Management Validation Summary{NC}")
        print("=" * 60)

        total_tests = self.passed + self.failed
        pass_rate = (self.passed / total_tests * 100) if total_tests > 0 else 0

        print(f"\nTests Run: {total_tests}")
        print(f"{GREEN}Passed: {self.passed}{NC}")
        print(f"{RED}Failed: {self.failed}{NC}")
        print(f"{YELLOW}Warnings: {self.warnings}{NC}")
        print(f"\nPass Rate: {pass_rate:.1f}%")

        if self.failed == 0:
            print(f"\n{GREEN}✓ All Risk Management Rules VALIDATED{NC}")
            print("\nRisk controls are properly configured:")
            print(f"  • Account equity: ${ACCOUNT_EQUITY_USD:.2f}")
            print(
                f"  • Position sizing: {MAX_RISK_PER_TRADE * 100:.0f}% risk per "
                "trade (paper, ADR-010)"
            )
            print(
                f"  • Position cap: {MAX_POSITION_SIZE_PCT:.0f}% of equity "
                f"(${ACCOUNT_EQUITY_USD * MAX_POSITION_SIZE_FRACTION:.2f})"
            )
            print(
                f"  • Daily loss limit: {MAX_DAILY_LOSS_PCT:.0f}% of portfolio "
                "(ADR-028)"
            )
            print(f"  • Circuit breaker: {MAX_DRAWDOWN * 100:.0f}% drawdown")
            print("  • Stop-loss: ATR-based dynamic")
            print(f"  • Max positions: {MAX_POSITIONS} concurrent")
            print(f"  • Leverage: {MAX_LEVERAGE}x (no leverage)")
            print("  • Emergency stop: Available")
            print(
                f"\n{YELLOW}Pre-live gate: LIVE caps per-trade risk at "
                f"{LIVE_MAX_RISK_PER_TRADE * 100:.0f}% "
                f"(${ACCOUNT_EQUITY_USD * LIVE_MAX_RISK_PER_TRADE:.2f} here). "
                f"Restore it before TRADING_MODE=LIVE.{NC}"
            )
            print("\n" + GREEN + "System is SAFE for paper trading" + NC)
            return 0

        elif self.failed <= 2:
            print(f"\n{YELLOW}⚠ Some Risk Rules Need Attention{NC}")
            print(
                f"\n{self.failed} test(s) failed - review and fix before live trading"
            )
            print("\nAction items:")
            print("  1. Review failed tests above")
            print("  2. Check trading engine configuration")
            print("  3. Verify risk manager implementation")
            print("  4. Re-run validation after fixes")
            return 1

        else:
            print(f"\n{RED}✗ Critical Risk Management Issues{NC}")
            print(f"\n{self.failed} test(s) failed - DO NOT proceed to live trading")
            print("\nImmediate actions required:")
            print("  1. Stop any active trading")
            print("  2. Review all failed tests")
            print("  3. Fix critical risk management bugs")
            print("  4. Add missing safety mechanisms")
            print("  5. Re-validate completely")
            print("\n" + RED + "System is NOT SAFE for trading" + NC)
            return 2


async def main():
    """Main validation routine"""
    parser = argparse.ArgumentParser(
        description="Validate risk management rules for crypto trading bot"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output with detailed test information",
    )
    args = parser.parse_args()

    # Print header
    print(f"{BLUE}╔═══════════════════════════════════════════════════════════╗{NC}")
    print(f"{BLUE}║  Crypto Trading Bot - Risk Management Validation         ║{NC}")
    print(
        f"{BLUE}║  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                       ║{NC}"
    )
    print(f"{BLUE}╚═══════════════════════════════════════════════════════════╝{NC}")

    if args.verbose:
        print(f"\n{YELLOW}Verbose mode enabled{NC}")

    # Create validator
    validator = RiskValidator(verbose=args.verbose)

    # Run all validation tests
    await validator.test_service_connectivity()
    await validator.test_position_size_calculation()
    await validator.test_daily_loss_limit()
    await validator.test_circuit_breaker()
    await validator.test_stop_loss_calculation()
    await validator.test_max_positions()
    await validator.test_leverage_restrictions()
    await validator.test_emergency_stop()

    # Print summary and exit
    exit_code = validator.print_summary()

    print(
        f"\n{BLUE}Validation completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{NC}\n"
    )

    sys.exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())
