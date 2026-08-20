"""Fixtures for edge_lab tests. Shared constants/helpers live in el_shared
(unique basename — a second top-level `conftest` module in tests/killtests
collides under pytest prepend import mode; see 2026-08-20 wait-window plan)."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from el_shared import DAY, T0, make_daily, assert_shift_invariant  # noqa: E402,F401


@pytest.fixture
def universe12():
    syms = [f"S{i:02d}USDT" for i in range(12)]
    drifts = {s: 0.004 if i < 3 else (-0.004 if i >= 9 else 0.0) for i, s in enumerate(syms)}
    return make_daily(syms, drifts=drifts)
