---
id: 09-01-evidence-loop-driver
phase: 09-ml-re-enablement-gate
plan: 01
wave: 1
type: execute
mode: standard
depends_on: []
autonomous: true
requirements:
  - MLGATE-01
files_modified:
  - services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql
  - scripts/forward_paper_test/run_evidence_loop.py
  - scripts/forward_paper_test/tests/test_run_evidence_loop.py
tags:
  - mlgate
  - evidence-loop
  - tournament-harness
  - psr-ci
  - phase-9
decisions:
  - D-09-01-01 — Table name resolution (locked carry-in from 08-CONTEXT.md lines 95-101 and 08-01-SUMMARY.md "Decisions Made"). REQUIREMENTS.md / ROADMAP.md success criteria reference a `tournament_results` table that does NOT exist; the actual schema is `leaderboard` in `services/tournament-harness/migrations/0001_initial.sql`. Phase 9 reads and writes the `leaderboard` table directly. The wording in REQUIREMENTS.md is a known documentation bug to be closed in a follow-up docs commit (same pattern as the Phase 8 carry-over). All acceptance criteria below use the literal identifier `leaderboard`.
  - D-09-01-02 — Schema extension lands as `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` adding columns `run_date TEXT` (ISO-8601 UTC, NULL until backfilled) and `psr_ci_published INTEGER NOT NULL DEFAULT 0 CHECK (psr_ci_published IN (0, 1))` to the existing `leaderboard` table. Both are nullable-OK / default-OK so the migration is non-destructive against existing rows; no `tournament_results` view or alias table is introduced (rejected because it would split the read surface and break TOURN-07 grep-gate scope).
  - D-09-01-03 — `run_evidence_loop.py` is an idempotent **orchestrator** over `psr_ci.compute_psr_with_bootstrap_ci` and the existing `leaderboard` rows; it does NOT re-implement bootstrap PSR/CI math (TOURN-07 spirit: canonical kernels imported, never re-implemented — see psr_ci.py lines 8-23). Idempotency natural key = the existing leaderboard composite PK `(architecture, symbol, horizon, target_mode, hp_hash, run_id)`; resume = `SELECT max(created_at) FROM leaderboard WHERE psr_ci_published = 0`.
  - D-09-01-04 — ≥7-day accrual rule is a wall-clock check on `run_date` BEFORE flipping `psr_ci_published=1`: `now_utc - min(run_date for this (architecture, symbol, horizon, target_mode, hp_hash) group) >= timedelta(days=7)`. Below 7 days: skip publish, log `MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open days_observed=N`. At or above 7 days: compute PSR-CI via `compute_psr_with_bootstrap_ci`, then UPDATE the row's `psr_ci_published=1` in a single transaction.
must_haves:
  truths:
    - "`python -m scripts.forward_paper_test.run_evidence_loop` exits 0 against a seeded leaderboard fixture (no duplicate rows created, idempotent on re-run)."
    - "Re-running the same command on an unchanged fixture produces the same final `leaderboard` row count and the same set of `psr_ci_published=1` rows — two-run-same-count invariant."
    - "The driver resumes from the last persisted row: with N rows where the first 3 are already published and the next 4 are in-accrual, a re-run reads exactly those 4 in-accrual rows and publishes only the ones whose 7-day window has elapsed."
    - "Below the 7-day accrual window, the driver logs `MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open` and does NOT flip `psr_ci_published`."
    - "Migration 0002 applies cleanly against a fresh sqlite database initialised from 0001; `PRAGMA table_info(leaderboard)` after migration includes columns `run_date` and `psr_ci_published`."
  artifacts:
    - path: "services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql"
      provides: "MLGATE schema extensions on `leaderboard` table (run_date, psr_ci_published)"
      contains: "ALTER TABLE leaderboard ADD COLUMN run_date"
      contains_2: "ALTER TABLE leaderboard ADD COLUMN psr_ci_published"
    - path: "scripts/forward_paper_test/run_evidence_loop.py"
      provides: "Idempotent ≥7-day evidence accrual + PSR-CI publish orchestrator (MLGATE-01)"
      exports: ["main", "run_evidence_loop", "DEFAULT_TOURNAMENT_DB_PATH", "ACCRUAL_WINDOW_DAYS"]
      contains_3: "MLGATE_EVIDENCE_LOOP"
    - path: "scripts/forward_paper_test/tests/test_run_evidence_loop.py"
      provides: "Idempotency + accrual-window + resume unit tests (≥8 cases)"
      min_tests: 8
  key_links:
    - from: "scripts/forward_paper_test/run_evidence_loop.py"
      to: "scripts/forward_paper_test/psr_ci.py::compute_psr_with_bootstrap_ci"
      via: "module import (canonical PSR-CI kernel — never re-implemented)"
      pattern: "from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci"
    - from: "scripts/forward_paper_test/run_evidence_loop.py"
      to: "leaderboard table"
      via: "sqlite3.connect(db_path) + parameterised SELECT/UPDATE"
      pattern: "FROM leaderboard"
    - from: "services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql"
      to: "services/tournament-harness/migrations/0001_initial.sql"
      via: "schema_version INSERT (version=2)"
      pattern: "INSERT OR IGNORE INTO schema_version"

