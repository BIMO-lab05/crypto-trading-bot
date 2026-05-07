---
phase: 02-integration-test-suite-runbook
plan: 06
subsystem: infra
tags: [bash, shell, pytest, anti-mock, iter-fix, diff-guard, tdd]

# Dependency graph
requires:
  - phase: 02-integration-test-suite-runbook
    provides: D-09..D-13 decisions and 02-PATTERNS.md refusal-pattern spec
provides:
  - scripts/iter-fix.sh — operator-facing iteration harness (one pytest → diff → check → commit cycle)
  - scripts/iter-fix-check-diff.sh — standalone anti-mock diff-grep (reusable from CI in Plan 02-09)
  - tests/scripts/test_iter_fix.sh — 8 fixture cases proving refusal patterns + exit codes
affects:
  - 02-09 (CI workflow will invoke scripts/iter-fix-check-diff.sh as a PR gate)
  - operator runbook (INFRA-03) that documents harness usage

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Standalone anti-mock refusal script pattern: diff piped into scripts/iter-fix-check-diff.sh; exits 1 with [REFUSED] and offending line"
    - "One-cycle-per-invocation anti-Goodhart harness: no while/for/do loop; operator re-runs for next iteration"
    - "TDD RED/GREEN for bash scripts: test fixtures committed first (exit 127, failing), implementation committed second (all pass)"

key-files:
  created:
    - scripts/iter-fix.sh
    - scripts/iter-fix-check-diff.sh
    - tests/scripts/test_iter_fix.sh
  modified: []

key-decisions:
  - "Test file written as .sh (inline PASS/FAIL) not .bats — bats not installed on WSL2 host; plan body explicitly authorizes this fallback"
  - "Executable bits set via git update-index --chmod=+x — WSL2 worktree has core.filemode=false so filesystem chmod does not propagate to git index"
  - "Banned-token strings assembled from string concat at runtime in iter-fix-check-diff.sh to prevent the script's own source triggering a future scripts/-scoped diff-grep"
  - "Threshold-lowering check uses awk for float comparison (bash arith is integer-only)"

patterns-established:
  - "Diff-guard pattern: scripts/iter-fix-check-diff.sh reads unified diff from stdin (or $1); tracks active target file via '+++ b/' markers; enforces only inside tests/; exits 1 with cited file path and matched pattern"
  - "Anti-Goodhart structure: harness script exits after one cycle; no loop; to iterate, operator re-runs the script"

requirements-completed: [INFRA-04]

# Metrics
duration: ~25min
completed: 2026-05-07
---

# Phase 02 Plan 06: iter-fix Harness Summary

**Anti-mock checkpointed iteration harness (INFRA-04): standalone diff-guard script + operator-facing pytest→diff→approve→commit loop, with 8-case bash test suite proving all D-12 refusal patterns**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-07T22:20:00Z
- **Completed:** 2026-05-07T23:00:00Z
- **Tasks:** 3 (Task 1 RED+GREEN via TDD; Task 2 implementation; Task 3 operator dry-run checkpoint — approved)
- **Files modified:** 3

## Accomplishments

- `scripts/iter-fix-check-diff.sh` rejects all 5 D-12 banned patterns (`unittest.mock`, `mocker.patch`, `pytest.skip`, `pytest.mark.xfail`, threshold-lowering numeric assert) when additions target `tests/`; passes clean diffs and changes outside `tests/` silently
- `scripts/iter-fix.sh` implements the one-cycle operator harness: pytest tests/integration -x → stop on first red → prompt operator for fix → pipe staged diff through diff-guard → Apply? [y/N] gate → atomic `git commit -m "$msg"`; no auto-iterate loop
- 8-case shell test suite in `tests/scripts/test_iter_fix.sh` covers all refusal categories plus allow-list cases (clean diff, non-tests file); all 8 pass
- Operator dry-run (Task 3 checkpoint) completed and approved: all 4 plan-mandated verification steps confirmed by operator

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Build tests/scripts/test_iter_fix.sh (failing)** - `40a3222` (test)
2. **Task 1 GREEN: Implement scripts/iter-fix-check-diff.sh** - `663eabe` (feat)
3. **Task 2: Implement scripts/iter-fix.sh** - `4840add` (feat)
4. **Task 3: Operator dry-run checkpoint** — approved by operator; no separate commit (checkpoint gate, not an auto task)

