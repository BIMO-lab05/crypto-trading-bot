"""Offline replay of the DEPLOYED ensemble signal chain (spec §3.1).

Seam: real TA FastAPI app served in-process via httpx.ASGITransport; real
SignalAggregator / MTF / CoreAggregator / MultiStrategyEnsemble loaded via
the dual-namespace shim pattern proven by run_walk_forward_ensemble.py:58-191.
Only the market-data HTTP boundary is faked (MockTransport -> CandleStore).

MUST be loaded once per process (TA app registers Prometheus collectors in
the global registry; a second import raises Duplicated timeseries).
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
    kernels: (
        dict  # {'deflated_sharpe_ratio', 'CombinatorialPurgedCV', 'cpcv_to_dsr', ...}
    )
    ta_app: object
    clock: ReplayClock


_LOADED: Stack = None


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

    sm = _spec_load(
        "_killtests_sharpe_metrics", os.path.join(_RM_PATH, "app", "sharpe_metrics.py")
    )
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


def _mk_market_data_transport(
    store: CandleStore, clock: ReplayClock
) -> httpx.MockTransport:
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

    def _stub_get_settings():
        return types.SimpleNamespace(
            technical_analysis_url="http://ta.offline",
            market_data_url="http://md.offline",
            service_name="killtests-offline-ensemble",
            max_risk_per_trade=DEFAULTS["MAX_RISK_PER_TRADE"],
            ensemble_min_position_pct=0.05,
            ensemble_confidence_size_multiplier=3.7,
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

    aggregation_pkg = types.ModuleType("app.aggregation")
    aggregation_pkg.__path__ = [os.path.join(_TE_PATH, "app", "aggregation")]
    sys.modules["app.aggregation"] = aggregation_pkg

    _load_te_module("app.phase1_metrics", "app/phase1_metrics.py")
    _load_te_module(
        "app.aggregation.confidence_guard", "app/aggregation/confidence_guard.py"
    )
    _load_te_module("app.aggregation.gatekeeper", "app/aggregation/gatekeeper.py")
    _load_te_module("app.aggregation.validator", "app/aggregation/validator.py")
    _load_te_module("app.aggregation.voter", "app/aggregation/voter.py")
    _load_te_module("app.aggregation.signal_cache", "app/aggregation/signal_cache.py")
    # signal_aggregator.py:23 `from app.aggregation.ml_gate_reasons import
    # log_ml_disabled` — not in the brief's stub set; discovered by grepping
    # signal_aggregator.py's import block. No further app.* deps of its own.
    _load_te_module(
        "app.aggregation.ml_gate_reasons", "app/aggregation/ml_gate_reasons.py"
    )
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

    _load_te_module(
        "app.strategies.simple_rsi_strategy", "app/strategies/simple_rsi_strategy.py"
    )
    _load_te_module(
        "app.strategies.mean_reversion_strategy",
        "app/strategies/mean_reversion_strategy.py",
    )
    mse_mod = _load_te_module(
        "app.strategies.multi_strategy_ensemble",
        "app/strategies/multi_strategy_ensemble.py",
    )

    return sa_mod, mse_mod, te_enums, regime_mod


def _swap_httpx_clients(
    obj, transport: httpx.AsyncBaseTransport, base_url: str
) -> None:
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
    global _LOADED
    if _LOADED is not None:
        raise RuntimeError(
            "load_stack may only run once per process (Prometheus registry)"
        )

    kernels = _load_kernels()
    ta_app, ta_fetcher_mod = _load_ta_app()

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
            return httpx.AsyncClient(
                transport=ta_transport, base_url="http://ta.offline", **kw
            )

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
