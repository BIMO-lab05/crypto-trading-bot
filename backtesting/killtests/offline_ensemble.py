"""Offline replay of the DEPLOYED ensemble signal chain (spec §3.1).

Seam: real TA FastAPI app served in-process via httpx.ASGITransport; real
SignalAggregator / MTF / CoreAggregator / MultiStrategyEnsemble loaded via
the dual-namespace shim pattern proven by run_walk_forward_ensemble.py:58-191.
Only the market-data HTTP boundary is faked (MockTransport -> CandleStore).

MUST be loaded once per process (TA app registers Prometheus collectors in
the global registry; a second import raises Duplicated timeseries).
`load_stack` enforces this itself: only the first call imports the TA app
and builds the TE namespace. A second call does not re-import — it rewires
the already-loaded stack onto the new (store, clock) pair (fresh
market-data MockTransport swapped onto the TA fetcher's httpx client,
`stack.clock` rebound) and returns the same Stack instance. This lets
`run_replay` and multiple pytest modules share one loaded stack across
different CandleStore/ReplayClock instances within one process.
"""

import importlib.util
import os
import re
import sys
import types
from contextlib import contextmanager
from dataclasses import dataclass
from unittest import mock

import httpx

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_TA_PATH = os.path.join(_REPO, "services", "technical-analysis")
_TE_PATH = os.path.join(_REPO, "services", "trading-engine")
_RM_PATH = os.path.join(_REPO, "services", "risk-metrics-service")

sys.path.insert(0, _REPO)

from killtests.candles import CandleStore  # noqa: E402


@dataclass
class ReplayClock:
    now_ms: int


@contextmanager
def frozen_time(clock: ReplayClock):
    """Pin wall clock to the replay clock for one call.

    signal_aggregator.py (and market_regime cache writes) use FUNCTION-LOCAL
    `import time` — a module-attribute patch is a no-op. Patch time.time
    process-wide for the duration of the call instead. asyncio/httpx use
    time.monotonic internally, which stays real.
    """
    with mock.patch("time.time", lambda: clock.now_ms / 1000.0):
        yield


@dataclass
class Stack:
    aggregator: object
    ensemble: object
    signal_aggregator_mod: object
    regime_mod: object  # loaded app.aggregation.market_regime (its `httpx` name is the patch point)
    SignalAction: object
    kernels: dict  # {'deflated_sharpe_ratio', 'CombinatorialPurgedCV', 'cpcv_to_dsr', ...}
    ta_app: object
    clock: ReplayClock


_LOADED: Stack = None
_TA_FETCHER_MOD = None  # cached for rewiring fetcher.client on a second load_stack call


def _purge_app_modules() -> None:
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]


_KERNELS: dict = None


def _load_kernels() -> dict:
    """Spec-load risk-metrics kernels under unique names — collision-proof and
    idempotent (callable before OR after the TE `app` namespace exists, and
    repeatedly within one pytest process). Never purges `sys.modules['app']`.
    """
    global _KERNELS
    if _KERNELS is not None:
        return _KERNELS

    def _spec_load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    sm = _spec_load("_killtests_sharpe_metrics", os.path.join(_RM_PATH, "app", "sharpe_metrics.py"))
    # cpcv.py does `from app.sharpe_metrics import deflated_sharpe_ratio`:
    # temporarily alias our loaded copy; restore whatever was there before.
    created_app = "app" not in sys.modules
    if created_app:
        sys.modules["app"] = types.ModuleType("app")
    prior = sys.modules.get("app.sharpe_metrics")
    sys.modules["app.sharpe_metrics"] = sm
    try:
        cp = _spec_load("_killtests_cpcv", os.path.join(_RM_PATH, "app", "cpcv.py"))
    finally:
        if prior is not None:
            sys.modules["app.sharpe_metrics"] = prior
        else:
            del sys.modules["app.sharpe_metrics"]
        if created_app:
            del sys.modules["app"]
    _KERNELS = {
        "deflated_sharpe_ratio": sm.deflated_sharpe_ratio,
        "probabilistic_sharpe_ratio": sm.probabilistic_sharpe_ratio,
        "CombinatorialPurgedCV": cp.CombinatorialPurgedCV,
        "cpcv_to_dsr": cp.cpcv_to_dsr,
        "cpcv_sharpe_distribution": cp.cpcv_sharpe_distribution,
    }
    return _KERNELS


