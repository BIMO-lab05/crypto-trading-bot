# Phase 3: Tournament Harness Core - Pattern Map

**Mapped:** 2026-05-08
**Files analyzed:** 17 new files + 4 modified files = 21 total
**Analogs found:** 12 / 21 (5 are reused-as-is imports — see "Reused modules", 4 have no analog — see "No Analog Found")

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `services/tournament-harness/Dockerfile` | config | build | `services/ml-retraining-service/Dockerfile` | exact |
| `services/tournament-harness/requirements.txt` | config | build | `services/ml-retraining-service/requirements.txt` | role-match (add `docker`, `pyyaml` already TF transitive) |
| `services/tournament-harness/app/main.py` | controller | request-response (read-only API per CD-07) | `services/ml-retraining-service/app/main.py` (status/list endpoints only — drop write paths) | role-match |
| `services/tournament-harness/app/orchestrator.py` | service | event-driven (per-experiment Docker container lifecycle) | None (no in-repo precedent for Docker SDK orchestration) | **none — see No Analog Found** |
| `services/tournament-harness/app/runner.py` | service | batch (one experiment, train + metrics + write result.json) | `services/ml-retraining-service/app/core/model_trainer.py:train_model` | exact (training pipeline structure) |
| `services/tournament-harness/app/config/settings.py` | config | static | `services/ml-retraining-service/app/config/settings.py` | exact |
| `services/tournament-harness/app/config/tournament_loader.py` | service | transform (YAML → Cartesian experiment list + hp_hash) | None (no in-repo YAML+Cartesian precedent) | **none — see No Analog Found** |
| `services/tournament-harness/app/leaderboard/db.py` | service | CRUD (SQLite single-writer, migration runner) | None (project DB layer is async SQLAlchemy + Postgres — different shape) | **none — see No Analog Found** |
| `services/tournament-harness/app/leaderboard/queries.py` | service | request-response (parameterized SQL DSL) | None (no in-repo raw-SQL DSL) | **none — see No Analog Found** |
| `services/tournament-harness/app/leaderboard/snapshot.py` | service | transform (SQLite → JSON) | `services/ml-retraining-service/app/core/model_trainer.py:save_model` (json.dump pattern) | role-match |
| `services/tournament-harness/app/cli.py` | controller | request-response (operator CLI) | None (existing services are FastAPI-only; CLI is new surface) | **none — see No Analog Found** |
| `services/tournament-harness/app/failure.py` | utility | transform (Docker container state → typed enum) | None (failure classification on Docker state inspection is novel here) | **none — see No Analog Found** |
| `services/tournament-harness/migrations/0001_initial.sql` | migration | DDL | `infrastructure/migrations/001_initial_schema.sql` + `infrastructure/migrations/002_performance_history.sql` | role-match (Postgres → SQLite dialect adjustments) |
| `services/tournament-harness/tests/conftest.py` | test | fixtures | `services/ml-retraining-service/tests/conftest.py` | exact |
| `services/tournament-harness/tests/unit/test_*.py` | test | unit | `services/ml-retraining-service/tests/test_model_trainer.py` (pattern reference) | role-match |
| `services/tournament-harness/tests/integration/test_*.py` | test | integration | `tests/integration/conftest.py` (Phase 2 — `bootstrap_stack` fixture) | role-match |
| **Modified files** | | | | |
| `docker-compose.unified.yml` (add `tournament-harness` stanza under `profile: ["tournament"]`) | config | static | `docker-compose.unified.yml:677-728` (`ml-prediction:` stanza — has the `profiles:` opt-in pattern) | exact |
| `services/ml-retraining-service/app/core/model_trainer.py` (refactor `build_gru_model` → `models/gru.py:build` registry per CD-01) | service | batch | self (refactor of existing) | self-refactor |
| `services/ml-retraining-service/app/core/models/gru.py` (NEW from refactor) | service | transform (build) | `services/ml-retraining-service/app/core/model_trainer.py:build_gru_model` lines 216-269 | exact |
| `services/ml-retraining-service/app/core/models/{lstm,transformer,tcn}.py` | service | transform (build) | `gru.py` (sibling — same `build(input_shape, hp) -> keras.Model` contract) | role-match |
| `infrastructure/database/` migration adding `tournament_reader` Postgres role | migration | DDL | `infrastructure/migrations/001_initial_schema.sql` (CREATE-with-comment header pattern) | role-match |
| `.gitignore` (add `services/tournament-harness/data/leaderboard.db`, `data/results/`, `data/snapshots/*.db`) | config | static | existing `.gitignore` entries — no excerpt needed | trivial |

---

## Reused Modules — Imported, NOT Copied (TOURN-07 grep gate)

These five modules are in canonical_refs but are **reused verbatim via import**, not patterns to extract. The TOURN-07 success criterion explicitly forbids re-implementation:
`grep -r "def directional_accuracy\|def sharpe\|def deflated" services/tournament-harness/` must return **nothing**.

The runner imports these from a shared location (CD-01 implies `libs/` shared package OR direct `PYTHONPATH` include of ml-retraining `app/`):

