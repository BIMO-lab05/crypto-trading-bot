---
phase: 10-path-to-live-dashboard
plan: 03
subsystem: testing
tags:
  - smoke
  - playwright
  - ci
  - grep-gates
  - phase-10
  - dashlive

dependency_graph:
  requires:
    - 10-01: GET /api/preflight/carry-ins endpoint shape + .planning/state/carry_ins.json (smoke asserts schema, fast-forward writes state)
    - 10-02: PathToLiveTile component data-testid selectors (smoke targets path-to-live-tile, path-to-live-banner, path-to-live-check-*, path-to-live-carry-in-*)
    - 08-02: /api/preflight/live-readiness endpoint (smoke cross-references chip status)
    - 09-02: MLGATE auto-flip + leaderboard schema (leaderboard_dsr_seeded fixture)
  provides:
    - pytest-playwright Chromium smoke covering all 7 D-10-18 assertions
    - Two defence-in-depth grep gates (PathToLiveTile + carry-ins literals)
    - .github/workflows/dashboard-smoke.yml — PR-paths-filtered CI smoke
    - tests/e2e/fixtures/test-live-trading.override.yml — D-10-18 #7 LIVE-mode override
  affects:
    - tests/e2e/conftest.py (extended with leaderboard_dsr_seeded + all_preflight_checks_passing fixtures + pytest_plugins re-export)

