"""
Evaluation-time CPCV + DSR for trained GRU price predictors.

Background:
    docs/strategy/research-2026-04-29/T0.2-cpcv-design.md §4 calls for
    *evaluation-time* CPCV: derive the strategy-return series from already
    computed (actual, predicted, reference) prices and run combinatorial
    purged folds on it without retraining. The handoff (T0.2) treats this
    as the cheap path; training-time CPCV (45× retrains per symbol) is
    operationally hostile on the WSL stack.

This module is the bridge between ``model_trainer`` (which owns the
arrays in memory at the end of ``train_model``) and the duplicated
``app.cpcv`` / ``app.sharpe_metrics`` modules. It produces a flat
``{dataset_name}_*`` dict in the same key style as ``returns_metrics``
so the trainer can ``test_metrics.update(...)`` it.

Strategy-return convention:
    For each test sample t,
        ``r_t = sign(pred_price_t - last_close_t) * actual_log_return_t``
    where ``actual_log_return_t = log(actual_price_t / last_close_t)``.
    Samples with non-positive prices are dropped (log undefined). Samples
    where ``pred_price_t == last_close_t`` produce r_t = 0 (the model is
    abstaining; treat as a flat position for that bar).

The reference-point (``last_close``) is the *same* one
``returns_metrics.compute_returns_metrics`` uses, so the directional
accuracy and the strategy returns are derived from a single bar
definition — no two-source-of-truth bugs.
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List

import numpy as np

from app.cpcv import CombinatorialPurgedCV, _per_path_sharpe, cpcv_to_dsr

logger = logging.getLogger(__name__)


# Defaults match T0.2-cpcv-design.md (López de Prado's recommendation).
DEFAULT_N_GROUPS = 10
DEFAULT_K_TEST_GROUPS = 2
DEFAULT_EMBARGO_PCT = 0.01


def compute_strategy_returns(
    actual_prices: np.ndarray,
    pred_prices: np.ndarray,
    last_close: np.ndarray,
) -> np.ndarray:
    """
    Strategy returns from a directional bet, sign-of-prediction × realised.

    Returns a 1-D float array of length equal to the number of *valid*
    samples (drops rows with non-positive prices). Predictions equal to
    the reference (sign=0) contribute 0 — flat position for that bar.
    """
    actual_prices = np.asarray(actual_prices, dtype=float)
    pred_prices = np.asarray(pred_prices, dtype=float)
    last_close = np.asarray(last_close, dtype=float)

    if not (len(actual_prices) == len(pred_prices) == len(last_close)):
        raise ValueError(
            f"shape mismatch: actual={actual_prices.shape} "
            f"pred={pred_prices.shape} last_close={last_close.shape}"
        )

    valid = (last_close > 0) & (actual_prices > 0) & (pred_prices > 0)
    if valid.sum() == 0:
        return np.array([], dtype=float)

    a = actual_prices[valid]
    p = pred_prices[valid]
    lc = last_close[valid]

    pred_dir = np.sign(p - lc)  # +1 / 0 / -1
    actual_log_ret = np.log(a / lc)
    return pred_dir * actual_log_ret


def _nan_dict(dataset_name: str) -> Dict[str, float]:
    """Sentinel result when CPCV cannot run (too few samples, all invalid, etc.)."""
    return {
        f"{dataset_name}_dsr": float("nan"),
        f"{dataset_name}_cpcv_sharpe_mean": float("nan"),
        f"{dataset_name}_cpcv_sharpe_std": float("nan"),
        f"{dataset_name}_cpcv_sharpe_median": float("nan"),
        f"{dataset_name}_cpcv_sharpe_ci_low": float("nan"),
        f"{dataset_name}_cpcv_sharpe_ci_high": float("nan"),
        f"{dataset_name}_cpcv_n_paths": 0,
        f"{dataset_name}_cpcv_oos_sharpe": float("nan"),
        f"{dataset_name}_cpcv_n_samples": 0,
        f"{dataset_name}_cpcv_dsr": float("nan"),
        f"{dataset_name}_cpcv_num_trials_used": 0,
    }


def evaluate_with_cpcv(
    actual_prices: np.ndarray,
    pred_prices: np.ndarray,
    last_close: np.ndarray,
    dataset_name: str,
    label_horizon: int,
    n_groups: int = DEFAULT_N_GROUPS,
    k_test_groups: int = DEFAULT_K_TEST_GROUPS,
    embargo_pct: float = DEFAULT_EMBARGO_PCT,
) -> Dict[str, float]:
    """
    Run CPCV on the strategy-return series and return DSR + path Sharpe stats.

    Args:
        actual_prices, pred_prices, last_close: 1-D arrays, same length.
        dataset_name: prefix for the returned keys (e.g. ``"test"``).
        label_horizon: forward horizon (in bars) of the per-sample label.
            For the GRU evaluator this is ``prediction_horizon`` (5).
            Pass ``sequence_length + prediction_horizon - 1`` for a
            conservative purge that also accounts for input-window overlap.
        n_groups, k_test_groups, embargo_pct: see ``CombinatorialPurgedCV``.

    Returns:
        Flat ``{dataset_name}_*`` dict (DSR, per-path Sharpe distribution
        stats, OOS Sharpe, n_samples). On any failure (too few valid bars,
        zero-variance returns, ValueError from CPCV constructor) returns
        a NaN-sentinel dict — the trainer must not abort.

        Two DSR variants are emitted (SEV-5 fix 2026-08):

        - ``{dataset_name}_dsr`` — legacy: num_trials = number of *valid*
          (non-degenerate) CPCV paths.
        - ``{dataset_name}_cpcv_dsr`` — decision-of-record honest N:
          num_trials = max(valid paths, total CPCV path count, e.g. 45 at
          the pinned 10/2). Equal to ``dsr`` when every path is valid;
          strictly more deflated when degenerate paths were dropped.
          ``{dataset_name}_cpcv_num_trials_used`` reports the N used.

    Note:
        Per the design doc §6, paths share training data so per-path
        Sharpes are correlated trials, mildly anticonservative for DSR.
        Document this where DSR is reported.
    """
    strategy_returns = compute_strategy_returns(actual_prices, pred_prices, last_close)
    if len(strategy_returns) < 2:
        logger.warning(
            "CPCV: skipping %s — only %d valid bars",
            dataset_name,
            len(strategy_returns),
        )
        return _nan_dict(dataset_name)

    try:
        cv = CombinatorialPurgedCV(
            n_groups=n_groups,
            k_test_groups=k_test_groups,
            embargo_pct=embargo_pct,
        )
    except ValueError as e:
        logger.warning("CPCV: invalid config for %s — %s", dataset_name, e)
        return _nan_dict(dataset_name)

    try:
        splits = list(cv.split(len(strategy_returns), label_horizon))
    except ValueError as e:
        # Most common: n_samples too small for the configured groups/horizon.
        logger.warning(
            "CPCV: cannot fold %s (n=%d, horizon=%d) — %s",
            dataset_name,
            len(strategy_returns),
            label_horizon,
            e,
        )
        return _nan_dict(dataset_name)

    returns_per_path: List[np.ndarray] = [
        strategy_returns[s.test_idx] for s in splits
    ]

    sharpes = [
        _per_path_sharpe(np.asarray(r, dtype=float)) for r in returns_per_path
    ]
    valid_sharpes = [s for s in sharpes if not math.isnan(s)]

    out = _nan_dict(dataset_name)
    out[f"{dataset_name}_cpcv_n_samples"] = int(len(strategy_returns))

    if not valid_sharpes:
        logger.warning(
            "CPCV: %s — all %d paths produced degenerate Sharpes",
            dataset_name,
            len(splits),
        )
        return out

    arr = np.asarray(valid_sharpes)
    out[f"{dataset_name}_cpcv_n_paths"] = int(len(arr))
    out[f"{dataset_name}_cpcv_sharpe_mean"] = float(np.mean(arr))
    out[f"{dataset_name}_cpcv_sharpe_std"] = (
        float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    )
    out[f"{dataset_name}_cpcv_sharpe_median"] = float(np.median(arr))
    out[f"{dataset_name}_cpcv_sharpe_ci_low"] = float(np.percentile(arr, 5))
    out[f"{dataset_name}_cpcv_sharpe_ci_high"] = float(np.percentile(arr, 95))

    oos_sharpe = _per_path_sharpe(strategy_returns)
    if not math.isnan(oos_sharpe):
        out[f"{dataset_name}_cpcv_oos_sharpe"] = oos_sharpe

    if len(arr) >= 2:
        # Legacy DSR: num_trials defaults to the valid-path count. No
        # config knob exists for a num_trials floor in this service's
        # settings, so the default is kept deliberately (noted per the
        # 2026-08 decision of record; the honest-N variant is below).
        dsr = cpcv_to_dsr(returns_per_path, strategy_returns)
        if not math.isnan(dsr):
            out[f"{dataset_name}_dsr"] = dsr

        # SEV-5: honest-N DSR. Decision of record: N = max(trial-ledger
        # effective count, total CPCV path count). This service has no
        # trial ledger, so N = max(valid paths, cv.n_paths). Components
        # (n_paths valid, num_trials_used) are reported alongside.
        num_trials_used = max(len(arr), cv.n_paths)
        cpcv_dsr = cpcv_to_dsr(
            returns_per_path, strategy_returns, num_trials=num_trials_used
        )
        out[f"{dataset_name}_cpcv_num_trials_used"] = int(num_trials_used)
        if not math.isnan(cpcv_dsr):
            out[f"{dataset_name}_cpcv_dsr"] = cpcv_dsr

    return out
