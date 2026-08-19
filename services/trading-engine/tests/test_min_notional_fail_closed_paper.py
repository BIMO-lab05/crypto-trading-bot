"""
Min-notional gate must fail CLOSED in PAPER, and stay fail-open in LIVE.

Review finding I12. When the instruments cache cannot supply a spec (import
error, connector unreachable, symbol never refreshed) the gate returned
``(True, None)`` in every mode. In LIVE that is defensible — Bybit rejects the
order itself, so refusing to trade because a metadata service is down would be
the worse failure mode. In PAPER nothing downstream re-checks, so the cold-cache
window (engine startup, which is exactly when the first cycles run) let through
precisely the trade the gate exists to prevent, and the paper series then
measured an account that could not exist on the venue.

The reject is labeled ``"spec_unavailable"`` — a distinct reason from
``min_qty`` / ``min_notional`` so the Prometheus series separates "we know it is
too small" from "we cannot tell". Quantities are never clamped up.

Host-run test: the account size comes from shared/account.py, never a literal.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py. conftest puts <repo>/shared on sys.path for the database
# package; `shared.account` needs the repo root itself.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import app.main / app.core.metrics so the deferred imports inside
# _passes_min_notional find the modules already in sys.modules (importing
# lazily during a test re-runs prometheus Counter registration and trips
# "Duplicated timeseries in CollectorRegistry").
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from app.auto_trader import AutoTrader  # noqa: E402
from app.models import OrderStatus  # noqa: E402
from app.models.enums import SignalAction  # noqa: E402
from app.services.instruments_cache import InstrumentSpec  # noqa: E402

BALANCE = Decimal(str(ACCOUNT_EQUITY_USD))
SOL_PRICE = 71.0


class _ColdCache:
    """Cache that has no spec for the symbol (connector outage at boot)."""

    def __init__(self):
        self.calls: list[str] = []

    async def get(self, symbol: str) -> Optional[InstrumentSpec]:
        self.calls.append(symbol)
        return None


class _RaisingCache:
    """Cache whose get() blows up (connector unreachable mid-flight)."""

    def __init__(self):
        self.calls: list[str] = []

    async def get(self, symbol: str) -> Optional[InstrumentSpec]:
        self.calls.append(symbol)
        raise RuntimeError("connector unreachable")


@pytest.fixture
def trader(monkeypatch):
    t = AutoTrader(symbols=["SOLUSDT"])
    monkeypatch.setattr(t.settings, "trading_mode", "PAPER", raising=False)
    monkeypatch.setattr(t.settings, "max_position_size_pct", 10.0, raising=False)
    monkeypatch.setattr(t.settings, "max_total_exposure_pct", 80.0, raising=False)
    t.notification_client = MagicMock()
    t.notification_client.notify_trade_open = AsyncMock()
    t.notification_client.notify_trade_close = AsyncMock()
    return t


def _counter(reason: str, symbol: str = "SOLUSDT"):
    import app.core.metrics as metrics

    return metrics.trades_rejected_min_notional_total.labels(
        symbol=symbol, reason=reason
    )


# ============================================================================
# PAPER: every route to "no spec" must REJECT
# ============================================================================


@pytest.mark.asyncio
async def test_paper_rejects_when_no_spec_cached(trader, monkeypatch):
    cache = _ColdCache()
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)
    before = _counter("spec_unavailable")._value.get()  # type: ignore[attr-defined]

    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=BALANCE,
    )

    assert ok is False
    assert reason == "spec_unavailable"
    assert cache.calls == ["SOLUSDT"]
    after = _counter("spec_unavailable")._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


@pytest.mark.asyncio
async def test_paper_rejects_when_cache_get_raises(trader, monkeypatch):
    cache = _RaisingCache()
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=BALANCE,
    )

    assert ok is False
    assert reason == "spec_unavailable"


@pytest.mark.asyncio
async def test_paper_rejects_when_cache_import_fails(trader, monkeypatch):
    """`from app.main import get_instruments_cache` raising must not open the
    gate in PAPER either."""
    monkeypatch.delattr(app.main, "get_instruments_cache", raising=True)

    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=BALANCE,
    )

    assert ok is False
    assert reason == "spec_unavailable"


# ============================================================================
# LIVE: fail-open preserved (Bybit is the backstop)
# ============================================================================


@pytest.mark.asyncio
async def test_live_still_fails_open_when_no_spec_cached(trader, monkeypatch):
    monkeypatch.setattr(trader.settings, "trading_mode", "LIVE", raising=False)
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: _ColdCache())

    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=BALANCE,
    )

    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_live_still_fails_open_when_cache_get_raises(trader, monkeypatch):
    monkeypatch.setattr(trader.settings, "trading_mode", "LIVE", raising=False)
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: _RaisingCache())

    ok, reason = await trader._passes_min_notional(
        symbol="SOLUSDT",
        quantity=Decimal("0.1"),
        price=Decimal(str(SOL_PRICE)),
        balance=BALANCE,
    )

    assert ok is True
    assert reason is None


# ============================================================================
# End-to-end: the cold-cache startup window places no paper order
# ============================================================================


def _ens_signal(price: float):
    sig = MagicMock()
    sig.action = SignalAction.BUY
    sig.confidence = 0.30
    sig.position_size_pct = 0.10
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


@pytest.mark.asyncio
async def test_ensemble_places_no_paper_order_while_cache_is_cold(trader, monkeypatch):
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: _ColdCache())

    risk_mgr = MagicMock()
    risk_mgr.should_halt_trading = MagicMock(return_value=False)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)

    aggregator = MagicMock()
    aggregator.get_trading_signal_multi_timeframe = AsyncMock(
        return_value=_base_signal(SOL_PRICE)
    )

    async def _fake_get_aggregator():
        return aggregator

    monkeypatch.setattr("app.auto_trader.get_aggregator", _fake_get_aggregator)

    paper_engine = MagicMock()
    paper_engine.get_balance = MagicMock(return_value=BALANCE)
    filled = MagicMock()
    filled.status = OrderStatus.FILLED
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))
    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)

    ensemble = MagicMock()
    ensemble.generate_signal = MagicMock(return_value=_ens_signal(SOL_PRICE))
    import app.strategies.multi_strategy_ensemble as ens_mod

    monkeypatch.setattr(ens_mod, "get_ensemble", lambda: ensemble)

    rejected_before = trader.total_trades_rejected
    await trader._check_and_trade_ensemble("SOLUSDT")

    paper_engine.execute_market_order.assert_not_awaited()
    assert trader.total_trades_rejected == rejected_before + 1
