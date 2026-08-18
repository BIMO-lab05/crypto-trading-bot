"""
The portfolio-heat gate must be fed the order the engine actually places.

The research/hybrid gate computed proposed_risk_pct from
trade_setup.position_size_pct (decorative - the sizing block never reads it)
and settings.default_stop_loss_pct (not the position's stop - it gets the ATR
stop from trade_setup, regime-adjusted). It also omitted side=, so
can_open_trade's pyramiding / no-hedging branch could never fire.

The post-fill ledger books the REAL quantity and stop, so total heat drifted
from what the gate approved. The ensemble path at :4698-4729 already does
this correctly and its comment names this site as the broken sibling.

proposed_risk_pct is percent-of-equity and stop-distance based, matching
PositionRisk.risk_pct. A raw notional percent would be 10.0 and would trip
max_per_trade_pct=2.0 on every entry.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

# Reuse the harness that already drives _execute_trade_with_setup end to end.
# `trader` is a module-local FIXTURE (test_te_cap_05_log_survival.py:82-85), not
# a conftest one, so it must be imported by name or pytest errors with
# "fixture 'trader' not found". The `# noqa: F401` is load-bearing: the ruff
# format hook strips bare imports. Same pattern as
# tests/test_cash_conservation_invariant.py:26-30.
from tests.test_te_cap_05_log_survival import (  # noqa: E402,F401  - fixture reuse
    _make_trade_setup,
    _patch_breach_path_deps,
    trader,
)


@pytest.mark.asyncio
async def test_heat_gate_receives_stop_distance_risk_and_side(trader, monkeypatch):
    # _patch_breach_path_deps is a PLAIN FUNCTION taking (monkeypatch, trader)
    # in that order and returning the 2-tuple (paper_engine, position_mgr)
    # (test_te_cap_05_log_survival.py:119, :201). It is NOT a context manager
    # and NOT a fixture - `with` on it raises TypeError, and swapping the args
    # calls monkeypatch.setattr on the AutoTrader.
    #
    # Call it FIRST: it stubs get_combined_size_multiplier (:165-174, returns a
    # (float, dict) 2-tuple the sizing path unpacks) and get_summary_dict
    # (:175-182) on trader.portfolio_heat_manager. Replacing that manager with a
    # bare MagicMock would strip those stubs - override only the one method
    # under test.
    _patch_breach_path_deps(monkeypatch, trader)
    heat = trader.portfolio_heat_manager
    heat.can_open_trade = MagicMock(return_value=(True, None, 1.0))

    # Side-effect-free post-FILLED stubs, mirroring
    # test_te_cap_05_log_survival.py:223-227.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock(
        return_value={"success": True}
    )
    trader.kill_switch.update_metrics = MagicMock(return_value=[])

    setup = _make_trade_setup()  # entry_price 60000, stop_loss = entry * 0.98

    # The helper stubs only the PRE-cap-check path; get_aggregator,
    # set_position_stops and partial_profit_taker stay live downstream, so a
    # bare await raises before the assertions run. Both existing tests in that
    # file swallow the same way (:242-247, :336-341). Safe here: the heat gate
    # fires before order placement, so call_args is already captured when the
    # downstream raises.
    try:
        await trader._execute_trade_with_setup(symbol="BTCUSDT", trade_setup=setup)
    except Exception:
        pass

    heat.can_open_trade.assert_called_once()
    kwargs = heat.can_open_trade.call_args.kwargs

    assert kwargs["side"] in ("LONG", "SHORT"), (
        "side= was omitted, so the pyramiding / no-hedging branch never fired"
    )

    stop_fraction = abs(setup.entry_price - setup.stop_loss) / setup.entry_price
    equity = kwargs["equity"]
    # risk% = (notional / equity) * stop_fraction * 100, and the notional is
    # clamped to the per-trade cap, so the fed risk cannot exceed
    # cap_fraction * stop_fraction * 100. Derive cap_fraction from the trader's
    # own settings (auto_trader.py:2111-2118) rather than hardcoding it, exactly
    # as test_te_cap_05_log_survival.py:277-280 does. The pre-fix call feeds
    # 1.0 (= position_size_pct 0.5 * 100 * default_stop_loss_pct/100) against a
    # post-fix bound of 0.2, so this assertion genuinely discriminates.
    cap_fraction = float(trader.settings.max_risk_per_trade)
    if str(trader.settings.trading_mode).upper() == "LIVE":
        cap_fraction = min(cap_fraction, 0.02)
    assert kwargs["proposed_risk_pct"] <= cap_fraction * stop_fraction * 100.0 + 1e-9, (
        f"fed risk {kwargs['proposed_risk_pct']} exceeds what a cap-clamped "
        f"order with a {stop_fraction:.1%} stop can possibly risk"
    )
    assert kwargs["proposed_risk_pct"] > 0.0
    assert equity > 0
