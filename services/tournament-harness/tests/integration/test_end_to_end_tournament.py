"""End-to-end real-stack tournament test (TOURN-01/02/04 wire-level proof).

Gate: requires the Phase 2 bootstrap_stack fixture (real TimescaleDB + recorded
tape via docker compose). If the fixture is unavailable (no Docker on host),
the test is skipped — it runs in nightly CI, not on every push.

Smoke shape:
  1. bootstrap_stack brings up timescaledb + recorded-tape market-data
  2. Apply migration 005_tournament_reader.sql against the running DB
  3. Insert ~60K synthetic klines for SOL/5m so the runner clears D-07 floor
  4. Run a 1-cell tournament via the CLI
  5. Assert leaderboard row exists with status='success' or 'failed' (either is fine —
     the test proves the wire works, not that the model is good)
  6. Assert export-snapshot writes a JSON file

Skip conditions:
  - Docker daemon not reachable
  - bootstrap_stack fixture not importable (Phase 2 not landed in this branch)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("docker") is None,
        reason="Docker not on PATH — skipping real-stack test",
    ),
]


# Phase 2's bootstrap_stack fixture lives in tests/integration/conftest.py.
# Try to import; if it doesn't exist, skip every test in this module.
_BOOTSTRAP_AVAILABLE = True
try:
    # Attempt to resolve fixture from the repo-level conftest — if Phase 2
    # hasn't landed, this import fails and we mark every test as skipped.
    import importlib.util

    _spec = importlib.util.find_spec("tests.integration.conftest")
    if _spec is None:
        _BOOTSTRAP_AVAILABLE = False
except Exception:
    _BOOTSTRAP_AVAILABLE = False

pytestmark.append(
    pytest.mark.skipif(
        not _BOOTSTRAP_AVAILABLE,
        reason="Phase 2 bootstrap_stack fixture not available",
    )
)


def _seed_synthetic_klines(timescaledb_container_name: str = "crypto-bot-timescaledb"):
    """Insert ~60K rows of synthetic SOL 5m klines so D-07 floor is met."""
    sql = textwrap.dedent("""
        INSERT INTO klines (timestamp, symbol, interval, open, high, low, close, volume, is_mainnet)
        SELECT
            generate_series('2026-01-01'::timestamp, '2026-05-01'::timestamp, '5 minutes'::interval),
            'SOLUSDT', '5m',
            100 + (random() * 5),
            100 + (random() * 5) + 1,
            100 + (random() * 5) - 1,
            100 + (random() * 5),
            1000,
            true
        ON CONFLICT DO NOTHING;
    """).strip()
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            timescaledb_container_name,
            "psql",
            "-U",
            "postgres",
            "-d",
            "trading_bot",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
    )


def _apply_tournament_reader_migration():
    """Apply infrastructure/migrations/005_tournament_reader.sql to the running DB."""
    repo_root = Path(__file__).resolve().parents[3]
    migration = (
        repo_root / "infrastructure" / "migrations" / "005_tournament_reader.sql"
    )
    if not migration.exists():
        pytest.skip("infrastructure/migrations/005_tournament_reader.sql missing")
    with open(migration) as f:
        sql = f.read()
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "crypto-bot-timescaledb",
            "psql",
            "-U",
            "postgres",
            "-d",
            "trading_bot",
            "-c",
            sql,
        ],
        check=True,
        capture_output=True,
    )
    # Rotate password from placeholder
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "crypto-bot-timescaledb",
            "psql",
            "-U",
            "postgres",
            "-d",
            "trading_bot",
            "-c",
            "ALTER ROLE tournament_reader PASSWORD 'tournament_test_pwd';",
        ],
        check=True,
        capture_output=True,
    )


def test_one_cell_tournament_against_real_timescaledb(tmp_path, bootstrap_stack):
    """End-to-end smoke: real DB, real Docker SDK, real runner image, 1 cell."""
    _apply_tournament_reader_migration()
    _seed_synthetic_klines()

    yaml_text = textwrap.dedent("""
        tournament_id: "e2e_smoke_1cell"
        seed: 42
        symbols: ["SOLUSDT"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        max_experiments: 1
        default_resource_caps:
          mem_limit: "2g"
          cpus: 1.0
          wallclock_timeout_seconds: 300
        architectures:
          gru:
            units: [[16]]
            dropout: [0.1]
            lr: [0.001]
            batch: [32]
            lookback: [10]
            horizon: [5]
    """).strip()
    yaml_path = tmp_path / "tournament.yaml"
    yaml_path.write_text(yaml_text)

    # Copy yaml into the container
    subprocess.run(
        [
            "docker",
            "cp",
            str(yaml_path),
            "crypto-bot-tournament-harness:/tmp/tournament.yaml",
        ],
        check=True,
    )

    # Run via CLI inside the tournament-harness container
    # (assumes bootstrap_stack has the --profile tournament service up)
    cli_cmd = [
        "docker",
        "exec",
        "-e",
        "TIMESCALE_PASSWORD=tournament_test_pwd",
        "-e",
        "GIT_SHA=test_sha",
        "-e",
        f"TS_START={datetime.now(timezone.utc).isoformat()}",
        "crypto-bot-tournament-harness",
        "python",
        "-m",
        "app.cli",
        "run",
        "/tmp/tournament.yaml",
        "--allow-dirty",
    ]
    result = subprocess.run(cli_cmd, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, (
        f"tournament run exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )

    summary = json.loads(result.stdout)
    assert summary["n_total"] == 1
    assert summary["n_success"] + summary["n_failed"] == 1

    # export-snapshot smoke
    snap_cmd = [
        "docker",
        "exec",
        "crypto-bot-tournament-harness",
        "python",
        "-m",
        "app.cli",
        "export-snapshot",
        "e2e_smoke_1cell",
    ]
    snap_result = subprocess.run(snap_cmd, capture_output=True, text=True)
    assert snap_result.returncode == 0
    snap_data = json.loads(snap_result.stdout)
    assert snap_data["n_rows"] == 1
