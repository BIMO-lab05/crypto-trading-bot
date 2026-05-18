---
phase: 09-ml-re-enablement-gate
plan: 02-startup-auto-flip
subsystem: trading-engine.lifespan + preflight
tags:
  - mlgate
  - lifespan
  - auto-flip
  - boot-enforcement
  - grep-gates
  - cross-plan-wiring
  - phase-9
requires:
  - 09-03-reason-enum-and-digest  # ONE-WAY import of set_current_reason from app.aggregation.ml_gate_reasons (D-09-02-06)
provides:
  - "auto_flip_ml_predictions() lifespan phase — boot-time gate flipping ENABLE_ML_PREDICTIONS based on DSR evidence"
  - "MLGATE_AUTO_FLIP direction=<v> reason=<v> log emission contract (logger.critical, emitted BEFORE env mutation)"
  - "/run/mlgate_auto_flip.json marker schema_version=1 (cross-phase interface for Phase 10 DASHLIVE-01)"
  - "Extended check_dsr_evidence() with 14-day staleness + psr_ci_published=1 filter (Path A single source of truth — D-09-02-01)"
  - "Cross-plan reason-state wiring — set_current_reason() called from auto-flip closes checker Blocker 1 (every disabled-event signal-aggregator emission now reads truthful reason instead of hardcoded manual_override)"
  - "Two new CI grep gates (test_mlgate_grep_gates.py) — defence-in-depth against silent log-emission or F401-import removal"
affects:
  - "phase 09-03 MLGATE-03 — log_ml_disabled() now reads get_current_reason() populated by THIS plan; without the cross-plan wiring the 5-member enum collapses to one reachable value (checker Blocker 1)"
  - "phase 10 DASHLIVE-01 — reads /run/mlgate_auto_flip.json marker for tile rendering"
  - "phase 8 check_dsr_evidence() — extended in-place (not duplicated); the 14-day staleness rule + psr_ci_published filter now live here"
  - "phase 8 tests test_check_dsr_evidence_ml_enabled_with_row_{above,below}_gate — fixtures updated in-place (Task 1 step 8 — psr_ci_published=1 + fresh run_date seeded)"
tech-stack:
  added: []
  patterns:
    - "Sync function at module scope ABOVE the asynccontextmanager that calls it — unit tests import directly without async-fixture overhead"
    - "Log-FIRST-then-mutate-env ordering (D-09-02-04) — the grep gate anchors on a stable log literal; mutating env first opens a window where the gate could pass against a no-op code path"
    - "Three best-effort try/except wrappers (settings reload, marker write, set_current_reason) — the log line is the only load-bearing artifact; trading-engine boot NEVER crashes on a side-effect failure (T-09-02-05, T-09-02-07)"
    - "6-member local reason tuple (lifespan/ml.py) intentionally a SUPERSET of Plan 09-03's 5-member ML_GATE_REASONS — adds dsr_above_gate for the enabled direction; only the 5 disabled-event members propagate to set_current_reason()"
    - "Dual-form grep gate (pathlib rglob + subprocess) scoped to TE_APP only — PLAN.md prose and the test file's own docstring contain the literal token; scope discipline keeps docs-only matches from satisfying the gate"
    - "Self-avoiding diagnostic message — assertion failure text assembles the bare grep target from variable parts (_TOKEN_HEAD + _TOKEN_TAIL) so the test file itself never contains the contiguous literal in an assertion message"
    - "Injectable now=datetime parameter on auto_flip_ml_predictions + check_dsr_evidence — deterministic unit testing of the 14-day staleness boundary; production callers pass None and the default datetime.now(timezone.utc) fires"
    - "Production-faithful inline SQLite seed (LEADERBOARD_SCHEMA_SQL merging migrations 0001 + 0002) — the unit-test fixture builds the same column types the runtime migration runner would produce; matches the meta-test test_dsr_fixture_schema_matches_production discipline from Phase 8"
