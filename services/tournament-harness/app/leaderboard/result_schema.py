"""Schema validator for experiment-container result.json (D-16).

Trust boundary: the experiment container is untrusted output. This module is
the only sanitiser between /output/result.json and the leaderboard SQL insert.
Bounded size, typed enum membership, and numeric sanity ranges enforced here.
"""

import math
from typing import Any, Dict, Tuple


MAX_RESULT_BYTES = 262_144  # 256 KB hard cap (T-03-07, T-03-10)

VALID_ARCHITECTURES = {"gru", "lstm", "transformer", "tcn"}
VALID_TARGET_MODES = {"price", "log_returns"}
VALID_FAILURE_REASONS = {
    "oom_killed",
    "nan_loss",
    "timeout",
    "exit_nonzero",
    "train_diverged",
    "db_unreachable",
    "unknown",
}

REQUIRED_TOP_LEVEL = (
    "status",
    "run_id",
    "tournament_id",
    "architecture",
    "symbol",
    "horizon",
    "target_mode",
    "hp_hash",
    "git_sha",
    "tournament_start_ts",
)
REQUIRED_METRICS_ON_SUCCESS = (
    "r2_returns",
    "dir_acc_corrected",
    "oos_sharpe",
    "psr",
    "dsr",
    "cpcv_dsr",
    "train_seconds",
)

# SEV-5/SEV-7 (2026-08): the honest metric pipeline emits None for any
# metric it could not compute (never a fabricated 0.0), and `psr` is now
# ALWAYS None — the forecast-path Sharpe moved to the honest name
# `forecast_path_sharpe` (see metrics_bridge). These columns are nullable
# REALs in the leaderboard schema; None passes through to SQL NULL.
# `train_seconds` is wall-clock, always measurable, and stays
# required-finite. The key must still be PRESENT on success rows — only
# its value may be None.
NULLABLE_METRICS_ON_SUCCESS = frozenset(
    {"r2_returns", "dir_acc_corrected", "oos_sharpe", "psr", "dsr", "cpcv_dsr"}
)

# Sanity ranges for honest-metrics columns. Outside these = corrupt result.
METRIC_RANGES = {
    "r2_returns": (-100.0, 1.0),
    "dir_acc_corrected": (0.0, 1.0),
    "oos_sharpe": (-100.0, 100.0),
    "psr": (0.0, 1.0),
    "dsr": (0.0, 1.0),
    "cpcv_dsr": (0.0, 1.0),
    "train_seconds": (0.0, 86_400.0),  # 24h hard ceiling
}


def _is_finite_number(x: Any) -> bool:
    return (
        isinstance(x, (int, float))
        and not isinstance(x, bool)
        and math.isfinite(float(x))
    )


def validate(payload: Dict[str, Any], raw_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
    """Validate a /output/result.json payload.

    Args:
        payload: parsed JSON dict.
        raw_bytes: the on-disk bytes (size cap enforced on these, NOT the dict).

    Returns:
        (status, normalised_payload) — normalised_payload is the same dict but
        with all metric fields coerced to float and missing-on-failure metrics
        set to None.

    Raises:
        ValueError: any invariant violation. Caller persists a failure row with
            failure_reason='unknown' and stderr_tail set to the exception message.
    """
    if not isinstance(raw_bytes, (bytes, bytearray)):
        raise ValueError("raw_bytes must be bytes")
    if len(raw_bytes) > MAX_RESULT_BYTES:
        raise ValueError(
            f"result.json exceeds 256KB cap ({len(raw_bytes)} bytes > {MAX_RESULT_BYTES})"
        )
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be dict, got {type(payload).__name__}")

    # Required top-level
    missing = [k for k in REQUIRED_TOP_LEVEL if k not in payload]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    status = payload["status"]
    if status not in {"success", "failed"}:
        raise ValueError(f"invalid status: {status!r}")

    if payload["architecture"] not in VALID_ARCHITECTURES:
        raise ValueError(f"invalid architecture: {payload['architecture']!r}")
    if payload["target_mode"] not in VALID_TARGET_MODES:
        raise ValueError(f"invalid target_mode: {payload['target_mode']!r}")

    horizon = payload["horizon"]
    if not (
        isinstance(horizon, int)
        and not isinstance(horizon, bool)
        and 1 <= horizon <= 256
    ):
        raise ValueError(f"horizon must be int in [1,256], got {horizon!r}")

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError(f"metrics must be dict, got {type(metrics).__name__}")

    normalised = dict(payload)

    if status == "success":
        for m in REQUIRED_METRICS_ON_SUCCESS:
            if m not in metrics:
                raise ValueError(f"success row missing metric: {m}")
            v = metrics[m]
            if v is None and m in NULLABLE_METRICS_ON_SUCCESS:
                # Honest NULL: metric was uncomputable (or, for psr,
                # intentionally not emitted). Persisted as SQL NULL.
                continue
            if not _is_finite_number(v):
                raise ValueError(f"metric {m} must be finite number, got {v!r}")
            lo, hi = METRIC_RANGES[m]
            if not (lo <= float(v) <= hi):
                raise ValueError(f"metric {m} out of sanity range [{lo},{hi}]: {v}")
            metrics[m] = float(v)
        normalised["failure_reason"] = None
        normalised["failure_stderr_tail"] = None
    else:  # failed
        reason = payload.get("reason") or payload.get("failure_reason")
        if reason not in VALID_FAILURE_REASONS:
            raise ValueError(f"failed row has invalid failure_reason: {reason!r}")
        normalised["failure_reason"] = reason
        # On failure, metrics are optional; if present, fill with None for absent fields.
        for m in REQUIRED_METRICS_ON_SUCCESS:
            metrics.setdefault(m, None)

    normalised["metrics"] = metrics
    return status, normalised
