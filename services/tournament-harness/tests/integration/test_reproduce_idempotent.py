"""D-12: reproduce round-trip must produce identical significance within FP-noise tolerance.

This test is the load-bearing CI proof for reproducibility. If it fails, the harness
is no longer reproducible and the operator must investigate before opening any PR.

Environment: this test exercises the full `run_open_pr` → `run_reproduce` round-trip
with `predict_cache.get_or_build_predictions` monkeypatched to return deterministic
synthetic prediction arrays. It therefore needs both `app.pr.open_pr` AND
`app.runner.metrics_bridge` to import successfully — which only happens inside the
harness Docker container (PYTHONPATH=/app:/opt/ml_retraining merges the two
namespaces). On host, the two `app` packages collide and the canonical metric
chain (sharpe_metrics, cpcv) does not resolve, so we skip cleanly.

A real-runner version (no monkeypatched predict) is filed for plan 04-06 e2e.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pytest


# Import-time skip: if the canonical metric chain is not available, the
# `app.pr.open_pr` import below would fail. We skip cleanly so host pytest
# runs (and CI matrices that don't merge ml-retraining into the same `app`)
# don't surface a spurious failure.
try:
    from app.runner.metrics_bridge import _CANONICAL_METRICS_AVAILABLE
except ImportError:  # pragma: no cover
    _CANONICAL_METRICS_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _CANONICAL_METRICS_AVAILABLE,
    reason=(
        "ml-retraining canonical metric chain not importable into harness `app` "
        "namespace — runs in container CI, not host pytest"
    ),
)


@pytest.fixture
def synthetic_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict):
    """Stand up a minimal harness root under tmp_path with a synthetic snapshot."""
    harness_root = tmp_path / "tournament-harness"
    (harness_root / "data" / "snapshots").mkdir(parents=True)
    (harness_root / "data" / "leaderboard").mkdir(parents=True)
    (harness_root / "data" / "cache").mkdir(parents=True)
    snap = synthetic_snapshot_dict()
    tid = snap["tournament_id"]
    with open(harness_root / "data" / "snapshots" / f"{tid}.json", "w") as f:
        json.dump(snap, f)

    # Monkeypatch HARNESS_ROOT in both pr.open_pr and pr.reproduce.
    from app.pr import open_pr as op_mod
    from app.pr import reproduce as rp_mod
    from app.significance import predict_cache as pc_mod

    monkeypatch.setattr(op_mod, "HARNESS_ROOT", harness_root)
    monkeypatch.setattr(rp_mod, "HARNESS_ROOT", harness_root)
    # Reproduce also needs the migrations directory pointing at the real on-disk dir.
    # MIGRATIONS_DIR is computed module-load time relative to the source file, so the
    # real services/tournament-harness/migrations/ path is already correct.

    # Monkeypatch git checks on every importer that resolves them.
    monkeypatch.setattr("app.orchestrator.launcher._git_is_dirty", lambda: False)
    monkeypatch.setattr("app.orchestrator.launcher._git_sha", lambda: "FIXED_SHA")
    monkeypatch.setattr(op_mod, "_git_is_dirty", lambda: False)
    monkeypatch.setattr(op_mod, "_git_sha", lambda: "FIXED_SHA")
    monkeypatch.setattr(rp_mod, "_git_is_dirty", lambda: False)
    monkeypatch.setattr(rp_mod, "_git_sha", lambda: "FIXED_SHA")

    # Deterministic predict callback — keyed on (tid, run_id) so each member
    # gets a stable array across both pipeline invocations.
    def fake_get_or_build_predictions(
        *, harness_root, tournament_id, run_id, predict_fn
    ):
        seed = abs(hash((tournament_id, run_id))) % (2**31)
        rng = np.random.default_rng(seed)
        n = 200
        last = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        # Predicted prices have a small positive drift relative to last_close.
        pred = last * np.exp(rng.normal(0.001, 0.01, n))
        actual = last * np.exp(rng.normal(0.0, 0.01, n))
        return {
            "pred_prices": pred.astype(np.float64),
            "last_close": last.astype(np.float64),
            "actual_prices": actual.astype(np.float64),
        }

    monkeypatch.setattr(
        pc_mod, "get_or_build_predictions", fake_get_or_build_predictions
    )
    # open_pr.py imports the symbol directly — patch the module-level binding too.
    monkeypatch.setattr(
        op_mod, "get_or_build_predictions", fake_get_or_build_predictions
    )

    return harness_root, tid


def test_reproduce_round_trip_idempotent(synthetic_run_dir):
    from app.pr.open_pr import run_open_pr
    from app.pr.reproduce import _diff_significance, run_reproduce

    harness_root, tid = synthetic_run_dir

    # Step 1: open-pr in dry-run mode → writes the operator's original significance.json.
    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0
    sig_path = harness_root / "data" / "snapshots" / f"{tid}.significance.json"
    assert sig_path.exists()
    with open(sig_path) as f:
        original = json.load(f)
    # Capture mtime BEFORE reproduce so we can assert it never changes (W2 fix).
    original_mtime_ns = sig_path.stat().st_mtime_ns

    # Step 2: reproduce → must produce identical significance within tolerance,
    # writing scratch artifacts under the dry-run suffix and cleaning them up on success.
    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA", force=False)
    assert rc == 0

    # Step 3: temp DB cleaned up; dry-run scratch artifacts cleaned up.
    assert not (harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db").exists()
    for ext in ("significance.json", "ensemble.json", "leaderboard.md"):
        scratch = harness_root / "data" / "snapshots" / f"{tid}.dry-run.{ext}"
        assert not scratch.exists(), (
            f"W2: dry-run scratch artifact not cleaned: {scratch}"
        )

    # Step 4: original significance.json is NEVER overwritten by reproduce (W2 fix).
    # mtime is preserved exactly — no Path.write_text against the original happened.
    assert sig_path.stat().st_mtime_ns == original_mtime_ns, (
        "W2 regression: original significance.json mtime changed during reproduce"
    )
    with open(sig_path) as f:
        after = json.load(f)
    assert after == original
    assert _diff_significance(original, after) == []


def test_reproduce_detects_drift(synthetic_run_dir, monkeypatch):
    from app.pr.open_pr import run_open_pr
    from app.pr.reproduce import run_reproduce

    harness_root, tid = synthetic_run_dir

    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0

    # Now corrupt the prediction callback so the second run produces different metrics.
    from app.pr import open_pr as op_mod

    def drifted(*, harness_root, tournament_id, run_id, predict_fn):
        seed = abs(hash((tournament_id, run_id, "DRIFT"))) % (2**31)
        rng = np.random.default_rng(seed)
        n = 200
        last = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        # Large positive drift → significantly different sharpe_lift / p-values.
        pred = last * np.exp(rng.normal(0.05, 0.01, n))
        actual = last
        return {
            "pred_prices": pred.astype(np.float64),
            "last_close": last.astype(np.float64),
            "actual_prices": actual.astype(np.float64),
        }

    monkeypatch.setattr(op_mod, "get_or_build_predictions", drifted)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA", force=True)
    assert exc.value.code == 4
    # Forensic — temp DB STILL EXISTS for inspection (CD-06).
    assert (harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db").exists()


def test_reproduce_round_trip_no_real_runner_imports(synthetic_run_dir):
    """Sanity: the round-trip MUST not pull in tensorflow/keras (CI-suitability)."""
    from app.pr.open_pr import run_open_pr
    from app.pr.reproduce import run_reproduce

    harness_root, tid = synthetic_run_dir

    before = set(sys.modules.keys())
    run_open_pr(tid, allow_dirty=False, dry_run=True)
    run_reproduce(tid, git_sha_expected="FIXED_SHA", force=False)
    after = set(sys.modules.keys())
    new = after - before
    # metrics_bridge MAY be imported at collect time elsewhere — what we forbid is
    # tensorflow/keras hot loads inside the test path.
    heavies = [m for m in new if "tensorflow" in m or "keras" in m]
    assert not heavies, f"reproduce round-trip pulled in TF/Keras: {heavies}"