## Files Created/Modified

- `scripts/iter-fix-check-diff.sh` (mode 100755) — standalone D-12 anti-mock diff-guard; reads unified diff from stdin or `$1`; exits 1 with `[REFUSED]` and cited file path+line on any banned pattern inside `tests/`; reusable by CI (Plan 02-09)
- `scripts/iter-fix.sh` (mode 100755) — operator-facing INFRA-04 harness; one-cycle pytest → diff → check → commit; delegates to `iter-fix-check-diff.sh`; no auto-iterate loop (D-13 anti-Goodhart)
- `tests/scripts/test_iter_fix.sh` (mode 100644) — 8 fixture cases (`.sh` fallback; see Deviations)

## Decisions Made

- Used inline PASS/FAIL shell test harness (`.sh`) instead of bats because bats is not installed on the WSL2 host; plan body explicitly authorizes this fallback at task 1 step 3
- Banned-token strings assembled from string concatenation at runtime in `iter-fix-check-diff.sh` so the script's own source does not contain the naked banned tokens — prevents a future scripts/-scoped diff-grep from false-positiving on its own guard implementation
- Executable bits forced via `git update-index --chmod=+x` because WSL2 worktree has `core.filemode=false`; filesystem `chmod +x` does not propagate to the git index in this configuration

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Test file written as tests/scripts/test_iter_fix.sh (not .bats) — bats not installed**
- **Found during:** Task 1 (RED phase — creating test fixtures)
- **Issue:** Plan specifies `tests/scripts/test_iter_fix.bats`; `bats` framework is not installed on the WSL2 host (command not found); running `bash tests/scripts/test_iter_fix.bats` would fail at the shebang / bats internal functions
- **Fix:** Wrote an equivalent 8-case inline PASS/FAIL shell script at `tests/scripts/test_iter_fix.sh`; each case pipes a fixture diff into the guard script and asserts exit code + output substring; prints `PASS` / `FAIL [reason]` per case and exits 1 if any fail. Plan body task 1 step 3 explicitly authorizes this: "if not present in the project, fall back to a `tests/scripts/test_iter_fix.sh` that runs each case and prints PASS/FAIL inline"
- **Files modified:** `tests/scripts/test_iter_fix.sh`
- **Verification:** All 8 cases pass against the GREEN implementation
- **Committed in:** `40a3222` (RED), `663eabe` (GREEN)

**2. [Rule 3 - Blocking] Executable bits set via git update-index --chmod=+x (WSL2 core.filemode=false workaround)**
- **Found during:** Task 1 (GREEN phase — committing iter-fix-check-diff.sh)
- **Issue:** The worktree has `core.filemode=false` (WSL2 default). `chmod +x <file>` changes filesystem permissions but does not update the git index; the file would be committed as mode 100644 (non-executable), causing `[ -x scripts/iter-fix-check-diff.sh ]` to fail and making the script non-callable without an explicit `bash` prefix in CI
- **Fix:** Ran `git update-index --chmod=+x scripts/iter-fix-check-diff.sh` (and same for `scripts/iter-fix.sh`) to force mode 100755 in the git index regardless of filesystem perception
- **Files modified:** git index entries for both scripts
- **Verification:** `git ls-files -s scripts/iter-fix*.sh` shows `100755` for both; plan acceptance criteria `[ -x scripts/iter-fix-check-diff.sh ]` passes
- **Committed in:** `663eabe`, `4840add`

---

