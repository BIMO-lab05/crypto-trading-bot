"""
The VP pipeline is gone.

Unreachable by any flag or env (enable_volume_profile defaults False and
get_auto_trader never passes it), broken at two independent layers when
forced on, no pytest test asserts on it, and every consumer already reads
.get(..., {}) - so removal is a behavioral no-op. Production behavior was
ALREADY 'VP absent'.
"""

# Pre-import app.main / app.core.metrics so the deferred imports inside the
# trading-engine modules find prometheus collectors already registered
# (importing lazily during a test re-runs Counter registration and trips
# "Duplicated timeseries in CollectorRegistry").
import app.main  # noqa: F401
import app.core.metrics  # noqa: F401

from app.signal_aggregator import SignalAggregator


def test_vp_producer_is_gone():
    assert not hasattr(SignalAggregator, "get_trading_signal_with_vp")
    assert not hasattr(SignalAggregator, "_fetch_candles_for_vp")


def test_auto_trader_has_no_vp_flag():
    import inspect

    from app.auto_trader import AutoTrader

    signature = inspect.signature(AutoTrader.__init__)
    assert "enable_volume_profile" not in signature.parameters
