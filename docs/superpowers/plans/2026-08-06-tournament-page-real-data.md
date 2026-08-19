# Tournament Page Real Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `http://localhost:3000/tournament` render a real leaderboard by fixing the seven defects that block the first real tournament run, backfilling real Bybit mainnet 5m candles, and running a 6-experiment GRU tournament through the designed pipeline (orchestrator → Docker runner containers → leaderboard SQLite → snapshot JSON → gateway → page).

**Architecture:** The page reads committed snapshot JSON files served by api-gateway from a RO bind-mount of `services/tournament-harness/data/snapshots/`. Nothing renders until a tournament runs and exports a snapshot. The harness orchestrator (in-container, docker.sock) launches one runner container per experiment; the runner trains a real GRU on TimescaleDB klines and writes `result.json`; the orchestrator ingests it into leaderboard SQLite; `export-snapshot` writes the JSON the gateway serves.

**Tech Stack:** Python 3.11 (harness container) / 3.12 (host), FastAPI, docker SDK, psycopg2, pandas, TensorFlow 2.15 (CPU), pytest, React 18 frontend (no frontend changes expected).

**Spec:** `docs/superpowers/specs/2026-08-06-tournament-page-real-data-design.md`

## Global Constraints

- Paper-trading repo; this plan touches NO money code. Account size is $100 — irrelevant here but never write account-size literals anywhere.
- Always pass `--no-cov` to pytest (`.claude/rules/testing.md`). Root `pytest.ini` sets `--strict-markers --strict-config` and `-p no:warnings` (warnings plugin disabled — its `filterwarnings` section is inert; do not add warning suppressions to new tests).
- Harness unit tests run on host from `services/tournament-harness/`: `python3 -m pytest tests/unit/ --no-cov -q`. No env vars needed. Never run bare `pytest` from repo root (collects all services).
- WSL2 Docker gotchas: use `DOCKER_BUILDKIT=0` for builds; docker context must be `default`.
- Compose file is `docker-compose.unified.yml` (plain `docker-compose.yml` is incomplete).
- Work happens on current branch `fix/audit-phase1`. Commit ONLY files this plan touches — the branch has unrelated uncommitted changes (`.planning/`, `backtesting/killtests/`, etc.). Never `git add -A`.
- All compose commands run from repo root `/mnt/d/Bimo_max/crypto-trading-bot` (RESULTS_HOST_DIR uses `${PWD}` substitution).
- Nothing fake: no hand-written snapshots, no synthetic klines in the DB, no mocked metrics in the final artifact. Mocks are allowed only inside unit tests.

## Defect inventory (all verified against code/live system 2026-08-06)

| # | Defect | Location | Symptom |
|---|--------|----------|---------|
| 1 | Bind-mount source is a container path; dockerd resolves it on the HOST | `launcher.py:110` (`volumes={str(run_output): ...}` where `run_output=/app/data/results/...`) | Runner writes result.json to wrong host dir (root-owned `/app/...` in WSL VM); orchestrator reads empty → every run `failed/unknown`; runner also hits PermissionError |
| 2 | `docker==7.0.0` + `requests 2.34.0` incompatible | harness image (verified live: `docker.from_env()` → `Not supported URL scheme http+docker`) | Orchestrator crashes before launching anything |
| 3 | tz-aware `TS_START` vs naive `CONTAMINATION_CUTOFF` | `data.py:15,59` (launcher sends `datetime.now(timezone.utc).isoformat()`) | `TypeError: can't compare offset-naive and offset-aware datetimes` → every run `exit_nonzero` |
| 4 | SQL binds datetimes against bigint ms-epoch column | `data.py:61-76` | `operator does not exist: bigint >= timestamp` → every run fails |
| 5 | Interval `"5m"` vs DB convention `"5"` | YAML + `data.py` (no mapping layer) | Zero rows → 50K floor → `train_diverged` |
| 6 | `RUNNER_IMAGE=crypto-bot-tournament-harness:latest` doesn't exist (built name is `crypto-trading-bot-tournament-harness:latest`) | `settings.py:47`, `docker-compose.unified.yml:900` | ImageNotFound on every launch |
| 7 | 5m data too thin: ~6.5K patchy rows/symbol vs `MIN_ROWS_FLOOR=50_000` | TimescaleDB `klines` | `train_diverged` even after fixes 3-5 |

Minor (fixed opportunistically): `timescale_db` code default `trading_bot` (DB doesn't exist; compose env saves it today); `_git_sha()` always `"unknown"` in-container (no `.git` in image).

---

### Task 1: Fix `app/runner/data.py` — interval map, ms-epoch params, tz-aware cutoff

**Files:**
- Modify: `services/tournament-harness/app/runner/data.py`
- Test: `services/tournament-harness/tests/unit/test_runner_data.py` (new)

**Interfaces:**
- Produces: `load_klines_from_timescale(symbol: str, interval: str, end_ts: datetime, days_back: int = 365) -> Tuple[pd.DataFrame, bool]` — signature UNCHANGED (callers `app/runner/__main__.py`, `app/runner/predict_fn.py` untouched). New module-level: `INTERVAL_TO_DB: dict[str, str]`, `_interval_to_db(interval: str) -> str`, `_to_utc(dt: datetime) -> datetime`. `CONTAMINATION_CUTOFF` becomes tz-aware UTC.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Baseline — existing tests referencing this module must pass before we touch it**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_nyquist_gaps.py tests/unit/test_runner_predict_fn.py --no-cov -q`
Expected: PASS (record the count). If already failing, STOP and report — do not build on a broken baseline.

- [ ] **Step 2: Write the failing tests**

Create `services/tournament-harness/tests/unit/test_runner_data.py`:

```python
"""Unit tests for app/runner/data.py loader fixes (2026-08-06):

- interval mapping "5m" -> "5" at the SQL boundary (DB stores Bybit convention)
- BETWEEN params sent as ms-epoch ints (klines.timestamp is bigint ms)
- tz-aware end_ts (launcher sends aware ISO TS_START) must not TypeError
  against CONTAMINATION_CUTOFF
"""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.runner.data import (
    CONTAMINATION_CUTOFF,
    MIN_ROWS_FLOOR,
    _interval_to_db,
    _to_utc,
    load_klines_from_timescale,
)


# ---------- _interval_to_db ----------

@pytest.mark.parametrize(
    "human,db",
    [("1m", "1"), ("5m", "5"), ("15m", "15"), ("1h", "60"), ("4h", "240"), ("1d", "D")],
)
def test_interval_map_human_to_db(human, db):
    assert _interval_to_db(human) == db


@pytest.mark.parametrize("already_db", ["1", "5", "15", "60", "240", "D"])
def test_interval_map_passthrough_db_convention(already_db):
    assert _interval_to_db(already_db) == already_db


def test_interval_map_unknown_raises():
    with pytest.raises(ValueError, match="unknown interval"):
        _interval_to_db("7m")


# ---------- _to_utc ----------

def test_to_utc_naive_assumed_utc():
    dt = datetime(2026, 8, 6, 12, 0, 0)
    out = _to_utc(dt)
    assert out.tzinfo == timezone.utc
    assert out.replace(tzinfo=None) == dt


def test_to_utc_aware_converted():
    aware = datetime.fromisoformat("2026-08-06T12:00:00+00:00")
    assert _to_utc(aware) == aware


def test_contamination_cutoff_is_aware():
    assert CONTAMINATION_CUTOFF.tzinfo is not None


# ---------- load_klines_from_timescale ----------

def _run_loader(end_ts, days_back=365, n_rows=60_000, interval="5m"):
    """Drive the loader with psycopg2 + pandas stubbed out; return (result, read_sql call)."""
    fake_psycopg2 = MagicMock()
    fake_conn = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn
    fake_psycopg2.OperationalError = Exception

    fake_df = MagicMock()
    fake_df.__len__.return_value = n_rows

    with patch.dict(sys.modules, {"psycopg2": fake_psycopg2}):
        with patch("app.runner.data.pd") as fake_pd:
            fake_pd.read_sql.return_value = fake_df
            result = load_klines_from_timescale(
                "SOLUSDT", interval, end_ts, days_back=days_back
            )
            call = fake_pd.read_sql.call_args
    return result, call


def test_loader_sends_ms_epoch_ints_and_db_interval():
    end_ts = datetime.fromisoformat("2026-08-06T00:00:00+00:00")  # aware, like TS_START
    (_df, contaminated), call = _run_loader(end_ts)
    params = call.kwargs["params"]
    symbol, interval, start_ms, end_ms = params
    assert symbol == "SOLUSDT"
    assert interval == "5"                      # mapped, not "5m"
    assert isinstance(start_ms, int) and isinstance(end_ms, int)
    assert end_ms == int(end_ts.timestamp() * 1000)
    assert end_ms - start_ms == 365 * 86_400 * 1000
    assert contaminated is True                  # 365d back crosses 2026-04-25


def test_loader_aware_end_ts_no_typeerror():
    # Regression: launcher sends datetime.now(timezone.utc).isoformat();
    # naive CONTAMINATION_CUTOFF used to raise TypeError before any SQL.
    end_ts = datetime.now(timezone.utc)
    (_df, contaminated), _call = _run_loader(end_ts, days_back=1)
    assert contaminated is False                 # 1-day window is post-cutoff


def test_loader_naive_end_ts_still_works():
    end_ts = datetime(2026, 8, 6, 0, 0, 0)      # naive — assumed UTC
    (_df, _c), call = _run_loader(end_ts)
    assert call.kwargs["params"][3] == int(
        end_ts.replace(tzinfo=timezone.utc).timestamp() * 1000
    )


def test_loader_floor_still_enforced():
    end_ts = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="insufficient klines"):
        _run_loader(end_ts, n_rows=MIN_ROWS_FLOOR - 1)