**Total deviations:** 2 auto-fixed (both Rule 3 — blocking environment constraints)
**Impact on plan:** Both fixes required for correctness in the WSL2 worktree environment. The `.sh` fallback is explicitly authorized by the plan. The `core.filemode` workaround is a standard WSL2 pattern. No scope creep.

## Task 3 Checkpoint Status

**Type:** checkpoint:human-verify
**Status:** Operator dry-run completed and approved.

The 4 plan-mandated verification steps were confirmed by the operator:
1. Standalone refusal script: `printf -- '...\n+    pytest.skip("services down")\n' | bash scripts/iter-fix-check-diff.sh` exits 1 with "REFUSED" and "pytest.skip" — confirmed.
2. Harness wires into git: deliberate `assert False` failure causes pytest to fail on first red; harness prompts "Make a fix..."; Ctrl-C aborts without committing — confirmed.
3. Refusal blocks on banned staged diff: staging `import unittest.mock` in a test file, running the harness → `[REFUSED] Staged diff hit D-12 anti-mock guard.` and exits 1 — confirmed.
4. Happy-path with clean fix: a real failing assertion fixed, staged, `bash scripts/iter-fix.sh`, `y` at Apply, commit message provided → single new commit, harness exits 0 — confirmed.

## Issues Encountered

None beyond the two deviations documented above.

## Threat Model Items Closed

All 6 items from the plan's STRIDE threat register addressed:

| ID | Category | Disposition | Implementation |
|----|----------|-------------|----------------|
| T-02-06-01 | Tampering (base64 bypass) | accept | Literal-string grep; D-11 operator review at Apply prompt is second defense |
| T-02-06-02 | Tampering (command injection via commit msg) | mitigate | Commit message via `read -p`, passed as quoted arg to `git commit -m "$msg"`; no `eval` |
| T-02-06-03 | Tampering (shell while/watch wrap) | accept | Script exits after one cycle; CI diff-check (02-09) is second structural defense |
| T-02-06-04 | Elevation (writes outside repo) | accept | `cd "$REPO_ROOT"` at start; no sudo; all git ops scoped |
| T-02-06-05 | Info disclosure (pytest log with secrets) | accept | Log is local `/tmp/<xxx>`; not uploaded by this script |
| T-02-06-06 | Elevation (crafted diff hits file-path parser) | mitigate | Bash regex `^\+\+\+ b/(.+)$` anchored; 8 test fixtures cover edge cases |

## Carry-Forward

- **Plan 02-09** (CI workflow) will invoke `scripts/iter-fix-check-diff.sh` as a PR gate step, passing `git diff origin/main..HEAD` on integration — the exact reuse pattern the script was designed for
- **Failed-attempt branch tagging** (`wip(iter)`) mentioned in 02-PATTERNS.md is NOT included — deferred to a future ergonomic improvement; documented as a comment in `scripts/iter-fix.sh`

## Next Phase Readiness

- `scripts/iter-fix-check-diff.sh` is the CI-reusable artifact; Plan 02-09 can `bash scripts/iter-fix-check-diff.sh <diff-file>` or pipe a diff to it directly
- `scripts/iter-fix.sh` is ready for operator use on any integration test failure
- INFRA-04 requirement satisfied; D-09, D-10, D-11, D-12 (structural part) addressed by this plan; D-12 CI enforcement deferred to 02-09

## Self-Check: PASSED

Files verified present in worktree at commit `4840add`:

- `scripts/iter-fix.sh` — FOUND (mode 100755 in git index)
- `scripts/iter-fix-check-diff.sh` — FOUND (mode 100755 in git index)
- `tests/scripts/test_iter_fix.sh` — FOUND (mode 100644 in git index)

Commits verified:
- `40a3222` — FOUND (test: RED phase TDD commit)
- `663eabe` — FOUND (feat: GREEN phase TDD commit)
- `4840add` — FOUND (feat: iter-fix.sh harness commit)

---
*Phase: 02-integration-test-suite-runbook*
*Completed: 2026-05-07*
