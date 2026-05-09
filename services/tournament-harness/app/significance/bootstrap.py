"""Stationary block bootstrap kernel for Phase 4 significance test.

Implements:
- ``derive_seed(tournament_id, symbol)`` — CD-07: blake2b-derived 31-bit seed
  so ``reproduce`` lands on identical resamples per (tournament, symbol).
- ``stationary_block_bootstrap_pvalue(...)`` — D-05/D-06: Politis–Romano
  stationary block bootstrap with geometric block lengths, one-tailed
  ``H1: metric(d) > 0``, additive-smoothed p-value (Davison & Hinkley §4.2).

Design notes
------------
- **One-tailed only.** D-06 wants "ensemble *better* than baseline", not
  "different". Two-tailed wastes statistical power on the side we don't
  care about.
- **Additive smoothing (T-04-06).** ``p = (1 + count) / (n_resamples + 1)``
  guarantees ``p > 0`` even when no resample matches; protects against
  "looks great until you check the formula" reporting.
- **Centering as the H0 implementation.** D-06 specifies "count of
  ``stat_resampled <= 0``". We re-cast that as: shift the sample so its
  mean is zero (``d_centered = d - d.mean()``), then count how many
  resampled metric values are ``>= observed``. The two forms agree for
  any location-equivariant metric (mean, Sharpe, dir_acc); centering is
  preferred because it generalises cleanly to non-mean metrics without
  changing the count.
- **TOURN-07.** No metric helpers defined here. The caller passes a
  ``metric_fn``; the grep gate enforces that no parallel
  ``sharpe`` / ``directional_accuracy`` / ``deflated`` /
  ``compute_returns_metrics`` definitions live in this file.
"""

from __future__ import annotations

import hashlib
import math
from typing import Callable, Dict, Literal

import numpy as np

# TOURN-07 hygiene marker: no parallel metric definitions in this module.
# `metric_fn` is a caller-supplied callable; the grep gate test enforces
# that none of the canonical metric names appear as `def ...` in this file.

Alternative = Literal["greater"]


def derive_seed(tournament_id: str, symbol: str) -> int:
    """CD-07: derive a 31-bit non-negative seed from ``tournament_id`` + ``symbol``.

    Uses ``blake2b(f"{tid}|sig|{symbol}", digest_size=8)``; masks to 31 bits
    so the value fits NumPy's ``default_rng`` accepted range without sign
    pitfalls. Per-symbol independence falls out of the digest input.

    Parameters
    ----------
    tournament_id
        The tournament identifier; must match between the original run and
        ``reproduce`` for identical resamples.
    symbol
        Trading-pair symbol (e.g. ``"BTCUSDT"``).

    Returns
    -------
    int
        Non-negative integer in ``[0, 2**31)``.
    """
    digest = hashlib.blake2b(
        f"{tournament_id}|sig|{symbol}".encode(),
        digest_size=8,
    ).hexdigest()
    return int(digest, 16) & 0x7FFFFFFF


def _generate_block_resample(
    rng: np.random.Generator,
    n: int,
    block_size: int,
) -> np.ndarray:
    """Politis–Romano stationary block resample: ``n`` indices in ``[0, n)``.

    Each block starts at a uniform-random index and has a geometric length
    with mean ``block_size``; consecutive within-block indices wrap around
    modulo ``n`` (circular Politis–Romano). Stops once ``n`` indices are
    emitted.

    Parameters
    ----------
    rng
        Per-call seeded ``np.random.Generator`` — caller owns determinism.
    n
        Length of the original series and of the returned index array.
    block_size
        Mean block length; ``geometric(p=1/block_size)`` controls each
        block's actual length.

    Returns
    -------
    np.ndarray
        ``int64`` array of shape ``(n,)``, every entry in ``[0, n)``.
    """
    idxs = np.empty(n, dtype=np.int64)
    i = 0
    p = 1.0 / float(block_size)
    while i < n:
        start = int(rng.integers(0, n))
        length = int(rng.geometric(p))
        length = min(length, n - i)
        # Circular wrap: indices may roll past n-1 within a block.
        for k in range(length):
            idxs[i + k] = (start + k) % n
        i += length
    return idxs


def stationary_block_bootstrap_pvalue(
    paired_diffs: np.ndarray,
    *,
    metric_fn: Callable[[np.ndarray], float],
    n_resamples: int = 10_000,
    seed: int,
    alternative: Alternative = "greater",
) -> Dict[str, float]:
    """One-tailed stationary block bootstrap p-value with additive smoothing.

    D-05/D-06: tests ``H0: metric(paired_diffs) <= 0`` vs.
    ``H1: metric(paired_diffs) > 0``.

    Parameters
    ----------
    paired_diffs
        1-D numpy array of per-bar paired differences
        ``d_t = ensemble_log_ret_t - baseline_log_ret_t``. With persistence
        baseline (D-04) this collapses to ``d_t = ensemble_log_ret_t``.
    metric_fn
        Callable ``np.ndarray -> float`` — e.g. ``np.mean``, a Sharpe
        helper, or ``dir_acc_corrected`` (caller imports the canonical
        version per TOURN-07 hygiene).
    n_resamples
        Number of bootstrap resamples. Default 10_000 (D-06 production).
    seed
        Required: 31-bit non-negative seed (typically from ``derive_seed``).
    alternative
        Only ``"greater"`` is supported (D-06).

    Returns
    -------
    dict
        Keys: ``observed_metric`` (float), ``p_value`` (float, ``> 0``,
        ``<= 1``), ``n_oos_bars`` (int), ``block_size`` (int),
        ``n_resamples`` (int).

    Raises
    ------
    ValueError
        If ``alternative != "greater"`` or if ``len(paired_diffs) < 2``.
    """
    if alternative != "greater":
        raise ValueError(
            f"only one-tailed 'greater' alternative is supported (D-06); got {alternative!r}"
        )
    d = np.asarray(paired_diffs, dtype=float)
    n = int(d.shape[0])
    if n < 2:
        raise ValueError(
            f"paired_diffs length {n} is too short for the block bootstrap (need >= 2)"
        )

    block_size = max(2, int(math.floor(math.sqrt(n))))
    rng = np.random.default_rng(seed)
    observed = float(metric_fn(d))

    # H0 implementation: shift to zero-mean, then count resamples whose metric
    # equals or exceeds the *observed* (un-shifted) metric. Algebraically
    # equivalent to "count resampled metric <= 0" for location-equivariant
    # metrics; generalises cleanly to non-mean metrics.
    d_centered = d - d.mean()
    count_ge_observed = 0
    for _ in range(n_resamples):
        idxs = _generate_block_resample(rng, n, block_size)
        stat = float(metric_fn(d_centered[idxs]))
        if stat >= observed:
            count_ge_observed += 1

    # D-06: additive smoothing — p > 0 always.
    p_value = (1 + count_ge_observed) / (n_resamples + 1)

    return {
        "observed_metric": observed,
        "p_value": float(p_value),
        "n_oos_bars": n,
        "block_size": int(block_size),
        "n_resamples": int(n_resamples),
    }


__all__ = [
    "Alternative",
    "derive_seed",
    "stationary_block_bootstrap_pvalue",
]