def _load_ta_app():
    """Import the full TA FastAPI app under TA's own `app` namespace, keep refs, purge."""
    sys.path.insert(0, _TA_PATH)
    import app.fetcher as ta_fetcher_mod  # noqa: PLC0415
    import app.main as ta_main  # noqa: PLC0415

    ta_app = ta_main.app
    _purge_app_modules()
    sys.path.remove(_TA_PATH)
    return ta_app, ta_fetcher_mod


def _mk_market_data_transport(store: CandleStore, clock: ReplayClock) -> httpx.MockTransport:
    kline_re = re.compile(r"/api/v1/klines/([A-Z]+)$")

    def handler(request: httpx.Request) -> httpx.Response:
        m = kline_re.search(request.url.path)
        if not m:
            return httpx.Response(404, json={"success": False, "error": "not mocked"})
        symbol = m.group(1)
        params = dict(request.url.params)
        interval = params.get("interval", "60")
        interval = {"D": "1440", "1440": "1440"}.get(interval, interval)
        limit = int(params.get("limit", 200))
        rows = store.as_of(symbol, interval, clock.now_ms, limit)
        return httpx.Response(200, json={"success": True, "data": rows})

    return httpx.MockTransport(handler)


def _load_te_module(dotted_name: str, rel_path: str):
    abs_path = os.path.join(_TE_PATH, rel_path)
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)
    return module


