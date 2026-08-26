"""
Stop and take-profit exits must fill at the trigger level, not at bar.close.

_close_position priced EVERY exit off bar.close, including stops and TPs that
_check_exit_conditions had already triggered intrabar (bar.low <= stop_loss for
a long, bar.high >= stop_loss for a short). A bar that pierces the stop and
then runs on reported an exit far past the stop.

Conventions pinned here, and asserted:
  - stop  -> reference = stop level, clamped to bar.open (a gap-through fills
             at the open; the market never traded the stop price after it),
             then adverse slippage on top.
  - TP    -> fills at exactly take_profit. A resting limit fills at its price
             or better; booking exactly its price means a gap can never
             flatter the result. No slippage, no gap bonus.
  - signal / backtest_end exits -> unchanged, still bar.close +/- slippage.

Entry prices are read back off the recorded trade rather than recomputed: the
entry leg still fills off its own bar's close plus slippage, and this task does
not touch that.

Run: cd services/trading-engine && python3 -m pytest \\
     tests/test_backtest_engine_stop_fills.py --no-cov
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pytest

from app.backtesting.backtest_engine import BacktestConfig, BacktestEngine
from app.backtesting.strategy_base import OHLCV, Signal, SignalType, StrategyBase

# 0.1% per side, large enough that "stop minus slippage" and "close minus
# slippage" cannot be confused with each other at these price scales.
SLIPPAGE_PCT = 0.1


class _StopScriptedStrategy(StrategyBase):
    """Emits one entry signal carrying explicit stop/TP levels, then nothing.

    tests/test_backtest_engine_cash_ledger.py's ScriptedStrategy attaches no
    stops, so it cannot exercise this path - hence a local strategy here.
    """

    def __init__(
        self,
        symbol: str,
        entry_bar: int,
        signal_type: SignalType,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        exits: Optional[Dict[int, SignalType]] = None,
    ):
        super().__init__(symbol)
        self._entry_bar = entry_bar
        self._signal_type = signal_type
        self._stop_loss = stop_loss
        self._take_profit = take_profit
        self._exits = exits or {}
        self._bar_index = -1

    def get_name(self) -> str:
        return "StopScriptedStrategy"

    def on_bar(self, bar: OHLCV, equity: float) -> Optional[Signal]:
        self._bar_index += 1
        if self._bar_index == self._entry_bar:
            return Signal(
                signal_type=self._signal_type,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                stop_loss=self._stop_loss,
                take_profit=self._take_profit,
                position_size_pct=100.0,
            )
        exit_type = self._exits.get(self._bar_index)
        if exit_type is not None:
            return Signal(
                signal_type=exit_type,
                symbol=self.symbol,
                price=bar.close,
                timestamp=bar.timestamp,
                position_size_pct=100.0,
            )
        return None


def _ohlc(bars: List[tuple]) -> List[OHLCV]:
    """Explicit (open, high, low, close) bars - intrabar range is the point."""
    start = datetime(2026, 1, 1)
    return [
        OHLCV(
            timestamp=start + timedelta(hours=i),
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=1000.0,
        )
        for i, (o, h, lo, c) in enumerate(bars)
    ]


@pytest.fixture
def config() -> BacktestConfig:
    """initial_equity omitted: BacktestConfig resolves it from Settings."""
    return BacktestConfig(slippage_pct=SLIPPAGE_PCT, position_size_pct=10.0)


def _slippage(reference: float, config: BacktestConfig) -> float:
    return reference * (config.slippage_pct / 100)


def test_long_stop_fills_at_the_stop_not_the_close(config):
    """Bar 1 pierces the stop at 95 and closes at 80: the exit is not 80."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    # Bar 1 opens above the stop, so no gap: the reference is the stop itself.
    engine.run(strategy, _ohlc([(100, 100, 100, 100), (99, 99, 78, 80)]))

    assert len(engine._trades) == 1
    trade = engine._trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(95.0 - _slippage(95.0, config)), (
        f"exit booked at {trade.exit_price}; the stop was 95 and the bar closed "
        "at 80 - pricing an intrabar stop off bar.close reports a fill the "
        "strategy never asked for"
    )


def test_long_stop_gaps_through_and_fills_at_the_open(config):
    """Opening below the stop must fill at the OPEN, never at the stop.

    Filling at 95 here would fabricate a price the market did not trade after
    the open - an optimism bug in the opposite direction.
    """
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (90, 91, 85, 88)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(90.0 - _slippage(90.0, config))
    assert trade.exit_price < 95.0


def test_short_stop_clamps_to_the_open_on_a_gap_up(config):
    """Mirror case: a short's stop is above, so the clamp takes the MAX."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.SELL, stop_loss=105.0, take_profit=50.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (110, 115, 109, 112)]))

    trade = engine._trades[0]
    assert trade.side == "short"
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == pytest.approx(110.0 + _slippage(110.0, config))
    assert trade.exit_price > 105.0


def test_take_profit_fills_exactly_at_the_limit(config):
    """A resting limit fills at its price - no slippage, no gap bonus."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=50.0, take_profit=110.0
    )

    # Bar 1 gaps open to 115 and runs to 130: the fill is the limit, not 115
    # and not the close.
    engine.run(strategy, _ohlc([(100, 100, 100, 100), (115, 130, 114, 128)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "take_profit"
    assert trade.exit_price == pytest.approx(110.0), (
        f"take-profit booked at {trade.exit_price}; a resting limit fills at "
        "its own price, and honouring the gap would flatter the backtest"
    )


def test_signal_exit_still_prices_off_bar_close(config):
    """Scope guard: only stop/TP exits change."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT",
        0,
        SignalType.BUY,
        stop_loss=None,
        take_profit=None,
        exits={2: SignalType.CLOSE_LONG},
    )

    engine.run(
        strategy,
        _ohlc([(100, 100, 100, 100), (105, 106, 104, 105), (110, 112, 108, 111)]),
    )

    trade = engine._trades[0]
    assert trade.exit_reason == "signal"
    assert trade.exit_price == pytest.approx(111.0 - _slippage(111.0, config))


def test_backtest_end_exit_still_prices_off_bar_close(config):
    """Scope guard: the final forced close is unchanged."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=None, take_profit=None
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (105, 106, 104, 105)]))

    trade = engine._trades[0]
    assert trade.exit_reason == "backtest_end"
    assert trade.exit_price == pytest.approx(105.0 - _slippage(105.0, config))


def test_recorded_slippage_matches_the_exit_reference(config):
    """Trade.slippage must not keep quoting a bar.close-derived figure."""
    engine = BacktestEngine(config)
    strategy = _StopScriptedStrategy(
        "BTCUSDT", 0, SignalType.BUY, stop_loss=95.0, take_profit=200.0
    )

    engine.run(strategy, _ohlc([(100, 100, 100, 100), (99, 99, 78, 80)]))

    trade = engine._trades[0]
    # Entry leg off the RECORDED entry price (bar-0 close plus its own
    # slippage), not off the raw 100 - recomputing it here would be off by the
    # entry slippage itself.
    entry_slippage = _slippage(trade.entry_price, config)
    exit_slippage = _slippage(95.0, config)  # stop reference, not the 80 close
    assert trade.slippage == pytest.approx(entry_slippage + exit_slippage), (
        f"recorded slippage {trade.slippage} still assumes both legs were "
        "priced off the same bar close"
    )
