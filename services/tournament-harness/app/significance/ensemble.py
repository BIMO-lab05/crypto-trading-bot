"""Per-symbol ensemble construction (D-01) + mean-log-returns aggregation (D-02).

Selection:
  D-01 — for each symbol, pick the top-N runs (default N=3) ordered by
         (dsr desc, cpcv_dsr desc, oos_sharpe desc, created_at asc).
         Only `status="success"` rows are eligible. CD-08 — symbols with fewer
         than N successful runs are returned with whatever they have; the
         caller (04-02 win-gate) decides whether to flag `[insufficient runs]`.

Aggregation:
  D-02 — equal-weighted mean of predicted log-returns across the N members per
         timestep. The averaged series is what the bootstrap test consumes.

TOURN-07 hygiene: this module IMPORTS the canonical metric helpers from
metrics_bridge but MUST NOT redefine any of them (sharpe / dir-acc / dsr /
compute_returns_metrics). The grep gate
test_no_parallel_metric_definitions_in_module enforces this.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np

# TOURN-07 + D-13 grep-gate compliance: this module MUST NOT redefine any of
# `directional_accuracy`, `sharpe`, `deflated`, or `compute_returns_metrics`.
# The grep-gate test test_no_parallel_metric_definitions_in_module enforces
# the rule statically. When 04-02 / 04-03 need the canonical implementations,
# they import directly from `app.runner.metrics_bridge` (which itself imports
# from ml-retraining-service). We deliberately do NOT eager-import the bridge
# at this module's top level — `app.core.returns_metrics` only resolves inside
# the harness Docker image (PYTHONPATH=/app:/opt/ml_retraining). On the host
# pytest runner, eager import would fail before any test can collect.
#
# Deviation rule 3 from plan 04-01 task 2: the plan listed
#   `from app.runner.metrics_bridge import compute_all_metrics  # noqa: F401`
# as the contract marker, but that import is unresolvable outside the
# container. Replaced with this comment + the existing grep-gate test (which
# is the actual TOURN-07 enforcement mechanism per plan 03-06 task 3).


def metric_sort_value(v: Any) -> float:
    """NaN/None-safe descending-sort key for metric columns (SEV-4a fix 2026-08).

    The previous key ``-float(r.get("dsr") or 0.0)`` let NaN through:
    ``float("nan") or 0.0`` evaluates to NaN (NaN is truthy), and a single
    NaN key poisons ``list.sort()``'s comparisons, producing an arbitrary
    order in which a NaN-dsr row can be "selected" over a real one.
    Missing/None/NaN/uncastable metrics map to -inf: worst possible,
    sorted last, never selected above any finite value.
    """
    if v is None:
        return float("-inf")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("-inf")
    return f if math.isfinite(f) else float("-inf")


def select_top_n_per_symbol(
    rows: Iterable[Dict[str, Any]], n: int = 3
) -> Dict[str, List[Dict[str, Any]]]:
    """D-01: per-symbol top-N by DSR with deterministic tie-break.

    Tie-break order:
      1. dsr desc
      2. cpcv_dsr desc
      3. oos_sharpe desc
      4. created_at asc (deterministic, breaks ties on the metric trio)

    Only `status="success"` rows are considered. Symbols with fewer than N
    eligible rows are returned with their available members (CD-08); caller
    decides what to do with the short list.
    """
    successful: List[Dict[str, Any]] = [r for r in rows if r.get("status") == "success"]
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for r in successful:
        by_symbol.setdefault(r["symbol"], []).append(r)
    out: Dict[str, List[Dict[str, Any]]] = {}
    for symbol, srows in by_symbol.items():
        # SEV-4a: metric_sort_value maps None/NaN to -inf so they sort last
        # and can never outrank a finite dsr.
        srows.sort(
            key=lambda r: (
                -metric_sort_value(r.get("dsr")),
                -metric_sort_value(r.get("cpcv_dsr")),
                -metric_sort_value(r.get("oos_sharpe")),
                str(r.get("created_at") or ""),
            )
        )
        # SEV-4b (2026-08): taking the top-N of M candidates by DSR is a
        # selection MAXIMUM that the per-run DSR does not account for
        # (Bailey & Lopez de Prado 2014: the expected max Sharpe under the
        # no-skill null grows with the number of trials, ~sqrt(2 ln N); a
        # DSR deflated for its own run's num_trials is still undeflated
        # for the across-runs pick). The leaderboard rows carry no return
        # series, so the honest adjusted DSR cannot be recomputed HERE —
        # instead each selected row is annotated with the selection pool
        # size M. Any downstream consumer that recomputes DSR from stored
        # predictions must pass
        #   num_trials = cpcv_num_trials_used + (selection_pool_size - 1)
        # via ``cpcv_to_dsr(..., num_trials=...)``. Within one symbol's
        # pool every candidate shares the same M, so the RANKING above is
        # unchanged by the common deflation; only the reported
        # significance of the selected member is affected.
        pool_size = len(srows)
        out[symbol] = [
            {**r, "selection_pool_size": pool_size} for r in srows[:n]
        ]
    return out


def aggregate_log_returns(
    member_log_returns: Sequence[np.ndarray],
) -> np.ndarray:
    """D-02: equal-weighted mean of predicted log-returns across ensemble members.

    Inputs: a sequence of 1-D numpy arrays, all of identical shape (N_oos,).
    Output: shape (N_oos,) float array — `mean(stack, axis=0)`.

    Raises ValueError if the input is empty or member shapes don't match.
    """
    if len(member_log_returns) == 0:
        raise ValueError("aggregate_log_returns requires at least one member array")
    shapes = {arr.shape for arr in member_log_returns}
    if len(shapes) != 1:
        raise ValueError(
            f"member log-return arrays must share shape; got {sorted(map(str, shapes))}"
        )
    stacked = np.stack(list(member_log_returns), axis=0)  # (n_members, N_oos)
    return stacked.mean(axis=0)


def _finite_or_none(value: Any) -> float | None:
    """Finite float or None — member_descriptor's honest-NULL companion to
    metric_sort_value (which maps the same inputs to -inf for sorting)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def member_descriptor(row: Dict[str, Any]) -> Dict[str, Any]:
    """Strip a snapshot row to the D-03 ensemble-member fields.

    D-03 — ensemble.json carries config-by-reference only:
      run_id, architecture, hp_hash, dsr, selection_pool_size.
    No oos_sharpe/cpcv_dsr/dir_acc here — those live in the leaderboard, not
    the ensemble artifact (the reproducer re-derives them from run_id+config).

    ``selection_pool_size`` (SEV-4b, 2026-08) is the number of candidates
    the member was picked from; the carried ``dsr`` is NOT deflated for
    that selection (Bailey-LdP selection bias) — consumers recomputing DSR
    must widen num_trials by (selection_pool_size - 1). None when the row
    was not produced by ``select_top_n_per_symbol``.
    """
    return {
        "run_id": row["run_id"],
        "architecture": row["architecture"],
        "hp_hash": row["hp_hash"],
        # None/NaN stay None in the artifact of record — never a fabricated 0.0
        # (same contract as metric_sort_value; NaN is truthy so `or 0.0` is wrong).
        "dsr": _finite_or_none(row.get("dsr")),
        "selection_pool_size": row.get("selection_pool_size"),
    }


__all__ = [
    "metric_sort_value",
    "select_top_n_per_symbol",
    "aggregate_log_returns",
    "member_descriptor",
]
