---
phase: 04-tournament-significance-auto-pr
plan: 05
subsystem: tournament-harness/ci-gates
tags: [tournament-harness, ci, grep-gate, significance, regression-guard]
requires: []
provides:
  - D-13 R² grep gate (services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py)
  - CD-10 no-auto-merge grep gate (services/tournament-harness/tests/integration/test_no_auto_merge.py)
  - B1 klines is_mainnet filter gate (services/tournament-harness/tests/integration/test_klines_filter_required.py)
  - B2 strengthened metric-reimplementation gate (services/tournament-harness/tests/integration/test_no_parallel_metric_reimplementations.py)
affects:
  - .github/workflows/tournament-harness.yml (will pick up new tests automatically when CI re-runs)
tech-stack:
  added: []
  patterns:
    - canonical Phase 3 grep-gate shape (mirror of test_tourn07_grep_gate.py)
    - "/tests/ substring filter as self-allowlist"
    - "anchored regex `^[^:]+:\\d+:(.*)$` for grep output parsing (W3 fix)"
    - "pattern-constants pin tests as regression guards"
key-files:
  created:
    - services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py
    - services/tournament-harness/tests/integration/test_no_auto_merge.py
    - services/tournament-harness/tests/integration/test_klines_filter_required.py
    - services/tournament-harness/tests/integration/test_no_parallel_metric_reimplementations.py
  modified: []
decisions:
  - "Skip subprocess grep test when neither pr/ nor significance/ exists yet (Phase 4 plans 04-06+ create them); avoids `grep -rEn PATTERN` falling back to cwd scan and matching reference docs in .claude/skills/."
metrics:
  duration: "~10 minutes"
  completed: "2026-05-09"
  commits: 4
  tests_added: 18 (17 active + 1 conditional skip)
---

# Phase 4 Plan 5: Tournament CI Grep Gates Summary

Four pytest integration tests enforcing ROADMAP success criteria as build-time grep gates. All four mirror the canonical Phase 3 `test_tourn07_grep_gate.py` shape.

## What was built

| Gate | File | Purpose | Tests |
|---|---|---|---|
| D-13 | `test_no_legacy_r2_criterion.py` | No `>5% R²` win-criterion in code/comments/strings/workflows | 5 |
| CD-10 | `test_no_auto_merge.py` | No `gh pr merge` invocation anywhere in harness or workflows | 4 |
| B1 | `test_klines_filter_required.py` | Every klines read carries `is_mainnet` filter within ±5 lines | 5 |
| B2 | `test_no_parallel_metric_reimplementations.py` | No `def _?(sharpe\|dir_acc\|deflated\|...)` or lambda-Sharpe in pr/+significance/ | 4 (1 skip pre-pr/) |

## Pattern lists

### D-13 (R² ban)
```python
PATTERNS = [
    r">\s*5\s*%",
    r"5\s*percent\s*R[²2]",
    r"r2[_\s]*returns?\s*>\s*0\.0?5",
    r"R[²2]\s*>\s*0?\.0?5",
]
LITERAL_STRINGS = ["5% R2", "5% R²", "five percent R"]
```
Scan: `services/tournament-harness/app/`, `services/tournament-harness/tests/` (with self-allowlist), `.github/workflows/tournament*.yml`.

### CD-10 (auto-merge ban)
```python
PATTERN = r"gh\s+pr\s+merge"
```
Scan: `services/tournament-harness/`, `.github/workflows/`.

### B1 (klines is_mainnet filter)
```python
KLINES_PATTERNS = [
    re.compile(r"\bFROM\s+klines\b", re.IGNORECASE),
    re.compile(r"\bSELECT[^;]*\bklines\b", re.IGNORECASE | re.DOTALL),
]
MAINNET_FILTER_PATTERN = re.compile(r"is_mainnet", re.IGNORECASE)
NEIGHBORHOOD_LINES = 5
```
Scan: `services/tournament-harness/app/`. Pins `app/runner/data.py` SQL retains `is_mainnet = TRUE`.

### B2 (no parallel metric reimplementations — strengthened)
```python
DEF_PATTERN = r"def\s+_?(sharpe|dir_acc|directional_accuracy|deflated|probabilistic_sharpe|compute_returns)\w*\s*\("
LAMBDA_PATTERN = r"lambda\s+\w+\s*:\s*[^,]*\.mean\(\)\s*/\s*\w+\.std"
```
Scan: `services/tournament-harness/app/pr/`, `services/tournament-harness/app/significance/`. Strengthens Phase 3 TOURN-07 with `_?` (catches `_sharpe`) and adds lambda form.

## Self-allowlist mechanism