key-files:
  created:
    - services/trading-engine/tests/test_ml_gate_auto_flip.py
    - tests/integration/test_mlgate_grep_gates.py
  modified:
    - services/trading-engine/app/preflight/checks.py
    - services/trading-engine/app/lifespan/ml.py
    - services/trading-engine/app/lifespan/__init__.py
    - services/trading-engine/app/main.py
    - services/trading-engine/tests/test_preflight_checks.py
decisions:
  - "D-09-02-01 honored — Path A locked: extend Phase 8's check_dsr_evidence() in-place; lifespan auto-flip READS from it. Zero duplicate DSR-row queries in lifespan/ml.py."
  - "D-09-02-02 honored — marker JSON schema_version=1 pinned with the 6-field shape (schema_version, direction, reason, evaluated_at, dsr_value, run_date); Phase 10 DASHLIVE-01 can render without re-discovery."
  - "D-09-02-03 honored — auto_flip_ml_predictions() runs at the VERY start of init_ml(), BEFORE the from app.main import ta_service_health line AND BEFORE await get_aggregator(); the aggregator's __init__ reads settings.enable_ml_predictions at construction time after the env+reload."
  - "D-09-02-04 honored — log emission ordering is load-bearing: logger.critical(MLGATE_AUTO_FLIP...) fires BEFORE os.environ mutation. The contiguous literal substring 'MLGATE_AUTO_FLIP direction=' lives in one f-string (not split across format fragments) so the grep gate anchor cannot rot under future autoflake/black passes."
  - "D-09-02-05 honored — REQUIREMENTS.md tournament_results wording-bug carry-in NOT touched here; check_dsr_evidence reads the leaderboard table per its actual schema. REQUIREMENTS.md correction deferred to a follow-up docs commit (same precedent as 09-01)."
  - "D-09-02-06 honored — cross-plan reason-state propagation wired: auto_flip_ml_predictions calls set_current_reason() on Plan 09-03's app.aggregation.ml_gate_reasons module after the marker write (only for the 5-member disabled-event vocab; dsr_above_gate is the enabled direction and is intentionally NOT cached). Wrapped in try/except Exception — best-effort cross-plan contract. Closes checker Blocker 1."
metrics:
  duration: ~120min  # cumulative across Wave 2 executor + this resume agent
  completed: "2026-05-17"
  tasks: 3
  files_created: 2
  files_modified: 5
  tests_added: 12  # 10 in test_ml_gate_auto_flip.py + 2 in test_mlgate_grep_gates.py
  tests_passing: 12
---

# Phase 09 Plan 02: Startup Auto-Flip Summary

Boot-time auto-flip of `ENABLE_ML_PREDICTIONS` based on DSR evidence in the `leaderboard` table — landed as an extended `check_dsr_evidence()` (14-day staleness + `psr_ci_published=1` filter), a new sync `auto_flip_ml_predictions()` function wired into `init_ml()` BEFORE aggregator construction (with log-first-then-mutate-env ordering per D-09-02-04), a marker-JSON writer pinned at `schema_version=1`, a cross-plan in-process reason cache populated via Plan 09-03's `set_current_reason()` (closes checker Blocker 1), 10 unit tests against seeded SQLite, and 2 CI grep gates with manually-verified failure-mode mutation discipline.

## Tasks

| Task | What | Commit |
|------|------|--------|
| 1 | Extend `check_dsr_evidence()` with 14-day staleness rule + `psr_ci_published=1` filter; update 2 Phase 8 DSR-evidence test fixtures in place | `c1dc23d` |
| 2 | Add `auto_flip_ml_predictions()` to `app/lifespan/ml.py` (sync, ABOVE `init_ml`); re-export from `lifespan/__init__.py`; F401 import in `main.py`; cross-plan `set_current_reason()` wiring (D-09-02-06); 10 unit tests against seeded SQLite (8 functions, 1 parametrized × 3) | `1a443ad` (impl), `881419f` (tests) |
| 3 | Add CI grep gates `tests/integration/test_mlgate_grep_gates.py` — log-literal survival + autoflake-survival F401 anchor; manual failure-mode mutation verification recorded below | `25e213a` |

## Decisions Made

All carried forward from PLAN.md:

