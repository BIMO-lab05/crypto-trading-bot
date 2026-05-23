---
phase: 13-bybit-connector-market-data-centralization
plan: 02
subsystem: testing
tags: [bybit-connector, ci, grep-gate, tdd, github-actions, pytest]

# Dependency graph
requires:
  - phase: 13-bybit-connector-market-data-centralization
    provides: D-05 / D-06 (CI grep gate scope and banned-pattern spec from 13-CONTEXT.md)
provides:
  - "tests/ci/test_no_bybit_bypass.py — the BC-03 grep gate, intentionally RED on main today (20 violations across 17 files)"
  - ".github/workflows/bybit-bypass-gate.yml — required CI workflow blocking PR merge on violations"
  - "tests/ci/__init__.py — pytest collection shim for the new directory"
  - "20-site RED inventory documented below for Wave 1+2 completion verification"
affects: [13-03 ml-prediction-service-orderbook, 13-04 scripts-refactor, 13-05 backtesting-refactor, 13-06 rotate-secrets, 13-07 market-data-config-fix, 13-08 binance-archival, all future BC-02 refactor plans]

# Tech tracking
tech-stack:
  added:
    - "pytest dual-form grep gate (pathlib rglob + subprocess grep with Python post-filter for parity)"
    - "GitHub Actions standalone-job workflow pattern (mirrors .github/workflows/tournament-harness.yml)"
  patterns:
    - "Pre-resolved EXEMPT_PREFIXES (string prefix) instead of per-file Path.resolve() — required on WSL2 where per-file stat is slow (~8s vs ~0s)"
    - "Dual-form scan with post-filtering in Python — GNU grep --exclude-dir matches basenames only, so post-filter in the test guarantees parity"
    - "Set-equality between pathlib and grep scans — works in both RED and GREEN states"
    - "Self-reference avoidance — gate file's own docstring cannot contain banned literals (Pitfall 4 in 13-RESEARCH.md)"

key-files:
  created:
    - "tests/ci/__init__.py"
    - "tests/ci/test_no_bybit_bypass.py"
    - ".github/workflows/bybit-bypass-gate.yml"
  modified: []

key-decisions:
  - "Standalone workflow (Pattern A from PATTERNS.md) over extending an existing CI workflow — gate is contract-level for the phase and must remain visible and required even during its RED window"
  - "String-prefix exempt check over per-file Path.resolve() — performance fix discovered during Task 1 verification (WSL2 stat too slow); REPO_ROOT resolved once at module import is sufficient"
  - "Post-filter grep stdout in Python rather than rely on GNU grep --exclude-dir — guarantees the pytest scan and subprocess grep agree by construction (GNU grep --exclude-dir matches basenames only, so the path-form arguments in PLAN Step 4 would have silently excluded nothing)"
  - "Set-equality assertion in Test 2 rather than 'stdout is empty' — required because the test must pass on both RED main (both sets non-empty + equal) and post-Wave-2 GREEN (both sets empty)"
  - "Add LSTM archive path to known_future in Test 3 — it does not yet exist on the worktree base (the CLAUDE.md claim about a prior LSTM archive does not currently match the filesystem)"
  - "Rewrite gate-file docstring to NOT contain banned URL literals — the alternative (allowlist the gate file in EXEMPT_FILES) would mean the gate explicitly does not check itself, which weakens the contract"

patterns-established:
  - "BC-03 grep-gate idiom: pathlib rglob + subprocess grep, post-filter both with the same _is_exempt helper, assert set equality — reusable for any future 'no direct X outside service-Y' CI gate"
  - "Workflow-comment block at top of standalone gate workflows documenting (a) the contract, (b) why standalone vs extended, (c) security posture for first-party-actions-only workflows"

requirements-completed: [BC-03]

# Metrics
duration: 23min
completed: 2026-05-21
---

# Phase 13 Plan 02: BC-03 CI Grep Gate Summary

**Pytest dual-form grep gate at `tests/ci/test_no_bybit_bypass.py` plus standalone GitHub Actions workflow `.github/workflows/bybit-bypass-gate.yml`, intentionally RED on main today (20-violation inventory across 17 files) — flips GREEN as Wave 1 (BC-02 refactor plans) and Wave 2 (BC-04 archival) close out the inventory.**

## Performance

- **Duration:** ~23 min
- **Started:** 2026-05-21T19:25:00Z
- **Completed:** 2026-05-21T19:48:15Z
- **Tasks:** 2
- **Files created:** 3
- **Files modified:** 0

