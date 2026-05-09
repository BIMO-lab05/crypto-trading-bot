---
phase: 03-tournament-harness-core
plan: "06"
subsystem: ml-training
tags: [tournament-harness, runner, gru, metrics-bridge, tourn-07, timescaledb, keras, cpcv]

# Dependency graph
requires:
  - phase: 03-02
    provides: REGISTRY model dispatch (REGISTRY[arch].build)
  - phase: 03-04
    provides: ExperimentSpec shape, HP schema, tournament_start_ts env
  - phase: 03-05
    provides: tournament_reader DB role for klines read

provides:
  - runner/__main__.py: python -m app.runner --spec-json CLI entry point
  - runner/data.py: TimescaleDB klines loader with contamination flag + 50K floor
  - runner/sequences.py: chronological sliding-window sequence builder
  - runner/metrics_bridge.py: import-only metrics barrier (TOURN-07 gate passes)
  - Dockerfile vendored ml-retraining app/ via /opt/ml_retraining

affects:
  - 03-07 (orchestrator launches python -m app.runner containers)
  - 03-09 (integration tests consume runner output + result.json schema)
  - 03-03 (result_schema validates runner's result.json structure)

# Tech tracking
tech-stack:
  added:
    - psycopg2-binary==2.9.9 (synchronous TimescaleDB access in runner)
    - sklearn.model_selection.train_test_split (chronological 80/20 split)
  patterns:
    - TOURN-07 import-only barrier: metrics_bridge imports canonical functions, never redefines
    - Atomic result.json write via tempfile.mkstemp + os.replace + fsync (T-03-22)
    - Typed failure reasons written by runner: nan_loss, db_unreachable, train_diverged, exit_nonzero
    - RNG seeding triplet: random.seed + np.random.seed + tf.random.set_seed from experiment_seed
    - Contamination flag: start_ts < 2026-04-25 sets train_window_includes_contaminated=True (D-08)

key-files:
  created:
    - services/tournament-harness/app/runner/__main__.py
    - services/tournament-harness/app/runner/metrics_bridge.py
    - services/tournament-harness/app/runner/data.py
    - services/tournament-harness/app/runner/sequences.py
    - services/tournament-harness/app/runner/__init__.py
    - services/tournament-harness/tests/unit/test_runner_metrics_bridge.py
    - services/tournament-harness/tests/unit/test_runner_sequences.py
  modified:
    - services/tournament-harness/Dockerfile (repo-root build context, /opt/ml_retraining)
    - docker-compose.unified.yml (tournament-harness build context -> .)
    - services/tournament-harness/requirements.txt (psycopg2-binary)

key-decisions:
  - "TOURN-07 grep gate: metrics_bridge docstring rephrased to avoid literal def directional_accuracy pattern — grep gate must pass on non-test .py files"
  - "psycopg2 over asyncpg: runner is synchronous single-container; no benefit from async DB in this context"
  - "shuffle=False enforced: chronological train/test split is load-bearing per V0 finding (T-03-23)"
  - "EarlyStopping monitors val_loss not val_r2_returns: mathematically equivalent for MSE+returns (see CONTEXT.md deferred proof)"
  - "train_diverged written for val_loss non-improvement: operator review gate before leaderboard row inserted"

patterns-established:
  - "Failure-reason taxonomy (D-15): runner writes nan_loss/db_unreachable/train_diverged/exit_nonzero; orchestrator infers oom_killed/timeout from container state"
  - "PYTHONPATH precedence: /app (tournament-harness own app/) wins over /opt/ml_retraining for any conflict"
  - "Defensive USDT-suffix assertion in data.py: belt-and-braces after tournament_loader SYMBOL_RE validation"

requirements-completed: ["TOURN-01", "TOURN-02", "TOURN-07"]

# Metrics
duration: ~40min (continuation agent)
completed: 2026-05-09
---

# Phase 03 Plan 06: Per-experiment runner — load klines, train, compute honest metrics, write result.json

**Tournament experiment runner with atomic result.json, TOURN-07 import-only metrics barrier, and typed D-15 failure reasons covering nan_loss/db_unreachable/train_diverged/exit_nonzero**

## Performance

- **Duration:** ~40 min (continuation agent, resumed mid-task-3)
- **Started:** 2026-05-09T15:30:00Z
- **Completed:** 2026-05-09T15:55:00Z
- **Tasks:** 4 (tasks 1+2 completed by prior agent; tasks 3+4 completed by this agent)
- **Files modified:** 9

## Accomplishments

- TOURN-07 grep gate passes: zero `def directional_accuracy|def sharpe|def deflated` matches in non-test tournament-harness files
- `python -m app.runner --spec-json '<json>'` entry point fully implemented with all D-15 failure reasons
- Atomic result.json write (tempfile.mkstemp + fsync + os.replace) prevents half-written file race (T-03-22)

## Task Commits

1. **Task 1: Dockerfile repo-root build context** - `243c113` (feat)
2. **Task 2 RED: runner sequences failing tests** - `68fd144` (test)
3. **Task 2 GREEN: data.py + sequences.py** - `a62fce6` (feat)
4. **Task 3 RED: TOURN-07 grep gate tests** - `3cf1154` (test)
5. **Task 3 GREEN: metrics_bridge.py** - `1370053` (feat)
6. **Task 4: runner/__main__.py** - `3a79787` (feat)

## Files Created/Modified

- `services/tournament-harness/app/runner/__main__.py` - CLI entry point; full load->train->metrics->result.json pipeline
- `services/tournament-harness/app/runner/metrics_bridge.py` - Import-only metrics barrier; compute_all_metrics wraps canonical ml-retraining functions
- `services/tournament-harness/app/runner/data.py` - TimescaleDB klines loader; contamination flag; 50K row floor; USDT-suffix assertion
- `services/tournament-harness/app/runner/sequences.py` - Chronological sliding-window sequence builder (no shuffle)
- `services/tournament-harness/app/runner/__init__.py` - Package init (empty)
- `services/tournament-harness/tests/unit/test_runner_metrics_bridge.py` - TOURN-07 grep gate tests (2 pass, 1 skips on host)
- `services/tournament-harness/tests/unit/test_runner_sequences.py` - 5 unit tests for create_sequences (all pass)
- `services/tournament-harness/Dockerfile` - Repo-root build context; COPY ml-retraining app to /opt/ml_retraining; PYTHONPATH=/app:/opt/ml_retraining
- `docker-compose.unified.yml` - tournament-harness build context changed to repo root (.)
- `services/tournament-harness/requirements.txt` - Added psycopg2-binary==2.9.9

## Decisions Made

- TOURN-07 grep gate docstring fix: the previous agent wrote metrics_bridge.py with the literal text `def directional_accuracy` in the module docstring, which caused the grep gate test to fail. Fixed by rephrasing the docstring to describe the pattern without using the literal regex-matching text.
- `test_metrics_bridge_imports_resolve` skip guard: added `pytest.importorskip("app.core.returns_metrics")` alongside the existing TF skip so the test correctly skips on host where ml-retraining's app/ is not on PYTHONPATH. Test runs fully inside the container.
- EarlyStopping monitors `val_loss` not `val_r2_returns`: mathematically equivalent for MSE loss on returns target (val_loss monotonic with r2_returns on fixed validation set). Deferred v2 custom metric to CONTEXT.md.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Rephrased metrics_bridge.py docstring to avoid TOURN-07 grep gate match**
- **Found during:** Task 3 GREEN (continuing from prior agent handoff)
- **Issue:** The prior agent wrote the docstring with literal text `def directional_accuracy, sharpe, or deflated`, which the grep gate regex `def\s+(directional_accuracy|sharpe|deflated)` matched
- **Fix:** Replaced the literal pattern text with a description referencing the plan and CI for the exact regex
- **Files modified:** services/tournament-harness/app/runner/metrics_bridge.py
- **Verification:** TOURN-07 grep gate test passes; grep -r returns 0 non-test matches
- **Committed in:** `1370053` (Task 3 GREEN commit)

**2. [Rule 1 - Bug] Added app.core skip guard to test_metrics_bridge_imports_resolve**
- **Found during:** Task 4 verification run
- **Issue:** `test_metrics_bridge_imports_resolve` only skipped on missing tensorflow, but app.core (ml-retraining) is also absent on host. The test's own docstring said "Skip if the import would fail" but the skip was incomplete.
- **Fix:** Added `pytest.importorskip("app.core.returns_metrics")` before the actual import to correctly skip on host
- **Files modified:** services/tournament-harness/tests/unit/test_runner_metrics_bridge.py
- **Verification:** Test suite: 7 passed, 1 skipped (correct — skips on host, runs in container)
- **Committed in:** `3a79787` (Task 4 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs introduced by prior agent's incomplete GREEN commit)
**Impact on plan:** Both fixes essential for test suite correctness and grep gate compliance. No scope creep.

## Issues Encountered

- Continuation required because prior agent's Task 3 GREEN never ran: `metrics_bridge.py` was created but the docstring contained the literal grep pattern, causing the TOURN-07 test to fail. Fixed before committing.
- `grep -c` exit code 1 on zero matches (standard grep behavior) — acceptance check script false-alarmed; verified with separate `wc -l` command confirming 0 matches.

## Known Stubs

None — all result.json fields are populated from real computation or typed failure paths. The `git_sha` field reads from `GIT_SHA` env var (injected by orchestrator at container launch per 03-07 spec).

## Threat Flags

None — no new network endpoints, auth paths, or file access patterns introduced beyond what the plan's threat model covers (T-03-19 through T-03-23 all addressed).

## TOURN-07 Grep Gate Verification

```
grep -r "def directional_accuracy\|def sharpe\|def deflated" \
    services/tournament-harness/ --include='*.py' | grep -v '/tests/' | wc -l
# Result: 0 (PASS)
```

## D-15 Failure Reason Coverage

| Reason | Written by | Trigger |
|--------|-----------|---------|
| `nan_loss` | runner | NaN detected in training loss history |
| `db_unreachable` | runner | ConnectionError from psycopg2.OperationalError |
| `train_diverged` | runner | ValueError (insufficient klines) OR val_loss non-improvement |
| `exit_nonzero` | runner | Any uncaught exception during pipeline |
| `oom_killed` | orchestrator | Container exit code 137 (inferred, not written by runner) |
| `timeout` | orchestrator | Container wall-time exceeded resource_caps.max_seconds |

## User Setup Required

None — runner is invoked inside experiment containers by the orchestrator (03-07). No manual configuration required.

## Next Phase Readiness

- 03-07 (orchestrator) can now launch `python -m app.runner --spec-json '...'` containers
- 03-09 (integration tests) can validate the full load->train->metrics->result.json pipeline against live TimescaleDB
- TOURN-07 grep gate is clean and will remain enforced by the unit test suite

---
*Phase: 03-tournament-harness-core*
*Completed: 2026-05-09*
