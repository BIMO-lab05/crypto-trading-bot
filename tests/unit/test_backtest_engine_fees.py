"""
FIX 14 — realistic-sim exit fees in backtesting/backtest_engine.py.

Until 2026-08-12 the engine's 'bybit_perp' mode classified stop_loss and
take_profit exits as LIMIT against `bybit_maker_fee = -0.0001`, so every
stop-out CREDITED the account ~1bp instead of paying the 5.5bp taker fee.
Both halves of that were wrong: Bybit conditional stop/TP orders trigger as
MARKET orders (taker), and Bybit pays maker rebates only at MM/high-VIP tiers
a $100 account cannot reach — maker is a +2bp CHARGE (app/costs.py
FeeSchedule.bybit_linear_perp). These tests pin both repairs: stop/TP exits
charge taker, and the engine's fee defaults come from the one cost model
instead of hand-copied literals.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Same bootstrap as tests/killtests/: backtesting/ modules are top-level there.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

from backtest_engine import BacktestEngine, OrderType  # noqa: E402
from costs_loader import load_costs  # noqa: E402

SCHEDULE = load_costs().FeeSchedule.bybit_linear_perp()

T0 = datetime(2026, 1, 1, 0, 0)
T1 = T0 + timedelta(hours=4)


def _engine(**kw):
    kw.setdefault("fee_mode", "bybit_perp")
    kw.setdefault("slippage", 0.0)  # isolate fees from slippage
    return BacktestEngine(**kw)


def _open_long(engine, price=100.0, **signal_extra):
    signal = {"stop_loss": 95.0, "take_profit": 110.0, **signal_extra}
    engine._open_position(OrderType.BUY, price, T0, signal)
    return engine.current_position


def _exit_commission(trade):
    """Exit-leg fee recovered from the trade record (gross − recorded net)."""
    if trade.order_type is OrderType.BUY:
        gross = (trade.exit_price - trade.entry_price) * trade.position_size
    else:
        gross = (trade.entry_price - trade.exit_price) * trade.position_size
    return gross - trade.profit_loss


def test_stop_loss_exit_charges_taker_fee():
    """A stop-out pays taker on the exit notional — never a credit."""
    engine = _engine()
    _open_long(engine)
    capital_after_entry = engine.capital

    engine._close_position(94.0, T1, "stop_loss")
    trade = engine.trades[0]

    commission = _exit_commission(trade)
    assert commission > 0  # pre-fix: maker "rebate" made this negative
    assert commission == pytest.approx(
        trade.position_size * trade.exit_price * engine.bybit_taker_fee
    )
    # Capital moves by net P&L exactly — the fee is inside it, not beside it.
    assert engine.capital == pytest.approx(capital_after_entry + trade.profit_loss)


def test_take_profit_exit_charges_taker_fee():
    """Bybit TP conditional orders trigger as market orders too."""
    engine = _engine()
    _open_long(engine)

    engine._close_position(111.0, T1, "take_profit")
    trade = engine.trades[0]

    commission = _exit_commission(trade)
    assert commission > 0
    assert commission == pytest.approx(
        trade.position_size * trade.exit_price * engine.bybit_taker_fee
    )


def test_default_fees_match_costs_model():
    """Defaults come from app/costs.py via costs_loader, not copied literals."""
    engine = BacktestEngine()
    assert engine.bybit_taker_fee == float(SCHEDULE.taker)
    assert engine.bybit_maker_fee == float(SCHEDULE.maker)
    # Maker is a CHARGE at this account tier, not a rebate.
    assert engine.bybit_maker_fee > 0


def test_constructor_fee_overrides_still_work():
    engine = _engine(bybit_taker_fee=0.001, bybit_maker_fee=0.0003)
    assert engine.bybit_taker_fee == 0.001
    assert engine.bybit_maker_fee == 0.0003
    assert engine._effective_fee_rate("MARKET") == 0.001
    assert engine._effective_fee_rate("LIMIT") == 0.0003


def test_resting_limit_entry_still_pays_maker_rate():
    """A genuinely-resting entry (signal order_type=LIMIT) stays maker —
    charged at the +2bp maker rate, not credited."""
    engine = _engine()
    capital_before = engine.capital
    pos = _open_long(engine, order_type="LIMIT")

    entry_fee = capital_before - engine.capital
    assert entry_fee > 0
    assert entry_fee == pytest.approx(
        pos.position_size * pos.entry_price * engine.bybit_maker_fee
    )
