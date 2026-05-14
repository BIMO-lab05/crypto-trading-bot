---
phase: 05-ml-cleanup-post-v0
plan: 02
subsystem: tournament-harness
tags: [tournament, ml-experiment, different-horizon, mlcl-02, insufficient-data]
requirements: [MLCL-02]
dependency_graph:
  requires:
    - 05-01 (forward-paper-test apparatus, PSR-CI kernel)
    - Phase 3 tournament harness (run + leaderboard + snapshot)
    - Phase 4 open-pr CLI (significance, ensemble, dry-run)
  provides:
    - T0.1.x experiment YAML config (t0_1_x_horizon_sweep)
    - MLCL-02 decision record with binding terminal verdict (INSUFFICIENT_DATA)
    - Integration test pinning evidence-and-verdict contract (5 assertions)
  affects:
    - services/tournament-harness/app/config/ (new YAML)
    - .planning/evidence/t0_1_x/ (new evidence directory)
    - services/tournament-harness/tests/integration/ (new test)
tech-stack:
  added: []
  patterns:
    - Path(__file__).resolve().parents[N] path discovery (mirrors Phase 4 grep gates)
    - YAML safe_load + field validation in integration test
    - Pure file-I/O tests with operator-actionable failure messages
key-files:
  created:
    - .planning/phases/05-ml-cleanup-post-v0/05-02-DECISION.md
    - services/tournament-harness/app/config/t0_1_x_experiment.yaml
    - services/tournament-harness/data/snapshots/.gitkeep
    - .planning/evidence/t0_1_x/.gitkeep
    - .planning/evidence/t0_1_x/leaderboard_row.md
    - .planning/evidence/t0_1_x/decision_note.md
    - services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py
  modified: []
decisions:
  - "different_horizon selected as T0.1.x experiment: zero new Python code, pure YAML edit, sweeps horizon [3,5,7,10] on GRU-only grid"
  - "GRU-only grid (no lstm/transformer/tcn) keeps total at 12 experiments, well within max_experiments=100 cap"
  - "target_modes=[log_returns] only — price-level R² excluded as leakage vector per V0 finding"
  - "Tournament outcome INSUFFICIENT_DATA: TIMESCALE_PASSWORD empty in container — run blocked before any training"
  - "INSUFFICIENT_DATA is a valid Phase 5 outcome per plan Task 2(F) and MLCL-02 success criteria"
  - "Commit type test(05-02-task3) only — no feat commit for Task 3 because artifacts produced by Tasks 1+2, nothing to implement in GREEN phase"
metrics:
  duration_minutes: ~25
  tasks_completed: 3
  files_created: 7
  files_modified: 0
  tests_added: 5
  completed_date: "2026-05-13"
---

# Phase 5 Plan 2: T0.1.x Horizon Sweep — MLCL-02 Summary

One-liner: `different_horizon` YAML authored and committed (GRU, horizons [3,5,7,10], 12-cell grid); tournament run blocked by empty TIMESCALE_PASSWORD — verdict INSUFFICIENT_DATA with 5-step operator remediation sequence.

## Decision Recorded

**Experiment selected:** `different_horizon`
**Decision file:** `.planning/phases/05-ml-cleanup-post-v0/05-02-DECISION.md`

All five T0.1.x candidates were analyzed with cost/info-gain/reversibility scoring:

| Option | Cost | Info Gain | Reversibility | Disposition |
|--------|------|-----------|---------------|-------------|
| different_horizon | LOW | LOW-MEDIUM | HIGH | **SELECTED** |
| classification_head | MEDIUM | MEDIUM | MEDIUM | Defer to V2 |
| xgboost_control | HIGH | HIGH | MEDIUM | Defer to V2 |
| cross_sectional | HIGH | HIGH | LOW | Defer to V2 |
| sentiment_filter | HIGH | MEDIUM | LOW | Defer per MLCL-V2-01 |

`different_horizon` dominates on three axes simultaneously: zero new Python code (pure
YAML edit verified by RESEARCH.md HIGH confidence), highest reversibility (delete YAML
= complete unship), and sufficient information gain for the MLCL-02 requirement (which
allows INSUFFICIENT_DATA as a valid outcome).

## Tournament Config

**File:** `services/tournament-harness/app/config/t0_1_x_experiment.yaml`
**Tournament ID:** `t0_1_x_horizon_sweep`
**Grid:** GRU-only, horizon [3, 5, 7, 10], symbols [SOLUSDT, BNBUSDT, ADAUSDT],
target_mode log_returns, seed 42, max_experiments 100
**Actual grid size:** 12 experiments (4 horizons × 3 symbols × 1 target_mode ×
1 HP combination)

