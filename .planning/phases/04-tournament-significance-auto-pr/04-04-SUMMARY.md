---
phase: 04-tournament-significance-auto-pr
plan: 04
subsystem: tournament-harness
tags: [reproducibility, cli, significance, d-12]
requires: [04-01, 04-02, 04-03, 04-07]
provides:
  - "tournament reproduce {tid} --git-sha {sha}" CLI subcommand
  - run_reproduce(tournament_id, *, git_sha_expected, force=False) -> int
  - _diff_significance(original, reproduced) -> list[str] D-12 helper
affects:
  - services/tournament-harness/app/cli.py (new subparser)
tech-stack:
  added: []
  patterns:
    - "Lazy import inside run_reproduce of app.pr.open_pr to keep heavy ensemble pipeline out of CLI parse path"
    - "CD-06 forensic temp-DB lifecycle: clean on success, retain on failure"
    - "W2 output_suffix='dry-run' so reproduce never overwrites operator originals"
key-files:
  created:
    - services/tournament-harness/app/pr/reproduce.py
    - services/tournament-harness/tests/unit/test_pr_reproduce.py
    - services/tournament-harness/tests/integration/test_reproduce_idempotent.py
  modified:
    - services/tournament-harness/app/cli.py
decisions:
  - "Snapshot rows are flat sqlite Row dicts; LeaderboardDB.insert_run expects nested metrics. Adapter `_wrap_snapshot_row_for_insert` re-packs at the call-site rather than changing insert_run's contract."
  - "Integration tests skipif _CANONICAL_METRICS_AVAILABLE is False — host pytest cannot merge ml-retraining's `app.*` into the harness `app.*` namespace. Tests run in container CI."
metrics:
  duration: ~25min
  completed: 2026-05-10
---

# Phase 04 Plan 04: Reproducibility Verifier Summary

`tournament reproduce {tid} --git-sha {sha}` is the executable proof that a recorded
tournament's `significance.json` is bit-(near-)identical when re-derived from the
snapshot at the recorded git SHA. D-12 (`(snapshot + git_sha + bootstrap_seed) →
identical significance`) becomes a CLI command + a CI gate.

## Public API

```python
from app.pr.reproduce import run_reproduce

run_reproduce(
    tournament_id: str,
    *,
    git_sha_expected: str,
    force: bool = False,
) -> int
```

Exit-code reference:

| Exit | Meaning |
|------|---------|
| `0`  | Reproduced significance is identical to the original within FP-noise tolerance (`Δsharpe ≤ 1e-6`, `Δp ≤ 0.005`). Temp DB + dry-run scratch artifacts cleaned up. |
| `2`  | Missing inputs (snapshot or original `significance.json` absent), OR temp DB already exists at `data/leaderboard/reproduce_{tid}.db` and `--force` not passed. |
| `3`  | Refusal gate: dirty git tree (D-12 — no `--allow-dirty` opt-out) OR `HEAD ≠ git_sha_expected`. |
| `4`  | Reproducibility broken — diff exceeds tolerance. **Temp DB and dry-run scratch artifacts are RETAINED at the snapshot dir for forensic inspection (CD-06).** |

## CLI surface

```
$ python -m app.cli reproduce --help
usage: python -m app.cli reproduce [-h] --git-sha GIT_SHA [--force] tournament_id

positional arguments:
  tournament_id

options:
  -h, --help         show this help message and exit
  --git-sha GIT_SHA  Expected HEAD; refuses with exit 3 if HEAD does not match
  --force            Drop existing temp DB before re-running (CD-06 forensic)
```

D-12 contract grep-checked: `--allow-dirty` is **not** offered for `reproduce`
(it is for `tournament run` and `tournament open-pr`).

## Behavior contract (selected highlights)

1. **Refusal gates first.** `_git_is_dirty()` and `HEAD vs git_sha_expected` are
   checked before any filesystem work. Both raise `SystemExit(3)`.
2. **Inputs validated.** Snapshot `data/snapshots/{tid}.json` and original
   `data/snapshots/{tid}.significance.json` must both exist. Missing →
   `SystemExit(2)` with a clear stderr pointer ("run `tournament open-pr` first").
3. **Temp leaderboard is separate.** `data/leaderboard/reproduce_{tid}.db` is
   built fresh per run (or pre-existing one drops on `--force`). Production
   `tournaments.db` is NEVER touched (T-04-25 mitigation). Confirmed by:
   `grep -nE '"tournaments\.db"|'\''tournaments\.db'\''' app/pr/reproduce.py`
   returns no matches.
4. **Lazy heavy import.** `from app.pr.open_pr import run_open_pr` happens
   inside `run_reproduce`, so `python -m app.cli reproduce --help` does not
   pull in numpy / TF (CLI parse stays fast).
