"""Persistence baseline for the Phase 4 significance test (D-04).

D-04 — predict next-bar close = current close → log-return = 0 per bar.
This file is intentionally a one-liner-with-docstring: the design choice
is to keep the call site stable so a Phase-5 production-aggregator
baseline can swap in without changing `bootstrap.py` consumers. The
`baseline: "persistence"` string in `significance.json` (D-14) carries
the identity downstream.

TOURN-07: no metric helpers (sharpe / dir_acc / dsr / compute_returns_metrics)
are defined in this module — by inspection, baseline only emits a zeros
array; the grep gate test catches any future drift.
"""

from __future__ import annotations

import numpy as np


def persistence_log_returns(n_oos_bars: int) -> np.ndarray:
    """Return a zeros array of shape ``(n_oos_bars,)``, dtype ``float64``.

    A persistence forecast says "tomorrow's close = today's close", so the
    predicted log-return is ``log(close / close) = 0`` for every OOS bar.
    Kept as a function (not a constant) to preserve the call site for a
    future production-aggregator baseline (Phase 5 follow-up).

    Parameters
    ----------
    n_oos_bars
        Number of out-of-sample bars to emit a baseline log-return for.
        Must be a non-negative integer or integer-like; cast via ``int(...)``
        defensively to accept ``np.int64`` / numpy scalar callers.

    Returns
    -------
    np.ndarray
        Shape ``(n_oos_bars,)``, dtype ``float64``, every element ``0.0``.
    """
    return np.zeros(int(n_oos_bars), dtype=float)


__all__ = ["persistence_log_returns"]
