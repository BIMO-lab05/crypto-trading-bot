"""Shared pytest fixtures for tournament-harness tests.

Path-import shim per PATTERNS.md (lines 612-617): make the service root
importable as `app.*` regardless of cwd, so `pytest tests/...` works without
an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# --- Path import shim (must run before any 'from app.*' import) ---
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


# Vendor ml-retraining for runner imports — same as the Dockerfile
# (PYTHONPATH=/app:/opt/ml_retraining inside the container; outside,
# we add it to sys.path for tests that exercise the metrics_bridge).
_REPO_ROOT = _SERVICE_ROOT.parent.parent
_ML_RETRAINING_APP = _REPO_ROOT / "services" / "ml-retraining-service"
if str(_ML_RETRAINING_APP) not in sys.path:
    sys.path.insert(0, str(_ML_RETRAINING_APP))


@pytest.fixture
def tmp_leaderboard_db(tmp_path, monkeypatch):
    """Initialise a fresh SQLite leaderboard with migrations applied — per-test isolation."""
    from app.leaderboard.db import run_migrations

    db_path = tmp_path / "leaderboard.db"
    migrations_dir = _SERVICE_ROOT / "migrations"
    run_migrations(db_path, migrations_dir)
    monkeypatch.setenv("LEADERBOARD_DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def fake_docker_client():
    """Standalone MagicMock for `docker.from_env()` returns.

    The launcher invokes `docker_client.containers.run(...)` and gets back a
    container object exposing wait/logs/kill/remove + `attrs.State`.
    """
    client = MagicMock()
    container = MagicMock()
    container.wait = MagicMock(return_value={"StatusCode": 0, "Error": None})
    container.logs = MagicMock(return_value=b"stdout line\n")
    container.kill = MagicMock()
    container.remove = MagicMock()
    container.reload = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {"OOMKilled": False, "ExitCode": 0}}
    container.labels = {"tournament_id": "t1", "run_id": "r1"}
    client.containers.run = MagicMock(return_value=container)
    return client


@pytest.fixture
def synthetic_klines():
    """OHLCV DataFrame for runner-pipeline tests without TimescaleDB."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 60_000  # above the 50K floor — runner won't reject
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    high = base + np.abs(rng.normal(0, 0.5, n))
    low = base - np.abs(rng.normal(0, 0.5, n))
    close = base + rng.normal(0, 0.2, n)
    volume = np.abs(rng.normal(1000, 100, n))
    timestamps = pd.date_range("2026-01-01", periods=n, freq="5min")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


@pytest.fixture
def test_client():
    """FastAPI TestClient for main.py read-only endpoints."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture
def synthetic_snapshot_dict():
    """Factory fixture returning a snapshot dict matching the Phase 3 export contract.

    Shape mirrors services/tournament-harness/app/leaderboard/snapshot.py:export_snapshot
    output:
      {tournament_id, exported_at, schema_version, config: {config_yaml, git_sha, seed,
       tournament_start_ts}, summary: {symbols, n_rows, n_success, n_failed, architectures},
       rows: [{run_id, symbol, architecture, hp_hash, dsr, cpcv_dsr, oos_sharpe,
               dir_acc_corrected, status, created_at, result_json, ...}, ...]}

    Each call produces deterministic values: dsr = 0.5 + 0.1*i within a symbol,
    plus one status="failed" row per symbol so D-01 selection logic can be
    exercised against the success-only filter.
    """

    def _build(
        symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"),
        runs_per_symbol=4,
        tournament_id="t-04-01-test",
    ):
        rows = []
        for sym in symbols:
            for i in range(runs_per_symbol):
                # Last run of each symbol marked failed so success-only filter has bite.
                is_failed = i == runs_per_symbol - 1
                rows.append(
                    {
                        "run_id": f"{sym.lower()}-r{i}",
                        "tournament_id": tournament_id,
                        "symbol": sym,
                        "architecture": "gru" if i % 2 == 0 else "lstm",
                        "hp_hash": f"h{i}",
                        "dsr": 0.5 + 0.1 * i if not is_failed else None,
                        "cpcv_dsr": 0.4 + 0.1 * i if not is_failed else None,
                        "oos_sharpe": 0.6 + 0.1 * i if not is_failed else None,
                        "dir_acc_corrected": 0.51 + 0.01 * i if not is_failed else None,
                        "status": "failed" if is_failed else "success",
                        "created_at": f"2026-05-09T00:{i:02d}:00Z",
                        "git_sha": "abcdef0",
                        "tournament_start_ts": "2026-05-09T00:00:00Z",
                        "horizon": 5,
                        "target_mode": "log_returns",
                        "result_json": {"metrics": {}},
                    }
                )
        snapshot = {
            "tournament_id": tournament_id,
            "exported_at": "2026-05-09T00:30:00Z",
            "schema_version": 1,
            "config": {
                "config_yaml": "tournament_id: t-04-01-test\n",
                "git_sha": "abcdef0",
                "seed": 42,
                "tournament_start_ts": "2026-05-09T00:00:00Z",
            },
            "summary": {
                "n_rows": len(rows),
                "n_success": sum(1 for r in rows if r["status"] == "success"),
                "n_failed": sum(1 for r in rows if r["status"] == "failed"),
                "symbols": sorted(set(symbols)),
                "architectures": sorted({r["architecture"] for r in rows}),
            },
            "rows": rows,
        }
        return snapshot

    return _build