## Accomplishments

- BC-03 grep gate landed at `tests/ci/test_no_bybit_bypass.py` with the four banned patterns from CONTEXT D-05 (`pybit_import`, `mainnet_rest_url`, `testnet_rest_url`, `wss_stream_url`).
- Dual-form scan: pathlib `rglob` + subprocess `grep -rEn`, both post-filtered with the same `_is_exempt` helper for guaranteed parity. Set-equality assertion works in both RED and GREEN states (defence-in-depth against scan-set drift).
- File-level allowlist for `tests/smoke/test_smoke.py` documented and asserted by a dedicated test (its `test_no_testnet_url_in_root_env_example` enumerates the literal `api-testnet.bybit` inside a forbidden-token list — security assertion, not a bypass call).
- Exempt-path rot detector (`test_exempt_paths_exist_or_are_known_future_paths`) accepts `_archive_exchanges/` and `_archive_lstm/` as known-future targets that BC-04 (and a future LSTM archival commit) will land.
- Required CI workflow at `.github/workflows/bybit-bypass-gate.yml` invoking the gate on every `pull_request` and `push` to `main`. No `continue-on-error: true`. First-party actions only — zero command-injection surface.
- Initial 20-site RED inventory captured below as the load-bearing artifact for Wave 1 + Wave 2 completion verification.

## Task Commits

1. **Task 1: `tests/ci/__init__.py` + `tests/ci/test_no_bybit_bypass.py`** — `23213d5` (test)
2. **Task 2: `.github/workflows/bybit-bypass-gate.yml`** — `1e72e93` (feat)

**Plan metadata commit:** `4c310b3` (this SUMMARY)

_Note: this plan has `type: tdd`. The RED test is the contract — there is no GREEN commit for Test 1 inside this plan. GREEN transitions land in subsequent BC-02 refactor plans (Wave 1) and BC-04 archival (Wave 2)._

## Files Created/Modified

- `tests/ci/__init__.py` — Pytest collection shim for the new `tests/ci/` directory.
- `tests/ci/test_no_bybit_bypass.py` — The grep gate. Four tests: Test 1 (RED today, contract for the phase), Tests 2-4 (defence-in-depth, all GREEN).
- `.github/workflows/bybit-bypass-gate.yml` — Required CI workflow invoking the gate on every PR to and push to `main`.

## Test 1 RED Inventory — 20 violations across 17 files

This is the load-bearing artifact for Wave 1 + Wave 2 completion verification. Each subsequent BC-02 refactor plan and BC-04 archival plan MUST reduce this set to empty. Captured from `pytest tests/ci/test_no_bybit_bypass.py::test_no_bybit_bypass_in_python_code -v` against worktree base `df6f42e`:

