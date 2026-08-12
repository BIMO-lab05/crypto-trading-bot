"""
ADR-015 weight adaptation must actually run.

The ensemble entry path tagged the freshly-opened position with its per-leg
contributions by assigning `position.metadata` — a field app/models/position.py
does not declare, on a pydantic model without `extra="allow"`. Every write
raised ValueError into a `logger.debug` handler, so nothing surfaced, and
MultiStrategyEnsemble.record_trade_outcome had no caller anywhere in app/.
Leg weights have therefore been frozen at their initial values since the
ensemble shipped: a leg that loses every trade keeps its vote.

The old block was additionally unreachable in every existing harness (it read
`position_mgr.get_open_positions()` a second time post-fill, which the stubs
return empty), which is why no test caught it.

Attribution now lives on the trader, keyed by position id, and is popped in
_finalize_closed_position — the one place every close path converges.

Scope note (2026-08-12): these tests pin what the TRADER sends. The consumer,
MultiStrategyEnsemble.record_trade_outcome, compares the sign of a leg's
contribution (+1 = BUY vote) against the sign of realized P&L — which is
already direction-adjusted, so a winning SHORT arrives positive against a
negative contribution and the leg is credited with a loss. That inversion is a
separate defect in a separate file and is deliberately not touched here.
"""

import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import uuid4

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py, never a literal.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import so deferred imports inside the trade path find the modules already
# in sys.modules (a lazy import during a test re-runs prometheus Counter
# registration and trips "Duplicated timeseries in CollectorRegistry").
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from app.models import OrderStatus  # noqa: E402
from app.models.enums import SignalAction  # noqa: E402
from app.services.instruments_cache import InstrumentSpec  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))
SOL_PRICE = 71.0

# Non-empty on purpose: an empty contributions dict makes the store assertion
# pass trivially while the learning call never fires.
LEG_CONTRIBUTIONS = {"simple_rsi": 0.42, "mean_reversion": -0.10, "multi_ind": 0.0}

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


def _stub_ensemble(monkeypatch):
    """Patch the module OBJECT, not the dotted string — see
    tests/test_ensemble_stops_applied.py for why."""
    import app.strategies.multi_strategy_ensemble as ens_mod

    ensemble = MagicMock()
    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)
    return ensemble


def _wire_entry(trader, monkeypatch):
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

    opened_position = SimpleNamespace(
        symbol="SOLUSDT",
        stop_loss=Decimal(str(SOL_PRICE * 0.96)),
        take_profit=Decimal(str(SOL_PRICE * 1.09)),
    )

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])
    position_mgr.get_position = MagicMock(return_value=opened_position)
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ens_signal = MagicMock()
    ens_signal.action = SignalAction.BUY
    ens_signal.confidence = 0.30
    ens_signal.position_size_pct = 0.10
    ens_signal.stop_loss = SOL_PRICE * 0.96
    ens_signal.take_profit = SOL_PRICE * 1.09
    ens_signal.leg_actions = {"simple_rsi": SignalAction.BUY.value}
    ens_signal.leg_contributions = dict(LEG_CONTRIBUTIONS)

    ensemble = _stub_ensemble(monkeypatch)
    ensemble.generate_signal = MagicMock(return_value=ens_signal)

    return paper_engine, filled, ensemble


def _wire_close(trader, monkeypatch):
    paper_engine = MagicMock()
    paper_engine.get_total_equity = MagicMock(return_value=BALANCE)
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)
    monkeypatch.setattr("app.auto_trader.get_performance_tracker", lambda: MagicMock())
    trader.kill_switch = MagicMock()
    trader.kill_switch.update_metrics = MagicMock(return_value=None)


def _position(position_id):
    position = Mock()
    position.id = position_id
    position.symbol = "SOLUSDT"
    position.side = Mock(value="LONG")
    position.entry_price = Decimal(str(SOL_PRICE))
    position.quantity = Decimal("0.1")
    return position


def _closed(pnl: str):
    closed = Mock()
    closed.realized_pnl = Decimal(pnl)
    closed.pnl_percentage = float(Decimal(pnl) / Decimal(str(SOL_PRICE)) * 100)
    return closed


@pytest.mark.asyncio
async def test_fill_stores_leg_attribution_on_the_trader(trader, monkeypatch):
    _paper_engine, filled, ensemble = _wire_entry(trader, monkeypatch)

    await trader._check_and_trade_ensemble("SOLUSDT")

    stored = trader._ensemble_attribution[filled.position_id]
    assert stored == LEG_CONTRIBUTIONS
    # A copy, not the signal's own dict: the ensemble rebuilds contributions
    # every signal, and the close can be hours later.
    assert stored is not ensemble.generate_signal.return_value.leg_contributions


@pytest.mark.asyncio
@pytest.mark.parametrize("pnl", ["-0.50", "0.50"])
async def test_close_feeds_record_trade_outcome_with_signed_pnl(
    trader, monkeypatch, pnl
):
    """The sign is the whole payload: record_trade_outcome credits a leg whose
    contribution matched the sign of P&L. Passing abs(pnl) trains the weights
    backwards — the SHORT-close-inversion failure mode."""
    ensemble = _stub_ensemble(monkeypatch)
    _wire_close(trader, monkeypatch)

    position_id = uuid4()
    trader._ensemble_attribution[position_id] = dict(LEG_CONTRIBUTIONS)

    await trader._finalize_closed_position(
        _position(position_id), _closed(pnl), SOL_PRICE, "take_profit"
    )

    ensemble.record_trade_outcome.assert_called_once()
    args, kwargs = ensemble.record_trade_outcome.call_args
    passed = {**dict(zip(("leg_contributions", "pnl"), args)), **kwargs}
    assert passed["leg_contributions"] == LEG_CONTRIBUTIONS
    assert passed["pnl"] == pytest.approx(float(Decimal(pnl)))
    assert (passed["pnl"] < 0) is (Decimal(pnl) < 0)

    # Bounded: the entry is consumed by the close it belongs to.
    assert position_id not in trader._ensemble_attribution


@pytest.mark.asyncio
async def test_close_without_attribution_is_a_no_op(trader, monkeypatch):
    """Non-ensemble closes (and closes after a restart) must not raise or
    invent an outcome for legs that never voted."""
    ensemble = _stub_ensemble(monkeypatch)
    _wire_close(trader, monkeypatch)

    await trader._finalize_closed_position(
        _position(uuid4()), _closed("0.50"), SOL_PRICE, "take_profit"
    )

    ensemble.record_trade_outcome.assert_not_called()
