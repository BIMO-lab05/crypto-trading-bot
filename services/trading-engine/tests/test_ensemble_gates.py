"""
Stage 0: the ensemble path enforces the gates every other entry path does.

Live evidence: trades.signal_confidence on ensemble entry legs reads
0.3804, 0.2995, 0.2680, 0.2818, 0.2960, 0.2357, 0.1730, 0.2695 - SEVEN of
eight below the configured min_signal_confidence of 0.30. The floor is real
(config.py:408) but it is read in exactly one function, RiskManager.
validate_signal, whose only production caller is the REST /signal endpoint.
No autonomous path has ever consulted it.

allowed_trade_sides is a List[str] in production (config.py:479,
default ["LONG", "SHORT"]) - NOT a "BOTH"/"LONG_ONLY" token. A gate written
against the token form blocks every SHORT in production while staying green
against a string fixture, so both shapes are covered below.
"""

import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py, never a literal.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import so the deferred imports inside _passes_min_notional /
# _snap_quantity_to_step find the modules already in sys.modules (importing
# lazily during a test re-runs prometheus Counter registration and trips
# "Duplicated timeseries in CollectorRegistry").
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from app.models import OrderStatus  # noqa: E402
from app.models.enums import SignalAction  # noqa: E402
from app.services.instruments_cache import InstrumentSpec  # noqa: E402


def _signal(action=SignalAction.BUY, confidence=0.55):
    return SimpleNamespace(
        action=action,
        confidence=confidence,
        stop_loss=71.0,
        take_profit=76.0,
        position_size_pct=0.10,
        leg_actions={"simple_rsi": "BUY"},
    )


@pytest.fixture
def trader(monkeypatch):
    from app.auto_trader import AutoTrader

    t = AutoTrader.__new__(AutoTrader)
    t.settings = SimpleNamespace(
        min_signal_confidence=0.30,
        short_min_confidence=0.70,
        short_trading_enabled=True,
        allowed_trade_sides="BOTH",
    )
    t.total_trades_rejected = 0
    return t


# ============================================================================
# Confidence floor
# ============================================================================


def test_long_below_the_confidence_floor_is_rejected(trader):
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.1730))
        is False
    )


def test_long_above_the_floor_passes(trader):
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.55))
        is True
    )


def test_confidence_exactly_at_the_floor_passes(trader):
    """0.30 is not BELOW 0.30. The live rows that must be rejected sit under
    it; an off-by-one here would silently kill the whole path."""
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.30))
        is True
    )


def test_missing_confidence_floor_setting_does_not_open_the_gate(trader):
    """Absent min_signal_confidence must fail CLOSED, not default to zero."""
    del trader.settings.min_signal_confidence
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.99))
        is False
    )


# ============================================================================
# SHORT side gates
# ============================================================================


def test_short_uses_the_higher_short_floor(trader):
    """0.55 clears min_signal_confidence but not short_min_confidence=0.70."""
    sig = _signal(action=SignalAction.SELL, confidence=0.55)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_short_above_the_short_floor_passes(trader):
    sig = _signal(action=SignalAction.SELL, confidence=0.75)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is True


def test_short_blocked_when_shorts_disabled(trader):
    trader.settings.short_trading_enabled = False
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_short_blocked_by_allowed_trade_sides(trader):
    trader.settings.allowed_trade_sides = "LONG_ONLY"
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_missing_short_floor_setting_does_not_silently_open_the_gate(trader):
    """auto_trader.py:3977 uses getattr(..., 0.0) — a rename would disable the
    gate rather than raise. The ensemble copy must fail CLOSED."""
    del trader.settings.short_min_confidence
    sig = _signal(action=SignalAction.SELL, confidence=0.35)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_missing_allowed_trade_sides_fails_closed(trader):
    del trader.settings.allowed_trade_sides
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_missing_short_trading_enabled_fails_closed(trader):
    del trader.settings.short_trading_enabled
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


