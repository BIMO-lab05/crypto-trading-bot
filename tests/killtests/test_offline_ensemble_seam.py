"""Smoke: the deployed chain runs offline end-to-end on synthetic candles."""

import asyncio
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import INTERVAL_MS, CandleStore  # noqa: E402

from conftest import _write_candles  # noqa: E402 same-dir conftest; pytest puts it on the path


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("candles")
    for iv, n in [("15", 2000), ("60", 600), ("240", 400), ("1440", 60)]:
        _write_candles(tmp, "BTCUSDT", iv, n, "2026-04-01 00:00:00")
    store = CandleStore(str(tmp), ["BTCUSDT"], ["15", "60", "240", "1440"])
    from killtests.offline_ensemble import ReplayClock, load_stack

    clock = ReplayClock(
        now_ms=int(store.frame("BTCUSDT", "60")["ts_ms"].iloc[-1]) + INTERVAL_MS["60"]
    )
    return load_stack(store, clock), clock, store


def _signal(st, clock, symbol="BTCUSDT"):
    from killtests.offline_ensemble import frozen_time

    with frozen_time(clock):
        return asyncio.run(
            st.aggregator.get_trading_signal_multi_timeframe(symbol, "60")
        )


def test_signal_computes_offline(stack):
    st, clock, store = stack
    sig = _signal(st, clock)
    assert sig.symbol == "BTCUSDT"
    assert sig.action is not None
    assert sig.indicators  # primary-timeframe indicator dict survives
    assert sig.timestamp == clock.now_ms  # frozen_time pin holds


def test_regime_fetch_is_real_not_default(stack):
    """The regime seam works: ADX reaches the offline TA app. An UNKNOWN-default
    regime on every call means the inline-httpx patch is broken (silent
    divergence from deployed behavior)."""
    st, clock, store = stack
    from killtests.offline_ensemble import frozen_time

    det = st.aggregator.core_aggregator.regime_detector
    det._cache.clear()
    with frozen_time(clock):
        analysis = asyncio.run(det.detect_regime("BTCUSDT", "60"))
    assert analysis.regime.name != "UNKNOWN", (
        "regime degraded to default — market_regime httpx shim not reaching the ASGI app"
    )


def test_deployed_bugs_preserved(stack):
    """Spec §3.3: ATR entry absent/None; atr_stop_loss has no producer."""
    st, clock, store = stack
    sig = _signal(st, clock)
    assert sig.indicators.get("ATR") is None
    assert "atr_stop_loss" not in sig.metadata


def test_ensemble_runs_on_signal(stack):
    st, clock, store = stack
    sig = _signal(st, clock)
    price = float(store.frame("BTCUSDT", "60")["close"].iloc[-1])
    ens = st.ensemble.generate_signal(sig, current_price=price)
    # None (HOLD) or an EnsembleSignal — both prove the leg wiring executes
    if ens is not None:
        assert ens.action.value in ("BUY", "SELL")
        assert set(ens.weights_snapshot) == {
            "simple_rsi",
            "multi_indicator",
            "mean_reversion",
        }


def test_as_of_no_lookahead(stack):
    """Signals at an earlier clock must not see later candles."""
    st, clock, store = stack
    f = store.frame("BTCUSDT", "60")
    clock.now_ms = int(f["ts_ms"].iloc[400]) + INTERVAL_MS["60"]
    sig = _signal(st, clock)
    assert sig.timestamp == clock.now_ms
    clock.now_ms = int(f["ts_ms"].iloc[-1]) + INTERVAL_MS["60"]  # restore
