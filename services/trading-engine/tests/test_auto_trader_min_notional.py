"""
Tests for the min-notional / min-qty pre-submit gate on AutoTrader.

Covers the four cases described in the spec:

* cache miss (spec is None) → allow trade, paper engine called
* qty below min_order_qty → reject, paper engine NOT called, counter increments
* notional below min_notional → reject, paper engine NOT called
* fully passes → proceed (we stub the rest of the path so we only assert the
  gate itself does not block)

All HTTP / DB / position-manager dependencies are stubbed via monkeypatch on
``app.main.<symbol>`` accessors so tests run as pure unit tests without a
container.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# Pre-import app.main so the deferred `from app.main import get_instruments_cache`
# inside the helper finds the module already in sys.modules. Importing it lazily
# during a test re-runs prometheus_client.Counter() registrations and trips
# `Duplicated timeseries in CollectorRegistry` against the default registry.
import app.main  # noqa: F401
import app.core.metrics  # noqa: F401  # pre-load so helper's deferred import succeeds

from app.auto_trader import AutoTrader
from app.services.instruments_cache import InstrumentSpec

# pinned small-account scenario: keeps reject-not-clamp coverage near the ~$5
# venue floor; NOT the declared account size (that lives in shared/account.py
# and Settings.paper_initial_balance). The gate's inputs (qty/price) are
# explicit in each test — balance is context only.
SMALL_BALANCE = Decimal("100")


# ---------------------------------------------------------------- helpers


def _spec(min_qty="0.001", min_notional: Optional[str] = "5") -> InstrumentSpec:
    return InstrumentSpec(
        symbol="BTCUSDT",
        min_order_qty=Decimal(min_qty),
        qty_step=Decimal("0.001"),
        tick_size=Decimal("0.10"),
        min_notional=Decimal(min_notional) if min_notional is not None else None,
        fetched_at=datetime.now(timezone.utc),
    )


class _StubInstrumentsCache:
    def __init__(self, spec: Optional[InstrumentSpec]):
        self._spec = spec
        self.calls: list[str] = []

    async def get(self, symbol: str):
        self.calls.append(symbol)
        return self._spec


@pytest.fixture(autouse=True)
def _force_live_mode(monkeypatch):
    """Force LIVE so the cache-miss case here asserts the LIVE fail-OPEN branch.

    The gate itself runs in every mode (since 2026-08-04) and a missing spec
    fails CLOSED in PAPER (review I12) — that half is covered by
    tests/test_min_notional_fail_closed_paper.py.
    """
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "trading_mode", "LIVE", raising=False)


@pytest.fixture
def trader():
    """Fresh AutoTrader for each test (no _trading_loop running)."""
    t = AutoTrader(symbols=["BTCUSDT"])
    return t


# ============================================================================
# Direct helper tests — exercise _passes_min_notional in isolation.
# ============================================================================


@pytest.mark.asyncio
async def test_passes_when_cache_miss(trader, monkeypatch):
    cache = _StubInstrumentsCache(spec=None)
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.0000166"),  # tiny — would normally be rejected
        price=Decimal("60000"),
        balance=SMALL_BALANCE,
    )
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_rejects_when_quantity_below_min_qty(trader, monkeypatch):
    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional=None))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.0000166"),  # < 0.001
        price=Decimal("60000"),
        balance=SMALL_BALANCE,
    )
    assert ok is False
    assert reason == "min_qty"


@pytest.mark.asyncio
async def test_rejects_when_notional_below_min_notional(trader, monkeypatch):
    # qty satisfies min_qty but notional ($3) below min_notional ($5).
    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional="5"))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.001"),
        price=Decimal("3000"),  # 0.001 * 3000 = $3
        balance=SMALL_BALANCE,
    )
    assert ok is False
    assert reason == "min_notional"


@pytest.mark.asyncio
async def test_passes_when_above_both_minima(trader, monkeypatch):
    from app.config import get_settings

    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional="5"))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.002"),
        price=Decimal("60000"),  # notional = $120
        balance=Decimal(str(get_settings().paper_initial_balance)),
    )
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_passes_when_min_notional_field_absent(trader, monkeypatch):
    """Bybit doesn't always return minNotionalValue — gate should only check qty."""
    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional=None))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.001"),
        price=Decimal("0.001"),  # absurdly tiny notional
        balance=SMALL_BALANCE,
    )
    # No min_notional → only min_qty matters, and we pass it.
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_paper_mode_enforces_gate(trader, monkeypatch):
    """PAPER mode must enforce the venue gate exactly like LIVE.

    Inverted 2026-08-05 (Phase 1, AUDIT.md hop 4b): the old PAPER
    short-circuit meant paper results could contain trades LIVE could never
    place. Paper mirrors the venue constraints of a real account (whatever
    size Settings declares), so a spec that would reject in LIVE must reject
    in PAPER too — and the cache must actually be consulted.
    """
    from app.config import get_settings

    s = get_settings()
    # Override the autouse LIVE fixture for this single test.
    monkeypatch.setattr(s, "trading_mode", "PAPER", raising=False)

    # A spec that rejects in LIVE: tiny qty + huge min_notional.
    cache = _StubInstrumentsCache(spec=_spec(min_qty="1.0", min_notional="1000"))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.0000166"),
        price=Decimal("60000"),
        balance=SMALL_BALANCE,
    )
    assert ok is False
    assert reason == "min_qty"
    # The gate must have hit the cache — no short-circuit before lookup.
    assert cache.calls == ["BTCUSDT"], "cache.get() must be invoked in PAPER mode"