tech_stack:
  added:
    - pytest-playwright Chromium driver (CI only, installed via playwright install --with-deps chromium)
    - Compose override pattern for trading-engine LIVE-mode env injection (PAPER_TRADING_MODE/TRADING_MODE/LIVE_TRADING_ACK/MAX_POSITION_RISK_PCT)
  patterns:
    - Dual-form grep gate (pathlib.rglob + subprocess grep) verbatim from test_preflight_grep_gates.py
    - PR paths filter listing all six D-10-19 paths (no nightly cron — Phase 12 owns nightly cadence)
    - PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 fast-forward env override for 24h-window smoke (D-10-09)
    - pytest_plugins re-export to extend tests/e2e/conftest.py without overwriting the existing async/httpx ServiceClient suite (PATTERNS.md divergence #2)

key_files:
  created:
    - tests/e2e/fixtures/test-live-trading.override.yml (14 lines — LIVE-mode trading-engine env override, MARKET_DATA_SOURCE intentionally absent for tape safety)
    - tests/e2e/test_path_to_live_smoke.py (290 lines — 4 test functions covering D-10-18 #1..#7)
    - tests/integration/test_dashlive_grep_gates.py (144 lines — two CI-enforced regression gates)
    - .github/workflows/dashboard-smoke.yml (89 lines — PR paths filter + workflow_dispatch only)
  modified:
    - tests/e2e/conftest.py (681 lines total; +393 -54 — pytest_plugins re-export, leaderboard_dsr_seeded fixture, all_preflight_checks_passing fixture)

key_decisions:
  - "D-10-18 split into 4 test functions (not one mega-test) so individual failures point to the exact assertion broken"
  - "leaderboard_dsr_seeded seeds dsr=0.97 + run_date=today + psr_ci_published=1 + status='success' + restarts trading-engine with ENABLE_ML_PREDICTIONS=true so DSR row chip flips PASS"
  - "all_preflight_checks_passing uses committed override file (not inline env injection) so CI run is reproducible from operator console — `docker compose -f docker-compose.unified.yml -f tests/e2e/fixtures/test-live-trading.override.yml up -d --force-recreate trading-engine`"
  - "Dashboard-smoke workflow does NOT include schedule cron — nightly cadence is explicitly deferred to Phase 12 per 10-CONTEXT.md Deferred Ideas, keeping deterministic CI lane unblocked"
  - "Pinned actions @v4/@v5 verbatim from preflight-live-readiness.yml per STATE.md decision 08-04 (supply-chain mitigation T-08-04-01)"

patterns_established:
  - "Pattern: pytest_plugins = ['tests.integration.conftest'] re-export — extends fixture surface without overwriting the existing async/httpx ServiceClient conftest"
  - "Pattern: Compose override file pattern for env injection — trading-engine only, MARKET_DATA_SOURCE intentionally absent so tape mode is preserved (no Bybit calls fire from LIVE-flip smoke)"
  - "Pattern: PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 fast-forward override — D-10-18 #7 24h window completes in 2s instead of 86400s"
  - "Pattern: PR paths filter as smoke-trigger discipline — workflow runs ONLY when one of six DASHLIVE-relevant paths changes, avoiding noise from unrelated PRs"

deviations_from_plan:
  - issue: "Plan's Task 2 automated verify script uses greedy `next((s for s in steps if 'pytest' in s.get('run','')))` which matched the `pip install pytest-playwright` step instead of the smoke step"
    resolution: "Restructured workflow install — base playwright/httpx in earlier step (no `pytest` literal), pytest-playwright + smoke run merged into single step (only step with `pytest` literal). Acceptance criteria still satisfied: workflow runs exact `pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v` command once"
  - issue: "Plan execution stream truncated after Task 1 commit (c45fe5a) due to harness stream-idle-timeout; tests/integration/test_dashlive_grep_gates.py was written to disk by the agent but not committed"
    resolution: "Orchestrator finished Task 2 inline — staged the orphan grep gates file + wrote dashboard-smoke.yml + ran task 2 verify (OK) + ran grep gates (2 passed) + committed as test(10-03)"

requirements_completed:
  - DASHLIVE-01
  - DASHLIVE-02
  - DASHLIVE-03
  - DASHLIVE-04

duration: ~30 min (15 min agent task 1 + 15 min orchestrator task 2 + summary)
completed: 2026-05-17
---

# Phase 10 Plan 03: Verification Surface

**Shipped pytest-playwright smoke covering all 7 D-10-18 assertions, two defence-in-depth grep gates, and a paths-filtered CI workflow that runs the smoke on PR.**

## Performance

- **Duration:** ~30 min (Task 1: ~15 min agent; Task 2: ~15 min orchestrator after stream truncation)
- **Started:** 2026-05-17T19:09Z (10-03 agent dispatched)
- **Completed:** 2026-05-17T20:?? (Task 2 orchestrator-finished)
- **Tasks:** 2/2
- **Files modified:** 5 (4 created + 1 extended)

## Accomplishments

- All 7 D-10-18 smoke assertions covered (tile visible, 6 PREFLIGHT chip rows, 5 carry-in rows, banner matches endpoint `overall`, schema v1 + 6 top-level keys, DSR row schema, 24h window fast-forward to READY)
- Two CI-enforced grep gates green against the post-10-01 + 10-02 codebase (2 passed, 1.87s)
- Dashboard-smoke CI workflow validates: pull_request paths filter with all six D-10-19 paths, workflow_dispatch, no schedule cron (Phase 12 deferred), pinned actions @v4/@v5
- LIVE-mode override file committed for reproducible D-10-18 #7 fast-forward (trading-engine only, MARKET_DATA_SOURCE absent → tape safety preserved)

## Task Commits

1. **Task 1: smoke fixtures + override + path-to-live smoke** — `c45fe5a` (test)
2. **Task 2: grep gates + dashboard-smoke CI workflow** — `5d38f99` (test)

## Files Created/Modified

- `tests/e2e/fixtures/test-live-trading.override.yml` — LIVE-mode trading-engine env override; MARKET_DATA_SOURCE intentionally absent so tape mode is preserved (no Bybit calls fire from LIVE-flip smoke)
- `tests/e2e/test_path_to_live_smoke.py` — 4 test functions covering D-10-18 #1..#7
- `tests/e2e/conftest.py` — extended via pytest_plugins re-export + leaderboard_dsr_seeded + all_preflight_checks_passing fixtures
- `tests/integration/test_dashlive_grep_gates.py` — two grep gates (PathToLiveTile + carry-ins)
- `.github/workflows/dashboard-smoke.yml` — PR paths filter + workflow_dispatch + concurrency + security-note block

## Decisions Made

See `key_decisions` in frontmatter — five decisions, all documented inline.

## Deviations from Plan

See `deviations_from_plan` in frontmatter — two deviations, both documented:
1. Reordered install step to satisfy plan's buggy `next()` verify script without changing acceptance criteria
2. Orchestrator finished Task 2 inline after agent stream truncation

## Verification

- `pytest tests/integration/test_dashlive_grep_gates.py -v` — **2 passed in 1.87s** (green against post-Wave-1 codebase)
- `python3 -c "import ast,yaml; ast.parse(...); yaml.safe_load(...)"` task 2 verify — **OK**
- YAML schema valid (pull_request paths + workflow_dispatch + no schedule)
- Smoke step runs exact required command: `pytest tests/e2e/test_path_to_live_smoke.py --screenshot=only-on-failure --video=retain-on-failure -v`
- PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 env set in Boot step (D-10-09 fast-forward)

## Open Items

- Live CI run on a real PR — workflow has not yet been triggered by a path-matching PR. Will fire on the merge PR for this branch.
- D-10-18 smoke not run end-to-end locally (no Chromium driver in this WSL2 environment, no full stack boot). Workflow runs it in ubuntu-latest. Local run can be done via `docker compose -f docker-compose.unified.yml up -d` + `playwright install chromium` + `pytest tests/e2e/test_path_to_live_smoke.py`.

## Self-Check: PASSED
