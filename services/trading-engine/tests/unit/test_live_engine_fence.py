"""The LIVE engine must be unconstructible until its accounting is repaired."""

import pytest


def test_live_engine_construction_is_fenced():
    from app.live_trading import LiveTradingEngine

    with pytest.raises(RuntimeError, match="fenced"):
        LiveTradingEngine()


def test_factory_is_fenced_too():
    import app.live_trading as live_trading

    live_trading._live_engine = None
    with pytest.raises(RuntimeError, match="fenced"):
        live_trading.get_live_engine()