All four gates filter `/tests/` substring from results. Each test file legitimately references its own forbidden patterns (in `PATTERNS` constants and assertion messages); the `/tests/` filter prevents self-trigger. Belt-and-suspenders: each test also filters `SELF_FILE_BASENAME` from grep output. Each gate has a `test_self_allowlist_works` assertion confirming `/tests/` appears in `Path(__file__).as_posix()` AND that the file contains the forbidden pattern (so the filter is doing real work, not just hiding zero matches).

## Sibling relationship to Phase 3

Phase 3's `test_tourn07_grep_gate.py` was the canonical "code can't sneak past human review" pattern. Phase 4 adds four siblings that all share its shape: build-time grep checks catching comments/strings/docs that runtime assertions would miss. They will all run in the same nightly CI step.

## Forward note (04-06 e2e)

When 04-06 e2e adds a CI workflow file under `.github/workflows/tournament*.yml`, the D-13 gate's `test_no_legacy_r2_in_workflows` will scan it automatically — no test edit needed.

When future plans create `services/tournament-harness/app/pr/` and `services/tournament-harness/app/significance/`, the B2 gate's `test_subprocess_grep_returns_empty` will stop skipping and start enforcing automatically — no test edit needed.

## Commits

| Task | Commit | Message |
|---|---|---|
| 1 | `9237534` | test(04-05): add D-13 R² grep gate (no >5% R² win criterion) |
| 2 | `63de38d` | test(04-05): add CD-10 no-auto-merge grep gate |
| 3 | `47d363f` | test(04-05): add B1 klines is_mainnet filter regression gate |
| 4 | `b7c5154` | test(04-05): add B2 strengthened metric-reimplementation gate (pr/ + significance/) |

## Verification

```bash
PYTHONPATH=services/tournament-harness pytest \
  services/tournament-harness/tests/integration/test_no_legacy_r2_criterion.py \
  services/tournament-harness/tests/integration/test_no_auto_merge.py \
  services/tournament-harness/tests/integration/test_klines_filter_required.py \
  services/tournament-harness/tests/integration/test_no_parallel_metric_reimplementations.py \
  -x -q
# 17 passed, 1 skipped (B2 subprocess grep — pr/ and significance/ not yet created)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] B2 subprocess grep fell back to scanning cwd when scan dirs absent**
- **Found during:** Task 4 verification
- **Issue:** When neither `services/tournament-harness/app/pr/` nor `services/tournament-harness/app/significance/` exists (current state at this point in Phase 4), the constructed `grep -rEn PATTERN` invocation had no path arguments, so grep fell back to recursing the current working directory and matched 18 unrelated lines in `.claude/skills/trading-strategy-dev/references/leakage-tests.md` (legitimate reference docs containing `def deflated_sharpe(`).
- **Fix:** Added a guard at the top of `test_subprocess_grep_returns_empty` that skips with a clear message when neither directory exists; once Phase 4 plan 04-06+ creates `pr/` or `significance/`, the test will automatically resume enforcement.
- **Files modified:** `services/tournament-harness/tests/integration/test_no_parallel_metric_reimplementations.py`
- **Commit:** `b7c5154` (folded into the same task commit, not a separate fix commit)

**2. [Worktree base mismatch — pre-flight]**
- **Found during:** First commit attempt
- **Issue:** Worktree HEAD was at `cdf46a6` (older than `EXPECTED_BASE=7af891b` from the prompt's worktree-branch-check); the harness directory the plan targets (`services/tournament-harness/`) does not exist at that revision. Additionally, the `tests/smoke/` directory required by the `pre-commit-smoke-check.sh` PreToolUse hook is not on the worktree branch.
- **Fix:** Ran the `git reset --hard 7af891b` step from the worktree-branch-check script (which surfaced `services/tournament-harness/`), and copied `tests/smoke/` from the main repo into the worktree as untracked files (added by the smoke hook's discovery, never staged into commits — `git status` confirms `tests/smoke/` remains `??` throughout).
- **Files modified:** None (operational reset + untracked copy only).
- **Commit:** N/A (pre-flight environment setup; not a deviation in plan content).

## Self-Check: PASSED

- All four test files exist at the planned paths.
- All four task commits present in `git log` (`9237534`, `63de38d`, `47d363f`, `b7c5154`).
- Combined pytest run: 17 passed, 1 skipped (expected pre-pr/-creation skip).
- Worktree HEAD correctly on `worktree-agent-a0232bf13bf5da6ae` per per-agent namespace.
- No `tests/smoke/` files staged in any of the four task commits (`git show --stat` confirms only the four test files were added).