- **D-09-02-01** — Path A locked: extend Phase 8's `check_dsr_evidence()` in-place. Single source of truth for "is DSR evidence good enough?" — lifespan auto-flip READS, never duplicates.
- **D-09-02-02** — Marker JSON schema pinned at `schema_version=1` with the 6-field shape (`schema_version`, `direction`, `reason`, `evaluated_at`, `dsr_value`, `run_date`). Phase 10 DASHLIVE-01 reads this without re-discovery.
- **D-09-02-03** — Lifespan insertion at the very start of `init_ml()`, BEFORE aggregator construction. The aggregator's `__init__` reads `settings.enable_ml_predictions` at construction time; the auto-flip mutates env + reloads settings first so the aggregator sees the new value.
- **D-09-02-04** — Log emission ordering is load-bearing: `logger.critical(f"MLGATE_AUTO_FLIP direction={direction} reason={reason}")` fires BEFORE `os.environ["ENABLE_ML_PREDICTIONS"]` mutation. The contiguous literal substring lives in one f-string template (not split across fragments) so the grep gate's anchor cannot rot under future autoflake/black passes.
- **D-09-02-05** — REQUIREMENTS.md `tournament_results` wording-bug carry-in NOT touched here; check_dsr_evidence reads the `leaderboard` table per its actual schema. Wording correction deferred to a follow-up docs commit (mirrors 09-01 precedent).
- **D-09-02-06** — Cross-plan reason-state wiring closes checker Blocker 1: `auto_flip_ml_predictions()` calls `set_current_reason(reason)` on Plan 09-03's `app.aggregation.ml_gate_reasons` module for the 5-member disabled-event vocab only (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`). The enabled-direction reason `dsr_above_gate` is intentionally NOT cached — Plan 09-03's `log_ml_disabled()` is by definition the disabled-event emission path. Wrapped in try/except Exception — failure logs a warning and trading-engine boot continues; the marker JSON is the durable source of truth.

## Implementation Notes

### Lifespan insertion point (D-09-02-03)

`auto_flip_ml_predictions()` is a **sync** function defined at module scope ABOVE `init_ml` in `app/lifespan/ml.py`. Unit tests import it directly via `from app.lifespan.ml import auto_flip_ml_predictions` — no async fixture overhead. `init_ml` calls it as the first statement after `logger.info("init_ml: enter")` and BEFORE `from app.main import ta_service_health` (the deferred import that breaks the circular dependency between main and lifespan/ml). After the auto-flip returns, `init_ml` re-fetches settings via `get_settings()` so the new `ENABLE_ML_PREDICTIONS` value flows into `paper_initial_balance` consumers.

### Log-first-then-mutate ordering (D-09-02-04)

The auto-flip body explicitly orders side effects:

```python
# 1. LOG FIRST — the grep gate's anchor
logger.critical(f"MLGATE_AUTO_FLIP direction={direction} reason={reason}")
# 2. THEN mutate env
os.environ["ENABLE_ML_PREDICTIONS"] = "true" if direction == "enabled" else "false"
# 3. Reload settings (best-effort, try/except)
# 4. Write marker JSON (best-effort, try/except OSError)
# 5. Call set_current_reason (best-effort, try/except Exception) — disabled-event only
```

This ordering means a future refactor that drops the log emission cannot "pass" the gate against a no-op code path — the grep target lives in production code and the mutation lives only after it.

### 6-member reason tuple is a superset (D-09-02-06)

Plan 09-03's `ML_GATE_REASONS` is exactly 5 members (`no_evidence`, `dsr_below_gate`, `evidence_stale`, `regime_shift`, `manual_override`). Plan 09-02's local `_MLGATE_REASONS` tuple is a 6-member superset adding `dsr_above_gate` for the enabled direction. The split is intentional: Plan 09-03's `log_ml_disabled()` is by definition the disabled-event emission path, so `set_current_reason()` only accepts the 5-member vocab — passing `dsr_above_gate` would raise `ValueError`. The Plan 09-02 wiring `if reason in _DISABLED_EVENT_REASONS: set_current_reason(reason)` enforces this contract at the call site.

