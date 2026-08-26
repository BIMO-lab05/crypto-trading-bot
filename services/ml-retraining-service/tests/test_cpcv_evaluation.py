"""
Tests for ``app.core.cpcv_evaluation``.

This module is the trainer-facing wrapper around the byte-duplicated
``app.cpcv`` / ``app.sharpe_metrics`` modules. The duplicates already
have full test coverage in ``services/risk-metrics-service/tests/``; here
we cover the wrapper-specific concerns:

- Strategy-return derivation matches ``returns_metrics``'s reference point.
- The result dict shape is what the trainer ``test_metrics.update(...)``-s.
- Degenerate-input failure modes return a NaN-sentinel dict, not raise.
- A perfect-skill predictor produces a strongly positive DSR; a
  no-skill predictor produces DSR ≪ 0.95.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sklearn")

import numpy as np  # noqa: E402

from app.core.cpcv_evaluation import (  # noqa: E402
    compute_strategy_returns,
    evaluate_with_cpcv,
)


# ---------------------------------------------------------------------------
# compute_strategy_returns
# ---------------------------------------------------------------------------


class TestComputeStrategyReturns:
    def test_perfect_predictor_returns_absolute_value_log_returns(self):
        # Predictor always picks the right direction → r = |log(actual/last)|.
        last = np.array([100.0, 100.0, 100.0])
        actual = np.array([110.0, 90.0, 105.0])
        pred = np.array([105.0, 95.0, 102.0])  # right direction every time
        r = compute_strategy_returns(actual, pred, last)
        assert r.shape == (3,)
        np.testing.assert_allclose(r, np.abs(np.log(actual / last)))

    def test_inverted_predictor_returns_negative_absolute_value(self):
        last = np.array([100.0, 100.0, 100.0])
        actual = np.array([110.0, 90.0, 105.0])
        pred = np.array([95.0, 105.0, 98.0])  # wrong every time
        r = compute_strategy_returns(actual, pred, last)
        np.testing.assert_allclose(r, -np.abs(np.log(actual / last)))

    def test_pred_equals_last_yields_zero(self):
        # sign(0) == 0 → strategy abstains → contributes 0 to return series.
        last = np.array([100.0, 100.0])
        actual = np.array([105.0, 95.0])
        pred = np.array([100.0, 100.0])
        r = compute_strategy_returns(actual, pred, last)
        np.testing.assert_allclose(r, [0.0, 0.0])

    def test_drops_non_positive_rows(self):
        last = np.array([0.0, 100.0, -1.0])
        actual = np.array([105.0, 110.0, 90.0])
        pred = np.array([105.0, 105.0, 95.0])
        r = compute_strategy_returns(actual, pred, last)
        # Only middle row survives (last=100>0, all positive).
        assert r.shape == (1,)
        np.testing.assert_allclose(r, [np.log(110.0 / 100.0)])

    def test_all_invalid_returns_empty(self):
        last = np.array([0.0, -1.0])
        actual = np.array([100.0, 100.0])
        pred = np.array([100.0, 100.0])
        r = compute_strategy_returns(actual, pred, last)
        assert r.shape == (0,)

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape mismatch"):
            compute_strategy_returns(
                np.array([100.0, 101.0]),
                np.array([100.0]),
                np.array([100.0, 101.0]),
            )


# ---------------------------------------------------------------------------
# evaluate_with_cpcv — shape and degenerate cases
# ---------------------------------------------------------------------------


EXPECTED_KEYS = {
    "test_dsr",
    "test_cpcv_sharpe_mean",
    "test_cpcv_sharpe_std",
    "test_cpcv_sharpe_median",
    "test_cpcv_sharpe_ci_low",
    "test_cpcv_sharpe_ci_high",
    "test_cpcv_n_paths",
    "test_cpcv_oos_sharpe",
    "test_cpcv_n_samples",
    # SEV-5 (2026-08): honest-N DSR variant + its trial-count component.
    "test_cpcv_dsr",
    "test_cpcv_num_trials_used",
}


def _make_drift_series(n: int, drift: float, sigma: float, seed: int):
    """OHLCV-shaped triple (actual, pred, last) with controllable skill."""
    rng = np.random.default_rng(seed)
    last = np.full(n, 100.0)
    log_ret = rng.normal(drift, sigma, size=n)
    actual = last * np.exp(log_ret)
    return last, actual


class TestEvaluateWithCPCV:
    def test_result_dict_has_expected_shape(self):
        last, actual = _make_drift_series(800, drift=0.0, sigma=0.01, seed=0)
        pred = actual.copy()  # perfect predictor
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="test", label_horizon=5
        )
        assert set(result.keys()) == EXPECTED_KEYS

    def test_too_few_samples_returns_nan_sentinel(self):
        last = np.array([100.0, 100.0])
        actual = np.array([101.0, 99.0])
        pred = np.array([102.0, 98.0])
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="oos", label_horizon=5
        )
        # All zeros / NaNs except n_samples (2) — and even that should be
        # short-circuited to 0 since CPCV needs n >= n_groups*(h+emb+1).
        assert math.isnan(result["oos_dsr"])
        assert math.isnan(result["oos_cpcv_sharpe_mean"])
        # n_paths is the *valid* path count; degenerate samples → 0.
        assert result["oos_cpcv_n_paths"] == 0

    def test_all_invalid_prices_returns_nan_sentinel(self):
        last = np.zeros(800)
        actual = np.full(800, 100.0)
        pred = np.full(800, 100.0)
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="oos", label_horizon=5
        )
        assert math.isnan(result["oos_dsr"])
        assert result["oos_cpcv_n_samples"] == 0

    def test_perfect_predictor_yields_high_dsr(self):
        # A predictor that always picks the right direction has positive
        # mean, near-zero variance across paths. DSR should clear 0.95.
        last, actual = _make_drift_series(1500, drift=0.0, sigma=0.01, seed=1)
        pred = actual.copy()
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="test", label_horizon=5
        )
        assert not math.isnan(result["test_dsr"])
        assert result["test_dsr"] > 0.95
        # Mean per-path Sharpe should be strongly positive.
        assert result["test_cpcv_sharpe_mean"] > 0.1
        # OOS Sharpe (concatenated) is similarly positive.
        assert result["test_cpcv_oos_sharpe"] > 0.1

    def test_no_skill_predictor_yields_low_dsr(self):
        # Predicted direction independent of realised → DSR well below 0.95.
        rng = np.random.default_rng(7)
        n = 1500
        last = np.full(n, 100.0)
        actual_logret = rng.normal(0.0, 0.01, size=n)
        pred_logret = rng.normal(0.0, 0.01, size=n)
        actual = last * np.exp(actual_logret)
        pred = last * np.exp(pred_logret)
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="test", label_horizon=5
        )
        assert not math.isnan(result["test_dsr"])
        assert result["test_dsr"] < 0.95
        assert abs(result["test_cpcv_sharpe_mean"]) < 0.1

    def test_n_paths_does_not_exceed_combinations(self):
        # With n_groups=10, k=2 the max possible paths is C(10,2) = 45.
        last, actual = _make_drift_series(2000, drift=0.0, sigma=0.01, seed=3)
        pred = actual.copy()
        result = evaluate_with_cpcv(
            actual,
            pred,
            last,
            dataset_name="test",
            label_horizon=5,
            n_groups=10,
            k_test_groups=2,
        )
        assert result["test_cpcv_n_paths"] <= 45

    def test_cpcv_dsr_uses_honest_num_trials(self):
        # SEV-5: cpcv_dsr deflates with N = max(valid paths, total path
        # count) = C(10,2) = 45 here, so it can never be less deflated
        # than the legacy dsr (which uses only the valid-path count).
        last, actual = _make_drift_series(1500, drift=0.0, sigma=0.01, seed=9)
        pred = actual.copy()
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="test", label_horizon=5
        )
        assert result["test_cpcv_num_trials_used"] == 45
        assert not math.isnan(result["test_cpcv_dsr"])
        # More (or equal) deflation than the legacy variant.
        assert result["test_cpcv_dsr"] <= result["test_dsr"] + 1e-12

    def test_cpcv_dsr_nan_sentinel_when_cpcv_cannot_run(self):
        # Degenerate input → cpcv_dsr is NaN (NEVER a copy of dsr, never 0.0).
        last = np.array([100.0, 100.0])
        actual = np.array([101.0, 99.0])
        pred = np.array([102.0, 98.0])
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="oos", label_horizon=5
        )
        assert math.isnan(result["oos_cpcv_dsr"])
        assert result["oos_cpcv_num_trials_used"] == 0

    def test_runs_with_dataset_name_prefix(self):
        # The "train" / "test" prefix follows returns_metrics convention.
        last, actual = _make_drift_series(800, drift=0.0, sigma=0.01, seed=4)
        pred = actual.copy()
        result = evaluate_with_cpcv(
            actual, pred, last, dataset_name="train", label_horizon=5
        )
        assert "train_dsr" in result
        assert "test_dsr" not in result


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
