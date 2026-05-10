"""Tests for app.significance.baseline.persistence_log_returns (D-04)."""

from __future__ import annotations

import numpy as np

from app.significance.baseline import persistence_log_returns


def test_persistence_returns_zeros_of_correct_length() -> None:
    """D-04: persistence baseline → log-return = 0 per bar."""
    out = persistence_log_returns(50)
    assert isinstance(out, np.ndarray)
    assert out.shape == (50,)
    assert out.dtype == np.float64
    assert np.all(out == 0.0)


def test_persistence_zero_length() -> None:
    """Edge case: zero bars must return shape (0,) without raising."""
    out = persistence_log_returns(0)
    assert out.shape == (0,)
    assert out.dtype == np.float64


def test_persistence_accepts_int_like() -> None:
    """Plan signature is `int`; defensively accept numpy int scalar via cast."""
    out = persistence_log_returns(np.int64(10))
    assert out.shape == (10,)
