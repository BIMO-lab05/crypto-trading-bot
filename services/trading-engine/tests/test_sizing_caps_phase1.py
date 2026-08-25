"""
Phase 1 regression tests for AUDIT.md §6.4 / §6.5c / §7 (H1, H2, H6).

Covers, against the declared account (shared/account.py is the declaration of
record — no account-size literals here; expectations derive from BALANCE):

* H1(a): the ensemble per-trade notional cap is independent of leverage —
  leverage divides margin, it must never multiply the cap ceiling.
* H1(b): total-exposure gate on the ensemble path rejects when open entry
  notionals plus the new notional exceed max_total_exposure_pct of balance.
* H1(c) / min-notional in PAPER: the gate no longer short-circuits in PAPER
  mode. On a pinned $100 balance (SMALL_BALANCE — the scenario the gate
  exists for) a 10% BTCUSDT trade (min qty 0.001 ≈ $62) must be REJECTED
  with reason "min_qty"; SOLUSDT one qty_step must pass.
* Quantity snapping: quantities floor DOWN to qty_step, never up.
* H2: a paper stop exit fills at the stop price (adjusted only by the
  slippage model) — the deterministic 0.5% buffer penalty is gone. A LONG
  with a 2.0% stop realizes ≈ −2.0%, never −2.49%.
* H6: max-hold (auto_close) exits arm the same per-symbol cooldown as
  stop-loss exits, and the ensemble entry path checks that cooldown.

All HTTP / DB / engine dependencies are stubbed via monkeypatch so these run
as pure host-side unit tests (no container).
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py, never a literal. conftest puts <repo>/shared on
# sys.path for the database package; `shared.account` needs the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import app.main / app.core.metrics so the deferred imports inside
# _passes_min_notional / _snap_quantity_to_step find the modules already in
# sys.modules (importing lazily during a test re-runs prometheus Counter
# registration and trips "Duplicated timeseries in CollectorRegistry").
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from app.auto_trader import AutoTrader  # noqa: E402
from app.models import OrderStatus  # noqa: E402
from app.models.enums import SignalAction, ExitKind  # noqa: E402
from app.services.instruments_cache import InstrumentSpec  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))

# pinned small-account scenario: keeps reject-not-clamp coverage (a 10% trade
# sitting under Bybit's min-qty floor); NOT the declared account size — that is
# BALANCE above, which tracks shared/account.py.
SMALL_BALANCE = Decimal("100")

# Venue specs from AUDIT.md §3 (live-fetched from bybit-connector 2026-08-04).
BTC_PRICE = 62551.0
SOL_PRICE = 71.0


def _spec(
    symbol: str,
    min_qty: str,
    qty_step: str,
    tick: str,
    min_notional: Optional[str] = "5",
) -> InstrumentSpec:
    return InstrumentSpec(
        symbol=symbol,
        min_order_qty=Decimal(min_qty),
        qty_step=Decimal(qty_step),
        tick_size=Decimal(tick),
        min_notional=Decimal(min_notional) if min_notional is not None else None,
        fetched_at=datetime.now(timezone.utc),
    )


BTC_SPEC = _spec("BTCUSDT", "0.001", "0.001", "0.10")
SOL_SPEC = _spec("SOLUSDT", "0.1", "0.1", "0.010")


class _StubInstrumentsCache:
    def __init__(self, specs: dict[str, InstrumentSpec]):
        self._specs = specs
        self.calls: list[str] = []

    async def get(self, symbol: str):
        self.calls.append(symbol)
        return self._specs.get(symbol)


@pytest.fixture
def instruments_cache(monkeypatch):
    cache = _StubInstrumentsCache({"BTCUSDT": BTC_SPEC, "SOLUSDT": SOL_SPEC})
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)
    return cache


@pytest.fixture
def trader(monkeypatch):
    # PortfolioHeatManager is a process-global singleton that earlier tests
    # leave positions in. The ensemble path consults it since Stage 0 Task 9,
    # so without this reset these sizing assertions fail on unrelated state.
    from app.trading_enhancements.portfolio_heat import (
        reset_portfolio_heat_manager,
    )

    reset_portfolio_heat_manager()

    t = AutoTrader(symbols=["BTCUSDT", "SOLUSDT"])
    # Deterministic risk config for the sizing math under test (mirrors the
    # compose/production values; percent vs fraction units per .claude/rules).
    monkeypatch.setattr(t.settings, "trading_mode", "PAPER", raising=False)
    monkeypatch.setattr(t.settings, "leverage_enabled", True, raising=False)
    monkeypatch.setattr(t.settings, "default_leverage", 10.0, raising=False)
    monkeypatch.setattr(t.settings, "max_leverage", 20.0, raising=False)
    monkeypatch.setattr(t.settings, "min_leverage", 1.0, raising=False)
    monkeypatch.setattr(t.settings, "max_position_size_pct", 10.0, raising=False)
    monkeypatch.setattr(t.settings, "max_total_exposure_pct", 80.0, raising=False)
    t.notification_client = MagicMock()
    t.notification_client.notify_trade_open = AsyncMock()
    t.notification_client.notify_trade_close = AsyncMock()
    return t


# ---------------------------------------------------------------- helpers


def _ens_signal(size_pct: float, price: float, confidence: float = 0.30):
    sig = MagicMock()
    sig.action = SignalAction.BUY
    sig.confidence = confidence
    sig.position_size_pct = size_pct
    sig.stop_loss = price * 0.98
    sig.take_profit = price * 1.04
    sig.leg_actions = {"simple_rsi": "BUY"}
    sig.leg_contributions = {}
    return sig


def _base_signal(price: float):
    indicator = MagicMock()
    indicator.metadata = {"current_price": price}
    sig = MagicMock()
    sig.indicators = {"rsi": indicator}
    return sig


def _open_position(symbol: str, entry_price: str, qty: str):
    p = MagicMock()
    p.symbol = symbol
    p.entry_price = Decimal(entry_price)
    p.quantity = Decimal(qty)
    p.remaining_quantity = Decimal(qty)
    return p


def _wire_ensemble(
    trader,
    monkeypatch,
    *,
    price: float,
    size_pct: float,
    open_positions: list,
    balance: Decimal = BALANCE,
):
    """Stub every external dependency of _check_and_trade_ensemble."""
    risk_mgr = MagicMock()
    risk_mgr.should_halt_trading = MagicMock(return_value=False)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)

    aggregator = MagicMock()
    aggregator.get_trading_signal_multi_timeframe = AsyncMock(return_value=_base_signal(price))

    async def _fake_get_aggregator():
        return aggregator

    monkeypatch.setattr("app.auto_trader.get_aggregator", _fake_get_aggregator)

    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=balance)
    filled = MagicMock()
    filled.status = OrderStatus.FILLED
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=open_positions)
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=_ens_signal(size_pct, price))
    # Patch the module OBJECT, not the dotted string: conftest's autouse
    # patch.dict("sys.modules") restore evicts modules first imported during a
    # test, and string-target monkeypatch then patches a module object that
    # auto_trader's deferred import no longer resolves. A plain import here
    # pins the same module object the deferred import will see this test.
    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)

    return paper_engine


# ============================================================================
# H1(a): per-trade notional cap independent of leverage (ensemble path)
# ============================================================================


@pytest.mark.asyncio
async def test_ensemble_cap_is_independent_of_leverage(trader, monkeypatch, instruments_cache):
    """10% size × 10x leverage used to produce ~100% of balance as notional.
    The notional must be capped at max_position_size_pct of balance, then
    floored DOWN to qty_step (expected quantity derived, not hand-computed)."""
    paper_engine = _wire_ensemble(
        trader, monkeypatch, price=SOL_PRICE, size_pct=0.10, open_positions=[]
    )

    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    order = paper_engine.execute_market_order.await_args.args[0]
    notional = float(order.quantity) * SOL_PRICE
    cap = float(BALANCE) * trader.settings.max_position_size_pct / 100.0
    assert notional <= cap + 1e-9, (
        f"notional ${notional:.2f} exceeds cap ${cap:.2f} — leverage is multiplying the cap again"
    )
    # cap / price snapped DOWN to a whole number of qty_steps, never up.
    raw_qty = Decimal(str(cap)) / Decimal(str(SOL_PRICE))
    expected_qty = (raw_qty // SOL_SPEC.qty_step) * SOL_SPEC.qty_step
    assert raw_qty != expected_qty, "fixture no longer exercises the snap"
    assert order.quantity == expected_qty
    assert notional == pytest.approx(float(expected_qty) * SOL_PRICE, abs=1e-9)


@pytest.mark.asyncio
async def test_ensemble_cap_holds_at_higher_leverage(trader, monkeypatch, instruments_cache):
    """Doubling leverage must not change the notional ceiling at all."""
    monkeypatch.setattr(trader.settings, "default_leverage", 20.0, raising=False)
    paper_engine = _wire_ensemble(
        trader, monkeypatch, price=SOL_PRICE, size_pct=0.10, open_positions=[]
    )

    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    order = paper_engine.execute_market_order.await_args.args[0]
    cap = float(BALANCE) * trader.settings.max_position_size_pct / 100.0
    assert float(order.quantity) * SOL_PRICE <= cap + 1e-9


# ============================================================================
# H1(b): total-exposure gate rejects (ensemble path)
# ============================================================================


@pytest.mark.asyncio
async def test_ensemble_exposure_gate_rejects(trader, monkeypatch, instruments_cache):
    """Open notionals at 76% of balance + a new ~10% trade breaches the 80%
    exposure cap → the trade must be REJECTED (not clamped, not placed)."""
    # Quantities derived so each open position is 38% of balance (76% total).
    open_positions = [
        _open_position("BNBUSDT", "576", BALANCE * Decimal("0.38") / Decimal("576")),
        _open_position("ADAUSDT", "0.169", BALANCE * Decimal("0.38") / Decimal("0.169")),
    ]
    paper_engine = _wire_ensemble(
        trader,
        monkeypatch,
        price=SOL_PRICE,
        size_pct=0.10,
        open_positions=open_positions,
    )

    rejected_before = trader.total_trades_rejected
    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert trader.total_trades_rejected == rejected_before + 1


@pytest.mark.asyncio
async def test_ensemble_exposure_gate_allows_under_cap(trader, monkeypatch, instruments_cache):
    """Sanity inverse: modest open exposure below the cap must still trade."""
    # ≈ 5% of balance open + a ~10% new trade stays well under the 80% cap.
    open_positions = [_open_position("BNBUSDT", "576", BALANCE * Decimal("0.05") / Decimal("576"))]
    paper_engine = _wire_ensemble(
        trader,
        monkeypatch,
        price=SOL_PRICE,
        size_pct=0.10,
        open_positions=open_positions,
    )

    await trader._check_and_trade_ensemble("SOLUSDT")
    paper_engine.execute_market_order.assert_awaited_once()


# ============================================================================
# H1(c) + PAPER min-notional: BTC rejected (min_qty), SOL passes
# ============================================================================


@pytest.mark.asyncio
async def test_min_notional_gate_active_in_paper_btc_rejected(trader, instruments_cache):
    """PAPER mode no longer short-circuits the gate. On the pinned $100
    balance a 10% BTC quantity (≈0.00015987 < 0.001 min) must be rejected
    with reason "min_qty". Pinned small-account scenario: at the declared
    balance a 10% BTC trade clears min_qty, which would make this vacuous."""
    assert trader.settings.trading_mode == "PAPER"
    qty = SMALL_BALANCE * Decimal("0.10") / Decimal(str(BTC_PRICE))  # ≈ 0.00015987

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=qty,
        price=Decimal(str(BTC_PRICE)),
        balance=SMALL_BALANCE,
    )
    assert ok is False
    assert reason == "min_qty"
    # The old PAPER short-circuit returned before ever touching the cache.
    assert instruments_cache.calls == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_min_notional_gate_active_in_paper_sol_passes(trader, instruments_cache):
    """SOL one qty_step (0.1 ≈ $7.10) clears min qty (0.1) and min notional
    ($5) — must pass in PAPER, even on the pinned small balance where the
    notional sits closest to the floor."""
    assert trader.settings.trading_mode == "PAPER"
    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=SMALL_BALANCE,
    )
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_ensemble_btc_rejected_end_to_end_with_min_qty_reason(
    trader, monkeypatch, instruments_cache
):
    """End-to-end on the ensemble path: on the pinned $100 balance, BTC under
    the 10% cap ($10) floors to zero at qty_step and the gate rejects it
    labeled "min_qty". No order ever reaches the engine. Pinned small-account
    scenario: keeps reject-not-clamp coverage; NOT the declared account size."""
    import app.core.metrics as metrics

    counter = metrics.trades_rejected_min_notional_total.labels(symbol="BTCUSDT", reason="min_qty")
    before = counter._value.get()  # type: ignore[attr-defined]

    paper_engine = _wire_ensemble(
        trader,
        monkeypatch,
        price=BTC_PRICE,
        size_pct=0.10,
        open_positions=[],
        balance=SMALL_BALANCE,
    )

    rejected_before = trader.total_trades_rejected
    await trader._check_and_trade_ensemble("BTCUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert trader.total_trades_rejected == rejected_before + 1
    after = counter._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


# ============================================================================
# Quantity snapping: DOWN to qty_step, never up
# ============================================================================


@pytest.mark.asyncio
async def test_snap_quantity_floors_down_never_up(trader, instruments_cache):
    # $10 / $71 = 0.14084… → 0.1 (down), never 0.2
    snapped = await trader._snap_quantity_to_step("SOLUSDT", 0.140845)
    assert snapped == Decimal("0.1")
    # 0.199999 is one micro-step short of 0.2 → still 0.1
    snapped = await trader._snap_quantity_to_step("SOLUSDT", 0.199999)
    assert snapped == Decimal("0.1")
    # BTC under the cap floors to zero (then rejected downstream, never filled)
    snapped = await trader._snap_quantity_to_step("BTCUSDT", 0.00015987)
    assert snapped == Decimal("0")
    # Exact multiples pass through untouched
    snapped = await trader._snap_quantity_to_step("SOLUSDT", Decimal("0.3"))
    assert snapped == Decimal("0.3")


@pytest.mark.asyncio
async def test_snap_quantity_fail_open_on_cache_miss(trader, monkeypatch):
    cache = _StubInstrumentsCache({})
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)
    snapped = await trader._snap_quantity_to_step("SOLUSDT", 0.140845)
    assert snapped == Decimal("0.140845")  # unchanged, loudly (fail-open)


# ============================================================================
# H2: paper stop exit fills at the stop price (no deterministic penalty)
# ============================================================================


def _stop_position(side: str, entry: str, stop: str):
    position = Mock()
    position.id = uuid4()
    position.symbol = "SOLUSDT"
    position.side = Mock(value=side)
    position.entry_price = Decimal(entry)
    position.quantity = Decimal("0.1")
    position.remaining_quantity = Decimal("0.1")
    position.stop_loss = Decimal(stop)
    return position


def _wire_stop_close(trader, monkeypatch):
    """Paper engine that echoes the reference price as the fill (i.e. a
    zero-slippage model) so the test isolates the buffer penalty."""
    paper_engine = MagicMock()

    async def _echo_fill(order, reference_price):
        filled = MagicMock()
        filled.status = OrderStatus.FILLED
        filled.filled_price = reference_price
        return (filled, None)

    paper_engine.execute_market_order = AsyncMock(side_effect=_echo_fill)
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_position = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    finalize = AsyncMock()
    monkeypatch.setattr(trader, "_finalize_closed_position", finalize)
    return paper_engine, finalize


@pytest.mark.asyncio
async def test_long_stop_exit_fills_at_stop_price_minus_2_pct(trader, monkeypatch):
    """LONG entry 100, stop 98 (2.0%). With a zero-slippage fill the exit must
    realize exactly −2.00% — never −2.49% (the old 0.5% buffer penalty)."""
    paper_engine, finalize = _wire_stop_close(trader, monkeypatch)
    position = _stop_position("LONG", "100.0", "98.0")

    await trader._close_position_with_limit_order(
        position=position, current_price=97.9, reason="stop_loss"
    )

    paper_engine.execute_market_order.assert_awaited_once()
    order, fill_ref = paper_engine.execute_market_order.await_args.args
    assert fill_ref == Decimal("98.0"), (
        f"fill reference {fill_ref} is not the stop price — buffer penalty is back"
    )
    assert order.reduce_only is True
    assert order.strategy == "stop_loss_limit"
    # Stage 0 (Task 6): _exit_kind_for is called on the undecorated "stop_loss"
    # reason before the order is built, so the structured record agrees with
    # the prose tag above.
    assert order.exit_kind == ExitKind.HARD_STOP

    finalize.assert_awaited_once()
    actual_fill = finalize.await_args.args[2]
    realized_pct = (actual_fill - 100.0) / 100.0 * 100.0
    assert realized_pct == pytest.approx(-2.0, abs=1e-9)
    assert realized_pct > -2.49


@pytest.mark.asyncio
async def test_short_stop_exit_fills_at_stop_price(trader, monkeypatch):
    """SHORT entry 100, stop 102 (2.0%): fill ref must be 102, realizing
    −2.00% — never −2.51%."""
    paper_engine, finalize = _wire_stop_close(trader, monkeypatch)
    position = _stop_position("SHORT", "100.0", "102.0")

    await trader._close_position_with_limit_order(
        position=position, current_price=102.1, reason="stop_loss"
    )

    _, fill_ref = paper_engine.execute_market_order.await_args.args
    assert fill_ref == Decimal("102.0")
    actual_fill = finalize.await_args.args[2]
    realized_pct = (100.0 - actual_fill) / 100.0 * 100.0  # SHORT P&L
    assert realized_pct == pytest.approx(-2.0, abs=1e-9)


@pytest.mark.asyncio
async def test_stop_exit_arms_symbol_cooldown(trader, monkeypatch):
    paper_engine, _finalize = _wire_stop_close(trader, monkeypatch)
    position = _stop_position("LONG", "100.0", "98.0")

    assert trader._check_symbol_cooldown("SOLUSDT") is True
    await trader._close_position_with_limit_order(
        position=position, current_price=97.9, reason="stop_loss"
    )
    assert trader._check_symbol_cooldown("SOLUSDT") is False
    # Stage 0 (Task 6): the same close that arms the :3073 cooldown predicate
    # must persist the structured exit_kind via the independent :2883 routing
    # predicate — they stay divergent, but both roads lead here.
    order, _fill_ref = paper_engine.execute_market_order.await_args.args
    assert order.exit_kind == ExitKind.HARD_STOP


# ============================================================================
# H6: max-hold exits arm the cooldown; ensemble entry respects it
# ============================================================================


def _closed_mock():
    closed = MagicMock()
    closed.realized_pnl = Decimal("0.50")
    closed.pnl_percentage = 0.5
    return closed


def _wire_finalize(trader, monkeypatch):
    paper_engine = MagicMock()
    paper_engine.get_total_equity = MagicMock(return_value=BALANCE)
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)
    monkeypatch.setattr("app.auto_trader.get_performance_tracker", lambda: MagicMock())
    trader.kill_switch = MagicMock()
    trader.kill_switch.update_metrics = MagicMock(return_value=None)


@pytest.mark.asyncio
async def test_max_hold_exit_arms_cooldown(trader, monkeypatch):
    """A MAX_HOLD_TIME_EXCEEDED close must arm the same per-symbol cooldown
    as a stop-loss exit (H6: the 2026-08-04 restart sweep closed and
    instantly reopened 4 same-symbol positions at identical prices)."""
    _wire_finalize(trader, monkeypatch)
    position = _stop_position("LONG", "71.0", "69.58")

    assert trader._check_symbol_cooldown("SOLUSDT") is True
    reason = "MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)"
    await trader._finalize_closed_position(position, _closed_mock(), 71.0, reason)
    assert trader._check_symbol_cooldown("SOLUSDT") is False
    # Stage 0 (Task 6): the :3073 cooldown predicate and _exit_kind_for read
    # the same reason string and agree here, even though they're allowed to
    # diverge in general (the enum drops the baked-in "49.0h" detail).
    assert trader._exit_kind_for(reason) == ExitKind.MAX_HOLD


@pytest.mark.asyncio
async def test_take_profit_exit_does_not_arm_cooldown(trader, monkeypatch):
    """Contrast case: a plain take-profit close must NOT block re-entry."""
    _wire_finalize(trader, monkeypatch)
    position = _stop_position("LONG", "71.0", "69.58")

    reason = "Take profit TP3 hit"
    await trader._finalize_closed_position(position, _closed_mock(), 74.0, reason)
    assert trader._check_symbol_cooldown("SOLUSDT") is True
    # Stage 0 (Task 6): confirms the take-profit record is TAKE_PROFIT, not a
    # side effect of the cooldown predicate not matching "loss"/"stop".
    assert trader._exit_kind_for(reason) == ExitKind.TAKE_PROFIT


@pytest.mark.asyncio
async def test_ensemble_entry_blocked_during_cooldown(trader, monkeypatch, instruments_cache):
    """After a max-hold exit armed the cooldown, the ensemble path must not
    re-enter the same symbol."""
    trader._record_sl_hit("SOLUSDT", "MAX_HOLD_TIME_EXCEEDED (49.0h > 48h)")

    paper_engine = _wire_ensemble(
        trader, monkeypatch, price=SOL_PRICE, size_pct=0.10, open_positions=[]
    )

    rejected_before = trader.total_trades_rejected
    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert trader.total_trades_rejected == rejected_before + 1
