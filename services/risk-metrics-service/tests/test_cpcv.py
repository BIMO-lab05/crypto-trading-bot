"""
Unit tests for app.cpcv — Combinatorial Purged Cross-Validation.

Coverage strategy mirrors test_sharpe_metrics.py:
- Combinatorics + iteration contract
- Fold coverage (every bar appears in test exactly C(N-1, k-1) times)
- Purge correctness (no train/test label overlap)
- Embargo correctness (right-side dilation)
- Leakage-detection (vectorized check on the same purge property)
- DSR bridge to sharpe_metrics.deflated_sharpe_ratio
- scipy/itertools cross-check
- Validation errors
"""

from __future__ import annotations

import math
from itertools import combinations

import numpy as np
import pytest

from app.cpcv import (
    CombinatorialPurgedCV,
    CPCVSplit,
    cpcv_sharpe_distribution,
    cpcv_to_dsr,
)


# ---------------------------------------------------------------------------
# Combinatorics & iteration
# ---------------------------------------------------------------------------


class TestCombinatorics:
    def test_n_paths_default(self):
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2)
        assert cv.n_paths == 45

    def test_n_paths_other_shapes(self):
        # C(6, 2) = 15; C(8, 3) = 56; C(5, 1) = 5
        assert CombinatorialPurgedCV(n_groups=6, k_test_groups=2).n_paths == 15
        assert CombinatorialPurgedCV(n_groups=8, k_test_groups=3).n_paths == 56
        assert CombinatorialPurgedCV(n_groups=5, k_test_groups=1).n_paths == 5

    def test_split_yields_n_paths_unique(self):
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.01)
        splits = list(cv.split(n_samples=1000, label_horizon=5))
        assert len(splits) == 45
        # Unique deterministic path_ids
        assert {s.path_id for s in splits} == set(range(45))
        # Unique test_groups tuples
        assert len({s.test_groups for s in splits}) == 45
        # All test_groups have exactly k entries
        assert all(len(s.test_groups) == 2 for s in splits)

    def test_test_groups_match_itertools_combinations(self):
        cv = CombinatorialPurgedCV(n_groups=6, k_test_groups=2, embargo_pct=0.0)
        seen = [s.test_groups for s in cv.split(600, 3)]
        expected = list(combinations(range(6), 2))
        assert seen == expected


# ---------------------------------------------------------------------------
# Fold coverage
# ---------------------------------------------------------------------------


class TestFoldCoverage:
    def test_every_bar_appears_in_test_C_n_minus_1_k_minus_1_times(self):
        # With N=10, k=2, every bar in some group g is held out exactly when
        # g is in the test combo: C(9, 1) = 9 times.
        n_samples = 1000
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.0)
        counts = np.zeros(n_samples, dtype=int)
        for split in cv.split(n_samples, label_horizon=3):
            counts[split.test_idx] += 1
        # Every bar (no purge applied to test set itself) appears 9 times
        assert np.all(counts == math.comb(9, 1))

    def test_train_and_test_are_disjoint(self):
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.01)
        for split in cv.split(1000, 5):
            assert len(np.intersect1d(split.train_idx, split.test_idx)) == 0


# ---------------------------------------------------------------------------
# Purge correctness — the load-bearing leakage check
# ---------------------------------------------------------------------------


def _min_train_test_distance(split: CPCVSplit) -> int:
    """For each train idx, distance to nearest test idx (vectorized)."""
    if len(split.train_idx) == 0 or len(split.test_idx) == 0:
        return 10**9  # vacuously satisfied
    sorted_test = np.sort(split.test_idx)
    pos = np.searchsorted(sorted_test, split.train_idx)
    last = len(sorted_test) - 1
    has_left = pos > 0
    has_right = pos <= last
    left_idx = np.clip(pos - 1, 0, last)
    right_idx = np.clip(pos, 0, last)
    left_dist = np.where(has_left, split.train_idx - sorted_test[left_idx], 10**9)
    right_dist = np.where(has_right, sorted_test[right_idx] - split.train_idx, 10**9)
    return int(np.minimum(left_dist, right_dist).min())