def test_loader_sql_keeps_mainnet_filter():
    # B1 regression guard (mirrors tests/integration/test_klines_filter_required.py)
    end_ts = datetime.now(timezone.utc)
    (_r, _c), call = _run_loader(end_ts)
    sql = call.args[0]
    assert "is_mainnet = TRUE" in sql
```

Note: if `pd.read_sql` in `data.py` ends up called positionally (`pd.read_sql(sql, conn, params=...)`), `call.args[0]` is the SQL and `call.kwargs["params"]` the params — the tests above assume exactly that call shape; keep it in the implementation.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_runner_data.py --no-cov -q`
Expected: FAIL — `ImportError: cannot import name '_interval_to_db'`.

- [ ] **Step 4: Implement the fix**

Rewrite `services/tournament-harness/app/runner/data.py` — full new content:

```python
"""Klines loader (TimescaleDB read-only via tournament_reader role, D-09)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# D-08: testnet-flip bug fix landed 2026-04-25; rows before this are mixed-history.
# tz-aware because the launcher's TS_START is datetime.now(timezone.utc).isoformat().
CONTAMINATION_CUTOFF = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
MIN_ROWS_FLOOR = 50_000  # D-07 hard floor

# klines.interval stores Bybit-convention strings ("5", "60", "D") — written by
# market-data-service (scheduler KLINE_INTERVALS). Tournament YAMLs use human
# forms ("5m"). Map at the SQL boundary only; run_id/hp_hash keep the YAML form.
INTERVAL_TO_DB = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W", "1M": "M",
}
_DB_INTERVALS = frozenset(INTERVAL_TO_DB.values())


def _interval_to_db(interval: str) -> str:
    if interval in _DB_INTERVALS:
        return interval
    try:
        return INTERVAL_TO_DB[interval]
    except KeyError:
        raise ValueError(
            f"unknown interval {interval!r}; expected one of "
            f"{sorted(INTERVAL_TO_DB)} or DB-convention {sorted(_DB_INTERVALS)}"
        ) from None


def _to_utc(dt: datetime) -> datetime:
    """Naive datetimes are assumed UTC (all pipeline timestamps are UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _build_dsn() -> str:
    """Construct DSN from env (set by orchestrator on the experiment container)."""
    user = os.environ.get("TIMESCALE_USER", "tournament_reader")
    pwd = os.environ.get("TIMESCALE_PASSWORD", "")
    host = os.environ.get("TIMESCALE_HOST", "timescaledb")
    port = os.environ.get("TIMESCALE_PORT", "5432")
    db = os.environ.get("TIMESCALE_DB", "market_data")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def load_klines_from_timescale(
    symbol: str,
    interval: str,
    end_ts: datetime,
    days_back: int = 365,
) -> Tuple[pd.DataFrame, bool]:
    """Fetch is_mainnet klines for (symbol, interval) over [end_ts - days_back, end_ts].

    Returns (df, train_window_includes_contaminated).
    Raises:
        ConnectionError: DB unreachable (caller writes failure result.json with reason='db_unreachable')
        ValueError: row count below MIN_ROWS_FLOOR, or unknown interval

    Note: `symbol` must be Bybit-convention quote-pair form (e.g. 'SOLUSDT'),
    NOT bare base ('SOL'). market-data-service writes klines.symbol in the
    USDT-suffixed form; bare base symbols would silently miss every row and
    trip the 50K floor on every cell. tournament_loader enforces this at YAML
    parse time (SYMBOL_RE), but the runner double-checks because experiment
    containers are isolated and a stale spec-json could slip through.

    klines.timestamp is a bigint in Unix MILLISECONDS — bind ints, never
    datetimes (Postgres has no bigint<->timestamp comparison operator).
    """
    assert symbol.endswith("USDT"), (
        f"Tournament symbols must be Bybit-convention quote-pair form, got {symbol!r}"
    )

    import psycopg2  # imported lazily — error gets caught more cleanly than at module import

    db_interval = _interval_to_db(interval)
    end_utc = _to_utc(end_ts)
    start_utc = end_utc - timedelta(days=days_back)
    contaminated = start_utc < CONTAMINATION_CUTOFF
    start_ms = int(start_utc.timestamp() * 1000)
    end_ms = int(end_utc.timestamp() * 1000)

    sql = """
        SELECT timestamp, open, high, low, close, volume
        FROM klines
        WHERE symbol = %s
          AND interval = %s
          AND is_mainnet = TRUE
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
    """
    try:
        conn = psycopg2.connect(_build_dsn())
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"timescaledb unreachable: {e}") from e

    try:
        df = pd.read_sql(sql, conn, params=(symbol, db_interval, start_ms, end_ms))
    finally:
        conn.close()

    n = len(df)
    logger.info(
        "loaded %d klines for %s/%s (db interval %s) in [%s, %s]; contaminated=%s",
        n, symbol, interval, db_interval, start_utc, end_utc, contaminated,
    )
    if n < MIN_ROWS_FLOOR:
        raise ValueError(
            f"insufficient klines: {n} rows < {MIN_ROWS_FLOOR} floor "
            f"({symbol}/{interval} in window {start_utc}..{end_utc})"
        )
    return df, contaminated
```

(Changes vs old: tz-aware cutoff; `_interval_to_db`; `_to_utc`; ms-epoch params; `_build_dsn` db default `market_data` instead of nonexistent `trading_bot`; mainnet filter and floor unchanged.)