@pytest.mark.asyncio
async def test_fail_open_when_cache_get_raises(trader, monkeypatch):
    class _Boom:
        async def get(self, symbol):
            raise RuntimeError("connector exploded")

    monkeypatch.setattr("app.main.get_instruments_cache", lambda: _Boom())

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.0000166"),
        price=Decimal("60000"),
        balance=SMALL_BALANCE,
    )
    # Fail-open — gate cannot block trading on connector unavailability.
    assert ok is True
    assert reason is None


@pytest.mark.asyncio
async def test_prometheus_counter_increments_on_min_qty_reject(trader, monkeypatch):
    import app.core.metrics as metrics

    cache = _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional=None))
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: cache)

    counter = metrics.trades_rejected_min_notional_total.labels(symbol="BTCUSDT", reason="min_qty")
    before = counter._value.get()  # type: ignore[attr-defined]

    ok, reason = await trader._passes_min_notional(
        symbol="BTCUSDT",
        quantity=Decimal("0.0000166"),
        price=Decimal("60000"),
        balance=SMALL_BALANCE,
    )
    assert ok is False and reason == "min_qty"

    after = counter._value.get()  # type: ignore[attr-defined]
    assert after == before + 1


# ============================================================================
# Integration through _execute_trade — assert paper_engine NOT called on
# reject and total_trades_rejected increments.
# ============================================================================


def _signal_with_price(price: float):
    """Minimal stand-in for TradingSignal that _execute_trade reads."""
    indicator = MagicMock()
    indicator.metadata = {"current_price": price}
    sig = MagicMock()
    sig.indicators = {"rsi": indicator}
    sig.metadata = {}
    return sig


def _patch_execute_trade_deps(
    monkeypatch, *, balance: float, paper_engine, position_sizer_qty: Decimal
):
    """Stub get_paper_engine / get_position_manager / get_risk_manager /
    get_position_sizer / get_performance_tracker on the auto_trader module."""

    paper_engine.get_balance = MagicMock(return_value=balance)
    paper_engine.execute_market_order = AsyncMock()  # default: not called

    position_mgr = MagicMock()
    position_mgr.get_open_positions = MagicMock(return_value=[])

    risk_mgr = MagicMock()

    sizer = MagicMock()
    size_result = MagicMock()
    size_result.quantity = position_sizer_qty
    size_result.position_value = Decimal(str(float(position_sizer_qty) * 60000))
    size_result.method = MagicMock()
    size_result.method.value = "confidence_adjusted"
    size_result.position_size_pct = 0.5
    size_result.reasoning = "stub"
    sizer.calculate_position_size = MagicMock(return_value=size_result)
    sizer.get_performance_stats_from_tracker = MagicMock(return_value={})

    monkeypatch.setattr("app.auto_trader.get_paper_engine", lambda: paper_engine)
    monkeypatch.setattr("app.auto_trader.get_position_manager", lambda: position_mgr)
    monkeypatch.setattr("app.auto_trader.get_risk_manager", lambda: risk_mgr)
    monkeypatch.setattr("app.auto_trader.get_position_sizer", lambda: sizer)
    monkeypatch.setattr("app.auto_trader.get_performance_tracker", lambda: MagicMock())


