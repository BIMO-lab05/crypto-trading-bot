"""
costs.py fee layer.

Two properties this pins, both of which the repo currently violates somewhere:
  * maker is a CHARGE, not a rebate. config.py:176 says taker 0.055% /
    maker 0.020%; backtesting/backtest_engine.py:140 says maker = -0.0001, a
    CREDIT. Bybit's standard USDT-perp schedule charges both; rebates exist
    only at market-maker tiers a $100 account cannot reach. The negative value
    makes every backtested stop-out credit the account.
  * costs.py imports STDLIB ONLY. Importing app.config from repo-root cwd
    raises SettingsError, and instruments_cache fails OPEN (returns None) on a
    network miss, which would silently delete quantization from every test
    while leaving the assertions green.
"""

from decimal import Decimal

import pytest

from app.costs import FeeSchedule, Liquidity, fee, round_trip_cost_bps, slippage_bps


SLIPPAGE = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
FALLBACK = Decimal("10")


def test_costs_module_imports_stdlib_only():
    """A single non-stdlib import makes this module unusable host-side.

    Reads the file by PATH rather than importing it. `app` is a regular package
    name claimed by technical-analysis in some processes, so resolving
    `app.costs` through the import system is exactly the fragility this test
    exists to protect against.
    """
    import ast
    import pathlib
    import sys

    here = pathlib.Path(__file__).resolve()
    costs_path = here.parents[1] / "app" / "costs.py"
    assert costs_path.is_file(), f"{costs_path} missing — coverage would be silent"

    tree = ast.parse(costs_path.read_text())
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])

    assert roots <= set(sys.stdlib_module_names), (
        f"costs.py must import stdlib only; found {sorted(roots - set(sys.stdlib_module_names))}"
    )


def test_bybit_schedule_charges_both_sides():
    s = FeeSchedule.bybit_linear_perp()
    assert s.taker == Decimal("0.00055")
    assert s.maker == Decimal("0.00020")
    assert s.maker > 0, "maker is a CHARGE on the standard schedule, not a rebate"


def test_fee_is_notional_times_rate():
    s = FeeSchedule.bybit_linear_perp()
    assert fee(Decimal("10"), Liquidity.TAKER, s) == Decimal("0.0055")
    assert fee(Decimal("10"), Liquidity.MAKER, s) == Decimal("0.0020")


def test_fee_rejects_negative_notional():
    s = FeeSchedule.bybit_linear_perp()
    with pytest.raises(ValueError):
        fee(Decimal("-1"), Liquidity.TAKER, s)


def test_slippage_is_per_symbol_with_a_wider_fallback():
    assert slippage_bps("BTCUSDT", SLIPPAGE, FALLBACK) == Decimal("5")
    assert slippage_bps("ADAUSDT", SLIPPAGE, FALLBACK) == Decimal("10")
    # An unvalidated symbol gets the wider alt bucket, never the majors bucket:
    # being wrong conservatively understates P&L, which is the safe error.
    assert slippage_bps("XRPUSDT", SLIPPAGE, FALLBACK) == Decimal("10")


def test_taker_round_trip_matches_the_hurdle_table():
    """21 bps majors / 31 bps BNB-ADA — the figures the design spec quotes."""
    s = FeeSchedule.bybit_linear_perp()
    majors = round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=Liquidity.TAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    alts = round_trip_cost_bps(
        "ADAUSDT",
        entry_liquidity=Liquidity.TAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert majors == Decimal("21")  # 2*5.5 fee + 2*5 slippage
    assert alts == Decimal("31")  # 2*5.5 fee + 2*10 slippage


def test_maker_round_trip_is_fees_only():
    """4 bps. A PostOnly order fills at the price it posted, so no adverse
    slippage — but adverse selection and non-fill are real costs this number
    does NOT capture, which is why the maker hurdle carries a caveat."""
    s = FeeSchedule.bybit_linear_perp()
    got = round_trip_cost_bps(
        "BTCUSDT",
        entry_liquidity=Liquidity.MAKER,
        exit_liquidity=Liquidity.MAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert got == Decimal("4")


def test_mixed_liquidity_round_trip():
    """Maker entry, taker exit — the realistic shape for a PostOnly entry with
    a market stop, since a triggered Bybit conditional stop is a taker order."""
    s = FeeSchedule.bybit_linear_perp()
    got = round_trip_cost_bps(
        "SOLUSDT",
        entry_liquidity=Liquidity.MAKER,
        exit_liquidity=Liquidity.TAKER,
        schedule=s,
        slippage_table=SLIPPAGE,
        slippage_fallback=FALLBACK,
    )
    assert got == Decimal("12.5")  # 2 + 5.5 fee + 0 + 5 slippage
