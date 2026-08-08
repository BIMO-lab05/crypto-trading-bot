"""
Stage 0: the ensemble path must apply the stop and target its own strategy
computed, and must refuse an inverted pair.

Before this task, ens_signal.stop_loss / take_profit were read exactly twice -
both inside the Telegram notify_trade_open call at auto_trader.py:4550-4551.
The position itself fell through to risk_manager.calculate_stop_loss, i.e. the
flat default_stop_loss_pct=2.0 / default_take_profit_pct=4.0. All 19 live rows
show exactly entry x0.98 and x1.04, while the aggregator was concurrently
emitting per-symbol ATR levels (BNB SL=587.27, BTC SL=63788.76 TP=67092.18).
So the operator got a Telegram message quoting levels the position did not have.

Inversion guard: EnsembleSignal inherits stop_loss/take_profit verbatim from
whichever leg had the largest absolute contribution
(multi_strategy_ensemble.py:277-284), with no check that they sit on the
correct side of entry for the ensemble's chosen action. A weighted-vote BUY
whose dominant leg fired SELL yields an inverted pair. Precedent: the Jan 2026
inverted-R/R bug (380a674).
"""

import pytest

from app.models.enums import SignalAction


@pytest.fixture
def guard():
    from app.auto_trader import AutoTrader

    return AutoTrader._ensemble_stops_are_consistent


def test_valid_long_pair_passes(guard):
    assert guard(SignalAction.BUY, 72.68, 71.22, 75.58) is True


def test_valid_short_pair_passes(guard):
    assert guard(SignalAction.SELL, 602.69, 614.74, 578.58) is True


def test_inverted_long_pair_is_rejected(guard):
    """Stop ABOVE entry on a LONG - the dominant leg fired the other way."""
    assert guard(SignalAction.BUY, 72.68, 75.58, 71.22) is False


def test_inverted_short_pair_is_rejected(guard):
    assert guard(SignalAction.SELL, 602.69, 578.58, 614.74) is False


def test_stop_equal_to_entry_is_rejected(guard):
    """A zero-distance stop makes R undefined and every R-multiple infinite."""
    assert guard(SignalAction.BUY, 72.68, 72.68, 75.58) is False


def test_non_positive_levels_are_rejected(guard):
    assert guard(SignalAction.BUY, 72.68, 0.0, 75.58) is False
    assert guard(SignalAction.BUY, 72.68, 71.22, 0.0) is False


# ============================================================================
# Integration coverage: the unit tests above only prove the guard's arithmetic
# in isolation. They say nothing about whether _check_and_trade_ensemble
# actually reaches position_mgr.set_position_stops on a filled order. Harness
# mirrors tests/test_sizing_caps_phase1.py, which already exercises this same
# call path (gates, quantity snapping) successfully end-to-end.
# ============================================================================

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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
from app.services.instruments_cache import InstrumentSpec  # noqa: E402

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
def trader(monkeypatch):
    from app.auto_trader import AutoTrader
    from app.trading_enhancements.portfolio_heat import (
        reset_portfolio_heat_manager,
    )

    # PortfolioHeatManager is a process-global singleton that earlier tests
    # leave positions in. The ensemble path consults it since Stage 0 Task 9.
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


def _wire(trader, monkeypatch, *, stop_loss, take_profit, action=SignalAction.BUY):
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
    filled = MagicMock()
    filled.status = OrderStatus.FILLED
    filled.position_id = uuid4()
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ens_signal = MagicMock()
    ens_signal.action = action
    ens_signal.confidence = 0.30
    ens_signal.position_size_pct = 0.10
    ens_signal.stop_loss = stop_loss
    ens_signal.take_profit = take_profit
    ens_signal.leg_actions = {"simple_rsi": action.value}
    ens_signal.leg_contributions = {}

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=ens_signal)

    # Patch the module OBJECT, not the dotted string (see
    # test_sizing_caps_phase1.py for why): conftest's autouse
    # patch.dict("sys.modules") restore evicts modules first imported during
    # a test, and string-target monkeypatch then patches a module object that
    # auto_trader's deferred import no longer resolves.
    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)

    return paper_engine, position_mgr, filled


@pytest.mark.asyncio
async def test_valid_pair_applies_stops_after_fill(trader, monkeypatch):
    paper_engine, position_mgr, filled = _wire(
        trader,
        monkeypatch,
        stop_loss=SOL_PRICE * 0.98,
        take_profit=SOL_PRICE * 1.04,
    )

    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    position_mgr.set_position_stops.assert_called_once()
    _, kwargs = position_mgr.set_position_stops.call_args
    assert kwargs["position_id"] == filled.position_id
    assert kwargs["stop_loss"] == Decimal(str(SOL_PRICE * 0.98))
    assert kwargs["take_profit"] == Decimal(str(SOL_PRICE * 1.04))


@pytest.mark.asyncio
async def test_inverted_pair_does_not_apply_stops(trader, monkeypatch, caplog):
    paper_engine, position_mgr, _filled = _wire(
        trader,
        monkeypatch,
        stop_loss=SOL_PRICE * 1.04,
        take_profit=SOL_PRICE * 0.98,
    )

    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_awaited_once()
    position_mgr.set_position_stops.assert_not_called()