| # | File | Line | Pattern | Snippet |
|---|------|------|---------|---------|
| 1 | `backtesting/bybit_data_fetcher.py` | 36 | `testnet_rest_url` | `self.base_url = "https://api-testnet.bybit.com"` |
| 2 | `backtesting/bybit_data_fetcher.py` | 38 | `mainnet_rest_url` | `self.base_url = "https://api.bybit.com"` |
| 3 | `infrastructure/scripts/rotate_secrets.py` | 232 | `pybit_import` | `from pybit.unified_trading import HTTP` |
| 4 | `infrastructure/scripts/rotate_secrets.py` | 234 | `mainnet_rest_url` | `base_url = "...api-testnet.bybit.com" if testnet else "https://api.bybit.com"` |
| 5 | `infrastructure/scripts/rotate_secrets.py` | 234 | `testnet_rest_url` | (same line, two patterns matched) |
| 6 | `scripts/collect_180_days_data.py` | 56 | `mainnet_rest_url` | `BYBIT_API_URL = "https://api.bybit.com"` |
| 7 | `scripts/collect_6months_for_ml.py` | 28 | `mainnet_rest_url` | `self.base_url = "https://api.bybit.com"` |
| 8 | `scripts/collect_bybit_direct_180days.py` | 59 | `mainnet_rest_url` | `BYBIT_API_ENDPOINT = 'https://api.bybit.com'` |
| 9 | `scripts/collect_ml_training_data_simple.py` | 18 | `pybit_import` | `from pybit.unified_trading import HTTP` |
| 10 | `scripts/data_quality_enhancement.py` | 72 | `mainnet_rest_url` | `self.bybit_base_url = 'https://api.bybit.com'` |
| 11 | `scripts/fetch_real_historical_data.py` | 31 | `mainnet_rest_url` | `self.base_url = "https://api.bybit.com"` |
| 12 | `scripts/test_public_bybit_api.py` | 21 | `mainnet_rest_url` | `api_url = "https://api.bybit.com/v5/market/klines"` |
| 13 | `services/market-data-service/tests/test_pagination_fix.py` | 36 | `mainnet_rest_url` | `BYBIT_API_URL = "https://api.bybit.com"` |
| 14 | `services/ml-prediction-service/app/handlers/orderbook.py` | 262 | `mainnet_rest_url` | `url = "https://api.bybit.com/v5/market/orderbook"` |
| 15 | `services/ml-prediction-service/download_final_4.py` | 18 | `mainnet_rest_url` | `BYBIT_API = "https://api.bybit.com/v5/market/kline"` |
| 16 | `services/ml-prediction-service/download_missing_symbols_data.py` | 43 | `mainnet_rest_url` | `BYBIT_API_URL = "https://api.bybit.com"` |
| 17 | `services/ml-prediction-service/download_op_sui_6months.py` | 30 | `mainnet_rest_url` | `url = "https://api.bybit.com/v5/market/kline"` |
| 18 | `services/ml-prediction-service/download_suiusdt_12months.py` | 39 | `mainnet_rest_url` | `url = "https://api.bybit.com/v5/market/kline"` |
| 19 | `shared/health_check.py` | 771 | `mainnet_rest_url` | `base_url = "...api-testnet.bybit.com" if testnet else "https://api.bybit.com"` |
| 20 | `shared/health_check.py` | 771 | `testnet_rest_url` | (same line, two patterns matched) |

### Notable: `shared/health_check.py` is a scope-creep discovery

`shared/health_check.py:771` is NOT enumerated in 13-CONTEXT.md's "In scope" list nor in the 13-ROADMAP.md initial audit. It is a real bypass site that the gate (correctly) caught: an auth-ping helper that switches between testnet and mainnet REST URLs based on a `testnet` flag, structurally identical to the `rotate_secrets.py` pattern (CONTEXT D-07). Wave 1 must pick this up — recommend bundling into the same BC-02 refactor plan that handles `rotate_secrets.py`, or creating a new BC-02 sub-task. **Surface to orchestrator for Wave 1 scoping decision.**

## Decisions Made

- **Standalone workflow over extending `.github/workflows/ci.yml`.** Pattern A from 13-PATTERNS.md. Reason: the gate is a contract-level invariant for the entire phase and must remain visible and required throughout the Wave 1+2 RED window. Folding it into a multi-job CI workflow risks future contributors silently disabling it.
- **String-prefix exempt check, not `Path.resolve()` per file.** Discovered during Task 1 verification — per-file `resolve()` on WSL2 pushed runtime from ~4s to >60s (timed out). REPO_ROOT is resolved once at module import; subsequent `rglob` returns absolute paths derived from it, so string-prefix comparison is reliable for our use case (no internal symlinks-to-directories in the tracked tree).
- **Post-filter grep stdout in Python rather than rely on GNU grep `--exclude-dir`.** Per the advisor's first call: GNU grep `--exclude-dir=PAT` matches directory basenames only — `--exclude-dir=services/bybit-connector` excludes nothing because no directory is literally named `services/bybit-connector`. The PLAN's Step 4 grep command would have silently excluded zero paths. Post-filtering both scans with the same `_is_exempt` helper guarantees parity by construction.
- **Set-equality Test 2 assertion, not "stdout is empty".** Required so the dual-form scan works in both RED main (both sets non-empty + equal) and post-Wave-2 GREEN (both sets empty + equal). PLAN Step 4's "stdout is empty" framing was the trivial sub-case, not the assertion shape.
- **Add `_archive_lstm/` to known_future in Test 3 alongside `_archive_exchanges/`.** Verified absent on the worktree base — the CLAUDE.md claim about "LSTM archived under `_archive_lstm/`" does not currently match filesystem reality. Both archive paths are now documented as future targets, so Test 3 passes today and remains passable after either archive lands.
- **Rewrite gate-file docstring to remove the `wss://stream.bybit` literal.** Pitfall 4 in 13-RESEARCH.md flagged this exact risk. Alternative (allowlist the gate file in EXEMPT_FILES) would weaken the contract — gate cannot validate itself. Substituted prose ("a Bybit WebSocket stream URL") that conveys the same meaning without the matched literal.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PLAN Step 4 grep command would have silently excluded zero paths**