# ============================================================================
# PRODUCTION SHAPE: allowed_trade_sides is a List[str], not a token string.
# A gate written as str(...).upper() in ("BOTH", "SHORT_ONLY") renders
# "['LONG', 'SHORT']" and blocks every SHORT in production.
# ============================================================================


def test_production_list_shape_allows_short(trader):
    trader.settings.allowed_trade_sides = ["LONG", "SHORT"]
    sig = _signal(action=SignalAction.SELL, confidence=0.75)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is True


def test_production_list_shape_allows_long(trader):
    trader.settings.allowed_trade_sides = ["LONG", "SHORT"]
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.55))
        is True
    )


def test_production_list_shape_long_only_blocks_short(trader):
    trader.settings.allowed_trade_sides = ["LONG"]
    sig = _signal(action=SignalAction.SELL, confidence=0.95)
    assert trader._ensemble_passes_signal_gates("ADAUSDT", sig) is False


def test_production_list_shape_short_only_blocks_long(trader):
    """The LONG side is gated too — mirrors the default path at :3961, which
    checks allowed_trade_sides for both directions."""
    trader.settings.allowed_trade_sides = ["SHORT"]
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.55))
        is False
    )


def test_empty_allowed_trade_sides_blocks_everything(trader):
    trader.settings.allowed_trade_sides = []
    assert (
        trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.99))
        is False
    )


# ============================================================================
# Counter hygiene
# ============================================================================


def test_gate_rejections_increment_the_rejection_counter_once(trader):
    trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.1))
    assert trader.total_trades_rejected == 1


def test_a_passing_signal_does_not_increment_the_counter(trader):
    trader._ensemble_passes_signal_gates("ADAUSDT", _signal(confidence=0.99))
    assert trader.total_trades_rejected == 0


def test_a_short_rejected_by_the_short_floor_counts_once_not_twice(trader):
    """The generic floor and the short floor are two checks on one signal;
    only the one that actually rejects may count."""
    sig = _signal(action=SignalAction.SELL, confidence=0.55)
    trader._ensemble_passes_signal_gates("ADAUSDT", sig)
    assert trader.total_trades_rejected == 1


# ============================================================================
# Integration: the gates are actually WIRED into _check_and_trade_ensemble,
# and the open-slot claim is released on every exit path. Harness mirrors
# tests/test_ensemble_stops_applied.py.
# ============================================================================

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))
SOL_PRICE = 71.0

SOL_SPEC = InstrumentSpec(
    symbol="SOLUSDT",
    min_order_qty=Decimal("0.1"),
    qty_step=Decimal("0.1"),
    tick_size=Decimal("0.010"),
    min_notional=Decimal("5"),
    fetched_at=datetime.now(timezone.utc),
)


class _StubInstrumentsCache:
    def __init__(self, specs):
        self._specs = specs

    async def get(self, symbol):
        return self._specs.get(symbol)


@pytest.fixture
def live_trader(monkeypatch):
    from app.auto_trader import AutoTrader
    from app.trading_enhancements.portfolio_heat import (
        reset_portfolio_heat_manager,
    )

    # PortfolioHeatManager is a process-global singleton and nothing in the
    # suite reset it, because until this task no test-reachable entry path
    # consulted it. Earlier tests leave positions in it, so without this the
    # heat gate below rejects on state from an unrelated test.
    reset_portfolio_heat_manager()

    t = AutoTrader(symbols=["SOLUSDT"])
    monkeypatch.setattr(t.settings, "trading_mode", "PAPER", raising=False)
    monkeypatch.setattr(t.settings, "leverage_enabled", False, raising=False)
    monkeypatch.setattr(t.settings, "max_position_size_pct", 10.0, raising=False)
    monkeypatch.setattr(t.settings, "max_total_exposure_pct", 80.0, raising=False)
    t.notification_client = MagicMock()
    t.notification_client.notify_trade_open = AsyncMock()
    t.notification_client.notify_trade_close = AsyncMock()
    return t


