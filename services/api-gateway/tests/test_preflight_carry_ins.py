"""Behavioral tests for GET /api/preflight/carry-ins (Phase 10, DASHLIVE-02).

Gap coverage:
  a. D-10-04 response shape: 7 required keys present in every response
  b. D-10-07 reset rule: first_all_pass_at set on first all-PASS, cleared on any not-PASS
  c. D-10-08: UNKNOWN check counts as not-PASS → overall=DO_NOT_FLIP
  d. D-10-11 graceful degradation: proxy raises → 200 with overall=DO_NOT_FLIP
  e. File-read failure fallback: missing state file → handler still returns 200
  f. Atomic write: _atomic_write_json uses tempfile+os.replace, no tmp file left on success

Run inside container:
    docker exec crypto-bot-api-gateway pytest tests/test_preflight_carry_ins.py -v
"""

import json

import pytest
from fastapi.responses import JSONResponse
from unittest.mock import patch, AsyncMock, Mock

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIX_PASS_CHECKS = [
    {"check": name, "status": "PASS", "detail": "ok"}
    for name in (
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    )
]

_SIX_FAIL_CHECKS = [
    {"check": name, "status": "FAIL", "detail": "bad"}
    for name in (
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    )
]

_SIX_UNKNOWN_CHECKS = [
    {"check": name, "status": "UNKNOWN", "detail": "trading-engine unreachable"}
    for name in (
        "cap",
        "paper_mode",
        "trading_mode",
        "ack",
        "emergency_stop",
        "dsr_evidence",
    )
]


def _build_response(content, status_code: int = 200) -> JSONResponse:
    """Mirror test_preflight_proxy._build_response — proxy_request returns JSONResponse
    with a populated .body attribute; handler decodes via json.loads(resp.body.decode())."""
    r = JSONResponse(content=content, status_code=status_code)
    r.body = json.dumps(content).encode()
    return r


def _live_readiness_payload(checks):
    return {
        "schema_version": 1,
        "overall": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
        "evaluated_at": "2026-01-01T00:00:00+00:00",
        "checks": checks,
    }


def _make_mock_proxy(checks):
    """Return a mock service proxy whose proxy_request returns the given checks."""
    proxy = Mock()
    async_mock = AsyncMock(
        return_value=_build_response(_live_readiness_payload(checks))
    )
    proxy.proxy_request = async_mock
    return proxy


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """Redirect state file to a tmp dir so tests don't touch /app/planning_state."""
    state_path = tmp_path / "carry_ins.json"
    monkeypatch.setenv("PREFLIGHT_CARRY_INS_PATH", str(state_path))
    return state_path


@pytest.fixture
def test_client():
    from app.main import app
    from fastapi.testclient import TestClient

    return TestClient(app)


# ---------------------------------------------------------------------------
# Gap a — D-10-04 response shape
# ---------------------------------------------------------------------------


def test_response_has_all_required_keys(test_client, isolated_state_dir):
    """D-10-04: every response includes all 7 required top-level keys."""
    mock_proxy = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        resp = test_client.get("/api/preflight/carry-ins")

    assert resp.status_code == 200
    body = resp.json()
    required_keys = {
        "schema_version",
        "evaluated_at",
        "overall",
        "carry_ins",
        "window",
        "preflight_summary",
        "live_readiness",
    }
    missing = required_keys - set(body.keys())
    assert not missing, f"Response missing required D-10-04 keys: {missing}"


def test_window_subkeys_present(test_client, isolated_state_dir):
    """D-10-04: window block has expected 4 sub-keys."""
    mock_proxy = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    window = body["window"]
    required = {
        "first_all_pass_at",
        "elapsed_seconds",
        "required_seconds",
        "remaining_seconds",
    }
    missing = required - set(window.keys())
    assert not missing, f"window block missing keys: {missing}"


def test_preflight_summary_subkeys_present(test_client, isolated_state_dir):
    """D-10-04: preflight_summary has pass/fail/unknown count keys."""
    mock_proxy = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    summary = body["preflight_summary"]
    required = {"pass", "fail", "unknown"}
    missing = required - set(summary.keys())
    assert not missing, f"preflight_summary missing keys: {missing}"


# ---------------------------------------------------------------------------
# Gap c — D-10-08: UNKNOWN counts as not-PASS
# ---------------------------------------------------------------------------