| Module | Public surface to import |
|--------|------------------------|
| `services/ml-retraining-service/app/core/returns_metrics.py` | `compute_returns_metrics(actual_prices, pred_prices, last_close, dataset_name) -> Dict[str, float]` (lines 25-30) |
| `services/ml-retraining-service/app/sharpe_metrics.py` | `probabilistic_sharpe_ratio(returns, benchmark_sr=0.0) -> float` (line 148), `expected_max_sharpe_under_null(num_trials, trial_sharpes_variance) -> float` (line 197), `deflated_sharpe_ratio(returns, num_trials, trial_sharpes_variance) -> float` (line 223) |
| `services/ml-retraining-service/app/cpcv.py` | `CombinatorialPurgedCV` (line 63), `cpcv_sharpe_distribution(returns_per_path) -> dict` (line 193), `cpcv_to_dsr(returns_per_path, concatenated_returns) -> float` (line 232) |
| `services/ml-retraining-service/app/core/cpcv_evaluation.py` | `evaluate_with_cpcv(actual_prices, pred_prices, last_close, dataset_name, label_horizon)` (used by `model_trainer.py:_calculate_cpcv_metrics` lines 549-555) — runner uses identical call |
| `services/ml-retraining-service/app/core/stationary_features.py` | `STATIONARY_FEATURE_COLS: List[str]` (line 34, 17 cols), `compute_stationary_features(df) -> pd.DataFrame` (line 64) |

**Plan-phase action:** add CI guard step `grep -r "def directional_accuracy\|def sharpe\|def deflated" services/tournament-harness/ && exit 1 || true` to enforce TOURN-07.

---

## Pattern Assignments

### `services/tournament-harness/Dockerfile` (config, build)

**Analog:** `services/ml-retraining-service/Dockerfile`

**Full file pattern (lines 1-41):**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System deps for compiled wheels (numpy, pandas, asyncpg, tensorflow)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Resilient pip on slow networks (audit 2026-04-29)
ENV PIP_DEFAULT_TIMEOUT=600 PIP_RETRIES=10
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/

# Tournament data dirs (bind-mounted from host in compose)
RUN mkdir -p /app/data/leaderboard /app/data/results /app/data/snapshots

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8010

# Health check (port placeholder — confirm in plan)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8010/health')"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

**Adaptation notes:**
- ml-retraining uses port 8009; tournament-harness needs a free port (8010 placeholder; confirm against `services/*/Dockerfile` collision in plan).
- ml-retraining `mkdir`s model dirs; tournament-harness `mkdir`s `data/{leaderboard,results,snapshots}`.
- The runner ENTRYPOINT is **the same image with a different CMD** (D-05). The Dockerfile CMD above is the orchestrator/API; the orchestrator launches each experiment with `command=["python", "-m", "app.runner", "--experiment-spec", "<json>"]` overriding CMD per-container.

---

### `services/tournament-harness/requirements.txt` (config, build)

**Analog:** `services/ml-retraining-service/requirements.txt`

**Pattern with tournament-specific additions:**
```
# Web Framework
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0

# DB clients
asyncpg==0.29.0          # TimescaleDB klines reads (read-only via tournament_reader role)
# NB: NO sqlalchemy here — leaderboard uses stdlib sqlite3 (D-17)

# Data Processing
pandas==2.1.4
numpy==1.26.2

# ML/AI (registry needs all four arch families; same TF version as ml-retraining)
tensorflow==2.15.0
scikit-learn==1.3.2

# YAML config (D-11 — already TF transitive, but pin explicitly)
pyyaml==6.0.1

# Docker SDK (D-02)
docker==7.0.0

# Logging / Testing (mirror ml-retraining)
python-json-logger==2.0.7
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
```

**Adaptation:** Drop `apscheduler` (no cron — start is operator-driven per D-12). Drop `redis`, `alembic` (SQLite + numbered SQL only). Add `docker` (Docker SDK — D-02) and explicit `pyyaml`.

---

### `services/tournament-harness/app/main.py` (controller, request-response — read-only)

**Analog:** `services/ml-retraining-service/app/main.py`

**Imports + lifespan pattern** (ml-retraining lines 1-87, simplified for read-only):
```python
"""
Tournament Harness - Main Application
Purpose: Read-only status / leaderboard inspection API (CD-07).
Mutation paths (start tournament) live in app/cli.py.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.config.settings import get_settings
from app.leaderboard.db import LeaderboardDB

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"Starting {settings.service_name}")
    logger.info("=" * 60)
    # No scheduler, no DB-init side effects on startup.
    # Migrations run lazily on first orchestrator invocation (CLI), not API boot.
    yield
    logger.info("Service stopped")


app = FastAPI(
    title="Tournament Harness",
    description="Read-only status / leaderboard inspection. Mutation via CLI only.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)
```

**Health endpoint pattern** (ml-retraining lines 113-125):
```python
@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.service_name,
        "timestamp": datetime.now().isoformat(),
    }
```

