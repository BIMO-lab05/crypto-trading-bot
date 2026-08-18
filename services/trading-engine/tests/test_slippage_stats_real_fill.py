"""
Slippage stats must compare the reference price against the real fill.

record_execution was fed trade_setup.entry_price as BOTH expected and actual,
so every record carried slippage_pct = 0.0. The comment claimed actual equals
expected "for market orders in simulation" - false since PAPER-01 (fb45efe,
2026-08-03): the paper engine applies paper_slippage.py and returns the
adjusted fill on executed_order.filled_price.

The adaptive machinery (per-symbol history, should_use_limit_order, the 0.50%
rejection threshold, get_status) therefore measured a constant zero.
"""

import sys
from decimal import Decimal
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# `trader` is a module-local FIXTURE (test_te_cap_05_log_survival.py:82-85), not
# a conftest one, so it must be imported by name. `# noqa: F401` is load-bearing
# against the ruff import-stripping hook. Same pattern as
# tests/test_stops_persistence.py:18.
from tests.test_te_cap_05_log_survival import (  # noqa: E402,F401  - fixture reuse
    _make_trade_setup,
    _patch_breach_path_deps,
    trader,
)


@pytest.mark.asyncio
async def test_record_execution_gets_the_real_fill(trader, monkeypatch):
    setup = _make_trade_setup(entry_price=60000.0)

    # _patch_breach_path_deps is a PLAIN FUNCTION taking (monkeypatch, trader)
    # and returning (paper_engine, position_mgr) — not a context manager, and it
    # has no `filled_price` parameter (its only keyword-only argument is
    # `balance`). See test_te_cap_05_log_survival.py:119, :201.
    paper_engine, _ = _patch_breach_path_deps(monkeypatch, trader)

    # The helper hardcodes filled_price = Decimal("60000") at :135, which is
    # numerically EQUAL to _make_trade_setup's default entry_price of 60000.0 —
    # it supplies NO divergence. Override the returned mock's fill here (do not
    # modify the shared helper); `filled_order` itself is a helper-local the
    # test cannot reach, but paper_engine.execute_market_order is
    # AsyncMock(return_value=(filled_order, None)) at :137, so index into it.
    # 5 bps worse than the reference the order was submitted at.
    fill = Decimal(str(setup.entry_price)) * Decimal("1.0005")
    paper_engine.execute_market_order.return_value[0].filled_price = fill

    recorder = MagicMock()
    trader.slippage_manager.record_execution = recorder

    # record_execution sits downstream of kill_switch.update_metrics
    # (auto_trader.py:2257-2265), so stub that and the notification client the
    # way test_te_cap_05_log_survival.py:223-227 does.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock(
        return_value={"success": True}
    )
    trader.kill_switch.update_metrics = MagicMock(return_value=[])

    # The helper stubs only the PRE-cap-check path; set_position_stops and
    # partial_profit_taker run live AFTER record_execution and raise. Both
    # existing tests in that file swallow identically (:242-247, :336-341), and
    # the swallow cannot mask the assertions below because record_execution is
    # already captured by the time the downstream raises.
    try:
        await trader._execute_trade_with_setup(symbol="BTCUSDT", trade_setup=setup)
    except Exception:
        pass

    recorder.assert_called_once()
    kwargs = recorder.call_args.kwargs
    assert kwargs["expected_price"] == Decimal(str(setup.entry_price))
    assert kwargs["actual_price"] == fill, (
        f"actual_price {kwargs['actual_price']} is the reference price, not "
        "the engine's slippage-adjusted fill - the stats measure zero"
    )
    assert kwargs["actual_price"] != kwargs["expected_price"]