### Cross-plan reason-state propagation (D-09-02-06)

`auto_flip_ml_predictions()` imports `from app.aggregation.ml_gate_reasons import set_current_reason` — the **only** cross-plan code import in Phase 9. After determining the auto-flip outcome and writing the marker JSON, the function calls `set_current_reason(reason)` for the 5 disabled-event reasons. This propagates the truthful reason to Plan 09-03's in-process cache so every signal-aggregator emission site (E1: enhanced_aggregator `__init__`; E2: enhanced_aggregator parallel-fetch else-branch; E3: signal_aggregator fallback) reads the live reason instead of the hardcoded `manual_override` default. Without this wiring, the 5-member enum is unreachable from production code paths — ROADMAP SC#3's example `(e.g., no_evidence: 3, dsr_below_gate: 1)` would be impossible to reproduce (checker Blocker 1).

### Phase 8 test fixture updates (Task 1 step 8)

Two Phase 8 DSR-evidence tests required in-place fixture updates so the new `WHERE psr_ci_published = 1` + 14-day-staleness filter would accept the seeded row:

- `test_check_dsr_evidence_ml_enabled_with_row_above_gate_passes` — now seeds `psr_ci_published=1` + `run_date=_fresh_run_date(days_ago=3)` so PASS branch still fires.
- `test_check_dsr_evidence_ml_enabled_with_row_at_or_below_gate_fails` — same seed pattern but `dsr=0.90` so FAIL branch still fires for the right reason (`dsr_below_gate`, not `evidence_stale`).

The other two Phase 8 DSR-evidence tests (`_ml_disabled_passes`, `_ml_enabled_no_marker_is_unknown`) short-circuit before the leaderboard read and required no fixture changes. The shared `LEADERBOARD_SCHEMA_SQL` in `test_preflight_checks.py` was updated to merge migrations 0001 + 0002 inline (advisor note 3 — apply both column sets in the single inline CREATE rather than re-running migration 0002 against the test DB).

## Deviations from Plan

**Task 2 implementation deviation** (minor — within Plan acceptance):

- Plan action step 1 specified: `"set_current_reason call wrapped in try/except Exception"`. Implementation also added a `try/except Exception` around the `reload_settings()` call (best-effort settings reload). Plan did not explicitly require this; rationale: a settings-reload failure (e.g., transient pydantic-v2 issue) MUST NOT crash trading-engine boot any more than a marker-write or set_current_reason failure should. Same defensive posture, same load-bearing-log-only principle (D-09-02-04). Logged as `MLGATE settings reload failed: <TypeName>` warning.
- The plan's pseudocode showed `else: # UNKNOWN` mapping to `(disabled, no_evidence)`. Implementation matches exactly. The `"ML disabled" in result.detail` check (PASS branch short-circuit) was kept intentionally to distinguish operator-chosen disablement (`manual_override`) from evidence-absence (`no_evidence`) — exactly per plan pseudocode.

**No other deviations.** Plan executed to acceptance.

## Verification

### Task 1 (Phase 8 DSR-evidence backward compatibility)

```
cd services/trading-engine && pytest tests/test_preflight_checks.py -v -k "dsr_evidence"
4 passed in 34.55s
```

All 4 Phase 8 DSR-evidence tests pass: `_ml_disabled_passes`, `_ml_enabled_no_marker_is_unknown`, `_ml_enabled_with_row_above_gate_passes`, `_ml_enabled_with_row_at_or_below_gate_fails`. The seed-fixture updates landed in `test_preflight_checks.py` (lines ~302 and ~333) — both row-inserting tests now reference `psr_ci_published=1` and `run_date=_fresh_run_date(days_ago=3)`.

### Task 2 (auto_flip_ml_predictions unit tests)

```
cd services/trading-engine && pytest tests/test_ml_gate_auto_flip.py -v
10 passed in 4.34s
```

