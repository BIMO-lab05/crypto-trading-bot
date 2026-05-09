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
