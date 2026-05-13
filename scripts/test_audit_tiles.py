"""
Tests for scripts/audit_tiles.py (Phase 6, DASH-01).

Covers the five behaviors required by 06-01-PLAN.md Task 2:

1. All FIXED tiles return 200 + matching shape -> exit 0.
2. Any FIXED tile returns 503 -> exit 1 + FAIL line for that tile.
3. LABELED_STALE rows are skipped (not probed).
4. _shape_matches accepts empty list for list[*] expected types.
5. Missing inventory file -> exit 2 with a clear error (no Python traceback).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from scripts import audit_tiles


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_inventory(tmp_path: Path, tiles: list[dict]) -> Path:
    """Write a minimal audit_tiles inventory JSON to tmp_path."""
    path = tmp_path / "inventory.json"
    payload = {
        "generated_at": "2026-05-13T20:43:20Z",
        "tiles": tiles,
    }
    path.write_text(json.dumps(payload))
    return path


def _make_response(status_code: int, payload):
    """Build a mocked requests.Response-like object."""
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.json = mock.MagicMock(return_value=payload)
    return resp


# ---------------------------------------------------------------------------
# Behavior tests
# ---------------------------------------------------------------------------


def test_all_fixed_tiles_pass_returns_zero(tmp_path, capsys):
    """Test 1: two FIXED tiles, both 200 with matching shape -> exit 0."""
    tiles = [
        {
            "tile": "AAA",
            "endpoint": "/api/trading/performance",
            "expected_shape": {"success": "bool", "metrics": "object"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
        {
            "tile": "BBB",
            "endpoint": "/api/trading/status",
            "expected_shape": {"success": "bool", "status": "object"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
    ]
    inv = _write_inventory(tmp_path, tiles)

    def fake_get(url, timeout):
        if "performance" in url:
            return _make_response(200, {"success": True, "metrics": {}})
        return _make_response(200, {"success": True, "status": {}})

    with mock.patch.object(audit_tiles.requests, "get", side_effect=fake_get):
        with pytest.raises(SystemExit) as exc:
            audit_tiles.main(["--against", "http://stub-host", "--inventory", str(inv)])
    assert exc.value.code == 0


def test_one_fixed_tile_returns_503_exits_one(tmp_path, capsys):
    """Test 2: one tile returns 503 -> exit 1 + FAIL line for that tile."""
    tiles = [
        {
            "tile": "GOOD",
            "endpoint": "/api/trading/performance",
            "expected_shape": {"success": "bool"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
        {
            "tile": "BROKEN",
            "endpoint": "/api/portfolio",
            "expected_shape": {"balance": "number"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
    ]
    inv = _write_inventory(tmp_path, tiles)

    def fake_get(url, timeout):
        if "performance" in url:
            return _make_response(200, {"success": True})
        return _make_response(503, {"detail": "service unavailable"})

    with mock.patch.object(audit_tiles.requests, "get", side_effect=fake_get):
        with pytest.raises(SystemExit) as exc:
            audit_tiles.main(["--against", "http://stub-host", "--inventory", str(inv)])
    assert exc.value.code == 1
    captured = capsys.readouterr().out
    assert "FAIL" in captured
    assert "BROKEN" in captured


def test_labeled_stale_row_skipped(tmp_path, capsys):
    """Test 3: LABELED_STALE row not probed; only FIXED rows counted."""
    tiles = [
        {
            "tile": "ALIVE",
            "endpoint": "/api/trading/performance",
            "expected_shape": {"success": "bool"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
        {
            "tile": "PHASE3",
            "endpoint": "/api/ml/predict/price/BTCUSDT",
            "expected_shape": {"prediction": "object"},
            "verdict": "LABELED_STALE",
            "last_updated_at_emitter": "n/a",
        },
        {
            "tile": "DEAD",
            "endpoint": "/api/market/orderbook/BTCUSDT",
            "expected_shape": {"bids": "list[object]"},
            "verdict": "REMOVED",
            "last_updated_at_emitter": "n/a",
        },
        {
            "tile": "ASK_OPERATOR",
            "endpoint": "/api/portfolio",
            "expected_shape": {"balance": "number"},
            "verdict": "PENDING-OPERATOR",
            "last_updated_at_emitter": "n/a",
        },
    ]
    inv = _write_inventory(tmp_path, tiles)

    calls: list[str] = []

    def fake_get(url, timeout):
        calls.append(url)
        return _make_response(200, {"success": True})

    with mock.patch.object(audit_tiles.requests, "get", side_effect=fake_get):
        with pytest.raises(SystemExit) as exc:
            audit_tiles.main(["--against", "http://stub-host", "--inventory", str(inv)])
    assert exc.value.code == 0
    # Only the FIXED row should have been probed
    assert len(calls) == 1
    assert "performance" in calls[0]
    captured = capsys.readouterr().out
    assert "1/1 tiles PASS" in captured
    # LABELED_STALE / REMOVED / PENDING-OPERATOR tiles must NOT appear in output
    assert "PHASE3" not in captured
    assert "DEAD" not in captured
    assert "ASK_OPERATOR" not in captured


def test_shape_matches_accepts_empty_list_for_list_type(tmp_path, capsys):
    """Test 4: expected list[object] is satisfied by empty list payload."""
    tiles = [
        {
            "tile": "POSITIONS",
            "endpoint": "/api/trading/positions",
            "expected_shape": {"positions": "list[object]"},
            "verdict": "FIXED",
            "last_updated_at_emitter": "no",
        },
    ]
    inv = _write_inventory(tmp_path, tiles)

    def fake_get(url, timeout):
        return _make_response(200, {"positions": []})

    with mock.patch.object(audit_tiles.requests, "get", side_effect=fake_get):
        with pytest.raises(SystemExit) as exc:
            audit_tiles.main(["--against", "http://stub-host", "--inventory", str(inv)])
    assert exc.value.code == 0


def test_missing_inventory_file_exits_two(tmp_path, capsys):
    """Test 5: --inventory pointing at a missing file -> exit 2, no traceback."""
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(SystemExit) as exc:
        audit_tiles.main(["--against", "http://stub-host", "--inventory", str(missing)])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback" not in combined
    # Should mention the missing path or "inventory" in the error message
    assert "inventory" in combined.lower() or str(missing) in combined
