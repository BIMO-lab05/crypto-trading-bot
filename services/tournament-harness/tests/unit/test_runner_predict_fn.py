"""Unit tests for app.runner.predict_fn.build_predict_fn (Phase 4 plan 04-07).

Resolves:
  - B3: predict_fn callable for ensemble re-hydration (was deferred between
        04-01/04-03/04-06).
  - B1 (static portion): klines reads route through canonical
        load_klines_from_timescale; no raw SQL in predict_fn.

Contract under test:
  build_predict_fn(snapshot) → callable(row) → {pred_prices, actual_prices, last_close}
  - 1-D numpy arrays of equal positive length.
  - Deterministic for same (snapshot, row) inputs (D-13 reproducibility).
  - tournament_id and run_id validated for path-traversal BEFORE any DB / model load.
  - Symbol must end with "USDT" (mirrors canonical loader's assertion).
  - Status must be "success" (snapshot pre-filters; predict_fn double-checks).
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest


# Source file path used by static-check tests (no raw SQL / canonical import).
HARNESS_ROOT = Path(__file__).resolve().parents[2]
PREDICT_FN_SOURCE = HARNESS_ROOT / "app" / "runner" / "predict_fn.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_klines_df():
    """Small deterministic OHLCV DataFrame returned by the mocked klines loader.

    `load_klines_from_timescale` is monkeypatched so the 50K-row floor never
    fires; we only need enough rows to feed create_sequences past its own
    minimum (sequence_length + horizon).
    """
    n = 200
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 0.5, n))
    timestamps = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base,
            "high": base + 0.1,
            "low": base - 0.1,
            "close": base,
            "volume": np.full(n, 1000.0),
        }
    )


@pytest.fixture
def stub_core_modules(monkeypatch, synthetic_klines_df):
    """Inject fake `app.core.stationary_features` and `app.core.models` modules.

    `app.core.*` does not resolve on the host pytest runner because the
    tournament-harness `app/` package is the only one on sys.path (see
    04-01 SUMMARY deviation note). For unit tests we inject lightweight stubs
    via sys.modules; predict_fn's lazy imports pick them up at call time.
    """
    feature_cols = ["close", "open", "high", "low", "volume"]

    def _compute_stationary_features(df: pd.DataFrame) -> pd.DataFrame:
        # Add a log_returns column so target_mode='log_returns' would work too,
        # but predict_fn uses 'close' for OOS reconstruction — keep simple.
        out = df.copy()
        out["log_returns"] = np.log(out["close"] / out["close"].shift(1)).fillna(0.0)
        return out

    fake_sf = types.ModuleType("app.core.stationary_features")
    fake_sf.STATIONARY_FEATURE_COLS = tuple(feature_cols)
    fake_sf.compute_stationary_features = _compute_stationary_features

    # Stub builder/model: model.predict(X) returns mean of each window — deterministic.
    class _StubModel:
        def __init__(self, horizon: int):
            self.horizon = horizon
            self.history = MagicMock()
            self.history.history = {"loss": [1.0, 0.5], "val_loss": [1.0, 0.5]}

        def fit(self, *args, **kwargs):
            return self.history

        def predict(self, X, verbose=0):
            # Deterministic transform: mean across the lookback window per feature.
            arr = np.asarray(X, dtype=np.float32)
            mean = arr.mean(axis=(1, 2)).reshape(-1, 1)
            # Repeat across horizon
            return np.repeat(mean, self.horizon, axis=1)

    class _StubBuilder:
        def build(self, *, input_shape, hp):
            horizon = int(hp.get("horizon", 1))
            return _StubModel(horizon)

    fake_models = types.ModuleType("app.core.models")
    fake_models.REGISTRY = {"gru": _StubBuilder(), "lstm": _StubBuilder()}

    fake_core = types.ModuleType("app.core")
    fake_core.stationary_features = fake_sf
    fake_core.models = fake_models

    monkeypatch.setitem(sys.modules, "app.core", fake_core)
    monkeypatch.setitem(sys.modules, "app.core.stationary_features", fake_sf)
    monkeypatch.setitem(sys.modules, "app.core.models", fake_models)

    # Mock the canonical klines loader.
    import app.runner.data as data_mod

    call_log = {"count": 0, "kwargs": None}

    def _fake_loader(*, symbol, interval, end_ts, days_back=365):
        call_log["count"] += 1
        call_log["kwargs"] = {
            "symbol": symbol,
            "interval": interval,
            "end_ts": end_ts,
            "days_back": days_back,
        }
        return synthetic_klines_df.copy(), False

    monkeypatch.setattr(data_mod, "load_klines_from_timescale", _fake_loader)

    # Also patch the import inside predict_fn module if it's already imported.
    # (predict_fn does `from app.runner.data import load_klines_from_timescale`,
    # which binds at import time. monkeypatch the bound name.)
    try:
        import app.runner.predict_fn as pf_mod

        monkeypatch.setattr(pf_mod, "load_klines_from_timescale", _fake_loader)
    except Exception:
        # Module not importable yet (RED phase) — that's expected.
        pass

    return call_log


@pytest.fixture
def good_snapshot(synthetic_snapshot_dict):
    """A safe snapshot with valid IDs."""
    snap = synthetic_snapshot_dict(
        symbols=("BTCUSDT",), runs_per_symbol=2, tournament_id="t-04-07-test"
    )
    # First row is the success row in synthetic_snapshot_dict (failed = last index).
    return snap


@pytest.fixture
def good_row(good_snapshot):
    """First success row from BTCUSDT."""
    for r in good_snapshot["rows"]:
        if r["status"] == "success":
            # Inject hp + interval that match __main__.py spec shape.
            r = dict(r)
            r["interval"] = "5m"
            r["result_json"] = dict(r["result_json"])
            r["result_json"]["hyperparameters"] = {
                "lookback": 10,
                "batch": 8,
                "epochs": 1,
            }
            r["result_json"]["interval"] = "5m"
            r["result_json"]["seed"] = 42
            r["result_json"]["label_horizon"] = 1
            return r
    raise RuntimeError("synthetic snapshot has no success row")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_predict_fn_shape_contract(stub_core_modules, good_snapshot, good_row):
    """build_predict_fn returns a dict with three 1-D equal-length arrays."""
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    out = predict(good_row)
    assert set(out.keys()) == {"pred_prices", "actual_prices", "last_close"}
    pred = out["pred_prices"]
    actual = out["actual_prices"]
    last = out["last_close"]
    assert isinstance(pred, np.ndarray)
    assert isinstance(actual, np.ndarray)
    assert isinstance(last, np.ndarray)
    assert pred.ndim == 1
    assert actual.ndim == 1
    assert last.ndim == 1
    assert len(pred) > 0
    assert len(pred) == len(actual) == len(last)


def test_predict_fn_uses_canonical_klines_loader(
    stub_core_modules, good_snapshot, good_row
):
    """Loader called exactly once with end_ts=tournament_start_ts and days_back=365."""
    from datetime import datetime
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    predict(good_row)

    assert stub_core_modules["count"] == 1, (
        f"expected exactly 1 loader call, got {stub_core_modules['count']}"
    )
    kw = stub_core_modules["kwargs"]
    assert kw["days_back"] == 365, "CD-11 requires 365-day OOS window"
    assert kw["symbol"] == "BTCUSDT"
    expected_end = datetime.fromisoformat(
        good_snapshot["config"]["tournament_start_ts"].replace("Z", "+00:00")
    )
    assert kw["end_ts"] == expected_end


def test_predict_fn_does_not_call_raw_sql():
    """Static check: predict_fn.py contains no raw SELECT — all klines via canonical reader."""
    src = PREDICT_FN_SOURCE.read_text()
    # Strip docstrings/comments by splitting on lines starting with # OR inside triple-quotes.
    # Simple heuristic — predict_fn must not have raw SELECT outside docstrings.
    # We accept the literal 'SELECT' inside triple-quoted docstrings if present;
    # easier: just require no SELECT at all (canonical loader is the only path).
    no_sql = re.search(r"\bSELECT\s+", src, re.IGNORECASE) is None
    no_from_klines = re.search(r"\bFROM\s+klines\b", src, re.IGNORECASE) is None
    assert no_sql, (
        "predict_fn.py contains raw SELECT — must use load_klines_from_timescale"
    )
    assert no_from_klines, "predict_fn.py references klines table directly"


def test_predict_fn_imports_canonical_loader():
    """Static check: predict_fn must import the canonical loader by name."""
    src = PREDICT_FN_SOURCE.read_text()
    assert "from app.runner.data import load_klines_from_timescale" in src, (
        "predict_fn.py must import the canonical klines reader"
    )


def test_predict_fn_is_mainnet_filter_evidenced():
    """Static check: predict_fn references is_mainnet (docstring/comment trail for B1 audit)."""
    src = PREDICT_FN_SOURCE.read_text()
    assert "is_mainnet" in src, (
        "predict_fn.py must mention is_mainnet (in docstring/comment) "
        "documenting that the canonical loader enforces is_mainnet=TRUE"
    )


def test_predict_fn_determinism_same_inputs_same_outputs(
    stub_core_modules, good_snapshot, good_row
):
    """Two invocations with same inputs return numpy-equal arrays (D-13)."""
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    out1 = predict(good_row)
    out2 = predict(good_row)
    np.testing.assert_array_equal(out1["pred_prices"], out2["pred_prices"])
    np.testing.assert_array_equal(out1["actual_prices"], out2["actual_prices"])
    np.testing.assert_array_equal(out1["last_close"], out2["last_close"])


def test_predict_fn_path_traversal_rejected_in_run_id(
    stub_core_modules, good_snapshot, good_row
):
    """Path-traversal-shaped run_id raises ValueError BEFORE any DB / model work."""
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    bad_inputs = ["../etc", "bad/id", "x\x00y", "id with space", "..\\win"]
    for bad in bad_inputs:
        bad_row = dict(good_row)
        bad_row["run_id"] = bad
        with pytest.raises(ValueError, match="run_id"):
            predict(bad_row)
    # Loader must NOT be called for any of those rejections.
    assert stub_core_modules["count"] == 0, (
        "loader should never run when run_id fails validation"
    )


def test_predict_fn_path_traversal_rejected_in_tournament_id(
    stub_core_modules, good_snapshot
):
    """Path-traversal-shaped tournament_id raises ValueError at factory build time."""
    from app.runner.predict_fn import build_predict_fn

    bad_snap = dict(good_snapshot)
    bad_snap["tournament_id"] = "../etc"
    with pytest.raises(ValueError, match="tournament_id"):
        build_predict_fn(bad_snap)


def test_predict_fn_status_failed_row_rejected(
    stub_core_modules, good_snapshot, good_row
):
    """Row with status != 'success' is rejected (snapshot pre-filters; predict_fn double-checks)."""
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    bad_row = dict(good_row)
    bad_row["status"] = "failed"
    with pytest.raises(ValueError, match="(?i)success|status"):
        predict(bad_row)


def test_predict_fn_assert_symbol_usdt_suffix(
    stub_core_modules, good_snapshot, good_row
):
    """Row with non-USDT symbol raises AssertionError (mirrors canonical loader's defense)."""
    from app.runner.predict_fn import build_predict_fn

    predict = build_predict_fn(good_snapshot)
    bad_row = dict(good_row)
    bad_row["symbol"] = "BTC"  # bare base, no USDT suffix
    with pytest.raises(AssertionError, match="USDT"):
        predict(bad_row)
