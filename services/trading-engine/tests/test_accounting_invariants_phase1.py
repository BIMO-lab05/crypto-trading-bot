"""
Accounting invariants — Phase 1 (AUDIT.md workstream B, 2026-08-04).

Covers the four confirmed accounting defects:
  * H7a: positions.realized_pnl was persisted GROSS of commissions
         -> must now be NET of entry + exit legs.
  * H7b: portfolios.realized_pnl was OVERWRITTEN with an in-memory total that
         resets on restart -> must now be ACCUMULATED via per-close deltas.
  * H5:  partial exits persisted neither the reduced quantity nor the
         incremental realized P&L -> restarts resurrected sold quantity
         (one position's close P&L overstated by exactly $1.7029).
  * Fee rate: paper_commission_pct default was 0.1 (~1.8x Bybit linear taker)
         -> must be 0.055.
Plus the task-5 config hardening: containerized boots must refuse to start
when any of the five capital/risk env vars is absent.

All monetary expectations are computed from the engine's own Settings
(commission rate, leverage) — no account-size literals.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

import app.config as config_module
import app.paper_trading as paper_trading_module
from app.config import Settings
from app.models import OrderCreate, OrderSide, OrderType
from app.paper_trading import PaperTradingEngine
from app.position_manager import PositionManager


async def _drain_tasks():
    """Let fire-and-forget persistence tasks run to completion."""
    for _ in range(10):
        await asyncio.sleep(0)


class _IdentitySlippage:
    """Slippage model that fills at the reference price (deterministic math)."""

    def fill_price(self, symbol, side, price):
        return price

    def describe(self):
        return "identity (test)"


def _mock_position_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.update_price = AsyncMock()
    repo.close = AsyncMock()
    repo.record_reduction = AsyncMock()
    repo.record_scale_in = AsyncMock()
    repo.get_open_positions = AsyncMock(return_value=[])
    return repo


def _mock_portfolio_repo():
    repo = MagicMock()
    repo.record_position_close = AsyncMock()
    repo.update_balance = AsyncMock()
    repo.get_or_create = AsyncMock()
    return repo


def _mock_risk_manager():
    rm = MagicMock()
    rm.calculate_stop_loss = MagicMock(return_value=Decimal("0.00000001"))
    rm.calculate_take_profit = MagicMock(return_value=Decimal("99999999"))
    rm.update_daily_pnl = MagicMock()
    return rm


@pytest.fixture
def stack():
    """Real PositionManager + real PaperTradingEngine over mocked repos."""
    position_repo = _mock_position_repo()
    portfolio_repo = _mock_portfolio_repo()
    trade_repo = MagicMock()
    trade_repo.log_trade = AsyncMock()
    risk_manager = _mock_risk_manager()

    with (
        patch("app.position_manager.get_risk_manager", return_value=risk_manager),
        patch(
            "app.position_manager.get_position_repository",
            return_value=position_repo,
        ),
        patch(
            "app.position_manager.get_portfolio_repository",
            return_value=portfolio_repo,
        ),
    ):
        manager = PositionManager()

    with (
        patch("app.paper_trading.get_position_manager", return_value=manager),
        patch("app.paper_trading.get_risk_manager", return_value=risk_manager),
        patch("app.paper_trading.get_trade_repository", return_value=trade_repo),
        patch(
            "app.paper_trading.get_portfolio_repository",
            return_value=portfolio_repo,
        ),
    ):
        engine = PaperTradingEngine()
    engine.slippage = _IdentitySlippage()

    # close_position() resolves cash via the module-level singleton; bind it
    # to THIS engine so the portfolio write carries this test's ledger.
    saved_engine = paper_trading_module._paper_engine
    paper_trading_module._paper_engine = engine

    yield SimpleNamespace(
        engine=engine,
        manager=manager,
        position_repo=position_repo,
        portfolio_repo=portfolio_repo,
        trade_repo=trade_repo,
        risk_manager=risk_manager,
    )

    paper_trading_module._paper_engine = saved_engine


def _buy(symbol, qty, position_id=None):
    return OrderCreate(
        symbol=symbol,
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        quantity=Decimal(qty),
        position_id=position_id,
    )


def _sell(symbol, qty, position_id=None, reduce_only=False):
    return OrderCreate(
        symbol=symbol,
        side=OrderSide.SELL,
        type=OrderType.MARKET,
        quantity=Decimal(qty),
        position_id=position_id,
        reduce_only=reduce_only,
    )


# =============================================================================
# H7a — realized P&L persisted NET of both legs' commissions
# =============================================================================


async def test_close_persists_net_realized_pnl_and_fees(stack):
    engine = stack.engine
    pct = engine.commission_pct  # Decimal fraction per side
    leverage = Decimal(str(engine.settings.default_leverage))

    order, err = await engine.execute_market_order(
        _buy("ETHUSDT", "0.01"), Decimal("2000")
    )
    assert err is None
    entry_fee = Decimal("2000") * Decimal("0.01") * pct

    order2, err2 = await engine.execute_market_order(
        _sell("ETHUSDT", "0.01", position_id=order.position_id, reduce_only=True),
        Decimal("2100"),
    )
    assert err2 is None
    exit_fee = Decimal("2100") * Decimal("0.01") * pct
    gross = (Decimal("2100") - Decimal("2000")) * Decimal("0.01")
    expected_net = gross - entry_fee - exit_fee

    closed = stack.manager.get_position(order.position_id)
    assert closed.realized_pnl == expected_net, (
        f"in-memory realized_pnl must be net of both fees: "
        f"{closed.realized_pnl} != {expected_net}"
    )

    await _drain_tasks()

    # Persisted position row: net P&L, exit fee, remaining_quantity zeroed
    stack.position_repo.close.assert_awaited_once()
    close_kwargs = stack.position_repo.close.await_args.kwargs
    close_args = stack.position_repo.close.await_args.args
    assert close_args[2] == expected_net  # realized_pnl positional
    assert close_kwargs["exit_fee"] == exit_fee

    # Entry fee persisted at create
    stack.position_repo.create.assert_awaited_once()
    assert stack.position_repo.create.await_args.kwargs["entry_fee"] == entry_fee

    # Cash ledger check: open debits margin+entry fee, close credits
    # margin+gross-exit fee, so Δcash over the round trip == net P&L.
    assert engine.balance == engine.initial_balance + expected_net

    # The close-leg trade row records the same net figure
    close_leg_calls = [
        c
        for c in stack.trade_repo.log_trade.await_args_list
        if c.kwargs.get("realized_pnl") is not None
    ]
    assert len(close_leg_calls) == 1
    assert close_leg_calls[0].kwargs["realized_pnl"] == expected_net
    assert leverage > 0  # silence unused warning; leverage exercised above


# =============================================================================
# H7b — portfolios.realized_pnl accumulates (delta-based), never overwrites
# =============================================================================


async def test_portfolio_realized_pnl_accumulates_across_closes(stack):
    engine = stack.engine
    pct = engine.commission_pct

    nets = []
    for symbol, entry, exit_ in [
        ("ETHUSDT", Decimal("2000"), Decimal("2100")),
        ("SOLUSDT", Decimal("70"), Decimal("69")),
    ]:
        order, err = await engine.execute_market_order(_buy(symbol, "0.01"), entry)
        assert err is None
        _, err2 = await engine.execute_market_order(
            _sell(symbol, "0.01", position_id=order.position_id, reduce_only=True),
            exit_,
        )
        assert err2 is None
        gross = (exit_ - entry) * Decimal("0.01")
        nets.append(
            gross - entry * Decimal("0.01") * pct - exit_ * Decimal("0.01") * pct
        )

    await _drain_tasks()

    # The overwriting writer must not be used on the close path at all
    stack.portfolio_repo.update_balance.assert_not_awaited()

    calls = stack.portfolio_repo.record_position_close.await_args_list
    assert len(calls) == 2
    deltas = [c.kwargs["realized_pnl_delta"] for c in calls]
    # Each call carries THAT position's net P&L (a delta, not a running total)
    assert deltas == nets

    # Accumulation invariant: simulated SQL ledger (start + sum of deltas)
    # equals the sum of closed positions' net realized P&L.
    ledger_start = Decimal("0")
    ledger = ledger_start + sum(deltas)
    closed_net_sum = sum(p.realized_pnl for p in stack.manager.get_closed_positions())
    assert ledger == closed_net_sum

    # And the deltas survive a restart conceptually: they do not depend on
    # in-memory history (each equals its own position's row value).
    for delta, pos in zip(deltas, stack.manager.get_closed_positions()):
        assert delta == pos.realized_pnl


async def test_close_persists_position_before_portfolio_ledger(stack):
    """RES-03 (2026-08-16): the CLOSED row must land BEFORE the aggregate runs.

    record_position_close now SUMs positions.unrealized_pnl over rows whose
    status is OPEN. The two persists used to be independent create_task()s in
    separate sessions with no ordering guarantee — if the portfolio write won
    the race, the just-closed position was still OPEN carrying its last stale
    tick value, which landed in unrealized_pnl / total_value / total_pnl ON TOP
    of the realized delta just accumulated. A nondeterministic double-count.
    """
    engine = stack.engine
    write_order = []

    async def _mark_close(*args, **kwargs):
        # Yield mid-write, which is what a real DB round trip does. Under the
        # old shape (two independent create_task()s) this hands control to the
        # portfolio task, which then completes FIRST and reads a still-OPEN
        # row. Under the chained shape the ledger coroutine is not even
        # scheduled until close() has returned, so no yield can reorder them.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        write_order.append("close")

    async def _mark_ledger(*args, **kwargs):
        write_order.append("ledger")

    stack.position_repo.close.side_effect = _mark_close
    stack.portfolio_repo.record_position_close.side_effect = _mark_ledger

    order, err = await engine.execute_market_order(
        _buy("ETHUSDT", "0.01"), Decimal("2000")
    )
    assert err is None
    _, err2 = await engine.execute_market_order(
        _sell("ETHUSDT", "0.01", position_id=order.position_id, reduce_only=True),
        Decimal("2100"),
    )
    assert err2 is None

    await _drain_tasks()

    assert write_order == ["close", "ledger"], (
        "position close must be persisted before the portfolio aggregate is "
        f"computed; got {write_order}"
    )


# =============================================================================
# H5 — partial exits persist remaining_quantity + incremental net P&L
# =============================================================================


async def test_reduce_position_persists_remaining_and_incremental_net(stack):
    engine = stack.engine
    pct = engine.commission_pct

    order, err = await engine.execute_market_order(
        _buy("SOLUSDT", "1.0"), Decimal("70")
    )
    assert err is None
    entry_fee = Decimal("70") * Decimal("1.0") * pct

    _, err2 = await engine.execute_market_order(
        _sell("SOLUSDT", "0.4", position_id=order.position_id, reduce_only=True),
        Decimal("71"),
    )
    assert err2 is None

    gross_leg = (Decimal("71") - Decimal("70")) * Decimal("0.4")
    exit_fee_leg = Decimal("71") * Decimal("0.4") * pct
    entry_fee_portion = entry_fee * Decimal("0.4") / Decimal("1.0")
    expected_net_leg = gross_leg - exit_fee_leg - entry_fee_portion

    pos = stack.manager.get_position(order.position_id)
    assert pos.remaining_quantity == Decimal("0.6")
    assert pos.realized_pnl == expected_net_leg

    await _drain_tasks()

    stack.position_repo.record_reduction.assert_awaited_once()
    kwargs = stack.position_repo.record_reduction.await_args.kwargs
    assert kwargs["remaining_quantity"] == Decimal("0.6")
    assert kwargs["realized_pnl"] == expected_net_leg
    assert kwargs["exit_fee"] == exit_fee_leg

    # Portfolio realized-P&L ledger accumulates at CLOSE only — a partial
    # exit must not push a delta (it reaches the ledger via the final close).
    stack.portfolio_repo.record_position_close.assert_not_awaited()


async def test_remaining_quantity_survives_simulated_reload(stack):
    """H5 kill test: reload from DB, then close — sold quantity must NOT
    resurrect and the close must realize P&L on the persisted remainder."""
    pct = stack.engine.commission_pct
    pid = uuid4()
    entry_fee = Decimal("70") * Decimal("1.0") * pct  # fee paid at open
    prior_exit_fee = Decimal("71") * Decimal("0.4") * pct
    prior_net = (
        (Decimal("71") - Decimal("70")) * Decimal("0.4")
        - prior_exit_fee
        - entry_fee * Decimal("0.4")
    )

    db_row = SimpleNamespace(
        position_id=pid,
        symbol="SOLUSDT",
        side="LONG",
        entry_price=Decimal("70"),
        quantity=Decimal("1.0"),
        remaining_quantity=Decimal("0.6"),
        current_price=Decimal("71"),
        stop_loss=None,
        take_profit=None,
        strategy=None,
        opened_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        realized_pnl=prior_net,
        entry_fee=entry_fee,
        exit_fee=prior_exit_fee,
        # Stage 0 (migration 008, 2026-08-07): load_positions_from_db now
        # reads these unconditionally. A SimpleNamespace has no fallback
        # attribute like MagicMock, so a fixture missing them raises
        # AttributeError inside the try/except and silently reports 0 loaded.
        posted_margin=Decimal("42"),
        leverage=Decimal("1"),
    )
    stack.position_repo.get_open_positions = AsyncMock(return_value=[db_row])

    # Simulated restart: fresh manager, positions rebuilt from the DB
    with (
        patch(
            "app.position_manager.get_risk_manager",
            return_value=stack.risk_manager,
        ),
        patch(
            "app.position_manager.get_position_repository",
            return_value=stack.position_repo,
        ),
        patch(
            "app.position_manager.get_portfolio_repository",
            return_value=stack.portfolio_repo,
        ),
    ):
        reloaded_manager = PositionManager()
    loaded = await reloaded_manager.load_positions_from_db()
    assert loaded == 1

    reloaded = reloaded_manager.get_position(pid)
    assert reloaded.remaining_quantity == Decimal("0.6"), (
        "restart resurrected sold quantity (AUDIT H5)"
    )
    assert reloaded_manager._entry_fees[pid] == entry_fee
    assert reloaded_manager._exit_fees[pid] == prior_exit_fee

    # Bind a fresh engine to the reloaded manager and close with an order
    # for the ORIGINAL full quantity — the fill must clamp to the remainder.
    with (
        patch(
            "app.paper_trading.get_position_manager",
            return_value=reloaded_manager,
        ),
        patch(
            "app.paper_trading.get_risk_manager",
            return_value=stack.risk_manager,
        ),
        patch(
            "app.paper_trading.get_trade_repository",
            return_value=stack.trade_repo,
        ),
        patch(
            "app.paper_trading.get_portfolio_repository",
            return_value=stack.portfolio_repo,
        ),
    ):
        engine2 = PaperTradingEngine()
    engine2.slippage = _IdentitySlippage()
    saved = paper_trading_module._paper_engine
    paper_trading_module._paper_engine = engine2
    try:
        order, err = await engine2.execute_market_order(
            _sell("SOLUSDT", "1.0", position_id=pid, reduce_only=True),
            Decimal("72"),
        )
        assert err is None
        assert order.filled_quantity == Decimal("0.6"), (
            "close consumed resurrected quantity instead of the persisted remainder"
        )

        final_exit_fee_leg = Decimal("72") * Decimal("0.6") * pct
        final_net_leg = (
            (Decimal("72") - Decimal("70")) * Decimal("0.6")
            - final_exit_fee_leg
            - entry_fee * Decimal("0.6")
        )
        closed = reloaded_manager.get_position(pid)
        assert closed.realized_pnl == prior_net + final_net_leg

        await _drain_tasks()
        close_args = stack.position_repo.close.await_args
        assert close_args.args[2] == prior_net + final_net_leg
        assert close_args.kwargs["exit_fee"] == prior_exit_fee + final_exit_fee_leg
        # Portfolio delta at close = the position's TOTAL net (partials
        # included), sourced from the persisted row — restart-proof.
        delta = stack.portfolio_repo.record_position_close.await_args.kwargs[
            "realized_pnl_delta"
        ]
        assert delta == prior_net + final_net_leg
    finally:
        paper_trading_module._paper_engine = saved


# =============================================================================
# I16 — entry-fee attribution is conserved when a scale-in follows a partial
# exit. _entry_fee_portion divided by position.quantity, which scale_in
# increments, so part of the entry fee was debited from cash but never reached
# reported P&L: the cash ledger and reported P&L silently diverged.
# =============================================================================


async def test_entry_fee_fully_attributed_across_scale_in_after_partial_exit(stack):
    """Worked example from the review, scaled to the real commission rate.

    open 10 -> partial-exit 5 -> scale in 10 -> close 15. Every dollar of entry
    commission the cash ledger paid must reach reported P&L exactly once.

    Prices are chosen so the weighted-average entry stays exact in Decimal:
    (5 x 1.00 + 10 x 2.50) / 15 == 2.00, and the margin posted over the two
    entry legs exactly matches the margin returned over the two exit legs.
    """
    engine = stack.engine
    pct = engine.commission_pct
    opening_balance = engine.balance

    # ---- leg 1: open 10 @ 1.00 ------------------------------------------
    order, err = await engine.execute_market_order(
        _buy("ADAUSDT", "10"), Decimal("1.00")
    )
    assert err is None
    pid = order.position_id
    entry_fee_1 = Decimal("1.00") * Decimal("10") * pct

    # ---- leg 2: partial exit 5 @ 1.20 -----------------------------------
    _, err = await engine.execute_market_order(
        _sell("ADAUSDT", "5", position_id=pid, reduce_only=True), Decimal("1.20")
    )
    assert err is None
    exit_fee_1 = Decimal("1.20") * Decimal("5") * pct
    gross_1 = (Decimal("1.20") - Decimal("1.00")) * Decimal("5")

    # ---- leg 3: scale in 10 @ 2.50 --------------------------------------
    _, err = await engine.execute_market_order(
        _buy("ADAUSDT", "10", position_id=pid), Decimal("2.50")
    )
    assert err is None
    entry_fee_2 = Decimal("2.50") * Decimal("10") * pct

    position = stack.manager.get_position(pid)
    assert position.remaining_quantity == Decimal("15")
    assert position.entry_price == Decimal("2.00"), (
        "weighted-average entry drifted; the rest of this test's arithmetic "
        "assumes it is exact"
    )

    # ---- leg 4: close the remaining 15 @ 3.00 ---------------------------
    _, err = await engine.execute_market_order(
        _sell("ADAUSDT", "15", position_id=pid, reduce_only=True), Decimal("3.00")
    )
    assert err is None
    exit_fee_2 = Decimal("3.00") * Decimal("15") * pct
    gross_2 = (Decimal("3.00") - Decimal("2.00")) * Decimal("15")

    entry_fee_paid = entry_fee_1 + entry_fee_2

    # (1) Cash-ledger identity. Margin nets to zero across the four legs, so
    # the change in cash must equal the reported net P&L exactly. This is the
    # assertion the defect breaks: cash paid both entry fees, reported P&L
    # only ever saw part of the second one.
    closed = stack.manager.get_position(pid)
    assert engine.balance - opening_balance == closed.realized_pnl, (
        f"cash moved {engine.balance - opening_balance} but P&L reported "
        f"{closed.realized_pnl} — the ledgers have diverged by "
        f"{closed.realized_pnl - (engine.balance - opening_balance)}"
    )

    # (2) Reported net P&L is gross minus every fee, both legs of both entries.
    expected_net = (
        gross_1 + gross_2 - exit_fee_1 - exit_fee_2 - entry_fee_1 - entry_fee_2
    )
    assert closed.realized_pnl == expected_net

    # (3) Stated directly: every unit of entry commission paid was attributed
    # to some exit leg.
    assert stack.manager._entry_fees[pid] == entry_fee_paid
    assert stack.manager._entry_fees_consumed[pid] == entry_fee_paid, (
        f"entry fee attributed to exits "
        f"({stack.manager._entry_fees_consumed[pid]}) != entry fee paid "
        f"({entry_fee_paid})"
    )


async def test_entry_fee_attribution_unchanged_without_scale_in(stack):
    """Exactness guard for the common case: with no scale-in the attribution
    is still a simple pro-rata split of the single entry fee."""
    engine = stack.engine
    pct = engine.commission_pct

    order, err = await engine.execute_market_order(
        _buy("SOLUSDT", "1.0"), Decimal("70")
    )
    assert err is None
    pid = order.position_id
    entry_fee = Decimal("70") * Decimal("1.0") * pct

    _, err = await engine.execute_market_order(
        _sell("SOLUSDT", "0.4", position_id=pid, reduce_only=True), Decimal("71")
    )
    assert err is None
    assert stack.manager._entry_fees_consumed[pid] == entry_fee * Decimal("0.4")

    _, err = await engine.execute_market_order(
        _sell("SOLUSDT", "0.6", position_id=pid, reduce_only=True), Decimal("72")
    )
    assert err is None
    assert stack.manager._entry_fees_consumed[pid] == entry_fee


# =============================================================================
# Fee rate — Bybit linear taker
# =============================================================================


def test_paper_commission_default_is_bybit_linear_taker():
    assert Settings.model_fields["paper_commission_pct"].default == 0.055, (
        "paper_commission_pct default must be 0.055 (Bybit linear-perp taker, "
        "AUDIT.md 6.2 — the old 0.1 over-charged fees ~1.8x)"
    )


# =============================================================================
# Task 5 — containerized boot refuses to start without capital env vars
# =============================================================================


class TestCapitalEnvBootValidation:
    def test_missing_env_raises_in_container(self, monkeypatch):
        monkeypatch.setattr(config_module, "_running_in_container", lambda: True)
        for key in config_module.REQUIRED_CAPITAL_ENV_VARS:
            monkeypatch.delenv(key, raising=False)

        with pytest.raises(RuntimeError) as exc:
            config_module.assert_capital_env_present()
        for key in config_module.REQUIRED_CAPITAL_ENV_VARS:
            assert key in str(exc.value)

        # And the guard is wired into settings construction
        saved = config_module._settings
        try:
            with pytest.raises(RuntimeError):
                config_module.reload_settings()
        finally:
            config_module._settings = saved

    def test_partial_env_names_only_missing_keys(self, monkeypatch):
        monkeypatch.setattr(config_module, "_running_in_container", lambda: True)
        for key in config_module.REQUIRED_CAPITAL_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("PAPER_INITIAL_BALANCE", "100.0")

        with pytest.raises(RuntimeError) as exc:
            config_module.assert_capital_env_present()
        assert "PAPER_INITIAL_BALANCE" not in str(exc.value)
        assert "MAX_RISK_PER_TRADE" in str(exc.value)

    def test_full_env_passes(self, monkeypatch):
        monkeypatch.setattr(config_module, "_running_in_container", lambda: True)
        monkeypatch.setenv("PAPER_INITIAL_BALANCE", "100.0")
        monkeypatch.setenv("MAX_RISK_PER_TRADE", "0.10")
        monkeypatch.setenv("MAX_DAILY_LOSS_PCT", "12.0")
        monkeypatch.setenv("MAX_POSITION_SIZE_PCT", "10.0")
        monkeypatch.setenv("MAX_TOTAL_EXPOSURE_PCT", "80.0")
        config_module.assert_capital_env_present()  # must not raise

    def test_host_runs_are_exempt(self, monkeypatch):
        monkeypatch.setattr(config_module, "_running_in_container", lambda: False)
        for key in config_module.REQUIRED_CAPITAL_ENV_VARS:
            monkeypatch.delenv(key, raising=False)
        saved = config_module._settings
        try:
            settings = config_module.reload_settings()  # must not raise
            assert settings.paper_initial_balance == 100.0
        finally:
            config_module._settings = saved
