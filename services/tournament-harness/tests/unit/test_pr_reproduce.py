"""Unit tests for app.pr.reproduce (04-04).

The reproduce subcommand re-derives significance.json from a snapshot at the
recorded git_sha and verifies the result is bit-(near-)identical within
D-12 FP-noise tolerance. These tests heavily monkeypatch run_open_pr so we
exercise the diff/refusal/lifecycle paths without invoking the heavy ensemble
pipeline.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _baseline_significance() -> Dict[str, Any]:
    """Minimal significance.json the operator originally captured."""
    return {
        "tournament_id": "t-04-04-test",
        "git_sha": "FIXED_SHA",
        "per_symbol": {
            "BTCUSDT": {
                "n_members": 3,
                "sharpe_lift": 0.10,
                "dir_acc_lift": 0.02,
                "sharpe_pvalue": 0.01,
                "dir_acc_pvalue": 0.04,
                "n_oos_bars": 200,
                "block_size": 5,
                "n_resamples": 10000,
                "bootstrap_seed": 12345,
            },
        },
        "n_winning_symbols": 1,
        "tournaments_evaluated_count": 1,
    }


@pytest.fixture
def repro_env(tmp_path, monkeypatch):
    """Set up a synthetic harness root + an existing baseline significance.json.

    Returns: (harness_root, tid, baseline_sig)
    """
    from app.pr import reproduce as rp_mod

    harness_root = tmp_path / "tournament-harness"
    snap_dir = harness_root / "data" / "snapshots"
    lb_dir = harness_root / "data" / "leaderboard"
    snap_dir.mkdir(parents=True)
    lb_dir.mkdir(parents=True)

    tid = "t-04-04-test"
    snapshot = {
        "tournament_id": tid,
        "config": {
            "config_yaml": "tournament_id: t-04-04-test\n",
            "git_sha": "FIXED_SHA",
            "seed": 42,
            "tournament_start_ts": "2026-05-09T00:00:00Z",
        },
        "rows": [],
        "summary": {
            "n_rows": 0,
            "n_success": 0,
            "n_failed": 0,
            "symbols": ["BTCUSDT"],
            "architectures": [],
        },
    }
    with open(snap_dir / f"{tid}.json", "w") as f:
        json.dump(snapshot, f)

    baseline = _baseline_significance()
    with open(snap_dir / f"{tid}.significance.json", "w") as f:
        json.dump(baseline, f)

    # Force module to use our tmp harness root.
    monkeypatch.setattr(rp_mod, "HARNESS_ROOT", harness_root)
    # Default: clean tree + matching SHA.
    monkeypatch.setattr(rp_mod, "_git_is_dirty", lambda: False)
    monkeypatch.setattr(rp_mod, "_git_sha", lambda: "FIXED_SHA")

    return harness_root, tid, baseline


def _patch_run_open_pr_writing(
    monkeypatch, harness_root: Path, tid: str, payload: Dict[str, Any]
):
    """Monkeypatch run_open_pr to write `payload` as the dry-run significance file.

    This bypasses the heavy ensemble pipeline; we drive only the diff path.
    """
    from app.pr import reproduce as rp_mod

    snap_dir = harness_root / "data" / "snapshots"

    def fake_run_open_pr(
        tournament_id, *, allow_dirty=False, dry_run=False, output_suffix=""
    ):
        assert dry_run is True, "reproduce must call run_open_pr with dry_run=True"
        assert output_suffix, "reproduce must pass a non-empty output_suffix"
        out = snap_dir / f"{tournament_id}.{output_suffix}.significance.json"
        with open(out, "w") as f:
            json.dump(payload, f)
        # Touch the other two scratch artifacts too — reproduce should clean them up.
        (snap_dir / f"{tournament_id}.{output_suffix}.ensemble.json").write_text("{}")
        (snap_dir / f"{tournament_id}.{output_suffix}.leaderboard.md").write_text("# x")
        return 0

    # Patch the module-level binding `run_open_pr` if reproduce imports it lazily,
    # we instead patch via `app.pr.open_pr` so the import inside run_reproduce
    # picks up the fake.
    import app.pr.open_pr as op_mod

    monkeypatch.setattr(op_mod, "run_open_pr", fake_run_open_pr)
    return rp_mod


# ---------------------------------------------------------------------------
# Refusal paths
# ---------------------------------------------------------------------------


def test_dirty_tree_refused(repro_env, monkeypatch, capsys):
    from app.pr import reproduce as rp_mod
    from app.pr.reproduce import run_reproduce

    harness_root, tid, _ = repro_env
    monkeypatch.setattr(rp_mod, "_git_is_dirty", lambda: True)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "dirty" in err.lower()
    # No temp DB created.
    assert not (harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db").exists()


def test_head_mismatch_refused(repro_env, monkeypatch, capsys):
    from app.pr import reproduce as rp_mod
    from app.pr.reproduce import run_reproduce

    _, tid, _ = repro_env
    monkeypatch.setattr(rp_mod, "_git_sha", lambda: "abc123")

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="def456")
    assert exc.value.code == 3
    err = capsys.readouterr().err
    assert "abc123" in err
    assert "def456" in err
    assert "git checkout" in err


# ---------------------------------------------------------------------------
# Temp DB lifecycle (CD-06)
# ---------------------------------------------------------------------------


def test_temp_db_path_correct(repro_env, monkeypatch):
    from app.pr.reproduce import _temp_db_path

    harness_root, tid, _ = repro_env
    expected = harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db"
    assert _temp_db_path(tid) == expected


def test_temp_db_cleaned_on_success(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, baseline)

    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert rc == 0
    assert not (harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db").exists()


def test_temp_db_retained_on_failure(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    drifted = json.loads(json.dumps(baseline))
    # Bust tolerance — sharpe_lift goes from 0.10 to 0.50.
    drifted["per_symbol"]["BTCUSDT"]["sharpe_lift"] = 0.50
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, drifted)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert exc.value.code == 4
    # Forensic — temp DB STILL EXISTS.
    assert (harness_root / "data" / "leaderboard" / f"reproduce_{tid}.db").exists()


def test_force_flag_drops_existing_tempdb(repro_env, monkeypatch, capsys):
    from app.pr.reproduce import run_reproduce, _temp_db_path

    harness_root, tid, baseline = repro_env
    # Pre-create a stale temp DB.
    stale = _temp_db_path(tid)
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b"stale")

    # Without --force → exit 2 with clear message.
    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA", force=False)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--force" in err

    # With --force, the stale DB is dropped + run completes successfully.
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, baseline)
    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA", force=True)
    assert rc == 0


# ---------------------------------------------------------------------------
# Diff tolerance (D-12)
# ---------------------------------------------------------------------------


def test_diff_within_tolerance_returns_0(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, baseline)

    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert rc == 0


def test_diff_sharpe_outside_tolerance_returns_4(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    drifted = json.loads(json.dumps(baseline))
    drifted["per_symbol"]["BTCUSDT"]["sharpe_lift"] = 0.20  # 0.10 vs 0.20 -> diff 0.10
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, drifted)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert exc.value.code == 4


def test_diff_pvalue_outside_tolerance_returns_4(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    drifted = json.loads(json.dumps(baseline))
    drifted["per_symbol"]["BTCUSDT"]["sharpe_pvalue"] = (
        0.10  # 0.01 vs 0.10 -> 0.09 > 0.005
    )
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, drifted)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert exc.value.code == 4


def test_diff_pvalue_at_threshold_passes(repro_env, monkeypatch):
    """0.005 difference is exactly the threshold — boundary inclusive."""
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    drifted = json.loads(json.dumps(baseline))
    # 0.01 + 0.005 = 0.015 → abs diff = 0.005 ≤ tol
    drifted["per_symbol"]["BTCUSDT"]["sharpe_pvalue"] = 0.015
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, drifted)

    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert rc == 0


# ---------------------------------------------------------------------------
# CLI surface (D-12: no --allow-dirty for reproduce)
# ---------------------------------------------------------------------------


def test_no_allow_dirty_flag_in_cli():
    """`reproduce --help` must NOT advertise --allow-dirty."""
    service_root = Path(__file__).resolve().parents[2]  # services/tournament-harness/
    out = subprocess.run(
        [sys.executable, "-m", "app.cli", "reproduce", "--help"],
        cwd=str(service_root),
        env={**__import__("os").environ, "PYTHONPATH": str(service_root)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--allow-dirty" not in out.stdout


def test_help_shows_required_git_sha():
    service_root = Path(__file__).resolve().parents[2]
    out = subprocess.run(
        [sys.executable, "-m", "app.cli", "reproduce", "--help"],
        cwd=str(service_root),
        env={**__import__("os").environ, "PYTHONPATH": str(service_root)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--git-sha" in out.stdout


# ---------------------------------------------------------------------------
# Path traversal (T-04-20)
# ---------------------------------------------------------------------------


def test_invalid_tournament_id_rejected():
    from app.pr.reproduce import _validate_tid

    for bad in ("../etc/passwd", "foo/bar", "x\0y", "a b", ""):
        with pytest.raises(ValueError):
            _validate_tid(bad)


# ---------------------------------------------------------------------------
# W2 fixes — mtime preservation + scratch artifact lifecycle
# ---------------------------------------------------------------------------


def test_original_artifacts_mtime_unchanged_after_reproduce(repro_env, monkeypatch):
    """The operator's original {tid}.significance.json must NEVER be overwritten.

    We additionally pre-create the ensemble.json + leaderboard.md (operator
    originals) and check all three mtimes survive intact.
    """
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    snap_dir = harness_root / "data" / "snapshots"
    sig_path = snap_dir / f"{tid}.significance.json"
    ens_path = snap_dir / f"{tid}.ensemble.json"
    lb_path = snap_dir / f"{tid}.leaderboard.md"
    ens_path.write_text("{}")
    lb_path.write_text("# baseline")

    sig_mtime = sig_path.stat().st_mtime_ns
    ens_mtime = ens_path.stat().st_mtime_ns
    lb_mtime = lb_path.stat().st_mtime_ns

    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, baseline)
    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert rc == 0

    assert sig_path.stat().st_mtime_ns == sig_mtime
    assert ens_path.stat().st_mtime_ns == ens_mtime
    assert lb_path.stat().st_mtime_ns == lb_mtime


def test_dryrun_scratch_artifacts_cleaned_on_success(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, baseline)

    rc = run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert rc == 0
    snap_dir = harness_root / "data" / "snapshots"
    for ext in ("significance.json", "ensemble.json", "leaderboard.md"):
        scratch = snap_dir / f"{tid}.dry-run.{ext}"
        assert not scratch.exists(), f"scratch artifact not cleaned: {scratch}"


def test_dryrun_scratch_artifacts_retained_on_failure(repro_env, monkeypatch):
    from app.pr.reproduce import run_reproduce

    harness_root, tid, baseline = repro_env
    drifted = json.loads(json.dumps(baseline))
    drifted["per_symbol"]["BTCUSDT"]["sharpe_lift"] = 0.99
    _patch_run_open_pr_writing(monkeypatch, harness_root, tid, drifted)

    with pytest.raises(SystemExit) as exc:
        run_reproduce(tid, git_sha_expected="FIXED_SHA")
    assert exc.value.code == 4

    snap_dir = harness_root / "data" / "snapshots"
    # The significance scratch must be retained for forensic inspection.
    assert (snap_dir / f"{tid}.dry-run.significance.json").exists()


def test_no_significance_original_json_choreography():
    """The W2 backup-and-restore choreography MUST be gone — no .original.json literal."""
    src = (
        Path(__file__).resolve().parents[2] / "app" / "pr" / "reproduce.py"
    ).read_text()
    assert ".original.json" not in src