# Coverage trace (each item must map to ≥1 task acceptance criterion)
coverage_trace:
  - id: MLGATE-01
    source: "REQUIREMENTS.md MLGATE-01 + ROADMAP Phase 9 success criterion #1"
    tasks: [task-1, task-2, task-3]
---

<objective>
Deliver MLGATE-01: an idempotent ≥7-day forward-paper-test evidence accrual + PSR-CI publish orchestrator. The driver script (`run_evidence_loop.py`) loops over un-published leaderboard rows, applies the 7-day wall-clock accrual rule, computes PSR-CI via the canonical kernel from `psr_ci.py`, and marks rows `psr_ci_published=1` exactly once per natural key. Two-run-same-count idempotency invariant is verifiable from a seeded SQLite fixture.

Purpose: MLGATE-02 (Plan 09-02) auto-flips `ENABLE_ML_PREDICTIONS` based on `dsr > 0.95 AND psr_ci_published = 1 AND run_date within 14 days`. Without MLGATE-01 writing the `psr_ci_published` flag and stamping `run_date`, the auto-flip can never enable. Phase 9 is incoherent without this driver.

Output:
- Migration `0002_mlgate_evidence_columns.sql` — adds `run_date TEXT` + `psr_ci_published INTEGER` columns to `leaderboard`.
- `scripts/forward_paper_test/run_evidence_loop.py` — CLI orchestrator + library entry-points.
- `scripts/forward_paper_test/tests/test_run_evidence_loop.py` — ≥8 unit tests covering idempotency, accrual-window skip, resume, error paths.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/REQUIREMENTS.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md

@services/tournament-harness/migrations/0001_initial.sql
@scripts/forward_paper_test/psr_ci.py
@scripts/forward_paper_test/profiles.py
@scripts/forward_paper_test/run_isolation.py
@scripts/forward_paper_test/tests/test_psr_ci.py

<interfaces>
<!-- Contracts the executor will consume — extracted from codebase; do NOT re-discover -->

From `services/tournament-harness/migrations/0001_initial.sql:9-43`:
```sql
CREATE TABLE IF NOT EXISTS leaderboard (
    run_id              TEXT NOT NULL,
    tournament_id       TEXT NOT NULL,
    architecture        TEXT NOT NULL CHECK (architecture IN ('gru','lstm','transformer','tcn')),
    symbol              TEXT NOT NULL,
    horizon             INTEGER NOT NULL CHECK (horizon >= 1 AND horizon <= 256),
    target_mode         TEXT NOT NULL CHECK (target_mode IN ('price','log_returns')),
    hp_hash             TEXT NOT NULL,
    r2_returns          REAL,
    dir_acc_corrected   REAL,
    oos_sharpe          REAL,
    psr                 REAL,
    dsr                 REAL,
    cpcv_dsr            REAL,
    train_seconds       REAL,
    git_sha             TEXT NOT NULL,
    tournament_start_ts TEXT NOT NULL,
    train_window_includes_contaminated INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL CHECK (status IN ('success','failed')),
    failure_reason      TEXT,
    failure_stderr_tail TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (architecture, symbol, horizon, target_mode, hp_hash, run_id)
);
```

From `scripts/forward_paper_test/psr_ci.py:151-229` — canonical kernel to import (do NOT re-implement):
```python
def compute_psr_with_bootstrap_ci(
    returns: np.ndarray,
    *,
    seed: int,
    n_resamples: int = 10_000,
    block_size: Optional[int] = None,
) -> dict:
    """Returns dict with keys: psr_point, psr_ci_low, psr_ci_high, n_resamples,
    n_resamples_valid, block_size, seed, n_bars. Raises ValueError if len(returns) < 30."""
```

