"""TE-CAP-05 / D-10: regression guarantee that the CRITICAL BREACH log line survives.

Phase 17 / TE-CAP-05 audits broad-except clauses on the cap-violation-adjacent
order path in services/trading-engine/app/auto_trader.py:1500-3210. This test
exercises the per-trade-cap breach path and asserts:

1. PRIMARY (D-10): the literal `[RISK_GATE] PER_TRADE_CAP BREACH` CRITICAL
   log line from auto_trader.py:1978-1984 appears in caplog.records — no
   surrounding except site swallows it.
2. SECONDARY (D-10): the Prometheus counter
   `risk_limit_breaches_total.labels(breach_type="position_size")` increments
   by exactly 1 across the call (pattern from test_auto_trader_min_notional.py:
   210-231).
3. Trader state: total_trades_rejected increments by 1 (cap-check side-effect
   at auto_trader.py:1985).

HONEST FRAMING (Phase 17 D-10 + advisor analysis): the cap-check block at
:1972-1986 has no intervening try/except today, so on current code the BREACH
log already reaches caplog and this test PASSES on first run. The test ships
as a forward-going regression guarantee — if any future code change introduces
an intervening swallow on the cap-check → BREACH-log → return path, this test
RED-s loudly. The honest "RED" is the failure mode it protects against, not a
current bug.

Per CLAUDE.md memory feedback_main_imports_autoflake.md: the `# noqa: F401`
markers on `app.main` and `app.core.metrics` are load-bearing — autoflake
strips bare imports otherwise, triggering
`Duplicated timeseries in CollectorRegistry` against the default registry.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

# Pre-import app.main + app.core.metrics so deferred imports inside
# _execute_trade_with_setup find the modules already in sys.modules.
# Importing them lazily during a test re-runs prometheus_client.Counter()
# registrations and trips `Duplicated timeseries in CollectorRegistry`.
# autoflake will strip these without the # noqa.
import app.main  # noqa: F401
import app.core.metrics  # noqa: F401

from app.auto_trader import AutoTrader
from app.models.enums import SignalAction
from app.strategies.research_optimized_strategy import (
    MarketCondition,
    SignalStrength,
    TradeSetup,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def trader():
    """Fresh AutoTrader for each test (no _trading_loop running)."""
    return AutoTrader(symbols=["BTCUSDT"])


def _make_trade_setup(entry_price: float = 60000.0) -> TradeSetup:
    """Construct a TradeSetup whose sizing math will breach the per-trade cap.

    With paper_engine.get_balance() = 100.0 and default max_risk_per_trade=0.02
    the cap is $2. We force position_value far above $2 by:
      - symbol_allocation defaults to 1.0/len(trading_symbols); for the single
        ["BTCUSDT"] trader that's 1.0 → allocated_capital = $100.
      - leverage_enabled is False by default, so leverage = 1.0.
      - heat_multiplier defaults to 1.0 unless heat manager intervenes.
      - position_value = allocated_capital * leverage * heat_multiplier = $100,
        which is >> $2 cap.
    The `position_size_pct` field below is decorative for the cap-check path
    (cap-check uses position_value from the sizing math at :1898-1907, not
    position_size_pct directly), but TradeSetup requires it to be set.
    """
    return TradeSetup(
        action=SignalAction.BUY,
        confidence=0.85,
        signal_strength=SignalStrength.STRONG,
        entry_price=entry_price,
        stop_loss=entry_price * 0.98,
        take_profit=entry_price * 1.04,
        position_size_pct=0.5,
        trailing_stop_atr_mult=2.0,
        reasoning=["test fixture: force per-trade cap breach"],
        indicators_aligned=3,
        market_condition=MarketCondition.TRENDING,
    )


def _patch_breach_path_deps(monkeypatch, trader, *, balance: float = 100.0):
    """Stub the dependencies _execute_trade_with_setup pulls from on the
    pre-cap-check path so the function reaches the cap-check without touching
    real services. Mirrors test_auto_trader_min_notional.py:250-279 but tuned
    for the cap-check path rather than the min-notional path.
    """
    # paper engine: get_balance drives `current_equity` at :1695 AND `balance`
    # at :1844. execute_market_order MUST NOT be called on the breach path
    # (cap-check returns at :1986 before submission) — install a defensive
    # AsyncMock so any unexpected call surfaces with a clear assertion.
    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=balance)
    paper_engine.execute_market_order = AsyncMock(
        side_effect=AssertionError(
            "execute_market_order called — cap-check did NOT reject as expected"
        )
    )

    # position manager: get_open_positions must return [] so the
    # "Already have open position" guard at :1851 doesn't short-circuit.
    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])

    # Stub all module-level lookups _execute_trade_with_setup pulls from on
    # the pre-cap-check path (lines roughly :1683-:1971).
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)
    monkeypatch.setattr("app.auto_trader.get_live_engine", lambda: paper_engine)

    # Bypass the concurrent-open dedup gate at :1674 (otherwise the cap-check
    # path is never reached on a fresh trader since _opening_lock interaction
    # is async).
    trader._claim_open_slot = AsyncMock(return_value=True)
    trader._release_open_slot = MagicMock()  # called in finally at :2338

    # Bypass the daily-trade-limit and per-symbol-cooldown guards at :1744, :1750.
    trader._check_daily_trade_limit = MagicMock(return_value=True)
    trader._check_symbol_cooldown = MagicMock(return_value=True)

    # The portfolio-heat manager: allow with multiplier 1.0 so position_value
    # remains at $100 (> $2 cap).
    trader.portfolio_heat_manager.can_open_trade = MagicMock(
        return_value=(True, "OK", 1.0)
    )
    trader.portfolio_heat_manager.get_combined_size_multiplier = MagicMock(
        return_value=(
            1.0,
            {
                "heat_multiplier": 1.0,
                "correlation_multiplier": 1.0,
                "correlation_level": "LOW",
            },
        )
    )
    trader.portfolio_heat_manager.get_summary_dict = MagicMock(
        return_value={
            "total_heat_pct": 0.0,
            "heat_level": "LOW",
            "limits": {"max_portfolio_heat": 100.0},
            "position_count": 0,
        }
    )

    # Kill switch: not halted (so we reach the cap-check, not the kill-switch return).
    trader.kill_switch.should_halt_trading = MagicMock(return_value=False)

    # Slippage manager: don't recommend limit (we're checking cap-check, not slippage).
    trader.slippage_manager.should_use_limit_order = MagicMock(
        return_value=(False, "no")
    )

    return paper_engine, position_mgr


# ============================================================================
# D-10 regression test
# ============================================================================


@pytest.mark.asyncio
async def test_per_trade_cap_breach_log_survives_to_caplog(trader, monkeypatch, caplog):
    """D-10: force position_value > cap_value; assert the CRITICAL BREACH log
    line at auto_trader.py:1978-1984 reaches caplog (no broad-except swallow)
    AND the risk_limit_breaches_total counter increments.

    On current code (Phase 17 land): cap-check block at :1972-1986 has no
    intervening try/except — this test PASSES on first run. Forward-going
    guarantee: any future code change introducing an intervening swallow on
    the cap-check → BREACH-log → return path will RED this test.
    """
    paper_engine, position_mgr = _patch_breach_path_deps(
        monkeypatch, trader, balance=100.0
    )

    trade_setup = _make_trade_setup(entry_price=60000.0)

    import app.core.metrics as metrics

    counter = metrics.risk_limit_breaches_total.labels(breach_type="position_size")
    before = counter._value.get()  # type: ignore[attr-defined]
    rejected_before = trader.total_trades_rejected

    # Pin caplog filter to the module the log line is emitted from. auto_trader.py
    # uses `logger = logging.getLogger(__name__)`, so logger name = "app.auto_trader".
    with caplog.at_level(logging.CRITICAL, logger="app.auto_trader"):
        await trader._execute_trade_with_setup(
            symbol="BTCUSDT", trade_setup=trade_setup
        )

    # Primary D-10 assertion: log line reached caplog.
    assert any(
        "[RISK_GATE] PER_TRADE_CAP BREACH" in rec.message for rec in caplog.records
    ), (
        f"CRITICAL BREACH log line swallowed; "
        f"got {len(caplog.records)} records: "
        f"{[(r.levelname, r.name, r.message[:80]) for r in caplog.records]!r}. "
        f"This means a broad-except site on the cap-check → BREACH-log → "
        f"return path is masking the log emit. Inspect Phase 17 D-09 table "
        f"for the offending site."
    )

    # Secondary D-10 assertion: counter incremented.
    after = counter._value.get()  # type: ignore[attr-defined]
    assert after == before + 1, (
        f'risk_limit_breaches_total.labels(breach_type="position_size") '
        f"did not increment exactly once: before={before}, after={after}. "
        f"Either the cap-check did not fire or the metric increment at "
        f"auto_trader.py:1977 was swallowed."
    )

    # Tertiary trader-state assertion: rejection counter bumped per :1985.
    assert trader.total_trades_rejected == rejected_before + 1, (
        f"total_trades_rejected did not increment: "
        f"before={rejected_before}, after={trader.total_trades_rejected}"
    )

    # Defensive: paper-engine submission must NOT have been called (the breach
    # path returns at :1986 before reaching execute_market_order at :2033).
    # The AsyncMock side_effect=AssertionError would have raised if it had
    # been awaited; if we reach here it was not called — confirm explicitly.
    paper_engine.execute_market_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_per_trade_cap_within_limit_does_not_emit_breach_log(
    trader, monkeypatch, caplog
):
    """Negative complement: when position_value <= cap_value the BREACH log
    must NOT appear. Defends against an over-eager rewrite that would emit
    the log unconditionally.

    Strategy: force balance high enough that the default sizing math stays
    under the cap. With balance=$1,000,000 the cap=$20,000 and position_value
    at allocation=1.0 × leverage=1.0 × heat=1.0 = $1,000,000 still breaches.
    To get UNDER the cap we shrink symbol_allocation via setattr.
    """
    paper_engine, _ = _patch_breach_path_deps(monkeypatch, trader, balance=1_000_000.0)

    # Shrink the BTCUSDT allocation so position_value (= allocation × balance)
    # stays well under cap_value (= 2% × balance).
    monkeypatch.setattr(
        trader.settings, "symbol_allocations", {"BTCUSDT": 0.001}, raising=False
    )

    # The under-cap path will continue into order submission — restore a
    # normal AsyncMock (no AssertionError side-effect this time).
    filled = MagicMock()
    from app.models import OrderStatus

    filled.status = OrderStatus.FILLED
    filled.order_id = "PAPER_BTCUSDT_BUY"
    filled.filled_quantity = Decimal("0.0000166")
    filled.filled_price = Decimal("60000")
    filled.position_id = "test-pos-id"
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))

    # Side-effect free notification + post-FILLED stubs so the test doesn't
    # explode after the cap-check passes. We DON'T care about those branches
    # for this negative assertion — just don't crash.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock(
        return_value={"success": True}
    )

    trade_setup = _make_trade_setup(entry_price=60000.0)

    with caplog.at_level(logging.CRITICAL, logger="app.auto_trader"):
        # Wrap in try/except — post-FILLED branches touch lots of services we
        # haven't stubbed; we only assert about caplog, not the call's outcome.
        try:
            await trader._execute_trade_with_setup(
                symbol="BTCUSDT", trade_setup=trade_setup
            )
        except Exception:
            pass

    assert not any(
        "[RISK_GATE] PER_TRADE_CAP BREACH" in rec.message for rec in caplog.records
    ), (
        f"BREACH log emitted when position_value <= cap_value (false positive). "
        f"Records: {[r.message[:80] for r in caplog.records]!r}"
    )