@pytest.mark.asyncio
async def test_execute_trade_cache_miss_proceeds(trader, monkeypatch):
    from app.config import get_settings

    paper_engine = MagicMock()
    _patch_execute_trade_deps(
        monkeypatch,
        # declared balance — large enough to satisfy any later gate
        balance=get_settings().paper_initial_balance,
        paper_engine=paper_engine,
        position_sizer_qty=Decimal("0.01"),
    )
    # Cache miss → fail-open, gate must allow trade.
    monkeypatch.setattr("app.main.get_instruments_cache", lambda: _StubInstrumentsCache(spec=None))

    # Stub the paper-engine fill so the function continues past OrderCreate.
    filled = MagicMock()
    filled.status = MagicMock()
    filled.status.name = "FILLED"
    # Use the actual OrderStatus enum from the module so the equality check
    # in _execute_trade works.
    from app.models import OrderStatus

    filled.status = OrderStatus.FILLED
    filled.order_id = "PAPER_BTCUSDT_BUY"
    filled.filled_quantity = Decimal("0.01")
    filled.filled_price = Decimal("60000")
    paper_engine.execute_market_order = AsyncMock(return_value=(filled, None))

    # Notification client and position-add side effects: don't care.
    trader.notification_client = MagicMock()
    trader.notification_client.notify_trade_open = AsyncMock()

    rejected_before = trader.total_trades_rejected
    await trader._execute_trade(
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.8,
        signal=_signal_with_price(60000.0),
    )
    # Gate didn't reject (cache miss = fail-open).
    assert trader.total_trades_rejected == rejected_before
    paper_engine.execute_market_order.assert_awaited()


@pytest.mark.asyncio
async def test_execute_trade_below_min_qty_rejects(trader, monkeypatch):
    paper_engine = MagicMock()
    # tiny quantity: 0.0000166 < 0.001 min (pinned small-account sizing)
    _patch_execute_trade_deps(
        monkeypatch,
        balance=float(SMALL_BALANCE),
        paper_engine=paper_engine,
        position_sizer_qty=Decimal("0.0000166"),
    )
    monkeypatch.setattr(
        "app.main.get_instruments_cache",
        lambda: _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional=None)),
    )

    rejected_before = trader.total_trades_rejected
    await trader._execute_trade(
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.8,
        signal=_signal_with_price(60000.0),
    )

    assert trader.total_trades_rejected == rejected_before + 1
    paper_engine.execute_market_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_trade_below_min_notional_rejects(trader, monkeypatch):
    paper_engine = MagicMock()
    # qty satisfies min_qty (0.001) but notional ($3) below min_notional ($5)
    # (pinned small-account sizing keeps the notional near the venue floor)
    _patch_execute_trade_deps(
        monkeypatch,
        balance=float(SMALL_BALANCE),
        paper_engine=paper_engine,
        position_sizer_qty=Decimal("0.001"),
    )
    monkeypatch.setattr(
        "app.main.get_instruments_cache",
        lambda: _StubInstrumentsCache(spec=_spec(min_qty="0.001", min_notional="5")),
    )

    rejected_before = trader.total_trades_rejected
    await trader._execute_trade(
        symbol="BTCUSDT",
        action="BUY",
        confidence=0.8,
        signal=_signal_with_price(3000.0),  # notional = 0.001 * 3000 = $3
    )

    assert trader.total_trades_rejected == rejected_before + 1
    paper_engine.execute_market_order.assert_not_awaited()