From `scripts/forward_paper_test/psr_ci.py:232-275`:
```python
def load_run_returns(run_dir: Path) -> np.ndarray:
    """Load per-trade log-returns from completed run's run.json. Raises FileNotFoundError
    if run.json missing, ValueError if returns empty or contains NaN."""
```

From `services/trading-engine/app/preflight/checks.py:45-49` (already-existing markers — schema this plan must NOT collide with):
```python
_MLGATE_MARKER_PATH = "/run/mlgate_auto_flip.json"  # Plan 09-02 writes here
_DEFAULT_TOURNAMENT_DB_PATH = "/data/tournament.db"  # SAME default used by this plan
_DSR_FLOOR = 0.95
```

From `scripts/forward_paper_test/__init__.py`:
```python
# Forward-paper-test apparatus for Tier-1 opt-in features.
# Host-runnable package — no Docker dependency.
```
The driver MUST stay host-runnable (no docker dependency) — same constraint as `psr_ci.py` and `run_isolation.py`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add migration 0002 — `run_date` and `psr_ci_published` columns on `leaderboard`</name>
  <read_first>
    - services/tournament-harness/migrations/0001_initial.sql (existing schema — column types, CHECK constraints, schema_version table convention)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md lines 95-101 (DSR evidence source — locked decision to use `leaderboard` not `tournament_results`)
    - .planning/phases/08-pre-live-preflight/08-01-SUMMARY.md lines 153-177 (Phase 8's analysis of the schema mismatch — Phase 9 closes this loop)
    - services/tournament-harness/app/db/*.py if any migrations runner exists (locate the auto-apply path; if not, document SQL is applied via direct sqlite3.execute on first connect)
  </read_first>
  <behavior>
    - Migration applies cleanly against a fresh sqlite db initialised from `0001_initial.sql` — no errors on first run.
    - After migration: `PRAGMA table_info(leaderboard)` includes columns `run_date` (TEXT, nullable) and `psr_ci_published` (INTEGER, default 0).
    - Migration is idempotent — applying twice does NOT error (`ADD COLUMN IF NOT EXISTS` is not standard SQLite; guard with the `schema_version` table check pattern from 0001 line 69, and use `ALTER TABLE leaderboard ADD COLUMN` only if version=2 not yet present).
    - After migration: `SELECT version FROM schema_version` includes a row `version=2, description='MLGATE evidence columns (run_date, psr_ci_published)'`.
    - Existing rows from 0001 survive — no DROP, no DELETE, no renamed columns.
  </behavior>
  <action>
    Per D-09-01-02, create `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` that:
    1. Wraps the ALTER TABLE statements in a conditional pattern: first `SELECT COUNT(*) FROM schema_version WHERE version = 2` — if zero, run the ALTERs; otherwise skip (SQLite has no native IF NOT EXISTS for columns, so use the existing migration-version idempotency pattern from 0001 line 69).
    2. ALTER 1: `ALTER TABLE leaderboard ADD COLUMN run_date TEXT;` — ISO-8601 UTC string; nullable so existing rows (which have only `created_at` and `tournament_start_ts`) survive.
    3. ALTER 2: `ALTER TABLE leaderboard ADD COLUMN psr_ci_published INTEGER NOT NULL DEFAULT 0 CHECK (psr_ci_published IN (0, 1));` — DEFAULT 0 so existing rows acquire the column with `0` retroactively.
    4. Create an index `idx_leaderboard_psr_published ON leaderboard(psr_ci_published, run_date DESC);` to make the MLGATE-02 lookup query fast (Plan 09-02 reads `WHERE psr_ci_published = 1 AND dsr > 0.95 ORDER BY run_date DESC LIMIT 1`).
    5. End with `INSERT OR IGNORE INTO schema_version (version, description) VALUES (2, 'MLGATE evidence columns (run_date, psr_ci_published)');` — same pattern as 0001 line 69.
    Note: per CLAUDE.md gotcha about WSL bind-mount races, the migration file is read-only at runtime and does not need world-writable permissions.
    If a migrations runner module exists (e.g. `services/tournament-harness/app/db/migrations.py`), this plan does NOT modify it — runners that already scan `migrations/*.sql` in lexical order will pick up `0002_*.sql` automatically. If no runner is found, document the gap in the SUMMARY and note that the SQL is applied by the orchestrator's first connect (tournament-harness boot path); do not invent a new runner.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; python3 -c "
import sqlite3, tempfile, pathlib
mig1 = pathlib.Path('services/tournament-harness/migrations/0001_initial.sql').read_text()
mig2 = pathlib.Path('services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql').read_text()
with tempfile.NamedTemporaryFile(suffix='.db') as f:
    conn = sqlite3.connect(f.name)
    conn.executescript(mig1)
    conn.executescript(mig2)
    # Idempotency: applying twice must not raise.
    conn.executescript(mig2)
    cols = {r[1] for r in conn.execute('PRAGMA table_info(leaderboard)')}
    assert 'run_date' in cols, f'run_date missing: {cols}'
    assert 'psr_ci_published' in cols, f'psr_ci_published missing: {cols}'
    versions = [r[0] for r in conn.execute('SELECT version FROM schema_version ORDER BY version')]
    assert 2 in versions, f'schema_version 2 missing: {versions}'
    print('OK migration 0002 applies and is idempotent; cols=', sorted(cols))
"</automated>
  </verify>
  <acceptance_criteria>
    - File `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` exists and is non-empty.
    - `grep -c "ADD COLUMN run_date" services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` returns 1.
    - `grep -c "ADD COLUMN psr_ci_published" services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` returns 1.
    - `grep -c "idx_leaderboard_psr_published" services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` returns 1.
    - `grep -c "INSERT OR IGNORE INTO schema_version" services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql` returns 1 (matches the line `... VALUES (2, '...')`).
    - The Python verify block above prints `OK migration 0002 applies and is idempotent; cols= [...]` and includes both new columns in the printed list.
  </acceptance_criteria>
  <done>
    Migration file exists; the verify Python script exits 0 with the OK line. Existing leaderboard rows from a 0001-only fixture continue to read back unchanged (verified by an additional column-count comparison in the unit tests of Task 3).
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Implement `run_evidence_loop.py` driver (idempotent + resume + 7-day accrual)</name>
  <read_first>
    - scripts/forward_paper_test/psr_ci.py (canonical PSR-CI kernel — IMPORT, do NOT re-implement; mirrors TOURN-07 spirit)
    - scripts/forward_paper_test/run_isolation.py (existing CLI module — copy the argparse + subprocess + PAPER_TRADING_MODE precondition shape; this plan also enforces PAPER mode)
    - scripts/forward_paper_test/profiles.py (Tier-1 profile shape — reference for future symbol/feature parametrisation; not modified here)
    - services/tournament-harness/migrations/0001_initial.sql AND the 0002 file from Task 1 (full schema knowledge for the SELECT/UPDATE queries)
    - services/trading-engine/app/preflight/checks.py lines 199-271 (canonical DSR query shape — Plan 09-02 reuses the same connection style; stay consistent)
  </read_first>
  <behavior>
    - `python -m scripts.forward_paper_test.run_evidence_loop --db-path <fixture.db> --dry-run` on an empty leaderboard exits 0 and logs `MLGATE_EVIDENCE_LOOP action=skip reason=no_rows`.
    - With N rows where psr_ci_published=0 and the earliest `run_date` is within the last 6 days, the driver logs `MLGATE_EVIDENCE_LOOP action=skip reason=accrual_window_open days_observed=6` for the affected group and exits 0 WITHOUT flipping any row.
    - With N rows where psr_ci_published=0 and the earliest `run_date` is ≥7 days ago AND the row has non-NULL returns-source metadata (or a synthetic returns array supplied via --returns-source for tests), the driver: (a) computes PSR-CI via `compute_psr_with_bootstrap_ci`, (b) UPDATEs `psr_ci_published=1` on the row matching the natural-key composite PK, (c) logs `MLGATE_EVIDENCE_LOOP action=publish run_id=<id> psr_point=<float> psr_ci_low=<float> psr_ci_high=<float>`, (d) exits 0.
    - Re-running the driver on the same db produces ZERO additional `action=publish` log lines for already-published rows (idempotency invariant — driver must `WHERE psr_ci_published = 0` filter at SELECT time, NOT post-filter).
    - Two-run-same-row-count invariant: `SELECT COUNT(*) FROM leaderboard` after run-1 equals `SELECT COUNT(*) FROM leaderboard` after run-2 (driver only UPDATEs, never INSERTs or DELETEs).
    - On sqlite3.Error (db locked, missing table), the driver logs `MLGATE_EVIDENCE_LOOP action=error reason=<exception class>` and exits 2 (NOT 1 — exit code 1 reserved for "ran but found no eligible rows").
    - Driver refuses to run if `TRADING_MODE=LIVE` in env (same paranoia as `run_isolation.py:_check_paper_mode_precondition`).
  </behavior>
  <action>
    Per D-09-01-03 and D-09-01-04, create `scripts/forward_paper_test/run_evidence_loop.py` with:
    1. **Module constants** at top: `DEFAULT_TOURNAMENT_DB_PATH = "/data/tournament.db"` (same literal as `services/trading-engine/app/preflight/checks.py:49` — single source of truth for the path), `ACCRUAL_WINDOW_DAYS = 7`, `LOG_PREFIX = "MLGATE_EVIDENCE_LOOP"`.
    2. **Public entry-point** `def run_evidence_loop(db_path: str = DEFAULT_TOURNAMENT_DB_PATH, *, dry_run: bool = False, returns_source: Path | None = None, now: datetime | None = None) -> dict` returning `{"published": int, "skipped": int, "errors": int}`. The `now` parameter is injectable for deterministic tests (default `datetime.now(timezone.utc)`).
    3. **Step 1 — paper-mode precondition**: copy the shape from `run_isolation.py:_check_paper_mode_precondition` (refuse to start if `TRADING_MODE=LIVE`; allow PAPER and unset).
    4. **Step 2 — SELECT eligible rows**: `SELECT architecture, symbol, horizon, target_mode, hp_hash, run_id, run_date, dsr, oos_sharpe FROM leaderboard WHERE psr_ci_published = 0 AND status = 'success' AND run_date IS NOT NULL ORDER BY run_date ASC` (uses the new `idx_leaderboard_psr_published` index from Task 1).
    5. **Step 3 — group by natural key** (architecture, symbol, horizon, target_mode, hp_hash): for each group, find `min(run_date)`. If `(now - min_run_date).days < ACCRUAL_WINDOW_DAYS`, log skip and continue.
    6. **Step 4 — compute PSR-CI**: read per-trade log-returns. Source preference:
       (a) if `returns_source` argument is a path to a JSON file with `{"returns": [...]}`, load via `psr_ci.load_run_returns` (host-test convenience);
       (b) else load from `.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json` (paths align with `run_isolation.py:_EVIDENCE_BASE`).
       If neither source resolvable, log `action=skip reason=returns_unavailable run_id=<id>` and continue (do NOT crash; missing returns must not break the loop).
    7. **Step 5 — UPDATE row**: in a single transaction: `UPDATE leaderboard SET psr_ci_published = 1 WHERE architecture=? AND symbol=? AND horizon=? AND target_mode=? AND hp_hash=? AND run_id=?` with the full composite PK. The UPDATE MUST be parameterised (sqlite3 placeholders) per `services/trading-engine/app/preflight/checks.py` style; never f-string interpolate user-controlled values into SQL.
    8. **Step 6 — emit log line** at INFO: `f"{LOG_PREFIX} action=publish run_id={run_id} psr_point={psr['psr_point']:.4f} psr_ci_low={psr['psr_ci_low']:.4f} psr_ci_high={psr['psr_ci_high']:.4f}"`.
    9. **`__main__` block**: `argparse` with `--db-path`, `--dry-run`, `--returns-source`. Exit code: `0` if `errors == 0`, `2` on sqlite3.Error (caught at the outer try/except), `1` on argparse error / paper-mode violation.
    10. **NEVER** call `compute_psr_with_bootstrap_ci` if `dry_run=True` — the dry-run path only enumerates eligible rows and prints what would happen. This is the equivalent of `run_isolation.py --dry-run` for CI / pre-flight inspection.

    **Constraints carried in from the codebase:**
    - Per the project memory `feedback_local_test_setup.md`: the driver MUST run host-side without docker (matches `scripts/forward_paper_test/__init__.py` comment "Host-runnable package — no Docker dependency"). No new docker / RabbitMQ / Redis dependencies.
    - Per CLAUDE.md "Search rule": this plan does NOT search for things ad-hoc; all required interfaces are listed in `<context>` already.
    - Per ADR-010 paper-relaxed cap and CLAUDE.md trading-mode discipline: this driver is paper-only.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; PYTHONPATH=. python3 -m scripts.forward_paper_test.run_evidence_loop --help 2&gt;&amp;1 | head -20</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/forward_paper_test/run_evidence_loop.py` exists.
    - `python3 -m scripts.forward_paper_test.run_evidence_loop --help` exits 0 and shows the three flags (`--db-path`, `--dry-run`, `--returns-source`).
    - `grep -c "from scripts.forward_paper_test.psr_ci import compute_psr_with_bootstrap_ci" scripts/forward_paper_test/run_evidence_loop.py` returns 1 (canonical kernel imported, not re-implemented — TOURN-07 spirit).
    - `grep -c "MLGATE_EVIDENCE_LOOP" scripts/forward_paper_test/run_evidence_loop.py` returns ≥4 (constant + 3 action variants `publish`, `skip`, `error`).
    - `grep -c "WHERE psr_ci_published = 0" scripts/forward_paper_test/run_evidence_loop.py` returns ≥1 (idempotency filter at SELECT time, not post-filter).
    - `grep -c "ACCRUAL_WINDOW_DAYS = 7" scripts/forward_paper_test/run_evidence_loop.py` returns 1.
    - `grep -c "DEFAULT_TOURNAMENT_DB_PATH = \"/data/tournament.db\"" scripts/forward_paper_test/run_evidence_loop.py` returns 1 (matches the literal in `services/trading-engine/app/preflight/checks.py:49` — single source of truth).
    - No fenced `subprocess.run(.*sql)` patterns: `grep -E "subprocess.*sql|os\\.system" scripts/forward_paper_test/run_evidence_loop.py | wc -l` returns 0 (all DB ops go through `sqlite3.connect` + parameterised cursor calls).
    - Refuses to run under TRADING_MODE=LIVE: `TRADING_MODE=LIVE python3 -m scripts.forward_paper_test.run_evidence_loop --db-path /tmp/none.db --dry-run; echo exit=$?` outputs `exit=1`.
  </acceptance_criteria>
  <done>
    Driver module exists, --help works, all 8 acceptance grep gates pass, and TRADING_MODE=LIVE refusal is verified. Task 3 unit tests will exercise the full SELECT/UPDATE behaviour.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Unit tests — idempotency, accrual-window skip, resume, error paths (≥8 cases)</name>
  <read_first>
    - scripts/forward_paper_test/tests/test_psr_ci.py (existing test pattern for this package — sqlite + numpy fixtures, monkeypatch.setenv, no docker)
    - scripts/forward_paper_test/tests/test_profiles.py (pytest module shape — parametrize, plain assert)
    - services/trading-engine/tests/test_preflight_checks.py (Phase 8 unit test patterns for DSR-evidence sqlite fixtures — `test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` builds a leaderboard fixture; reuse this fixture-build pattern)
    - The new `run_evidence_loop.py` from Task 2 + the new migration file from Task 1
  </read_first>
  <behavior>
    - `test_evidence_loop_empty_db_skips_cleanly` — no eligible rows → returns `{"published": 0, "skipped": 0, "errors": 0}`, exits 0.
    - `test_evidence_loop_window_open_skips_without_publish` — 1 row with `run_date` = now-3d → returns `{"published": 0, "skipped": 1, "errors": 0}`, no UPDATE happens (verify `psr_ci_published` remains 0 in the DB).
    - `test_evidence_loop_window_closed_publishes` — 1 row with `run_date` = now-8d + a provided returns array of length 40 → returns `{"published": 1, "skipped": 0, "errors": 0}`, the row's `psr_ci_published` flips to 1.
    - `test_evidence_loop_idempotent_two_runs` — seed 3 eligible rows + 1 already-published row → run twice, both runs return same row counts, the published count after run-2 is identical to after run-1.
    - `test_evidence_loop_two_runs_same_row_count` — `SELECT COUNT(*) FROM leaderboard` after run-1 == after run-2 (the driver MUST NOT INSERT or DELETE).
    - `test_evidence_loop_resume_from_partial_state` — seed N rows, mark first 3 as already published (`psr_ci_published=1`), run driver, verify it processes only the remaining N-3 rows.
    - `test_evidence_loop_dry_run_does_not_mutate` — `dry_run=True` on a fully-eligible fixture → no UPDATEs happen, log lines emitted as if publishing.
    - `test_evidence_loop_refuses_live_mode` — `TRADING_MODE=LIVE` env → SystemExit(1) with stderr containing "paper-only" or "TRADING_MODE=LIVE".
  </behavior>
  <action>
    Per D-09-01-03, create `scripts/forward_paper_test/tests/test_run_evidence_loop.py` with:
    1. **Shared fixture** `def _build_leaderboard_db(tmp_path) -> Path`: creates an empty sqlite, runs migrations 0001 + 0002 (loaded via `pathlib.Path.read_text()`), returns the db path. Mirror the pattern from `services/trading-engine/tests/test_preflight_checks.py` (the `test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` fixture).
    2. **Helper** `def _insert_row(conn, *, run_id, run_date_iso, psr_ci_published=0, dsr=0.97, ...)`: inserts a single leaderboard row with all NOT NULL columns from 0001 satisfied. Use `architecture='gru'`, `symbol='BTCUSDT'`, `horizon=5`, `target_mode='log_returns'`, `hp_hash='deadbeef'`, `tournament_id='t-test'`, `git_sha='abc1234'`, `tournament_start_ts='2026-05-09T00:00:00Z'`, `status='success'` — the natural-key fields can vary per test via kwargs.
    3. **Helper** `def _returns_json(tmp_path, returns)`: writes a `{"returns": [...]}` JSON file (40+ values to satisfy `compute_psr_with_bootstrap_ci`'s `len >= 30` guard) and returns the path. Use a deterministic numpy seed for reproducibility.
    4. **Implement the 8 named tests** above, each using `_build_leaderboard_db` + `_insert_row`. Inject `now=datetime(2026, 5, 16, tzinfo=timezone.utc)` so window math is deterministic.
    5. Tests MUST run with `pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py -xvs` host-side (no docker — per package convention in `__init__.py`).
    6. Each test must explicitly assert on the **logged literal** `MLGATE_EVIDENCE_LOOP action=<value> reason=<reason>` using `caplog` (pytest builtin). The logged literal is a contract surface — Plan 09-03 reads similar literals for the digest.
  </action>
  <verify>
    <automated>cd /mnt/d/Bimo_max/crypto-trading-bot &amp;&amp; pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py -v 2&gt;&amp;1 | tail -25</automated>
  </verify>
  <acceptance_criteria>
    - File `scripts/forward_paper_test/tests/test_run_evidence_loop.py` exists.
    - `pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py --collect-only -q | tail -3` shows at least 8 test functions.
    - All 8 tests PASS: `pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py -v 2&gt;&amp;1 | grep -c "PASSED"` returns ≥8.
    - Zero failures: `pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py -v 2&gt;&amp;1 | grep -cE "(FAILED|ERROR)"` returns 0.
    - `grep -c "caplog" scripts/forward_paper_test/tests/test_run_evidence_loop.py` returns ≥6 (most tests verify log literals as contract surface).
    - `grep -cE "def test_evidence_loop_(empty_db|window_open|window_closed|idempotent|two_runs_same|resume|dry_run|refuses_live)" scripts/forward_paper_test/tests/test_run_evidence_loop.py` returns 8 (all 8 named tests present).
  </acceptance_criteria>
  <done>
    All 8 unit tests defined and pass. Idempotency and two-run-same-count invariants verified against a seeded SQLite fixture. The driver's behavior matches MLGATE-01 success criteria #1 (verbatim) — idempotent across restart, resumes from last persisted row, two-run-same-final-count.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Operator shell → driver script | Operator runs `python -m scripts.forward_paper_test.run_evidence_loop`; env vars (TRADING_MODE, PAPER_TRADING_MODE) are operator-controlled and untrusted at boot. |
| Driver script → tournament-harness sqlite db | Single-process file-backed db; tournament-harness orchestrator (separate process) may hold writer lock. Driver only writes the `psr_ci_published` column; never modifies `dsr`, `r2_returns`, or other skill metrics. |
| Driver script → `psr_ci.py` kernel | Canonical PSR-CI kernel — TOURN-07 grep gate already enforces "no re-implementation". |
| `returns_source` file (test only) → driver | JSON file path; trust comes from operator-controlled test fixture in tmp_path. Test surface only — production reads from `.planning/evidence/forward_paper_test/<flag>/<run_id>/run.json` which is operator-owned. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-09-01-01 | Tampering | Forged DSR row inserted via driver | accept | Driver only UPDATEs `psr_ci_published` (never inserts new rows or modifies skill metrics). DSR values are written exclusively by tournament-harness orchestrator (separate trust domain). Documented in Task 2 action step 7. |
| T-09-01-02 | Tampering | Forged `run_date` to bypass 7-day accrual | mitigate | `run_date` is written by tournament-harness when the row is created, not by this driver. Driver READS `run_date` and applies the 7-day rule against a `now` clock value. Future work (Phase 11 LIVECLOSE-03) seals this further with a separate audit log. |
| T-09-01-03 | Information Disclosure | sqlite3.Error message containing filesystem paths leaks via log | mitigate | Mirror `services/trading-engine/app/preflight/checks.py:246-251` — error log emits `type(e).__name__` only, never `str(e)`. Acceptance assertion grep-checks the driver does not interpolate `{e}` raw into log lines. |
| T-09-01-04 | Denial of Service | Long-running PSR-CI bootstrap (10000 resamples × N rows) blocks operator shell | accept | Operator runs the driver synchronously; bounded by `len(returns)` which is ≤ a few hundred per row per CLAUDE.md forward-paper-test conventions. No daemon mode; --dry-run shortcut available for fast inspection. |
| T-09-01-05 | Elevation of Privilege | Driver invoked under TRADING_MODE=LIVE accidentally publishes evidence that gates LIVE bootup | mitigate | Step 1 of Task 2 action: copy `run_isolation.py:_check_paper_mode_precondition` — refuse to run with `TRADING_MODE=LIVE` and exit 1 with stderr message. Acceptance assertion verifies exit code 1. |
| T-09-01-06 | Spoofing | Attacker writes a fake `returns_source` JSON to flip a row | accept | The `returns_source` flag is a developer-only test convenience (documented in Task 2 action step 6). Production paths resolve under `.planning/evidence/forward_paper_test/` which is git-tracked + operator-reviewed. |
</threat_model>

<verification>
1. **Migration applies cleanly** — Task 1 verify Python script exits 0 with OK line.
2. **Driver runs host-side without docker** — `python3 -m scripts.forward_paper_test.run_evidence_loop --help` exits 0; no `docker compose` invocation in the module source.
3. **Idempotency invariant** — Task 3's `test_evidence_loop_idempotent_two_runs` passes; running the driver twice on the same DB does not flip an already-published row twice.
4. **Two-run-same-count invariant** — Task 3's `test_evidence_loop_two_runs_same_row_count` passes; the driver never INSERTs/DELETEs.
5. **7-day accrual rule honored** — Task 3's `test_evidence_loop_window_open_skips_without_publish` and `test_evidence_loop_window_closed_publishes` both pass with the boundary at 6 days (skip) and 8 days (publish).
6. **Paper-mode precondition** — `TRADING_MODE=LIVE python3 -m scripts.forward_paper_test.run_evidence_loop --db-path /tmp/x.db --dry-run` exits 1.
7. **Canonical-kernel reuse** — `grep -c "compute_psr_with_bootstrap_ci" scripts/forward_paper_test/run_evidence_loop.py` returns ≥1; no inlined bootstrap math (TOURN-07 spirit; acceptance asserts no `np.percentile` inside the driver module).
</verification>

<success_criteria>
- All 8 unit tests in `scripts/forward_paper_test/tests/test_run_evidence_loop.py` PASS host-side.
- The migration 0002 idempotency Python verify exits 0.
- Driver refuses LIVE mode (exit 1).
- `MLGATE_EVIDENCE_LOOP` log literal appears ≥4 times in the driver source (`publish`, `skip`, `error`, constant).
- ROADMAP Phase 9 success criterion #1 holds: re-running `python -m scripts.forward_paper_test.run_evidence_loop` produces the same final row count and no duplicate publishes.
</success_criteria>

<output>
After completion, create `.planning/phases/09-ml-re-enablement-gate/09-01-SUMMARY.md` with:
- `requires`: [] (Wave 1, no dependencies on other Phase 9 plans)
- `provides`: schema migration 0002 (run_date, psr_ci_published columns + new index); run_evidence_loop driver as orchestrator over psr_ci kernel; test surface for idempotency
- `affects`: phase 09-02 (auto-flip reads `psr_ci_published=1 AND run_date within 14d`), phase 11 LIVECLOSE-03 (operator runs this driver to accrue evidence)
- Decisions made — including the locked carry-in re: `leaderboard` table name
- Three commit hashes (one per task)
</output>