def _build_te_namespace():
    """PHASE 3 of the shim pattern, extended for the full deployed chain."""
    from shared.account import DEFAULTS  # noqa: PLC0415

    sys.path.insert(0, _TE_PATH)
    app_pkg = types.ModuleType("app")
    app_pkg.__path__ = [os.path.join(_TE_PATH, "app")]
    sys.modules["app"] = app_pkg

    te_enums = _load_te_module("app.models.enums", "app/models/enums.py")
    te_signal = _load_te_module("app.models.signal", "app/models/signal.py")
    models_stub = types.ModuleType("app.models")
    models_stub.SignalAction = te_enums.SignalAction
    models_stub.IndicatorSignal = te_signal.IndicatorSignal
    models_stub.TradingSignal = te_signal.TradingSignal
    sys.modules["app.models"] = models_stub

    config_stub = types.ModuleType("app.config")

    # Spec-load the REAL trading-engine config.py (same mechanism as
    # tests/test_account_config_sync.py — it imports only pydantic /
    # pydantic_settings / typing, and Settings is never instantiated at
    # import) so stub gate values track declared defaults instead of rotting.
    _cfg_spec = importlib.util.spec_from_file_location(
        "_killtests_te_config", os.path.join(_TE_PATH, "app", "config.py")
    )
    assert _cfg_spec is not None and _cfg_spec.loader is not None
    _cfg_mod = importlib.util.module_from_spec(_cfg_spec)
    _cfg_spec.loader.exec_module(_cfg_mod)

    def _te_default(field: str):
        return _cfg_mod.Settings.model_fields[field].default

    def _stub_get_settings():
        return types.SimpleNamespace(
            technical_analysis_url="http://ta.offline",
            market_data_url="http://md.offline",
            service_name="killtests-offline-ensemble",
            max_risk_per_trade=DEFAULTS["MAX_RISK_PER_TRADE"],
            ensemble_min_position_pct=_te_default("ensemble_min_position_pct"),
            ensemble_confidence_size_multiplier=_te_default("ensemble_confidence_size_multiplier"),
            # Gatekeeper thresholds landed after this stub was first written
            # (fix/gates-ta-dsr); pinning them here is how the stub rotted the
            # last time, so every gate value now derives from the spec-loaded
            # real config.py declared defaults via _te_default().
            gatekeeper_block_threshold=_te_default("gatekeeper_block_threshold"),
            gatekeeper_block_penalty=_te_default("gatekeeper_block_penalty"),
            gatekeeper_counter_trend_penalty=_te_default("gatekeeper_counter_trend_penalty"),
            # Deployed default (CLAUDE.md §3): ML predictions gated off and
            # sentiment removed from the pipeline. get_trading_signal_enhanced
            # (Phase 3 path) reads this; the Phase-1 path the driver exercises
            # does not, but the stub must not AttributeError if a later task
            # reaches that branch.
            enable_ml_predictions=False,
        )

    config_stub.get_settings = _stub_get_settings
    sys.modules["app.config"] = config_stub

    monitoring_pkg = types.ModuleType("app.monitoring")
    monitoring_pkg.__path__ = []
    sys.modules["app.monitoring"] = monitoring_pkg
    metrics_stub = types.ModuleType("app.monitoring.metrics")
    metrics_stub.record_cache_hit = lambda *a, **kw: None
    metrics_stub.record_cache_miss = lambda *a, **kw: None
    sys.modules["app.monitoring.metrics"] = metrics_stub
    # aggregator_core.py:26 `from app.monitoring.signal_funnel import
    # get_signal_funnel` (landed 42e2250, after this stub set was written —
    # it silently broke every kernel spec-load until 2026-08-26). The module
    # is stdlib-only, so load the real one rather than stubbing 22 stages.
    _load_te_module("app.monitoring.signal_funnel", "app/monitoring/signal_funnel.py")

    aggregation_pkg = types.ModuleType("app.aggregation")
    aggregation_pkg.__path__ = [os.path.join(_TE_PATH, "app", "aggregation")]
    sys.modules["app.aggregation"] = aggregation_pkg

    _load_te_module("app.phase1_metrics", "app/phase1_metrics.py")
    _load_te_module("app.aggregation.confidence_guard", "app/aggregation/confidence_guard.py")
    _load_te_module("app.aggregation.gatekeeper", "app/aggregation/gatekeeper.py")
    _load_te_module("app.aggregation.validator", "app/aggregation/validator.py")
    _load_te_module("app.aggregation.voter", "app/aggregation/voter.py")
    _load_te_module("app.aggregation.signal_cache", "app/aggregation/signal_cache.py")
    # signal_aggregator.py:23 `from app.aggregation.ml_gate_reasons import
    # log_ml_disabled` — not in the brief's stub set; discovered by grepping
    # signal_aggregator.py's import block. No further app.* deps of its own.
    _load_te_module("app.aggregation.ml_gate_reasons", "app/aggregation/ml_gate_reasons.py")
    regime_mod = _load_te_module(
        "app.aggregation.market_regime", "app/aggregation/market_regime.py"
    )
    core_mod = _load_te_module(
        "app.aggregation.aggregator_core", "app/aggregation/aggregator_core.py"
    )
    mtf_mod = _load_te_module(
        "app.aggregation.multi_timeframe", "app/aggregation/multi_timeframe.py"
    )
    # signal_aggregator's imports from app.aggregation (top-of-file line 22 and
    # lazy line 974) must both resolve against the stub package:
    aggregation_pkg.CoreAggregator = core_mod.CoreAggregator
    aggregation_pkg.get_multi_timeframe_analyzer = mtf_mod.get_multi_timeframe_analyzer

    # signal_aggregator.py:24 `from app.services.indicator_registry import get_indicator_registry`
    # — stub the package so the REAL app/services/__init__.py (which drags in
    # trading_service and the full models package) never runs.
    services_pkg = types.ModuleType("app.services")
    services_pkg.__path__ = []
    sys.modules["app.services"] = services_pkg
    reg_mod = _load_te_module(
        "app.services.indicator_registry", "app/services/indicator_registry.py"
    )
    services_pkg.indicator_registry = reg_mod

    sa_mod = _load_te_module("app.signal_aggregator", "app/signal_aggregator.py")

    _load_te_module("app.strategies.simple_rsi_strategy", "app/strategies/simple_rsi_strategy.py")
    _load_te_module(
        "app.strategies.mean_reversion_strategy",
        "app/strategies/mean_reversion_strategy.py",
    )
    mse_mod = _load_te_module(
        "app.strategies.multi_strategy_ensemble",
        "app/strategies/multi_strategy_ensemble.py",
    )

    return sa_mod, mse_mod, te_enums, regime_mod