- `test_auto_flip_enabled_when_fresh_dsr_above_gate` — PASS branch, log + marker + os.environ asserted.
- `test_auto_flip_disabled_when_no_evidence` — UNKNOWN-marker-absent path; verifies `direction=disabled reason=no_evidence`.
- `test_auto_flip_disabled_when_evidence_stale` — fresh-dsr-above-gate + run_date=now-20d -> `evidence_stale`.
- `test_auto_flip_disabled_when_dsr_below_gate` — dsr=0.90 -> `dsr_below_gate` (precedence over staleness).
- `test_auto_flip_ignores_unpublished_rows` — psr_ci_published=0 row filtered out -> `no_evidence`.
- `test_auto_flip_marker_write_failure_does_not_raise` — OSError-raising Path.write_text monkeypatch; function returns normally + warning logged + marker not created.
- `test_auto_flip_sets_current_reason_for_disabled_branches[no_evidence|dsr_below_gate|evidence_stale]` — **D-09-02-06 reachability proof** (3 parametrized cases): for each scenario, `get_current_reason()` matches the auto-flip outcome.
- `test_auto_flip_does_not_crash_when_set_current_reason_raises` — best-effort cross-plan contract: RuntimeError from `set_current_reason` does not crash boot; marker JSON still written.

### Task 2 (Phase 8 lifespan regression)

```
cd services/trading-engine && pytest tests/test_preflight_lifespan.py -v
6 passed in <part of 21.53s>
```

All 6 Phase 8 lifespan tests still pass — no regression from the auto-flip wiring at the start of `init_ml()`.

### Task 3 (new CI grep gates)

```
cd services/trading-engine && pytest /mnt/.../tests/integration/test_mlgate_grep_gates.py -v
2 passed in 4.88s
```

Both gates pass: `test_mlgate_auto_flip_log_exists` (dual-form scan: pathlib rglob + subprocess grep, scope=TE_APP only) and `test_mlgate_module_imports_at_main` (inspect.getsource assertion).

### Task 3 (co-existence with Phase 8 grep gates)

```
cd services/trading-engine && pytest /mnt/.../tests/integration/test_preflight_grep_gates.py /mnt/.../tests/integration/test_mlgate_grep_gates.py -v
4 passed in 7.64s
```

No co-existence regression — Phase 8 + Phase 9 grep gates both pass in a single run.

## Manual Verification Records

**Failure-mode mutation verification** (Task 3 step 5 — mirror 08-03-SUMMARY.md lines 104-116 format):

| Step | Action | `grep -c "MLGATE_AUTO_FLIP" services/trading-engine/app/lifespan/ml.py` | Gate result |
|------|--------|--------------------------------------------------------------------------|-------------|
| 1 | Baseline (pre-mutation) | **2** | PASSED |
| 2 | `sed -i 's/MLGATE_AUTO_FLIP/DISABLED_FOR_FAIL_TEST/g' lifespan/ml.py` | **0** | **FAILED** with diagnostic naming `lifespan/ml.py::auto_flip_ml_predictions` |
| 3 | Restore from `/tmp/ml.py.orig.<pid>` backup | **2** | PASSED |

The gate's assertion-failure message correctly identified the missing emission and pointed to the production file. The diagnostic message does NOT contain the bare `MLGATE_AUTO_FLIP` literal — it is assembled at runtime via `f"{_GREP_TARGET_DIAG} log emission removed..."` where `_GREP_TARGET_DIAG = f"{_TOKEN_HEAD}_{_TOKEN_TAIL}"`. This means the test file itself does NOT self-satisfy the gate when the subprocess scope is correctly narrowed to TE_APP.

**Token-count discipline**: `grep -c "MLGATE_AUTO_FLIP" tests/integration/test_mlgate_grep_gates.py` returns **3** (within the `<=3` acceptance threshold) — exactly one each in the module docstring, the `re.compile` call, and the `subprocess.run` argument list. Zero occurrences in assertion messages or other locations.

## Threat Flags

No new threat surface beyond what `<threat_model>` already captured (T-09-02-01 through T-09-02-07). All mitigations implemented; none deferred.

## Known Stubs

