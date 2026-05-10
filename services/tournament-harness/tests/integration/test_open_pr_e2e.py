"""End-to-end smoke test for `tournament open-pr` (Phase 4 ROADMAP success criteria 1+3).

All four ROADMAP success criteria are tested across the phase:
  1. Ensemble + bootstrap p-value: significance.json schema + n_resamples=10000
     (test_open_pr_smoke_round_trip_winner).
  2. No legacy R² criterion: covered by 04-05 grep gate
     (services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py).
  3. Draft PR shape: gh argv captured under dry_run=False with mocked subprocess
     (test_open_pr_gh_argv_shape_under_real_path).
  4. No `gh pr merge` invocation: covered by 04-05 grep gate
     (services/tournament-harness/tests/integration/test_no_auto_merge.py).

Environment: this test exercises the full `run_open_pr` pipeline with
`predict_cache.get_or_build_predictions` monkeypatched to return deterministic
synthetic prediction arrays. It therefore needs both `app.pr.open_pr` AND
`app.runner.metrics_bridge` to import successfully — which only happens inside
the harness Docker container (PYTHONPATH=/app:/opt/ml_retraining merges the two
namespaces). On host, the two `app` packages collide and the canonical metric
chain (sharpe_metrics, cpcv) does not resolve, so we skip cleanly. Mirrors the
host-skip pattern from 04-04's test_reproduce_idempotent.py.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


# Import-time skip: if the canonical metric chain is not available, the
# `app.pr.open_pr` import below would fail. We skip cleanly so host pytest
# runs (and CI matrices that don't merge ml-retraining into the same `app`
# namespace) don't surface a spurious failure.
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


_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _SERVICE_ROOT / "migrations"


def _build_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict, *, drift: float):
    """Stand up a tmp harness root + monkeypatched predictions.

    drift > 0 → predictions show positive log-return on average → winning ensemble.
    drift = 0 → predictions ≈ persistence baseline → no win.
    """
    from app.leaderboard.db import LeaderboardDB, run_migrations
    from app.pr import open_pr as op_mod
    from app.significance import predict_cache as pc_mod

    harness_root = tmp_path / "tournament-harness"
    (harness_root / "data" / "snapshots").mkdir(parents=True)
    (harness_root / "data" / "leaderboard").mkdir(parents=True)
    (harness_root / "data" / "cache").mkdir(parents=True)

    snap = synthetic_snapshot_dict()
    tid = snap["tournament_id"]
    with open(harness_root / "data" / "snapshots" / f"{tid}.json", "w") as f:
        json.dump(snap, f)

    # Stand up a real leaderboard SQLite (so count_tournaments runs against real
    # data and the D-09 disclosure note populates).
    db_path = harness_root / "data" / "leaderboard" / "tournaments.db"
    run_migrations(db_path, _MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    try:
        db.upsert_tournament(
            snap["tournament_id"],
            snap["config"]["config_yaml"],
            snap["config"].get("git_sha", "FIXED_SHA"),
            int(snap["config"].get("seed", 0)),
        )
        # Use the same flat→nested adapter reproduce.py uses, inlined here.
        for row in snap["rows"]:
            db.insert_run(
                {
                    "run_id": row["run_id"],
                    "tournament_id": row["tournament_id"],
                    "architecture": row["architecture"],
                    "symbol": row["symbol"],
                    "horizon": row.get("horizon", 0),
                    "target_mode": row.get("target_mode", "log_returns"),
                    "hp_hash": row["hp_hash"],
                    "git_sha": row.get("git_sha", "FIXED_SHA"),
                    "tournament_start_ts": row.get("tournament_start_ts", ""),
                    "train_window_includes_contaminated": 0,
                    "status": row.get("status", "success"),
                    "failure_reason": row.get("failure_reason"),
                    "failure_stderr_tail": row.get("failure_stderr_tail"),
                    "metrics": {
                        "r2_returns": None,
                        "dir_acc_corrected": row.get("dir_acc_corrected"),
                        "oos_sharpe": row.get("oos_sharpe"),
                        "psr": None,
                        "dsr": row.get("dsr"),
                        "cpcv_dsr": row.get("cpcv_dsr"),
                        "train_seconds": None,
                    },
                }
            )
    finally:
        db.close()

    # Patch HARNESS_ROOT so artifacts land under tmp_path.
    monkeypatch.setattr(op_mod, "HARNESS_ROOT", harness_root)

    # Patch git checks — never invoke real `git` from inside a tmp tree.
    monkeypatch.setattr(op_mod, "_git_is_dirty", lambda: False)
    monkeypatch.setattr(op_mod, "_git_sha", lambda: "FIXED_SHA")

    # Deterministic predictions — keyed on (tid, run_id) so each member gets a
    # stable array. drift parameter controls whether the ensemble wins.
    def fake_get_or_build_predictions(
        *, harness_root, tournament_id, run_id, predict_fn
    ):
        seed = abs(hash((tournament_id, run_id))) % (2**31)
        rng = np.random.default_rng(seed)
        n = 200
        last = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
        # Predicted prices: drift > 0 means systematic positive log-return signal.
        # drift = 0 → predictions match last_close on average → ≈ persistence.
        pred = last * np.exp(rng.normal(drift, 0.005, n))
        actual = last * np.exp(rng.normal(drift, 0.005, n))
        return {
            "pred_prices": pred.astype(np.float64),
            "last_close": last.astype(np.float64),
            "actual_prices": actual.astype(np.float64),
        }

    # Patch BOTH the source module and the open_pr-level binding (open_pr.py
    # imports the symbol directly via `from ... import get_or_build_predictions`).
    monkeypatch.setattr(
        pc_mod, "get_or_build_predictions", fake_get_or_build_predictions
    )
    monkeypatch.setattr(
        op_mod, "get_or_build_predictions", fake_get_or_build_predictions
    )

    return harness_root, tid


@pytest.fixture
def winner_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict):
    """Tmp harness root + monkeypatched predictions designed to PRODUCE a winning ensemble."""
    return _build_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict, drift=0.005)


@pytest.fixture
def no_win_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict):
    """Tmp harness root + zero-drift predictions (no winning ensemble expected)."""
    return _build_run_dir(tmp_path, monkeypatch, synthetic_snapshot_dict, drift=0.0)


def test_open_pr_smoke_round_trip_winner(winner_run_dir, capsys):
    """ROADMAP success criterion 1: ensemble + bootstrap p-value vs persistence.

    Asserts the full schema of significance.json and ensemble.json end-to-end.
    """
    from app.pr.open_pr import run_open_pr

    harness_root, tid = winner_run_dir

    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0

    snap_dir = harness_root / "data" / "snapshots"
    ens_path = snap_dir / f"{tid}.ensemble.json"
    sig_path = snap_dir / f"{tid}.significance.json"
    lb_path = snap_dir / f"{tid}.leaderboard.md"
    assert ens_path.exists() and sig_path.exists() and lb_path.exists()
    # No partials.
    assert list(snap_dir.glob("*.tmp")) == []

    with open(sig_path) as f:
        sig = json.load(f)
    assert sig["baseline"] == "persistence"
    assert sig["aggregation"] == "mean_log_returns"
    assert isinstance(sig["tournaments_evaluated_count"], int)
    assert sig["n_winning_symbols"] >= 1, (
        f"expected at least 1 winner with drift=0.005; got {sig}"
    )
    # Per-symbol schema: every entry must carry the full significance contract.
    for sym, entry in sig["per_symbol"].items():
        for key in (
            "sharpe_pvalue",
            "dir_acc_pvalue",
            "sharpe_lift",
            "dir_acc_lift",
            "n_oos_bars",
            "block_size",
            "n_resamples",
            "bootstrap_seed",
            "win_gate_passed",
            "n_members",
        ):
            assert key in entry, f"{sym} missing {key}"
        # n_resamples is fixed at 10_000 unless the symbol had insufficient runs.
        if entry["n_members"] >= 3:
            assert entry["n_resamples"] == 10_000, (
                f"{sym}: expected n_resamples=10000, got {entry['n_resamples']}"
            )

    with open(ens_path) as f:
        ens = json.load(f)
    # Five symbols × top-3 ensemble members each.
    assert isinstance(ens["ensembles"], list)
    assert len(ens["ensembles"]) == 5, (
        f"expected 5 ensembles, got {len(ens['ensembles'])}"
    )
    for member_block in ens["ensembles"]:
        assert len(member_block["members"]) == 3, (
            f"expected top-3 ensemble; got {len(member_block['members'])}"
        )
        for m in member_block["members"]:
            for k in ("run_id", "architecture", "hp_hash", "dsr"):
                assert k in m, f"ensemble member missing {k}"
    # D-03 invariant: no weights/scalers/predictions in artifact.
    flat = json.dumps(ens).lower()
    for forbidden in ("weights", "scaler", "pred_prices", "actual_prices"):
        assert forbidden not in flat, (
            f"D-03 violation: ensemble.json contains {forbidden!r}"
        )

    lb_text = lb_path.read_text()
    assert "[WIN]" in lb_text, "leaderboard.md missing [WIN] tag for winning symbol"

    # PR-shape JSON went to stdout under dry_run=True.
    captured = capsys.readouterr()
    assert '"dry_run": true' in captured.out


def test_open_pr_smoke_no_win_path(no_win_run_dir, capsys):
    """No winning symbol → no PR opened, exit 0, stdout signals no_win."""
    from app.pr.open_pr import run_open_pr

    harness_root, tid = no_win_run_dir

    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0
    with open(harness_root / "data" / "snapshots" / f"{tid}.significance.json") as f:
        sig = json.load(f)
    assert sig["n_winning_symbols"] == 0, (
        f"expected 0 winners with drift=0.0; got {sig['n_winning_symbols']}"
    )
    captured = capsys.readouterr()
    assert '"no_win": true' in captured.out


def test_open_pr_records_git_sha_consistently(winner_run_dir):
    """T-04-35: git_sha is identical across ensemble.json AND significance.json."""
    from app.pr.open_pr import run_open_pr

    harness_root, tid = winner_run_dir
    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0

    with open(harness_root / "data" / "snapshots" / f"{tid}.ensemble.json") as f:
        ens = json.load(f)
    with open(harness_root / "data" / "snapshots" / f"{tid}.significance.json") as f:
        sig = json.load(f)
    assert ens["git_sha"] == sig["git_sha"] == "FIXED_SHA"


def test_open_pr_gh_argv_shape_under_real_path(winner_run_dir, monkeypatch):
    """ROADMAP success criterion 3: draft PR opened with the right argv shape.

    When dry_run=False, gh subprocess.run is mocked. We assert:
      - argv starts with ['gh', 'pr', 'create', '--draft']
      - --head value is f'tournament/{tid}' (CD-02 branch convention)
      - labels include 'tournament', 'evaluation-gate', 'winner'
      - GH_TOKEN literal NEVER appears in argv (T-04-14 — env, not argv)
      - shell=False (no shell injection surface)
      - No 'gh pr merge' anywhere — the auto-merge subcommand must not be invoked
        (CD-10 / T-04-16 — re-asserted at the integration layer for belt-and-suspenders).
    """
    from app.pr import gh as gh_mod
    from app.pr.open_pr import run_open_pr

    harness_root, tid = winner_run_dir

    # Mock subprocess + env so we don't actually call gh.
    monkeypatch.setenv("GH_TOKEN", "ghp_fake_token_for_test")
    monkeypatch.setattr(gh_mod, "_check_gh_installed", lambda: None)

    captured_calls = []

    def fake_run(cmd, *args, **kwargs):
        captured_calls.append({"cmd": list(cmd), "kwargs": dict(kwargs)})
        r = MagicMock()
        r.returncode = 0
        r.stdout = "https://github.com/owner/repo/pull/123"
        r.stderr = ""
        return r

    monkeypatch.setattr(gh_mod.subprocess, "run", fake_run)

    rc = run_open_pr(tid, allow_dirty=False, dry_run=False)
    assert rc == 0
    assert len(captured_calls) == 1, (
        f"expected exactly one gh subprocess call; got {len(captured_calls)}"
    )

    cmd = captured_calls[0]["cmd"]
    kwargs = captured_calls[0]["kwargs"]

    # Prefix shape: gh pr create --draft.
    assert cmd[:4] == ["gh", "pr", "create", "--draft"], (
        f"expected ['gh','pr','create','--draft'] prefix; got {cmd[:4]}"
    )

    # All required flags present.
    for flag in ("--title", "--body", "--head", "--base"):
        assert flag in cmd, f"argv missing {flag}: {cmd}"

    # CD-02 branch convention: tournament/{tid}.
    head_idx = cmd.index("--head")
    assert cmd[head_idx + 1] == f"tournament/{tid}", (
        f"expected --head tournament/{tid}; got {cmd[head_idx + 1]}"
    )

    # CD-02: base is main.
    base_idx = cmd.index("--base")
    assert cmd[base_idx + 1] == "main", f"expected --base main; got {cmd[base_idx + 1]}"

    # Labels: tournament + evaluation-gate (always) + winner (n_wins>=1).
    labels = [cmd[i + 1] for i, x in enumerate(cmd) if x == "--label"]
    assert "tournament" in labels, f"missing 'tournament' label: {labels}"
    assert "evaluation-gate" in labels, f"missing 'evaluation-gate' label: {labels}"
    assert "winner" in labels, f"missing 'winner' label: {labels}"

    # T-04-14: GH_TOKEN literal must NEVER appear in argv (env-only).
    assert all("ghp_fake_token_for_test" not in str(x) for x in cmd), (
        "T-04-14 regression: GH_TOKEN literal leaked into argv"
    )

    # No shell=True (no shell injection surface).
    assert kwargs.get("shell", False) is False, (
        "subprocess.run invoked with shell=True — injection surface"
    )

    # CD-10 / T-04-16 belt-and-suspenders: no 'gh pr merge' anywhere.
    # Construct the literal at runtime so this file's source itself does not
    # contain the auto-merge string (mirrors gh.py docstring discipline).
    auto_merge_subcmd = "merge"
    # The argv pattern that would represent auto-merge is gh + pr + merge.
    pr_idx = cmd.index("pr") if "pr" in cmd else -1
    assert pr_idx == -1 or cmd[pr_idx + 1] != auto_merge_subcmd, (
        f"CD-10 violation: argv contains 'gh pr {auto_merge_subcmd}': {cmd}"
    )


def test_open_pr_count_tournaments_reflects_state_at_call_time(winner_run_dir):
    """D-09: tournaments_evaluated_count is queried at PR-open time, not module-load time.

    Insert two extra tournament rows AFTER fixture setup but BEFORE run_open_pr.
    The disclosure count in significance.json must reflect the post-insert state.
    """
    from app.leaderboard.db import LeaderboardDB
    from app.pr.open_pr import run_open_pr

    harness_root, tid = winner_run_dir

    db = LeaderboardDB(harness_root / "data" / "leaderboard" / "tournaments.db")
    try:
        db.upsert_tournament("extra_tid_1", "config: {}", "FIXED_SHA", 1)
        db.upsert_tournament("extra_tid_2", "config: {}", "FIXED_SHA", 2)
    finally:
        db.close()

    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0
    with open(harness_root / "data" / "snapshots" / f"{tid}.significance.json") as f:
        sig = json.load(f)
    # Original tid + 2 extras = 3.
    assert sig["tournaments_evaluated_count"] >= 3, (
        f"D-09 regression: expected count >= 3 after inserting 2 extras; got "
        f"{sig['tournaments_evaluated_count']}"
    )


def test_open_pr_imports_real_predict_fn_factory():
    """B3 e2e proof: open_pr.py imports the canonical 04-07 build_predict_fn.

    Defends against a regression that re-introduces the prior NotImplementedError stub.
    Static check on the module source is included so even a moved-to-helper-module
    stub would still trip the assertion.
    """
    from app.pr import open_pr as op_mod

    importlib.reload(op_mod)
    assert hasattr(op_mod, "build_predict_fn"), (
        "B3 regression: open_pr.py does not import build_predict_fn from app.runner.predict_fn"
    )
    from app.runner.predict_fn import build_predict_fn as canonical

    assert op_mod.build_predict_fn is canonical, (
        "B3 regression: open_pr.build_predict_fn is not the canonical 04-07 implementation"
    )
    src = (_SERVICE_ROOT / "app" / "pr" / "open_pr.py").read_text()
    assert "NotImplementedError" not in src, (
        "B3 regression: open_pr.py still contains a NotImplementedError stub"
    )


def test_open_pr_writes_no_partial_artifacts(winner_run_dir):
    """Atomic-write discipline holds end-to-end: no .tmp files leftover.

    Covers both data/snapshots/ (artifacts.py atomic writes) and data/cache/
    (predict_cache CD-11 atomic writes — the cache_dir is empty in this test
    because predict_cache is monkeypatched, but the assertion is still correct
    if the harness ever switches to the real cache).
    """
    from app.pr.open_pr import run_open_pr

    harness_root, tid = winner_run_dir
    rc = run_open_pr(tid, allow_dirty=False, dry_run=True)
    assert rc == 0
    snap_dir = harness_root / "data" / "snapshots"
    assert list(snap_dir.glob("*.tmp")) == []
    cache_dir = harness_root / "data" / "cache"
    if cache_dir.exists():
        assert list(cache_dir.rglob("*.tmp")) == []