class TestPurgeCorrectness:
    @pytest.mark.parametrize("h", [1, 3, 5, 12])
    def test_no_train_idx_within_label_horizon_of_any_test_idx(self, h):
        n_samples = 2000
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.0)
        for split in cv.split(n_samples, h):
            min_dist = _min_train_test_distance(split)
            assert min_dist >= h, (
                f"Leakage: train/test distance {min_dist} < horizon {h} "
                f"(test_groups={split.test_groups})"
            )

    def test_naive_kfold_would_leak_but_purged_does_not(self):
        # Sanity oracle: build a "fold" with NO purging and confirm the same
        # property (min distance >= h) FAILS — i.e. our test would catch a
        # leak if CPCV were broken. Then confirm CPCV passes.
        n_samples = 200
        h = 5
        # Naive: train = [50, 150), test = [100, 110) — directly adjacent
        naive = CPCVSplit(
            train_idx=np.concatenate([np.arange(50, 100), np.arange(110, 150)]),
            test_idx=np.arange(100, 110),
            test_groups=(0,),
            path_id=0,
        )
        assert _min_train_test_distance(naive) < h  # leakage exists

        cv = CombinatorialPurgedCV(n_groups=4, k_test_groups=1, embargo_pct=0.0)
        for split in cv.split(n_samples, h):
            assert _min_train_test_distance(split) >= h


# ---------------------------------------------------------------------------
# Embargo correctness
# ---------------------------------------------------------------------------


class TestEmbargo:
    def test_no_train_idx_in_embargo_window_after_test_group(self):
        n_samples = 1000
        embargo_pct = 0.05  # → embargo_len = 50
        cv = CombinatorialPurgedCV(
            n_groups=10, k_test_groups=2, embargo_pct=embargo_pct
        )
        embargo_len = max(1, math.ceil(embargo_pct * n_samples))
        bounds = cv._group_bounds(n_samples)
        for split in cv.split(n_samples, label_horizon=2):
            for g in split.test_groups:
                _, b = bounds[g]
                in_window = split.train_idx[
                    (split.train_idx >= b) & (split.train_idx < b + embargo_len)
                ]
                assert len(in_window) == 0, (
                    f"Embargo violation at group {g} end {b}: "
                    f"{len(in_window)} train indices in [b, b+{embargo_len})"
                )

    def test_zero_embargo_keeps_immediate_post_group_indices(self):
        # With embargo=0, the only exclusion past test-group end is from
        # purging — at h=1 there's no purge past the boundary, so the very
        # next index after the test group should remain in the train set
        # (provided that index is not in another test group).
        cv = CombinatorialPurgedCV(n_groups=4, k_test_groups=1, embargo_pct=0.0)
        bounds = cv._group_bounds(400)
        seen_post_boundary = False
        for split in cv.split(400, label_horizon=1):
            for g in split.test_groups:
                _, b = bounds[g]
                if b < 400 and b in split.train_idx:
                    seen_post_boundary = True
        assert seen_post_boundary


# ---------------------------------------------------------------------------
# Aggregation: cpcv_sharpe_distribution
# ---------------------------------------------------------------------------


class TestSharpeDistribution:
    def test_zero_mean_paths_distribute_around_zero(self):
        rng = np.random.default_rng(0)
        paths = [rng.normal(0.0, 0.01, size=200) for _ in range(45)]
        d = cpcv_sharpe_distribution(paths)
        assert d["n_paths"] == 45
        assert abs(d["mean"]) < 0.5
        assert d["std"] > 0.0
        assert d["ci_low"] < d["median"] < d["ci_high"]

    def test_positive_mean_paths_distribute_above_zero(self):
        rng = np.random.default_rng(0)
        paths = [rng.normal(0.001, 0.005, size=500) for _ in range(45)]
        d = cpcv_sharpe_distribution(paths)
        assert d["mean"] > 0.05
        assert d["ci_low"] > -0.5  # bulk well above the noise floor

    def test_empty_returns_path_dropped(self):
        d = cpcv_sharpe_distribution([np.array([0.01, 0.02]), np.array([])])
        assert d["n_paths"] == 1

    def test_zero_variance_paths_are_dropped(self):
        # All-constant returns → std=0 → drop
        d = cpcv_sharpe_distribution([np.array([0.001] * 100)])
        assert d["n_paths"] == 0
        assert math.isnan(d["mean"])

    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            cpcv_sharpe_distribution([])