None. All auto-flip outcomes route to either an enabled / disabled `os.environ` mutation + marker write + reason-state cache update, with best-effort try/except wrappers around the side effects. The only "stub-like" item is the `regime_shift` enum member in Plan 09-03's `ML_GATE_REASONS` — reserved for v1.2 per Plan 09-02 must_haves note; no production path in Phase 9. Documented here for the verifier; intentional gap, not a stub-the-plan-failed-to-wire.

## Deferred Items

1. **REQUIREMENTS.md `tournament_results` → `leaderboard` wording correction** — carry-in from Phase 8 / Plan 09-01 (D-09-02-05). Deferred to a follow-up docs commit; same precedent as Plan 09-01 (which also did not touch REQUIREMENTS.md wording). Not blocking — the production code reads the correct table name (`leaderboard`).
2. **CI workflow wiring of `test_mlgate_grep_gates.py`** — `.github/workflows/preflight-live-readiness.yml` line 42 currently invokes only `test_preflight_grep_gates.py`. Adding the new sibling file to that step is a single-line edit (`pytest tests/integration/test_preflight_grep_gates.py tests/integration/test_mlgate_grep_gates.py -v`) and is out of scope for this plan per Task 3 step 7 (Phase 12 or operator follow-up).
3. **CI workflow `working-directory` fix for grep gates step** (observed during execution, not in plan) — the existing Phase 8 CI step at line 42 runs from REPO_ROOT, not from `services/trading-engine`; `test_preflight_module_imports_at_lifespan` would fail with `ModuleNotFoundError: No module named 'app'` if actually invoked against the current CI workflow. Both Phase 8 and Phase 9 sibling tests share this latent issue (Phase 8 ships it; Phase 9 mirrors the pattern). The local-developer invocation `cd services/trading-engine && pytest tests/integration/test_mlgate_grep_gates.py -v` works correctly. Recommended follow-up: add `working-directory: services/trading-engine` to the "Grep gates" step in the CI workflow.

## Deploy Order (Operator Note — checker WARNING 3)

Apply Plan 09-01's tournament-harness migration 0002 BEFORE booting trading-engine with `ENABLE_ML_PREDICTIONS=true`. Without migration 0002 the `psr_ci_published` and `run_date` columns are missing on `leaderboard`; `check_dsr_evidence` raises `sqlite3.OperationalError` → Phase 8 sqlite-error path returns `UNKNOWN` → auto-flip maps `UNKNOWN → direction=disabled reason=no_evidence`. This is **graceful degradation** — trading-engine does NOT crash on boot; ML stays off as the safe default. But the auto-flip gate is non-functional until migration runs.

Recommended sequence on a fresh deploy:

1. Apply migration 0002 (Plan 09-01 — `services/tournament-harness/migrations/0002_mlgate_evidence_columns.sql`).
2. Run `python -m scripts.forward_paper_test.run_evidence_loop` to populate `psr_ci_published=1` on qualifying rows (Plan 09-01 driver).
3. Boot trading-engine — `auto_flip_ml_predictions()` will now see the populated `leaderboard` and either flip ML on (if `dsr > 0.95 AND run_date within 14d`) or emit a truthful `reason=` (`dsr_below_gate` / `evidence_stale`).

## Commits

| Hash | Type | Message |
|------|------|---------|
| `c1dc23d` | feat | Extend `check_dsr_evidence` with 14-day staleness + `psr_ci_published` filter |
| `1a443ad` | feat | Add `auto_flip_ml_predictions` lifespan phase + marker writer + cross-plan reason-state wiring |
| `881419f` | test | Add 10 unit tests for `auto_flip_ml_predictions` (seeded SQLite + cross-plan reachability) |
| `25e213a` | test | Add CI grep gates for `MLGATE_AUTO_FLIP` log + auto_flip import survival |

## Self-Check: PASSED

- All 4 created/modified production files exist at the documented paths.
- All 4 commit hashes resolve in `git log`.
- All 12 added tests pass (10 unit + 2 grep gates).
- All 29 Phase 8 trading-engine tests still pass (23 preflight_checks + 6 preflight_lifespan).
- All 2 Phase 8 grep gates still pass (no co-existence regression).
- Manual failure-mode mutation verification recorded with before/after grep counts and gate exit codes.
