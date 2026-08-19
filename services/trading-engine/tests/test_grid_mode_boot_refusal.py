"""
GRID_TRADING mode must refuse to boot instead of failing once per symbol
per cycle.

The dispatch at auto_trader.py:961 called `self._check_and_trade_grid(symbol)`,
a method that has never existed on AutoTrader. With STRATEGY_MODE=grid_trading
every symbol raised AttributeError inside the per-symbol try, which the
circuit breaker counted as an aggregator failure — so the engine looked like
it had a flaky upstream instead of an unimplemented strategy, and traded
nothing while the breaker opened.

Removing the branch alone is not enough: get_auto_trader's mode_map uses
`.get(..., StrategyMode.HYBRID)`, so an unmapped string silently trades a
different strategy than the operator configured. The refusal has to happen in
the constructor, on the enum.
"""

import pytest

from app.auto_trader import AutoTrader, StrategyMode


def test_grid_mode_constructor_refuses():
    with pytest.raises(ValueError) as exc:
        AutoTrader(symbols=["SOLUSDT"], strategy_mode=StrategyMode.GRID_TRADING)

    message = str(exc.value)
    assert "grid_trading" in message
    # The error has to tell the operator what to set instead, or the only
    # recovery is reading source.
    for supported in ("standard", "research", "hybrid", "ensemble"):
        assert supported in message


def test_supported_modes_still_construct():
    for mode in (
        StrategyMode.STANDARD,
        StrategyMode.RESEARCH,
        StrategyMode.HYBRID,
        StrategyMode.ENSEMBLE,
    ):
        trader = AutoTrader(symbols=["SOLUSDT"], strategy_mode=mode)
        assert trader.strategy_mode is mode


def test_no_grid_dispatch_target_exists():
    """Pins the reason for the refusal: there is nothing to dispatch to."""
    assert not hasattr(AutoTrader, "_check_and_trade_grid")


def test_get_auto_trader_does_not_silently_fall_back_from_grid(monkeypatch):
    """mode_map.get() maps 'grid_trading' to a mode that cannot run; the
    constructor must raise rather than let HYBRID trade under a grid label."""
    from app.auto_trader import get_auto_trader, reset_auto_trader
    from app.config import get_settings

    reset_auto_trader()
    monkeypatch.setattr(get_settings(), "strategy_mode", "grid_trading")
    try:
        with pytest.raises(ValueError):
            get_auto_trader()
    finally:
        reset_auto_trader()
