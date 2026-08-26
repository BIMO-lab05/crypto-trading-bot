"""
Standard-mode entries must respect the daily trade limit and record the trade.

_execute_trade is the default strategy_mode="standard" path. It never called
_check_daily_trade_limit and never called _record_trade, so standard mode
could open unlimited trades per day and its fills never consumed the budget
the research/hybrid and ensemble paths gate on. The cooldown check that IS
present reads last_trade_time_per_symbol, which only _record_trade writes.

Assert on the counters, not merely on whether a second trade is blocked: a
separate 60s open-cooldown in _last_open_at masks the missing cooldown.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402  - prometheus duplicate-registration guard
import app.core.metrics  # noqa: F401,E402

from unittest.mock import Mock, patch  # noqa: E402

import pytest  # noqa: E402

# Reuse the fully-stubbed harness that already drives this exact path.
# `trader` is a FIXTURE and must be imported by name: pytest resolves fixtures
# from the test module's namespace, its conftest chain, or plugins — and it is
# defined per-module at test_exposure_gate_all_paths.py:84-94, not in
# tests/conftest.py. Without this import both tests ERROR at setup with
# "fixture 'trader' not found". The `# noqa: F401` is load-bearing: the ruff
# format hook strips bare imports and would reintroduce that failure. This is
# the established house pattern — see tests/test_cash_conservation_invariant.py
# :26-30, tests/test_stops_persistence.py:18.
from tests.test_exposure_gate_all_paths import (  # noqa: E402,F401  - fixture reuse
    _drive_default_path,
    _signal,
    _PermissiveInstrumentsCache,
    trader,
)


@pytest.mark.asyncio
async def test_filled_standard_entry_feeds_the_daily_counter(trader):
    engine, sizer, mgr = _drive_default_path(trader, [])
    before = trader.daily_trades_count

    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    assert trader.daily_trades_count == before + 1, (
        "a filled standard-mode entry did not consume the daily budget"
    )
    assert "BTCUSDT" in trader.last_trade_time_per_symbol, (
        "the trade was not recorded, so the general cooldown can never fire"
    )


@pytest.mark.asyncio
async def test_daily_limit_blocks_a_standard_entry(trader):
    engine, sizer, mgr = _drive_default_path(trader, [])
    # daily_trades_date is stamped with today at __init__, so the new-day reset
    # inside _check_daily_trade_limit (auto_trader.py:1448-1454) will not undo
    # this assignment.
    trader.daily_trades_count = trader.max_daily_trades

    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    engine.execute_market_order.assert_not_awaited()
