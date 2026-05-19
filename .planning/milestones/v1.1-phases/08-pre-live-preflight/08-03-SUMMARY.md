---
phase: 08-pre-live-preflight
plan: 03
subsystem: trading-engine
tags:
  - preflight
  - lifespan
  - boot-enforcement
  - grep-gates
  - PREFLIGHT-02

requires:
  - phase: 08-01
    provides: app.preflight.check_cap (drift-detection counterpart for boundary test)
  - phase: 08-02
    provides: services/trading-engine/app/handlers/preflight.py router (mounted by this plan)
provides:
  - trading-engine lifespan boot-time cap-check (rejects LIVE + cap > 0.02)
  - LIVE_PREFLIGHT_REJECTED critical log emission at boot rejection
  - GET /api/preflight/live-readiness route mounted on trading-engine (port 8005)
  - autoflake-survival F401 import of app.preflight on main.py
  - 5 lifespan integration tests (6 pytest invocations) under services/trading-engine/tests/
  - 2 CI grep gates under tests/integration/
  - boundary-agreement test (drift detector for the two hard-coded 0.02 thresholds)
affects:
  - phase 08-04 (CI workflow invokes both test suites)
  - phase 09 MLGATE (dsr_evidence check graduates from UNKNOWN to PASS once Phase 9 lands)
  - phase 10 DASHLIVE (dashboard tile reads from the mounted route)

tech-stack:
  added: []
  patterns:
    - autoflake-survival F401 markers on imports referenced only by grep gates (project memory feedback_main_imports_autoflake.md)
    - boundary-agreement test pattern — parametrise across exact-boundary + just-above values, assert two independent code paths agree, surface "DRIFT DETECTED" message when they diverge
    - scope-narrowed grep gate (TE_APP only, never REPO_ROOT) so docs prose cannot satisfy production-code regression detectors
    - dual-form grep gate (pathlib rglob + subprocess grep) for cross-platform fidelity AND CI-command fidelity

key-files:
  created:
    - services/trading-engine/tests/test_preflight_lifespan.py
    - tests/integration/test_preflight_grep_gates.py
    - .planning/phases/08-pre-live-preflight/08-03-SUMMARY.md
  modified:
    - services/trading-engine/app/main.py (3 surgical inserts — cap-check block, F401 preflight import, router mount)

key-decisions:
  - Cap-check stays inline at main.py:259, NOT extracted to a helper (locked by 08-CONTEXT.md lines 36-53; co-locates with existing LIVE_TRADING_ACK gate)
  - Boundary-agreement test is the drift detector for the two hard-coded 0.02 thresholds (inline at main.py + check_cap() in app/preflight/checks.py); the two are intentional duplicates per 08-CONTEXT.md
  - Grep gate scope is services/trading-engine/app/ (NOT repo root) — RUNBOOK.md prose containing the literal would otherwise mask production-code removal

patterns-established:
  - Boundary-agreement test (parametrised across boundary-exact + boundary-plus-epsilon, asserting cross-path verdict equality) — generalises to any future "duplicate threshold deliberately preserved" pair
  - Scope-narrowed grep gate with assertion-level guard against widening — "grep -A30 def test_... | grep -c REPO_ROOT" returns 0

requirements-completed:
  - PREFLIGHT-02

# Metrics
duration: ~25min
completed: 2026-05-16
---

# Phase 08-03: Lifespan cap-check + boundary-agreement + grep gates Summary

**Trading-engine refuses to boot in LIVE mode when max_risk_per_trade > 0.02; LIVE_PREFLIGHT_REJECTED log emission + preflight import are guarded by two CI grep gates and a boundary-agreement test that detects drift between the inline lifespan threshold and the shared check_cap() threshold.**

## Performance

- **Duration:** ~25 minutes
- **Started:** 2026-05-16T20:58Z (after worktree merge of sync/cherry-picks-2026-05-05 to obtain 08-01 + 08-02 dependencies)
- **Completed:** 2026-05-16T21:23Z
- **Tasks:** 3
- **Files modified:** 1 (main.py)
- **Files created:** 2 (test_preflight_lifespan.py, test_preflight_grep_gates.py)