# ---------------------------------------------------------------------------
# Bridge: cpcv_to_dsr
# ---------------------------------------------------------------------------


class TestCpcvToDsr:
    def test_zero_mean_concat_returns_dsr_well_below_pass(self):
        # Zero-skill returns + 45 trials → DSR should be far below the 0.95
        # passing threshold.
        rng = np.random.default_rng(0)
        paths = [rng.normal(0.0, 0.01, size=200) for _ in range(45)]
        concat = np.concatenate(paths)
        dsr = cpcv_to_dsr(paths, concat)
        assert 0.0 <= dsr < 0.95

    def test_strong_signal_concat_returns_higher_dsr_than_zero(self):
        # A clear positive Sharpe across many paths → DSR > zero-mean case.
        rng = np.random.default_rng(0)
        paths = [rng.normal(0.0008, 0.005, size=500) for _ in range(45)]
        concat = np.concatenate(paths)
        dsr_signal = cpcv_to_dsr(paths, concat)

        rng2 = np.random.default_rng(1)
        zero_paths = [rng2.normal(0.0, 0.005, size=500) for _ in range(45)]
        zero_concat = np.concatenate(zero_paths)
        dsr_null = cpcv_to_dsr(zero_paths, zero_concat)

        assert dsr_signal > dsr_null

    def test_one_valid_path_returns_nan(self):
        # Need at least 2 paths to estimate trial variance
        result = cpcv_to_dsr([np.array([0.001] * 100)], np.array([0.001] * 100))
        assert math.isnan(result)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"n_groups": 1},
            {"n_groups": 0},
            {"k_test_groups": 0},
            {"k_test_groups": 5, "n_groups": 5},  # k must be < n_groups
            {"embargo_pct": -0.1},
            {"embargo_pct": 1.0},
        ],
    )
    def test_invalid_constructor_args_raise(self, kwargs):
        defaults = {"n_groups": 6, "k_test_groups": 2, "embargo_pct": 0.01}
        defaults.update(kwargs)
        with pytest.raises(ValueError):
            CombinatorialPurgedCV(**defaults)

    def test_n_samples_too_small_raises(self):
        cv = CombinatorialPurgedCV(n_groups=10, k_test_groups=2, embargo_pct=0.05)
        # n_samples=50 — way too small for label_horizon=5 + embargo
        with pytest.raises(ValueError, match="n_samples"):
            list(cv.split(50, label_horizon=5))

    def test_label_horizon_zero_raises(self):
        cv = CombinatorialPurgedCV(n_groups=4, k_test_groups=1, embargo_pct=0.0)
        with pytest.raises(ValueError):
            list(cv.split(400, label_horizon=0))


# ---------------------------------------------------------------------------
# Optional cross-check vs scipy when present
# ---------------------------------------------------------------------------


class TestAgainstScipy:
    @pytest.fixture(autouse=True)
    def _skip_if_no_scipy(self):
        pytest.importorskip("scipy")

    def test_sharpe_distribution_aligns_with_scipy_describe(self):
        # cpcv_sharpe_distribution uses np.mean / np.std — scipy.stats.describe
        # gives the same first/second moments. Sanity check on agreement.
        from scipy import stats

        rng = np.random.default_rng(0)
        paths = [rng.normal(0.0, 0.01, size=300) for _ in range(45)]
        d = cpcv_sharpe_distribution(paths)
        # Recompute Sharpe per path manually
        sharpes = np.asarray(
            [float(np.mean(p) / np.std(p, ddof=1)) for p in paths]
        )
        descr = stats.describe(sharpes)
        assert d["mean"] == pytest.approx(float(descr.mean), abs=1e-9)
        # ddof=1 std must match describe.variance**0.5
        assert d["std"] == pytest.approx(float(descr.variance) ** 0.5, abs=1e-9)
