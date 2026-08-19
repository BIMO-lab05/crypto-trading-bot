"""
Host-side access to services/trading-engine/app/costs.py.

`from app.costs import ...` DOES NOT WORK from backtesting/.
services/technical-analysis/app/__init__.py exists, making `app` a regular
(non-namespace) package, and backtesting/prod_indicators.py:37-38 and
run_walk_forward_ensemble.py:62 both claim `app` for technical-analysis.
Reproduced: with the TA path loaded first, `import app.paper_slippage` raises
ModuleNotFoundError.

costs.py is stdlib-only, so it needs no sys.path manipulation at all - just a
spec load under a non-`app` name. Same mechanism as
run_walk_forward_ensemble.py:96-104, minus the path juggling.
"""

from __future__ import annotations

import csv
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COSTS_PATH = _REPO_ROOT / "services" / "trading-engine" / "app" / "costs.py"

_MODULE_NAME = "te_costs"

_cached = None


def load_costs():
    """The costs module, loaded once per process under the name `te_costs`.

    The `sys.modules` registration is load-bearing, not bookkeeping. costs.py
    opens with `from __future__ import annotations`, so its dataclass field
    types are strings, and `dataclasses` resolves them via
    `sys.modules.get(cls.__module__).__dict__`. Exec a module without
    registering it and that lookup returns None, so building FeeSchedule
    raises `AttributeError: 'NoneType' object has no attribute '__dict__'` at
    class-creation time. Register BEFORE exec_module, and unregister if the
    exec fails, so a half-built module is never left behind.
    """
    global _cached
    if _cached is None:
        spec = importlib.util.spec_from_file_location(_MODULE_NAME, _COSTS_PATH)
        assert spec is not None and spec.loader is not None, (
            f"cannot load {_COSTS_PATH}"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[_MODULE_NAME] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[_MODULE_NAME]
            raise
        _cached = module
    return _cached


def load_funding(symbol: str, data_dir="backtesting/data/funding") -> list:
    """Settlements for one symbol, ascending. Empty list when absent.

    Deliberately NOT raising on a missing file: funding_cost() treats an empty
    series as zero, which is honest, whereas a hardcoded default rate is not.
    Callers that require funding must check for themselves - and callers that
    REPORT funding must say when the series was empty, because a zero that
    means "no data" reads identically to a zero that means "measured at zero".
    `screen.py` does exactly that.

    Nothing in this repo has ever stored funding rates: TimescaleDB
    `market_data` holds only klines, orderbook_snapshots and tickers. As of
    2026-08-09 `backtesting/data/funding/` is empty, so every call here returns
    [] until a backfill lands.
    """
    costs = load_costs()
    path = Path(data_dir) / f"{symbol}_funding.csv"
    if not path.is_file():
        return []
    out = []
    with path.open() as fh:
        for row in csv.DictReader(fh):
            out.append(
                costs.FundingSettlement(
                    ts_ms=int(row["ts_ms"]),
                    rate=Decimal(row["funding_rate"]),
                )
            )
    out.sort(key=lambda s: s.ts_ms)
    return out
