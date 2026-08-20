"""
Tests for the api-gateway GET /api/tournament/snapshots[/<id>] routes
(Phase 7, DASH-04 / Plan 07-01).

Covers (one function per case):
- Empty snapshots directory       -> 200 {success:True, count:0, tournaments:[]}
- List passes summary block       -> n_rows / n_success / n_failed / arch / symbols
- List skips Phase 4 sidecars     -> *.ensemble.json / *.significance.json excluded
- List skips corrupt files        -> bad JSON logged + skipped, 200 with healthy rows
- Detail returns 404              -> when snapshot file absent
- Detail rejects path traversal   -> regex blocks ../, foo.bar, etc; 400
- Detail rejects oversized files  -> >50 MiB returns 500 (file body never read)
- Detail returns null sidecars    -> D-05: ensemble/significance None when absent
- Detail merges three files       -> snapshot + ensemble + significance present

Filesystem strategy: uses pytest's `tmp_path` fixture + monkeypatch of the
module-level constant `app.main._TOURNAMENT_SNAPSHOTS_DIR` (the route reads
files through this seam in production; tests swap it for a tmp dir). Real
filesystem I/O via pathlib.Path.write_text — we DELIBERATELY do not mock
the builtin open() because pathlib.Path.read_text goes through _io.open
(C-level), bypassing builtin-level mocks silently. See project memory
feedback_pathlib_mocking.md.

Tests MUST run inside the api-gateway container (CLAUDE.md gotcha — host
fastapi 0.136 returns 401 from HTTPBearer auto_error, container fastapi
0.109 returns 403; this route is unauthenticated so the discrepancy does
not bite, but the in-container rule is uniform — mirrors test_safety_state
.py:17-21).

Container invocation:
    docker exec crypto-bot-api-gateway pytest /app/tests/test_tournament_snapshots.py -v
"""

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_snapshot(directory: Path, tournament_id: str, *, summary=None, extra=None):
    """Write a snapshot JSON file mirroring export_snapshot() shape."""
    payload = {
        "tournament_id": tournament_id,
        "exported_at": "2026-05-14T10:00:00+00:00",
        "schema_version": 1,
        "config": {"placeholder": True},
        "rows": [],
        "summary": summary
        or {
            "n_rows": 0,
            "n_success": 0,
            "n_failed": 0,
            "architectures": [],
            "symbols": [],
        },
    }
    if extra:
        payload.update(extra)
    (directory / f"{tournament_id}.json").write_text(json.dumps(payload))
    return payload


def _seed_snapshot_dir(monkeypatch, tmp_path: Path) -> Path:
    """Repoint app.main._TOURNAMENT_SNAPSHOTS_DIR at tmp_path."""
    monkeypatch.setattr("app.main._TOURNAMENT_SNAPSHOTS_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# List endpoint tests
# ---------------------------------------------------------------------------


def test_list_returns_empty_when_snapshots_directory_absent(
    test_client, tmp_path, monkeypatch
):
    """D-06: missing snapshots dir -> 200 with empty list (NEVER 500).

    We point the snapshots-dir constant at a child path that does NOT
    exist on disk; route's `if not snapshots_dir.exists()` short-circuits
    to the graceful-degradation branch.
    """
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr("app.main._TOURNAMENT_SNAPSHOTS_DIR", missing)

    resp = test_client.get("/api/tournament/snapshots")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"success": True, "count": 0, "tournaments": []}


def test_list_returns_summary_block_per_snapshot_file(
    test_client, tmp_path, monkeypatch
):
    """List endpoint surfaces each snapshot's summary block + tournament_id
    + exported_at (D-01 contract)."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)

    _write_snapshot(
        d,
        "t1",
        summary={
            "n_rows": 4,
            "n_success": 3,
            "n_failed": 1,
            "architectures": ["GRU"],
            "symbols": ["BTC", "ETH"],
        },
    )
    _write_snapshot(
        d,
        "t2",
        summary={
            "n_rows": 2,
            "n_success": 2,
            "n_failed": 0,
            "architectures": ["LSTM", "GRU"],
            "symbols": ["SOL"],
        },
    )

    resp = test_client.get("/api/tournament/snapshots")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["count"] == 2
    ids = {t["tournament_id"] for t in body["tournaments"]}
    assert ids == {"t1", "t2"}

    t1 = next(t for t in body["tournaments"] if t["tournament_id"] == "t1")
    assert t1["n_rows"] == 4
    assert t1["n_success"] == 3
    assert t1["n_failed"] == 1
    assert t1["architectures"] == ["GRU"]
    assert t1["symbols"] == ["BTC", "ETH"]
    assert t1["exported_at"] == "2026-05-14T10:00:00+00:00"


def test_list_skips_ensemble_and_significance_sidecars(
    test_client, tmp_path, monkeypatch
):
    """Phase 4 sidecars (*.ensemble.json, *.significance.json) MUST NOT
    appear in the list output."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)
    _write_snapshot(d, "t1")
    # Sidecars with bare summary-less payload — they should be skipped
    # before any decode happens (filename rule).
    (d / "t1.ensemble.json").write_text(json.dumps({"ensembles": []}))
    (d / "t1.significance.json").write_text(json.dumps({"per_symbol": {}}))

    resp = test_client.get("/api/tournament/snapshots")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["tournaments"][0]["tournament_id"] == "t1"


