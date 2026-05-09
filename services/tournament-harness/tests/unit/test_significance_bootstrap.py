"""Tests for app.significance.bootstrap (D-05/D-06/CD-07).

Covers:
- derive_seed: blake2b-derived 31-bit seed; per-symbol uniqueness; deterministic.
- stationary_block_bootstrap_pvalue: block-size formula, additive smoothing,
  one-tailed alternative, seed determinism, known-input significance.
- @pytest.mark.slow guards the n_resamples=10_000 production-value variant.

NOTE: TOURN-07 — this module imports the kernel only, never re-implements
metrics. The grep gate is a separate test in test_no_parallel_metric_definitions.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.significance.bootstrap import (
    _generate_block_resample,
    derive_seed,
    stationary_block_bootstrap_pvalue,
)


# ---------------------------------------------------------------------------
# derive_seed (CD-07)
# ---------------------------------------------------------------------------


def test_derive_seed_format() -> None:
    """CD-07: derive_seed returns a non-negative 31-bit int (< 2**31)."""
    s = derive_seed("tid-abc", "BTCUSDT")
    assert isinstance(s, int)
    assert 0 <= s < 2**31


def test_derive_seed_unique_per_symbol() -> None:
    """CD-07: per-symbol independence — same tid, different symbol → different seed."""
    s_btc = derive_seed("t1", "BTCUSDT")
    s_eth = derive_seed("t1", "ETHUSDT")
    s_sol = derive_seed("t1", "SOLUSDT")
    assert len({s_btc, s_eth, s_sol}) == 3


def test_derive_seed_stable() -> None:
    """Same (tid, symbol) → identical seed across calls (load-bearing for reproduce)."""
    a = derive_seed("tid-xyz", "ADAUSDT")
    b = derive_seed("tid-xyz", "ADAUSDT")
    assert a == b


# ---------------------------------------------------------------------------
# Block-size formula (D-05)
# ---------------------------------------------------------------------------


def _mean_metric(r: np.ndarray) -> float:
    """Plain mean — sufficient to exercise the bootstrap kernel without dragging in Sharpe."""
    return float(np.mean(r))


def test_block_size_formula() -> None:
    """N=100 → block_size = max(2, floor(sqrt(100))) = 10."""
    rng_seed = derive_seed("t1", "BTCUSDT")
    diffs = np.linspace(-0.01, 0.02, 100)
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=200, seed=rng_seed
    )
    assert res["block_size"] == 10
    assert res["n_oos_bars"] == 100
    assert res["n_resamples"] == 200


def test_block_size_min_two() -> None:
    """Tiny N=2 → block_size clamps to 2 (the max(2,...) floor)."""
    diffs = np.array([0.01, 0.02])
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=50, seed=42
    )
    assert res["block_size"] == 2


def test_block_size_n_4_gives_sqrt() -> None:
    """N=4 → max(2, floor(sqrt(4))) = 2."""
    diffs = np.array([0.0, 0.01, 0.02, -0.01])
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=50, seed=1
    )
    assert res["block_size"] == 2


# ---------------------------------------------------------------------------
# Additive smoothing (D-06): p ∈ (0, 1]
# ---------------------------------------------------------------------------


def test_pvalue_lower_bound_nonzero() -> None:
    """T-04-06: additive smoothing — even all-positive lift never returns p == 0."""
    # Strongly positive paired diffs: every resample of the centered series should
    # rarely exceed the observed (positive) metric → smallest possible smoothed p.
    diffs = np.full(200, 0.05)
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=200, seed=7
    )
    assert res["p_value"] > 0.0
    # Lower bound from the smoothing formula = 1 / (n+1) when count == 0.
    assert res["p_value"] >= 1.0 / 201


def test_pvalue_additive_smoothing_upper_bound() -> None:
    """Constant diffs (mean == 0 already) → centered diffs all zero → every resample equals observed.
    With `stat >= observed`, count == n_resamples → p = (1+n)/(n+1) = 1.0.
    """
    diffs = np.zeros(100)
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=200, seed=3
    )
    assert res["p_value"] == pytest.approx(1.0, abs=1e-12)


def test_pvalue_in_unit_interval_random() -> None:
    """Across random seeds and random diffs, p ∈ (0, 1]."""
    rng = np.random.default_rng(2026)
    for _ in range(50):
        diffs = rng.normal(0.0, 0.01, size=100)
        seed = int(rng.integers(1, 2**31 - 1))
        res = stationary_block_bootstrap_pvalue(
            diffs, metric_fn=_mean_metric, n_resamples=100, seed=seed
        )
        assert 0.0 < res["p_value"] <= 1.0


# ---------------------------------------------------------------------------
# One-tailed alternative (D-06)
# ---------------------------------------------------------------------------


def test_one_tailed_all_positive_low_p() -> None:
    """All-positive lift → low p (significant)."""
    diffs = np.full(200, 0.02)  # constant, strongly positive
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=500, seed=11
    )
    assert res["p_value"] < 0.05


def test_one_tailed_all_negative_high_p() -> None:
    """All-negative lift → very high p (≈ 1.0): never beats baseline."""
    diffs = np.full(200, -0.02)
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=500, seed=13
    )
    assert res["p_value"] > 0.95


def test_one_tailed_symmetric_noise_p_around_half() -> None:
    """Symmetric zero-mean noise → p ≈ 0.5."""
    rng = np.random.default_rng(99)
    diffs = rng.normal(0.0, 0.01, size=400)
    seed = derive_seed("t-noise", "BTCUSDT")
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=2000, seed=seed
    )
    # Wide tolerance — bootstrap noise on 2000 resamples + one realization of diffs.
    assert 0.2 < res["p_value"] < 0.8


def test_alternative_only_greater() -> None:
    """Only one-tailed 'greater' is supported (D-06); other values raise."""
    with pytest.raises(ValueError):
        stationary_block_bootstrap_pvalue(
            np.array([0.01, 0.02, 0.03]),
            metric_fn=_mean_metric,
            n_resamples=10,
            seed=1,
            alternative="two-sided",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Seed determinism (T-04-07)
# ---------------------------------------------------------------------------


def test_seed_determinism() -> None:
    """Same (paired_diffs, seed, n_resamples) → identical p_value across calls."""
    diffs = np.linspace(-0.005, 0.01, 150)
    a = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=300, seed=12345
    )
    b = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=300, seed=12345
    )
    assert a["p_value"] == b["p_value"]
    assert a["observed_metric"] == b["observed_metric"]


def test_seed_changes_resamples() -> None:
    """Different seeds → bootstrap traverses different resamples → typically different p_value.

    Sanity check: at minimum, the underlying block-resample index sequences differ.
    """
    rng_a = np.random.default_rng(1)
    rng_b = np.random.default_rng(2)
    idx_a = _generate_block_resample(rng_a, 100, 10)
    idx_b = _generate_block_resample(rng_b, 100, 10)
    assert not np.array_equal(idx_a, idx_b)


# ---------------------------------------------------------------------------
# Known input synthetic signal (D-06)
# ---------------------------------------------------------------------------


def test_known_input_synthetic() -> None:
    """Hand-built diffs with mean=0.5, std=0.1 over N=500 → p clearly < 0.05."""
    rng = np.random.default_rng(2024)
    diffs = rng.normal(loc=0.5, scale=0.1, size=500)
    seed = derive_seed("known-input", "BTCUSDT")
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=500, seed=seed
    )
    assert res["p_value"] < 0.05
    assert res["observed_metric"] == pytest.approx(0.5, abs=0.05)


# ---------------------------------------------------------------------------
# Block-resample internals (D-05: indices in [0, N))
# ---------------------------------------------------------------------------


def test_block_resample_indices_in_range() -> None:
    """Politis-Romano block resample → all indices in [0, N)."""
    rng = np.random.default_rng(0)
    n, block_size = 200, 14
    idxs = _generate_block_resample(rng, n, block_size)
    assert idxs.shape == (n,)
    assert idxs.min() >= 0
    assert idxs.max() < n


def test_block_resample_length_matches_n() -> None:
    """Generated block-resample series has exactly N entries."""
    rng = np.random.default_rng(0)
    for n in (10, 50, 200, 1000):
        idxs = _generate_block_resample(rng, n, max(2, int(math.floor(math.sqrt(n)))))
        assert len(idxs) == n


# ---------------------------------------------------------------------------
# Input-validation: too short
# ---------------------------------------------------------------------------


def test_too_short_paired_diffs_raises() -> None:
    """N < 2 → ValueError (block_size = 2 minimum)."""
    with pytest.raises(ValueError):
        stationary_block_bootstrap_pvalue(
            np.array([0.01]),
            metric_fn=_mean_metric,
            n_resamples=10,
            seed=1,
        )


# ---------------------------------------------------------------------------
# Slow path: D-06 production n_resamples = 10_000
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_pvalue_at_production_n_resamples() -> None:
    """D-06 production value: n_resamples=10_000 still terminates and obeys invariants."""
    rng = np.random.default_rng(2025)
    diffs = rng.normal(0.005, 0.01, size=300)
    seed = derive_seed("slow-test", "BTCUSDT")
    res = stationary_block_bootstrap_pvalue(
        diffs, metric_fn=_mean_metric, n_resamples=10_000, seed=seed
    )
    assert 0.0 < res["p_value"] <= 1.0
    assert res["n_resamples"] == 10_000
