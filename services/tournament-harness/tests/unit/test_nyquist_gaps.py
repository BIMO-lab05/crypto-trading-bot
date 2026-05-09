"""Nyquist gap-fill tests — Phase 03 tournament-harness-core.

Covers four behavioral requirements that the existing test suite checks only
via static evidence (source grep, schema existence) rather than runtime
assertion:

  GAP-1: TOURN-02 composite PK uniqueness — INSERT of duplicate row raises
          IntegrityError (schema declares the PK, no prior test forces a
          violation).

  GAP-2: D-08 contamination flag — load_klines_from_timescale sets
          train_window_includes_contaminated=True when the 12-month window
          reaches before 2026-04-25 (the testnet-flip date).

  GAP-3: D-07 50K row floor — load_klines_from_timescale raises ValueError
          when the returned row count is below MIN_ROWS_FLOOR.

  GAP-4: D-04 resource caps propagation — launch_one_experiment passes
          mem_limit and nano_cpus from the experiment spec to docker
          containers.run() (existing tests only checked read_only, cap_drop,
          network).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@contextmanager
def _mock_psycopg2_and_read_sql(df_to_return):
    """Context manager that:
    1. Injects a mock psycopg2 into sys.modules so the lazy `import psycopg2`
       inside load_klines_from_timescale resolves without a real DB.
    2. Patches pd.read_sql (via app.runner.data.pd) to return df_to_return.

    psycopg2 is imported lazily inside the function body — there is no
    module-level attribute to patch. sys.modules injection is the correct
    approach for lazily-imported dependencies.
    """
    mock_psycopg2 = MagicMock()
    mock_conn = MagicMock()
    mock_psycopg2.connect.return_value = mock_conn
    mock_psycopg2.OperationalError = Exception  # so the except clause is type-valid

    prev = sys.modules.get("psycopg2")
    sys.modules["psycopg2"] = mock_psycopg2
    try:
        with patch("app.runner.data.pd") as mock_pd:
            mock_pd.read_sql.return_value = df_to_return
            yield
    finally:
        if prev is None:
            sys.modules.pop("psycopg2", None)
        else:
            sys.modules["psycopg2"] = prev


# --------------------------------------------------------------------------- #
# Helpers / shared paths
# --------------------------------------------------------------------------- #

_SERVICE_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = _SERVICE_ROOT / "migrations"


def _make_db(tmp_path):
    from app.leaderboard.db import run_migrations, LeaderboardDB

    db_path = tmp_path / "lb.db"
    run_migrations(db_path, MIGRATIONS_DIR)
    db = LeaderboardDB(db_path)
    db.upsert_tournament("t1", "config\n", "abc", 42)
    return db, db_path


def _success_payload(**overrides):
    base = {
        "status": "success",
        "run_id": "r1",
        "tournament_id": "t1",
        "architecture": "gru",
        "symbol": "SOLUSDT",
        "horizon": 5,
        "target_mode": "log_returns",
        "hp_hash": "deadbeef",
        "git_sha": "abc123",
        "tournament_start_ts": "2026-05-08T00:00:00",
        "train_window_includes_contaminated": 0,
        "metrics": {
            "r2_returns": 0.05,
            "dir_acc_corrected": 0.55,
            "oos_sharpe": 0.8,
            "psr": 0.7,
            "dsr": 0.55,
            "cpcv_dsr": 0.5,
            "train_seconds": 120.0,
        },
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# GAP-1: TOURN-02 — composite PK uniqueness enforced at the DB layer
# --------------------------------------------------------------------------- #


def test_tourn02_duplicate_pk_raises_integrity_error(tmp_path):
    """Inserting a second row with the same composite PK must raise IntegrityError.

    TOURN-02 requires the leaderboard to be indexed by
    (architecture, symbol, horizon, target_mode, hp_hash, run_id).
    The schema declares PRIMARY KEY; this test proves it is actually enforced —
    not just declared in DDL comments.
    """
    from app.leaderboard.result_schema import validate

    db, _ = _make_db(tmp_path)

    # Build and insert first row
    payload = _success_payload()
    raw = json.dumps(payload).encode()
    _, norm = validate(payload, raw)
    db.insert_run(norm)

    # Second insert with IDENTICAL (architecture, symbol, horizon, target_mode, hp_hash, run_id)
    # must violate the PRIMARY KEY constraint.
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_run(norm)

    db.close()


def test_tourn02_different_hp_hash_allows_two_rows(tmp_path):
    """Two cells that differ only in hp_hash are distinct PK rows — both must be accepted."""
    from app.leaderboard.result_schema import validate

    db, _ = _make_db(tmp_path)

    p1 = _success_payload(run_id="run_aaa", hp_hash="aaa00000")
    p2 = _success_payload(run_id="run_bbb", hp_hash="bbb11111")
    for p in (p1, p2):
        raw = json.dumps(p).encode()
        _, norm = validate(p, raw)
        db.insert_run(norm)

    rows = db.list_runs(tournament_id="t1")
    assert len(rows) == 2, (
        "Two rows with distinct hp_hash must both persist (TOURN-02 PK includes hp_hash)"
    )
    db.close()


# --------------------------------------------------------------------------- #
# GAP-2: D-08 — contamination flag set when window reaches before 2026-04-25
# --------------------------------------------------------------------------- #


def test_d08_contamination_flag_set_when_window_predates_cutoff():
    """train_window_includes_contaminated must be True when tournament_start_ts - 365d
    falls before 2026-04-25 (CONTAMINATION_CUTOFF in data.py).

    The 12-month lookback window starting today-ish (2026-05) reaches back to
    ~2025-05, which is well before the testnet-flip date. The runner must stamp
    contaminated=True on every row for that tournament.
    """
    from app.runner.data import load_klines_from_timescale, MIN_ROWS_FLOOR

    import pandas as pd
    import numpy as np

    # end_ts just after the cutoff but 365d window reaches before it:
    # start_ts = 2025-10-25 < CONTAMINATION_CUTOFF (2026-04-25)
    end_ts = datetime(2026, 10, 25)

    rng = np.random.default_rng(0)
    n = MIN_ROWS_FLOOR + 1000
    df_fake = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-10-25", periods=n, freq="5min"),
            "open": rng.uniform(90, 110, n),
            "high": rng.uniform(110, 120, n),
            "low": rng.uniform(80, 90, n),
            "close": rng.uniform(90, 110, n),
            "volume": rng.uniform(100, 1000, n),
        }
    )

    with _mock_psycopg2_and_read_sql(df_fake):
        _, contaminated = load_klines_from_timescale(
            symbol="SOLUSDT",
            interval="5m",
            end_ts=end_ts,
            days_back=365,
        )

    assert contaminated is True, (
        "D-08: window starting before 2026-04-25 must yield contaminated=True"
    )


def test_d08_contamination_flag_false_when_window_clear():
    """Window entirely after 2026-04-25 must yield contaminated=False."""
    from app.runner.data import load_klines_from_timescale, MIN_ROWS_FLOOR

    import pandas as pd
    import numpy as np

    # end_ts = 2027-10-01 → start_ts = 2026-10-01 > CONTAMINATION_CUTOFF
    end_ts = datetime(2027, 10, 1)

    rng = np.random.default_rng(1)
    n = MIN_ROWS_FLOOR + 500
    df_fake = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-10-01", periods=n, freq="5min"),
            "open": rng.uniform(90, 110, n),
            "high": rng.uniform(110, 120, n),
            "low": rng.uniform(80, 90, n),
            "close": rng.uniform(90, 110, n),
            "volume": rng.uniform(100, 1000, n),
        }
    )

    with _mock_psycopg2_and_read_sql(df_fake):
        _, contaminated = load_klines_from_timescale(
            symbol="SOLUSDT",
            interval="5m",
            end_ts=end_ts,
            days_back=365,
        )

    assert contaminated is False, (
        "D-08: window entirely after 2026-04-25 must yield contaminated=False"
    )


# --------------------------------------------------------------------------- #
# GAP-3: D-07 — 50K row floor raises ValueError, not silently returns
# --------------------------------------------------------------------------- #


def test_d07_50k_row_floor_raises_value_error_on_insufficient_data():
    """load_klines_from_timescale must raise ValueError (not return silently) when
    the DB returns fewer than 50 000 rows for a (symbol, interval) pair.

    D-07: 'tournament refuses to start if any (symbol, interval) pair has fewer
    than 50K rows in window.' In the runner, this is enforced by a ValueError
    that the runner entrypoint catches and converts to failure_reason='db_unreachable'
    or records as failed. The important behavioral assertion is that ValueError is
    raised — not that the runner silently uses 49 999 rows of bad statistics.
    """
    from app.runner.data import load_klines_from_timescale, MIN_ROWS_FLOOR

    import pandas as pd
    import numpy as np

    rng = np.random.default_rng(2)
    # Only 100 rows — far below 50 000
    n = 100
    df_too_small = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="5min"),
            "open": rng.uniform(90, 110, n),
            "high": rng.uniform(110, 120, n),
            "low": rng.uniform(80, 90, n),
            "close": rng.uniform(90, 110, n),
            "volume": rng.uniform(100, 1000, n),
        }
    )

    end_ts = datetime(2027, 5, 1)

    with _mock_psycopg2_and_read_sql(df_too_small):
        with pytest.raises(ValueError, match=str(MIN_ROWS_FLOOR)):
            load_klines_from_timescale(
                symbol="SOLUSDT",
                interval="5m",
                end_ts=end_ts,
                days_back=365,
            )


def test_d07_50k_row_floor_boundary_exactly_at_floor():
    """Exactly MIN_ROWS_FLOOR rows must succeed (boundary — one below must fail,
    one at-or-above must not raise).
    """
    from app.runner.data import load_klines_from_timescale, MIN_ROWS_FLOOR

    import pandas as pd
    import numpy as np

    rng = np.random.default_rng(3)
    n = MIN_ROWS_FLOOR  # exactly at floor
    df_exact = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01", periods=n, freq="5min"),
            "open": rng.uniform(90, 110, n),
            "high": rng.uniform(110, 120, n),
            "low": rng.uniform(80, 90, n),
            "close": rng.uniform(90, 110, n),
            "volume": rng.uniform(100, 1000, n),
        }
    )

    # end_ts far enough that start_ts > 2026-04-25 (clean window)
    end_ts = datetime(2027, 7, 1)

    with _mock_psycopg2_and_read_sql(df_exact):
        # Must not raise
        df_out, _ = load_klines_from_timescale(
            symbol="SOLUSDT",
            interval="5m",
            end_ts=end_ts,
            days_back=365,
        )

    assert len(df_out) == MIN_ROWS_FLOOR


# --------------------------------------------------------------------------- #
# GAP-4: D-04 — resource caps (mem_limit, nano_cpus) propagated from spec
# --------------------------------------------------------------------------- #


def test_d04_mem_limit_from_spec_passed_to_docker_run(tmp_path, monkeypatch):
    """launch_one_experiment must translate spec.resource_caps['mem_limit'] into
    the docker containers.run() call's mem_limit kwarg.

    The existing integration test checks read_only, cap_drop, and network but
    does NOT verify mem_limit or nano_cpus — so a regression that hardcodes
    '4g' regardless of the spec would slip through.
    """
    from app.orchestrator.launcher import launch_one_experiment
    from app.config.tournament_loader import ExperimentSpec

    # Build a spec with a non-default mem_limit (8g, as Transformer uses)
    spec = ExperimentSpec(
        tournament_id="gap4_test",
        run_id="gru_SOLUSDT_5m_log_returns_aabbccdd",
        architecture="gru",
        symbol="SOLUSDT",
        interval="5m",
        horizon=5,
        target_mode="log_returns",
        hp={
            "units": [32],
            "dropout": 0.1,
            "lr": 0.001,
            "batch": 32,
            "lookback": 10,
            "horizon": 5,
        },
        hp_hash="aabbccdd",
        experiment_seed=12345,
        resource_caps={
            "mem_limit": "8g",  # non-default — test that this flows through
            "cpus": 3.0,  # non-default nano_cpus = 3_000_000_000
            "wallclock_timeout_seconds": 60,
        },
    )

    # Settings stub
    settings_stub = MagicMock()
    settings_stub.runner_image = "crypto-bot-tournament-harness:latest"
    settings_stub.docker_network = "crypto-bot-network"
    settings_stub.timescale_host = "timescaledb"
    settings_stub.timescale_port = 5432
    settings_stub.timescale_db = "trading_bot"
    settings_stub.timescale_user = "tournament_reader"
    settings_stub.timescale_password = "test_pw"

    fake_client = MagicMock()
    container = MagicMock()
    container.wait = MagicMock(return_value={"StatusCode": 0, "Error": None})
    container.logs = MagicMock(return_value=b"")
    container.kill = MagicMock()
    container.remove = MagicMock()
    container.reload = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {"OOMKilled": False, "ExitCode": 0}}
    fake_client.containers.run = MagicMock(return_value=container)

    output_root = tmp_path / "results"

    launch_one_experiment(
        docker_client=fake_client,
        spec=spec,
        settings=settings_stub,
        output_root=output_root,
        env_extra={},
    )

    fake_client.containers.run.assert_called_once()
    call_kwargs = fake_client.containers.run.call_args.kwargs

    # D-04: mem_limit must come from the spec, not be hardcoded
    assert call_kwargs.get("mem_limit") == "8g", (
        f"D-04: mem_limit must be '8g' from spec.resource_caps, got {call_kwargs.get('mem_limit')!r}"
    )

    # D-04: nano_cpus must be 3.0 * 1e9 = 3_000_000_000
    assert call_kwargs.get("nano_cpus") == 3_000_000_000, (
        f"D-04: nano_cpus must be 3_000_000_000 (3.0 CPUs from spec), got {call_kwargs.get('nano_cpus')!r}"
    )


def test_d04_default_mem_limit_when_no_override(tmp_path):
    """When resource_caps uses the default mem_limit='4g', Docker must receive '4g'."""
    from app.orchestrator.launcher import launch_one_experiment
    from app.config.tournament_loader import ExperimentSpec

    spec = ExperimentSpec(
        tournament_id="gap4_default",
        run_id="gru_SOLUSDT_5m_log_returns_default00",
        architecture="gru",
        symbol="SOLUSDT",
        interval="5m",
        horizon=5,
        target_mode="log_returns",
        hp={
            "units": [32],
            "dropout": 0.1,
            "lr": 0.001,
            "batch": 32,
            "lookback": 10,
            "horizon": 5,
        },
        hp_hash="default00",
        experiment_seed=99,
        resource_caps={
            "mem_limit": "4g",  # default
            "cpus": 2.0,
            "wallclock_timeout_seconds": 60,
        },
    )

    settings_stub = MagicMock()
    settings_stub.runner_image = "crypto-bot-tournament-harness:latest"
    settings_stub.docker_network = "crypto-bot-network"
    settings_stub.timescale_host = "timescaledb"
    settings_stub.timescale_port = 5432
    settings_stub.timescale_db = "trading_bot"
    settings_stub.timescale_user = "tournament_reader"
    settings_stub.timescale_password = "test_pw"

    fake_client = MagicMock()
    container = MagicMock()
    container.wait = MagicMock(return_value={"StatusCode": 0, "Error": None})
    container.logs = MagicMock(return_value=b"")
    container.kill = MagicMock()
    container.remove = MagicMock()
    container.reload = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {"OOMKilled": False, "ExitCode": 0}}
    fake_client.containers.run = MagicMock(return_value=container)

    launch_one_experiment(
        docker_client=fake_client,
        spec=spec,
        settings=settings_stub,
        output_root=tmp_path / "results",
        env_extra={},
    )

    call_kwargs = fake_client.containers.run.call_args.kwargs
    assert call_kwargs.get("mem_limit") == "4g"
    assert call_kwargs.get("nano_cpus") == 2_000_000_000
