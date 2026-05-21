"""
Walk-forward gate for the LIVE ensemble strategy (aggregator_core path).

Goal: produce honest edge evidence for the strategy that the auto-trader actually
runs. Prior walk-forward harnesses measured `phase1_prod` (deprecated, 0-trade
output) or `sqzmom_v2` (Phase C proposal, not deployed). Neither exercises
`services/trading-engine/app/aggregation/aggregator_core.CoreAggregator`, which
is what the live `strategy_mode=ensemble` invokes on every loop tick.

This harness imports the live CoreAggregator and drives it bar-by-bar across
180d hourly history per validated symbol. ADR-013 gate applies:
  OOS Sharpe >= 1.0, OOS/IS >= 0.6, DSR >= 0.95, max DD < 30%, PF mean >= 1.2.

Run:
  python3 backtesting/run_walk_forward_ensemble.py [SYMBOL ...]
  (no args => all five validated symbols)

Design notes:
  - Dual-namespace import: TA indicator classes (services/technical-analysis)
    and TE aggregator code (services/trading-engine) both register a package
    named `app`. We load TA indicators first, capture class refs, purge
    sys.modules["app.*"], then load TE aggregator under a stubbed `app.models`
    / `app.config` / `app.monitoring.metrics` namespace that exposes only the
    symbols aggregator_core needs. This skips TE's heavy models/__init__.py and
    config/env validation that are irrelevant to backtest.
  - SignalType (TA enum) and SignalAction (TE enum) are distinct classes with
    identical string values; we bridge with SignalAction(ta_signal.value).
  - Per-bar indicator pass is not vectorized; ~4320 bars/symbol * 10 indicators
    is tolerable (single-digit minutes per symbol).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import os
import sys
import types
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_TA_PATH = os.path.join(_REPO_ROOT, "services", "technical-analysis")
_TE_PATH = os.path.join(_REPO_ROOT, "services", "trading-engine")

sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HERE)

# ============================================================================
# PHASE 1: load TA indicators (their `from app.models import SignalType`
# resolves against TA's own `app` package).
# ============================================================================
sys.path.insert(0, _TA_PATH)
from app.indicators.rsi import RSICalculator as _RSI  # noqa: E402
from app.indicators.macd import MACDCalculator as _MACD  # noqa: E402
from app.indicators.bollinger_bands import (  # noqa: E402
    BollingerBandsCalculator as _BB,
)
from app.indicators.moving_averages import (  # noqa: E402
    SMACalculator as _SMA,
    EMACalculator as _EMA,
)
from app.indicators.stochastic import Stochastic as _Stoch  # noqa: E402
from app.indicators.ichimoku import IchimokuCalculator as _Ichi  # noqa: E402
from app.indicators.adx import ADXCalculator as _ADX  # noqa: E402
from app.indicators.atr import ATR as _ATR  # noqa: E402
from app.indicators.trend_filter import TrendFilter as _TrendFilter  # noqa: E402
from app.indicators.volume_confirmation import (  # noqa: E402
    VolumeConfirmation as _VolConf,
)

# capture TA's SignalType + the enum string values we map from
_TA_SignalType = sys.modules["app.models"].SignalType


# ============================================================================
# PHASE 2: purge `app.*` modules and the TA path so we can rebuild the
# namespace pointed at TE.
# ============================================================================
for _key in list(sys.modules.keys()):
    if _key == "app" or _key.startswith("app."):
        del sys.modules[_key]
sys.path.remove(_TA_PATH)


# ============================================================================
# PHASE 3: build a minimal stub `app.models` / `app.config` / `app.monitoring`
# package tree so aggregator_core's `from app.models import ...`,
# `from app.config import get_settings`, and signal_cache's
# `from app.monitoring.metrics import ...` resolve without dragging in
# stat_arb dependencies, env-validated Settings, or Prometheus exporters.
# ============================================================================
sys.path.insert(0, _TE_PATH)


def _load_te_module(dotted_name: str, rel_path: str):
    """Load a TE source file as a named module (registered in sys.modules)."""
    abs_path = os.path.join(_TE_PATH, rel_path)
    spec = importlib.util.spec_from_file_location(dotted_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[dotted_name] = module
    spec.loader.exec_module(module)
    return module


# Register `app` as a synthetic package so submodule registration works.
_app_pkg = types.ModuleType("app")
_app_pkg.__path__ = [_TE_PATH + "/app"]
sys.modules["app"] = _app_pkg

# Load enums + signal models directly (bypasses models/__init__.py and its
# stat_arb_models cascade).
_te_enums = _load_te_module("app.models.enums", "app/models/enums.py")
_te_signal = _load_te_module("app.models.signal", "app/models/signal.py")

# Synthesize `app.models` exposing only what aggregator_core imports.
_models_stub = types.ModuleType("app.models")
_models_stub.SignalAction = _te_enums.SignalAction
_models_stub.IndicatorSignal = _te_signal.IndicatorSignal
_models_stub.TradingSignal = _te_signal.TradingSignal
sys.modules["app.models"] = _models_stub

# Stub `app.config.get_settings`. Aggregator only reads `settings` to access
# unrelated trading params we don't need; a SimpleNamespace fallback works.
_config_stub = types.ModuleType("app.config")


def _stub_get_settings():
    return types.SimpleNamespace(
        technical_analysis_url="http://localhost:8004",
        market_data_url="http://localhost:8002",
        service_name="backtest-ensemble",
    )


_config_stub.get_settings = _stub_get_settings
sys.modules["app.config"] = _config_stub

# Stub `app.monitoring.metrics` (signal_cache imports record_cache_hit/miss).
_monitoring_pkg = types.ModuleType("app.monitoring")
_monitoring_pkg.__path__ = []
sys.modules["app.monitoring"] = _monitoring_pkg
_metrics_stub = types.ModuleType("app.monitoring.metrics")
_metrics_stub.record_cache_hit = lambda *a, **kw: None
_metrics_stub.record_cache_miss = lambda *a, **kw: None
sys.modules["app.monitoring.metrics"] = _metrics_stub

# Stub `app.aggregation` as an empty package so we can register submodules
# without triggering the real `app/aggregation/__init__.py`, which would
# eagerly load EnhancedAggregator + MultiTimeframeAnalyzer + their httpx /
# Prometheus / cross-service deps we don't need for this harness.
_aggregation_pkg = types.ModuleType("app.aggregation")
_aggregation_pkg.__path__ = [os.path.join(_TE_PATH, "app", "aggregation")]
sys.modules["app.aggregation"] = _aggregation_pkg

# Load the submodules aggregator_core needs, in dependency order.
_load_te_module("app.phase1_metrics", "app/phase1_metrics.py")
_load_te_module(
    "app.aggregation.confidence_guard", "app/aggregation/confidence_guard.py"
)
_load_te_module("app.aggregation.gatekeeper", "app/aggregation/gatekeeper.py")
_load_te_module("app.aggregation.validator", "app/aggregation/validator.py")
_load_te_module("app.aggregation.voter", "app/aggregation/voter.py")
_load_te_module("app.aggregation.signal_cache", "app/aggregation/signal_cache.py")
_load_te_module("app.aggregation.market_regime", "app/aggregation/market_regime.py")
_aggregator_core = _load_te_module(
    "app.aggregation.aggregator_core", "app/aggregation/aggregator_core.py"
)
_market_regime = sys.modules["app.aggregation.market_regime"]
SignalAction = _te_enums.SignalAction
IndicatorSignal = _te_signal.IndicatorSignal
TradingSignal = _te_signal.TradingSignal
CoreAggregator = _aggregator_core.CoreAggregator
RegimeAnalysis = _market_regime.RegimeAnalysis
MarketRegime = _market_regime.MarketRegime
TrendDirection = _market_regime.TrendDirection

# ============================================================================
# data + engine shims that already work under repo-root path
# ============================================================================
from data_downloader import HistoricalDataDownloader  # noqa: E402
from backtest_engine import BacktestEngine  # noqa: E402


# ============================================================================
# Walk-forward configuration (matches sqzmom_v2 layout)
# ============================================================================
DEFAULT_SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT", "BTCUSDT", "ETHUSDT"]
DAYS = 180  # post-2026-04-25 testnet flip
INTERVAL = "60"
FOLDS = 4
IS_FRAC = 0.75
WARMUP_BARS = 200  # 200-EMA-style indicators need ~200 bars
ATR_STOP_MULT = 1.5  # ADR-013 default
ATR_TP_MULT = 3.0  # R/R 2:1
# Honest count of distinct strategies explored on the same data window:
#   1) phase1_prod (run_walk_forward.py)
#   2..7) sqzmom_v2 L0..L5
#   8) ensemble (this run)
N_TRIALS = 8

RESULTS_SUBDIR = "wf_ensemble_2026-05-20"

# Indicator weights: live voter weight table (only non-1.0 values matter)
# Source: services/trading-engine/app/aggregation/voter.py
INDICATOR_WEIGHTS: Dict[str, float] = {
    "ICHIMOKU": 0.9,
    # RSI_DIVERGENCE/SQZMOM_ENHANCED disabled in live; not emitted here.
}

# Regime confidence modifier table (per market_regime.MarketRegimeDetector)
REGIME_MODIFIERS: Dict[str, float] = {
    "STRONG_TREND": 1.2,
    "TRENDING": 1.1,
    "WEAK_TREND": 1.0,
    "RANGING": 0.8,
    "VOLATILE": 0.7,
    "UNKNOWN": 1.0,
}


# ============================================================================
# Per-bar indicator dict builder
# ============================================================================
def _bridge_signal(ta_signal) -> SignalAction:
    """Convert TA's SignalType enum (or string) to TE's SignalAction enum."""
    if hasattr(ta_signal, "value"):
        value = ta_signal.value
    else:
        value = str(ta_signal)
    try:
        return SignalAction(value)
    except ValueError:
        # CONFIRM / REJECT / BULLISH etc. are not SignalAction values; coerce.
        if value in ("CONFIRM", "BULLISH"):
            return SignalAction.BUY
        if value in ("REJECT", "BEARISH"):
            return SignalAction.SELL
        return SignalAction.HOLD


def _wrap(
    name: str,
    signal: SignalAction,
    confidence: float,
    value: Optional[float] = None,
    **meta,
) -> IndicatorSignal:
    md = dict(meta)
    if name in INDICATOR_WEIGHTS:
        md.setdefault("weight", INDICATOR_WEIGHTS[name])
    else:
        md.setdefault("weight", 1.0)
    return IndicatorSignal(
        name=name,
        signal=signal,
        confidence=float(max(0.0, min(1.0, confidence))),
        value=value,
        metadata=md,
    )


def _compute_indicators(hist: pd.DataFrame) -> Optional[Dict]:
    """Run all indicator calculators on hist[:idx+1] and return raw outputs.

    Returns None if any required indicator can't compute (warmup not satisfied).
    """
    closes = hist["close"].astype(float)
    highs = hist["high"].astype(float).tolist()
    lows = hist["low"].astype(float).tolist()
    close_list = closes.tolist()
    vol_list = hist["volume"].astype(float).tolist()
    current_price = float(closes.iloc[-1])

    try:
        rsi_val, rsi_sig, rsi_conf = _RSI(period=9).calculate_with_signal(hist)
        if rsi_val is None:
            return None
        macd_val, macd_sig, macd_conf = _MACD(
            fast_period=8, slow_period=17, signal_period=9
        ).calculate_with_signal(hist)
        if macd_val is None:
            return None
        bb_data, bb_sig, bb_conf = _BB(period=20, std_dev=2.5).calculate_with_signal(
            hist
        )
        if bb_data is None:
            return None

        sma_calc = _SMA(period=21)
        sma_val = sma_calc.calculate(hist)
        if sma_val is None:
            return None
        sma_sig, sma_conf = sma_calc.generate_signal(sma_val, current_price)

        ema_calc = _EMA(period=21)
        ema_val = ema_calc.calculate(hist)
        if ema_val is None:
            return None
        ema_sig, ema_conf = ema_calc.generate_signal(ema_val, current_price)

        stoch = _Stoch().calculate(highs, lows, close_list)
        ichi_dict = _Ichi().calculate(hist)
        if ichi_dict is None:
            return None
        ichi_sig, ichi_conf = _Ichi().generate_signal(ichi_dict)

        adx = _ADX(period=14).calculate(highs, lows, close_list)
        atr = _ATR(period=14).calculate(highs, lows, close_list, current_price)
        trend = _TrendFilter().calculate(close_list)
        vol = _VolConf().calculate(vol_list)
    except Exception as exc:  # noqa: BLE001
        # Surface unexpected failures but don't crash the whole walk-forward.
        print(f"  indicator-error: {exc}")
        return None

    return {
        "rsi": (rsi_val, _bridge_signal(rsi_sig), rsi_conf),
        "macd": (
            macd_val.get("histogram") if isinstance(macd_val, dict) else macd_val,
            _bridge_signal(macd_sig),
            macd_conf,
        ),
        "bb": (bb_data, _bridge_signal(bb_sig), bb_conf),
        "sma": (sma_val, _bridge_signal(sma_sig), sma_conf),
        "ema": (ema_val, _bridge_signal(ema_sig), ema_conf),
        "stoch": stoch,
        "ichi": (ichi_dict, _bridge_signal(ichi_sig), ichi_conf),
        "adx": adx,
        "atr": atr,
        "trend": trend,
        "vol": vol,
        "current_price": current_price,
    }


def _build_indicator_dict(ind_out: Dict) -> Dict[str, IndicatorSignal]:
    rsi_v, rsi_s, rsi_c = ind_out["rsi"]
    macd_v, macd_s, macd_c = ind_out["macd"]
    bb_d, bb_s, bb_c = ind_out["bb"]
    sma_v, sma_s, sma_c = ind_out["sma"]
    ema_v, ema_s, ema_c = ind_out["ema"]
    stoch = ind_out["stoch"]
    ichi_d, ichi_s, ichi_c = ind_out["ichi"]
    adx = ind_out["adx"]
    trend = ind_out["trend"]
    vol = ind_out["vol"]

    indicators: Dict[str, IndicatorSignal] = {}
    indicators["RSI"] = _wrap("RSI", rsi_s, rsi_c, value=rsi_v, period=9)
    indicators["MACD"] = _wrap("MACD", macd_s, macd_c, value=macd_v)
    indicators["BOLLINGER_BANDS"] = _wrap(
        "BOLLINGER_BANDS",
        bb_s,
        bb_c,
        value=bb_d.get("current_price"),
        upper_band=bb_d.get("upper_band"),
        middle_band=bb_d.get("middle_band"),
        lower_band=bb_d.get("lower_band"),
    )
    indicators["SMA"] = _wrap("SMA", sma_s, sma_c, value=sma_v)
    indicators["EMA"] = _wrap("EMA", ema_s, ema_c, value=ema_v)
    indicators["STOCHASTIC"] = _wrap(
        "STOCHASTIC",
        _bridge_signal(stoch.get("signal", "HOLD")),
        float(stoch.get("confidence", 0.0)),
        value=stoch.get("k"),
    )
    indicators["ICHIMOKU"] = _wrap(
        "ICHIMOKU",
        ichi_s,
        ichi_c,
        value=ichi_d.get("current_price"),
        role="MULTI_ASPECT_TREND",
    )
    # ADX as TREND_GATE leg (live signal_aggregator.fetch_adx pattern).
    adx_direction = adx.get("direction", "NEUTRAL")
    if adx.get("adx", 0) >= 20 and adx_direction == "BULLISH":
        adx_sig = SignalAction.BUY
    elif adx.get("adx", 0) >= 20 and adx_direction == "BEARISH":
        adx_sig = SignalAction.SELL
    else:
        adx_sig = SignalAction.HOLD
    indicators["ADX"] = _wrap(
        "ADX",
        adx_sig,
        float(adx.get("confidence", 0.0)),
        value=adx.get("adx"),
        role="TREND_GATE",
    )

    # GATEKEEPER + VALIDATOR legs (non-voting; aggregator filters them).
    indicators["TREND_FILTER"] = _wrap(
        "TREND_FILTER",
        _bridge_signal(trend.get("signal", "HOLD")),
        float(trend.get("confidence", 0.0)),
        value=trend.get("spread_pct"),
        trend=trend.get("trend"),
    )
    indicators["VOLUME_CONFIRMATION"] = _wrap(
        "VOLUME_CONFIRMATION",
        _bridge_signal(vol.get("signal", "REJECT")),
        float(vol.get("confidence", 0.0)),
        value=vol.get("volume_ratio"),
        confirmed=vol.get("confirmed"),
        strength=vol.get("strength"),
    )
    return indicators


def _build_regime(adx_out: Dict) -> RegimeAnalysis:
    regime_str = adx_out.get("regime", "UNKNOWN")
    direction_str = adx_out.get("direction", "NEUTRAL")
    try:
        regime = MarketRegime(regime_str)
    except ValueError:
        regime = MarketRegime.UNKNOWN
    try:
        direction = TrendDirection(direction_str)
    except ValueError:
        direction = TrendDirection.NEUTRAL
    return RegimeAnalysis(
        regime=regime,
        direction=direction,
        adx=float(adx_out.get("adx", 0.0)),
        plus_di=float(adx_out.get("plus_di", 0.0)),
        minus_di=float(adx_out.get("minus_di", 0.0)),
        confidence=float(adx_out.get("confidence", 0.5)),
        confidence_modifier=REGIME_MODIFIERS.get(regime.value, 1.0),
        description=adx_out.get("description", ""),
        strategy_recommendation="ensemble-backtest",
    )


# ============================================================================
# Strategy factory: returns the (row, position, idx, data) callable
# that BacktestEngine expects.
# ============================================================================
def make_ensemble_strategy(aggregator: CoreAggregator) -> Callable:
    def strategy(row, position, idx, data: pd.DataFrame):
        if idx < WARMUP_BARS:
            return None
        hist = data.iloc[: idx + 1]
        ind_out = _compute_indicators(hist)
        if ind_out is None:
            return None

        indicators = _build_indicator_dict(ind_out)
        regime = _build_regime(ind_out["adx"])
        atr = ind_out["atr"]

        timestamp_ms = (
            int(pd.Timestamp(row.name).timestamp() * 1000)
            if hasattr(row, "name") and row.name is not None
            else int(pd.Timestamp(hist.index[-1]).timestamp() * 1000)
        )

        signal = aggregator.aggregate_signals(
            indicators=indicators,
            timestamp=timestamp_ms,
            atr_data=atr,
            regime_analysis=regime,
        )

        action = (
            signal.action.value
            if hasattr(signal.action, "value")
            else str(signal.action)
        )
        if action == "BUY":
            return {
                "action": "BUY",
                "stop_loss": atr.get("stop_loss_long"),
                "take_profit": atr.get("take_profit_long"),
                "metadata": {
                    "confidence": signal.confidence,
                    "aggregated_score": signal.aggregated_score,
                    "consensus": signal.consensus_count,
                    "strategy": "ensemble_backtest",
                },
            }
        if action == "SELL":
            return {
                "action": "SELL",
                "stop_loss": atr.get("stop_loss_short"),
                "take_profit": atr.get("take_profit_short"),
                "metadata": {
                    "confidence": signal.confidence,
                    "aggregated_score": signal.aggregated_score,
                    "consensus": signal.consensus_count,
                    "strategy": "ensemble_backtest",
                },
            }
        return None

    return strategy


# ============================================================================
# Fold splitter + metrics (copied from sqzmom_v2 harness for consistency)
# ============================================================================
def calc_sharpe(equity_curve, periods_per_year: int = 24 * 365) -> float:
    if len(equity_curve) < 2:
        return 0.0
    arr = np.asarray(equity_curve, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    if rets.std(ddof=0) == 0:
        return 0.0
    return float(rets.mean() / rets.std(ddof=0) * math.sqrt(periods_per_year))


def split_folds(data: pd.DataFrame, n_folds: int, is_frac: float = 0.75):
    n = len(data)
    folds = []
    for k in range(n_folds):
        split_end = round((k + 1) / n_folds * n)
        split_is = round(split_end * is_frac)
        if split_end - split_is < 1:
            continue
        folds.append((data.iloc[:split_is], data.iloc[split_is:split_end]))
    return folds


def deflated_sharpe(sr_obs: float, n_trials: int, n_obs: int) -> float:
    if n_obs <= 1:
        return 0.0
    if n_trials <= 1:
        n_trials = 2
    from scipy.stats import norm

    expected_max_sr = (1 - np.euler_gamma) * norm.ppf(
        1 - 1.0 / n_trials
    ) + np.euler_gamma * norm.ppf(1 - 1.0 / (n_trials * np.e))
    z = (sr_obs - expected_max_sr) * math.sqrt(n_obs - 1)
    return float(norm.cdf(z))


# ============================================================================
# Symbol driver
# ============================================================================
async def run_symbol(symbol: str, out_dir: str, progress_log) -> Optional[Dict]:
    line = f"\n=== {symbol} ===\n"
    print(line, end="")
    progress_log.write(line)
    progress_log.flush()

    downloader = HistoricalDataDownloader(market_data_url="http://localhost:8002")
    raw = await downloader.download_historical_data(
        symbol=symbol, interval=INTERVAL, days=DAYS
    )
    await downloader.close()

    if raw is None or len(raw) == 0:
        msg = f"  FAIL: no data for {symbol}\n"
        print(msg, end="")
        progress_log.write(msg)
        return None

    # is_mainnet guard (ADR-013 testnet-taint rule).
    if "is_mainnet" in raw.columns:
        before = len(raw)
        raw = raw[raw["is_mainnet"] == True]  # noqa: E712
        dropped = before - len(raw)
        if dropped:
            note = f"  filtered {dropped} testnet rows; {len(raw)} mainnet kept\n"
            print(note, end="")
            progress_log.write(note)

    if "timestamp" in raw.columns:
        ts = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw.assign(timestamp=ts).set_index("timestamp")

    if len(raw) < WARMUP_BARS + FOLDS * 30:
        msg = f"  FAIL: insufficient bars ({len(raw)}) after filter\n"
        print(msg, end="")
        progress_log.write(msg)
        return None

    folds = split_folds(raw, FOLDS, IS_FRAC)
    aggregator = CoreAggregator(enable_market_regime=True)
    strategy = make_ensemble_strategy(aggregator)

    is_sharpes: List[float] = []
    oos_sharpes: List[float] = []
    fold_rows: List[Tuple] = []

    for k, (is_slice, oos_slice) in enumerate(folds):
        # In-sample (rule-based: same strategy applied to IS slice).
        is_engine = BacktestEngine(initial_capital=10000.0)
        is_engine.run_backtest(is_slice, strategy, strategy_name=f"ensemble_is_{k}")
        is_sharpe = calc_sharpe(is_engine.equity_curve)
        is_sharpes.append(is_sharpe)

        # Out-of-sample.
        oos_engine = BacktestEngine(initial_capital=10000.0)
        oos_result = oos_engine.run_backtest(
            oos_slice, strategy, strategy_name=f"ensemble_oos_{k}"
        )
        oos_sharpe = calc_sharpe(oos_engine.equity_curve)
        oos_sharpes.append(oos_sharpe)

        fold_rows.append(
            (
                k,
                len(oos_slice),
                len(oos_engine.trades),
                getattr(oos_result, "win_rate", 0.0),
                oos_sharpe,
                getattr(oos_result, "max_drawdown_pct", 0.0),
                getattr(oos_result, "profit_factor", 0.0),
                getattr(oos_result, "total_profit_loss_pct", 0.0),
            )
        )

    # Pretty per-fold print.
    hdr = (
        f"  {'Fold':<6} {'Bars':<7} {'Trades':<8} {'WR%':<7} "
        f"{'Sharpe':<8} {'DD%':<8} {'PF':<6} {'PnL%':<7}\n"
    )
    print(hdr, end="")
    progress_log.write(hdr)
    for r in fold_rows:
        k, b, t, wr, s, dd, pf, pl = r
        ln = (
            f"  {k:<6} {b:<7} {t:<8} {wr:<7.1f} {s:<8.2f} "
            f"{dd:<8.2f} {pf:<6.2f} {pl:<7.2f}\n"
        )
        print(ln, end="")
        progress_log.write(ln)

    is_mean = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    oos_mean = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    ratio = (oos_mean / is_mean) if is_mean > 0 else 0.0
    n_obs_total = sum(len(oos_slice) for _, oos_slice in folds)
    dsr = deflated_sharpe(oos_mean, N_TRIALS, n_obs_total)
    pf_mean = float(np.mean([r[6] for r in fold_rows])) if fold_rows else 0.0
    max_dd_pct = float(max((abs(r[5]) for r in fold_rows), default=0.0))

    # Gate (ADR-013).
    fail: List[str] = []
    if oos_mean < 1.0:
        fail.append(f"OOS Sharpe {oos_mean:.2f} < 1.00")
    if ratio < 0.6:
        fail.append(f"OOS/IS ratio {ratio:.2f} < 0.60")
    if dsr < 0.95:
        fail.append(f"DSR {dsr:.2f} < 0.95")
    if max_dd_pct > 30.0:
        fail.append(f"Max DD {max_dd_pct:.2f}% > 30%")
    if pf_mean < 1.2:
        fail.append(f"PF mean {pf_mean:.2f} < 1.20")

    verdict = "PASS" if not fail else "FAIL"

    summary = (
        "================================================================================\n"
        f"WALK-FORWARD RESULTS — {symbol} {INTERVAL}m {DAYS}d (ensemble strategy)\n"
        "================================================================================\n"
        f"{'fold':<5}{'bars':>6}{'trades':>8}{'WR%':>8}{'Sharpe':>10}{'maxDD%':>10}{'PF':>8}{'PnL%':>10}\n"
    )
    for r in fold_rows:
        k, b, t, wr, s, dd, pf, pl = r
        summary += (
            f"{k:<5}{b:>6}{t:>8}{wr:>8.1f}{s:>10.2f}{dd:>10.2f}{pf:>8.2f}{pl:>10.2f}\n"
        )
    summary += (
        "--------------------------------------------------------------------------------\n"
        f"IS Sharpe mean : {is_mean:+.3f}\n"
        f"OOS Sharpe mean: {oos_mean:+.3f}\n"
        f"OOS/IS ratio   : {ratio:+.3f}  (gate >= 0.60)\n"
        f"DSR            : {dsr:.3f}  (gate >= 0.95)\n"
        f"PF mean        : {pf_mean:.3f}  (gate >= 1.20)\n"
        f"Max DD         : {max_dd_pct:.2f}%  (gate < 30%)\n"
        f"Gate passed    : {verdict == 'PASS'}\n"
    )
    if fail:
        summary += "Gate failures  :\n"
        for f in fail:
            summary += f"  - {f}\n"
    summary += "================================================================================\n"

    print(summary)
    progress_log.write(summary)
    progress_log.flush()

    out_path = os.path.join(out_dir, f"{symbol}_summary.txt")
    with open(out_path, "w") as fh:
        fh.write(summary)

    return {
        "symbol": symbol,
        "oos_sharpe_mean": oos_mean,
        "is_sharpe_mean": is_mean,
        "ratio": ratio,
        "dsr": dsr,
        "pf_mean": pf_mean,
        "max_dd_pct": max_dd_pct,
        "verdict": verdict,
        "fail_reasons": fail,
    }


async def main():
    symbols = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SYMBOLS
    out_dir = os.path.join(_HERE, "results", RESULTS_SUBDIR)
    os.makedirs(out_dir, exist_ok=True)
    progress_path = os.path.join(out_dir, "_progress.log")
    results: List[Dict] = []
    with open(progress_path, "a") as progress_log:
        progress_log.write(
            f"\n# run {pd.Timestamp.utcnow().isoformat()} — symbols={symbols}\n"
        )
        for symbol in symbols:
            r = await run_symbol(symbol, out_dir, progress_log)
            if r is not None:
                results.append(r)

    print(
        "\n================================================================================"
    )
    print(f"ENSEMBLE WALK-FORWARD — {len(results)}/{len(symbols)} symbols ran")
    print(
        "================================================================================"
    )
    for r in results:
        print(
            f"  {r['symbol']:8s} verdict={r['verdict']}  "
            f"OOS Sharpe={r['oos_sharpe_mean']:+.2f}  "
            f"DSR={r['dsr']:.2f}  "
            f"PF={r['pf_mean']:.2f}  "
            f"DD={r['max_dd_pct']:.2f}%"
        )
        if r["fail_reasons"]:
            for fr in r["fail_reasons"]:
                print(f"      - {fr}")


if __name__ == "__main__":
    asyncio.run(main())