- [ ] **Step 5: Run new tests — verify pass**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_runner_data.py --no-cov -q`
Expected: PASS — 21 items (11 test functions; the two interval-map tests are 6-way parametrized).

- [ ] **Step 6: Run neighboring tests — no regressions**

Run: `python3 -m pytest tests/unit/test_nyquist_gaps.py tests/unit/test_runner_predict_fn.py tests/integration/test_klines_filter_required.py --no-cov -q`
Expected: same pass count as Step 1 baseline. If `test_nyquist_gaps.py` asserts on old datetime params, update ONLY those assertions to the ms-epoch ints and note it in the commit message.

- [ ] **Step 7: Commit**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
git add services/tournament-harness/app/runner/data.py services/tournament-harness/tests/unit/test_runner_data.py
git commit -m "fix(tournament-harness): kline loader — ms-epoch params, interval map, tz-aware cutoff

klines.timestamp is bigint ms; binding datetimes raised
'operator does not exist: bigint >= timestamp' on every experiment.
YAML intervals are human-form ('5m') but the DB stores Bybit convention
('5') — mapped at the SQL boundary. CONTAMINATION_CUTOFF is now tz-aware
because the launcher's TS_START is an aware UTC ISO string (comparing it
against a naive cutoff raised TypeError before any SQL ran)."
```

---

### Task 2: Fix launcher host-path bind mount + settings + compose env

**Files:**
- Modify: `services/tournament-harness/app/config/settings.py`
- Modify: `services/tournament-harness/app/orchestrator/launcher.py`
- Modify: `docker-compose.unified.yml` (tournament-harness environment block, ~line 890-900)
- Test: `services/tournament-harness/tests/unit/test_launcher_volume_path.py` (new)

**Interfaces:**
- Produces: `TournamentSettings.results_host_dir: str` (env `RESULTS_HOST_DIR`, default `""`); `launch_one_experiment(..., host_output_root: Path | None = None)` — new optional kwarg, bind-mount source becomes `host_output_root/<tid>/<rid>` when provided; `run_tournament` raises `RuntimeError` when `settings.results_host_dir` is empty. `runner_image` default becomes `crypto-trading-bot-tournament-harness:latest`; `timescale_db` default becomes `market_data`.
- Consumes: nothing from Task 1 (independent).

Why: the Docker daemon resolves bind-mount **sources on the host**. The launcher currently passes its own container path (`/app/data/results/...`) as the source, so the runner's `/output` points at a dockerd-created root-owned dir in the WSL VM — not at `./services/tournament-harness/data/results/` where the orchestrator reads `result.json`. Every exit-0 run would ingest as `failed/unknown`.

- [ ] **Step 1: Write the failing tests**

First read `services/tournament-harness/tests/integration/test_orchestrator_with_fake_docker.py` and `tests/conftest.py` to confirm the `fake_docker_client` fixture shape (MagicMock with `.containers.run` returning a container mock with `.wait/.logs/.reload/.remove/.attrs`). Then create `services/tournament-harness/tests/unit/test_launcher_volume_path.py`:

```python
"""launch_one_experiment must bind-mount the HOST results path, not the
container path — dockerd resolves bind sources on the host (2026-08-06 fix)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config.tournament_loader import ExperimentSpec
from app.orchestrator.launcher import launch_one_experiment


def _spec():
    return ExperimentSpec(
        tournament_id="t1",
        run_id="gru_SOLUSDT_5m_log_returns_abc123",
        architecture="gru",
        symbol="SOLUSDT",
        interval="5m",
        horizon=5,
        target_mode="log_returns",
        hp={"units": [64], "dropout": 0.2, "lr": 0.001, "batch": 64,
            "lookback": 60, "horizon": 5},
        hp_hash="abc123",
        experiment_seed=1,
        resource_caps={"mem_limit": "1g", "cpus": 1.0,
                       "wallclock_timeout_seconds": 5},
    )


def _fake_docker():
    client = MagicMock()
    container = MagicMock()
    container.wait.return_value = {"StatusCode": 0}
    container.attrs = {"State": {"ExitCode": 0, "OOMKilled": False}}
    container.logs.return_value = b""
    client.containers.run.return_value = container
    return client


def _fake_settings(tmp_path):
    s = MagicMock()
    s.runner_image = "crypto-trading-bot-tournament-harness:latest"
    s.docker_network = "crypto-bot-network"
    s.timescale_host = "timescaledb"
    s.timescale_port = 5432
    s.timescale_db = "market_data"
    s.timescale_user = "tournament_reader"
    s.timescale_password = "pw"
    return s


def test_bind_source_uses_host_root_when_given(tmp_path):
    client = _fake_docker()
    spec = _spec()
    container_root = tmp_path / "container_results"
    host_root = Path("/mnt/d/somewhere/data/results")

    launch_one_experiment(
        docker_client=client,
        spec=spec,
        settings=_fake_settings(tmp_path),
        output_root=container_root,
        env_extra={},
        host_output_root=host_root,
    )

    volumes = client.containers.run.call_args.kwargs["volumes"]
    expected_src = str(host_root / spec.tournament_id / spec.run_id)
    assert volumes == {expected_src: {"bind": "/output", "mode": "rw"}}
    # result.json is still read via the orchestrator's own container path
    # (bind-mounted to the same host dir by compose)
    assert (container_root / spec.tournament_id / spec.run_id).is_dir()


def test_bind_source_falls_back_to_output_root_when_none(tmp_path):
    client = _fake_docker()
    spec = _spec()
    launch_one_experiment(
        docker_client=client,
        spec=spec,
        settings=_fake_settings(tmp_path),
        output_root=tmp_path,
        env_extra={},
        host_output_root=None,
    )
    volumes = client.containers.run.call_args.kwargs["volumes"]
    assert str(tmp_path / spec.tournament_id / spec.run_id) in volumes
```

Adjust `_spec()` field values ONLY if `ExperimentSpec` rejects them (fields verified 2026-08-06: tournament_id, run_id, architecture, symbol, interval, horizon, target_mode, hp, hp_hash, experiment_seed, resource_caps).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_launcher_volume_path.py --no-cov -q`
Expected: FAIL — `TypeError: launch_one_experiment() got an unexpected keyword argument 'host_output_root'`.

- [ ] **Step 3: Implement settings changes**

In `services/tournament-harness/app/config/settings.py`:

Replace:
```python
    timescale_db: str = Field(default="trading_bot")
```
with:
```python
    timescale_db: str = Field(default="market_data")
```

Replace:
```python
    # Image tag for experiment containers (D-05 — same image as orchestrator)
    runner_image: str = Field(default="crypto-bot-tournament-harness:latest")
```
with:
```python
    # Image tag for experiment containers (D-05 — same image as orchestrator).
    # Compose builds it as <project>-tournament-harness; the project directory
    # is crypto-trading-bot, hence the prefix.
    runner_image: str = Field(default="crypto-trading-bot-tournament-harness:latest")

    # HOST-side path of results_dir. The Docker daemon resolves bind-mount
    # sources on the HOST, so the launcher cannot hand it a container path.
    # Compose sets this from ${PWD}; empty means "refuse to launch".
    results_host_dir: str = Field(default="")
```

- [ ] **Step 4: Implement launcher changes**

In `services/tournament-harness/app/orchestrator/launcher.py`:

Change the `launch_one_experiment` signature and volume construction. Replace:
```python
def launch_one_experiment(
    docker_client,
    spec: ExperimentSpec,
    settings,
    output_root: Path,
    env_extra: Dict[str, str],
) -> Dict[str, Any]:
    """Run ONE experiment to completion. Returns container state dict + stderr tail.

    Result.json read + DB insert is the caller's job (caller has the LeaderboardDB).
    """
    run_output = output_root / spec.tournament_id / spec.run_id
    run_output.mkdir(parents=True, exist_ok=True)
```
with:
```python
def launch_one_experiment(
    docker_client,
    spec: ExperimentSpec,
    settings,
    output_root: Path,
    env_extra: Dict[str, str],
    host_output_root: Path | None = None,
) -> Dict[str, Any]:
    """Run ONE experiment to completion. Returns container state dict + stderr tail.

    Result.json read + DB insert is the caller's job (caller has the LeaderboardDB).

    host_output_root: HOST-side path of output_root. The Docker daemon resolves
    bind-mount sources on the host, so the runner's /output must be bound to the
    host path of the run dir — output_root is this process's container path and
    only valid for mkdir/read on our side of the compose bind mount.
    """
    run_output = output_root / spec.tournament_id / spec.run_id
    run_output.mkdir(parents=True, exist_ok=True)
    host_run_output = (host_output_root or output_root) / spec.tournament_id / spec.run_id
