"""
Combinatorial Purged Cross-Validation (CPCV).

Reference:
    López de Prado, M. (2018). *Advances in Financial Machine Learning*,
    chapter 7.4 (Listings 7.3 "getTrainTimes" and 7.4 "getEmbargoTimes").
    Bailey, Borwein, López de Prado, Zhu (2017). "The Probability of
    Backtest Overfitting."

Why this lives alongside sharpe_metrics.py:
    CPCV's primary downstream consumer is the Deflated Sharpe Ratio
    (sharpe_metrics.deflated_sharpe_ratio): the path count *is* the
    trial count, and the variance of per-path Sharpes *is*
    `trial_sharpes_variance`. The bridge `cpcv_to_dsr` makes this link
    explicit so callers don't have to guess at num_trials — see the
    warning at sharpe_metrics.py:240-245.

Stdlib + numpy only — no scipy, no sklearn.

Tradeoffs (more N, more paths, smaller groups → noisier per-fold Sharpe;
more k → coarser test sets, fewer paths). Default N=10, k=2 yields 45
paths and is López de Prado's recommended starting point.

This module ships *evaluation-time* CPCV: it accepts already-computed
predicted returns and runs purged folds over them. Training-time CPCV
(retrain N×C(N,k) times) is the textbook recipe but operationally
hostile for the GRU stack — see docs/strategy/research-2026-04-29/
T0.2-cpcv-design.md for the rationale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Iterator, List, Sequence, Tuple

import numpy as np

from app.sharpe_metrics import deflated_sharpe_ratio


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CPCVSplit:
    """One train/test fold from a CPCV run."""

    train_idx: np.ndarray
    test_idx: np.ndarray
    test_groups: Tuple[int, ...]
    path_id: int


# ---------------------------------------------------------------------------
# Combinatorial Purged Cross-Validator
# ---------------------------------------------------------------------------


class CombinatorialPurgedCV:
    """
    Yield C(N, k) train/test splits with purging and embargo.

    A test fold consists of `k_test_groups` contiguous bar-time groups out of
    `n_groups` total. Every combination is enumerated (deterministic order
    via itertools.combinations). For each fold, the train set is everything
    not in test, *minus*:

    - Purged samples whose label window `[s, s + label_horizon)` overlaps
      any test sample's label window `[t, t + label_horizon)`. For a
      contiguous test group `[a, b)`, this excludes train indices in the
      open interval `(a - label_horizon, b + label_horizon - 1)`.
    - Embargoed samples in `[b, b + embargo_len)` after each test group.
      Embargo only fires on the right side — serial correlation flows
      forward in time (Listing 7.4).

    Args:
        n_groups: Number of contiguous bar-time groups (≥ 2).
        k_test_groups: Number of groups held out per fold (1 ≤ k < n_groups).
        embargo_pct: Fraction of n_samples to embargo right of each test
            group (0 ≤ p < 1). Default 1%.

    Raises:
        ValueError: If args violate the constraints above.
    """

    def __init__(
        self,
        n_groups: int = 10,
        k_test_groups: int = 2,
        embargo_pct: float = 0.01,
    ):
        if n_groups < 2:
            raise ValueError(f"n_groups must be >= 2, got {n_groups}")
        if not (1 <= k_test_groups < n_groups):
            raise ValueError(
                f"k_test_groups must be in [1, n_groups - 1], got {k_test_groups}"
            )
        if not (0.0 <= embargo_pct < 1.0):
            raise ValueError(f"embargo_pct must be in [0, 1), got {embargo_pct}")
        self.n_groups = n_groups
        self.k_test_groups = k_test_groups
        self.embargo_pct = embargo_pct

    @property
    def n_paths(self) -> int:
        return math.comb(self.n_groups, self.k_test_groups)

    def _group_bounds(self, n_samples: int) -> List[Tuple[int, int]]:
        """Return list of (start, end_exclusive) for each contiguous group."""
        cuts = np.array_split(np.arange(n_samples), self.n_groups)
        return [(int(arr[0]), int(arr[-1]) + 1) for arr in cuts]

    def _embargo_len(self, n_samples: int) -> int:
        return max(1, int(math.ceil(self.embargo_pct * n_samples))) if self.embargo_pct > 0 else 0

    def split(self, n_samples: int, label_horizon: int) -> Iterator[CPCVSplit]:
        """
        Yield C(N, k) folds for `n_samples` whose labels each span
        `label_horizon` bars forward (e.g., for a 12-bar-ahead forecast,
        pass label_horizon=12).

        For models with input-window leakage on top of label leakage (e.g.,
        a GRU whose input also runs back `sequence_length` bars), the
        conservative effective horizon is `sequence_length + prediction_horizon - 1`.
        """
        if n_samples < 2:
            raise ValueError(f"n_samples must be >= 2, got {n_samples}")
        if label_horizon < 1:
            raise ValueError(f"label_horizon must be >= 1, got {label_horizon}")
        embargo_len = self._embargo_len(n_samples)
        # Sanity: each group must comfortably exceed purge + embargo width.
        min_required = self.n_groups * (label_horizon + embargo_len + 1)
        if n_samples < min_required:
            raise ValueError(
                f"n_samples={n_samples} too small for n_groups={self.n_groups}, "
                f"label_horizon={label_horizon}, embargo_len={embargo_len}; "
                f"need at least {min_required}"
            )

        bounds = self._group_bounds(n_samples)
        all_indices = np.arange(n_samples)

        for path_id, test_combo in enumerate(
            combinations(range(self.n_groups), self.k_test_groups)
        ):
            test_mask = np.zeros(n_samples, dtype=bool)
            purge_mask = np.zeros(n_samples, dtype=bool)
            for g in test_combo:
                a, b = bounds[g]
                test_mask[a:b] = True
                # Purge: train labels [s, s+h) overlapping [a, b+h-1)
                # → train indices in open interval (a-h, b+h-1)
                # → integer range [a-h+1, b+h-2]
                lo = max(0, a - label_horizon + 1)
                hi = min(n_samples, b + label_horizon - 1)  # exclusive
                if hi > lo:
                    purge_mask[lo:hi] = True
                # Embargo on right side only
                emb_end = min(n_samples, b + embargo_len)
                if emb_end > b:
                    purge_mask[b:emb_end] = True

            train_mask = ~test_mask & ~purge_mask
            yield CPCVSplit(
                train_idx=all_indices[train_mask],
                test_idx=all_indices[test_mask],
                test_groups=tuple(test_combo),
                path_id=path_id,
            )


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _per_path_sharpe(returns: np.ndarray) -> float:
    """Per-bar Sharpe (mean / std with ddof=1) or NaN if degenerate."""
    if len(returns) < 2:
        return float("nan")
    std = float(np.std(returns, ddof=1))
    # np.std on near-constant arrays returns ~1e-19 from finite-precision
    # rounding rather than exact 0; treat any near-zero std as degenerate.
    if std < 1e-15:
        return float("nan")
    return float(np.mean(returns) / std)


def cpcv_sharpe_distribution(returns_per_path: Sequence[np.ndarray]) -> dict:
    """
    Compute summary stats over per-path Sharpe ratios.

    Each element of `returns_per_path` is the strategy return series for one
    CPCV path. We compute one Sharpe per path and report mean / std /
    median / 5th-95th percentile / count of valid paths. Empty or
    zero-variance paths are dropped.
    """
    if len(returns_per_path) == 0:
        raise ValueError("returns_per_path is empty")

    sharpes: List[float] = []
    for r in returns_per_path:
        s = _per_path_sharpe(np.asarray(r, dtype=float))
        if not math.isnan(s):
            sharpes.append(s)

    if not sharpes:
        return {
            "mean": float("nan"),
            "std": float("nan"),
            "median": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "n_paths": 0,
        }

    arr = np.asarray(sharpes)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        "median": float(np.median(arr)),
        "ci_low": float(np.percentile(arr, 5)),
        "ci_high": float(np.percentile(arr, 95)),
        "n_paths": len(arr),
    }


def cpcv_to_dsr(
    returns_per_path: Sequence[np.ndarray],
    concatenated_returns: np.ndarray,
) -> float:
    """
    Bridge CPCV path returns to the Deflated Sharpe Ratio.

    Variance of per-path Sharpes feeds DSR's `trial_sharpes_variance`; the
    path count feeds `num_trials`. DSR is then evaluated against
    `concatenated_returns` (typically all out-of-sample bars reassembled).

    A passing strategy clears DSR > 0.95 (significance at 5%, accounting
    for both non-normality and selection bias). Returns NaN if fewer than
    2 valid paths exist.

    Caveat: paths share training data so per-path Sharpes are *correlated*
    trials, violating the independence assumption in DSR's
    expected_max_sharpe_under_null formula. This is mildly anticonservative;
    document it where you report DSR.
    """
    sharpes: List[float] = []
    for r in returns_per_path:
        s = _per_path_sharpe(np.asarray(r, dtype=float))
        if not math.isnan(s):
            sharpes.append(s)

    if len(sharpes) < 2:
        return float("nan")

    trial_var = float(np.var(np.asarray(sharpes), ddof=1))
    return deflated_sharpe_ratio(
        np.asarray(concatenated_returns, dtype=float),
        num_trials=len(sharpes),
        trial_sharpes_variance=trial_var,
    )