- **Found during:** Task 1 (Test 2 implementation)
- **Issue:** PLAN Step 4 specified `--exclude-dir=services/bybit-connector` etc. GNU grep's `--exclude-dir=PAT` matches directory **basenames** (single path components), not paths. None of the four path-form arguments exclude any directory. The grep would have walked the entire repo including `services/bybit-connector/` itself — Test 2 would have failed every run because the grep stdout would contain matches the pytest scan correctly excluded.
- **Fix:** Removed the broken `--exclude-dir=` arguments. Post-filter grep stdout in Python using the same `_is_exempt` helper as the pathlib scan. Two scans now agree by construction. Also implemented Test 2 as set-equality rather than "stdout is empty" so it works in both RED and GREEN states.
- **Files modified:** `tests/ci/test_no_bybit_bypass.py` (within Task 1 commit)
- **Verification:** Test 2 passes (`pytest test_grep_command_matches_pytest_scan -v` GREEN on RED main).
- **Committed in:** `23213d5` (Task 1 commit)

**2. [Rule 3 - Blocking] Per-file `Path.resolve()` made the gate hang on WSL2**

- **Found during:** Task 1 verification (initial `pytest tests/ci/test_no_bybit_bypass.py` timed out at 60s)
- **Issue:** The first implementation called `.resolve()` per file inside `_is_exempt` (1011 files × 4 EXEMPT_PATHS resolutions ≈ 4,000 WSL2 filesystem stats). Hot loop took 8+ seconds for the exempt check alone, and the wrapped subprocess grep parser brought total runtime past 60s. The PLAN allowed up to 30s and CI minutes are not free.
- **Fix:** Pre-compute `_EXEMPT_PREFIXES` (tuple of `str(p) + '/'` for each exempt path) at module import. `_is_exempt` now uses `str(path).startswith(_EXEMPT_PREFIXES)` — zero per-file syscalls. REPO_ROOT is still `.resolve()`-d once at module import to handle the worktree symlinks, but all derived paths use that resolved root unchanged. Runtime dropped from >60s timeout to ~13s (and Tests 2-4 run in 7s).
- **Files modified:** `tests/ci/test_no_bybit_bypass.py` (within Task 1 commit)
- **Verification:** `timeout 30 pytest tests/ci/test_no_bybit_bypass.py -v` completes well under timeout; full suite runs in 13s.
- **Committed in:** `23213d5` (Task 1 commit)

**3. [Rule 2 - Missing Critical] Gate file would have fired on itself**

- **Found during:** Task 1 verification (first full run showed 21 violations — one of them was `tests/ci/test_no_bybit_bypass.py:8` itself)
- **Issue:** The gate's module-level docstring originally contained the literal `wss://stream.bybit` to document the contract. That literal matched the `wss_stream_url` regex, so the gate fired on itself — a circular failure that would persist forever even after Wave 2 GREEN.
- **Fix:** Rewrite the docstring to describe the violation in prose ("opens a Bybit WebSocket stream URL directly") without reproducing the literal URL. Added an explicit pointer to Pitfall 4 in 13-RESEARCH.md so a future maintainer understands why the docstring is paraphrased.
- **Files modified:** `tests/ci/test_no_bybit_bypass.py` (within Task 1 commit)
- **Verification:** `grep -nE "https?://api(-testnet)?\.bybit\.com|wss?://stream(-testnet)?\.bybit|from pybit|import pybit" tests/ci/test_no_bybit_bypass.py` returns empty; full pytest run shows 20 violations (not 21).
- **Committed in:** `23213d5` (Task 1 commit)

**4. [Rule 3 - Blocking] PLAN's known_future set was missing `_archive_lstm/`**

- **Found during:** Task 1 (Test 3 implementation)
- **Issue:** PLAN Step 5 specified `known_future = {REPO_ROOT/'_archive_exchanges'}`. EXEMPT_PATHS also includes `services/ml-prediction-service/models/_archive_lstm/` (documented in CLAUDE.md as a prior LSTM archive). Verified `find` and `ls`: that directory does not exist on the worktree base. With `_archive_lstm/` in EXEMPT_PATHS but neither existing nor in known_future, Test 3 would have failed on the first run with `EXEMPT_PATHS rot — entries neither exist nor are documented as known-future archive targets`.
- **Fix:** Expand `known_future` to include both `_archive_exchanges/` (BC-04 will land it) and `_archive_lstm/` (a future LSTM cleanup commit will land it). Both are documented in the test docstring.
- **Files modified:** `tests/ci/test_no_bybit_bypass.py` (within Task 1 commit)
- **Verification:** Test 3 passes on the worktree base.
- **Committed in:** `23213d5` (Task 1 commit)