```
and replace:
```python
            volumes={str(run_output): {"bind": "/output", "mode": "rw"}},
```
with:
```python
            volumes={str(host_run_output): {"bind": "/output", "mode": "rw"}},
```

In `run_tournament`, after the `TIMESCALE_PASSWORD` guard block, insert:
```python
    if not settings.results_host_dir:
        raise RuntimeError(
            "RESULTS_HOST_DIR is unset. The Docker daemon resolves bind-mount "
            "sources on the HOST, so the launcher needs the host path of the "
            "results dir (compose sets it to "
            "${PWD}/services/tournament-harness/data/results). Refusing to "
            "launch runners whose result.json would land in the wrong place."
        )
```
and replace:
```python
    output_root = Path(settings.results_dir)
```
with:
```python
    output_root = Path(settings.results_dir)
    host_output_root = Path(settings.results_host_dir)
```
and add the kwarg to the call inside the loop — replace:
```python
            outcome = launch_one_experiment(
                docker_client=docker_client,
                spec=exp,
                settings=settings,
                output_root=output_root,
                env_extra=env_extra,
            )
```
with:
```python
            outcome = launch_one_experiment(
                docker_client=docker_client,
                spec=exp,
                settings=settings,
                output_root=output_root,
                env_extra=env_extra,
                host_output_root=host_output_root,
            )
```

- [ ] **Step 5: Implement compose changes**

In `docker-compose.unified.yml`, tournament-harness `environment:` block, replace:
```yaml
      - RUNNER_IMAGE=crypto-bot-tournament-harness:latest
```
with:
```yaml
      # Compose builds the image as <project>-tournament-harness (project dir
      # is crypto-trading-bot). The old crypto-bot-* name never existed.
      - RUNNER_IMAGE=crypto-trading-bot-tournament-harness:latest
      # Host-side path of /app/data/results — dockerd resolves bind-mount
      # sources on the HOST. Requires compose to be invoked from the repo root.
      - RESULTS_HOST_DIR=${PWD}/services/tournament-harness/data/results
```

- [ ] **Step 6: Run tests to verify pass**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_launcher_volume_path.py --no-cov -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Run orchestrator integration tests — adapt if they call run_tournament**

Run: `python3 -m pytest tests/integration/test_orchestrator_with_fake_docker.py --no-cov -q`
If failures are `RuntimeError: RESULTS_HOST_DIR is unset`: in those tests, monkeypatch the settings singleton (`import app.config.settings as settings_mod; monkeypatch.setattr(settings_mod, "_settings", None); monkeypatch.setenv("RESULTS_HOST_DIR", str(tmp_path))`) before calling `run_tournament`, and reset `_settings` to `None` again in teardown so other tests see a fresh singleton. Do NOT weaken the guard.
Expected after adaptation: PASS.

- [ ] **Step 8: Commit**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
git add services/tournament-harness/app/config/settings.py \
        services/tournament-harness/app/orchestrator/launcher.py \
        services/tournament-harness/tests/unit/test_launcher_volume_path.py \
        services/tournament-harness/tests/integration/test_orchestrator_with_fake_docker.py \
        docker-compose.unified.yml
git commit -m "fix(tournament-harness): bind runner /output to HOST results path

The launcher passed its own container path (/app/data/results/...) as the
bind-mount source; dockerd resolves sources on the host, so runner results
landed in a root-owned dir in the WSL VM while the orchestrator read the
(empty) compose bind mount — every exit-0 run ingested as failed/unknown.
New RESULTS_HOST_DIR env (compose: \${PWD}/services/tournament-harness/data/results)
carries the host path; run_tournament refuses to launch without it.
Also: RUNNER_IMAGE default fixed to the image name compose actually builds
(crypto-trading-bot-*, not crypto-bot-*), timescale_db default fixed to
market_data (trading_bot does not exist)."
```

---

### Task 3: Pin docker SDK 7.1.0 + GIT_SHA env override

**Files:**
- Modify: `services/tournament-harness/requirements.txt`
- Modify: `services/tournament-harness/app/orchestrator/launcher.py` (`_git_sha`)
- Test: `services/tournament-harness/tests/unit/test_launcher_git_sha.py` (new)

**Interfaces:**
- Produces: `_git_sha()` prefers env `GIT_SHA` when non-empty. `docker==7.1.0` in requirements.
- Consumes: Task 2's launcher file state (same file — apply after Task 2).

Why: verified live — the current image's `docker.from_env()` throws `Not supported URL scheme http+docker` (docker 7.0.0 is incompatible with requests ≥2.32; image has requests 2.34.0). 7.1.0 fixes it. And `_git_sha()` runs `git rev-parse` in `/app` where no `.git` exists → provenance columns read `"unknown"`; the operator can pass the real sha via env at run time.

- [ ] **Step 1: Write the failing test**

Create `services/tournament-harness/tests/unit/test_launcher_git_sha.py`:

```python
"""_git_sha: GIT_SHA env wins when set (the image has no .git — in-container
git rev-parse always fails and provenance read 'unknown')."""

from app.orchestrator.launcher import _git_sha


def test_git_sha_env_override(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123def456")
    assert _git_sha() == "abc123def456"


def test_git_sha_env_blank_ignored(monkeypatch):
    monkeypatch.setenv("GIT_SHA", "   ")
    # falls through to subprocess path; on a host repo this returns a real
    # 40-char sha, in-container it returns "unknown" — either way not blank
    out = _git_sha()
    assert out.strip() != ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/unit/test_launcher_git_sha.py --no-cov -q`
Expected: `test_git_sha_env_override` FAILS (returns repo sha or "unknown", not "abc123def456").

- [ ] **Step 3: Implement**

In `launcher.py`, replace:
```python
def _git_sha() -> str:
    """git rev-parse HEAD — captured once at tournament start (D-13)."""
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd="/app").strip()
        return out.decode()
    except Exception as e:
        logger.warning("git_sha unavailable: %s", e)
        return "unknown"
```
with:
```python
def _git_sha() -> str:
    """git rev-parse HEAD — captured once at tournament start (D-13).

    The image contains no .git, so in-container the subprocess path always
    returns "unknown". Operators pass the real sha via GIT_SHA env
    (docker exec -e GIT_SHA=$(git rev-parse HEAD) ...).
    """
    env_sha = os.environ.get("GIT_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd="/app").strip()
        return out.decode()
    except Exception as e:
        logger.warning("git_sha unavailable: %s", e)
        return "unknown"
```

In `services/tournament-harness/requirements.txt`, replace the `docker==7.0.0` line with:
```
docker==7.1.0  # 7.0.0 breaks with requests>=2.32 ("Not supported URL scheme http+docker")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest tests/unit/test_launcher_git_sha.py --no-cov -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Full harness unit suite**

Run: `python3 -m pytest tests/unit/ --no-cov -q`
Expected: PASS (all — new + pre-existing).

- [ ] **Step 6: Commit**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
git add services/tournament-harness/requirements.txt \
        services/tournament-harness/app/orchestrator/launcher.py \
        services/tournament-harness/tests/unit/test_launcher_git_sha.py
git commit -m "fix(tournament-harness): docker 7.1.0 pin + GIT_SHA env override

docker==7.0.0 with requests 2.34 (already in the built image) raises
'Not supported URL scheme http+docker' at from_env() — verified live;
the orchestrator could never reach the Docker socket. 7.1.0 fixes it.
_git_sha() now honors a GIT_SHA env override because the image has no
.git and provenance columns always read 'unknown'."
```

---

### Task 4: Backfill script `scripts/backfill_klines_5m.py` + unit tests

**Files:**
- Create: `scripts/backfill_klines_5m.py`
- Test: `tests/test_backfill_klines_5m.py` (repo-root tests/, host-run)