**List endpoint pattern** (ml-retraining lines 276-318 — `list_model_versions`; mirror for `GET /api/v1/tournaments/{tid}/runs`):
```python
@app.get("/api/v1/tournaments/{tournament_id}/runs", tags=["Tournament"])
async def list_runs(
    tournament_id: str,
    architecture: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None, description="success | failed"),
    limit: int = Query(default=100, le=1000),
):
    try:
        db = LeaderboardDB()
        rows = db.list_runs(
            tournament_id=tournament_id,
            architecture=architecture, symbol=symbol, status=status, limit=limit,
        )
        return {"success": True, "count": len(rows), "runs": rows}
    except Exception as e:
        logger.error(f"Error listing runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

**Error handling pattern** (ml-retraining lines 207-209, repeated throughout):
```python
except HTTPException:
    raise
except Exception as e:
    logger.error(f"<context>: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=str(e))
```

**What NOT to copy from ml-retraining `main.py`:**
- All `POST` endpoints (CD-07 says read-only API; mutation via CLI).
- `BackgroundTasks` / scheduler endpoints (no cron).
- `db: AsyncSession = Depends(get_db)` SQLAlchemy injection — leaderboard is stdlib `sqlite3`.

---

### `services/tournament-harness/app/runner.py` (service, batch — single experiment train + metrics + result.json)

**Analog:** `services/ml-retraining-service/app/core/model_trainer.py` lines 271-497 (`train_model`)

**Training pipeline structure to copy** (lines 300-403, abbreviated):
```python
def run_experiment(spec: ExperimentSpec) -> dict:
    """Execute one experiment: load → train → metrics → write result.json"""
    start_time = datetime.now()
    try:
        # Step 1: Prepare features (stationary-only, locked per D-10)
        from app.core.stationary_features import (
            STATIONARY_FEATURE_COLS, compute_stationary_features,
        )
        data_with_features = compute_stationary_features(klines_df)

        if len(data_with_features) < spec.lookback + spec.horizon + 100:
            raise ValueError(f"Insufficient data: {len(data_with_features)} rows")

        # Step 2: Create sequences (target_col flips on target_mode)
        target_col = "close" if spec.target_mode == "price" else "log_returns"
        X, y = create_sequences(
            data_with_features,
            target_col=target_col,
            feature_cols=list(STATIONARY_FEATURE_COLS),
            sequence_length=spec.lookback,
            prediction_horizon=spec.horizon,
        )

        # Step 3: Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # Step 4: Build model from registry (CD-01)
        from app.core.models import REGISTRY
        builder = REGISTRY[spec.architecture]  # gru | lstm | transformer | tcn
        model = builder.build(input_shape=(X_train.shape[1], X_train.shape[2]), hp=spec.hp)

        # Step 5: Callbacks (mirror lines 343-356)
        early_stopping = callbacks.EarlyStopping(
            monitor='val_loss', patience=10, restore_best_weights=True, verbose=1
        )
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor='val_loss', factor=0.5, patience=5, min_lr=0.00001, verbose=1
        )

        # Step 6: Train (mirror lines 361-368)
        history = model.fit(
            X_train, y_train,
            epochs=spec.max_epochs, batch_size=spec.batch,
            validation_split=0.2,
            callbacks=[early_stopping, reduce_lr],
            verbose=1,
        )
        # ... (continue with metrics + cpcv + result.json write) ...
```

**Metrics pattern (lines 379-413) — IMPORTS, never re-implements (TOURN-07):**
```python
# Honest skill-on-returns metrics — IMPORT, do not redefine.
from app.core.returns_metrics import compute_returns_metrics
from app.core.cpcv_evaluation import evaluate_with_cpcv
from app.sharpe_metrics import deflated_sharpe_ratio  # if direct DSR call needed
from app.cpcv import cpcv_to_dsr

last_close_test = data_with_features['close'].values[
    spec.lookback - 1 + len(X_train) :
    spec.lookback - 1 + len(X_train) + len(X_test)
]
test_metrics.update(compute_returns_metrics(actual_prices, pred_prices, last_close_test, "test"))

# CPCV — drop-in (mirrors lines 519-562)
label_horizon = spec.lookback + spec.horizon - 1
cpcv_metrics = evaluate_with_cpcv(
    actual_prices, pred_prices, last_close_test,
    dataset_name="test", label_horizon=label_horizon,
)
test_metrics.update(cpcv_metrics)
```

**Result.json contract (D-16) — written before exit:**
```python
result = {
    "status": "success",  # or "failed"
    "reason": None,        # set to nan_loss | train_diverged | db_unreachable on failure
    "tournament_id": spec.tournament_id,
    "run_id": spec.run_id,
    "architecture": spec.architecture,
    "symbol": spec.symbol,
    "horizon": spec.horizon,
    "target_mode": spec.target_mode,
    "hp_hash": spec.hp_hash,
    "metrics": {
        # exact column names per TOURN-02
        "r2_returns": test_metrics["test_r2_returns"],
        "dir_acc_corrected": test_metrics["test_dir_acc_corrected"],
        "oos_sharpe": test_metrics["test_cpcv_oos_sharpe"],
        "psr": ...,            # via probabilistic_sharpe_ratio(returns)
        "dsr": test_metrics["test_dsr"],
        "cpcv_dsr": ...,       # via cpcv_to_dsr(returns_per_path, concatenated)
        "train_seconds": training_time,
    },
    "git_sha": os.environ["GIT_SHA"],          # injected by orchestrator
    "tournament_start_ts": os.environ["TS_START"],
    "train_window_includes_contaminated": ...,  # D-08 flag
}
with open("/output/result.json", "w") as f:
    json.dump(result, f, indent=2, default=str)