def test_list_skips_corrupt_files_without_500(test_client, tmp_path, monkeypatch):
    """A malformed JSON file MUST be logged + skipped; the rest of the
    listing remains healthy (T-07-05 graceful degradation)."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)
    _write_snapshot(d, "good")
    (d / "bad.json").write_text("not json {")  # malformed

    resp = test_client.get("/api/tournament/snapshots")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["tournaments"][0]["tournament_id"] == "good"


# ---------------------------------------------------------------------------
# Detail endpoint tests
# ---------------------------------------------------------------------------


def test_detail_returns_404_when_snapshot_absent(test_client, tmp_path, monkeypatch):
    """Detail endpoint: 404 with detail body containing the requested id."""
    _seed_snapshot_dir(monkeypatch, tmp_path)
    resp = test_client.get("/api/tournament/snapshots/missing-id")
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert "snapshot missing-id not found" in body["detail"]


def test_detail_returns_400_on_path_traversal_attempt(
    test_client, tmp_path, monkeypatch
):
    """Regex `^[A-Za-z0-9_\\-]+$` rejects `.`, `/`, `\\`, `..`, URL-encoded
    variants. Both unencoded `../etc/passwd` and the URL-encoded form must
    be rejected, and so must any id containing a literal `.` (e.g.
    `foo.bar`).
    """
    _seed_snapshot_dir(monkeypatch, tmp_path)

    # `..` segment — FastAPI normalizes the path; `..` is part of the
    # path segment so the route may not even fire. Both unencoded and
    # url-encoded forms should fail (status_code != 200).
    resp_unencoded = test_client.get(
        "/api/tournament/snapshots/../etc/passwd", follow_redirects=False
    )
    assert resp_unencoded.status_code in {400, 404}, resp_unencoded.text

    resp_encoded = test_client.get(
        "/api/tournament/snapshots/..%2Fetc%2Fpasswd", follow_redirects=False
    )
    # %2F decoded to / — FastAPI treats this as a non-matching path or
    # the regex blocks it. Either way: NOT 200.
    assert resp_encoded.status_code in {400, 404}, resp_encoded.text

    # `.` segment — regex MUST reject "foo.bar" (contains a dot).
    resp_dot = test_client.get("/api/tournament/snapshots/foo.bar")
    assert resp_dot.status_code == 400, resp_dot.text
    assert "invalid tournament_id" in resp_dot.json()["detail"]

    # Trailing `/` and slash-injection inside the id are blocked by the
    # regex too.
    resp_slash = test_client.get("/api/tournament/snapshots/foo%2Fbar")
    assert resp_slash.status_code in {400, 404}, resp_slash.text


def test_detail_returns_500_when_file_exceeds_50mb(test_client, tmp_path, monkeypatch):
    """File-size guardrail (T-07-04): stat()-based check fires BEFORE the
    file body is read. We monkeypatch pathlib.Path.stat for the specific
    file path so we don't actually need to write 50 MiB to disk."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)
    _write_snapshot(d, "huge")

    target = d / "huge.json"
    # Replace Path.stat so it reports a giant size for THIS file only,
    # delegating to the original stat() for everything else.
    import pathlib

    original_stat = pathlib.Path.stat

    class _BigStat:
        def __init__(self, real):
            self._real = real
            self.st_size = 50 * 1024 * 1024 + 1

        def __getattr__(self, name):
            return getattr(self._real, name)

    # Resolve the target ONCE, before the patch is installed. On Python 3.12
    # `Path.resolve()` itself calls `Path.stat()`, so resolving inside
    # `fake_stat` re-enters the patched stat and recurses until the stack
    # blows (RecursionError). Precomputing keeps the comparison cheap and
    # keeps `fake_stat` free of any call that can re-enter stat().
    target_resolved = target.resolve()

    def fake_stat(self, *args, **kwargs):  # type: ignore[override]
        real = original_stat(self, *args, **kwargs)
        if self == target_resolved or self == target:
            return _BigStat(real)
        return real

    monkeypatch.setattr(pathlib.Path, "stat", fake_stat)

    resp = test_client.get("/api/tournament/snapshots/huge")
    assert resp.status_code == 500, resp.text
    assert "snapshot file too large" in resp.json()["detail"]


def test_detail_returns_null_sidecars_when_absent_d05(
    test_client, tmp_path, monkeypatch
):
    """D-05: when no ensemble/significance sidecars are on disk, the
    detail response MUST return them as null (NOT missing keys, NOT
    error). The snapshot block is always populated."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)
    _write_snapshot(d, "t1")

    resp = test_client.get("/api/tournament/snapshots/t1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["snapshot"]["tournament_id"] == "t1"
    assert body["ensemble"] is None
    assert body["significance"] is None


def test_detail_merges_all_three_files_when_present(test_client, tmp_path, monkeypatch):
    """When ensemble.json and significance.json sidecars are present
    next to the snapshot, the response merges all three into one body
    (D-03)."""
    d = _seed_snapshot_dir(monkeypatch, tmp_path)
    _write_snapshot(d, "t1", extra={"marker": "snapshot"})
    (d / "t1.ensemble.json").write_text(json.dumps({"marker": "ensemble"}))
    (d / "t1.significance.json").write_text(json.dumps({"marker": "significance"}))

    resp = test_client.get("/api/tournament/snapshots/t1")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["snapshot"]["marker"] == "snapshot"
    assert body["ensemble"]["marker"] == "ensemble"
    assert body["significance"]["marker"] == "significance"
