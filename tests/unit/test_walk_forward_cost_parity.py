"""
FIX 15 — IS and OOS folds must run the same cost model.

Until 2026-08-12 run_walk_forward.py built the per-fold IS engine bare
(`BacktestEngine(initial_capital=...)`) while `run_one_fold` built the OOS
engine with `**_engine_kwargs()` — so under --realistic-sim the ADR-013
OOS/IS Sharpe-ratio gate measured the fee-model delta, not regime drift.
run_walk_forward_ensemble.py built BOTH engines bare with no way to engage
realistic costs at all. These tests drive each harness through its own CLI
wiring and assert every IS engine carries the same fee/slippage/funding
config as its OOS counterpart.
"""

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

# Same bootstrap as tests/killtests/: backtesting/ modules are top-level there.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backtesting"))

import run_walk_forward as rwf  # noqa: E402


def _cost_config(engine) -> dict:
    """Every constructor knob that changes simulated costs."""
    return {
        "fee_mode": engine.fee_mode,
        "bybit_taker_fee": engine.bybit_taker_fee,
        "bybit_maker_fee": engine.bybit_maker_fee,
        "slippage_mode": engine.slippage_mode,
        "atr_slippage_factor": engine.atr_slippage_factor,
        "atr_slippage_floor": engine.atr_slippage_floor,
        "funding_enabled": engine.funding_enabled,
        "funding_rate_per_8h": engine.funding_rate_per_8h,
        "partial_fill_volume_pct": engine.partial_fill_volume_pct,
        "commission": engine.commission,
        "slippage": engine.slippage,
    }


def _recording_engine(base_cls):
    """Real __init__ (so cost attrs are the engine's own), stubbed run loop."""

    class RecordingEngine(base_cls):
        instances: list = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            type(self).instances.append(self)

        def run_backtest(self, data, strategy_func, strategy_name="Unknown Strategy"):
            self.strategy_name = strategy_name
            self.equity_curve = [float(self.initial_capital)] * max(len(data), 2)
            self.trades = []
            return SimpleNamespace()

    return RecordingEngine


def _stub_downloader(df: pd.DataFrame):
    class StubDownloader:
        def __init__(self, *args, **kwargs):
            pass

        async def download_historical_data(self, **kwargs):
            return df

        async def close(self):
            pass

    return StubDownloader


def _bars(n: int) -> pd.DataFrame:
    # Post-2026-04-25 timestamps: clears the testnet-flip taint gate.
    ts = pd.date_range("2026-05-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1.0,
        }
    )


def test_walk_forward_is_engine_shares_oos_cost_model(monkeypatch):
    """main() with --realistic-sim: every IS engine must carry the realistic
    cost model, identical to its fold's OOS engine."""
    engine_cls = _recording_engine(rwf.BacktestEngine)
    monkeypatch.setattr(rwf, "BacktestEngine", engine_cls)
    monkeypatch.setattr(rwf, "HistoricalDataDownloader", _stub_downloader(_bars(48)))
    monkeypatch.setattr(rwf, "_GLOBAL_ENGINE_KWARGS", {})
    monkeypatch.setattr(
        sys, "argv", ["run_walk_forward.py", "--symbol", "TESTUSDT", "--realistic-sim"]
    )

    asyncio.run(rwf.main())

    is_engines = [
        e for e in engine_cls.instances if e.strategy_name.startswith("phase1_is_")
    ]
    oos_engines = [
        e
        for e in engine_cls.instances
        if e.strategy_name.startswith("phase1_prod_fold_")
    ]
    assert is_engines, "no IS engines constructed"
    assert len(is_engines) == len(oos_engines)
    for is_e, oos_e in zip(is_engines, oos_engines):
        assert _cost_config(is_e) == _cost_config(oos_e)
    # --realistic-sim must reach the IS engines, not only OOS.
    for e in is_engines:
        assert e.fee_mode == "bybit_perp"
        assert e.slippage_mode == "atr_aware"
        assert e.funding_enabled is True


def _load_ensemble():
    # Deferred: import performs the dual-namespace app.* stub dance.
    return importlib.import_module("run_walk_forward_ensemble")


def test_ensemble_realistic_sim_flag_wires_shared_cost_model(monkeypatch):
    ens = _load_ensemble()
    monkeypatch.setattr(ens, "_GLOBAL_ENGINE_KWARGS", {})

    symbols = ens._apply_cli_flags(["--realistic-sim", "SOLUSDT"])

    assert symbols == ["SOLUSDT"]
    kwargs = ens._engine_kwargs()
    assert kwargs["fee_mode"] == "bybit_perp"
    assert kwargs["slippage_mode"] == "atr_aware"
    assert kwargs["funding_enabled"] is True


def test_ensemble_is_and_oos_engines_share_cost_model(monkeypatch, tmp_path):
    ens = _load_ensemble()
    engine_cls = _recording_engine(ens.BacktestEngine)
    monkeypatch.setattr(ens, "BacktestEngine", engine_cls)
    # WARMUP_BARS + FOLDS * 30 minimum, plus slack.
    monkeypatch.setattr(
        ens,
        "HistoricalDataDownloader",
        _stub_downloader(_bars(ens.WARMUP_BARS + ens.FOLDS * 30 + 20)),
    )
    monkeypatch.setattr(ens, "_GLOBAL_ENGINE_KWARGS", {})
    ens._apply_cli_flags(["--realistic-sim"])

    with open(tmp_path / "progress.log", "w") as progress_log:
        result = asyncio.run(ens.run_symbol("TESTUSDT", str(tmp_path), progress_log))

    assert result is not None
    is_engines = [
        e for e in engine_cls.instances if e.strategy_name.startswith("ensemble_is_")
    ]
    oos_engines = [
        e for e in engine_cls.instances if e.strategy_name.startswith("ensemble_oos_")
    ]
    assert is_engines, "no IS engines constructed"
    assert len(is_engines) == len(oos_engines)
    for is_e, oos_e in zip(is_engines, oos_engines):
        assert _cost_config(is_e) == _cost_config(oos_e)
    for e in is_engines + oos_engines:
        assert e.fee_mode == "bybit_perp"
        assert e.slippage_mode == "atr_aware"
        assert e.funding_enabled is True