def _swap_httpx_clients(obj, transport: httpx.AsyncBaseTransport, base_url: str) -> None:
    """Replace every httpx.AsyncClient attribute on obj (one level deep)."""
    for name in dir(obj):
        try:
            attr = getattr(obj, name)
        except Exception:
            continue
        if isinstance(attr, httpx.AsyncClient):
            setattr(
                obj,
                name,
                httpx.AsyncClient(transport=transport, base_url=base_url, timeout=30.0),
            )


def load_stack(store: CandleStore, clock: ReplayClock) -> Stack:
    global _LOADED, _TA_FETCHER_MOD
    if _LOADED is not None:
        # Cache-and-rewire: the TA app cannot be re-imported (Prometheus
        # registry), so rebuild only what closed over the FIRST caller's
        # store/clock -- the market-data transport -- and rebind the clock
        # reference. The ta_transport (ASGITransport into ta_app) and the
        # regime_mod httpx shim are unaffected: they call into the TA app,
        # which itself resolves candles through the fetcher we just rewired.
        md_transport = _mk_market_data_transport(store, clock)
        fetcher = _TA_FETCHER_MOD.get_fetcher()
        fetcher.client = httpx.AsyncClient(
            transport=md_transport, base_url="http://md.offline", timeout=30.0
        )
        _LOADED.clock = clock
        return _LOADED

    kernels = _load_kernels()
    ta_app, ta_fetcher_mod = _load_ta_app()
    _TA_FETCHER_MOD = ta_fetcher_mod

    # Patch market-data boundary: real TA fetcher keeps its validation pipeline,
    # only its HTTP client is mocked to serve CandleStore rows as-of the clock.
    md_transport = _mk_market_data_transport(store, clock)
    fetcher = ta_fetcher_mod.get_fetcher()
    fetcher.client = httpx.AsyncClient(
        transport=md_transport, base_url="http://md.offline", timeout=30.0
    )

    sa_mod, mse_mod, te_enums, regime_mod = _build_te_namespace()

    aggregator = sa_mod.SignalAggregator()
    ta_transport = httpx.ASGITransport(app=ta_app)
    _swap_httpx_clients(aggregator, ta_transport, "http://ta.offline")

    # MarketRegimeDetector builds `httpx.AsyncClient` INLINE per ADX fetch
    # (market_regime.py:242) — no attribute exists to swap. Patch the loaded
    # module's `httpx` name with a factory shim so those inline constructions
    # get the ASGI transport. Unpatched, every regime fetch fails silently and
    # degrades to the UNKNOWN default — a divergence the golden gate can't see.
    class _HttpxShim:
        ASGITransport = httpx.ASGITransport
        MockTransport = httpx.MockTransport
        Response = httpx.Response
        Request = httpx.Request

        @staticmethod
        def AsyncClient(**kw):
            kw.pop("transport", None)
            kw.setdefault("timeout", 30.0)
            return httpx.AsyncClient(transport=ta_transport, base_url="http://ta.offline", **kw)

    regime_mod.httpx = _HttpxShim

    ensemble = mse_mod.MultiStrategyEnsemble()
    # Determinism pin: weights file absent on host -> default 0.50 win rates -> 1/3 each.
    snapshot = (
        ensemble.weights.normalized_weights()
        if hasattr(ensemble.weights, "normalized_weights")
        else None
    )
    if snapshot is not None:
        vals = sorted(round(v, 6) for v in snapshot.values())
        assert vals == [round(1 / 3, 6)] * 3, f"weights not pinned to 1/3: {snapshot}"

    _LOADED = Stack(
        aggregator=aggregator,
        ensemble=ensemble,
        signal_aggregator_mod=sa_mod,
        regime_mod=regime_mod,
        SignalAction=te_enums.SignalAction,
        kernels=kernels,
        ta_app=ta_app,
        clock=clock,
    )
    return _LOADED