YAML validated: `python3 -c "import yaml; cfg=yaml.safe_load(...); assert
cfg['tournament_id'].startswith('t0_1_x_'); assert cfg['max_experiments'] <= 100"` exits 0.

## Tournament Outcome: INSUFFICIENT_DATA

**Terminal verdict:** `INSUFFICIENT_DATA`
**Evidence file:** `.planning/evidence/t0_1_x/decision_note.md`
**Leaderboard file:** `.planning/evidence/t0_1_x/leaderboard_row.md` (schema stub only)

### What was attempted

The tournament-harness Docker container was started successfully (image pulled from
cache, service healthy on port 8010). The CLI was accessible (`python -m app.cli --help`
returned correctly). The YAML was copied into the container and parsed successfully (12
experiments enumerated by the orchestrator).

The run was blocked before any training began:

```
RuntimeError: TIMESCALE_PASSWORD is unset or still the placeholder;
follow RUNBOOK.md tournament-harness first-time setup before running.
```

`docker exec crypto-bot-tournament-harness env | grep TIMESCALE_PASSWORD` returned
`TIMESCALE_PASSWORD=` (empty string). The launcher validates DB credentials at startup
and refuses to proceed when the password is blank.

### Operator remediation sequence (5 steps)

1. Verify `.env` contains `TIMESCALE_PASSWORD` (non-empty): `grep TIMESCALE_PASSWORD .env`
2. Recreate the tournament-harness container: `docker compose -f docker-compose.unified.yml --profile tournament up -d --force-recreate tournament-harness`
3. Confirm password propagated: `docker exec crypto-bot-tournament-harness env | grep TIMESCALE_PASSWORD`
4. Re-run the tournament (20-60 min expected): `docker exec crypto-bot-tournament-harness python -m app.cli run /app/app/config/t0_1_x_experiment.yaml --allow-dirty 2>&1 | tee .planning/evidence/t0_1_x/run.log`
5. Run open-pr dry-run, copy leaderboard.md to evidence dir, update decision_note.md with actual EDGE_FOUND or NO_EDGE_FOUND verdict.

### Phase follow-up

This is an operator credential configuration issue, not a code defect. No new plan
is required. The YAML, integration test, and evidence directory structure are all
in place. Only the execution + evidence update step remains.

## Integration Test

**File:** `services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py`
**Tests:** 5/5 PASS in 0.67 seconds

| Test | What it asserts |
|------|----------------|
| test_yaml_config_exists_and_valid | YAML exists, parses, tournament_id starts with t0_1_x_, max_experiments <= 100, symbols valid |
| test_leaderboard_markdown_exists_and_nonempty | leaderboard_row.md exists, size > 0 |
| test_decision_note_exists_has_min_lines_and_valid_verdict | decision_note.md exists, >=20 non-blank lines, final line in {EDGE_FOUND, NO_EDGE_FOUND, INSUFFICIENT_DATA} |
| test_decision_note_cites_tournament_id_from_yaml | decision_note.md contains `t0_1_x_horizon_sweep` literally |
| test_decision_doc_exists_has_min_lines_and_decision_heading | 05-02-DECISION.md exists, >=80 lines, has ## Decision: heading |

Prior Phase 4 grep gates also still pass: 9/9 (test_no_legacy_r2_criterion + test_no_auto_merge).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrong REPO_ROOT parent count in Task 3 test file**

- **Found during:** Task 3 — running `pytest` for the first time
- **Issue:** Test file used `HARNESS_ROOT.parents[2]` for REPO_ROOT which resolves to
  `/mnt/d/Bimo_max` (one level too high). The correct value is `HARNESS_ROOT.parents[1]`
  which is `/mnt/d/Bimo_max/crypto-trading-bot`. Tests 2-5 failed because evidence paths
  and DECISION.md were not found.
- **Fix:** Changed `REPO_ROOT = HARNESS_ROOT.parents[2]` to `REPO_ROOT = HARNESS_ROOT.parents[1]`
  in the test file. Added explanatory comment. Tests went 1/5 → 5/5 PASS.
- **Files modified:** `services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py`
- **Commit:** `5839f4b`

### Infrastructure Notes

**2. TIMESCALE_PASSWORD empty in tournament-harness container**

This is not a code deviation — it is a documented infrastructure failure per plan
Task 2(F). The tournament could not run because the DB credential was not set in the
container environment. The `decision_note.md` documents the exact error and a 5-step
remediation sequence. The INSUFFICIENT_DATA terminal verdict was written per the
plan's explicit instruction: "do NOT silently skip. Write decision_note.md with
terminal verdict INSUFFICIENT_DATA AND a Blocker section."