### Plan Inconsistencies (NOT auto-fixed; documented for plan-checker follow-up)

**P-1: PLAN frontmatter acceptance criterion `grep -c "BANNED_PATTERNS" == 1` is contradicted by the must_haves `contains: "BANNED_PATTERNS"` (≥1) clause.**

The natural shape of the gate file defines `BANNED_PATTERNS` once and iterates over it in `_scan_py_files`, `test_grep_command_matches_pytest_scan`, and the dict comprehension that builds the regex set — so `grep -c "BANNED_PATTERNS"` is **4**, not 1. The `must_haves` block in the same frontmatter requires only presence (`contains: "BANNED_PATTERNS"`), which `4 ≥ 1` satisfies. Reading both lines together, the `== 1` is most likely a typo (should be `≥ 1`); rewriting the gate to a single occurrence would force pattern repetition. Plan executor proceeded with the natural shape; verify in plan-checker that the `== 1` acceptance line was a typo and update.

---

**Total deviations:** 4 auto-fixed (1 bug, 2 blocking, 1 missing-critical) + 1 documented plan inconsistency.
**Impact on plan:** All four auto-fixes were necessary for the gate to function correctly on the worktree base. No scope creep — every fix stayed within the file changes already required by the plan. The 20-site RED inventory matches the expected ROADMAP §"Phase 13" initial audit shape (plus the `shared/health_check.py` scope-creep discovery flagged above).

## Issues Encountered

- **GitHub Actions workflow Write blocked once by security-reminder hook.** First Write attempt to `.github/workflows/bybit-bypass-gate.yml` was blocked by a pre-tool hook flagging command-injection patterns (default workflow security guidance). Re-tried the write after confirming the workflow has zero `${{ github.event.* }}` substitutions; second attempt succeeded. Added an explicit security-posture comment block at the top of the workflow so a future reviewer can see the analysis without re-deriving it.

## User Setup Required

None — gate is wired into the GitHub Actions CI; nothing for the operator to install or configure.

## Next Phase Readiness

- **Ready for Wave 1 (BC-02 refactor plans):** Each Wave 1 plan can verify completion by re-running `pytest tests/ci/test_no_bybit_bypass.py::test_no_bybit_bypass_in_python_code -v` and confirming the violation count decreases by the expected delta. Wave 1 finishes when the count is 1 (just `shared/health_check.py` or whichever site is intentionally last) and Wave 2 archives the remaining Binance-adjacent code.
- **Blocker surfaced upward:** `shared/health_check.py:771` is a Wave-1 scope-creep discovery (not in CONTEXT.md enumeration). Recommend orchestrator add a sub-task to whichever Wave 1 plan handles `infrastructure/scripts/rotate_secrets.py` (CONTEXT D-07) — pattern is structurally identical (testnet/mainnet URL switch on a `testnet` flag).
- **Self-check (post-write):** all three created files exist on disk; both task commits present in `git log`.

## Threat Flags

None — gate adds a defensive surface (CI pre-merge check). No new external surface introduced. Threat register entries T-BC03-LeakedBypass / T-BC03-EmptyExempt / T-BC03-FalsePositive from PLAN are all mitigated (see Decisions Made above for the mitigation mapping).

## Self-Check: PASSED

- `tests/ci/__init__.py` — FOUND
- `tests/ci/test_no_bybit_bypass.py` — FOUND (347 lines; line count ≥ 70 acceptance criterion satisfied)
- `.github/workflows/bybit-bypass-gate.yml` — FOUND
- `.planning/phases/13-bybit-connector-market-data-centralization/13-02-SUMMARY.md` — FOUND (this file)
- Task 1 commit `23213d5` — FOUND in `git log`
- Task 2 commit `1e72e93` — FOUND in `git log`
- Final gate suite behavior: Test 1 RED (1 failed), Tests 2-4 GREEN (3 passed) in 13.09s — matches the PLAN's RED-by-design contract.

---
*Phase: 13-bybit-connector-market-data-centralization*
*Completed: 2026-05-21*
