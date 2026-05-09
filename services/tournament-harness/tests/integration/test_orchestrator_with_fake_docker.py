"""Integration test — run_tournament with a MagicMock docker client.

Exercises the full pipeline:
  load_tournament → enumerate_experiments → for each cell: launch (mocked)
  → write fake result.json into the bind-mount dir → ingest → DB insert.

Validates TOURN-01 (sequential launch over arch × sym × HP), TOURN-02
(every cell produces a leaderboard row), TOURN-04 (failed runs persist).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config.tournament_loader import enumerate_experiments, load_tournament
from app.leaderboard.db import LeaderboardDB
from app.orchestrator.launcher import run_tournament


# Migrations directory relative to service root (not /app/migrations which is container-only).
_SERVICE_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS_DIR = _SERVICE_ROOT / "migrations"


def _make_tiny_yaml(tmp_path, *, force_failure=False) -> Path:
    """Construct a 2-cell YAML — small enough to keep the test fast."""
    yaml_text = textwrap.dedent("""
        tournament_id: "fake_docker_test"
        seed: 42
        symbols: ["SOLUSDT"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        max_experiments: 5
        default_resource_caps:
          mem_limit: "1g"
          cpus: 1.0
          wallclock_timeout_seconds: 60
        architectures:
          gru:
            units: [[16], [32]]
            dropout: [0.1]
            lr: [0.001]
            batch: [32]
            lookback: [10]
            horizon: [5]
    """).strip()
    p = tmp_path / "tournament.yaml"
    p.write_text(yaml_text)
    return p


def _patch_settings(monkeypatch, tmp_path):
    """Point settings.leaderboard_db_path + results_dir at tmp_path; set placeholder password."""
    monkeypatch.setenv("LEADERBOARD_DB_PATH", str(tmp_path / "leaderboard.db"))
    monkeypatch.setenv("RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("TIMESCALE_PASSWORD", "fake_pw_for_test")
    # Reset the get_settings singleton so the new env wins
    from app.config import settings as settings_mod

    settings_mod._settings = None


def _patch_migrations(monkeypatch):
    """Redirect the hardcoded /app/migrations path to the local migrations dir."""
    from app.orchestrator import launcher as launcher_mod
    from app.leaderboard import db as db_mod

    real_run_migrations = db_mod.run_migrations

    def patched_run_migrations(db_path, migrations_dir):
        return real_run_migrations(db_path, _MIGRATIONS_DIR)

    monkeypatch.setattr(launcher_mod, "run_migrations", patched_run_migrations)


def _seed_result_files(yaml_path, results_root, *, fail_run_idx=None):
    """For each enumerated experiment, pre-populate /output/{tid}/{rid}/result.json
    so the fake docker client's container.run can be a no-op while ingest still
    sees a real file.
    """
    spec = load_tournament(yaml_path)
    experiments = enumerate_experiments(spec)
    for i, exp in enumerate(experiments):
        run_dir = Path(results_root) / exp.tournament_id / exp.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        if fail_run_idx is not None and i == fail_run_idx:
            payload = {
                "status": "failed",
                "reason": "nan_loss",
                "run_id": exp.run_id,
                "tournament_id": exp.tournament_id,
                "architecture": exp.architecture,
                "symbol": exp.symbol,
                "horizon": exp.horizon,
                "target_mode": exp.target_mode,
                "hp_hash": exp.hp_hash,
                "git_sha": "test_sha",
                "tournament_start_ts": "test_ts",
            }
        else:
            payload = {
                "status": "success",
                "reason": None,
                "run_id": exp.run_id,
                "tournament_id": exp.tournament_id,
                "architecture": exp.architecture,
                "symbol": exp.symbol,
                "horizon": exp.horizon,
                "target_mode": exp.target_mode,
                "hp_hash": exp.hp_hash,
                "git_sha": "test_sha",
                "tournament_start_ts": "test_ts",
                "metrics": {
                    "r2_returns": 0.05,
                    "dir_acc_corrected": 0.55,
                    "oos_sharpe": 0.8,
                    "psr": 0.7,
                    "dsr": 0.55,
                    "cpcv_dsr": 0.5,
                    "train_seconds": 12.5,
                },
            }
        (run_dir / "result.json").write_text(json.dumps(payload))


def test_run_tournament_full_pipeline_all_success(
    tmp_path, monkeypatch, fake_docker_client
):
    yaml_path = _make_tiny_yaml(tmp_path)
    _patch_settings(monkeypatch, tmp_path)
    _patch_migrations(monkeypatch)
    _seed_result_files(yaml_path, tmp_path / "results")

    summary = run_tournament(
        yaml_path, allow_dirty=True, docker_client=fake_docker_client
    )

    assert summary["tournament_id"] == "fake_docker_test"
    # GRU has 2 unit choices × 1 of everything else × 1 sym × 1 interval × 1 tm = 2 cells
    assert summary["n_total"] == 2
    assert summary["n_success"] == 2
    assert summary["n_failed"] == 0

    # Every cell has a leaderboard row
    db = LeaderboardDB(tmp_path / "leaderboard.db")
    rows = db.list_runs(tournament_id="fake_docker_test")
    assert len(rows) == 2
    assert all(r["status"] == "success" for r in rows)
    db.close()

    # T-03-24 security lockdown — assert containers.run was actually called with the
    # hardened kwargs. Guards against silent regression of the docker.sock mitigation.
    fake_docker_client.containers.run.assert_called()
    call_kwargs = fake_docker_client.containers.run.call_args.kwargs
    assert call_kwargs.get("read_only") is True, (
        "container must be launched with read_only=True (T-03-24 lockdown)"
    )
    assert "ALL" in (call_kwargs.get("cap_drop") or []), (
        "container must be launched with cap_drop=['ALL'] (T-03-24 lockdown)"
    )
    # Network must be the project's named network (D-09), not bridge / host
    assert call_kwargs.get("network") == "crypto-bot-network", (
        f"container must join crypto-bot-network, got {call_kwargs.get('network')!r}"
    )


def test_run_tournament_persists_failed_rows(tmp_path, monkeypatch, fake_docker_client):
    """TOURN-04 — failed runs ALWAYS get a leaderboard row, never silently dropped."""
    yaml_path = _make_tiny_yaml(tmp_path)
    _patch_settings(monkeypatch, tmp_path)
    _patch_migrations(monkeypatch)
    _seed_result_files(yaml_path, tmp_path / "results", fail_run_idx=0)

    summary = run_tournament(
        yaml_path, allow_dirty=True, docker_client=fake_docker_client
    )

    assert summary["n_total"] == 2
    assert summary["n_success"] == 1
    assert summary["n_failed"] == 1

    db = LeaderboardDB(tmp_path / "leaderboard.db")
    failed_rows = db.list_runs(tournament_id="fake_docker_test", status="failed")
    assert len(failed_rows) == 1
    assert failed_rows[0]["failure_reason"] == "nan_loss"
    db.close()


def test_run_tournament_oom_via_container_state(tmp_path, monkeypatch):
    """Orchestrator-side classification: container reports OOMKilled → leaderboard row
    gets failure_reason='oom_killed' even when no result.json exists.
    """
    yaml_path = _make_tiny_yaml(tmp_path)
    _patch_settings(monkeypatch, tmp_path)
    _patch_migrations(monkeypatch)
    # NO result.json this time

    fake_client = MagicMock()
    container = MagicMock()
    container.wait = MagicMock(return_value={"StatusCode": 137, "Error": None})
    container.logs = MagicMock(return_value=b"oom\n")
    container.kill = MagicMock()
    container.remove = MagicMock()
    container.reload = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {"OOMKilled": True, "ExitCode": 137}}
    container.labels = {"tournament_id": "t", "run_id": "r"}
    fake_client.containers.run = MagicMock(return_value=container)

    summary = run_tournament(yaml_path, allow_dirty=True, docker_client=fake_client)

    assert summary["n_failed"] == 2  # both cells OOM
    db = LeaderboardDB(tmp_path / "leaderboard.db")
    rows = db.list_runs(tournament_id="fake_docker_test", status="failed")
    assert all(r["failure_reason"] == "oom_killed" for r in rows)
    db.close()


def test_run_tournament_refuses_dirty_tree(tmp_path, monkeypatch, fake_docker_client):
    """D-13: dirty git tree blocks tournament unless --allow-dirty."""
    yaml_path = _make_tiny_yaml(tmp_path)
    _patch_settings(monkeypatch, tmp_path)
    _patch_migrations(monkeypatch)

    # Force git_is_dirty to True
    from app.orchestrator import launcher

    monkeypatch.setattr(launcher, "_git_is_dirty", lambda: True)

    with pytest.raises(RuntimeError, match="dirty"):
        run_tournament(yaml_path, allow_dirty=False, docker_client=fake_docker_client)


def test_run_tournament_refuses_placeholder_password(
    tmp_path, monkeypatch, fake_docker_client
):
    """Refuses to start when TIMESCALE_PASSWORD is the CHANGE_ME_VIA_ENV placeholder."""
    yaml_path = _make_tiny_yaml(tmp_path)
    monkeypatch.setenv("LEADERBOARD_DB_PATH", str(tmp_path / "leaderboard.db"))
    monkeypatch.setenv("TIMESCALE_PASSWORD", "CHANGE_ME_VIA_ENV")
    from app.config import settings as settings_mod

    settings_mod._settings = None

    with pytest.raises(RuntimeError, match="placeholder"):
        run_tournament(yaml_path, allow_dirty=True, docker_client=fake_docker_client)