def _wire(
    live_trader,
    monkeypatch,
    *,
    confidence=0.55,
    action=SignalAction.BUY,
    fill=True,
):
    """Stub every external dependency of _check_and_trade_ensemble."""
    cache = _StubInstrumentsCache({"SOLUSDT": SOL_SPEC})
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    risk_mgr = MagicMock()
    risk_mgr.should_halt_trading = MagicMock(return_value=False)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)

    indicator = MagicMock()
    indicator.metadata = {"current_price": SOL_PRICE}
    base_signal = MagicMock()
    base_signal.indicators = {"rsi": indicator}

    aggregator = MagicMock()
    aggregator.get_trading_signal_multi_timeframe = AsyncMock(return_value=base_signal)

    async def _fake_get_aggregator():
        return aggregator

    monkeypatch.setattr("app.auto_trader.get_aggregator", _fake_get_aggregator)

    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=BALANCE)
    if fill:
        filled = MagicMock()
        filled.status = OrderStatus.FILLED
        filled.position_id = uuid4()
        paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))
    else:
        paper_engine.execute_market_order = AsyncMock(return_value=(None, "rejected"))
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ens_signal = MagicMock()
    ens_signal.action = action
    ens_signal.confidence = confidence
    ens_signal.position_size_pct = 0.10
    # Mirror the pair for a SELL. This used to hardcode the LONG shape for
    # every action, which wired the SHORT test with an INVERTED pair — stop
    # below entry, target above it. That was invisible while the inversion
    # check ran only after the fill; the pre-fill gate added on 2026-08-08
    # rejects it, correctly, before the heat manager is ever consulted. The
    # fixture was wrong, not the gate.
    if action == SignalAction.SELL:
        ens_signal.stop_loss = SOL_PRICE * 1.02
        ens_signal.take_profit = SOL_PRICE * 0.96
    else:
        ens_signal.stop_loss = SOL_PRICE * 0.98
        ens_signal.take_profit = SOL_PRICE * 1.04
    ens_signal.leg_actions = {"simple_rsi": action.value}
    ens_signal.leg_contributions = {}

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=ens_signal)

    # Patch the module OBJECT, not the dotted string (see
    # test_sizing_caps_phase1.py for why).
    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)

    return paper_engine


@pytest.mark.asyncio
async def test_live_evidence_confidence_is_rejected_end_to_end(
    live_trader, monkeypatch
):
    """0.1730 is the lowest confidence observed on a real ensemble entry leg."""
    paper_engine = _wire(live_trader, monkeypatch, confidence=0.1730)

    before = live_trader.total_trades_rejected
    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert live_trader.total_trades_rejected == before + 1
    assert "SOLUSDT" not in live_trader._opening_symbols


@pytest.mark.asyncio
async def test_daily_trade_limit_blocks_the_ensemble_path(live_trader, monkeypatch):
    paper_engine = _wire(live_trader, monkeypatch)
    live_trader.daily_trades_count = live_trader.max_daily_trades

    before = live_trader.total_trades_rejected
    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert live_trader.total_trades_rejected == before + 1
    assert "SOLUSDT" not in live_trader._opening_symbols


@pytest.mark.asyncio
async def test_portfolio_heat_blocks_the_ensemble_path(live_trader, monkeypatch):
    paper_engine = _wire(live_trader, monkeypatch)
    heat = MagicMock()
    heat.can_open_trade = MagicMock(return_value=(False, "heat CRITICAL", 0.0))
    live_trader.portfolio_heat_manager = heat

    before = live_trader.total_trades_rejected
    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert live_trader.total_trades_rejected == before + 1
    assert "SOLUSDT" not in live_trader._opening_symbols


