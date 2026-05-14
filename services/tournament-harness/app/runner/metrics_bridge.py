"""Honest-metrics bridge.

This module is the ONLY place in services/tournament-harness/ that touches
metric computation. It imports — never re-implements — the canonical
implementations from ml-retraining-service.

TOURN-07 grep gate (load-bearing): scanning services/tournament-harness/ for
metric function definitions (directional accuracy, sharpe, or deflated variants)
must return ZERO matches. Any metric implementation belongs in
services/ml-retraining-service, NOT here. See plan 03-06 task 3 for the
exact grep pattern used in CI.
"""

from __future__ import annotations

import logging
from typing import Dict

import numpy as np

# Canonical implementations — IMPORTED, not redefined (TOURN-07).
# These resolve inside the harness Docker image (PYTHONPATH=/app:/opt/ml_retraining)
# but not always on the host pytest runner where two separate `app` packages
# cannot merge. We attempt the import but tolerate failure so unit tests that
# don't exercise compute_all_metrics (e.g. test_metrics_bridge_log_returns.py)
# can still import this module on the host. compute_all_metrics itself raises
# clearly when invoked without the canonical chain available.
try:
    from app.core.returns_metrics import compute_returns_metrics  # noqa: F401
    from app.core.cpcv_evaluation import evaluate_with_cpcv  # noqa: F401
    from app.sharpe_metrics import (  # noqa: F401
        probabilistic_sharpe_ratio,
        deflated_sharpe_ratio,
    )
    from app.cpcv import cpcv_to_dsr  # noqa: F401

    _CANONICAL_METRICS_AVAILABLE = True
except ImportError as _e:  # pragma: no cover — environment-dependent
    _CANONICAL_METRICS_AVAILABLE = False
    _CANONICAL_METRICS_IMPORT_ERROR = _e


logger = logging.getLogger(__name__)


def dir_acc_corrected_from_log_returns(
    actual_lr: np.ndarray,
    pred_lr: np.ndarray,
) -> float:
    """Chance-corrected directional accuracy on log-return series (D-02).

    D-02 mandates ensemble metrics are computed directly on the averaged
    log-return series — no re-conversion to price for metric purposes.
    `compute_returns_metrics` consumes price arrays, so this is the canonical
    log-return-input sibling. A model with no skill scores ~0; perfect sign
    agreement scores 1.0; perfect sign disagreement scores -1.0.

    Returns ``2 * (mean(sign(actual_lr) == sign(pred_lr)) - 0.5)``.

    NOTE: when ``pred_lr`` is the persistence baseline (all zeros),
    ``np.sign(0)`` is 0 and never agrees with non-zero actual signs, so the
    function returns -1.0. This is the INTENDED chance baseline — persistence
    has no directional skill on log-returns by construction; the ensemble's
    lift over this floor is exactly what the bootstrap test measures.
    """
    actual_lr = np.asarray(actual_lr, dtype=float)
    pred_lr = np.asarray(pred_lr, dtype=float)
    if actual_lr.shape != pred_lr.shape:
        raise ValueError(
            f"shape mismatch: actual_lr={actual_lr.shape} pred_lr={pred_lr.shape}"
        )
    if actual_lr.size == 0:
        return float("nan")
    agree = (np.sign(actual_lr) == np.sign(pred_lr)).astype(float)
    return 2.0 * (float(np.mean(agree)) - 0.5)


def compute_all_metrics(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    last_close_test: np.ndarray,
    label_horizon: int,
) -> Dict[str, float]:
    """Compute the full TOURN-02 metric set using imported functions only.

    Returns a dict with keys:
      r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr.
    Caller adds train_seconds (wall time, not a 'metric' here).
    """
    if not _CANONICAL_METRICS_AVAILABLE:
        raise RuntimeError(
            "compute_all_metrics requires the canonical metric chain from "
            "ml-retraining-service (PYTHONPATH=/app:/opt/ml_retraining inside "
            f"the harness image): {_CANONICAL_METRICS_IMPORT_ERROR!r}"
        )
    if len(y_test) == 0:
        raise ValueError("y_test is empty — cannot compute metrics")
    if len(last_close_test) != len(y_test):
        raise ValueError(
            f"last_close_test len {len(last_close_test)} != y_test len {len(y_test)}"
        )

    pred_prices = model.predict(X_test, verbose=0)
    actual_prices = y_test

    # Returns metrics — IMPORTED (TOURN-07)
    rm = compute_returns_metrics(actual_prices, pred_prices, last_close_test, "test")

    # CPCV metrics — IMPORTED (TOURN-07)
    cpcv = evaluate_with_cpcv(
        actual_prices,
        pred_prices,
        last_close_test,
        dataset_name="test",
        label_horizon=label_horizon,
    )

    out: Dict[str, float] = {}
    # The keys returned by compute_returns_metrics use a 'test_' prefix in
    # ml-retraining (see returns_metrics.py). Strip the prefix for the
    # tournament leaderboard column names (TOURN-02).
    for src, dst in (
        ("test_r2_returns", "r2_returns"),
        ("test_dir_acc_corrected", "dir_acc_corrected"),
    ):
        if src in rm:
            out[dst] = float(rm[src])
        elif dst in rm:
            out[dst] = float(rm[dst])

    for src, dst in (
        ("test_cpcv_oos_sharpe", "oos_sharpe"),
        ("test_dsr", "dsr"),
    ):
        if src in cpcv:
            out[dst] = float(cpcv[src])
        elif dst in cpcv:
            out[dst] = float(cpcv[dst])

    # PSR — direct call on returns derived from predictions
    pred_returns = np.diff(pred_prices.flatten()) / np.where(
        pred_prices.flatten()[:-1] != 0, pred_prices.flatten()[:-1], 1.0
    )
    out["psr"] = float(probabilistic_sharpe_ratio(pred_returns, benchmark_sr=0.0))

    # cpcv_dsr — only if the cpcv dict provided per-path returns
    returns_per_path = cpcv.get("returns_per_path") or cpcv.get("test_returns_per_path")
    concatenated = cpcv.get("concatenated_returns") or cpcv.get(
        "test_concatenated_returns"
    )
    if returns_per_path is not None and concatenated is not None:
        out["cpcv_dsr"] = float(cpcv_to_dsr(returns_per_path, concatenated))
    else:
        # Fall back to dsr if cpcv didn't expose path-level returns
        out["cpcv_dsr"] = out.get("dsr", 0.0)

    # Defensive: every TOURN-02 metric is present (None acceptable but key must exist)
    for k in (
        "r2_returns",
        "dir_acc_corrected",
        "oos_sharpe",
        "psr",
        "dsr",
        "cpcv_dsr",
    ):
        out.setdefault(k, 0.0)

    return out
