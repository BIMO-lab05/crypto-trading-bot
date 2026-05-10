"""Unit tests for metrics_bridge.dir_acc_corrected_from_log_returns (B5/D-02).

This is the canonical log-return-input chance-corrected directional accuracy.
Persistence baseline (all-zero pred_lr) returns -1.0 by construction — see
docstring + test_dir_acc_corrected_persistence_baseline_is_zero below.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.runner.metrics_bridge import dir_acc_corrected_from_log_returns


def test_dir_acc_corrected_from_log_returns_perfect():
    """pred_lr == actual_lr → all signs match → returns 1.0."""
    actual = np.array([0.01, -0.02, 0.005, -0.01, 0.02])
    pred = actual.copy()
    assert dir_acc_corrected_from_log_returns(actual, pred) == pytest.approx(1.0)


def test_dir_acc_corrected_from_log_returns_inverse():
    """pred_lr == -actual_lr → all signs opposite → returns -1.0."""
    actual = np.array([0.01, -0.02, 0.005, -0.01, 0.02])
    pred = -actual
    assert dir_acc_corrected_from_log_returns(actual, pred) == pytest.approx(-1.0)


def test_dir_acc_corrected_from_log_returns_chance():
    """Random predictions with ~50% sign-agreement → ≈0.0 within ±0.05 over n=10000."""
    rng = np.random.default_rng(42)
    actual = rng.standard_normal(10_000)
    pred = rng.standard_normal(10_000)
    val = dir_acc_corrected_from_log_returns(actual, pred)
    assert abs(val) < 0.05, f"chance baseline drifted: {val}"


def test_dir_acc_corrected_persistence_baseline_is_zero():
    """Persistence baseline (pred_lr all zeros) returns -1.0 by construction.

    np.sign(0) is 0 and never agrees with non-zero actual signs → mean(agree) is 0
    → 2*(0 - 0.5) = -1.0. This is the INTENTIONAL chance baseline — persistence
    has no directional skill on log-returns by construction. The ensemble's lift
    over this floor is exactly what the bootstrap test measures.
    """
    actual = np.array([0.01, -0.02, 0.005, -0.01, 0.02])
    pred = np.zeros_like(actual)
    assert dir_acc_corrected_from_log_returns(actual, pred) == pytest.approx(-1.0)


def test_dir_acc_corrected_shape_mismatch_raises():
    actual = np.array([0.01, -0.02, 0.005])  # shape (3,)
    pred = np.array([0.01, -0.02, 0.005, 0.0])  # shape (4,)
    with pytest.raises(ValueError):
        dir_acc_corrected_from_log_returns(actual, pred)