@pytest.mark.asyncio
async def test_heat_is_called_with_equity_and_side_and_returns_three(
    live_trader, monkeypatch
):
    """can_open_trade's real signature REQUIRES equity and returns a 3-tuple.
    The existing call at :1831 omits side=, so its pyramiding / no-hedging
    branch never fires there; this path must pass it."""
    _wire(live_trader, monkeypatch)
    heat = MagicMock()
    heat.can_open_trade = MagicMock(return_value=(True, None, 1.0))
    live_trader.portfolio_heat_manager = heat

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    heat.can_open_trade.assert_called_once()
    kwargs = heat.can_open_trade.call_args.kwargs
    assert kwargs["symbol"] == "SOLUSDT"
    assert kwargs["equity"] == pytest.approx(float(BALANCE))
    assert kwargs["side"] == "LONG"
    # Risk is stop-distance based, matching PositionRisk.risk_pct
    # (portfolio_heat.py:233) - a raw notional percent would be 10.0 and
    # would trip max_per_trade_pct=2.0 on every single entry.
    assert kwargs["proposed_risk_pct"] == pytest.approx(0.10 * 0.02 * 100, rel=1e-6)


@pytest.mark.asyncio
async def test_short_side_is_reported_to_the_heat_manager(live_trader, monkeypatch):
    _wire(live_trader, monkeypatch, action=SignalAction.SELL, confidence=0.95)
    heat = MagicMock()
    heat.can_open_trade = MagicMock(return_value=(True, None, 1.0))
    live_trader.portfolio_heat_manager = heat

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    heat.can_open_trade.assert_called_once()
    assert heat.can_open_trade.call_args.kwargs["side"] == "SHORT"


@pytest.mark.asyncio
async def test_open_slot_is_released_when_the_fill_fails(live_trader, monkeypatch):
    """A leaked slot permanently blocks the symbol. The method has 8 early
    returns after the claim; the release must live in a finally."""
    paper_engine = _wire(live_trader, monkeypatch, fill=False)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    assert "SOLUSDT" not in live_trader._opening_symbols
    # No position opened - the open-cooldown stamp must NOT be armed.
    assert "SOLUSDT" not in live_trader._last_open_at


@pytest.mark.asyncio
async def test_open_slot_is_released_and_stamped_after_a_successful_fill(
    live_trader, monkeypatch
):
    paper_engine = _wire(live_trader, monkeypatch)

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    assert "SOLUSDT" not in live_trader._opening_symbols
    assert "SOLUSDT" in live_trader._last_open_at


@pytest.mark.asyncio
async def test_a_filled_ensemble_entry_feeds_the_daily_counter(
    live_trader, monkeypatch
):
    """_check_daily_trade_limit reads daily_trades_count, which only
    _record_trade increments — called from _execute_trade_with_setup alone
    before this change. Without this the new daily-limit gate is a gate on a
    counter nothing on this path ever moves."""
    _wire(live_trader, monkeypatch)
    before = live_trader.daily_trades_count

    await live_trader._check_and_trade_ensemble("SOLUSDT")

    assert live_trader.daily_trades_count == before + 1


@pytest.mark.asyncio
async def test_a_second_open_in_flight_is_refused_without_double_counting(
    live_trader, monkeypatch
):
    """_claim_open_slot increments total_trades_rejected internally. A call
    site that also increments would count one rejection twice."""
    _wire(live_trader, monkeypatch)
    live_trader._opening_symbols.add("SOLUSDT")

    before = live_trader.total_trades_rejected
    await live_trader._check_and_trade_ensemble("SOLUSDT")

    assert live_trader.total_trades_rejected == before + 1
# ============================================================================
# 2026-08-20 default fix: short_min_confidence 0.70 -> 0.35. The old default
# sat above the ensemble's structural SELL ceiling of ~0.60 (leg SELL caps
# simple_rsi 0.80 + mean_reversion 1.00 + aggregator 0, weights 1/3 each), so
# the SHORT gate was mathematically unreachable — 379 of 623 SELLs died there
# in one run, all-time max recorded ensemble confidence 0.3804.
# ============================================================================


def test_shipped_short_floor_default_is_0_35():
    """Guards the default itself, not just the mechanism: >= 0.60 is
    unreachable for the 3-leg ensemble."""
    from app.config import Settings

    assert Settings.model_fields["short_min_confidence"].default == 0.35