def test_unknown_check_produces_do_not_flip(test_client, isolated_state_dir):
    """D-10-08: if any check is UNKNOWN, overall must be DO_NOT_FLIP (not ALMOST/READY)."""
    mock_proxy = _make_mock_proxy(_SIX_UNKNOWN_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    assert body["overall"] == "DO_NOT_FLIP", (
        f"Expected DO_NOT_FLIP when checks UNKNOWN, got {body['overall']!r}"
    )


def test_mixed_pass_unknown_produces_do_not_flip(test_client, isolated_state_dir):
    """D-10-08: 5 PASS + 1 UNKNOWN must NOT be overall=ALMOST or READY."""
    mixed_checks = _SIX_PASS_CHECKS[:5] + [
        {"check": "dsr_evidence", "status": "UNKNOWN", "detail": "unreachable"}
    ]
    mock_proxy = _make_mock_proxy(mixed_checks)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    assert body["overall"] == "DO_NOT_FLIP", (
        f"5 PASS + 1 UNKNOWN should be DO_NOT_FLIP, got {body['overall']!r}"
    )


# ---------------------------------------------------------------------------
# Gap d — D-10-11: proxy failure → graceful degradation
# ---------------------------------------------------------------------------


def test_proxy_raises_returns_200_do_not_flip(test_client, isolated_state_dir):
    """D-10-11: trading-engine proxy raises → handler returns 200, overall=DO_NOT_FLIP."""
    failing_proxy = Mock()
    failing_proxy.proxy_request = AsyncMock(side_effect=Exception("connection refused"))
    with patch("app.main.get_proxy", return_value=failing_proxy):
        resp = test_client.get("/api/preflight/carry-ins")

    assert resp.status_code == 200
    body = resp.json()
    assert body["overall"] == "DO_NOT_FLIP", (
        f"Proxy failure must produce DO_NOT_FLIP, got {body['overall']!r}"
    )


def test_proxy_raises_checks_surface_as_unknown(test_client, isolated_state_dir):
    """D-10-11: when proxy raises, live_readiness checks are all UNKNOWN (not PASS)."""
    failing_proxy = Mock()
    failing_proxy.proxy_request = AsyncMock(side_effect=Exception("timeout"))
    with patch("app.main.get_proxy", return_value=failing_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    checks = body["live_readiness"]["checks"]
    assert len(checks) == 6, f"Expected 6 degraded checks, got {len(checks)}"
    non_unknown = [c for c in checks if c["status"] != "UNKNOWN"]
    assert not non_unknown, f"Degraded checks must all be UNKNOWN; found: {non_unknown}"


def test_proxy_non_200_returns_do_not_flip(test_client, isolated_state_dir):
    """D-10-11: proxy returns non-200 status → overall=DO_NOT_FLIP."""
    proxy_504 = Mock()
    proxy_504.proxy_request = AsyncMock(
        return_value=_build_response({"error": "bad gateway"}, status_code=504)
    )
    with patch("app.main.get_proxy", return_value=proxy_504):
        body = test_client.get("/api/preflight/carry-ins").json()

    assert body["overall"] == "DO_NOT_FLIP"


# ---------------------------------------------------------------------------
# Gap e — File-read failure fallback
# ---------------------------------------------------------------------------


def test_missing_state_file_still_returns_200(test_client, isolated_state_dir):
    """Handler must not raise when state file is absent — returns 200 with empty carry_ins."""
    # isolated_state_dir points to a file that doesn't exist yet
    assert not isolated_state_dir.exists(), "Precondition: state file must not exist"
    mock_proxy = _make_mock_proxy(_SIX_FAIL_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        resp = test_client.get("/api/preflight/carry-ins")

    assert resp.status_code == 200
    body = resp.json()
    assert body["carry_ins"] == [], (
        f"Missing file should produce empty carry_ins, got {body['carry_ins']}"
    )


def test_malformed_state_file_still_returns_200(
    test_client, isolated_state_dir, tmp_path
):
    """Handler must not raise on malformed JSON state file."""
    isolated_state_dir.write_text("not-json!!!", encoding="utf-8")
    mock_proxy = _make_mock_proxy(_SIX_FAIL_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        resp = test_client.get("/api/preflight/carry-ins")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Gap b — D-10-07 reset rule (two-call sequence)
# ---------------------------------------------------------------------------


def test_d1007_first_all_pass_sets_timer(test_client, isolated_state_dir):
    """D-10-07: first poll where all 6 PASS must set first_all_pass_at (non-null)."""
    mock_proxy = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body = test_client.get("/api/preflight/carry-ins").json()

    assert body["window"]["first_all_pass_at"] is not None, (
        "first_all_pass_at must be set after first all-PASS poll"
    )
    assert body["window"]["elapsed_seconds"] >= 0


def test_d1007_not_pass_clears_timer(test_client, isolated_state_dir):
    """D-10-07: after all-PASS poll, a subsequent not-PASS poll must clear first_all_pass_at."""
    # Call 1: all PASS — sets the timer
    mock_proxy_pass = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy_pass):
        body1 = test_client.get("/api/preflight/carry-ins").json()

    assert body1["window"]["first_all_pass_at"] is not None, (
        "Precondition: first_all_pass_at must be set after first PASS poll"
    )

    # Call 2: one FAIL — must clear the timer
    fail_checks = _SIX_PASS_CHECKS[:5] + [
        {"check": "dsr_evidence", "status": "FAIL", "detail": "failed"}
    ]
    mock_proxy_fail = _make_mock_proxy(fail_checks)
    with patch("app.main.get_proxy", return_value=mock_proxy_fail):
        body2 = test_client.get("/api/preflight/carry-ins").json()

    assert body2["window"]["first_all_pass_at"] is None, (
        f"D-10-07: first_all_pass_at must be cleared after any not-PASS poll; got {body2['window']['first_all_pass_at']!r}"
    )
    assert body2["overall"] == "DO_NOT_FLIP"


def test_d1007_second_all_pass_preserves_timer(test_client, isolated_state_dir):
    """D-10-07: consecutive all-PASS polls must NOT reset first_all_pass_at (monotone)."""
    mock_proxy = _make_mock_proxy(_SIX_PASS_CHECKS)
    with patch("app.main.get_proxy", return_value=mock_proxy):
        body1 = test_client.get("/api/preflight/carry-ins").json()
    first_ts = body1["window"]["first_all_pass_at"]
    assert first_ts is not None

    with patch("app.main.get_proxy", return_value=mock_proxy):
        body2 = test_client.get("/api/preflight/carry-ins").json()
    second_ts = body2["window"]["first_all_pass_at"]

    assert second_ts == first_ts, (
        f"D-10-07: consecutive PASS polls must not reset the timer; first={first_ts!r}, second={second_ts!r}"
    )


# ---------------------------------------------------------------------------
# Gap f — Atomic write: tmp file cleaned up on success
# ---------------------------------------------------------------------------


def test_atomic_write_leaves_no_tmp_files(tmp_path):
    """_atomic_write_json must not leave .tmp files in the directory after success."""
    from app.routes.preflight_carry_ins import _atomic_write_json

    target = tmp_path / "state.json"
    payload = {"schema_version": 1, "carry_ins": [], "_state": {}}
    _atomic_write_json(target, payload)

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert not tmp_files, f"_atomic_write_json left tmp files: {tmp_files}"
    assert target.exists(), "Target file must exist after atomic write"
    written = json.loads(target.read_text())
    assert written == payload


def test_atomic_write_result_is_valid_json(tmp_path):
    """_atomic_write_json output must be valid JSON matching the input payload."""
    from app.routes.preflight_carry_ins import _atomic_write_json

    target = tmp_path / "state.json"
    payload = {
        "schema_version": 1,
        "carry_ins": [{"id": "OP-01", "state": "open"}],
        "_state": {"first_all_pass_at": None},
    }
    _atomic_write_json(target, payload)
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload


def test_atomic_write_cleans_up_tmp_on_exception(tmp_path, monkeypatch):
    """_atomic_write_json exception path: tmp file must be unlinked, target not created.

    Load-bearing safety property (Gap f): on any failure after mkstemp,
    the except-block calls os.unlink(tmp_name) then re-raises. Without this,
    a failed write leaves a .tmp file in the state directory (torn write).
    """
    import app.routes.preflight_carry_ins as mod
    from app.routes.preflight_carry_ins import _atomic_write_json

    def boom(src, dst):
        raise RuntimeError("simulated os.replace failure")

    monkeypatch.setattr(mod.os, "replace", boom)

    target = tmp_path / "state.json"
    with pytest.raises(RuntimeError, match="simulated os.replace failure"):
        _atomic_write_json(target, {"x": 1})

    # Target must not have been created
    assert not target.exists(), "Target file must not exist after failed atomic write"
    # No .tmp leftovers — exception cleanup ran
    tmp_leftovers = list(tmp_path.glob("*.tmp"))
    assert not tmp_leftovers, f"Exception path leaked tmp files: {tmp_leftovers}"
