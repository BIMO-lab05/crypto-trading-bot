"""Golden-sample parity: same candles -> identical signals, offline vs live TA.

Two layers:
  A) every TA indicator endpoint: live HTTP response == offline ASGI response
     for the identical candle window (window equality asserted first).
  B) full aggregator chain: SignalAggregator against live TA vs against the
     offline ASGI app — TradingSignal fields must match.
Requires the docker stack; skips (loudly) otherwise. Each test records its
own outcome into `killtests.parity_stamp.RUN`; the stamp consumed by the H4
CLI gate is minted once, from `conftest.pytest_sessionfinish`, and only when
the whole session came back clean. Nothing in this module writes it.

KILLTESTS_DATA_DIR overrides the CSV dir for the offline leg (default
backtesting/data). Use a freshly-fetched parity copy when the canonical
data dir must stay frozen as the provenance of an in-flight signal-series
run — the stamp certifies seam parity (code-path equivalence at the live
latest bar), not the identity of any particular CSV snapshot.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

TA_URL = "http://localhost:8004"
MD_URL = "http://localhost:8002"
DATA_DIR = os.environ.get("KILLTESTS_DATA_DIR", "backtesting/data")

pytestmark = pytest.mark.golden


def _stack_up() -> bool:
    try:
        return (
            httpx.get(f"{TA_URL}/health", timeout=3).status_code == 200
            and httpx.get(f"{MD_URL}/health", timeout=3).status_code == 200
        )
    except Exception:
        return False


if not _stack_up():
    pytest.skip(
        "GOLDEN PARITY SKIPPED - docker stack down. H4 verdicts are INVALID "
        "until this suite passes. Start: docker compose -f docker-compose.unified.yml up -d",
        allow_module_level=True,
    )

from killtests.parity_stamp import RUN  # noqa: E402,F401 (import after the skip)

SYMBOLS = [
    "BTCUSDT",
    "SOLUSDT",
    "ADAUSDT",
]  # 3 windows (one per symbol) — see spec amendment: live TA has no as-of param, so window breadth comes from symbols + endpoints, not from time travel
ENDPOINTS = [  # (path template, params) — the full active fetch set (fetch_all_indicators, signal_aggregator.py); rsi-divergence and sqzmom-enhanced are commented out there, so excluded here too
    ("/api/v1/indicators/rsi/{s}", {"interval": "60", "period": 9}),
    ("/api/v1/indicators/macd/{s}", {"interval": "60"}),
    ("/api/v1/indicators/bollinger/{s}", {"interval": "60", "std_dev": 2.5}),
    ("/api/v1/indicators/sma/{s}", {"interval": "60", "period": 21}),
    ("/api/v1/indicators/ema/{s}", {"interval": "60", "period": 21}),
    ("/api/v1/indicators/trend/{s}", {"interval": "60", "limit": 300}),
    ("/api/v1/indicators/volume/{s}", {"interval": "60", "signal_type": "breakout"}),
    ("/api/v1/indicators/stochastic/{s}", {"interval": "60"}),
    (
        "/api/v1/indicators/ichimoku/{s}",
        {
            "interval": "60",
            "tenkan_period": 20,
            "kijun_period": 60,
            "senkou_b_period": 120,
        },
    ),
    ("/api/v1/indicators/adx/{s}", {"interval": "60"}),
    ("/api/v1/indicators/atr/{s}", {"interval": "60"}),
]

# Arms the stamp machinery and snapshots the inputs (data-dir fingerprint,
# backfill-manifest digest) that end up inside the stamp. Reached only after
# the stack probe above, so a skipped module never arms anything.
RUN.begin(symbols=SYMBOLS, data_dir=DATA_DIR)


@pytest.fixture(scope="module")
def offline():
    from killtests.candles import CandleStore
    from killtests.offline_ensemble import ReplayClock, load_stack

    store = CandleStore(
        DATA_DIR,
        ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"],
        ["15", "60", "240", "1440"],
    )
    clock = ReplayClock(now_ms=int(time.time() * 1000))
    return load_stack(store, clock), store, clock


def test_candle_window_equality(offline):
    """Precondition: DB candles == CSV candles for the comparison window."""
    RUN.record_start("test_candle_window_equality")
    _, store, clock = offline
    for sym in SYMBOLS:
        live = httpx.get(
            f"{MD_URL}/api/v1/klines/{sym}",
            params={"interval": "60", "limit": 50, "mainnet_only": "true"},
            timeout=10,
        ).json()["data"]
        offline_rows = store.as_of(sym, "60", clock.now_ms, 50)
        live_by_ts = {int(r["timestamp"]): r for r in live}
        matched = 0
        for row in offline_rows:
            lv = live_by_ts.get(row["timestamp"])
            if lv is None:
                continue
            assert float(lv["close"]) == pytest.approx(row["close"]), (
                f"{sym} candle mismatch at {row['timestamp']}"
            )
            matched += 1
        assert matched >= 40, (
            f"{sym}: only {matched}/50 overlapping candles (backfill stale? refresh it)"
        )
    RUN.record_pass("test_candle_window_equality")


def _strip_timestamps(obj):
    """Drop every "timestamp" key, at any nesting depth.

    Several indicator handlers (adx, atr, stochastic, trend_filter,
    volume_confirmation — see app/indicators/*.py) stamp
    `int(pd.Timestamp.now()...)` a level down inside a "data" dict, not only
    at the top level. Both legs compute this at slightly different wall-clock
    instants by construction; it's the same generation-time field the
    top-level pop already excludes, just nested. Not a signal value.
    """
    if isinstance(obj, dict):
        return {k: _strip_timestamps(v) for k, v in obj.items() if k != "timestamp"}
    if isinstance(obj, list):
        return [_strip_timestamps(v) for v in obj]
    return obj


def test_indicator_endpoint_parity(offline):
    RUN.record_start("test_indicator_endpoint_parity")
    stack, store, clock = offline
    transport = httpx.ASGITransport(app=stack.ta_app)

    async def compare():
        async with (
            httpx.AsyncClient(transport=transport, base_url="http://ta.offline") as oc,
            httpx.AsyncClient(base_url=TA_URL) as lc,
        ):
            for sym in SYMBOLS:
                for tmpl, params in ENDPOINTS:
                    path = tmpl.format(s=sym)
                    o = _strip_timestamps((await oc.get(path, params=params)).json())
                    l = _strip_timestamps((await lc.get(path, params=params)).json())
                    assert o == l, f"parity break {sym} {path}:\noffline={o}\nlive={l}"

    asyncio.run(compare())
    RUN.record_pass("test_indicator_endpoint_parity")


def _run_chain_leg(stack, symbol, client_factory, regime_httpx):
    """One full-chain evaluation with BOTH transports (aggregator client and the
    regime module's inline-httpx factory) pointed at the same target.

    Two places build ABSOLUTE URLs from a base captured once at construction
    and fixed at "http://ta.offline" (the offline stub's fake host, routable
    only because the offline `_HttpxShim.AsyncClient` ignores the target host
    and always dials the ASGI transport):
      - SignalAggregator.base_url (signal_aggregator.py:49) — every fetch_*
        builds `f"{self.base_url}/api/v1/indicators/.../{symbol}"`.
      - MarketRegimeDetector.settings.technical_analysis_url
        (market_regime.py:238) — its own inline `httpx.AsyncClient()` per ADX
        fetch.
    Swapping `agg.client` / `regime_mod.httpx` to the REAL httpx for the live
    leg is not enough on its own: real httpx honors the URL host in an
    absolute URL, so it would try to actually resolve "ta.offline" and fail
    name resolution. Point both base URLs at the real TA host for the live
    leg too, restoring the offline fake host after.

    client_factory (not a client): each leg runs in its own asyncio.run()
    loop, and an AsyncClient's keep-alive pool binds connections to the loop
    of first use. A client shared across legs hands a later leg a connection
    whose loop is closed — every fetch then dies with "Event loop is closed",
    the aggregator degrades that timeframe to an error/HOLD signal, and the
    MTF modifier silently flips (observed: live leg 0.9 vs offline 1.05 for
    whichever symbol ran within the ~5s keep-alive window of the previous
    leg). The client must be born and closed inside the leg's own loop.
    """
    agg = stack.aggregator
    det = agg.core_aggregator.regime_detector
    saved_client, saved_httpx = agg.client, stack.regime_mod.httpx
    saved_base_url, saved_ta_url = agg.base_url, det.settings.technical_analysis_url
    ta_url = TA_URL if regime_httpx is httpx else "http://ta.offline"
    stack.regime_mod.httpx = regime_httpx
    agg.base_url = ta_url
    det.settings.technical_analysis_url = ta_url
    det._cache.clear()

    async def _leg():
        async with client_factory() as client:
            agg.client = client
            return await agg.get_trading_signal_multi_timeframe(symbol, "60")

    try:
        return asyncio.run(_leg())
    finally:
        agg.client, stack.regime_mod.httpx = saved_client, saved_httpx
        agg.base_url = saved_base_url
        det.settings.technical_analysis_url = saved_ta_url


def test_full_chain_parity(offline):
    """SignalAggregator vs live TA == SignalAggregator vs offline ASGI —
    field-for-field on TradingSignal, per-indicator, AND the ensemble output
    (spec §7.1). All 3 golden symbols."""
    RUN.record_start("test_full_chain_parity")
    stack, store, clock = offline

    def asgi_factory():
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=stack.ta_app),
            base_url="http://ta.offline",
            timeout=30.0,
        )

    def live_factory():
        return httpx.AsyncClient(base_url=TA_URL, timeout=30.0)

    for sym in SYMBOLS:
        sig_off = _run_chain_leg(stack, sym, asgi_factory, stack.regime_mod.httpx)
        sig_live = _run_chain_leg(
            stack, sym, live_factory, httpx
        )  # live leg: REAL httpx
        assert sig_off.action == sig_live.action, sym
        assert sig_off.confidence == pytest.approx(sig_live.confidence, abs=1e-9), sym
        assert sig_off.aggregated_score == pytest.approx(
            sig_live.aggregated_score, abs=1e-9
        ), sym
        assert sig_off.consensus_count == sig_live.consensus_count, sym
        assert set(sig_off.indicators) == set(sig_live.indicators), sym
        for name, ind_off in sig_off.indicators.items():
            ind_live = sig_live.indicators[name]
            if ind_off is None or ind_live is None:
                assert ind_off is ind_live, f"{sym}/{name}: one leg None"
                continue
            assert ind_off.signal == ind_live.signal, f"{sym}/{name}"
            assert ind_off.confidence == pytest.approx(ind_live.confidence, abs=1e-9), (
                f"{sym}/{name}"
            )
            assert ind_off.value == ind_live.value or ind_off.value == pytest.approx(
                ind_live.value, abs=1e-9
            ), f"{sym}/{name}"
        price = float(store.frame(sym, "60")["close"].iloc[-1])
        ens_off = stack.ensemble.generate_signal(sig_off, current_price=price)
        ens_live = stack.ensemble.generate_signal(sig_live, current_price=price)
        assert (ens_off is None) == (ens_live is None), sym
        if ens_off is not None:
            assert ens_off == ens_live, f"{sym}: EnsembleSignal diverged"
        RUN.record_chain_action(sym, sig_off.action.value)
    RUN.record_pass("test_full_chain_parity")
