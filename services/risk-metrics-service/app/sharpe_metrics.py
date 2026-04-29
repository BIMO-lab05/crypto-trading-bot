"""
Probabilistic and Deflated Sharpe Ratio.

Reference:
    Bailey, D. H. & López de Prado, M. (2014). "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality."
    Journal of Portfolio Management 40(5), 94-107.
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551

Why this lives here, in risk-metrics-service:
    The legacy `RiskEngine.calculate_performance_metrics` reports the
    naive Sharpe Ratio, which is biased upward when (a) returns are
    non-normal, and (b) the strategy was selected from a pool of
    candidates. PSR adjusts for (a). DSR adjusts for (a) AND (b).

    Both are recommendation T0.2 of docs/strategy/RESEARCH_PLAN_2026-04-29:
    "Replace fixed split + walk-forward with CPCV + Deflated Sharpe for
    evaluation. Without this, lift estimates are unreliable."

Stdlib + numpy only — no scipy dependency. The standard-normal CDF uses
math.erf; the inverse CDF uses an Acklam approximation accurate to ~1e-9.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np


# Euler-Mascheroni constant — appears in DSR's expected-max-Sharpe formula.
EULER_MASCHERONI = 0.5772156649015329


# ---------------------------------------------------------------------------
# Standard-normal helpers (no scipy)
# ---------------------------------------------------------------------------


def standard_normal_cdf(x: float) -> float:
    """Standard normal CDF Φ(x). Wraps math.erf — exact to float64 precision."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def standard_normal_inv_cdf(p: float) -> float:
    """
    Standard normal inverse CDF Φ⁻¹(p). Acklam (2003) rational approximation,
    accurate to ~1e-9 over (1e-15, 1 - 1e-15). Raises on p ∉ (0, 1).
    """
    if not (0.0 < p < 1.0):
        raise ValueError(f"standard_normal_inv_cdf requires 0 < p < 1; got {p}")

    # Coefficients
    a = (
        -3.969683028665376e+01,
        2.209460984245205e+02,
        -2.759285104469687e+02,
        1.383577518672690e+02,
        -3.066479806614716e+01,
        2.506628277459239e+00,
    )
    b = (
        -5.447609879822406e+01,
        1.615858368580409e+02,
        -1.556989798598866e+02,
        6.680131188771972e+01,
        -1.328068155288572e+01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
        4.374664141464968e+00,
        2.938163982698783e+00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e+00,
        3.754408661907416e+00,
    )

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)

    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(
        ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
    ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)


# ---------------------------------------------------------------------------
# Sample moments — match scipy.stats.skew / kurtosis with bias=False & fisher=True
# ---------------------------------------------------------------------------


def _sample_skewness(returns: np.ndarray) -> float:
    """Sample (Fisher-Pearson) adjusted skewness. Matches scipy.stats.skew(bias=False)."""
    n = len(returns)
    if n < 3:
        return 0.0
    mean = np.mean(returns)
    diff = returns - mean
    m2 = np.mean(diff ** 2)
    m3 = np.mean(diff ** 3)
    if m2 <= 0:
        return 0.0
    g1 = m3 / (m2 ** 1.5)
    # Adjusted (sample-stat) form
    return float(g1 * math.sqrt(n * (n - 1)) / (n - 2))