5. **W2 — no atomic-rename choreography.** `run_open_pr` is invoked with
   `output_suffix="dry-run"`, so the reproduced artifacts land at
   `{tid}.dry-run.{ensemble,significance,leaderboard}.{json,md}` — the
   operator's originals are never overwritten. The earlier "backup-and-restore"
   pattern (`{tid}.significance.original.json`) is gone:
   `grep -n '\.original\.json' app/pr/reproduce.py` returns no matches.
6. **Forensic retain on failure.** On diff > tolerance, both the temp DB and
   the dry-run scratch artifacts stay on disk so the operator can re-diff
   manually. On success they are unlinked.

## Tolerance helper (`_diff_significance`)

Boundary-inclusive — the comparator uses `>` not `>=`, so `|Δp| = 0.005` exactly
is treated as a pass. Keys checked per symbol:

- `sharpe_lift` — tol `1e-6`
- `dir_acc_lift` — tol `1e-6`
- `sharpe_pvalue` — tol `0.005`
- `dir_acc_pvalue` — tol `0.005`

Symbols with `n_members < 3` (`insufficient_runs` per W1) carry zeroed lifts and
`pvalue = 1.0`, so they always diff to zero between runs.

## Tests

### Unit — `services/tournament-harness/tests/unit/test_pr_reproduce.py` (17 tests)

| Group | Tests |
|-------|-------|
| Refusal gates | `test_dirty_tree_refused`, `test_head_mismatch_refused` |
| Temp DB CD-06 | `test_temp_db_path_correct`, `test_temp_db_cleaned_on_success`, `test_temp_db_retained_on_failure`, `test_force_flag_drops_existing_tempdb` |
| Diff tolerance D-12 | `test_diff_within_tolerance_returns_0`, `test_diff_sharpe_outside_tolerance_returns_4`, `test_diff_pvalue_outside_tolerance_returns_4`, `test_diff_pvalue_at_threshold_passes` |
| CLI surface | `test_no_allow_dirty_flag_in_cli`, `test_help_shows_required_git_sha` |
| T-04-20 path traversal | `test_invalid_tournament_id_rejected` |
| W2 fixes | `test_original_artifacts_mtime_unchanged_after_reproduce`, `test_dryrun_scratch_artifacts_cleaned_on_success`, `test_dryrun_scratch_artifacts_retained_on_failure`, `test_no_significance_original_json_choreography` |

These tests inject a stub `app.pr.open_pr` module via `sys.modules` so they
run on host without needing the canonical metrics chain.

### Integration — `services/tournament-harness/tests/integration/test_reproduce_idempotent.py` (3 tests)

The **load-bearing CI gate** for D-12:

- `test_reproduce_round_trip_idempotent`: open-pr (dry-run) → reproduce →
  empty diff; mtime of original `significance.json` is preserved exactly.
- `test_reproduce_detects_drift`: a perturbed second invocation triggers
  exit 4 AND the temp DB at `reproduce_{tid}.db` survives for forensics.
- `test_reproduce_round_trip_no_real_runner_imports`: tensorflow/keras must
  not be hot-loaded during the round-trip (CI-suitability guard).

These run in **container CI only** — they need `app.pr.open_pr` to import,
which depends on `app.runner.metrics_bridge` resolving the canonical
`app.sharpe_metrics` + `app.cpcv` chain. On host pytest, the two `app.*`
namespaces (tournament-harness + ml-retraining) collide; the file skips
cleanly via a `pytest.mark.skipif(_CANONICAL_METRICS_AVAILABLE)` guard.

A real-runner version (no monkeypatched predict) is the eventual full-coverage
test owned by Plan 04-06 e2e; the monkeypatched form is the everyday CI gate
the operator should monitor.

## Verification — grep gates

```
$ grep -nE 'SHARPE_TOLERANCE\s*=\s*1e-6|PVALUE_TOLERANCE\s*=\s*0\.005' services/tournament-harness/app/pr/reproduce.py
47:SHARPE_TOLERANCE = 1e-6
48:PVALUE_TOLERANCE = 0.005

$ grep -n 'allow_dirty' services/tournament-harness/app/cli.py
37:    summary = run_tournament(args.yaml_path, allow_dirty=args.allow_dirty)
63:        allow_dirty=args.allow_dirty,
# (only `tournament run` and `tournament open-pr` — NOT reproduce)

$ grep -n '\.original\.json' services/tournament-harness/app/pr/reproduce.py
# (no matches — backup-restore choreography removed)

$ grep -n 'output_suffix' services/tournament-harness/app/pr/reproduce.py
13:- Re-run the open-pr pipeline in --dry-run mode with output_suffix="dry-run"
216:        output_suffix=_DRYRUN_SUFFIX,
```

