"""Unit tests for app.significance.ensemble (Phase 4 plan 04-01 Task 2).

Covers D-01 selection (per-symbol top-N by DSR with tie-break order),
D-02 aggregation (mean of log-returns equal-weighted across members),
and TOURN-07 hygiene (no parallel metric definitions in this module).
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pytest

from app.significance.ensemble import (
    aggregate_log_returns,
    member_descriptor,
    select_top_n_per_symbol,
)


# --- D-01 selection -----------------------------------------------------------


def test_select_top_3_orders_by_dsr_then_cpcv_then_sharpe_then_created_at():
    """Tie-break order: dsr desc, cpcv_dsr desc, oos_sharpe desc, created_at asc."""
    rows = [
        # All four rows have identical dsr=0.9 to force every tie-break level.
        {
            "run_id": "A",
            "symbol": "BTC",
            "status": "success",
            "dsr": 0.9,
            "cpcv_dsr": 0.5,
            "oos_sharpe": 0.5,
            "created_at": "2026-01-04T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
        # Beats A on cpcv_dsr.
        {
            "run_id": "B",
            "symbol": "BTC",
            "status": "success",
            "dsr": 0.9,
            "cpcv_dsr": 0.8,
            "oos_sharpe": 0.1,
            "created_at": "2026-01-03T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
        # Beats A on oos_sharpe (cpcv tied with A).
        {
            "run_id": "C",
            "symbol": "BTC",
            "status": "success",
            "dsr": 0.9,
            "cpcv_dsr": 0.5,
            "oos_sharpe": 0.9,
            "created_at": "2026-01-02T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
        # Tied with A on every metric — earliest created_at wins.
        {
            "run_id": "D",
            "symbol": "BTC",
            "status": "success",
            "dsr": 0.9,
            "cpcv_dsr": 0.5,
            "oos_sharpe": 0.5,
            "created_at": "2026-01-01T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
    ]
    result = select_top_n_per_symbol(rows, n=4)
    order = [r["run_id"] for r in result["BTC"]]
    # Expected: B (highest cpcv) → C (highest sharpe at same cpcv) → D (earliest at full tie) → A
    assert order == ["B", "C", "D", "A"], f"got {order}"


def test_select_top_3_filters_status_success(synthetic_snapshot_dict):
    snap = synthetic_snapshot_dict()
    result = select_top_n_per_symbol(snap["rows"], n=3)
    for sym, members in result.items():
        for m in members:
            # Members must all be original "success" rows; failed rows must not leak in.
            assert m["status"] == "success", f"{sym} contains non-success row: {m}"


def test_select_top_3_returns_per_symbol_groups(synthetic_snapshot_dict):
    """Fixture has 5 symbols × 4 rows (3 success + 1 failed each) → 5 keys, lists len ≤ 3."""
    snap = synthetic_snapshot_dict()
    result = select_top_n_per_symbol(snap["rows"], n=3)
    assert set(result.keys()) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"}
    for sym, members in result.items():
        assert len(members) == 3, f"{sym}: expected 3 members, got {len(members)}"


def test_select_top_3_insufficient_runs():
    """CD-08: symbols with <3 successful rows return their available members; caller decides."""
    rows = [
        {
            "run_id": "x",
            "symbol": "RARE",
            "status": "success",
            "dsr": 0.5,
            "cpcv_dsr": 0.0,
            "oos_sharpe": 0.0,
            "created_at": "2026-01-01T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
        {
            "run_id": "y",
            "symbol": "RARE",
            "status": "failed",
            "dsr": None,
            "cpcv_dsr": None,
            "oos_sharpe": None,
            "created_at": "2026-01-02T00:00:00Z",
            "architecture": "gru",
            "hp_hash": "h",
        },
    ]
    result = select_top_n_per_symbol(rows, n=3)
    assert "RARE" in result
    assert len(result["RARE"]) == 1
    assert result["RARE"][0]["run_id"] == "x"


# --- D-02 aggregation ---------------------------------------------------------


def test_aggregate_log_returns_mean_equal_weighted():
    """Hand-computed mean across 3 members per timestep."""
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([2.0, 4.0, 6.0, 8.0])
    c = np.array([3.0, 6.0, 9.0, 12.0])
    result = aggregate_log_returns([a, b, c])
    expected = np.array([2.0, 4.0, 6.0, 8.0])
    np.testing.assert_allclose(result, expected, rtol=1e-12)


def test_aggregate_log_returns_rejects_unequal_lengths():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([1.0, 2.0])  # mismatched
    with pytest.raises(ValueError, match="shape"):
        aggregate_log_returns([a, b])


def test_aggregate_log_returns_empty_input():
    with pytest.raises(ValueError, match="at least one"):
        aggregate_log_returns([])


# --- TOURN-07 hygiene ---------------------------------------------------------


def test_no_parallel_metric_definitions_in_module():
    """Per TOURN-07 — ensemble.py must NOT redefine sharpe/dir-acc/dsr/returns metrics."""
    src_path = (
        Path(__file__).resolve().parents[2] / "app" / "significance" / "ensemble.py"
    )
    text = src_path.read_text()
    forbidden = re.compile(
        r"^\s*def\s+("
        r"directional_accuracy|sharpe|deflated|compute_returns_metrics"
        r")\b",
        re.MULTILINE,
    )
    matches = forbidden.findall(text)
    assert matches == [], f"forbidden metric definitions found: {matches}"


# --- Helper -------------------------------------------------------------------


def test_member_descriptor_strips_to_d03_fields():
    row = {
        "run_id": "r1",
        "symbol": "BTC",
        "architecture": "gru",
        "hp_hash": "h1",
        "dsr": 0.85,
        "cpcv_dsr": 0.7,
        "oos_sharpe": 0.9,
        "status": "success",
        "result_json": {"large": "blob"},
    }
    desc = member_descriptor(row)
    # D-03 — exactly these four keys (the artifact contract).
    assert set(desc.keys()) == {"run_id", "architecture", "hp_hash", "dsr"}
    assert desc["run_id"] == "r1"
    assert desc["dsr"] == 0.85
    # `result_json` and other fat fields are stripped (config-by-reference).
    assert "result_json" not in desc
