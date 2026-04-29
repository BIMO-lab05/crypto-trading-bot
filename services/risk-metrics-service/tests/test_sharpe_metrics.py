"""
Unit tests for app.sharpe_metrics — PSR / DSR / standard-normal helpers.

The module is pure stdlib + numpy, so these tests don't need scipy.
When scipy IS present, additional comparison tests run automatically to
cross-check our Acklam approximation against scipy.stats.norm.ppf and
our sample skew/kurtosis against scipy.stats.skew/kurtosis (bias=False).

Reference for hand-computed values:
    Bailey & López de Prado (2014), "The Deflated Sharpe Ratio."
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.sharpe_metrics import (
    EULER_MASCHERONI,
    deflated_sharpe_ratio,
    expected_max_sharpe_under_null,
    probabilistic_sharpe_ratio,
    standard_normal_cdf,
    standard_normal_inv_cdf,
    _sample_excess_kurtosis,
    _sample_skewness,
)


# ---------------------------------------------------------------------------
# Standard-normal CDF and inverse CDF
# ---------------------------------------------------------------------------


class TestStandardNormalCDF:
    def test_at_zero(self):
        assert standard_normal_cdf(0.0) == pytest.approx(0.5)

    def test_known_values(self):
        # Φ(1) ≈ 0.8413, Φ(-1) ≈ 0.1587, Φ(1.96) ≈ 0.975
        assert standard_normal_cdf(1.0) == pytest.approx(0.8413447, rel=1e-6)
        assert standard_normal_cdf(-1.0) == pytest.approx(0.1586553, rel=1e-6)
        assert standard_normal_cdf(1.96) == pytest.approx(0.9750021, rel=1e-6)

    def test_symmetry(self):
        for x in [0.5, 1.0, 2.0, 3.5]:
            assert standard_normal_cdf(x) + standard_normal_cdf(-x) == pytest.approx(1.0)

    def test_extreme_tails(self):
        assert 0.0 <= standard_normal_cdf(-10.0) < 1e-20
        assert 1.0 - 1e-20 <= standard_normal_cdf(10.0) <= 1.0


class TestStandardNormalInvCDF:
    def test_known_values(self):
        # Φ⁻¹(0.5) = 0; Φ⁻¹(0.975) ≈ 1.96; Φ⁻¹(0.025) ≈ -1.96
        assert standard_normal_inv_cdf(0.5) == pytest.approx(0.0, abs=1e-9)
        assert standard_normal_inv_cdf(0.975) == pytest.approx(1.959964, rel=1e-6)
        assert standard_normal_inv_cdf(0.025) == pytest.approx(-1.959964, rel=1e-6)

    def test_inverse_round_trip(self):
        for x in [-3.0, -1.5, -0.7, 0.0, 0.2, 1.0, 2.5]:
            p = standard_normal_cdf(x)
            assert standard_normal_inv_cdf(p) == pytest.approx(x, abs=1e-7)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError):
            standard_normal_inv_cdf(0.0)
        with pytest.raises(ValueError):
            standard_normal_inv_cdf(1.0)
        with pytest.raises(ValueError):
            standard_normal_inv_cdf(-0.1)
        with pytest.raises(ValueError):
            standard_normal_inv_cdf(1.5)


# ---------------------------------------------------------------------------
# Sample moments
# ---------------------------------------------------------------------------


class TestSampleMoments:
    def test_skewness_zero_for_symmetric(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, size=10000)
        # ~0 with some sampling noise
        assert abs(_sample_skewness(x)) < 0.1

    def test_skewness_positive_right_tail(self):
        rng = np.random.default_rng(1)
        x = rng.lognormal(0.0, 1.0, size=5000)
        assert _sample_skewness(x) > 1.0  # log-normal has strong right skew

    def test_kurtosis_zero_for_normal(self):
        rng = np.random.default_rng(2)
        x = rng.normal(0, 1, size=10000)
        # Excess kurtosis should be near 0 for normal
        assert abs(_sample_excess_kurtosis(x)) < 0.2

    def test_kurtosis_positive_for_fat_tailed(self):
        rng = np.random.default_rng(3)
        x = rng.standard_t(df=4, size=5000)
        # Student-t with df=4 has excess kurtosis = 6/(df - 4) → infinite,
        # but for finite samples we just need it to be clearly > 0.
        assert _sample_excess_kurtosis(x) > 1.0

    def test_too_few_samples_returns_zero(self):
        assert _sample_skewness(np.array([1.0, 2.0])) == 0.0
        assert _sample_excess_kurtosis(np.array([1.0, 2.0, 3.0])) == 0.0


# ---------------------------------------------------------------------------
# Probabilistic Sharpe Ratio
# ---------------------------------------------------------------------------


class TestProbabilisticSharpeRatio:
    def test_zero_mean_returns_psr_not_extreme(self):
        # A true zero-skill strategy's observed PSR is approximately uniform
        # in (0, 1). For a single sample we can only assert "not extreme" —
        # i.e. we don't accidentally always emit ~0 or ~1.
        rng = np.random.default_rng(0)
        r = rng.normal(0.0, 0.01, size=500)
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        assert 0.05 < psr < 0.95

    def test_positive_mean_psr_well_above_half(self):
        # Strong positive Sharpe over many bars → PSR strongly > 0.5
        rng = np.random.default_rng(0)
        r = rng.normal(0.001, 0.005, size=5000)  # SR ~ 0.2 per bar, lots of bars
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        assert psr > 0.99

    def test_short_series_returns_nan(self):
        assert math.isnan(probabilistic_sharpe_ratio(np.array([0.01])))

    def test_zero_variance_returns_nan(self):
        r = np.array([0.001] * 100)  # constant returns → std = 0
        assert math.isnan(probabilistic_sharpe_ratio(r))

    def test_psr_decreases_as_benchmark_rises(self):
        rng = np.random.default_rng(0)
        r = rng.normal(0.001, 0.01, size=2000)
        psr_0 = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        psr_low = probabilistic_sharpe_ratio(r, benchmark_sr=0.05)
        psr_high = probabilistic_sharpe_ratio(r, benchmark_sr=0.2)
        assert psr_0 > psr_low > psr_high

    def test_negative_mean_psr_well_below_half(self):
        rng = np.random.default_rng(0)
        r = rng.normal(-0.001, 0.005, size=5000)
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        assert psr < 0.01


# ---------------------------------------------------------------------------
# Expected max Sharpe under null
# ---------------------------------------------------------------------------


class TestExpectedMaxSharpeUnderNull:
    def test_single_trial_is_zero(self):
        assert expected_max_sharpe_under_null(1, 0.04) == 0.0

    def test_more_trials_higher_threshold(self):
        # With more trials, expected best-of-N grows
        e10 = expected_max_sharpe_under_null(10, 0.04)
        e100 = expected_max_sharpe_under_null(100, 0.04)
        e1000 = expected_max_sharpe_under_null(1000, 0.04)
        assert 0.0 < e10 < e100 < e1000

    def test_higher_variance_higher_threshold(self):
        e_low = expected_max_sharpe_under_null(50, 0.01)
        e_high = expected_max_sharpe_under_null(50, 0.04)
        assert e_high > e_low

    def test_invalid_args(self):
        with pytest.raises(ValueError):
            expected_max_sharpe_under_null(0, 0.04)
        with pytest.raises(ValueError):
            expected_max_sharpe_under_null(10, -0.01)


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio
# ---------------------------------------------------------------------------


class TestDeflatedSharpeRatio:
    def test_dsr_below_psr_when_trials_gt_one(self):
        # Same returns; DSR with multiple trials must be lower than PSR
        # because the threshold rises above zero.
        rng = np.random.default_rng(0)
        r = rng.normal(0.0008, 0.01, size=2000)
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        dsr = deflated_sharpe_ratio(r, num_trials=100, trial_sharpes_variance=0.04)
        assert dsr < psr

    def test_dsr_decreases_as_num_trials_rises(self):
        # Calibrated so both DSR values are distinguishable (not pegged at
        # 0 or 1). Modest observed Sharpe (~0.06/bar, ~0.95 annualised at
        # 252 bars) plus tight per-trial variance so even the N=1000
        # threshold stays below the observed Sharpe.
        rng = np.random.default_rng(0)
        r = rng.normal(0.0003, 0.005, size=5000)
        d10 = deflated_sharpe_ratio(r, num_trials=10, trial_sharpes_variance=0.0001)
        d1000 = deflated_sharpe_ratio(r, num_trials=1000, trial_sharpes_variance=0.0001)
        assert d10 > d1000
        assert 0.0 < d1000 < d10 < 1.0

    def test_dsr_with_one_trial_equals_psr(self):
        rng = np.random.default_rng(0)
        r = rng.normal(0.0005, 0.01, size=1500)
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=0.0)
        dsr = deflated_sharpe_ratio(r, num_trials=1, trial_sharpes_variance=0.04)
        assert dsr == pytest.approx(psr, abs=1e-9)


# ---------------------------------------------------------------------------
# Cross-check vs scipy when available
# ---------------------------------------------------------------------------


class TestAgainstScipy:
    @pytest.fixture(autouse=True)
    def _skip_if_no_scipy(self):
        pytest.importorskip("scipy")

    def test_phi_inv_matches_scipy_norm_ppf(self):
        from scipy.stats import norm
        for p in [0.001, 0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 0.999]:
            assert standard_normal_inv_cdf(p) == pytest.approx(
                float(norm.ppf(p)), abs=1e-7
            )

    def test_skewness_matches_scipy(self):
        from scipy.stats import skew
        rng = np.random.default_rng(123)
        for size in [50, 500, 5000]:
            x = rng.normal(0, 1, size=size)
            assert _sample_skewness(x) == pytest.approx(
                float(skew(x, bias=False)), abs=1e-9
            )

    def test_excess_kurtosis_matches_scipy(self):
        from scipy.stats import kurtosis
        rng = np.random.default_rng(456)
        for size in [50, 500, 5000]:
            x = rng.normal(0, 1, size=size)
            assert _sample_excess_kurtosis(x) == pytest.approx(
                float(kurtosis(x, fisher=True, bias=False)), abs=1e-9
            )


def test_module_constant_euler_mascheroni():
    assert EULER_MASCHERONI == pytest.approx(0.577215664901, rel=1e-10)
