"""
Tests for ``app.core.model_trainer.compute_returns_metrics``.

Lives in its own file (not ``test_model_trainer.py``) because that file
``pytest.importorskip``-s tensorflow at module load — these tests don't
need TF, only numpy + sklearn, and we want them to run in environments
where TF isn't available.

Background: docs/strategy/research-2026-04-29/V0-FINDINGS-gru-metric-bug.md
established that the production GRU's price-level R² is autocorrelation
noise and the recorded directional accuracy was buggy (look-ahead +
degenerate reference). compute_returns_metrics is the honest counterpart
that the next retrain will record alongside the legacy metrics.
"""

from __future__ import annotations

import math

import pytest

# numpy + sklearn are required at the module level via the function under test.
pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import numpy as np  # noqa: E402

from app.core.returns_metrics import compute_returns_metrics  # noqa: E402


class TestComputeReturnsMetrics:
    def test_perfect_prediction_gets_perfect_scores(self):
        last = np.array([100.0, 100.0, 100.0])
        actual = np.array([101.0, 99.0, 100.5])
        m = compute_returns_metrics(actual, actual.copy(), last, "test")
        assert m["test_r2_returns"] == pytest.approx(1.0)
        assert m["test_dir_acc_corrected"] == pytest.approx(1.0)

    def test_persistence_baseline_dir_acc_near_zero(self):
        # "Predict no change" — pred_prices == last_close.
        # np.sign(0) == 0 ≠ ±1 of any real move, so dir_acc ≈ 0.
        last = np.array([100.0, 100.0, 100.0, 100.0])
        actual = np.array([101.0, 99.0, 100.5, 99.5])
        pred = last.copy()
        m = compute_returns_metrics(actual, pred, last, "test")
        assert m["test_dir_acc_corrected"] == pytest.approx(0.0)

    def test_inverted_prediction_negative_r2(self):
        # Predict the negative of the actual return → R² strongly negative.
        last = np.array([100.0] * 100)
        rng = np.random.default_rng(0)
        actual = last * np.exp(rng.normal(0.0, 0.01, size=100))
        pred = last * np.exp(-np.log(actual / last))  # invert the move
        m = compute_returns_metrics(actual, pred, last, "test")
        assert m["test_r2_returns"] < -1.0  # significantly worse than mean
        assert m["test_dir_acc_corrected"] == pytest.approx(0.0)

    def test_random_prediction_dir_acc_near_half(self):
        rng = np.random.default_rng(42)
        n = 5000
        last = np.full(n, 100.0)
        actual = last * np.exp(rng.normal(0.0, 0.01, size=n))
        pred = last * np.exp(rng.normal(0.0, 0.01, size=n))
        m = compute_returns_metrics(actual, pred, last, "oos")
        # Two independent symmetric distributions of returns → ~50% sign agreement
        assert 0.45 < m["oos_dir_acc_corrected"] < 0.55
        # R² on independent series should be near 0 or negative
        assert m["oos_r2_returns"] < 0.1

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_returns_metrics(
                np.array([100.0]),
                np.array([100.0, 101.0]),
                np.array([100.0]),
                "test",
            )

    def test_drops_non_positive_prices(self):
        # Two of three rows have invalid data; only the valid row should
        # contribute to the metric. Perfect prediction on the valid row.
        last = np.array([0.0, -1.0, 100.0])
        actual = np.array([101.0, 102.0, 105.0])
        pred = np.array([101.0, 102.0, 105.0])
        m = compute_returns_metrics(actual, pred, last, "tr")
        assert m["tr_dir_acc_corrected"] == pytest.approx(1.0)

    def test_all_invalid_returns_nan(self):
        last = np.array([0.0, 0.0])
        actual = np.array([100.0, 101.0])
        pred = np.array([100.0, 101.0])
        m = compute_returns_metrics(actual, pred, last, "tr")
        assert math.isnan(m["tr_r2_returns"])
        assert math.isnan(m["tr_dir_acc_corrected"])


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