**Interfaces:**
- Produces: pure helpers `kline_rows_to_tuples(rows, symbol, interval_db, interval_ms, created_ms, fetch_time_ms) -> list[tuple]` and `next_page_window(current_end_ms, start_ms, interval_ms, page_limit) -> tuple[int, int]`, plus `main()` CLI. Runs INSIDE `crypto-bot-market-data` (has httpx 0.27.0 + psycopg2; reaches `bybit-connector:8001` and `timescaledb:5432` by service name — verified).
- Consumes: nothing from other tasks (independent of harness fixes).

Facts baked in (verified 2026-08-06): connector `GET /api/v1/market/kline` takes `category, symbol, interval, limit (max 1000), start, end` (ms epoch); expects Bybit convention `interval=5`; response `{"success": true, "data": [[startTimeMs, open, high, low, close, volume, turnover], ...]}` — flat list of 7-string rows, **newest first**, already unwrapped once (never double-unwrap — historical bug); connector rate limit 200/min per IP; klines PK `(timestamp, symbol, interval)`; `created_at` ms epoch; `is_mainnet` set explicitly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_backfill_klines_5m.py`:

```python
"""Unit tests for the pure helpers in scripts/backfill_klines_5m.py.
Network + DB paths are exercised live (docker exec) — not here."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_klines_5m.py"
_spec = importlib.util.spec_from_file_location("backfill_klines_5m", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

INTERVAL_MS = 5 * 60 * 1000


def _row(ts_ms, o="1.0", h="2.0", low="0.5", c="1.5", v="100", t="150"):
    return [str(ts_ms), o, h, low, c, v, t]


def test_rows_to_tuples_drops_forming_bar():
    closed_ts = 1_780_000_000_000
    forming_ts = closed_ts + INTERVAL_MS
    fetch_time = forming_ts + 10_000  # forming bar open only 10s -> not closed
    rows = [_row(forming_ts), _row(closed_ts)]  # newest first, like the API
    out = mod.kline_rows_to_tuples(
        rows, "SOLUSDT", "5", INTERVAL_MS, created_ms=123, fetch_time_ms=fetch_time
    )
    assert len(out) == 1
    assert out[0][0] == closed_ts


def test_rows_to_tuples_shape_and_types():
    ts = 1_780_000_000_000
    out = mod.kline_rows_to_tuples(
        [_row(ts)], "SOLUSDT", "5", INTERVAL_MS,
        created_ms=999, fetch_time_ms=ts + INTERVAL_MS + 1,
    )
    (row,) = out
    # (timestamp, symbol, interval, open, high, low, close, volume,
    #  turnover, created_at, is_mainnet)
    assert row == (ts, "SOLUSDT", "5", 1.0, 2.0, 0.5, 1.5, 100.0, 150.0, 999, True)
    assert isinstance(row[0], int) and isinstance(row[3], float)


def test_rows_to_tuples_null_turnover_ok():
    ts = 1_780_000_000_000
    row = _row(ts)
    row[6] = ""
    out = mod.kline_rows_to_tuples(
        [row], "SOLUSDT", "5", INTERVAL_MS,
        created_ms=1, fetch_time_ms=ts + INTERVAL_MS + 1,
    )
    assert out[0][8] is None


def test_next_page_window_steps_back_and_clamps():
    start = 1_000_000
    page_span = 1000 * INTERVAL_MS
    s, e = mod.next_page_window(start + 5 * page_span, start, INTERVAL_MS, 1000)
    assert e == start + 5 * page_span
    assert s == e - page_span
    # clamp at start
    s2, e2 = mod.next_page_window(start + page_span // 2, start, INTERVAL_MS, 1000)
    assert s2 == start
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot && python3 -m pytest tests/test_backfill_klines_5m.py --no-cov -q`
Expected: FAIL — script file does not exist.

- [ ] **Step 3: Write the script**

Create `scripts/backfill_klines_5m.py`:

```python
"""Backfill 365 days of real Bybit MAINNET 5m klines into TimescaleDB.

Feeds the tournament-harness data floor (MIN_ROWS_FLOOR=50_000; a year of 5m
is ~105K bars/symbol). Fetches via bybit-connector /api/v1/market/kline
(connector selects mainnet via its own BYBIT_TESTNET env) and inserts with
ON CONFLICT DO NOTHING so collector-written rows are never overwritten.

Run inside the market-data container (has httpx + psycopg2, resolves service
names):
    docker cp scripts/backfill_klines_5m.py crypto-bot-market-data:/tmp/
    docker exec crypto-bot-market-data python /tmp/backfill_klines_5m.py

Env: prefers the TIMESCALE_* vars the market-data container exports
(TIMESCALE_HOST/PORT/USER/PASSWORD/DB), falling back to DB_* then to the
same defaults as backfill_klines_from_csv.py. Also BYBIT_CONNECTOR_URL
(default http://bybit-connector:8001), BACKFILL_DAYS (default 365),
BACKFILL_SYMBOLS (comma-separated, default SOLUSDT,BNBUSDT,ADAUSDT).
"""

from __future__ import annotations

import os
import sys
import time

CONNECTOR_URL = os.getenv("BYBIT_CONNECTOR_URL", "http://bybit-connector:8001")
SYMBOLS = [s for s in os.getenv("BACKFILL_SYMBOLS", "SOLUSDT,BNBUSDT,ADAUSDT").split(",") if s]
DAYS = int(os.getenv("BACKFILL_DAYS", "365"))
INTERVAL_DB = "5"            # Bybit convention — what klines.interval stores
INTERVAL_MS = 5 * 60 * 1000
PAGE_LIMIT = 1000            # connector clamps to 1000 server-side
RATE_DELAY_S = 0.2           # 200/min connector limit; ~106 pages/symbol
BATCH_SIZE = 2000
STALENESS_INTERVALS = 3      # abort if newest candle older than this many bars

INSERT_SQL = (
    "INSERT INTO klines "
    "(timestamp, symbol, interval, open, high, low, close, volume, turnover, "
    "created_at, is_mainnet) "
    "VALUES %s "
    "ON CONFLICT (timestamp, symbol, interval) DO NOTHING"
)


def kline_rows_to_tuples(rows, symbol, interval_db, interval_ms, created_ms, fetch_time_ms):
    """Connector rows ([startTimeMs, o, h, l, c, vol, turnover] strings, newest
    first) -> insert tuples. Drops the still-forming bar (close time in the
    future at fetch time) — mirrors market-data fetcher behavior."""
    out = []
    for r in rows:
        ts = int(r[0])
        if ts + interval_ms > fetch_time_ms:
            continue  # forming bar — not closed yet
        turnover = float(r[6]) if len(r) > 6 and r[6] not in ("", None) else None
        out.append(
            (ts, symbol, interval_db,
             float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]),
             turnover, created_ms, True)
        )
    return out


def next_page_window(current_end_ms, start_ms, interval_ms, page_limit):
    """Window covering at most page_limit bars ending at current_end_ms,
    clamped to start_ms."""
    span = page_limit * interval_ms
    return max(start_ms, current_end_ms - span), current_end_ms


def _fetch_page(client, symbol, start_ms, end_ms):
    """One connector page; one retry on transient failure so a single blip
    doesn't silently truncate the backfill."""
    for attempt in (1, 2):
        try:
            resp = client.get(
                f"{CONNECTOR_URL}/api/v1/market/kline",
                params={"category": "linear", "symbol": symbol,
                        "interval": INTERVAL_DB, "limit": PAGE_LIMIT,
                        "start": start_ms, "end": end_ms},
            )
            resp.raise_for_status()
            body = resp.json()
            if not body.get("success"):
                raise RuntimeError(f"connector success=false: {body}")
            return body.get("data") or []  # already the flat row list — never unwrap again
        except Exception as e:
            if attempt == 2:
                raise
            print(f"  page fetch failed ({e}); retrying once...", flush=True)
            time.sleep(2.0)


def _assert_connector_fresh(client, symbol):
    """Refuse to backfill from a stale/tape-mode connector."""
    rows = _fetch_page_latest(client, symbol)
    if not rows:
        raise SystemExit(f"connector returned no candles for {symbol} — aborting")
    newest = int(rows[0][0])
    age_ms = int(time.time() * 1000) - newest
    if age_ms > STALENESS_INTERVALS * INTERVAL_MS:
        raise SystemExit(
            f"newest {symbol} 5m candle is {age_ms / 60000:.1f} min old "
            f"(> {STALENESS_INTERVALS} intervals) — connector may be in tape "
            f"mode or market-data is stale; refusing to backfill"
        )


def _fetch_page_latest(client, symbol):
    resp = client.get(
        f"{CONNECTOR_URL}/api/v1/market/kline",
        params={"category": "linear", "symbol": symbol,
                "interval": INTERVAL_DB, "limit": 2},
    )
    resp.raise_for_status()
    body = resp.json()
    return body.get("data") or []


def _env(*names, default):
    """First non-empty env var among names, else default."""
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return default


def _connect_db():
    # market-data container exports TIMESCALE_* (verified 2026-08-06), not DB_*;
    # prefer those so the script always talks to the same DB the service does.
    import psycopg2

    return psycopg2.connect(
        host=_env("TIMESCALE_HOST", "DB_HOST", default="timescaledb"),
        port=int(_env("TIMESCALE_PORT", "DB_PORT", default="5432")),
        user=_env("TIMESCALE_USER", "DB_USER", default="cryptobot"),
        password=_env("TIMESCALE_PASSWORD", "DB_PASSWORD", default="cryptobot_secure_2024"),
        dbname=_env("TIMESCALE_DB", "DB_NAME", default="market_data"),
    )


def backfill_symbol(client, conn, symbol):
    from psycopg2.extras import execute_values

    fetch_time_ms = int(time.time() * 1000)
    created_ms = fetch_time_ms
    end_ms = fetch_time_ms
    start_ms = end_ms - DAYS * 86_400_000

    _assert_connector_fresh(client, symbol)

    seen = set()
    tuples = []
    current_end = end_ms
    pages = 0
    while current_end > start_ms:
        page_start, page_end = next_page_window(current_end, start_ms, INTERVAL_MS, PAGE_LIMIT)
        rows = _fetch_page(client, symbol, page_start, page_end)
        pages += 1
        if not rows:
            break  # reached the start of available history
        batch = kline_rows_to_tuples(
            rows, symbol, INTERVAL_DB, INTERVAL_MS, created_ms, fetch_time_ms
        )
        fresh = [t for t in batch if t[0] not in seen]
        seen.update(t[0] for t in fresh)
        tuples.extend(fresh)
        oldest = int(rows[-1][0])  # rows are newest-first; last element is oldest
        current_end = oldest - 1
        time.sleep(RATE_DELAY_S)

    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(tuples), BATCH_SIZE):
            execute_values(cur, INSERT_SQL, tuples[i : i + BATCH_SIZE], page_size=BATCH_SIZE)
            inserted += cur.rowcount
    conn.commit()
    print(
        f"{symbol}: pages={pages} fetched={len(tuples)} inserted={inserted} "
        f"skipped_existing={len(tuples) - inserted}",
        flush=True,
    )
    return len(tuples), inserted


