"""Unit tests for app.significance.predict_cache (Phase 4 plan 04-01 Task 3).

Covers CD-11 cache-path layout, hit/miss semantics, atomic .npz write,
T-04-01 path-traversal guard on tournament_id and run_id, and the pure-numpy
log_returns_from_predictions helper.
"""

from __future__ import annotations


import numpy as np
import pytest

from app.significance.predict_cache import (
    _cache_path,
    get_or_build_predictions,
    log_returns_from_predictions,
)


def _make_payload(n: int = 10):
    rng = np.random.default_rng(0)
    last_close = 100 + rng.normal(0, 1, n)
    pred_prices = last_close + rng.normal(0, 0.1, n)
    actual_prices = last_close + rng.normal(0, 0.1, n)
    return {
        "pred_prices": pred_prices,
        "actual_prices": actual_prices,
        "last_close": last_close,
    }


def test_cache_path_is_per_tournament_per_run(tmp_path):
    """CD-11: data/cache/{tournament_id}/predictions/{run_id}.npz under harness root."""
    p = _cache_path(tmp_path, "t1", "r1")
    assert p == tmp_path / "data" / "cache" / "t1" / "predictions" / "r1.npz"


def test_cache_hit_returns_existing_array_without_recompute(tmp_path):
    """Pre-write a .npz; predict callback must NOT be invoked on hit."""
    expected = _make_payload(8)
    cache_file = _cache_path(tmp_path, "t1", "r1")
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    np.savez(cache_file, **expected)

    calls = {"n": 0}

    def predict_fn():
        calls["n"] += 1
        raise AssertionError("predict_fn must NOT be called on cache hit")

    got = get_or_build_predictions(
        harness_root=tmp_path,
        tournament_id="t1",
        run_id="r1",
        predict_fn=predict_fn,
    )
    assert calls["n"] == 0
    np.testing.assert_array_equal(got["pred_prices"], expected["pred_prices"])
    np.testing.assert_array_equal(got["actual_prices"], expected["actual_prices"])
    np.testing.assert_array_equal(got["last_close"], expected["last_close"])


def test_cache_miss_invokes_predict_callback_then_persists(tmp_path):
    payload = _make_payload(12)
    calls = {"n": 0}

    def predict_fn():
        calls["n"] += 1
        return payload

    got = get_or_build_predictions(
        harness_root=tmp_path,
        tournament_id="t1",
        run_id="r1",
        predict_fn=predict_fn,
    )
    assert calls["n"] == 1
    cache_file = _cache_path(tmp_path, "t1", "r1")
    assert cache_file.exists()
    np.testing.assert_array_equal(got["pred_prices"], payload["pred_prices"])

    # Subsequent call hits cache and does not invoke the callback again.
    got2 = get_or_build_predictions(
        harness_root=tmp_path,
        tournament_id="t1",
        run_id="r1",
        predict_fn=predict_fn,
    )
    assert calls["n"] == 1, "second call must hit cache"
    np.testing.assert_array_equal(got2["pred_prices"], payload["pred_prices"])


def test_log_returns_from_predictions():
    """Pure helper: log(pred / last_close) per row."""
    pred = np.array([110.0, 90.0, 100.0])
    last = np.array([100.0, 100.0, 100.0])
    out = log_returns_from_predictions(pred, last)
    expected = np.log(pred / last)
    np.testing.assert_allclose(out, expected, rtol=1e-12)


def test_atomic_npz_write_no_partial(tmp_path):
    payload = _make_payload(5)
    get_or_build_predictions(
        harness_root=tmp_path,
        tournament_id="t1",
        run_id="r1",
        predict_fn=lambda: payload,
    )
    leftovers = list((tmp_path / "data" / "cache" / "t1" / "predictions").glob("*.tmp"))
    assert leftovers == [], f".npz.tmp leftovers: {leftovers}"


def test_invalid_tournament_id_rejected(tmp_path):
    """T-04-01: refuse path-traversal sequences in tournament_id."""
    with pytest.raises(ValueError, match="invalid tournament_id"):
        _cache_path(tmp_path, "../etc/passwd", "r1")
    with pytest.raises(ValueError, match="invalid tournament_id"):
        _cache_path(tmp_path, "a/b", "r1")


def test_invalid_run_id_rejected(tmp_path):
    """T-04-01: refuse path-traversal sequences in run_id too."""
    with pytest.raises(ValueError, match="invalid run_id"):
        _cache_path(tmp_path, "t1", "../boom")


def test_predict_returns_mismatched_shapes_raises(tmp_path):
    """Validation: actual_prices/last_close must match pred_prices length."""
    bad_payload = {
        "pred_prices": np.array([1.0, 2.0, 3.0]),
        "actual_prices": np.array([1.0, 2.0]),  # too short
        "last_close": np.array([1.0, 2.0, 3.0]),
    }
    with pytest.raises(ValueError, match="actual_prices shape"):
        get_or_build_predictions(
            harness_root=tmp_path,
            tournament_id="t1",
            run_id="r1",
            predict_fn=lambda: bad_payload,
        )
    # No partial cache file persisted on validation failure.
    cache_file = _cache_path(tmp_path, "t1", "r1")
    assert not cache_file.exists()