```

**Failure-path early write (D-15: nan_loss / db_unreachable):**
```python
# Inside train loop — runner sets these explicitly so orchestrator can classify:
if np.isnan(history.history['loss']).any():
    write_failure_result(spec, reason="nan_loss")
    sys.exit(0)  # exit 0 — orchestrator parses result.json for the typed reason

# Connection-time
try:
    klines_df = load_klines_from_timescale(spec)
except (asyncpg.exceptions.ConnectionRejectionError, OSError) as e:
    write_failure_result(spec, reason="db_unreachable", err=str(e))
    sys.exit(0)
```

---

### `services/tournament-harness/app/config/settings.py` (config, static)

**Analog:** `services/ml-retraining-service/app/config/settings.py`

**Pydantic-Settings pattern** (lines 13-279, abbreviated for tournament):
```python
import json
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional


class TournamentSettings(BaseSettings):
    """Tournament Harness Configuration (process-level defaults).

    Tournament-run shape (architectures × symbols × HP grid) lives in the
    operator's tournament.yaml — NOT here. This class only holds:
      - service ports / paths
      - default Docker SDK resource caps (D-04)
      - default DB / leaderboard / results paths
      - TimescaleDB connection (read-only tournament_reader role)
    """

    # Service Configuration
    service_name: str = Field(default="tournament-harness")
    service_host: str = Field(default="0.0.0.0")
    service_port: int = Field(default=8010)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # Default per-experiment resource caps (D-04). Override per-arch in YAML.
    default_mem_limit: str = Field(default="4g")
    default_cpus: float = Field(default=2.0)
    default_wallclock_timeout_seconds: int = Field(default=1800)  # 30 min

    # Storage paths (host-side; bind-mounted into orchestrator container)
    leaderboard_db_path: str = Field(default="/app/data/leaderboard/leaderboard.db")
    results_dir: str = Field(default="/app/data/results")
    snapshots_dir: str = Field(default="/app/data/snapshots")

    # TimescaleDB connection (read-only tournament_reader role, D-09)
    timescale_host: str = Field(default="timescaledb")
    timescale_port: int = Field(default=5432)
    timescale_db: str = Field(default="trading_bot")
    timescale_user: str = Field(default="tournament_reader")
    timescale_password: str = Field(default="")

    # Docker network the experiment containers join (D-09)
    docker_network: str = Field(default="crypto-bot-network")

    # Image tag for experiment containers (D-05 — same image as orchestrator)
    runner_image: str = Field(default="crypto-bot-tournament-harness:latest")

    @property
    def timescale_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.timescale_user}:{self.timescale_password}"
            f"@{self.timescale_host}:{self.timescale_port}/{self.timescale_db}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


_settings: TournamentSettings | None = None

def get_settings() -> TournamentSettings:
    global _settings
    if _settings is None:
        _settings = TournamentSettings()
    return _settings
```

**Singleton pattern** copied verbatim from analog lines 282-298.

---

### `services/tournament-harness/app/leaderboard/snapshot.py` (service, transform — SQLite → JSON)

**Analog:** `services/ml-retraining-service/app/core/model_trainer.py:save_model` lines 695-707 (json.dump with indent + default=str for datetimes)

**Pattern to copy** (lines 695-697):
```python
with open(metadata_path, 'w') as f:
    json.dump(metadata, f, indent=2, default=str)