@pytest.fixture
def trader_with_config_defaults():
    """Gate fixture wired to the REAL shipped defaults, so these tests fail
    if either floor drifts back above the structural ceiling."""
    from app.auto_trader import AutoTrader
    from app.config import Settings

    fields = Settings.model_fields
    t = AutoTrader.__new__(AutoTrader)
    t.settings = SimpleNamespace(
        min_signal_confidence=fields["min_signal_confidence"].default,
        short_min_confidence=fields["short_min_confidence"].default,
        short_trading_enabled=True,
        allowed_trade_sides=["LONG", "SHORT"],
    )
    t.total_trades_rejected = 0
    return t


def test_short_at_0_40_passes_the_new_default_short_floor(
    trader_with_config_defaults,
):
    """0.40 is inside the observed ensemble range (max 0.3804 is close) and
    above the 0.35 floor — the gate is now reachable."""
    sig = _signal(action=SignalAction.SELL, confidence=0.40)
    assert (
        trader_with_config_defaults._ensemble_passes_signal_gates("ADAUSDT", sig)
        is True
    )


def test_short_at_0_32_fails_the_short_floor(trader_with_config_defaults):
    """0.32 clears the general 0.30 floor but not the 0.35 short floor."""
    sig = _signal(action=SignalAction.SELL, confidence=0.32)
    assert (
        trader_with_config_defaults._ensemble_passes_signal_gates("ADAUSDT", sig)
        is False
    )


def test_long_at_0_32_passes_where_the_short_fails(trader_with_config_defaults):
    """The 0.35 floor is SHORT-only extra conviction; LONGs face only 0.30."""
    sig = _signal(action=SignalAction.BUY, confidence=0.32)
    assert (
        trader_with_config_defaults._ensemble_passes_signal_gates("ADAUSDT", sig)
        is True
    )


def test_short_at_0_28_fails_the_general_floor(trader_with_config_defaults):
    """Below min_signal_confidence=0.30 the general gate rejects before the
    short floor is ever consulted."""
    sig = _signal(action=SignalAction.SELL, confidence=0.28)
    assert (
        trader_with_config_defaults._ensemble_passes_signal_gates("ADAUSDT", sig)
        is False
    )


# ============================================================================
# Boot-time warning: an unreachable short floor must be flagged at startup
# (log-only — never a boot failure). Wired in app/lifespan/data.py right
# after validate_allocations().
# ============================================================================


def test_boot_warning_fires_when_short_floor_is_structurally_unreachable(
    caplog,
):
    """0.70 sits above the ~0.60 ceiling that holds under DEFAULT 1/3 leg
    weights (adaptive weights can raise it - the warning is hedged)."""
    from app.config import Settings

    s = Settings(short_min_confidence=0.70)
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s.warn_if_short_gate_unreachable()
    assert any(
        "SHORT entries cannot pass the ensemble gate" in rec.message
        for rec in caplog.records
    )
    assert any(
        "under default 1/3 ensemble weights" in rec.message
        for rec in caplog.records
    )


def test_boot_warning_fires_when_short_floor_is_inert(caplog):
    """0.25 sits below min_signal_confidence=0.30: the SHORT-specific floor
    can never be the rejecting gate - the general floor rejects first."""
    from app.config import Settings

    s = Settings(short_min_confidence=0.25)
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s.warn_if_short_gate_unreachable()
    assert any(
        "SHORT-specific floor is inert" in rec.message for rec in caplog.records
    )


def test_no_boot_warning_at_the_shipped_default(caplog):
    """0.35 sits between the general floor (0.30) and the default-weights
    ceiling (~0.60): neither warning may fire."""
    from app.config import Settings

    s = Settings()
    with caplog.at_level(logging.WARNING, logger="app.config"):
        s.warn_if_short_gate_unreachable()
    assert not any(
        "short_min_confidence" in rec.message for rec in caplog.records
    )