## Test runs

- `PYTHONPATH=services/tournament-harness pytest services/tournament-harness/tests/unit/test_pr_reproduce.py -q`
  → **17 passed**.
- `PYTHONPATH=services/tournament-harness pytest services/tournament-harness/tests/integration/test_reproduce_idempotent.py -q`
  → **3 skipped** (host); will run + assert in container CI.
- Full unit-suite regression: 211 passed, 1 pre-existing skip (`test_runner_metrics_bridge.py` —
  unrelated to this plan).

## Deviations from plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] `LeaderboardDB.insert_run` shape mismatch with snapshot rows**
- **Found during:** Task 1 implementation (writing `run_reproduce`).
- **Issue:** The plan body shows `for row in snapshot["rows"]: db.insert_run(row)`, but
  snapshot rows are flat sqlite Row dicts (e.g. top-level `dsr`, `cpcv_dsr`, ...) while
  `LeaderboardDB.insert_run` expects the nested `{"metrics": {...}, "run_id": ..., ...}`
  shape used by the orchestrator's normalised result schema. Calling `insert_run` directly
  on a flat snapshot row raises `KeyError`.
- **Fix:** Added a private `_wrap_snapshot_row_for_insert` adapter inside `reproduce.py`
  that re-packs the flat snapshot row into the nested shape before calling `insert_run`.
  No change to `LeaderboardDB`'s contract.
- **Files modified:** `services/tournament-harness/app/pr/reproduce.py`.
- **Commit:** `3a0e9de`.

**2. [Rule 3 - Blocker] `run_migrations` requires `migrations_dir`**
- **Found during:** Task 1 implementation.
- **Issue:** Plan body suggests `run_migrations(temp_db)`, but the function signature is
  `run_migrations(db_path, migrations_dir)`.
- **Fix:** Module-level `MIGRATIONS_DIR = HARNESS_ROOT / "migrations"`, then
  `run_migrations(temp_db, MIGRATIONS_DIR)` at the call-site.
- **Files modified:** `services/tournament-harness/app/pr/reproduce.py`.
- **Commit:** `3a0e9de`.

**3. [Rule 3 - Blocker] Host pytest cannot import `app.pr.open_pr`**
- **Found during:** Task 1 unit-test runs.
- **Issue:** `app.pr.open_pr` imports `probabilistic_sharpe_ratio` from
  `app.runner.metrics_bridge` at module load. On host, the harness `app.*` and
  ml-retraining `app.*` packages don't merge — `_CANONICAL_METRICS_AVAILABLE` is
  False and `probabilistic_sharpe_ratio` is unbound. The plan's unit tests imported
  `app.pr.open_pr` directly to monkeypatch `run_open_pr` there; this raised
  `ImportError`.
- **Fix:**
  - Unit tests now inject a stub `app.pr.open_pr` module into `sys.modules` BEFORE
    `run_reproduce` performs its lazy `from app.pr.open_pr import run_open_pr`.
    Tests run cleanly on host.
  - Integration tests carry `pytest.mark.skipif(not _CANONICAL_METRICS_AVAILABLE)`
    so they skip on host and run in container CI (where PYTHONPATH merges
    `/app:/opt/ml_retraining` into one namespace).
- **Files modified:** `tests/unit/test_pr_reproduce.py`,
  `tests/integration/test_reproduce_idempotent.py`.
- **Commits:** `582e524`, `374c65d`.

## Commit log

| Hash | Type | Subject |
|------|------|---------|
| `582e524` | test | add failing tests for run_reproduce (TDD RED) |
| `3a0e9de` | feat | implement run_reproduce + reproduce CLI subcommand (GREEN) |
| `374c65d` | test | reproduce round-trip idempotency CI gate (integration) |

## Next plan note (04-06 e2e)

A real-runner version of `test_reproduce_round_trip_idempotent` (no monkeypatched
predict — full ensemble pipeline driving real metrics) is the eventual full-coverage
test. The monkeypatched form here is the everyday CI gate the operator should
monitor; the e2e version is one of the things 04-06 will add.

## Self-Check: PASSED
- services/tournament-harness/app/pr/reproduce.py: FOUND
- services/tournament-harness/tests/unit/test_pr_reproduce.py: FOUND
- services/tournament-harness/tests/integration/test_reproduce_idempotent.py: FOUND
- services/tournament-harness/app/cli.py: contains `cmd_reproduce` + `p_repro` (FOUND)
- Commit `582e524`: FOUND
- Commit `3a0e9de`: FOUND
- Commit `374c65d`: FOUND