logger.info(f"Metadata saved: {metadata_path}")
```

**Adapted for snapshot:**
```python
def export_snapshot(tournament_id: str, output_path: Path) -> None:
    """Export a tournament's leaderboard rows + config to a committable JSON.
    Per D-18, this is the artifact Phase 4 (TOURN-05) and Phase 7 (DASH-04) read.
    """
    db = LeaderboardDB()
    rows = db.list_runs(tournament_id=tournament_id, limit=10**9)
    config = db.get_tournament_config(tournament_id)

    snapshot = {
        "tournament_id": tournament_id,
        "exported_at": datetime.now().isoformat(),
        "config": config,
        "rows": rows,
        "schema_version": db.schema_version(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(snapshot, f, indent=2, default=str)
    logger.info(f"Snapshot saved: {output_path} ({len(rows)} rows)")
```

---

### `services/tournament-harness/migrations/0001_initial.sql` (migration, DDL)

**Analog:** `infrastructure/migrations/001_initial_schema.sql` (Postgres) + `infrastructure/migrations/002_performance_history.sql` (numbered + commented header)

**Header pattern** (`001_initial_schema.sql` lines 1-7 + `002_performance_history.sql` lines 1-9):
```sql
-- Migration 0001: Initial Tournament Leaderboard Schema
-- Purpose: Create leaderboard rows + schema_version tracking
-- Date: 2026-05-08
-- Author: Tournament Harness (Phase 3)
```

**`CREATE TABLE IF NOT EXISTS` + comments + indexes pattern** (lines 9-30):
```sql
-- ============================================================================
-- LEADERBOARD ROWS (TOURN-02: PK on architecture, symbol, horizon, target_mode, hp_hash, run_id)
-- ============================================================================
CREATE TABLE IF NOT EXISTS leaderboard (
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL,         -- gru | lstm | transformer | tcn
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL,
    target_mode         TEXT NOT NULL,         -- price | log_returns
    hp_hash             TEXT NOT NULL,
    -- Honest metrics (TOURN-02 columns)
    r2_returns          REAL,
    dir_acc_corrected   REAL,
    oos_sharpe          REAL,
    psr                 REAL,
    dsr                 REAL,
    cpcv_dsr            REAL,
    train_seconds       REAL,
    -- Reproducibility stamps (D-13, D-07)
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    train_window_includes_contaminated INTEGER NOT NULL DEFAULT 0,  -- D-08
    -- Failure semantics (D-15)
    status              TEXT NOT NULL,         -- success | failed
    failure_reason      TEXT,                  -- oom_killed | nan_loss | timeout | exit_nonzero | train_diverged | db_unreachable | unknown
    failure_stderr_tail TEXT,                  -- last 4KB stderr
    -- Audit
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);

CREATE INDEX IF NOT EXISTS idx_leaderboard_tournament ON leaderboard(tournament_id);
CREATE INDEX IF NOT EXISTS idx_leaderboard_dsr ON leaderboard(tournament_id, dsr DESC);
CREATE INDEX IF NOT EXISTS idx_leaderboard_arch_symbol ON leaderboard(architecture, symbol);
CREATE INDEX IF NOT EXISTS idx_leaderboard_status ON leaderboard(status);

-- ============================================================================
-- TOURNAMENT CONFIG (one row per tournament — full YAML stored verbatim)
-- ============================================================================
CREATE TABLE IF NOT EXISTS tournaments (
    tournament_id       TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at        TEXT,
    config_yaml         TEXT NOT NULL,         -- full YAML for reproducibility
    git_sha             TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    n_experiments_total    INTEGER,
    n_experiments_success  INTEGER,
    n_experiments_failed   INTEGER
);

-- ============================================================================
-- SCHEMA VERSION TRACKING (D-17)
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES (1, 'Initial leaderboard + tournaments + schema_version tables');
```

**Adaptation notes:**
- Postgres → SQLite: `SERIAL` → no equivalent (use `TEXT` natural keys); `TIMESTAMP DEFAULT NOW()` → `TEXT NOT NULL DEFAULT (datetime('now'))`; no `JSONB` → use `TEXT` (raw JSON string for `config_yaml`).
- No `COMMENT ON TABLE` in SQLite — use `--` line comments (already shown).
- Idempotent — analog uses `CREATE TABLE IF NOT EXISTS` (lines 9, 35, 74, 107, 139); same pattern here.

**Migration runner pattern (D-17 — applied at orchestrator startup):**
```python
def run_migrations(db_path: Path, migrations_dir: Path) -> None:
    """Apply numbered SQL files in order. Idempotent via schema_version + IF NOT EXISTS."""
    conn = sqlite3.connect(str(db_path))
    try:
        # Bootstrap schema_version table (no-op after first run).
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS schema_version "
            "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')), "
            "description TEXT NOT NULL);"
        )
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_version")}
        for sql_file in sorted(migrations_dir.glob("*.sql")):
            version = int(sql_file.stem.split("_")[0])
            if version in applied:
                continue
            logger.info(f"Applying migration {sql_file.name}")
            conn.executescript(sql_file.read_text())
            conn.commit()
    finally:
        conn.close()
```

---

### `services/tournament-harness/tests/conftest.py` (test, fixtures)

**Analog:** `services/ml-retraining-service/tests/conftest.py` lines 70-127

**Path-import-shim pattern** (lines 70-73):
```python
# Make the service root importable as ``app.*`` regardless of cwd
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))
```

**FastAPI TestClient fixture pattern** (lines 103-126):
```python
@pytest.fixture
def test_client():
    """FastAPI TestClient — tournament API is read-only, no DB-dep override needed."""
    from fastapi.testclient import TestClient
    from app.main import app
    # No app.dependency_overrides — main.py has no Depends(get_db) in CD-07 scope.
    client = TestClient(app)
    yield client
