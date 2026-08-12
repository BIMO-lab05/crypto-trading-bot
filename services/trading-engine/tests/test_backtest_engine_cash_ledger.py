"""
Tests: in-service backtest engine cash ledger, equity and fee source
====================================================================

Pins three defects found by the 2026-08-12 profit-path audit (Wave 2):

* FIX 12 — `_close_position` credited the EXIT notional after `_open_position`
  debited the ENTRY notional. A long round trip credited P&L twice; a short
  round trip dropped it entirely. Round-trip cash delta must be
  `gross_pnl - entry_commission - exit_commission` for BOTH sides.
* FIX 13 — `_calculate_equity` computed `unrealized_pnl` and then discarded it,
  marking the position at `quantity * current_price`. For a SHORT that is
  sign-flipped: price rising against the position RAISED reported equity.
* FIX 16 — the engine costed trades at 0.1%/side, 1.8x the paper engine's
  0.055% Bybit linear-perp taker. Screen verdicts and paper P&L could not
  reconcile. The default now derives from Settings.

The engine is float end-to-end; these tests use `pytest.approx` because
`quantity = notional / price` followed by `price * quantity` is not bit-exact.

Run: cd services/trading-engine && python3 -m pytest \
     tests/test_backtest_engine_cash_ledger.py --no-cov
"""

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from app.config import get_settings
from app.backtesting.backtest_engine import (
    BacktestConfig,
    BacktestEngine,
)
from app.backtesting.strategy_base import OHLCV, Signal, SignalType, StrategyBase


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

# Zero slippage isolates the ledger: entry and exit fill at the bar close, so
# every figure below is exact arithmetic on the configured commission.
NO_SLIPPAGE = 0.0

# Signal.position_size_pct is multiplied as a PERCENT by _open_position
# (config.position_size_pct * signal.position_size_pct / 100), so 100.0 means
# "the full configured position size" — 10% of cash here.
FULL_SIZE = 100.0


class ScriptedStrategy(StrategyBase):
    """Emits a fixed signal per bar index. No stops, so exits are scripted only."""

    def __init__(self, symbol: str, script: Dict[int, SignalType]):
        super().__init__(symbol)
        self._script = script
        self._bar_index = -1

    def get_name(self) -> str:
        return "ScriptedStrategy"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        self._bar_index += 1
        signal_type = self._script.get(self._bar_index)
        if signal_type is None:
            return None

        return Signal(
            signal_type=signal_type,
            symbol=self.symbol,
            price=bar.close,
            timestamp=bar.timestamp,
            position_size_pct=FULL_SIZE,
        )


def _bars(closes: List[float]) -> List[OHLCV]:
    """Flat bars at the given closes — high/low equal close so no stop can fire."""
    start = datetime(2026, 1, 1)
    return [
        OHLCV(
            timestamp=start + timedelta(hours=i),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000.0,
        )
        for i, close in enumerate(closes)
    ]


@pytest.fixture
def ledger_config() -> BacktestConfig:
    """initial_equity omitted: BacktestConfig resolves it from Settings (AUDIT 2.5)."""
    return BacktestConfig(slippage_pct=NO_SLIPPAGE, position_size_pct=10.0)


def _expected_round_trip_cash(config: BacktestConfig, trade) -> float:
    """Cash after a closed round trip: entry escrow returned, P&L in, both fees out."""
    entry_notional = trade.entry_price * trade.quantity
    exit_notional = trade.exit_price * trade.quantity
    fees = (entry_notional + exit_notional) * (config.commission_pct / 100)
    if trade.side == "long":
        gross_pnl = (trade.exit_price - trade.entry_price) * trade.quantity
    else:
        gross_pnl = (trade.entry_price - trade.exit_price) * trade.quantity
    return config.initial_equity + gross_pnl - fees


# ---------------------------------------------------------------------------
# FIX 12 — round-trip cash ledger
# ---------------------------------------------------------------------------


def test_long_round_trip_cash_is_pnl_minus_fees(ledger_config):
    """Long round trip credited the exit notional on top of P&L already in it."""
    engine = BacktestEngine(ledger_config)
    strategy = ScriptedStrategy(
        "BTCUSDT", {0: SignalType.BUY, 2: SignalType.CLOSE_LONG}
    )

    engine.run(strategy, _bars([100.0, 105.0, 110.0]))

    assert len(engine._trades) == 1
    trade = engine._trades[0]
    assert trade.side == "long"
    assert trade.exit_price > trade.entry_price  # the move must be non-zero

    expected = _expected_round_trip_cash(ledger_config, trade)
    assert engine._cash == pytest.approx(expected), (
        "Long round trip must leave cash at initial + gross P&L - both "
        "commissions; a larger figure means the exit notional was credited "
        "instead of the entry escrow (P&L counted twice)."
    )