## Accomplishments

- Boot-time LIVE-strict cap gate wired into the trading-engine lifespan immediately after the existing LIVE_TRADING_ACK check; PAPER mode unaffected (ADR-010 10% preserved)
- Preflight router from 08-02 mounted, making `GET /api/preflight/live-readiness` reachable at runtime on port 8005
- 5 lifespan tests (6 pytest invocations, all passing) covering: source-inspection regression guard, LIVE+0.03 rejection, LIVE+0.02 acceptance, PAPER+0.10 skip, and the **boundary-agreement drift detector** at the 2% boundary
- 2 CI grep gates (passing) for `LIVE_PREFLIGHT_REJECTED` literal survival and `app.preflight` import survival
- Manual failure-mode verification of grep gate #1 (mutated literal → gate FAILED with the expected diagnostic; reverted → PASSED)
- Manual drift-detection verification of the boundary test (mutated inline threshold to 0.025 → boundary 0.0201 case FAILED; reverted → PASSED)

## Task Commits

1. **Task 1: Insert cap-check block + F401 preflight import + router mount in main.py** — `c23a9dd` (feat)
2. **Task 2: Lifespan integration + boundary-agreement tests** — `9a2f00a` (test)
3. **Task 3: CI grep gates — log emission + import survival** — `9b30f0a` (test)

## Boundary-Agreement Test Detail (addresses checker W2)

`test_lifespan_and_check_cap_agree_at_boundary` is the safety net for 08-CONTEXT.md's locked decision to keep two hard-coded 0.02 thresholds (inline at main.py for lifespan locality + `check_cap()` at app/preflight/checks.py for shared CLI/HTTP logic). The test drives BOTH paths with the same `Settings(...)` at:

| Parametrised case | Cap value | Lifespan verdict | `check_cap()` verdict | Both paths agree? |
|---|---|---|---|---|
| `boundary_exact_0.0200` | 0.0200 | PASS (0.0200 > 0.02 is False) | PASS | Yes |
| `boundary_plus_epsilon_0.0201` | 0.0201 | FAIL — raises RuntimeError | FAIL | Yes |

When either threshold drifts (e.g., inline relaxed to 0.025 while check_cap stays strict), the parametrised case where they disagree fails the test with either `DID NOT RAISE` (`pytest.raises` mismatch) or the explicit `DRIFT DETECTED at cap={cap}: lifespan inline check verdict={X} but check_cap.status={Y}. The two hard-coded 0.02 thresholds ... have diverged.` assertion message naming both files.

## Manual Verification Records

### 1. Grep gate #1 failure-mode (T-08-03-01 mitigation)
- Mutated both `LIVE_PREFLIGHT_REJECTED` occurrences in `services/trading-engine/app/main.py` to `DISABLED_FOR_FAIL_TEST` via `sed`
- Confirmed `grep -c LIVE_PREFLIGHT_REJECTED services/trading-engine/app/main.py` returned 0
- Ran `pytest tests/integration/test_preflight_grep_gates.py::test_live_preflight_rejected_log_exists` — **FAILED** with the expected diagnostic: "LIVE_PREFLIGHT_REJECTED log emission removed from production code. PREFLIGHT-02 enforces the literal must live in services/trading-engine/app/ so CI grep gates can detect silent removal. Restore the logger.critical(...) line in app/main.py lifespan."
- Reverted main.py from `/tmp/main.py.orig` backup; confirmed grep count = 2; re-ran test — **PASSED**

### 2. Boundary-agreement drift detection (T-08-03-07 mitigation)
- Mutated the inline lifespan threshold from `> 0.02` to `> 0.025` via `sed`
- Confirmed `diff` showed exactly the one-line change in main.py
- Ran `pytest "tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary[boundary_plus_epsilon_0.0201]"` — **FAILED** with "DID NOT RAISE <class 'RuntimeError'>"; the captured logs additionally confirmed the buggy state — the lifespan emitted `LIVE preflight cap check passed: max_risk_per_trade=0.0201 <= 0.02` (wrong PASS) while `check_cap()` still returned FAIL for the same cap value
- Reverted main.py from `/tmp/main.py.orig` backup; re-ran boundary test — **PASSED** in both cases
- The 0.0200 boundary case continued to PASS through both mutations, confirming the drift only fires on the FAIL-side asymmetry (the test discriminates correctly)

