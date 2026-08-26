"""
Total-exposure gate must guard every entry path, not just the ensemble one.

Review finding I20. The open-notional sum and the max_total_exposure_pct
comparison lived inline in _check_and_trade_ensemble only — 1 of the 3 paths
that can open a position. The other two (_execute_trade_with_setup, the
research/hybrid path, and _execute_trade, the default path) could open a
position with no account-level exposure check at all.

It is not breachable on today's configuration: per-symbol dedup means at most
one position per symbol, and 5 validated symbols x the 10% per-trade cap
cannot reach the 80% exposure cap. That bound depends entirely on the symbol
list staying at 5, which is not something the sizing code checks or states.

The gate rejects, never clamps: a silently resized order hides the breach.

Host-run test: the account size comes from shared/account.py, never a literal.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Host-run test: money rules require the account size to come from
# shared/account.py. conftest puts <repo>/shared on sys.path for the database
# package; `shared.account` needs the repo root itself.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

# Pre-import app.main / app.core.metrics so the deferred imports inside the
# gate helpers find the modules already in sys.modules (importing lazily during
# a test re-runs prometheus Counter registration and trips "Duplicated
# timeseries in CollectorRegistry").
import app.main  # noqa: F401,E402
import app.core.metrics  # noqa: F401,E402

from app.auto_trader import AutoTrader  # noqa: E402
from app.services.instruments_cache import InstrumentSpec  # noqa: E402

BALANCE = float(ACCOUNT_EQUITY_USD)
BTC_PRICE = 50000.0

_BAL = Decimal(str(ACCOUNT_EQUITY_USD))


def _qty_frac(frac: str, price: str) -> Decimal:
    """Quantity whose notional is `frac` of the account balance at `price`.

    Fixtures stay balance-relative so the exposure percentages under test
    hold at any declared account size."""
    return _BAL * Decimal(frac) / Decimal(price)


class _PermissiveInstrumentsCache:
    """Spec clearing every venue floor, so min-notional never masks the
    exposure behaviour under test."""

    async def get(self, symbol: str) -> InstrumentSpec:
        return InstrumentSpec(
            symbol=symbol,
            min_order_qty=Decimal("1E-15"),
            qty_step=Decimal("1E-15"),
            tick_size=Decimal("0.10"),
            min_notional=None,
            fetched_at=datetime.now(timezone.utc),
        )


def _open_position(symbol: str, entry_price: str, qty: str, remaining=None):
    p = MagicMock()
    p.symbol = symbol
    p.entry_price = Decimal(entry_price)
    p.quantity = Decimal(qty)
    p.remaining_quantity = Decimal(remaining) if remaining is not None else Decimal(qty)
    return p


def _position_mgr(open_positions):
    mgr = MagicMock()
    mgr.get_open_positions = MagicMock(return_value=open_positions)
    return mgr


@pytest.fixture
def trader(monkeypatch):
    t = AutoTrader(symbols=["BTCUSDT"])
    monkeypatch.setattr(t.settings, "trading_mode", "PAPER", raising=False)
    monkeypatch.setattr(t.settings, "max_total_exposure_pct", 80.0, raising=False)
    monkeypatch.setattr(t.settings, "max_risk_per_trade", 0.10, raising=False)
    monkeypatch.setattr(t.settings, "max_position_size_pct", 10.0, raising=False)
    t.notification_client = MagicMock()
    t.notification_client.notify_trade_open = AsyncMock()
    t.notification_client.notify_trade_close = AsyncMock()
    return t


# ============================================================================
# The shared helper
# ============================================================================


def test_helper_rejects_when_open_plus_new_breaches_cap(trader, caplog):
    """76% open + a 10% new trade exceeds the 80% cap."""
    mgr = _position_mgr(
        [
            _open_position("ETHUSDT", "3800", _qty_frac("0.38", "3800")),  # 38%
            _open_position("SOLUSDT", "76", _qty_frac("0.38", "76")),  # 38%
        ]
    )
    with caplog.at_level(logging.WARNING, logger="app.auto_trader"):
        ok = trader._passes_exposure_gate(
            symbol="BTCUSDT",
            new_notional=BALANCE * 0.10,
            balance=BALANCE,
            position_mgr=mgr,
        )
    assert ok is False
    assert any("[RISK_GATE] EXPOSURE REJECT" in rec.message for rec in caplog.records), (
        f"log format changed: {[r.message[:90] for r in caplog.records]!r}"
    )


def test_helper_allows_when_under_cap(trader):
    # 38% open + 10% new = 48%, under the 80% cap.
    mgr = _position_mgr([_open_position("ETHUSDT", "3800", _qty_frac("0.38", "3800"))])
    assert (
        trader._passes_exposure_gate(
            symbol="BTCUSDT",
            new_notional=BALANCE * 0.10,
            balance=BALANCE,
            position_mgr=mgr,
        )
        is True
    )


def test_helper_counts_remaining_quantity_not_original(trader):
    """A position that has taken a partial exit occupies only its remainder.

    Original quantity is 76% of balance (would breach with the 40% new trade);
    the 38% remainder plus 40% stays under the 80% cap — so a pass proves the
    gate counted the remainder, not the original."""
    original = _qty_frac("0.76", "3800")
    mgr = _position_mgr([_open_position("ETHUSDT", "3800", original, remaining=original / 2)])
    assert (
        trader._passes_exposure_gate(
            symbol="BTCUSDT",
            new_notional=BALANCE * 0.40,
            balance=BALANCE,
            position_mgr=mgr,
        )
        is True
    )


def test_helper_keeps_ensemble_log_tag(trader, caplog):
    """The ensemble path's log line is unchanged by the hoist."""
    mgr = _position_mgr(
        [_open_position("ETHUSDT", "7600", _qty_frac("0.76", "7600"))]  # 76%
    )
    with caplog.at_level(logging.WARNING, logger="app.auto_trader"):
        ok = trader._passes_exposure_gate(
            symbol="BTCUSDT",
            new_notional=BALANCE * 0.10,
            balance=BALANCE,
            position_mgr=mgr,
            tag="[ENSEMBLE][RISK_GATE]",
        )
    assert ok is False
    assert any("[ENSEMBLE][RISK_GATE] EXPOSURE REJECT" in rec.message for rec in caplog.records)