def main():
    import httpx

    print(f"backfill: {SYMBOLS} interval={INTERVAL_DB} days={DAYS} via {CONNECTOR_URL}", flush=True)
    conn = _connect_db()
    try:
        with httpx.Client(timeout=30.0) as client:
            for symbol in SYMBOLS:
                backfill_symbol(client, conn, symbol)
    finally:
        conn.close()

    # verification counts
    conn = _connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT symbol, count(*) FROM klines "
                "WHERE interval = %s AND is_mainnet AND symbol = ANY(%s) "
                "GROUP BY symbol ORDER BY symbol",
                (INTERVAL_DB, SYMBOLS),
            )
            for sym, n in cur.fetchall():
                print(f"VERIFY {sym} interval={INTERVAL_DB}: {n} rows", flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot && python3 -m pytest tests/test_backfill_klines_5m.py --no-cov -q`
Expected: PASS (4 tests). (Module import runs only stdlib top-level code — httpx/psycopg2 are lazy imports.)

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_klines_5m.py tests/test_backfill_klines_5m.py
git commit -m "feat(scripts): 365-day 5m mainnet kline backfill via bybit-connector

Tournament harness needs >=50K rows per (symbol, interval); 5m data on
disk was ~6.5K patchy rows/symbol. Paginates 1000 bars/page backwards,
drops the forming bar, refuses stale/tape-mode connectors, inserts with
ON CONFLICT DO NOTHING (collector rows never overwritten), is_mainnet
set explicitly."
```

---

### Task 5: Execute the backfill (real data lands in TimescaleDB)

**Files:** none (execution only)

**Interfaces:**
- Consumes: `scripts/backfill_klines_5m.py` from Task 4.
- Produces: ≥100K real mainnet 5m klines per symbol in TimescaleDB — the precondition for Task 8's tournament run.

- [ ] **Step 1: Preflight connector**

Run: `curl -s -m 5 "http://localhost:8001/api/v1/market/kline?category=linear&symbol=SOLUSDT&interval=5&limit=2"`
Expected: `{"success":true,"data":[[...7 string fields...],[...]]}` with current-epoch ms timestamps (~1.786e12). If not, fix the connector before proceeding (see `docker compose -f docker-compose.unified.yml logs bybit-connector`).

- [ ] **Step 2: Run the backfill in the market-data container**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
docker cp scripts/backfill_klines_5m.py crypto-bot-market-data:/tmp/
docker exec crypto-bot-market-data python /tmp/backfill_klines_5m.py
```
Expected: per-symbol `pages=~106 fetched=~105000 inserted=...` lines, then three `VERIFY <sym> interval=5: <n> rows` lines with n ≥ 100,000. Takes ~1-2 min/symbol (rate-limit sleeps). Bybit lists these pairs well before 2025-08, so a full year exists upstream; if `fetched` comes back far below ~100K, treat it as a failure to investigate (connector logs, retCode errors), not as "no more history".

- [ ] **Step 3: Independent DB verification (not trusting script output)**

```bash
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
 "SELECT symbol, count(*),
         to_timestamp(min(timestamp)/1000)::date AS from_d,
         to_timestamp(max(timestamp)/1000)::date AS to_d
  FROM klines WHERE interval='5' AND is_mainnet
    AND symbol IN ('SOLUSDT','BNBUSDT','ADAUSDT')
  GROUP BY symbol;"
```
Expected: count ≥ 100,000 per symbol; from_d ≈ 2025-08-06; to_d = today. Also spot-check no duplicate timestamps:
```bash
docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
 "SELECT symbol, timestamp, count(*) FROM klines
  WHERE interval='5' AND symbol IN ('SOLUSDT','BNBUSDT','ADAUSDT')
  GROUP BY symbol, timestamp HAVING count(*) > 1 LIMIT 5;"
```
Expected: 0 rows.

No commit (no file changes).

---

### Task 6: Tournament config `tournament_gru_v1.yaml`

**Files:**
- Create: `services/tournament-harness/app/config/tournament_gru_v1.yaml`

**Interfaces:**
- Consumes: loader schema (required keys: tournament_id, seed, symbols, intervals, target_modes, architectures, default_resource_caps; gru HP dims: units, dropout, lr, batch, lookback, horizon; extra HP keys become grid axes — `epochs` is deliberate, the runner reads `hp.get("epochs", 30)`).
- Produces: the 6-experiment grid Task 8 runs; run_ids of form `gru_<SYMBOL>_5m_log_returns_<hash>`.

- [ ] **Step 1: Write the YAML**

```yaml
# First real tournament — minimal GRU grid (design spec 2026-08-06).
# 2 HP combos x 3 symbols x 1 interval x 1 target_mode = 6 experiments.
# LSTM excluded (ML-PURGE-02 in progress); transformer/TCN deferred.
#
# SECURITY: never put secrets in this file. Credentials come from env vars.

tournament_id: "gru_v1_2026_08_06"
seed: 42

symbols:
  - SOLUSDT
  - BNBUSDT
  - ADAUSDT

# Human-form interval; the runner maps to DB convention ("5") at the SQL boundary.
intervals:
  - "5m"

# log_returns only — the price-level path is the V0 mistake (R² on levels).
target_modes:
  - "log_returns"

default_resource_caps:
  mem_limit: "4g"
  cpus: 2.0
  # 60 min: GRU [128,64] on ~105K rows of 5m CPU-only can exceed the old 30 min.
  wallclock_timeout_seconds: 3600

max_experiments: 50

architectures:
  gru:
    units:
      - [64]
      - [128, 64]
    dropout: [0.2]
    lr: [0.001]
    batch: [64]
    lookback: [60]
    horizon: [5]
    # Extra HP axis (single value): runner reads hp.get("epochs", 30).
    # 20 caps worst-case wallclock; EarlyStopping(patience=10) usually stops sooner.
    epochs: [20]
```

- [ ] **Step 2: Validate the grid enumerates to exactly 6**

Run from `services/tournament-harness/`:
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from app.config.tournament_loader import load_tournament, enumerate_experiments
spec = load_tournament('app/config/tournament_gru_v1.yaml')
exps = enumerate_experiments(spec)
print(len(exps))
for e in exps[:3]:
    print(e.run_id, e.hp)
"
```
Expected: `6`, run_ids like `gru_SOLUSDT_5m_log_returns_<16hex>`, hp containing `epochs: 20`.

- [ ] **Step 3: Commit**

```bash
git add services/tournament-harness/app/config/tournament_gru_v1.yaml
git commit -m "feat(tournament-harness): first real tournament config — 6-experiment GRU grid"
```

---

### Task 7: Rebuild image, recreate harness, preflight everything

**Files:** none (execution only)

**Interfaces:**
- Consumes: Tasks 1-3 code fixes (baked into the image — runner containers use the SAME image), Task 6 YAML (copied into image via `COPY app/`).
- Produces: a running `crypto-bot-tournament-harness` container whose env, SDK, DB reach, and runner image are all verified — the launch platform for Task 8.

- [ ] **Step 1: Rebuild (BuildKit off — WSL2 hang gotcha)**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml --profile tournament build tournament-harness
```
Expected: image builds clean; pip installs `docker==7.1.0`.

- [ ] **Step 2: Recreate the container (MUST run from repo root — ${PWD} feeds RESULTS_HOST_DIR)**

```bash
docker compose -f docker-compose.unified.yml --profile tournament up -d --force-recreate tournament-harness
```

- [ ] **Step 3: Preflight checks (all four must pass before running the tournament)**

```bash
# (a) env correctness inside the container
docker exec crypto-bot-tournament-harness env | grep -E "RUNNER_IMAGE|RESULTS_HOST_DIR|TIMESCALE_DB"
# Expected: RUNNER_IMAGE=crypto-trading-bot-tournament-harness:latest
#           RESULTS_HOST_DIR=/mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness/data/results
#           TIMESCALE_DB=market_data

# (b) docker SDK works now (was broken with 7.0.0 — verified failing before)
docker exec crypto-bot-tournament-harness python -c "import docker; print(docker.from_env().ping())"
# Expected: True

# (c) runner image exists under the corrected name
docker images --format '{{.Repository}}:{{.Tag}}' | grep '^crypto-trading-bot-tournament-harness:latest$'
# Expected: one line

# (d) DB reachable as tournament_reader with the fixed loader (5m rows visible)
docker exec crypto-bot-tournament-harness python -c "
import os, psycopg2
conn = psycopg2.connect(host=os.environ['TIMESCALE_HOST'], port=os.environ['TIMESCALE_PORT'],
    user=os.environ['TIMESCALE_USER'], password=os.environ['TIMESCALE_PASSWORD'],
    dbname=os.environ['TIMESCALE_DB'])
cur = conn.cursor()
cur.execute(\"SELECT count(*) FROM klines WHERE symbol='SOLUSDT' AND interval='5' AND is_mainnet\")
print('SOLUSDT 5m rows visible to tournament_reader:', cur.fetchone()[0])
"
# Expected: >= 100000
```
If (a) shows a blank RESULTS_HOST_DIR, compose was invoked from the wrong cwd — rerun Step 2 from the repo root. If (d) fails with a permission error, the `tournament_reader` role lacks SELECT on klines — grant it via `docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c "GRANT SELECT ON klines TO tournament_reader;"` and re-check.

- [ ] **Step 4: Health check**

Run: `curl -s -m 5 http://localhost:8010/health`
Expected: `{"status":"healthy",...}` (also proves the canonical-metrics import chain — the lifespan fails fast if broken).

No commit (no file changes).

---

### Task 8: Run the real tournament

**Files:** none (execution only)

**Interfaces:**
- Consumes: everything above.
- Produces: leaderboard SQLite rows for `gru_v1_2026_08_06` — 6 rows, honestly succeeded or honestly failed.

- [ ] **Step 0: Memory headroom check (VERIFIED CONSTRAINT — do not skip)**

The WSL2 VM has only ~3.9 GB total RAM (verified 2026-08-06: 681 MB available, swap 4/8 GB consumed with the stack idle). The 4g per-runner `mem_limit` exceeds VM total; TF training would swap-thrash and produce `timeout` failures that are infra artifacts, not honest model failures. Before launching, do ONE of:

- **(a) preferred:** raise WSL memory — add to the Windows-side `.wslconfig` `[wsl2] memory=8GB`, then `wsl --shutdown` from Windows and restart the stack (`docker compose -f docker-compose.unified.yml up -d` + `--profile tournament up -d tournament-harness`, from repo root). This restarts everything — pick a moment when nothing else runs.
- **(b) fallback:** free memory in-place — stop containers not needed for the run: `docker stop crypto-bot-rabbitmq crypto-bot-notification crypto-bot-risk-metrics` (RabbitMQ carries no traffic per ADR-016). Restart them after the tournament.

Then verify: `free -m` shows ≥ 3,000 MB available before launch. If it cannot reach that, drop to option (a).

- [ ] **Step 1: Launch (detached — 1-3h wallclock; exec client must not be the only record)**

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot
docker exec -d -e GIT_SHA=$(git rev-parse HEAD) crypto-bot-tournament-harness \
  sh -c 'python -m app.cli run app/config/tournament_gru_v1.yaml --allow-dirty \
         > /app/data/results/tournament_run.log 2>&1'
```
`-d` detaches so a dying exec client cannot lose the run; the JSON summary survives in `services/tournament-harness/data/results/tournament_run.log` on the host (via the data/ bind mount). `$(git rev-parse HEAD)` substitutes on the host before exec — intended. `--allow-dirty` is explicit and honest: the image has no `.git`, so the dirty-check is a no-op in-container anyway, and the working tree genuinely has unrelated uncommitted changes.

- [ ] **Step 2: Monitor**

- Every ~10 min: `docker ps --filter label=tournament_id` (shows the current experiment container).
- `docker logs crypto-bot-tournament-harness --tail 20` (shows `[i/6] launching ...` / `... → success|failed(reason)` lines).
- Runner training logs land in `services/tournament-harness/data/results/gru_v1_2026_08_06/<run_id>/stdout.log` on the host — if the volume fix works, these files APPEAR ON THE HOST. Their absence after the first experiment finishes = the volume fix regressed; stop and debug (superpowers:systematic-debugging) rather than letting 6 failures accumulate.

- [ ] **Step 3: On completion — read the summary honestly**

Read the summary from `services/tournament-harness/data/results/tournament_run.log`. Expected best case: `{"tournament_id": "gru_v1_2026_08_06", "n_total": 6, "n_success": 6, "n_failed": 0, ...}`.
Failures are acceptable ONLY as honest failures: the leaderboard row must carry the true reason. On THIS host, any `timeout` or `oom_killed` must first be checked against memory pressure (`free -m`, `dmesg | grep -i oom`, swap usage during the run) before being accepted as a model failure — a swap-thrashed timeout is an infra artifact, not evidence. `n_failed=6` with a shared reason = a pipeline bug — debug it (systematic-debugging skill), fix, and re-run; do NOT export a snapshot of a fully-failed tournament as "done".

- [ ] **Step 4: Evidence — leaderboard rows (CLAUDE.md §7: paste the SELECT)**

```bash
docker exec crypto-bot-tournament-harness python -c "
import sqlite3
conn = sqlite3.connect('/app/data/leaderboard/leaderboard.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT run_id, symbol, status, failure_reason, dsr, oos_sharpe, dir_acc_corrected, train_seconds, git_sha FROM leaderboard WHERE tournament_id=? ORDER BY symbol', ('gru_v1_2026_08_06',)).fetchall()
for r in rows: print(dict(r))
print('total:', len(rows))
"
```
Expected: 6 rows; success rows have all metrics non-null and finite; `git_sha` is the real repo sha (not `unknown`). Per repo history, expect DSR near 0 / chance-level dir_acc — **page working ≠ edge found**; whatever the numbers are, they are the numbers.

No commit.

---

### Task 9: Export snapshot + gateway verification

**Files:** none (the snapshot JSON lands in `services/tournament-harness/data/snapshots/` — gitignored data, not committed)

**Interfaces:**
- Consumes: Task 8's leaderboard rows.
- Produces: `gru_v1_2026_08_06.json` on the host; gateway list + detail endpoints returning it. Snapshot top-level: `tournament_id, exported_at, schema_version, config, rows, summary{n_rows, n_success, n_failed, architectures, symbols}` — exactly what the gateway spreads and the frontend consumes (`tournament_id`, `exported_at`, `n_rows` in the selector; `snapshot.rows` in the table).

- [ ] **Step 1: Export**

```bash
docker exec crypto-bot-tournament-harness python -m app.cli export-snapshot gru_v1_2026_08_06
```
Expected: prints `{"snapshot_path": "/app/data/snapshots/gru_v1_2026_08_06.json", "n_rows": 6, ...}`.

- [ ] **Step 2: File on host (bind-mount proof)**

Run: `ls -la /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness/data/snapshots/`
Expected: `gru_v1_2026_08_06.json`, non-trivial size (tens of KB).

- [ ] **Step 3: Gateway endpoints (the exact ones the page calls)**

```bash
curl -s http://localhost:8000/api/tournament/snapshots | python3 -m json.tool | head -20
# Expected: count=1, tournaments[0] has tournament_id=gru_v1_2026_08_06,
#           exported_at=<today ISO>, n_rows=6, n_success/n_failed

curl -s http://localhost:8000/api/tournament/snapshots/gru_v1_2026_08_06 | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('success:', d['success'])
print('rows:', len(d['snapshot']['rows']))
print('ensemble:', d['ensemble'], '| significance:', d['significance'])
print('first row keys:', sorted(d['snapshot']['rows'][0].keys())[:8], '...')
"
# Expected: success True, rows 6, ensemble/significance None (sidecars are
#           produced by the open-pr flow — out of scope; page renders null fine)
```
The gateway container needs NO restart — it reads the RO bind-mount from disk on every request.

No commit.

---

### Task 10: Browser verification of the page + fix any real rendering errors

**Files:** possibly `frontend/src/**` — ONLY if a real defect surfaces with real data (none expected; contract verified against code).

**Interfaces:**
- Consumes: gateway serving the real snapshot.
- Produces: the deliverable — `/tournament` rendering real data, console clean, screenshot evidence.

- [ ] **Step 1: Load the page in Chrome (claude-in-chrome skill/tools)**

Navigate to `http://localhost:3000/tournament`. Verify against the CONTAINER at :3000 (prod nginx proxies `/api/` → gateway — verified end-to-end); the vite dev server has no `/api/tournament` proxy mapping and would 404 — never debug the pipeline from a dev-server 404. Expected within one refetch cycle:
- Selector shows `gru_v1_2026_08_06 · 2026-08-06 · 6 runs` and the URL gains `?tournament_id=gru_v1_2026_08_06` (auto-select of latest).
- Desktop table renders 6 rows sorted by DSR desc; DSR/OOS Sharpe/PSR/Dir.Acc/R² cells show finite numbers (or the honest `—` for failed rows).
- ContaminatedWindowWarning IS visible (365d window predates 2026-04-25 — honest labeling, do not "fix" it away).
- Footer shows `exported <ISO> · git <7-char real sha> · tournament started <ISO>`.

- [ ] **Step 2: Interactions**

- Click a column header (e.g. OOS Sharpe): rows re-sort, URL gets `?sort=oos_sharpe&dir=desc`.
- Click a symbol filter chip (e.g. SOL): table filters to 2 rows, chip counts match.
- Click Refresh: spinner cycles, data unchanged.

- [ ] **Step 3: Console + network clean**

Read browser console (pattern-filter for `error|warn`) and network requests. Expected: no errors; `GET /api/tournament/snapshots` and `/api/tournament/snapshots/gru_v1_2026_08_06` both 200. React key warnings, undefined-field TypeErrors, or failed requests = real defects: fix them (systematic-debugging skill, test-first where testable), commit as `fix(frontend): ...`.

- [ ] **Step 4: Screenshot evidence**

Capture a full-page screenshot of the populated leaderboard for the final report.

Commit only if frontend fixes were needed.

---

### Task 11: Final sweep — full test suites, evidence summary

**Files:**
- Possibly modify: none expected.

- [ ] **Step 1: Full harness suite (unit + integration)**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot/services/tournament-harness && python3 -m pytest tests/ --no-cov -q`
Expected: PASS. (Integration tests use fake docker — no live containers touched.)

- [ ] **Step 2: Root-level tests touched by this plan**

Run: `cd /mnt/d/Bimo_max/crypto-trading-bot && python3 -m pytest tests/test_backfill_klines_5m.py --no-cov -q`
Expected: PASS.

- [ ] **Step 3: Uncommitted-files check**

Run: `git status --porcelain` — every file this plan touched must be committed; unrelated pre-existing modifications (`.planning/`, `backtesting/killtests/`, etc.) must remain untouched.

- [ ] **Step 4: Evidence summary for the user (CLAUDE.md §7 format)**

Assemble in the final message: (1) leaderboard SELECT output, (2) snapshot file path + host `ls` proof, (3) gateway curl outputs, (4) screenshot, (5) honest metric readout (expected: no edge — say so plainly), (6) list of commits.

---

## Self-review notes (completed at plan time)

- **Spec coverage:** §1 backfill → Tasks 4-5; §2 harness fixes → Tasks 1-3 (interval map, ms-epoch, tz — Task 1; RUNNER_IMAGE — Task 2; floor untouched — verified in Task 1 code); §3 run config → Task 6; §4 execution → Tasks 7-8; error-handling honesty → Tasks 8.3, 10.1; §5 verification → Tasks 8.4, 9, 10, 11. Defects discovered post-spec (volume path, docker SDK pin, tz-aware, git_sha, timescale_db default) are covered by Tasks 1-3 and noted in the defect inventory.
- **Placeholder scan:** none — every code step carries full content; the two "adapt if" steps (Task 1 Step 6, Task 2 Step 7) specify exactly which assertions may change and in which direction.
- **Type consistency:** `_interval_to_db`/`_to_utc`/`INTERVAL_TO_DB` names match between Task 1 impl and tests; `host_output_root` kwarg matches between Task 2 impl and tests; `kline_rows_to_tuples`/`next_page_window` match between Task 4 script and tests; tournament_id `gru_v1_2026_08_06` used consistently in Tasks 6-10.
