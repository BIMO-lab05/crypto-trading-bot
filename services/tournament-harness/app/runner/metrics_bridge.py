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
import math
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
    _CANONICAL_METRICS_IMPORT_ERROR: Exception | None = None
except ImportError as _e:  # pragma: no cover — environment-dependent
    _CANONICAL_METRICS_AVAILABLE = False
    _CANONICAL_METRICS_IMPORT_ERROR = _e


logger = logging.getLogger(__name__)


def assert_canonical_metrics_available() -> None:
    """Fail-fast guard for deployed runtimes.

    Raise RuntimeError if the canonical metric chain (compute_returns_metrics,
    evaluate_with_cpcv, probabilistic_sharpe_ratio, deflated_sharpe_ratio,
    cpcv_to_dsr) failed to import at module load.

    Call from FastAPI lifespan and from the runner CLI entrypoint so the
    container surfaces a PYTHONPATH break at boot, not silently at first
    metric call. Host pytest paths that do not exercise compute_all_metrics
    must NOT call this — they tolerate the missing chain on purpose
    (see top-of-module docstring).

    See v1.0 milestone audit INT-02.
    """
    if _CANONICAL_METRICS_AVAILABLE:
        return
    raise RuntimeError(
        "tournament-harness canonical metric chain unavailable -- import failed "
        "at module load. Expected resolution via PYTHONPATH=/app:/opt/ml_retraining "
        "inside the harness Docker image. Underlying ImportError: "
        f"{_CANONICAL_METRICS_IMPORT_ERROR!r}. "
        "TOURN-07 forbids reimplementation; fix the import path. "
        "See v1.0 milestone audit INT-02."
    )


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
) -> Dict[str, float | None]:
    """Compute the full TOURN-02 metric set using imported functions only.

    Returns a dict with keys:
      r2_returns, dir_acc_corrected, oos_sharpe, psr, dsr, cpcv_dsr,
      forecast_path_sharpe, and (when CPCV ran) cpcv_num_trials_used.
    Caller adds train_seconds (wall time, not a 'metric' here).

    Honesty contract (SEV-5 / SEV-7 fixes 2026-08):
      - a metric that could not be computed is None — never a fabricated
        0.0 and never a silent copy of another metric;
      - ``psr`` is always None: the only return series available here is
        the model's own predicted price path, whose Sharpe is emitted
        under the honest name ``forecast_path_sharpe`` instead.
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

    out: Dict[str, float | None] = {}
    # The keys returned by compute_returns_metrics use a 'test_' prefix in
    # ml-retraining (see returns_metrics.py). Strip the prefix for the
    # tournament leaderboard column names (TOURN-02). NaN/inf sentinels
    # (e.g. from a degenerate CPCV _nan_dict) map to None — honest NULL,
    # not a number that survives into the leaderboard (SEV-5).
    for src, dst in (
        ("test_r2_returns", "r2_returns"),
        ("test_dir_acc_corrected", "dir_acc_corrected"),
    ):
        if src in rm:
            val = float(rm[src])
        elif dst in rm:
            val = float(rm[dst])
        else:
            continue
        out[dst] = val if math.isfinite(val) else None

    for src, dst in (
        ("test_cpcv_oos_sharpe", "oos_sharpe"),
        ("test_dsr", "dsr"),
    ):
        if src in cpcv:
            val = float(cpcv[src])
        elif dst in cpcv:
            val = float(cpcv[dst])
        else:
            continue
        out[dst] = val if math.isfinite(val) else None

    # SEV-7 (2026-08): the only return series available here derives from
    # the model's own PREDICTED price path. A smoothly drifting forecast
    # scores a high "Sharpe" on that series while trading nothing — calling
    # it `psr` was dishonest. The number is kept under the honest name
    # `forecast_path_sharpe` (a smoothness/drift diagnostic of the forecast
    # path, NOT evidence of tradeable edge) and `psr` is emitted as None.
    # Consumers tolerate the NULL: the leaderboard `psr` column is a
    # nullable REAL, result_schema accepts None on success rows, and
    # trading-engine preflight reads `psr_ci_published` + `dsr`, never the
    # `psr` metric column.
    pred_returns = np.diff(pred_prices.flatten()) / np.where(
        pred_prices.flatten()[:-1] != 0, pred_prices.flatten()[:-1], 1.0
    )
    fps = float(probabilistic_sharpe_ratio(pred_returns, benchmark_sr=0.0))
    out["forecast_path_sharpe"] = fps if math.isfinite(fps) else None
    out["psr"] = None

    # SEV-5 (2026-08): cpcv_dsr is the honest-N DSR emitted by
    # evaluate_with_cpcv — num_trials = max(valid paths, total CPCV path
    # count), see cpcv_evaluation.py. The old code read
    # `returns_per_path` / `concatenated_returns` keys that
    # evaluate_with_cpcv never emitted, so the fallback silently copied
    # `dsr` on every run. When CPCV could not produce the value (<2 valid
    # paths / degenerate returns) it stays None — NEVER a copy of dsr and
    # NEVER a fabricated 0.0.
    for src in ("test_cpcv_dsr", "cpcv_dsr"):
        if src in cpcv:
            val = float(cpcv[src])
            if math.isfinite(val):
                out["cpcv_dsr"] = val
            break
    # Decision of record (2026-08): verdict artifacts report the
    # num_trials components. Pass the honest-N component to result.json.
    for src in ("test_cpcv_num_trials_used", "cpcv_num_trials_used"):
        if src in cpcv:
            out["cpcv_num_trials_used"] = int(cpcv[src])
            break

    # Defensive: every TOURN-02 metric key exists. A missing/uncomputable
    # metric stays None (honest NULL) — the old `setdefault(k, 0.0)`
    # masked missing metrics as measured zeros (SEV-5).
    for k in (
        "r2_returns",
        "dir_acc_corrected",
        "oos_sharpe",
        "psr",
        "dsr",
        "cpcv_dsr",
        "forecast_path_sharpe",
    ):
        out.setdefault(k, None)

    return out