def test_short_round_trip_cash_reflects_pnl(ledger_config):
    """Short round trip credited the exit notional, which cancels the P&L exactly."""
    engine = BacktestEngine(ledger_config)
    strategy = ScriptedStrategy(
        "BTCUSDT", {0: SignalType.SELL, 2: SignalType.CLOSE_SHORT}
    )

    engine.run(strategy, _bars([100.0, 95.0, 90.0]))

    assert len(engine._trades) == 1
    trade = engine._trades[0]
    assert trade.side == "short"
    assert trade.exit_price < trade.entry_price  # a winning short

    expected = _expected_round_trip_cash(ledger_config, trade)
    assert engine._cash == pytest.approx(expected), (
        "Winning short must raise cash by gross P&L minus both commissions; "
        "crediting the exit notional silently discards the P&L."
    )


# ---------------------------------------------------------------------------
# FIX 13 — open-position equity marking
# ---------------------------------------------------------------------------


def test_open_short_equity_falls_when_price_rises(ledger_config):
    """Marking a short at quantity * price made an adverse move look profitable."""
    engine = BacktestEngine(ledger_config)
    strategy = ScriptedStrategy("BTCUSDT", {0: SignalType.SELL})

    # No close signal: the equity curve is sampled with the short still open.
    engine.run(strategy, _bars([100.0, 100.0, 110.0]))

    equity_at_entry = engine._equity_curve[0]
    equity_after_adverse_move = engine._equity_curve[2]

    assert equity_after_adverse_move < equity_at_entry, (
        "Price rising against an open SHORT must reduce equity; marking the "
        "leg at quantity * current_price inverts the sign."
    )

    trade = engine._trades[0]  # closed at the last bar by backtest_end
    entry_notional = trade.entry_price * trade.quantity
    entry_commission = entry_notional * (ledger_config.commission_pct / 100)
    unrealized = (trade.entry_price - 110.0) * trade.quantity
    assert equity_after_adverse_move == pytest.approx(
        ledger_config.initial_equity - entry_commission + unrealized
    )


def test_open_long_equity_falls_when_price_falls(ledger_config):
    """Same escrow convention for the long side: cash + entry value + unrealized."""
    engine = BacktestEngine(ledger_config)
    strategy = ScriptedStrategy("BTCUSDT", {0: SignalType.BUY})

    engine.run(strategy, _bars([100.0, 100.0, 90.0]))

    trade = engine._trades[0]
    entry_notional = trade.entry_price * trade.quantity
    entry_commission = entry_notional * (ledger_config.commission_pct / 100)
    unrealized = (90.0 - trade.entry_price) * trade.quantity

    assert engine._equity_curve[2] == pytest.approx(
        ledger_config.initial_equity - entry_commission + unrealized
    )
    assert engine._equity_curve[2] < engine._equity_curve[0]


# ---------------------------------------------------------------------------
# FIX 16 — fee default derives from the paper engine's own source
# ---------------------------------------------------------------------------


def test_backtest_config_commission_default_is_settings_taker_fee():
    """commission_pct and paper_commission_pct are both PERCENT per side."""
    settings = get_settings()

    assert BacktestConfig().commission_pct == pytest.approx(0.055)
    assert BacktestConfig().commission_pct == pytest.approx(
        settings.paper_commission_pct
    ), "Backtest fees must come from the same Settings field the paper engine uses"


def test_backtest_request_models_default_to_settings_taker_fee():
    """The HTTP surface must not cost trades at 1.8x the venue taker fee."""
    from app.handlers.backtest import BacktestRequest, WalkForwardRequest

    settings = get_settings()

    assert BacktestRequest(strategy="rsi_momentum").commission_pct == pytest.approx(
        settings.paper_commission_pct
    )
    assert WalkForwardRequest(strategy="rsi_momentum").commission_pct == pytest.approx(
        settings.paper_commission_pct
    )


def test_no_hardcoded_commission_literal_in_backtest_handler():
    """compare_strategies used to build BacktestConfig(commission_pct=0.1)."""
    source = (
        Path(__file__)
        .parent.parent.joinpath("app/handlers/backtest.py")
        .read_text(encoding="utf-8")
    )

    offenders = re.findall(r"commission_pct\s*[=:]\s*0\.\d+", source)
    assert offenders == [], (
        f"Hardcoded commission literals in backtest handler: {offenders!r}. "
        "Derive the default from Settings.paper_commission_pct instead."
    )
