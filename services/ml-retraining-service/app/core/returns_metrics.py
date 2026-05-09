"""
Honest skill-on-returns metrics — the truth-tellers complementing
price-level R² and the legacy directional_accuracy.

Background: docs/strategy/research-2026-04-29/V0-FINDINGS-gru-metric-bug.md
established that the production GRU's price-level R² is autocorrelation
noise (a persistence baseline gets the same number) and that the
directional_accuracy metric in services/ml-prediction-service was both
look-ahead-leaked and degenerate (fixed in commit c56765c).

This module provides the pure-numpy/sklearn helper used by the trainer
to record an honest second look at every retrain. Lives in its own
module (not inside model_trainer.py) so unit tests don't have to drag
tensorflow into the test environment.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
from sklearn.metrics import r2_score


def compute_returns_metrics(
    actual_prices: np.ndarray,
    pred_prices: np.ndarray,
    last_close: np.ndarray,
    dataset_name: str,
) -> Dict[str, float]:
    """
    Skill-on-returns metrics — the honest complement to price-level R².

    Args:
        actual_prices: Actual close prices at horizon=1 (shape (N,)).
        pred_prices:   Predicted close prices at horizon=1 (shape (N,)).
        last_close:    Close price of the last bar in each input sequence
                       (shape (N,)) — the reference point both actual and
                       predicted directions are measured against.
        dataset_name:  Prefix for the returned keys (e.g. "train", "test").

    Returns:
        {f"{dataset_name}_r2_returns": float,
         f"{dataset_name}_dir_acc_corrected": float}

    Notes:
        - r2_returns is R² on log-returns (log(price/last_close)). A model
          with no skill on returns gets ~0; price-level R² is irrelevant.
        - dir_acc_corrected uses the input sequence's last bar as the
          reference, NOT a future bar (which was the bug fixed in commit
          c56765c in services/ml-prediction-service). Coin-flip baseline
          is ~0.5; "predict no change" gets near 0 because np.sign(0) = 0
          never matches +/-1.
        - NaN-safe: drops samples where any input is non-positive (log
          would blow up). If all samples are invalid, returns NaN for both.
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
        return {
            f"{dataset_name}_r2_returns": float("nan"),
            f"{dataset_name}_dir_acc_corrected": float("nan"),
        }

    a = actual_prices[valid]
    p = pred_prices[valid]
    lc = last_close[valid]

    actual_log_ret = np.log(a / lc)
    pred_log_ret = np.log(p / lc)
    r2_returns = r2_score(actual_log_ret, pred_log_ret)

    actual_dir = np.sign(a - lc)
    pred_dir = np.sign(p - lc)
    dir_acc_corrected = float(np.mean(actual_dir == pred_dir))

    return {
        f"{dataset_name}_r2_returns": float(r2_returns),
        f"{dataset_name}_dir_acc_corrected": dir_acc_corrected,
    }