# ============================================================================
# The default path (_execute_trade) — the gate never existed here
# ============================================================================


def _signal(price: float = BTC_PRICE):
    from app.models import IndicatorSignal, SignalAction, TradingSignal

    indicator = Mock(spec=IndicatorSignal)
    indicator.metadata = {"current_price": price}
    sig = Mock(spec=TradingSignal)
    sig.action = SignalAction.BUY
    sig.confidence = 0.85
    sig.indicators = {"RSI": indicator}
    sig.metadata = {}
    return sig


def _drive_default_path(trader, open_positions):
    """Run _execute_trade with everything external stubbed. Returns the paper
    engine mock so the caller can assert whether an order was submitted."""
    from app.models import OrderStatus
    from app.position_sizing import PositionSizeResult, SizingMethod

    engine = Mock()
    engine.get_balance.return_value = BALANCE
    executed = Mock()
    executed.status = OrderStatus.FILLED
    engine.execute_market_order = AsyncMock(return_value=(executed, None))

    sizer = Mock()
    # 30% of balance: deliberately over the 10% per-trade cap so the clamp
    # runs first and the exposure gate sees the CLAMPED notional, as it does
    # in production.
    oversized_value = _BAL * Decimal("0.30")
    sizer.calculate_position_size.return_value = PositionSizeResult(
        position_size_pct=30.0,
        position_value=oversized_value,
        quantity=oversized_value / Decimal(str(BTC_PRICE)),
        method=SizingMethod.FIXED,
        kelly_fraction=None,
        confidence_modifier=None,
        reasoning="test fixture",
    )

    return engine, sizer, _position_mgr(open_positions)


@pytest.mark.asyncio
async def test_default_path_rejects_exposure_breach(trader, caplog):
    """76% open + a clamped 10% trade breaches the 80% cap: no order placed."""
    engine, sizer, mgr = _drive_default_path(
        trader,
        [
            _open_position("ETHUSDT", "3800", _qty_frac("0.38", "3800")),  # 38%
            _open_position("SOLUSDT", "76", _qty_frac("0.38", "76")),  # 38%
        ],
    )

    rejected_before = trader.total_trades_rejected
    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
        caplog.at_level(logging.WARNING, logger="app.auto_trader"),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    engine.execute_market_order.assert_not_awaited()
    assert trader.total_trades_rejected == rejected_before + 1
    assert any("EXPOSURE REJECT" in rec.message for rec in caplog.records), (
        f"no exposure reject logged: {[r.message[:90] for r in caplog.records]!r}"
    )


@pytest.mark.asyncio
async def test_default_path_allows_under_cap(trader):
    """Sanity inverse: modest open exposure must still trade."""
    engine, sizer, mgr = _drive_default_path(
        trader,
        # 38% open + a clamped 10% trade stays under the 80% cap.
        [_open_position("ETHUSDT", "3800", _qty_frac("0.38", "3800"))],
    )

    executed_before = trader.total_trades_executed
    with (
        patch("app.auto_trader.get_paper_engine", return_value=engine),
        patch("app.auto_trader.get_position_manager", return_value=mgr),
        patch("app.auto_trader.get_risk_manager", return_value=Mock()),
        patch("app.auto_trader.get_position_sizer", return_value=sizer),
        patch("app.main.get_instruments_cache", lambda: _PermissiveInstrumentsCache()),
    ):
        await trader._execute_trade("BTCUSDT", "BUY", 0.85, _signal())

    engine.execute_market_order.assert_awaited_once()
    assert trader.total_trades_executed == executed_before + 1
