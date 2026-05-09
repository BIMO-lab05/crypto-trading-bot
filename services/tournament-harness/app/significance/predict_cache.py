"""Predict-only re-hydration + on-disk cache for ensemble members (CD-11).

Why this module exists:
  Phase 3 snapshots are config-by-reference (D-03 / D-18) — they don't persist
  predictions. Phase 4 needs the OOS log-return series for each top-3 ensemble
  member to feed the bootstrap test (D-05/D-06). Re-running predict against
  the same OOS klines + the same model+seed reproduces those arrays
  deterministically (Phase 3 D-13 reproducibility contract). The cache here
  stores the predict result on first call so re-runs of `tournament open-pr`
  and `tournament reproduce` (04-03) skip recompute.

Cache contract (CD-11):
  data/cache/{tournament_id}/predictions/{run_id}.npz
  Each .npz holds three 1-D arrays of equal length: pred_prices, actual_prices,
  last_close — the exact tuple `compute_returns_metrics` expects.

NOTE on integration-points conflict:
  04-CONTEXT.md "Integration Points" claims `open-pr` does NOT touch
  TimescaleDB. CD-11 contradicts that — re-running predict on OOS klines
  pulls them from TimescaleDB via the existing `tournament_reader` role
  (Phase 3 D-09). CD-11 wins because the bootstrap can't run without the
  OOS log-return series. The actual db read happens in the predict_fn
  callback wired by 04-03 (`open-pr` CLI handler), NOT in this module.
  This module only owns the cache contract + the callback protocol.

Threat model (T-04-01):
  Both tournament_id and run_id appear in cache paths. Both are validated
  against the same regex (`^[A-Za-z0-9._\\-]+$`) snapshot.py uses, refusing
  any traversal sequence (`..`, `/`, ...) before any path is constructed.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Callable, Dict

import numpy as np

logger = logging.getLogger(__name__)


# Mirrors the snapshot.py path-traversal guard. Allows alphanumerics, dot,
# underscore, hyphen — refuses slashes and `..`.
_TID_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def _cache_path(harness_root: Path, tournament_id: str, run_id: str) -> Path:
    """Build the per-(tournament, run) cache file path. T-04-01 mitigation.

    Validates BOTH tournament_id and run_id against `_TID_RE` before
    constructing the path; bare ValueError for any traversal-shaped input.
    """
    if not _TID_RE.fullmatch(tournament_id):
        raise ValueError(f"invalid tournament_id for cache path: {tournament_id!r}")
    if not _TID_RE.fullmatch(run_id):
        raise ValueError(f"invalid run_id for cache path: {run_id!r}")
    return (
        Path(harness_root)
        / "data"
        / "cache"
        / tournament_id
        / "predictions"
        / f"{run_id}.npz"
    )


def get_or_build_predictions(
    *,
    harness_root: Path,
    tournament_id: str,
    run_id: str,
    predict_fn: Callable[[], Dict[str, np.ndarray]],
) -> Dict[str, np.ndarray]:
    """Return cached predictions for (tournament_id, run_id) or build + cache.

    The `predict_fn` callback is wired by the 04-03 `open-pr` CLI handler;
    here we only own the protocol: a zero-arg callable returning a dict with
    keys `pred_prices`, `actual_prices`, `last_close`, all 1-D numpy arrays
    of identical length.

    Cache layout (CD-11):
      data/cache/{tournament_id}/predictions/{run_id}.npz

    The .npz write follows the same atomic discipline as artifacts.py
    (mkstemp + os.replace + cleanup-on-failure), so partial writes never
    leave a corrupt cache entry.
    """
    path = _cache_path(Path(harness_root), tournament_id, run_id)
    if path.exists():
        logger.info("predict cache hit: %s", path)
        with np.load(path) as data:
            return {
                "pred_prices": np.asarray(data["pred_prices"]),
                "actual_prices": np.asarray(data["actual_prices"]),
                "last_close": np.asarray(data["last_close"]),
            }
    logger.info("predict cache miss → recompute: %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    result = predict_fn()
    # Validate shapes BEFORE writing — a bad payload must never poison the cache.
    pred = np.asarray(result["pred_prices"])
    if pred.ndim != 1:
        raise ValueError(f"pred_prices must be 1-D; got shape {pred.shape}")
    n = pred.shape[0]
    actual = np.asarray(result["actual_prices"])
    last = np.asarray(result["last_close"])
    if actual.shape != (n,):
        raise ValueError(f"actual_prices shape {actual.shape} != expected ({n},)")
    if last.shape != (n,):
        raise ValueError(f"last_close shape {last.shape} != expected ({n},)")

    # numpy.savez ALWAYS appends ".npz" if the target path doesn't already
    # end in ".npz". Use a tempfile suffix that ends in ".npz" so savez writes
    # exactly where we expect — no ".npz.tmp" surprise. We still write through
    # mkstemp + os.replace for atomicity.
    fd, tmp = tempfile.mkstemp(prefix="pred.", suffix=".tmp.npz", dir=str(path.parent))
    os.close(fd)
    try:
        # savez sees ".npz" suffix → writes to `tmp` directly (no extra suffix added).
        np.savez(tmp, pred_prices=pred, actual_prices=actual, last_close=last)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"pred_prices": pred, "actual_prices": actual, "last_close": last}


def log_returns_from_predictions(
    pred_prices: np.ndarray, last_close: np.ndarray
) -> np.ndarray:
    """Per-bar log return = log(pred_prices / last_close).

    Mirrors the convention `returns_metrics.py:compute_returns_metrics` uses
    when it converts predicted prices to a log-return series. `last_close <= 0`
    is treated as 1.0 to avoid div-by-zero / log-of-negative; in real OOS data
    crypto closes are strictly positive — this branch is defensive only.
    """
    last_close_safe = np.where(last_close > 0, last_close, 1.0)
    return np.log(pred_prices / last_close_safe)


__all__ = [
    "get_or_build_predictions",
    "log_returns_from_predictions",
]