**3. TDD structure for Task 3 — no RED phase**

Per advisor guidance: by the time Task 3 ran, Tasks 1+2 had already produced all
artifacts. The tests passed on first run (GREEN immediately). Per the orchestrator's
pre-confirmed sequential execution pattern, this is expected behavior. The test was
committed once as `test(05-02-task3):`; no separate feat commit was created (nothing
to implement in the GREEN phase — artifacts were already in place).

**4. Commit message convention reconciliation**

Plan Task 2 acceptance says `feat(tournament): ship T0.1.x <experiment_id>`.
Orchestrator's `<sequential_execution>` block specifies `feat(05-02-task2): ...`.
The orchestrator's active instruction layer took precedence: all commits use the
orchestrator's `feat(05-02-taskN):` pattern. Documented here per deviation tracking.

## Known Stubs

**leaderboard_row.md contains a schema stub, not actual results.** The file documents
the expected row format and provides the CLI command to retrieve actual rows once the
tournament runs successfully. This stub is intentional and documented — the INSUFFICIENT_DATA
verdict is explicit, and the operator's next action is clearly stated.

The stub does NOT prevent the plan's goal from being achieved. MLCL-02 explicitly allows
INSUFFICIENT_DATA as a valid outcome ("result is allowed to be no edge and that's a
valid outcome"). The evidence directory is structured correctly for the operator to
update once TIMESCALE_PASSWORD is configured.

## Acceptance Gates

| Gate | Status |
|------|--------|
| `test -f .planning/phases/05-ml-cleanup-post-v0/05-02-DECISION.md` | PASS |
| `wc -l 05-02-DECISION.md >= 80` | PASS (285 lines) |
| `test -f services/tournament-harness/app/config/t0_1_x_experiment.yaml` | PASS |
| `python3 -c "... assert cfg['tournament_id'].startswith('t0_1_x_'); assert cfg['max_experiments'] <= 100"` | PASS |
| `test -f .planning/evidence/t0_1_x/decision_note.md` | PASS |
| `tail -1 decision_note.md | grep -E '^(EDGE_FOUND|NO_EDGE_FOUND|INSUFFICIENT_DATA)$'` | PASS |
| `pytest test_t0_1_x_experiment_shipped.py -v` | PASS (5/5) |
| Phase 4 grep gates: `pytest test_no_legacy_r2_criterion.py test_no_auto_merge.py` | PASS (9/9) |

## Operator Handoff

**Situation:** INSUFFICIENT_DATA — tournament did not run due to TIMESCALE_PASSWORD
being empty in the container environment.

**Operator's next action:**
1. Check `.env` for `TIMESCALE_PASSWORD` and set it if missing.
2. Recreate the tournament-harness container and confirm the env var propagates.
3. Re-run the 12-experiment horizon sweep (~20-60 min).
4. Copy the produced leaderboard.md to `.planning/evidence/t0_1_x/leaderboard_row.md`.
5. Update `decision_note.md` with the actual EDGE_FOUND or NO_EDGE_FOUND verdict, bootstrap
   p-values, and lift values from `t0_1_x_horizon_sweep.significance.json`.

**After update:** If EDGE_FOUND on any symbol — default-on the horizon configuration
in v2 planning and extend the experiment to other architectures. If NO_EDGE_FOUND —
the V0 negative result generalizes across horizons; proceed to classification_head as
next T0.1.x experiment in a new plan.

## Self-Check

**Files created:**
- `.planning/phases/05-ml-cleanup-post-v0/05-02-DECISION.md` — FOUND (285 lines)
- `services/tournament-harness/app/config/t0_1_x_experiment.yaml` — FOUND
- `services/tournament-harness/data/snapshots/.gitkeep` — FOUND
- `.planning/evidence/t0_1_x/.gitkeep` — FOUND
- `.planning/evidence/t0_1_x/leaderboard_row.md` — FOUND (non-empty)
- `.planning/evidence/t0_1_x/decision_note.md` — FOUND (133 lines, terminal: INSUFFICIENT_DATA)
- `services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py` — FOUND

**Commits:**
- `bd496c1` feat(05-02-task1): write 05-02-DECISION.md selecting different_horizon — CONFIRMED
- `9b08ea4` feat(05-02-task2): ship T0.1.x horizon_sweep experiment config and evidence — CONFIRMED
- `5839f4b` test(05-02-task3): pin T0.1.x evidence contract — CONFIRMED

## Self-Check: PASSED