async def run_replay(
    store: CandleStore,
    stack: Stack,
    clock: ReplayClock,
    symbols: list,
    warmup_bars: int = 300,
):
    """Walk the 60m bar-close clock for each symbol, calling the real deployed
    aggregator+ensemble stack (spec §3.1) at every decision point.

    Decision time for bar i is the CLOSE of bar i: `clock.now_ms` is set to
    bar_close_ms BEFORE the aggregator call, so `CandleStore.as_of`
    (close + step <= now_ms) serves bar i itself as the latest closed candle
    and nothing later -- matching the live forming-candle drop, no
    look-ahead. Deployed-path bugs are preserved, not fixed (spec §3.3): a
    weird/flat/degenerate signal here IS the measurement.
    """
    assert clock is stack.clock, (
        "clock must be the same object load_stack rewired the market-data "
        "transport onto -- a different instance leaves the mocked transport "
        "reading a stale now_ms while this loop advances a detached clock, "
        "silently starving as_of() of any closed bars"
    )
    import pandas as pd  # local: keeps module import light

    from killtests.candles import INTERVAL_MS

    rows = []
    step = INTERVAL_MS["60"]
    for symbol in symbols:
        f60 = store.frame(symbol, "60")
        for i in range(warmup_bars, len(f60)):
            bar_close_ms = int(f60["ts_ms"].iloc[i]) + step
            clock.now_ms = bar_close_ms
            _clear_regime_cache(stack.aggregator)
            with frozen_time(clock):  # pins time.time -> bar close (function-local imports)
                sig = await stack.aggregator.get_trading_signal_multi_timeframe(symbol, "60")
            close = float(f60["close"].iloc[i])
            ens = stack.ensemble.generate_signal(sig, current_price=close)
            rows.append(
                {
                    "symbol": symbol,
                    "ts_ms": bar_close_ms,
                    "action": sig.action.value,
                    "confidence": float(sig.confidence),
                    "aggregated_score": float(sig.aggregated_score),
                    "consensus_count": int(sig.consensus_count),
                    "ens_action": ens.action.value if ens else None,
                    "ens_confidence": float(ens.confidence) if ens else None,
                    "ens_position_size_pct": (float(ens.position_size_pct) if ens else None),
                    "close": close,
                }
            )
    return pd.DataFrame(rows)


def _clear_regime_cache(aggregator) -> None:
    # Verified location: aggregator_core.py:119 -- NOT on the aggregator itself.
    det = aggregator.core_aggregator.regime_detector
    assert det is not None, "regime detector missing -- determinism pin broken"
    det._cache.clear()


# The 5 symbols validated for position-taking (CLAUDE.md section 5); market-data
# ingests a wider 14-symbol universe for research, but trading-engine restricts
# to these.
_VALIDATED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]


def main() -> None:
    import argparse
    import asyncio

    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="backtesting/data")
    ap.add_argument("--symbols", nargs="+", default=_VALIDATED_SYMBOLS)
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--out", default=".planning/evidence/killtests/signal-series.csv")
    args = ap.parse_args()

    intervals = ["15", "60", "240", "1440"]
    store = CandleStore(args.data_dir, args.symbols, intervals)
    clock = ReplayClock(now_ms=0)
    stack = load_stack(store, clock)
    df = asyncio.run(run_replay(store, stack, clock, args.symbols, warmup_bars=args.warmup))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()