def _sample_excess_kurtosis(returns: np.ndarray) -> float:
    """Sample excess kurtosis. Matches scipy.stats.kurtosis(bias=False, fisher=True)."""
    n = len(returns)
    if n < 4:
        return 0.0
    mean = np.mean(returns)
    diff = returns - mean
    m2 = np.mean(diff ** 2)
    m4 = np.mean(diff ** 4)
    if m2 <= 0:
        return 0.0
    g2 = m4 / (m2 ** 2) - 3.0  # Fisher (excess) kurtosis, biased
    # Adjusted (sample-stat) form
    return float(((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * g2 + 6.0))


# ---------------------------------------------------------------------------
# Sharpe variants
# ---------------------------------------------------------------------------


def probabilistic_sharpe_ratio(
    returns: np.ndarray,
    benchmark_sr: float = 0.0,
) -> float:
    """
    Probabilistic Sharpe Ratio: P(SR_true > benchmark_sr | observed sample).

    PSR(SR*) = Φ(
        (SR_obs - SR*) · √(N - 1)
        / √(1 − γ₃ · SR_obs + (γ₄ − 1)/4 · SR_obs²)
    )

    where SR_obs is the observed (per-bar, NOT annualised) Sharpe, γ₃ is
    sample skewness, γ₄ is sample excess kurtosis. Returns 0..1.

    Args:
        returns: 1-D array of per-bar returns. PSR is bar-frequency
            invariant — feed daily returns and pass benchmark_sr in daily
            units (e.g. 0.0 / sqrt(252) for an annualised-zero benchmark).
        benchmark_sr: Per-bar benchmark Sharpe (default 0.0).

    Returns:
        Probability the true Sharpe exceeds benchmark_sr, in [0, 1].
        Returns NaN if returns has < 2 samples or zero variance.
    """
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if n < 2:
        return float("nan")

    std = float(np.std(r, ddof=1))
    if std == 0.0:
        return float("nan")
    sr_obs = float(np.mean(r) / std)

    skew = _sample_skewness(r)
    excess_kurt = _sample_excess_kurtosis(r)

    # Standard error of the (per-bar) Sharpe estimate, accounting for
    # non-normality. Note: the formula uses excess kurtosis γ₄ − 1 where γ₄
    # is plain kurtosis; with excess kurtosis we substitute (γ₄_excess + 2).
    var_term = 1.0 - skew * sr_obs + ((excess_kurt + 2.0) / 4.0) * sr_obs * sr_obs
    if var_term <= 0.0:
        return float("nan")

    z = (sr_obs - benchmark_sr) * math.sqrt(n - 1) / math.sqrt(var_term)
    return standard_normal_cdf(z)


def expected_max_sharpe_under_null(
    num_trials: int,
    trial_sharpes_variance: float,
) -> float:
    """
    Expected maximum Sharpe under the null of zero-skill, given N independent
    backtest trials whose Sharpes have variance σ². Bailey & López de Prado:

        E[max SR_n] ≈ √V[SR_n] · ((1 − γ_E)·Φ⁻¹(1 − 1/N) + γ_E·Φ⁻¹(1 − 1/(N·e)))

    where γ_E is the Euler-Mascheroni constant. This is the bar to clear.
    """
    if num_trials < 1:
        raise ValueError("num_trials must be >= 1")
    if trial_sharpes_variance < 0:
        raise ValueError("trial_sharpes_variance must be >= 0")
    if num_trials == 1:
        return 0.0
    sd = math.sqrt(trial_sharpes_variance)
    one_over_n = 1.0 / num_trials
    one_over_ne = 1.0 / (num_trials * math.e)
    term1 = (1.0 - EULER_MASCHERONI) * standard_normal_inv_cdf(1.0 - one_over_n)
    term2 = EULER_MASCHERONI * standard_normal_inv_cdf(1.0 - one_over_ne)
    return sd * (term1 + term2)


def deflated_sharpe_ratio(
    returns: np.ndarray,
    num_trials: int,
    trial_sharpes_variance: float,
) -> float:
    """
    Deflated Sharpe Ratio: PSR with the benchmark set to the expected
    maximum Sharpe under no-skill given N trials.

        DSR = PSR(E[max SR_n])

    A passing strategy is one where DSR > 0.95 (significant at 5%).

    Args:
        returns: 1-D per-bar returns.
        num_trials: Number of independent backtest variants tried during
            selection (the implicit search count). Be honest — count
            hyperparameter sweeps, indicator combinations, etc.
        trial_sharpes_variance: Variance of the per-bar Sharpe estimates
            across those trials. If unknown, a working heuristic is to
            use the variance of the current strategy's bootstrap-resampled
            Sharpe distribution; better is to actually log it during
            backtesting.

    Returns:
        DSR in [0, 1]. NaN if inputs degenerate.
    """
    threshold = expected_max_sharpe_under_null(num_trials, trial_sharpes_variance)
    return probabilistic_sharpe_ratio(returns, benchmark_sr=threshold)