### 3. In-container smoke (CLAUDE.md "Verification standards" partial — predicate-level only)
The trading-engine container currently running (`crypto-bot-trading`) was built before this plan's main.py edits, so the live deployed lifespan does NOT yet have the cap-check block. To validate the predicate WITHOUT disrupting the running PAPER stack, I ran the same Settings + log + RuntimeError code path inside the container via `docker exec`:
```
docker exec crypto-bot-trading sh -c '
  TRADING_MODE=LIVE MAX_RISK_PER_TRADE=0.03 LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY \
  python -c "...settings + cap-check predicate..."'
```
Captured output (verbatim, copied from the docker exec stderr/stdout):
```
settings: mode=LIVE, cap=0.03
CRITICAL LIVE_PREFLIGHT_REJECTED reason=cap_too_high cap=0.03 limit=0.02
RAISED: Refusing to boot: TRADING_MODE=LIVE with max_risk_per_trade=0.03 > 0.02. Restore the LIVE-strict cap before flipping the mode.
```
This confirms the log format and RuntimeError message at runtime, matching the spec exactly. The full container-restart smoke (rebuild image with the new main.py and observe the container exit non-zero with the log line in `docker logs`) is deferred to post-merge once 08-03 lands on `sync/cherry-picks-2026-05-05`. **The .env file was NOT modified** — env-mutation was scoped to the docker exec subprocess only; the running container's mode remained PAPER throughout.

## Test Results Snapshot

```
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_source_contains_cap_check PASSED
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_rejects_live_with_high_cap PASSED
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_accepts_live_with_strict_cap PASSED
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_paper_mode_skips_cap_check PASSED
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary[boundary_exact_0.0200] PASSED
services/trading-engine/tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary[boundary_plus_epsilon_0.0201] PASSED
========== 6 passed in 19.17s ==========

tests/integration/test_preflight_grep_gates.py::test_live_preflight_rejected_log_exists PASSED
tests/integration/test_preflight_grep_gates.py::test_preflight_module_imports_at_lifespan PASSED
========== 2 passed in 7.37s ==========
```

## Files Created/Modified

- `services/trading-engine/app/main.py` — 3 surgical inserts:
  - F401 autoflake-survival import `from app.preflight import run_all` after existing F401 block (~line 162)
  - Cap-check block inside `if settings.trading_mode == "LIVE":` after the existing `LIVE_TRADING_ACK` check (~line 268-282)
  - Router mount `app.include_router(preflight_router)` after `performance_dashboard_router` (~line 456)
- `services/trading-engine/tests/test_preflight_lifespan.py` — 5 test defs (6 pytest invocations) with the boundary-agreement drift detector
- `tests/integration/test_preflight_grep_gates.py` — 2 grep gates with scope-narrowed (TE_APP-only) subprocess grep + dual-form pathlib scan

## Decisions Made

