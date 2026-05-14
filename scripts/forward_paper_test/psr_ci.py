"""PSR with bootstrap percentile confidence interval.

Imports canonical kernels — never re-implements them (TOURN-07 spirit):

  - ``probabilistic_sharpe_ratio`` from
    ``services/risk-metrics-service/app/sharpe_metrics.py``
  - ``_generate_block_resample`` + ``derive_seed`` from
    ``services/tournament-harness/app/significance/bootstrap.py``

**Distinct from Phase 4's H0 bootstrap test:**

The Phase 4 H0 kernel (intentionally NOT imported here) centers its input
for null-distribution construction and returns only a p-value dict — no
per-resample distribution array. Both properties make it structurally wrong
for percentile-CI construction, where we need (a) the original (un-centered)
returns and (b) a distribution of per-resample PSR values to take the
2.5th/97.5th percentiles of. See ``05-RESEARCH.md`` Section "Correct CI
construction pattern" for the full analysis.

This module implements the correct CI kernel: ``_percentile_ci_kernel``
loops over bootstrap resamples produced by ``_generate_block_resample``,
computes PSR on each, filters NaN values, and takes percentiles of the
collected distribution.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Sys.path injection — mirrors services/tournament-harness/app/runner/metrics_bridge.py
# ---------------------------------------------------------------------------

_REPO = Path(__file__).resolve().parents[2]
_SHARPE_METRICS_DIR = _REPO / "services" / "risk-metrics-service" / "app"
_BOOTSTRAP_DIR = _REPO / "services" / "tournament-harness" / "app" / "significance"

for _p in (_SHARPE_METRICS_DIR, _BOOTSTRAP_DIR):
    _p_str = str(_p)
    if _p_str not in sys.path:
        sys.path.insert(0, _p_str)

from sharpe_metrics import probabilistic_sharpe_ratio  # noqa: E402  # type: ignore
from bootstrap import _generate_block_resample  # noqa: E402  # type: ignore


# ---------------------------------------------------------------------------
# Zero-safe baseline guard (vendored from Plan 04-10 SUMMARY)
#
# Source: services/tournament-harness/app/pr/open_pr.py::_zero_safe_baseline_sharpe
# Contract: identical semantics, ≤3 AST body statements (AST gate enforced by
# 05-01 acceptance criterion). The two size/variance guards are collapsed into
# a single boolean to satisfy the gate; behaviour is identical to the original.
# ---------------------------------------------------------------------------


def _zero_safe_baseline_sharpe(
    baseline_log_ret: np.ndarray, *, var_eps: float = 1e-12
) -> float:
    """Return 0.0 for zero-variance input; canonical PSR otherwise. (Plan 04-10)"""
    arr = np.asarray(baseline_log_ret, dtype=float)
    if arr.size < 2 or float(np.std(arr, ddof=1)) < var_eps:
        return 0.0
    return float(probabilistic_sharpe_ratio(arr, benchmark_sr=0.0))


# ---------------------------------------------------------------------------
# Bootstrap percentile CI kernel
# ---------------------------------------------------------------------------


def _percentile_ci_kernel(
    returns: np.ndarray,
    benchmark_sr: float = 0.0,
    n_resamples: int = 10_000,
    block_size: Optional[int] = None,
    seed: int = 0,
    ci_low: float = 0.025,
    ci_high: float = 0.975,
) -> dict:
    """Bootstrap percentile CI for PSR. NOT an H0 test — no centering.

    Parameters
    ----------
    returns:
        1-D array of per-bar log-returns. Must have len >= 30 (enforced by
        the public wrapper).
    benchmark_sr:
        Benchmark Sharpe passed to ``probabilistic_sharpe_ratio``.
    n_resamples:
        Number of bootstrap resamples.
    block_size:
        Mean block length for the stationary block bootstrap. Defaults to
        ``max(1, int(len(returns) ** 0.5))`` (standard rule of thumb).
    seed:
        Seed for ``np.random.default_rng`` — set for reproducibility.
    ci_low, ci_high:
        Quantile levels for the lower and upper CI bounds (default 2.5% / 97.5%).

    Returns
    -------
    dict
        Keys: ``psr_observed``, ``psr_ci_low``, ``psr_ci_high``,
        ``n_resamples_valid``, ``n_resamples``.
    """
    n = len(returns)
    if block_size is None:
        block_size = max(1, int(n**0.5))
    rng = np.random.default_rng(seed)
    resampled_psrs: list[float] = []
    for _ in range(n_resamples):
        idxs = _generate_block_resample(rng, n, block_size)
        r = returns[idxs]
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=benchmark_sr)
        if not np.isnan(psr):
            resampled_psrs.append(psr)
    arr = np.array(resampled_psrs)
    n_valid = len(arr)
    if n_valid < n_resamples * 0.9:
        warnings.warn(
            f"PSR-CI: only {n_valid}/{n_resamples} resamples produced finite PSR "
            "— input window may be pathological",
            UserWarning,
            stacklevel=3,
        )
    psr_ci_low = (
        float(np.percentile(arr, ci_low * 100)) if n_valid > 0 else float("nan")
    )
    psr_ci_high = (
        float(np.percentile(arr, ci_high * 100)) if n_valid > 0 else float("nan")
    )
    return {
        "psr_observed": probabilistic_sharpe_ratio(returns, benchmark_sr=benchmark_sr),
        "psr_ci_low": psr_ci_low,
        "psr_ci_high": psr_ci_high,
        "n_resamples_valid": n_valid,
        "n_resamples": n_resamples,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_psr_with_bootstrap_ci(
    returns: np.ndarray,
    *,
    seed: int,
    n_resamples: int = 10_000,
    block_size: Optional[int] = None,
) -> dict:
    """Compute PSR point estimate + bootstrap percentile CI.

    Parameters
    ----------
    returns:
        1-D array of per-bar log-returns. Must have at least 30 observations
        (T-05-01-05 usability guard — a 7-day run on 5 symbols typically yields
        50-200 per-trade returns; per-day yields only 7, which is insufficient).
    seed:
        Reproducibility seed (31-bit integer). Use ``derive_seed(flag, run_id)``
        for consistent cross-run comparisons.
    n_resamples:
        Number of bootstrap resamples (default 10_000).
    block_size:
        Override mean block length; defaults to ``max(1, int(len(returns) ** 0.5))``.

    Returns
    -------
    dict with keys:
        ``psr_point``          — point PSR of the raw series (0.0 for zero-variance input).
        ``psr_ci_low``         — 2.5th percentile of bootstrap PSR distribution.
        ``psr_ci_high``        — 97.5th percentile of bootstrap PSR distribution.
        ``n_resamples``        — requested number of resamples.
        ``n_resamples_valid``  — resamples that produced finite PSR (NaN-filtered).
        ``block_size``         — actual mean block length used.
        ``seed``               — seed value used.
        ``n_bars``             — length of the input series.
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 30:
        raise ValueError(
            "forward-paper-test requires per-trade returns or sub-daily bars; "
            f"got fewer than 30 observations (got {len(r)})"
        )

    n = len(r)
    if block_size is None:
        block_size = max(1, int(n**0.5))

    # Zero-variance carve-out: short-circuit without invoking the bootstrap loop.
    # Mirrors the Plan 04-10 pattern in services/tournament-harness/app/pr/open_pr.py.
    psr_point = _zero_safe_baseline_sharpe(r)
    if psr_point == 0.0 and float(np.std(r, ddof=1)) < 1e-12:
        return {
            "psr_point": 0.0,
            "psr_ci_low": 0.0,
            "psr_ci_high": 0.0,
            "n_resamples": n_resamples,
            "n_resamples_valid": 0,
            "block_size": block_size,
            "seed": seed,
            "n_bars": n,
        }

    kernel_result = _percentile_ci_kernel(
        r,
        benchmark_sr=0.0,
        n_resamples=n_resamples,
        block_size=block_size,
        seed=seed,
    )
    return {
        "psr_point": psr_point,
        "psr_ci_low": kernel_result["psr_ci_low"],
        "psr_ci_high": kernel_result["psr_ci_high"],
        "n_resamples": n_resamples,
        "n_resamples_valid": kernel_result["n_resamples_valid"],
        "block_size": block_size,
        "seed": seed,
        "n_bars": n,
    }


def load_run_returns(run_dir: Path) -> np.ndarray:
    """Load per-trade log-returns from a completed run's ``run.json``.

    Parameters
    ----------
    run_dir:
        Directory containing ``run.json`` (written by the operator or by
        ``complete_run.py`` after the paper-trade window closes).

    Returns
    -------
    np.ndarray
        1-D float array of log-returns.

    Raises
    ------
    FileNotFoundError
        If ``run.json`` does not exist in ``run_dir``.
    ValueError
        If the ``returns`` array is empty or contains NaN values.
    """
    run_json_path = Path(run_dir) / "run.json"
    if not run_json_path.exists():
        raise FileNotFoundError(f"run.json not found in {run_dir}")

    with open(run_json_path) as f:
        data = json.load(f)

    raw = data.get("returns", [])
    arr = np.asarray(raw, dtype=float)

    if arr.size == 0:
        raise ValueError(
            f"returns array is empty in {run_json_path} — "
            "run may not have completed or produced any trades"
        )

    if np.any(np.isnan(arr)):
        raise ValueError(
            f"returns array contains NaN values in {run_json_path} — "
            "check the paper-trade log for corrupt entries"
        )

    return arr


__all__ = ["compute_psr_with_bootstrap_ci", "load_run_returns"]