```

**Synthetic OHLCV fixture pattern** (lines 167-192):
```python
@pytest.fixture
def synthetic_klines():
    """OHLCV DataFrame for runner-pipeline tests without TimescaleDB."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 200
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    high = base + np.abs(rng.normal(0, 0.5, n))
    low = base - np.abs(rng.normal(0, 0.5, n))
    close = base + rng.normal(0, 0.2, n)
    volume = np.abs(rng.normal(1000, 100, n))
    timestamps = pd.date_range("2024-01-01", periods=n, freq="60min")
    return pd.DataFrame({
        "timestamp": timestamps, "open": base, "high": high, "low": low,
        "close": close, "volume": volume,
    })
```

**Tournament-specific addition (no analog — fresh fixture):**
```python
@pytest.fixture
def tmp_leaderboard_db(tmp_path, monkeypatch):
    """Initialise a fresh SQLite leaderboard with migrations applied — per-test isolation."""
    db_path = tmp_path / "leaderboard.db"
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    from app.leaderboard.db import run_migrations
    run_migrations(db_path, migrations_dir)
    monkeypatch.setenv("LEADERBOARD_DB_PATH", str(db_path))
    return db_path


@pytest.fixture
def fake_docker_client():
    """MagicMock for `docker.from_env()` — orchestrator unit tests should not hit Docker."""
    from unittest.mock import MagicMock
    client = MagicMock()
    client.containers.run.return_value = MagicMock(
        wait=lambda timeout=None: {"StatusCode": 0, "Error": None},
        logs=lambda **kw: b"stdout\n",
        kill=MagicMock(),
        remove=MagicMock(),
        attrs={"State": {"OOMKilled": False, "ExitCode": 0}},
        labels={"tournament_id": "t1", "run_id": "r1"},
    )
    return client
```

---

### `docker-compose.unified.yml` — add `tournament-harness:` stanza (config, static)

**Analog:** `docker-compose.unified.yml:677-728` (`ml-prediction:` — has the `profiles:` opt-in, container_name, network, healthcheck, deploy.resources)

**Pattern to copy** (lines 677-728, abbreviated):
```yaml
  ml-prediction:
    build:
      context: ./services/ml-prediction-service
      dockerfile: Dockerfile
    container_name: crypto-bot-ml-prediction
    hostname: ml-prediction
    ports:
      - "${ML_PORT:-8007}:8007"
    environment:
      - SERVICE_NAME=ml-prediction-service
      - SERVICE_PORT=8007
      ...
    volumes:
      - ./services/ml-prediction-service/logs:/app/logs
      - ./services/ml-prediction-service/models:/app/models
    networks:
      - crypto-bot-network
    depends_on:
      market-data:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8007/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    profiles:
      - ml
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
```

**Adapted tournament-harness stanza:**
```yaml
  # ---------------------------------------------------------------------------
  # Tournament Harness - Docker-isolated ML candidate evaluation (Phase 3)
  # Profile: opt-in only. Default `bootstrap.sh up` does not start it.
  # Bring up with: docker compose -f docker-compose.unified.yml --profile tournament up tournament-harness
  # ---------------------------------------------------------------------------
  tournament-harness:
    build:
      context: ./services/tournament-harness
      dockerfile: Dockerfile
    container_name: crypto-bot-tournament-harness
    hostname: tournament-harness
    ports:
      - "${TOURNAMENT_PORT:-8010}:8010"
    environment:
      - SERVICE_NAME=tournament-harness
      - SERVICE_PORT=8010
      - DEBUG=${DEBUG:-false}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - TIMESCALE_HOST=timescaledb
      - TIMESCALE_PORT=5432
      - TIMESCALE_DB=${TIMESCALE_DB:-trading_bot}
      - TIMESCALE_USER=tournament_reader
      - TIMESCALE_PASSWORD=${TOURNAMENT_READER_PASSWORD:-}
      - DOCKER_NETWORK=crypto-bot-network
      - RUNNER_IMAGE=crypto-bot-tournament-harness:latest
    volumes:
      - ./services/tournament-harness/data:/app/data
      # Privilege boundary: orchestrator spawns experiment containers via SDK.
      # See code_context Integration Points — document risk in plan.
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - crypto-bot-network
    depends_on:
      timescaledb:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    restart: unless-stopped
    profiles:
      - tournament      # D-01: opt-in only
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G    # Orchestrator footprint; per-experiment containers have own caps.
```

**Adaptation notes:**
- Reuses every block from the `ml-prediction:` stanza: `build`, `container_name`, `hostname`, `ports`, `environment`, `volumes`, `networks`, `depends_on`, `healthcheck`, `restart`, `profiles`, `deploy.resources`.
- New: `/var/run/docker.sock` bind-mount (Docker SDK requirement, D-02). Must be flagged in plan as a privilege-boundary risk.
- `profiles: [tournament]` (D-01) instead of `profiles: [ml]`.
- `depends_on` only `timescaledb` (orchestrator does not depend on the trading engine).

---

### `services/ml-retraining-service/app/core/models/gru.py` (NEW from CD-01 refactor)

**Analog:** `services/ml-retraining-service/app/core/model_trainer.py:build_gru_model` lines 216-269

**Existing pattern to extract** (lines 216-269):
```python
def build_gru_model(self, input_shape: Tuple[int, int]) -> keras.Model:
    """
    Build GRU model architecture from ``self.gru_units``.

    Stacks ``len(self.gru_units)`` GRU layers in order. All layers
    except the last set ``return_sequences=True``; the last sets
    ``return_sequences=False`` so it feeds a Dense head.
    """
    n_layers = len(self.gru_units)
    model = keras.Sequential()
    for i, units in enumerate(self.gru_units):
        return_sequences = (i < n_layers - 1)
        if i == 0:
            model.add(layers.GRU(units, return_sequences=return_sequences,
                                 input_shape=input_shape))
        else:
            model.add(layers.GRU(units, return_sequences=return_sequences))
        model.add(layers.Dropout(self.dropout_rate))

    model.add(layers.Dense(self.prediction_horizon))
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=0.001),
                  loss='mse', metrics=['mae'])
    return model
```

**Refactored contract for `models/gru.py:build` (CD-01):**
```python
"""GRU builder — registry entry for the architecture-coverage refactor (CD-01)."""
from typing import Tuple
from tensorflow import keras
from tensorflow.keras import layers


def build(input_shape: Tuple[int, int], hp: dict) -> keras.Model:
    """
    Build GRU model. Same logic as legacy build_gru_model, parameterised on `hp`.

    hp keys: units (List[int]), dropout (float), lr (float), horizon (int)
    """
    units_list = hp["units"]   # e.g. [128, 64] or [32]
    dropout = hp["dropout"]
    lr = hp["lr"]
    horizon = hp["horizon"]

    n_layers = len(units_list)
    model = keras.Sequential()
    for i, units in enumerate(units_list):
        return_sequences = (i < n_layers - 1)
        if i == 0:
            model.add(layers.GRU(units, return_sequences=return_sequences,
                                 input_shape=input_shape))
        else:
            model.add(layers.GRU(units, return_sequences=return_sequences))
        model.add(layers.Dropout(dropout))

    model.add(layers.Dense(horizon))
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=lr),
                  loss='mse', metrics=['mae'])
    return model
```

**`models/{lstm,transformer,tcn}.py` siblings** must implement the **same `build(input_shape, hp) -> keras.Model` signature**. CD-01 specifies ≤80 LOC each, Keras-only:
- `lstm.py`: replace `layers.GRU` with `layers.LSTM`; same stacking + dropout + Dense head.
- `transformer.py`: stacked `MultiHeadAttention` + FFN + positional encoding (Keras provides `MultiHeadAttention`); per-layer LayerNorm; final `GlobalAveragePooling1D` → `Dense`.
- `tcn.py`: stacked dilated `Conv1D` with residual connections; final `GlobalAveragePooling1D` → `Dense`.

**Registry module** (`models/__init__.py`):
```python
from app.core.models import gru, lstm, transformer, tcn

REGISTRY = {
    "gru": gru,
    "lstm": lstm,
    "transformer": transformer,
    "tcn": tcn,
}
```

**Trainer change in `model_trainer.py`** (replace `build_gru_model` call at line 340):
```python
# OLD: model = self.build_gru_model(input_shape=(X_train.shape[1], X_train.shape[2]))
# NEW:
from app.core.models import REGISTRY
builder = REGISTRY[self.architecture]   # default "gru" preserves legacy behaviour
model = builder.build(
    input_shape=(X_train.shape[1], X_train.shape[2]),
    hp={"units": self.gru_units, "dropout": self.dropout_rate, "lr": 0.001,
        "horizon": self.prediction_horizon},
)
```

---

### `infrastructure/database/` — new migration adding `tournament_reader` Postgres role

**Analog:** `infrastructure/migrations/001_initial_schema.sql` (header pattern + DDL style)

**Pattern (header lines 1-7):**
```sql
-- Migration 005: Tournament Reader Role
-- Purpose: Read-only Postgres role for tournament harness DB access (D-09)
-- Date: 2026-05-08
-- Author: Tournament Harness (Phase 3)

-- ============================================================================
-- TOURNAMENT_READER ROLE
-- ============================================================================
-- D-09: tournament-harness experiment containers use this role to read klines.
-- SELECT-only. No insert / update / delete. Password injected by orchestrator.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tournament_reader') THEN
        CREATE ROLE tournament_reader WITH LOGIN PASSWORD 'CHANGE_ME_VIA_ENV';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE trading_bot TO tournament_reader;
GRANT USAGE ON SCHEMA public TO tournament_reader;
GRANT SELECT ON klines TO tournament_reader;

-- Idempotent: revoke any accidental grant beyond SELECT (defensive).
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON klines FROM tournament_reader;

-- Comments (analog convention)
COMMENT ON ROLE tournament_reader IS 'Read-only access for tournament-harness experiment containers';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
DO $$
BEGIN
    RAISE NOTICE 'Tournament reader role created with SELECT on klines';
END $$;
```

**Adaptation notes:** Numbering — confirm in plan whether this lands in `infrastructure/migrations/005_*.sql` or `database/migrations/007_*.sql` (two parallel migration directories exist; STATE/RESEARCH should clarify which is canonical for production).

---

## Shared Patterns

### Logging
**Source:** `services/ml-retraining-service/app/main.py` lines 30-33
**Apply to:** All new Python files
```python
import logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
```

### Error Handling (FastAPI endpoints)
**Source:** `services/ml-retraining-service/app/main.py` lines 207-209 (repeated 17× in the analog)
**Apply to:** All `services/tournament-harness/app/main.py` endpoints
```python
except HTTPException:
    raise
except Exception as e:
    logger.error(f"<context>: {e}", exc_info=True)
    raise HTTPException(status_code=500, detail=str(e))
```

### Pydantic Settings Singleton
**Source:** `services/ml-retraining-service/app/config/settings.py` lines 282-298
**Apply to:** `services/tournament-harness/app/config/settings.py`
```python
_settings: TournamentSettings | None = None

def get_settings() -> TournamentSettings:
    global _settings
    if _settings is None:
        _settings = TournamentSettings()
    return _settings
```

### JSON Persistence (with datetime support)
**Source:** `services/ml-retraining-service/app/core/model_trainer.py` line 696
**Apply to:** `snapshot.py`, runner's `result.json` write
```python
json.dump(payload, f, indent=2, default=str)   # default=str handles datetime
```

### Numbered SQL Migrations (idempotent)
**Source:** `infrastructure/migrations/001_initial_schema.sql` lines 9, 35, 74, 107, 139 (`CREATE TABLE IF NOT EXISTS` everywhere)
**Apply to:** `services/tournament-harness/migrations/0001_initial.sql` and the future `infrastructure/migrations/005_tournament_reader.sql`
- Filename: `NNNN_descriptive_name.sql` (4-digit zero-padded numbering for tournament; 3-digit existing for `infrastructure/migrations/`).
- Header: 4-line comment block (Migration N + Purpose + Date + Author).
- All DDL uses `IF NOT EXISTS` (or `DO $$ ... pg_roles WHERE` guard for roles).
- Trailing `RAISE NOTICE` confirmation block (Postgres) / no equivalent for SQLite — use `INSERT OR IGNORE INTO schema_version` instead.

### Service Test Layout
**Source:** `services/ml-retraining-service/tests/` directory structure
**Apply to:** `services/tournament-harness/tests/`
```
tests/
├── conftest.py           # path-import shim + shared fixtures
├── unit/
│   ├── test_runner.py
│   ├── test_orchestrator.py
│   ├── test_leaderboard_db.py
│   ├── test_tournament_loader.py
│   └── test_failure_classifier.py
└── integration/
    └── test_end_to_end_tournament.py   # uses tests/integration/conftest.py:bootstrap_stack
```

---

## No Analog Found

Files with no close match in the codebase. Planner should reach for **RESEARCH.md** (Standard Stack / Architecture Patterns / Code Examples) for these:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `services/tournament-harness/app/orchestrator.py` | service | event-driven | No in-repo precedent for Docker SDK orchestration. Docker SDK's `client.containers.run(...)` + label-based discovery + `container.wait(timeout=)` + state inspection are net-new. RESEARCH.md should provide the canonical Docker SDK call shape from D-02. |
| `services/tournament-harness/app/config/tournament_loader.py` | service | transform | No in-repo YAML+full-Cartesian enumerator. Existing `Pydantic-Settings` only loads env-vars; tournament YAML has nested architecture-specific HP grids (D-14). Must hand-write the Cartesian product + `hp_hash` (deterministic SHA-256 over sorted HP-dict JSON per D-13). |
| `services/tournament-harness/app/leaderboard/db.py` | service | CRUD | Project DB layer is async SQLAlchemy + Postgres. Leaderboard is **stdlib `sqlite3`, single-writer, synchronous** (D-17, D-18). No in-repo precedent — pattern from RESEARCH.md / stdlib docs. |
| `services/tournament-harness/app/leaderboard/queries.py` | service | request-response | No in-repo raw-SQL DSL. Must hand-write a small parameterized builder (CD-05: `--top 3 --by dsr --where "symbol=SOL AND architecture=GRU"`). RESEARCH.md should call out SQL-injection guard via `?` placeholders only — never f-string interpolation. |
| `services/tournament-harness/app/cli.py` | controller | request-response | All existing services are FastAPI-only. CLI is new surface. Stdlib `argparse` + commands (`run`, `leaderboard list`, `export-snapshot`) per CD-05. Operator's bash-completion not in scope for v1. |
| `services/tournament-harness/app/failure.py` | utility | transform | Failure classification on Docker container state inspection (`exit code 137 → oom_killed`, `inspect.State.OOMKilled`, `container.wait(timeout=) → timeout`) is novel. RESEARCH.md or Docker SDK reference should provide the State / inspect attribute names verbatim. |

---

## Metadata

**Analog search scope:**
- `services/ml-retraining-service/` (full app/ + tests/conftest.py + Dockerfile + requirements.txt)
- `infrastructure/migrations/{001_initial_schema.sql, 002_performance_history.sql}`
- `docker-compose.unified.yml:677-728` (ml-prediction stanza for opt-in profile pattern)
- `services/portfolio-manager/` (skimmed — confirmed not closer than ml-retraining)

**Files scanned:** 11 (read in full or targeted line ranges; no re-reads)
**Pattern extraction date:** 2026-05-08

**TOURN-07 grep gate (load-bearing):**
```
grep -r "def directional_accuracy\|def sharpe\|def deflated" services/tournament-harness/
# MUST return zero matches — these come from imports (returns_metrics / sharpe_metrics / cpcv) only.
```
Plan-phase: wire as CI step.