- Cap-check left inline in lifespan body (NOT extracted to a helper module) per 08-CONTEXT.md lock — preserves co-location with the existing LIVE_TRADING_ACK gate
- Boundary-agreement test placed inside `test_preflight_lifespan.py` (NOT a new file) per checker W2 fix-text directive
- Subprocess grep scope is `TE_APP` (`services/trading-engine/app/`) only, never repo root — RUNBOOK.md prose containing the literal would otherwise mask production-code removal
- Used parametrised pytest case with explicit IDs (`boundary_exact_0.0200`, `boundary_plus_epsilon_0.0201`) for diagnostic clarity in CI logs
- Mocked the 4 phase context managers (`init_data`, `init_ml`, `init_strategy`, `init_risk`) via `monkeypatch.setattr` for the LIVE+0.02 acceptance, PAPER skip, and boundary tests — phases need DB/Redis/RabbitMQ; the test isolates the cap-check branch

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree missing 08-01 + 08-02 deliverables**
- **Found during:** Pre-Task-1 dependency check
- **Issue:** Worktree branch `worktree-agent-a9bdfbbab9eca1b1b` was forked from an older commit (43ba59a) that pre-dates the 08-01 (preflight module) and 08-02 (handler + CLI) work. Task 1 needs both `app.preflight.run_all` (08-01) and `app.handlers.preflight.router` (08-02) to import.
- **Fix:** Merged `sync/cherry-picks-2026-05-05` into the worktree-agent branch — fast-forward succeeded since the worktree had no local edits to those files. HEAD remained on `worktree-agent-a9bdfbbab9eca1b1b` (satisfies pre-commit HEAD safety assertion); did NOT switch branches.
- **Files modified:** Merge brought in 08-01 and 08-02 artifacts; no edits added by me
- **Verification:** `ls services/trading-engine/app/preflight/checks.py services/trading-engine/app/handlers/preflight.py` confirmed both files present
- **Committed in:** Merge commit (no separate commit needed; existing merge from the orchestrator's prior wave)

**2. [Rule 1 - Bug] Docstring contained REPO_ROOT literal inside the grep-gate test function, tripping a scope-correctness acceptance assertion**
- **Found during:** Task 3 acceptance verification
- **Issue:** The plan's acceptance assertion `grep -A30 "def test_live_preflight_rejected_log_exists" tests/integration/test_preflight_grep_gates.py | grep -c "REPO_ROOT"` requires returning 0. My initial docstring contained the phrase "scope is TE_APP only (NOT REPO_ROOT)" which made the count 1.
- **Fix:** Rephrased docstring to "scope is TE_APP only (intentionally narrower than the repo root)" — preserves the intent (scope clarity) without the literal `REPO_ROOT` token inside the function. Also changed `py.relative_to(REPO_ROOT)` → `py.relative_to(TE_APP)` in the matches list for the same reason.
- **Files modified:** `tests/integration/test_preflight_grep_gates.py`
- **Verification:** `grep -A30 ... | grep -c "REPO_ROOT"` now returns 0; both tests still pass
- **Committed in:** `9b30f0a` (Task 3 commit, applied before commit)

---

**Total deviations:** 2 auto-fixed (1 blocking dependency merge, 1 bug fix to satisfy scope-correctness assertion)
**Impact on plan:** None — all auto-fixes were necessary to clear the plan's own acceptance criteria. No scope creep; deliverable signatures unchanged.

## Issues Encountered

- The `-B5` window in the plan's "cap-check inside LIVE branch" source assertion is too narrow (the LIVE_TRADING_ACK block + RuntimeError + critical log occupy ~10 lines between `trading_mode == "LIVE"` and `max_risk_per_trade > 0.02`). The cap-check is correctly nested per the planning intent — verified with `-B15` returning 1, and visual inspection of the awk-extracted block. Not a deviation from plan substance; just a scope-window mismatch in the acceptance assertion as written.

## Threat Flags

None — this plan strictly tightens an existing trust boundary (LIVE-mode boot gate). No new network surface, no new auth paths, no new file-write side effects.

## Next Phase Readiness

- **08-04 (CI workflow)** can now invoke both `pytest services/trading-engine/tests/test_preflight_*` AND `pytest tests/integration/test_preflight_grep_gates.py` from the labelled-PR gate
- **Phase 9 (MLGATE)** unchanged dependency surface — `check_dsr_evidence()` still returns `UNKNOWN` until Phase 9 writes the auto-flip marker
- **Phase 10 (DASHLIVE)** can hit `GET /api/preflight/live-readiness` on port 8005 (mounted by this plan) once trading-engine is rebuilt with these edits

## Self-Check: PASSED

- main.py contains `LIVE_PREFLIGHT_REJECTED` (count: 2), `from app.preflight import` (count: 1), `preflight_router` (count: 2)
- All 3 commits present in git log: `c23a9dd`, `9a2f00a`, `9b30f0a`
- All 6 lifespan tests + 2 grep gate tests pass after manual mutations reverted
- Both manual verifications (failure-mode + drift-detection) confirmed the gates actually detect their target regressions

---
*Phase: 08-pre-live-preflight*
*Completed: 2026-05-16*
