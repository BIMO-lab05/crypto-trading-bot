"""Sliding-window sequence construction for model training.

Mirrors the existing ml-retraining create_sequences logic (model_trainer.py
lines 270-340) but kept local so the runner is self-contained.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
import pandas as pd


def create_sequences(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: List[str],
    sequence_length: int,
    prediction_horizon: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Build sliding windows.

    Args:
        df: DataFrame with all required feature_cols + target_col.
        target_col: 'close' (price mode) or 'log_returns' (returns mode).
        feature_cols: List of column names to use as inputs.
        sequence_length: Lookback length.
        prediction_horizon: How many steps ahead to predict.

    Returns:
        X with shape (n, sequence_length, n_features); y with shape (n, prediction_horizon).
    """
    if target_col not in df.columns:
        raise ValueError(
            f"target_col {target_col!r} not in df columns: {list(df.columns)}"
        )
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"feature_cols missing from df: {missing}")

    features = df[feature_cols].to_numpy(dtype=np.float32)
    target = df[target_col].to_numpy(dtype=np.float32)

    n = len(df) - sequence_length - prediction_horizon + 1
    if n <= 0:
        raise ValueError(
            f"not enough rows: have {len(df)}, need >= {sequence_length + prediction_horizon}"
        )

    X = np.empty((n, sequence_length, features.shape[1]), dtype=np.float32)
    y = np.empty((n, prediction_horizon), dtype=np.float32)
    for i in range(n):
        X[i] = features[i : i + sequence_length]
        y[i] = target[i + sequence_length : i + sequence_length + prediction_horizon]
    return X, y
